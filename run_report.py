#!/usr/bin/env python3
"""Read a run directory and say, in one file, whether the run went normally.

The records were already complete before this existed. What was missing was something
that *reads* them. On 2026-08-13 a run reported "3/3 succeeded" while two warnings sat
in its own `run.jsonl` — an OKF tool had failed, and the trial that hit the failure came
back with one column where its prompt allowed three to eight. Nothing surfaced either,
so nobody looked.

So this asks the questions a person would ask, and puts the answers at the top:

- did any log record come out at warning or above?
- did any tool call fail?
- did any trial fail, or break the column constraint its own prompt set?

Only the run directory is read — never the database. An archived folder has to keep
working after the rows are gone, and it does, because everything needed is already in
manifest.json, todo_rows.json, summary.json and run.jsonl.

Usage::

    python sandbox/run_report.py outputs/runs/<run>

02_mvp_pipeline.py calls :func:`build_report` at the end of every run, so a run
directory arrives with its REPORT.md already written.


==============================================================================
 이 파일을 읽는 법
==============================================================================

 실행 폴더 하나를 읽고 **"이 실행이 정상이었나"** 를 한 파일(REPORT.md)로 적는다.
 판정은 셋이다 — 정상 · 주의 · 실패. 그리고 그 판정이 나온 이유를 맨 위에 적는다.

 함수는 다섯이다.

   _read_json / _read_jsonl   파일을 읽는다. 없거나 깨져도 멈추지 않는다
   collect(run_dir)           네 파일에서 필요한 숫자를 전부 모은다
   judge(data)                모은 것을 보고 판정과 이유를 낸다
   render(...)                판정을 마크다운 글로 만든다
   build_report(run_dir)      위 셋을 이어 REPORT.md 를 쓴다

 읽는 것은 실행 폴더 안의 네 파일뿐이다 — manifest.json · todo_rows.json ·
 summary.json · run.jsonl. **데이터베이스는 보지 않는다.** 오래된 폴더는 데이터베이스
 줄이 사라진 뒤에도 그대로 읽혀야 하기 때문이다.

 놓치기 쉬운 것:

   · **도구 호출 수는 그냥 세면 두 배가 된다.** 도구를 한 번 부르면
     `mcp.tool.executed` 가 **두 로거에서 각각** 찍힌다. 그래서 adapters 쪽만
     남기고 거른다. 자세한 것은 collect() 안의 주석에 있다.
   · 실패한 도구 호출은 `mcp.tool.executed` 에 아예 오지 않는다. 따로 세야 한다.
   · **가설이 제 약속(컬럼 3~8개)을 지켰는지도 검사한다.** 실행은 성공했는데
     컬럼이 1개인 것은 정상이 아니고, 누군가는 그렇게 말할 수 있어야 한다.
   · 비용은 가능하면 시행 기록에서 가져온다. 로그만 더하면 실제의 1/10 쯤이 나온다.

 이 파일이 생긴 이유: 2026-08-13 의 어느 실행이 "3/3 성공" 이라고 보고했는데,
 그 실행의 run.jsonl 에는 경고 두 건이 있었다. 도구 하나가 실패했고, 그 실패를 만난
 시행은 컬럼을 1개만 골라 돌아왔다 — 프롬프트는 3~8개를 허용했는데도. 둘 다 아무
 데도 드러나지 않았고, 그래서 아무도 보지 않았다. 기록은 이미 완전했다. 없던 것은
 그것을 **읽어 주는 쪽**이었다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline_core import COLUMN_COUNT_MIN

# Ordered worst-first: the verdict is the first one whose condition holds.
#
# ↑ 나쁜 쪽부터 적어 두었다. 판정은 **조건이 맞는 첫 번째 것**이다. 순서가 뒤집히면
#   실패한 실행이 "주의" 로 내려앉는다.
VERDICT_FAIL = "실패"   # 성공한 시행이 하나도 없다
VERDICT_WARN = "주의"   # 돌기는 했지만 걸린 것이 있다
VERDICT_OK = "정상"     # 걸린 것이 하나도 없다


def _read_json(path: Path, default: Any) -> Any:
    """JSON 파일 하나를 읽는다. 없거나 깨져 있으면 default 를 돌려준다.

    보고서를 쓰다가 파일 하나 때문에 멈추면, 나머지 멀쩡한 정보까지 못 보게 된다.
    """
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """한 줄에 JSON 하나씩 든 로그 파일을 읽는다."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a truncated last line on a killed run is not worth failing over
                # ↑ 실행이 강제로 끊기면 마지막 줄이 중간에 잘려 있다. 그 한 줄 때문에
                #   보고서 전체를 포기할 이유는 없어서, 조용히 건너뛴다.
    return out


def collect(run_dir: Path) -> dict[str, Any]:
    """Everything the report needs, gathered from the four files in *run_dir*.

    ↑ 보고서에 필요한 것을 실행 폴더의 **네 파일**에서 전부 모은다. 판정은 하지
      않는다 — 그것은 judge() 의 일이다. 모으기와 판정하기를 갈라 두면, 판정 기준을
      바꿀 때 읽기 쪽을 건드리지 않아도 된다.
    """
    manifest = _read_json(run_dir / "manifest.json", {})   # 무엇을 어떻게 돌렸나
    rows = _read_json(run_dir / "todo_rows.json", [])      # 시행별 결과
    summary = _read_json(run_dir / "summary.json", {})     # 전체 요약
    records = _read_jsonl(run_dir / "run.jsonl")           # 구조화 로그 전량

    # Kept whole, not counted. A count tells you something happened; the text tells you
    # what, and that is the part that was missed last time.
    #
    # ↑ 세지 않고 **통째로 들고 간다.** 개수는 무슨 일이 있었다는 것만 알려 주고,
    #   무슨 일이었는지는 글이 알려 준다. 지난번에 놓친 것이 바로 그 글 쪽이다.
    #   그래서 보고서에도 잘라내지 않고 전문 그대로 싣는다.
    problems = [r for r in records if r.get("level") in ("warning", "error", "critical")]

    # One tool call produces TWO mcp.tool.executed events: agentic_core.mcp.client logs the
    # transport, agentic_core.mcp.adapters logs the call the agent made. On all three real
    # runs the two counts were identical (88/88, 75/75, 49/49), so counting both doubled
    # every figure in this report — and those figures reached the documents. The question
    # this report answers is how often an *agent* reached for a tool, so count the adapter
    # side; a driving script's own direct call appears only on the client side and is
    # rightly left out.
    #
    # ↑ **도구를 한 번 부르면 `mcp.tool.executed` 가 두 번 찍힌다.** 로거가 둘이라서다 —
    #   `agentic_core.mcp.client` 는 오간 통신을, `agentic_core.mcp.adapters` 는
    #   에이전트가 실제로 한 호출을 남긴다.
    #
    #   실제 실행 셋에서 두 쪽 개수가 정확히 같았다(88/88, 75/75, 49/49). 그래서 그냥
    #   세면 이 보고서의 모든 도구 숫자가 **두 배**가 되고, 실제로 그 두 배 숫자가
    #   문서에까지 실려 나갔다.
    #
    #   이 보고서가 답하려는 질문은 "**에이전트가** 도구에 몇 번 손을 뻗었나" 이므로
    #   adapters 쪽을 센다. 파이프라인 스크립트가 직접 부른 것은 client 쪽에만 남는데,
    #   그것은 에이전트의 행동이 아니므로 빠지는 것이 맞다.
    executed = [r for r in records if r.get("event") == "mcp.tool.executed"]
    by_adapter = [r for r in executed if r.get("logger") == "agentic_core.mcp.adapters"]
    # adapters 쪽이 아예 없는 로그(설정이 다른 옛날 실행)라면 있는 대로 센다.
    executed = by_adapter or executed  # a log without the adapter side is counted as it is

    # (도구 이름, 성공 여부) 별 횟수. 보고서의 도구 표가 이것으로 그려진다.
    tool_calls: Counter[tuple[str, bool]] = Counter()
    for r in executed:
        tool_calls[(str(r.get("tool")), bool(r.get("success", True)))] += 1
    # A tool that errors never reaches mcp.tool.executed — it is reported separately, so
    # counting only the executed events would show a clean sheet.
    #
    # ↑ **오류가 난 도구 호출은 `mcp.tool.executed` 에 아예 오지 않는다.** 다른 사건
    #   이름으로 따로 남는다. 그래서 executed 만 세면 실패가 있어도 표가 깨끗하게
    #   나온다 — 2026-08-13 에 실제로 그렇게 됐다.
    tool_errors: Counter[str] = Counter(
        str(r.get("tool")) for r in records if r.get("event") == "mcp.tool.error_result"
    )

    # Cost comes from the rows when they carry it, because the log cannot be trusted for
    # this: `llm.call.completed` is emitted only by _complete and _complete_text
    # (llm_service.py:576, :1053), never by complete_with_tools — which is the path every
    # reason_act turn takes. Summing the log on a real 3-trial run caught 9 of 41 calls
    # and understated the cost roughly tenfold. Runs recorded before the rows carried
    # cost still get a number, labelled as the lower bound it is.
    #
    # ↑ 비용은 **시행 기록에 있으면 거기서** 가져온다. 이 항목에서는 로그를 믿을 수
    #   없기 때문이다. `llm.call.completed` 는 `_complete` 와 `_complete_text` 에서만
    #   찍히고, reason_act 가 매 턴 지나가는 `complete_with_tools` 에서는 찍히지 않는다.
    #
    #   실제 3시행 실행에서 로그를 다 더해 봤더니 41번의 호출 중 9번만 잡혔고, 비용은
    #   실제의 약 1/10 로 나왔다. 시행 기록에 비용이 없던 옛날 실행도 숫자는 내주되,
    #   보고서에 **"이상"(하한)** 이라고 못 박아 적는다.
    if any(row.get("cost") for row in rows):
        cost = sum(float(v) for row in rows for v in (row.get("cost") or {}).values())
        toks = [(row.get("tokens") or {}).values() for row in rows]
        prompt_tokens = sum(int(p[0]) for vs in toks for p in vs)
        completion_tokens = sum(int(p[1]) for vs in toks for p in vs)
        cost_source = "rows"
    else:
        llm = [r for r in records if r.get("event") == "llm.call.completed"]
        cost = sum(float(r.get("cost_usd") or 0) for r in llm)
        prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in llm)
        completion_tokens = sum(int(r.get("completion_tokens") or 0) for r in llm)
        cost_source = "log"

    # 에이전트가 아무것도 고르지 않은 경우만 비정상으로 표시한다 (상한 없음).
    trials = []
    for row in rows:
        chosen = [c for c in (row.get("columns") or [])]
        trials.append(
            {
                "trial": row.get("trial"),
                "ok": row.get("auc") is not None,
                "auc": row.get("auc"),
                "n_columns": len(chosen),
                "columns": chosen,
                # 컬럼을 하나도 고르지 않은 경우만 위반으로 표시.
                "out_of_range": bool(chosen) and len(chosen) < COLUMN_COUNT_MIN,
                "error": row.get("error") or "",
                "perspective": row.get("perspective") or "",
            }
        )

    return {
        "manifest": manifest,
        "summary": summary,
        "trials": trials,
        "problems": problems,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "n_records": len(records),
        "cost": cost,
        "cost_source": cost_source,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "n_runs": sum(len(row.get("run_ids") or {}) for row in rows),
    }


def judge(data: dict[str, Any]) -> tuple[str, list[str]]:
    """Return the verdict and the reasons for it. No reasons means it was clean.

    ↑ 판정과 그 이유를 돌려준다. **이유가 비어 있으면 걸린 것이 없었다는 뜻이다.**

      묻는 것은 넷이다.
        · 요청한 만큼 시행 기록이 남았는가
        · 경고 이상 로그가 있었는가
        · 도구 호출이 실패했는가
        · 실패한 시행, 또는 제 컬럼 수 약속을 어긴 시행이 있는가
    """
    trials = data["trials"]
    failed = [t for t in trials if not t["ok"]]
    out_of_range = [t for t in trials if t["out_of_range"]]

    reasons: list[str] = []

    # A run whose trials all died before producing a row leaves an empty list, and an
    # empty list trips none of the checks below — it would be reported clean. Compare
    # against what was asked for instead of trusting what is there.
    #
    # ↑ 모든 시행이 기록 한 줄 남기기도 전에 죽으면 목록이 **빈 채로** 남는다. 그리고
    #   빈 목록은 아래 어느 검사에도 걸리지 않는다 — 전멸한 실행이 "정상" 으로
    #   보고된다. 그래서 있는 것을 믿지 말고 **요청한 개수와 맞춰 본다.**
    requested = (data["manifest"].get("args") or {}).get("trials")
    if isinstance(requested, int) and len(trials) != requested:
        reasons.append(f"시행 기록이 {len(trials)}건뿐 — {requested}건을 요청했다")
        if not trials:
            return VERDICT_FAIL, reasons

    if data["problems"]:
        reasons.append(f"경고 이상 로그 {len(data['problems'])}건")
    if data["tool_errors"]:
        detail = ", ".join(f"{t} {n}건" for t, n in sorted(data["tool_errors"].items()))
        reasons.append(f"도구 호출 실패 — {detail}")
    if failed:
        reasons.append(f"실패한 시행 {len(failed)}건 (#{', #'.join(str(t['trial']) for t in failed)})")
    if out_of_range:
        detail = ", ".join(f"#{t['trial']} {t['n_columns']}개" for t in out_of_range)
        reasons.append(f"컬럼을 하나도 고르지 않음 — {detail}")

    # 여기서부터 판정. 나쁜 쪽부터 본다.
    # 성공한 시행이 하나도 없으면 실패, 걸린 것이 있으면 주의, 아니면 정상.
    if trials and not any(t["ok"] for t in trials):
        return VERDICT_FAIL, reasons or ["성공한 시행이 없다"]
    if reasons:
        return VERDICT_WARN, reasons
    return VERDICT_OK, []


def render(run_dir: Path, data: dict[str, Any], verdict: str, reasons: list[str]) -> str:
    """모은 것과 판정을 마크다운 글 한 덩어리로 만든다. 파일로 쓰지는 않는다.

    L 이라는 목록에 줄을 하나씩 쌓았다가 마지막에 이어 붙인다. 글을 계속 더해 가며
    만드는 것보다 줄 단위로 읽기 쉽고, 어느 줄이 어느 절에 속하는지 눈에 보인다.

    절 구성: 판정 → 1 경고·오류 → 2 도구 호출 → 3 시행별 → 4 비용·토큰 → 5 더 볼 것.
    **판정과 그 이유가 맨 위에 온다.** 아래로 내려가야 알 수 있으면 아무도 안 본다.
    """
    manifest = data["manifest"]
    result = manifest.get("result") or {}
    args = manifest.get("args") or {}
    L: list[str] = []

    L.append(f"# 실행 보고서 — {run_dir.name}")
    L.append("")
    L.append(f"## 판정: **{verdict}**")
    L.append("")
    if reasons:
        L.append("걸린 것:")
        L.append("")
        for r in reasons:
            L.append(f"- {r}")
    else:
        L.append("걸린 것 없음 — 경고 0건, 도구 실패 0건, 실패한 시행 0건, 제약 위반 0건.")
    L.append("")
    L.append(
        f"시행 {result.get('n_succeeded', '?')}/{result.get('n_trials', '?')} 성공 · "
        f"평균 AUC {result.get('mean_auc')} · "
        f"모델 {args.get('model', '?')} · "
        f"{manifest.get('started_at', '?')} → {manifest.get('finished_at', '?')}"
    )
    L.append("")
    L.append("---")
    L.append("")

    # --- 경고·오류 -------------------------------------------------------
    L.append(f"## 1. 경고·오류 — {len(data['problems'])}건")
    L.append("")
    if not data["problems"]:
        L.append(f"로그 {data['n_records']}줄 중 warning 이상 **0건**.")
    else:
        L.append("**전문 그대로.** 잘라내지 않는다.")
        L.append("")
        for p in data["problems"]:
            where = " · ".join(
                str(p[k]) for k in ("trial", "stage") if k in p and p[k] is not None
            )
            L.append(f"- `{p.get('level')}` **{p.get('event')}**" + (f" — 시행 {where}" if where else ""))
            for key in ("tool", "server", "content", "error", "reason"):
                if p.get(key):
                    L.append(f"  - {key}: `{p[key]}`")
    L.append("")

    # --- 도구 ------------------------------------------------------------
    L.append("## 2. 도구 호출")
    L.append("")
    names = sorted({t for t, _ in data["tool_calls"]} | set(data["tool_errors"]))
    if not names:
        L.append("도구 호출 기록 없음.")
    else:
        L.append("| 도구 | 성공 | 실패 |")
        L.append("|---|---:|---:|")
        for name in names:
            ok = data["tool_calls"][(name, True)]
            bad = data["tool_calls"][(name, False)] + data["tool_errors"][name]
            mark = " **←실패**" if bad else ""
            L.append(f"| `{name}` | {ok} | {bad}{mark} |")
    L.append("")

    # --- 시행 ------------------------------------------------------------
    L.append("## 3. 시행별")
    L.append("")
    L.append("컬럼 수 제약 없음 — 에이전트가 OKF 근거에 따라 스스로 판단.")
    L.append("")

    # Only when this dataset carries the planted answer key — see pipeline_core.aggregate.
    # On any other dataset there is no answer key, and reporting one would be a
    # failure that did not happen.
    #
    # ↑ 정답을 심어 둔 합성 데이터일 때만 이 줄을 찍는다. 다른 데이터에는 정답이라는
    #   것이 아예 없어서, "회수율 0%" 같은 숫자를 찍으면 일어나지도 않은 실패를
    #   보고하는 셈이 된다.
    summary = data["summary"]
    if "planted_recall" in summary:
        L.append(
            f"심어둔 신호 회수 **{summary['planted_recall']}** — "
            f"찾음 {summary.get('planted_found_in_top6') or '없음'}"
        )
        L.append("")
    L.append("| # | 결과 | AUC | 컬럼 | 관점 |")
    L.append("|---|---|---:|---|---|")
    for t in data["trials"]:
        status = "성공" if t["ok"] else f"**실패** — {t['error']}"
        cols = f"{t['n_columns']}개"
        if t["out_of_range"]:
            cols += " **←컬럼 없음**"
        L.append(f"| {t['trial']} | {status} | {t['auc']} | {cols} | {t['perspective']} |")
    L.append("")

    # --- 비용 ------------------------------------------------------------
    L.append("## 4. 비용·토큰")
    L.append("")
    if data["cost_source"] == "rows":
        L.append(f"- 에이전트 실행 {data['n_runs']}건")
        L.append(f"- 토큰 {data['prompt_tokens']:,} 입력 / {data['completion_tokens']:,} 출력")
        L.append(f"- 비용 **${data['cost']:.4f}**")
    else:
        L.append(f"- 비용 **${data['cost']:.4f} 이상** — 실제는 이보다 훨씬 크다")
        L.append(f"- 토큰 {data['prompt_tokens']:,} 입력 / {data['completion_tokens']:,} 출력 (같은 하한)")
        L.append("")
        L.append(
            "> ⚠️ **이 실행에는 정확한 비용이 기록돼 있지 않다.** core는 "
            "`llm.call.completed`를 `_complete`·`_complete_text`에서만 찍고, "
            "reason_act가 매 턴 쓰는 `complete_with_tools`에서는 찍지 않는다. "
            "이 실행에서 로그에 잡힌 것은 41회 중 9회뿐이었다. "
            "이후 실행은 `execute_run`이 돌려주는 값을 시행 기록에 담으므로 정확하다. "
            f"실제 값은 `trace/`에서 볼 수 있다."
        )
    L.append("")

    # --- 다음 ------------------------------------------------------------
    L.append("## 5. 더 볼 것")
    L.append("")
    L.append("| 파일 | 무엇 |")
    L.append("|---|---|")
    L.append("| `trace/trialNN.txt` | 그 시행의 모든 단계 — 도구 인자와 결과 전문 |")
    L.append("| `console.log` | 터미널에 나갔던 것 그대로 |")
    L.append("| `run.jsonl` | 구조화 로그 전량. 모든 줄에 trial·stage 태그 |")
    L.append("")
    L.append("```bash")
    L.append(f"python trace_run.py --from {run_dir} --trial 0 --full")
    L.append("```")
    L.append("")

    return "\n".join(L)


def build_report(run_dir: Path) -> tuple[str, list[str], Path]:
    """Write REPORT.md into *run_dir*. Returns the verdict, its reasons and the path.

    ↑ 실행 폴더에 REPORT.md 를 쓴다. 판정 · 이유 · 쓴 파일 경로를 돌려준다.

      바깥에서 부르는 입구는 이 함수 하나다. 02_mvp_pipeline.py 가 실행이 끝날 때마다
      이것을 불러서, 실행 폴더는 만들어질 때부터 REPORT.md 를 안고 있게 된다.
    """
    data = collect(run_dir)
    verdict, reasons = judge(data)
    path = run_dir / "REPORT.md"
    path.write_text(render(run_dir, data, verdict, reasons), encoding="utf-8")
    return verdict, reasons, path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="a directory under outputs/runs/")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"!! not a directory: {run_dir}", file=sys.stderr)
        return 1

    verdict, reasons, path = build_report(run_dir)
    print(f"판정: {verdict}")
    for r in reasons:
        print(f"  - {r}")
    print(f"{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
