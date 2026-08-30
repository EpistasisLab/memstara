#!/usr/bin/env python3
"""ML-tool MCP server — train on a sub-dataset, return AUC and feature importance.

The meeting never settled on an engine — *"XGBoost, whatever we decide to do"*. So
the engine is swappable through `MEMSTARA_ML_ENGINE`. Changing it touches neither the
agent definitions nor the pipeline.

    MEMSTARA_ML_ENGINE   sklearn_hgb (default) | random_forest | xgboost
    MEMSTARA_OUTPUT_DIR  the only directory inputs may come from (default: outputs/ beside this file)

The default is scikit-learn to keep the install small — one package and it runs.
xgboost is optional and only fails if you select that engine.

WARNING: env vars must be on the allowlist to reach this process — see
`mcp_allowed_env_vars` in `sandbox/settings.py`.


==============================================================================
 이 파일을 읽는 법
==============================================================================

 학습 담당 도구 서버. 겉으로 보이는 도구는 **하나뿐**이다.

   train_and_score(path, y_column)   작은 CSV 로 모델을 학습하고 AUC 를 돌려준다

 안에서 부르는 도우미 둘:
   _make_model(engine)      엔진 이름 → 실제 모델 객체
   _importance(model, ...)  어느 컬럼이 얼마나 기여했나

 흐름:
   ① 경로가 허용된 폴더 안인가 (보안 검사)
   ② CSV 를 읽는다
   ③ 문자열 컬럼을 숫자로 편다 (원-핫)
   ④ 학습/시험으로 나눈다
   ⑤ 학습하고 AUC 를 잰다
   ⑥ 중요도를 뽑는다

 AUC 는 0.5 가 동전 던지기, 1.0 이 완벽이다. 0.64 면 "약간의 신호는 있다" 정도.

 사람이 직접 불러 보려면: `python debug_harness.py ml`
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from mcp.server.fastmcp import FastMCP

# 자식 프로세스라 부모 디버거가 안 닿는다. MEMSTARA_DEBUGPY 에 이 서버 이름이
# 들어 있을 때만 디버거를 기다린다 — 없으면 아무 일도 하지 않는다. debug_hook.py 참고.
from debug_hook import quiet_child, wait_for_debugger

quiet_child()          # 자식이 켜질 때 찍는 잡음 세 가지를 끈다
wait_for_debugger('memstara-ml')

mcp = FastMCP("memstara-ml")

_DEFAULT_OUT = Path(__file__).parent / "outputs"


def _output_dir() -> Path:
    """읽어도 되는 유일한 폴더. resolve() 로 심볼릭 링크까지 펴서 실제 경로로 만든다."""
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or _DEFAULT_OUT).resolve()


def _make_model(engine: str) -> Any:
    """Build a model for the named engine.

    Imports are deferred so that a missing optional engine does not prevent the
    server from starting.

    ↑ import 를 함수 **안**에 둔 이유: xgboost 가 안 깔려 있어도 서버는 떠야 한다.
      맨 위에 두면 xgboost 를 안 쓰는 사람까지 설치해야 한다.
    """
    if engine == "sklearn_hgb":
        # 기본값. 히스토그램 기반 그래디언트 부스팅.
        # **결측(NaN)을 그대로 처리한다** — NHANES 처럼 30% 가 비어도 안 터진다.
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=0)
    if engine == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(n_estimators=300, random_state=0, n_jobs=-1)
    if engine == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(n_estimators=200, max_depth=4, eval_metric="logloss", random_state=0)

    # 오타를 조용히 넘기지 않는다. 무엇을 쓸 수 있는지도 같이 알려 준다.
    raise RuntimeError(f"unknown MEMSTARA_ML_ENGINE: {engine!r} (sklearn_hgb | random_forest | xgboost)")


def _importance(model: Any, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """Extract per-column importance, whichever engine produced the model.

    HistGradientBoosting has no ``feature_importances_``, so fall back to
    permutation importance. Slower, but there are fewer than ten columns here, and
    it yields a comparable quantity across engines.

    ↑ 엔진마다 중요도를 주는 방식이 다르다. 랜덤포레스트·XGBoost 는 자기가 계산해
      들고 있지만, 기본 엔진(HistGradientBoosting)은 없다. 그럴 땐 **순열 중요도**를
      쓴다 — 한 컬럼의 값을 뒤섞어 보고 성능이 얼마나 떨어지는지로 재는 방식이다.
      느리지만 컬럼이 열 개도 안 되고, 엔진이 달라도 서로 비교할 수 있는 값이 된다.
    """
    if hasattr(model, "feature_importances_"):
        # 모델이 이미 들고 있으면 그대로 쓴다.
        return {c: float(v) for c, v in zip(X.columns, model.feature_importances_)}

    from sklearn.inspection import permutation_importance

    # n_repeats=5 — 뒤섞기를 다섯 번 해서 평균. 한 번만 하면 우연에 흔들린다.
    r = permutation_importance(model, X, y, n_repeats=5, random_state=0, scoring="roc_auc")
    return {c: float(v) for c, v in zip(X.columns, r.importances_mean)}


@mcp.tool()
def train_and_score(path: str, y_column: str, test_size: float = 0.25, seed: int = 42) -> str:
    """Train a binary classifier on a sub-dataset and return AUC and feature importance.

    Args:
        path: sub-dataset CSV produced by slice_columns.
        y_column: name of the outcome column.
        test_size: test split fraction (default 0.25).
        seed: random seed, for reproducibility.

    Returns:
        JSON with auc, feature_importance, n_train, n_test and model. Report the
        returned numbers as they stand; do not restate them approximately.

    ↑ 요약: slice_columns 가 만든 작은 CSV 로 학습하고 AUC 를 돌려준다.
      seed 가 고정돼 있어 같은 입력이면 **항상 같은 숫자**가 나온다 — 그래서
      나중에 손으로 다시 채점해 판의 값과 대조할 수 있다.
    """
    # The path check comes FIRST. Putting a security check behind an optional
    # dependency means it is skipped entirely wherever that package is absent,
    # hidden behind an "install scikit-learn" message.
    #
    # ↑ 경로 검사를 **맨 먼저** 한다. 이걸 scikit-learn import 뒤에 두면, 그 패키지가
    #   없는 환경에서는 보안 검사 자체가 건너뛰어진다 — "설치하세요" 메시지 뒤에 숨는다.
    out_dir = _output_dir()
    try:
        p = Path(path).resolve()
        # relative_to 는 p 가 out_dir 아래가 아니면 예외를 던진다.
        # "../../etc/passwd" 같은 경로를 막는 장치다.
        p.relative_to(out_dir)
    except (ValueError, OSError):
        return json.dumps({"error": f"path is outside the allowed directory: {path}", "allowed_dir": str(out_dir)})
    if not p.is_file():
        return json.dumps({"error": f"file not found: {p}"})

    try:
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split
    except ImportError:
        return json.dumps({"error": "scikit-learn is not installed. `pip install scikit-learn`"})

    # 환경변수가 없거나 비어 있으면 기본 엔진.
    engine = os.environ.get("MEMSTARA_ML_ENGINE", "").strip() or "sklearn_hgb"

    try:
        df = pd.read_csv(p)
        if y_column not in df.columns:
            return json.dumps({"error": f"y_column '{y_column}' not found"})

        y = df[y_column]                      # 맞혀야 할 값 (0 또는 1)
        if y.nunique() < 2:
            # 전부 0 이거나 전부 1 이면 배울 것이 없다.
            return json.dumps({"error": "the outcome has only one class; nothing to train"})

        # One-hot so the engine tolerates categorical columns.
        # ↑ 문자열 컬럼을 숫자로 편다. 예: Race1 하나가 Race1_White, Race1_Hispanic …
        #   여러 개로 갈라진다. drop_first=True 는 그중 **한 범주를 기준으로 빼는** 것인데,
        #   그래서 남은 것들의 중요도는 "그 값이 기여한다" 가 아니라 "빠진 범주 대비 차이" 다.
        #   이 점이 해석을 헷갈리게 만든다 — 아직 고치지 않은 자리다.
        X = pd.get_dummies(df.drop(columns=[y_column]), drop_first=True)
        if X.empty or X.shape[1] == 0:
            return json.dumps({"error": "no feature columns"})

        # 학습용과 시험용으로 나눈다. stratify=y 는 양성 비율을 양쪽에 똑같이 맞춘다 —
        # 양성이 10% 뿐인 데이터에서 이게 없으면 시험 쪽에 양성이 거의 안 갈 수 있다.
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y)
        model = _make_model(engine)
        model.fit(X_tr, y_tr)                 # 학습

        # predict_proba 는 [0일 확률, 1일 확률] 를 준다. [:, 1] 로 1일 확률만 뽑는다.
        auc = float(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1]))

        # 중요도는 **시험 데이터**로 잰다. 학습 데이터로 재면 외운 것까지 중요해 보인다.
        importance = _importance(model, X_te, y_te)
    except Exception as e:
        # 무엇이 터졌는지 종류까지 적어 돌려준다. 에이전트가 읽고 판단할 수 있게.
        return json.dumps({"error": f"{type(e).__name__}: {e}"})

    return json.dumps(
        {
            "auc": round(auc, 4),
            # The columns this actually trained on, as the sub-dataset spells them —
            # BEFORE one-hot. Two things need it. First, it is the only place a result
            # can be checked against the hypothesis it is filed under: without it the
            # board records what the data stage said it cut, never what the ml stage
            # read, and a sub-dataset that was overwritten between the two stages scores
            # silently under the wrong row. Second, `feature_importance` is keyed by
            # post-one-hot names (`Race1_White`), which match no column and no knowledge
            # source concept; this keeps the original names in the record beside them.
            #
            # ↑ 한국어 요약: **실제로 학습에 쓴 컬럼**을 원-핫 이전 이름으로 남긴다.
            #   두 가지 때문이다.
            #   ① 결과가 자기 가설의 것인지 대조할 수 있는 **유일한 자리**다. 이게 없으면
            #      판에는 "데이터 단계가 잘랐다고 말한 것" 만 남고 "학습이 실제로 읽은 것"
            #      은 어디에도 없다 — 그 사이에 파일이 덮어써져도 조용히 지나간다.
            #   ② feature_importance 의 키는 원-핫 뒤 이름(`Race1_White`)이라 데이터셋에도
            #      지식원에도 없는 이름이다. 원래 이름을 옆에 같이 남겨 둔다.
            "features": [c for c in df.columns if c != y_column],
            # 중요도가 큰 것부터 정렬해서 돌려준다 — 위에서부터 읽으면 되게.
            "feature_importance": {k: round(v, 5) for k, v in sorted(importance.items(), key=lambda kv: -kv[1])},
            "n_train": int(len(X_tr)),
            "n_test": int(len(X_te)),
            "model": engine,      # 어느 엔진으로 낸 숫자인지 기록에 남긴다
        }
    )


if __name__ == "__main__":
    mcp.run()
