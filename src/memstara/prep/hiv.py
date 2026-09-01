#!/usr/bin/env python3
"""Flatten the shared HIV cohort into a table the pipeline can actually slice.

The cohort as shared is not a feature matrix. Of its 18 columns, seven hold a whole
list crammed into one cell, pipe-delimited, and the length differs per patient —
diagnoses run from 1 to 1,143 with a median of 53. A model needs one value per patient
per column, and `slice_columns` only *picks* existing columns; it does not unpack
anything. So the unpacking happens here, once, before the pipeline ever runs.

What comes out:

    9   as-is        age · BMI · sex · ethnicity · race · marital · tobacco · drug · alcohol
    4   counts       how many diagnoses / medications / surgeries / lab components
    16  flags        the 8 most prevalent diagnoses and 8 most prevalent medications
    1   outcome      HIV_DETECTABLE

Counts and flags are deliberately the *simplest* things derivable from the lists.
Anything more is feature construction, which is a different project — the MVP fixed on
2026-08-06 is a feature **selection** operator, and this file exists only to give it
something to select from.

The source directory is **read only**. Output goes to this sandbox's outputs/.

Usage::

    python -m memstara.prep.hiv
    python -m memstara.prep.hiv --top 12 --out outputs/hiv_cohort.csv


==============================================================================
 이 파일을 읽는 법
==============================================================================

 reviewer 이 공유한 **HIV 코호트**를 파이프라인이 쓸 수 있는 CSV 한 장으로 펴 낸다.
 받은 파일은 한 칸 안에 목록이 통째로 들어 있어(진단명이 파이프 `|` 로 이어져
 환자마다 1개에서 1,143개까지) 그대로는 학습에 못 쓴다. 결과변수는
 `HIV_DETECTABLE`(바이러스가 검출되는가).

 함수는 넷이다.

   items(cell)                 파이프로 이어 붙은 한 칸을 **중복 없는 목록**으로 쪼갠다
   column_name(prefix, label)  진단명 같은 긴 이름을 열 이름으로 다듬는다
   build(source, top)          펴 내기 전체. **이 파일의 본체**
   main()                      읽고 · build 부르고 · 저장하고 · 무엇이 나왔는지 찍는다

 나오는 것: 그대로 쓰는 9열 + 개수 4열 + 있음/없음 표시 16열 + 결과변수 1열.

 놓치기 쉬운 것:

   · **개수와 있음/없음 표시는 일부러 가장 단순한 것만** 만든다. 이보다 나아가면
     그것은 변수 만들기(feature construction)이고, 이 프로젝트가 정한 범위는
     이미 있는 변수 중에서 **고르는 것**이다. 이 파일은 고를 거리를 마련할 뿐이다.
   · 원본 폴더는 **읽기만 한다.** 결과는 이 폴더의 outputs/ 로 나간다.
   · 열 이름을 사람이 읽을 수 있게 만드는 것이 중요하다. 지식원의 개념과 데이터의
     열을 이어 붙이는 쪽이 **둘 다 읽는 LLM** 이라, `dx_f329` 로는 "우울증" 과
     연결하지 못한다.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from memstara.paths import DEFAULT_OUTPUT_DIR, SHARED_ROOT

SOURCE = SHARED_ROOT / "Agentic-Clinical-Feature-Construction-Demo" / "cohort_v1_latest_no_PHI.csv"
DEFAULT_OUT = DEFAULT_OUTPUT_DIR / "hiv_cohort.csv"

OUTCOME = "HIV_DETECTABLE"   # 맞히려는 것 — 바이러스가 검출되는가

# Columns that already hold one value per patient.
#
# ↑ 환자 한 명당 값이 이미 하나뿐인 열들. 손댈 것이 없어 그대로 옮긴다.
FLAT = [
    "CURRENT_AGE",
    "BMI",
    "SEX",
    "ETHNIC_GROUP",
    "RACE_1",
    "MARITAL_STATUS",
    "TOBACCO_LAST_STATUS",
    "ILL_DRUG_LAST_STATUS",
    "ALCOHOL_LAST_STATUS",
]

# (source column, count column name, flag prefix or None)
#
# ↑ (원본 열 이름, 개수를 담을 열 이름, 표시 열 앞머리 또는 None)
#   앞머리가 None 인 둘은 **개수만** 만들고 있음/없음 표시는 만들지 않는다.
#   수술과 검사 항목은 종류가 너무 흩어져 있어, 가장 흔한 8개를 뽑아도 대부분의
#   환자에게 0 만 찍히는 열이 되기 때문이다.
LISTS = [
    ("DX_NAME_LIST", "n_diagnoses", "dx"),
    ("MED_NAME_LIST", "n_medications", "med"),
    ("SURGERY_PROC_LIST", "n_surgeries", None),
    ("GENERAL_LAB_COMPONENTS_LIST", "n_lab_components", None),
]


def items(cell: object) -> list[str]:
    """Split one pipe-delimited cell into its distinct entries.

    ↑ 파이프(`|`)로 이어 붙은 한 칸을 **중복 없는** 목록으로 쪼갠다.

      중복을 없애는 것이 요점이다. 같은 진단이 방문마다 다시 적혀 있으면, 그대로
      세었을 때 "진단 개수" 가 병의 가짓수가 아니라 **방문 횟수**를 재게 된다.
      빈 칸이나 글자가 아닌 값은 빈 목록으로 돌려준다.
    """
    if not isinstance(cell, str) or not cell.strip():
        return []
    return sorted({p.strip() for p in cell.split("|") if p.strip()})


def column_name(prefix: str, label: str) -> str:
    """A readable column name.

    Readable on purpose. The thing that has to connect a knowledge-source concept to a
    column is an LLM reading both, and it cannot connect `dx_f329` to "depression".

    ↑ **일부러** 사람이 읽을 수 있게 만든다. 지식원의 개념과 데이터의 열을 이어
      붙이는 쪽은 둘 다 읽는 LLM 이고, `dx_f329` 를 보고 "우울증" 을 떠올리지는
      못한다. 그래서 진단명을 소문자로 바꾸고 기호를 밑줄로 바꾼 뒤 앞머리를 붙여
      `dx_major_depressive_disorder` 같은 이름을 만든다. 40자에서 자른다.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"{prefix}_{slug[:40]}".rstrip("_")


def build(source: Path, top: int) -> tuple[pd.DataFrame, dict[str, list[tuple[str, int]]]]:
    """받은 코호트를 펴 낸다. **이 파일의 본체.**

    돌려주는 것은 둘 — 정리된 표와, 어떤 진단·약이 뽑혔는지의 기록.

    모든 열을 글자(dtype=str)로 읽고 `keep_default_na=False` 를 준다. pandas 가
    알아서 숫자로 바꾸거나 빈 칸을 NaN 으로 만들면, 목록을 쪼개는 단계에서 값이
    글자인지 아닌지를 매번 따져야 한다. 필요한 열만 나중에 숫자로 바꾼다.
    """
    raw = pd.read_csv(source, dtype=str, keep_default_na=False)

    # The shared file has a few rows where a diagnosis name spilled into the label
    # column — an unescaped delimiter upstream. Keep only rows whose label is 0 or 1
    # and say how many were dropped; silently losing rows is how row counts stop
    # matching between steps.
    #
    # ↑ 받은 파일에는 진단명이 **결과변수 칸으로 흘러 들어간** 행이 몇 개 있다.
    #   위쪽 어딘가에서 구분 기호를 제대로 감싸지 않아 생긴 일이다. 결과변수가
    #   0 이나 1 인 행만 남기고, **몇 행을 버렸는지 반드시 찍는다.** 말없이 행이
    #   줄어드는 것이 단계마다 행 수가 안 맞기 시작하는 출발점이다.
    keep = raw[OUTCOME].isin(["0", "1"])
    dropped = int((~keep).sum())
    raw = raw[keep].reset_index(drop=True)

    # ① 이미 한 값짜리인 열은 그대로 옮긴다. 빈 글자는 결측으로 바꿔 두어야
    #    "비어 있음" 과 "빈 문자열" 이 뒤섞이지 않는다. 나이와 BMI 만 숫자로.
    out = pd.DataFrame(index=raw.index)
    for c in FLAT:
        s = raw[c].replace("", pd.NA)
        out[c] = pd.to_numeric(s) if c in ("CURRENT_AGE", "BMI") else s

    # ② 목록 열을 편다. 열마다 개수 하나를 만들고, 앞머리가 있는 것만 가장 흔한
    #    top 개를 골라 있음/없음(1/0) 열을 더 만든다.
    chosen: dict[str, list[tuple[str, int]]] = {}
    for src, count_col, prefix in LISTS:
        parsed = raw[src].map(items)          # 각 칸을 목록으로
        out[count_col] = parsed.map(len)      # 그 목록의 길이 = 개수
        if prefix is None:
            continue
        freq = Counter(v for lst in parsed for v in lst)   # 전체에서 몇 명에게 있었나
        picked = freq.most_common(top)                     # 가장 흔한 top 개
        chosen[src] = picked
        # `l=label` 로 값을 그 자리에서 붙잡아 둔다. 이것을 빼면 반복이 끝난 뒤의
        # label 값 하나만 쓰이게 되어, 모든 표시 열이 마지막 진단명 하나를 가리킨다.
        for label, _ in picked:
            out[column_name(prefix, label)] = parsed.map(lambda lst, l=label: int(l in lst))

    # ③ 결과변수는 맨 마지막에 붙여 표의 끝에 오게 한다.
    out[OUTCOME] = pd.to_numeric(raw[OUTCOME])
    return out, {"__dropped__": dropped, **chosen}  # type: ignore[dict-item]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--top", type=int, default=8, help="how many diagnoses / medications to flag")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.is_file():
        print(f"!! not found: {source}", file=sys.stderr)
        return 1

    # build 는 뽑힌 진단·약 기록에 버린 행 수를 함께 실어 돌려준다. 여기서 꺼낸다.
    df, chosen = build(source, args.top)
    dropped = chosen.pop("__dropped__")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    pos = int(df[OUTCOME].sum())
    print(f"source: {source}")
    print(f"        (read only — nothing is written back there)\n")
    print(f"rows    {len(df):,}   ({dropped} dropped: label was not 0/1)")
    print(f"columns {len(df.columns)}   = {len(FLAT)} as-is + {len(LISTS)} counts "
          f"+ {sum(len(v) for v in chosen.values())} flags + outcome")
    print(f"outcome {OUTCOME}: {pos} positive / {len(df) - pos} negative  ({pos / len(df) * 100:.1f}%)\n")

    for src, picked in chosen.items():
        print(f"{src} — {len(picked)} most prevalent")
        for label, n in picked:
            print(f"   {n / len(df) * 100:5.1f}%  {label[:64]}")
        print()

    # Missingness is the one property a column name cannot convey, and the hypothesis
    # agent decides from names. Print it so the number is on the record here too.
    #
    # ↑ 결측률은 **열 이름만 봐서는 절대 알 수 없는** 유일한 성질이다. 그런데 가설
    #   에이전트는 이름만 보고 고른다. 그래서 여기서도 숫자를 찍어 기록에 남긴다
    #   — 나중에 어떤 열이 왜 쓸모없었는지 되짚을 근거가 된다.
    miss = df.isna().mean().sort_values(ascending=False)
    miss = miss[miss > 0]
    if len(miss):
        print("columns with missing values")
        for c, frac in miss.items():
            print(f"   {frac * 100:5.1f}%  {c}")

    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
