#!/usr/bin/env python3
"""Turn the public NHANES survey into a table the pipeline can run against.

Why this dataset
----------------
Everything the board path has run on so far is synthetic, with the answer planted so
the pipeline could be scored. That proves it works; it does not show what breaks on
real data. And a paper needs one dataset a reviewer can download — reviewer's HIV cohort
cannot be published.

NHANES is public, clinical, and wide enough that a hypothesis limited to 3-8 columns
has to actually choose. The CDC's own XPT files are unreachable from here (wwwn.cdc.gov
answers with its homepage HTML instead of the file), so this reads the copy shipped in
CRAN's NHANES R package, which is the same survey with the columns already typed.

    curl -L -o NHANES.rda \
      https://raw.githubusercontent.com/cran/NHANES/master/data/NHANES.rda

What is dropped, and why
------------------------
- `ID`, `SurveyYr`          identifiers, not measurements
- >30% missing              Testosterone, TVHrsDay, CompHrsDay
- restatements              BMI_WHO (of BMI), AgeDecade (of Age),
                            BPSys1..3 / BPDia1..3 (of BPSysAve / BPDiaAve)

Restatements matter more than they look: leaving BPSys1 beside BPSysAve gives the
hypothesis stage three ways to say "systolic blood pressure", which inflates any
count of how often a concept was chosen.

Adults only (Age >= 20), and rows where the outcome is known.

Usage::

    Rscript -e 'load("NHANES.rda"); write.csv(NHANES, "nhanes_raw.csv", row.names=FALSE)'
    python prep_nhanes.py --raw nhanes_raw.csv


==============================================================================
 이 파일을 읽는 법
==============================================================================

 **공개 데이터 NHANES**(미국 국민건강영양조사)를 파이프라인이 바로 읽을 수 있는
 CSV 한 장으로 정리한다. 성인만 남기고, 너무 비어 있는 열과 같은 말을 되풀이하는
 열을 뺀다. 결과변수는 `Diabetes`(당뇨 여부), 양성이 약 10.3% 다.

 함수는 둘뿐이다.

   build(raw)   걸러내기와 열 정리를 전부 한다. **이 파일의 본체**
   main()       원본 CSV 를 읽고 build 를 부르고 저장한 뒤, 무엇을 뺐는지 찍는다

 이 파일이 있는 이유: 지금까지 돌린 데이터는 전부 정답을 심어 둔 합성 데이터였다.
 그건 파이프라인이 **작동한다**는 증거이지, 실제 데이터에서 무엇이 깨지는지는
 보여 주지 못한다. 그리고 논문에는 심사자가 직접 내려받을 수 있는 데이터가
 하나는 있어야 한다 — reviewer 의 HIV 코호트는 공개할 수 없다.

 놓치기 쉬운 것:

   · **같은 말을 되풀이하는 열**(BPSys1 과 BPSysAve 처럼)을 빼는 것이 겉보기보다
     중요하다. 남겨 두면 가설 단계가 "수축기 혈압" 을 말하는 방법을 셋 갖게 되고,
     어떤 개념이 몇 번 뽑혔는지 세는 숫자가 그만큼 부풀려진다.
   · build 는 이름과 달리 표 하나가 아니라 **표와 뺀 열 목록 두 개**를 돌려준다.
     함수 위에 적힌 반환형 표기(pd.DataFrame)와는 어긋나 있다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
OUT_DIR = HERE / "outputs"

OUTCOME = "Diabetes"      # 맞히려는 것 — 당뇨 여부
MIN_AGE = 20              # 성인만 남긴다
MAX_MISSING = 0.30        # 30% 넘게 비어 있는 열은 버린다

# Dropped for the reasons in the module docstring.
#
# ↑ 왜 빼는지는 파일 맨 위 설명에 있다. 아래 두 묶음은 성격이 다르다.
#   DROP_IDENTIFIERS  는 **측정값이 아닌 것**(일련번호, 조사연도)이고,
#   DROP_RESTATEMENTS 는 **다른 열을 다시 말한 것**이다.
DROP_IDENTIFIERS = ["ID", "SurveyYr"]
DROP_RESTATEMENTS = [
    "BMI_WHO", "AgeDecade", "BMICatUnder20yrs",   # BMI·Age 를 구간으로 다시 쓴 것
    "BPSys1", "BPDia1", "BPSys2", "BPDia2", "BPSys3", "BPDia3",  # 평균값이 따로 있다
    "HHIncome",        # HHIncomeMid is the same thing as a number
                       # ↑ 같은 가구소득을 구간 문자열로 쓴 것. 숫자판이 HHIncomeMid 다
    "Length", "HeadCirc",  # infant measurements; empty for adults
                       # ↑ 영아 측정치. 성인만 남기면 통째로 비어 있다
    "Smoke100n",       # restatement of Smoke100
                       # ↑ Smoke100 을 말만 바꿔 적은 것
]


def build(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Adults with a known outcome, measurement columns only.

    ↑ 성인이면서 결과가 알려진 행만, 그리고 측정값인 열만 남긴다.

      돌려주는 것은 **둘**이다 — 정리된 표와, 결측이 많아 빠진 열 이름 목록.
      목록을 같이 돌려주는 이유는 main() 이 그것을 화면에 찍기 위해서다. 무엇이
      조용히 사라졌는지 남기지 않으면, 나중에 열 수가 안 맞을 때 설명할 길이 없다.

      (위의 반환형 표기는 표 하나만 적혀 있어 실제와 다르다. 실행에는 영향이 없다.)
    """
    # 성인(20세 이상)이고, 결과변수가 비어 있지 않은 행만. .copy() 는 이 뒤의 수정이
    # 원본 raw 를 건드리지 않게 하려는 것이다.
    df = raw[(raw["Age"] >= MIN_AGE) & raw[OUTCOME].notna()].copy()

    # 있는 것만 골라 지운다 — 목록에 적힌 열이 원본에 없어도 오류가 나지 않는다.
    df = df.drop(columns=[c for c in DROP_IDENTIFIERS + DROP_RESTATEMENTS if c in df.columns])

    # Columns that are mostly blank cannot support a model, and leaving them in lets the
    # hypothesis stage pick something that quietly becomes a column of NaNs.
    #
    # ↑ 대부분 비어 있는 열로는 모델을 만들 수 없다. 그런데 그냥 두면 가설 단계가
    #   그 열을 고를 수 있고, 고른 뒤에야 **통째로 빈 열**이었다는 것이 드러난다.
    #   그때는 이미 시행 하나를 버린 뒤다. 결과변수 자신은 이 검사에서 제외한다.
    missing = df.isna().mean()
    too_empty = sorted(missing[missing > MAX_MISSING].index.difference([OUTCOME]))
    df = df.drop(columns=too_empty)

    # Yes/No -> 1/0. The ML tool expects a numeric target.
    #
    # ↑ "Yes"/"No" 를 1/0 으로 바꾼다. 학습 도구가 숫자 목표값을 기대한다.
    df[OUTCOME] = (df[OUTCOME].astype(str) == "Yes").astype(int)

    # Move the outcome last, the way the synthetic dataset has it.
    #
    # ↑ 결과변수를 맨 뒤로 보낸다. 합성 데이터와 열 배치를 맞춰 두면, 데이터가
    #   바뀌어도 사람이 표를 읽는 방식이 달라지지 않는다.
    cols = [c for c in df.columns if c != OUTCOME] + [OUTCOME]
    return df[cols], too_empty


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(OUT_DIR / "nhanes_raw.csv"),
                    help="CSV exported from NHANES.rda")
    ap.add_argument("--out", default=str(OUT_DIR / "nhanes_adult.csv"))
    args = ap.parse_args()

    # 원본 CSV 는 R 이 먼저 만들어야 한다. 없으면 여기서 멈추고 방법을 알려 준다.
    raw_path = Path(args.raw)
    if not raw_path.exists():
        print(f"없다: {raw_path}\n  R 로 먼저 내보내십시오 — 모듈 설명 참고", file=sys.stderr)
        return 1

    # low_memory=False: 한 열 안에 숫자와 문자가 섞여 있을 때 pandas 가 조각마다
    # 다른 자료형을 추측하는 것을 막는다.
    raw = pd.read_csv(raw_path, low_memory=False)
    df, too_empty = build(raw)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    n_pos = int(df[OUTCOME].sum())
    print(f"  원본        {len(raw):,}행 × {raw.shape[1]}열")
    print(f"  성인·결과있음 {len(df):,}행")
    print(f"  결측 {MAX_MISSING:.0%} 초과로 뺀 열: {', '.join(too_empty) if too_empty else '없음'}")
    print(f"  남은 열      {df.shape[1] - 1}개 + {OUTCOME}")
    print(f"  {OUTCOME}    {n_pos:,} 양성 / {len(df) - n_pos:,} 음성  ({n_pos / len(df):.1%})")
    print(f"  →           {args.out}")

    # A column that is entirely one value teaches a model nothing and wastes a pick.
    #
    # ↑ 전부 같은 값인 열은 모델에게 아무것도 가르쳐 주지 못하면서, 가설 단계가
    #   쓸 수 있는 3~8개의 자리 하나를 잡아먹는다. 여기서는 지우지 않고 **경고만**
    #   찍는다 — 지울지 말지는 데이터를 아는 사람이 정할 일이다.
    constant = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    if constant:
        print(f"  ⚠ 값이 하나뿐인 열: {constant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
