#!/usr/bin/env python3
"""Generate a synthetic dataset and a sample OKF bundle. Run once.

There is no real dataset and no real OKF bundle yet, so this makes both, which is
what lets the pipeline be validated now. When real data arrives, point
MEMSTARA_DATASET_PATH and AGENTIC_OKF_BUNDLE_DIR at it — the pipeline code does not
change.

Two properties of this data are deliberate, and the pipeline is worthless without
them.

**Column names are opaque codes.** Everything is an NHANES-style identifier —
LBXGH, BMXBMI, BPXSY1 — including the non-predictive columns. An earlier version
named them bmi / hba1c / noise_01, which let the hypothesis agent pick correctly
from the names alone and reduced the knowledge source to after-the-fact
justification. Opaque codes mean the ONLY route from a column to its meaning runs
through OKF.

**The knowledge source offers more candidates than a hypothesis can use.** Roughly
18 of the dataset's columns are described by a concept, but only six carry signal.
With the agent limited to 3-8 columns it has to choose, so different perspectives
select different subsets — which is the precondition for overlap across trials to
carry any information. If OKF pointed only at the six real ones, "take everything
OKF mentions" would win trivially and every trial would return the same set.

A real signal is still planted: LBXGH / BMXBMI / RIDAGEYR / BPXSY1 genuinely predict
the outcome. Measured one at a time the univariate AUC is 0.73 / 0.66 / 0.63 / 0.60,
against 0.51 for a noise column — a coin toss. If those four rise to the top of an
aggregate, the pipeline works. It is **an exam paper that comes with its answer key**.

Usage::

    python -m memstara.prep.sample
    python -m memstara.prep.sample --rows 1700 --seed 42

This file makes **one sheet of fake clinical data (dataset.csv)** and **one fake
bundle of knowledge (an OKF bundle, 31 .md files)** in a single go and puts them under
outputs/. Real data and a real knowledge bundle do not exist yet, so validating the
pipeline now means inventing both. When the real ones arrive, only the two environment
variables (MEMSTARA_DATASET_PATH, AGENTIC_OKF_BUNDLE_DIR) are pointed at them; the
pipeline code is not touched.

There are three functions.

    build_dataset(n_rows, seed)       makes one table (a dataframe). It draws the
                                      columns first, then combines six of them into
                                      the outcome variable Y
    write_okf_bundle(okf_dir, stamp)  writes the 31 concepts as 31 markdown files,
                                      with index.md and log.md added on top
    main()                            reads the arguments, calls the two above, and
                                      prints a summary

Easy to miss:

  1. **The answer is planted on purpose.** hba1c (LBXGH) · bmi (BMXBMI) · age
     (RIDAGEYR) · systolic pressure (BPXSY1) genuinely predict Y. Measured on their
     own the univariate AUC is 0.73 / 0.66 / 0.63 / 0.60, against 0.51 for a noise
     column — a coin toss. Because the answer is fixed, "did the pipeline find the
     right one" can be scored. That is why this file exists.
  2. **Column names were made opaque on purpose.** From a code like LBXGH alone
     there is no telling that it is glycated haemoglobin. Only if the one route to
     meaning is OKF does whether the agent actually read OKF show up in the result.
     (reviewer's real cohort, though, has column names a person can read. This
     encoding is a device used in the synthetic data only, not a property of the
     real data.)
  3. **This bundle is flat.** No per-domain subfolders — the 31 .md files sit at the
     root as they are. A bundle with a hierarchy has not been tried yet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from memstara.paths import DEFAULT_OUTPUT_DIR

OUT_DIR = DEFAULT_OUTPUT_DIR
# Bundle folders are named okf_<source>_<what it holds> so the folder name alone
# says where the knowledge came from — see outputs/README.md.
#
# ↑ 번들 폴더 이름은 `okf_<출처>_<담고 있는 것>` 꼴로 짓는다. 폴더 이름만 봐도
#   이 지식이 어디서 왔는지 알 수 있게 하려는 것이다. 여기서는 `okf_synthetic_sample`
#   — 합성(synthetic)으로 지어낸 표본(sample)이라는 뜻이다.
#
#   이 번들은 **평평하다**: 도메인별 하위 폴더를 두지 않고 루트에 .md 31장을
#   그대로 놓는다. 폴더로 나뉜 번들에서도 되는지는 아직 확인하지 않았다.
OKF_DIR = OUT_DIR / "okf_synthetic_sample"
DATASET = OUT_DIR / "dataset.csv"

Y_COLUMN = "outcome"
# ↑ 예측 대상(결과변수)의 컬럼 이름. 0 또는 1이 들어간다.

# Columns that actually generate Y, and their weights.
#
# ↑ Y를 **실제로 만들어 내는** 컬럼과 그 가중치. 이 네 개가 이 파일이 심어 둔
#   정답이며, 파이프라인 채점의 기준이 된다. 가중치가 클수록 Y에 세게 관여한다
#   — LBXGH(1.10)가 가장 세고 BPXSY1(0.60)이 가장 약하다.
TRUE_SIGNAL: dict[str, float] = {
    "LBXGH": 1.10,      # glycated haemoglobin
    "BMXBMI": 0.90,     # body mass index
    "RIDAGEYR": 0.70,   # age in years
    "BPXSY1": 0.60,     # systolic blood pressure
}
# Contribute only weakly — there to see whether the aggregate separates strong from
# weak rather than merely present from absent.
#
# ↑ 약하게만 관여하는 컬럼. 집계가 "신호가 있다/없다"만 가르는지, 아니면 "센 신호와
#   약한 신호"까지 구분해 내는지를 보려고 넣었다. 있으면 있는 대로 잡히지만
#   TRUE_SIGNAL 넷보다는 아래에 놓여야 정상이다.
WEAK_SIGNAL: dict[str, float] = {
    "LBDLDL": 0.25,     # LDL cholesterol
    "LBXCRP": 0.20,     # C-reactive protein
}

# Non-predictive, but indistinguishable from the above by name. Each is drawn from a
# plausible clinical distribution so that inspecting values gives nothing away
# either. Naming these VAR_001... would put the old giveaway back in a new costume.
#
#   code -> (mean, sd, low, high, decimals)
#
# ↑ **미끼(decoy) 컬럼.** Y를 전혀 예측하지 못하지만, 이름만 봐서는 위의 진짜
#   신호와 구별되지 않는다. 값도 실제 임상 수치처럼 그럴듯한 분포에서 뽑는다 —
#   숫자를 들여다봐도 힌트가 없게 하려는 것이다. 이것들을 VAR_001 식으로 이름
#   붙였다면 "이건 잡음이구나"가 이름에서 그대로 드러나, 앞서 없앤 힌트를 옷만
#   갈아입혀 되살리는 꼴이 된다.
#
#   괄호 안 다섯 숫자의 뜻: (평균, 표준편차, 하한, 상한, 반올림 소수점 자리).
#   예를 들어 BPXDI1은 평균 74, 표준편차 11인 정규분포에서 뽑되 40~120 밖으로는
#   나가지 않게 자르고, 소수점 없이(0자리) 반올림한다.
DECOY_COLUMNS: dict[str, tuple[float, float, float, float, int]] = {
    "BPXDI1": (74, 11, 40, 120, 0),        # diastolic blood pressure
    "BMXWAIST": (98, 15, 55, 160, 1),      # waist circumference
    "BMXHT": (167, 10, 140, 200, 1),       # standing height
    "LBXTC": (190, 38, 90, 340, 0),        # total cholesterol
    "LBDHDD": (53, 15, 20, 120, 0),        # HDL cholesterol
    "LBXTR": (135, 70, 30, 600, 0),        # triglycerides
    "LBXSAL": (4.2, 0.35, 2.5, 5.5, 2),    # serum albumin
    "LBXSATSI": (24, 11, 5, 120, 0),       # alanine aminotransferase
    "LBXSASSI": (23, 9, 6, 110, 0),        # aspartate aminotransferase
    "LBXSCR": (0.9, 0.25, 0.3, 3.0, 2),    # serum creatinine
    "LBXSUA": (5.5, 1.4, 2.0, 12.0, 1),    # uric acid
    "LBXWBCSI": (7.2, 2.0, 2.0, 18.0, 1),  # white blood cell count
    "LBXHGB": (14.0, 1.5, 8.0, 19.0, 1),   # haemoglobin
    "LBXPLTSI": (250, 60, 80, 500, 0),     # platelet count
    "LBXSNASI": (139, 2.5, 128, 150, 0),   # serum sodium
    "LBXSKSI": (4.1, 0.4, 2.8, 6.0, 1),    # serum potassium
    "URXUMA": (18, 45, 1, 900, 1),         # urinary albumin
    "LBXSTB": (0.7, 0.3, 0.1, 3.0, 2),     # total bilirubin
}

# Extra unnamed noise, to keep the column count up without inventing more codes that
# would need concepts written for them.
#
# ↑ 이름 없는 잡음 컬럼을 16개 더 붙인다(XVAR001 … XVAR016). 컬럼 수를 실제 데이터
#   비슷하게 유지하려는 것인데, 코드를 더 지어내면 그 하나하나에 개념 문서도
#   써 줘야 하므로 그냥 번호를 붙인 잡음으로 채운다. 어떤 개념도 이것들을 설명하지
#   않으므로, 에이전트가 OKF를 통해서는 결코 닿을 수 없는 컬럼이다.
N_UNLABELLED_NOISE = 16


def build_dataset(n_rows: int, seed: int) -> pd.DataFrame:
    """Build a synthetic table shaped like clinical data.

    Precise realism is not the goal — recovering the planted variables is — so each
    variable only has to be plausible.

    ↑ 임상 데이터처럼 생긴 표 한 장을 만든다.

    정밀한 사실성은 목표가 아니다. 목표는 **심어 둔 변수를 파이프라인이 되찾아
    내는지 보는 것**이므로, 각 변수는 "그럴듯한 정도"면 충분하다. 예컨대 나이가
    평균 58세인 코호트가 현실의 어떤 병원과 정확히 일치할 필요는 없다.

    Args:
        n_rows: 만들 행(환자) 수.
        seed: 난수 씨앗. 같은 값을 주면 항상 같은 표가 나온다.

    Returns:
        결과변수 `outcome` 컬럼까지 포함한 데이터프레임.
    """
    # 씨앗을 고정한 난수 발생기. 같은 seed면 같은 숫자열이 나오므로, 다시 돌려도
    # 어제와 똑같은 데이터가 만들어진다 — 결과를 비교하려면 이것이 전제다.
    rng = np.random.default_rng(seed)

    # 진짜 신호 넷 + 약한 신호 둘. 여기 값들은 실제 성인 코호트에서 흔히 보는
    # 범위를 흉내 낸 것이다. `.clip(하한, 상한)` 은 정규분포 꼬리에서 나온
    # 비현실적인 값(예: BMI 3, 나이 -4)을 잘라 낸다.
    df = pd.DataFrame(
        {
            "RIDAGEYR": rng.normal(58, 13, n_rows).clip(18, 95).round(0),
            "BMXBMI": rng.normal(28.5, 5.8, n_rows).clip(15, 55).round(1),
            "LBXGH": rng.normal(6.1, 1.3, n_rows).clip(4.0, 14.0).round(1),
            "BPXSY1": rng.normal(131, 18, n_rows).clip(85, 210).round(0),
            "LBDLDL": rng.normal(115, 33, n_rows).clip(35, 260).round(0),
            "LBXCRP": rng.lognormal(0.4, 0.9, n_rows).clip(0.1, 60).round(2),
        }
    )

    # Decoys — described by OKF concepts, but unrelated to Y.
    #
    # ↑ 미끼 컬럼. OKF에 개념 문서가 있어서 에이전트가 찾아낼 수는 있지만, Y와는
    #   아무 관계도 없다. Y를 만드는 식(아래)에 들어가지 않기 때문이다.
    for code, (mean, sd, low, high, dec) in DECOY_COLUMNS.items():
        df[code] = rng.normal(mean, sd, n_rows).clip(low, high).round(dec)

    # Unlabelled noise — no concept describes these.
    #
    # ↑ 라벨 없는 잡음. 어떤 개념 문서도 이것들을 설명하지 않는다. 평균 0,
    #   표준편차 1의 순수한 난수다.
    for i in range(1, N_UNLABELLED_NOISE + 1):
        df[f"XVAR{i:03d}"] = rng.normal(0, 1, n_rows).round(3)

    # Y: standardise the signal columns and combine them logistically.
    #
    # ↑ 여기가 **정답을 심는 자리**다. 순서대로 읽으면 이렇다.
    #
    #   1. `logit` 을 -0.30 으로 시작한다. 이 값이 전체 양성 비율을 대략 정한다
    #      (음수라 절반보다 조금 낮게 나온다).
    #   2. 신호 컬럼 여섯 개를 하나씩 **표준화**한다 — 평균을 빼고 표준편차로
    #      나눠서 "평균에서 몇 표준편차 떨어졌나(z)"로 바꾼다. 단위가 다른
    #      값(%, kg/m², mmHg)을 같은 자로 재기 위해서다.
    #   3. 각 z에 가중치를 곱해 더한다. 가중치가 큰 LBXGH가 Y를 가장 많이 흔든다.
    #   4. 로지스틱 함수 1/(1+e^-logit) 로 그 합을 0~1 사이 **확률**로 바꾼다.
    #   5. 그 확률만큼의 확률로 동전을 던져 0/1을 정한다. 확률 그대로가 아니라
    #      동전을 한 번 더 던지기 때문에 완벽하지 않은, 현실 같은 노이즈가 남는다
    #      — 그래서 AUC가 1.0이 아니라 0.7 언저리에 머문다.
    #
    #   미끼 컬럼과 XVAR 잡음은 이 식 어디에도 등장하지 않는다. 그것이 그것들이
    #   "예측력 없음"인 이유다.
    logit = np.full(n_rows, -0.30)
    for col, weight in {**TRUE_SIGNAL, **WEAK_SIGNAL}.items():
        z = (df[col] - df[col].mean()) / df[col].std()
        logit += weight * z
    prob = 1.0 / (1.0 + np.exp(-logit))
    df[Y_COLUMN] = (rng.random(n_rows) < prob).astype(int)

    return df


# --------------------------------------------------------------------------- #
#  OKF bundle
# --------------------------------------------------------------------------- #
#
# Each entry: (id, type, title, tags, variables, description, body)
#
# `variables` is the code-to-concept mapping and the reason this design works.
# get_concept returns the whole frontmatter (mcp_servers/okf.py:331), so the key
# survives — but search_concepts and list_concepts return only id/type/title/tags.
# An agent can therefore FIND a concept by searching, and can only learn which column
# it refers to by opening it. Reading the knowledge source is unavoidable.
#
# Four kinds are mixed together:
#   1. Signal    — map to columns that genuinely predict Y
#   2. Decoy     — map to real columns with no predictive value
#   3. Trap      — map to codes absent from the dataset
#   4. Metadata  — map to nothing
#
# ↑ 항목 하나는 7칸짜리 묶음이다:
#   (아이디, 종류, 제목, 태그들, 변수코드들, 한 줄 설명, 본문)
#
#   이 중 `variables` 가 **코드 ↔ 개념을 잇는 유일한 다리**이고, 이 설계가 작동하는
#   이유다. 왜 그런가:
#     - `get_concept`(개념 하나를 열어 보기)은 머리말(frontmatter) 전체를 그대로
#       돌려주므로 `variables` 가 살아서 나온다.
#     - 반면 `search_concepts`·`list_concepts`(검색·목록)는 id / type / title / tags
#       네 가지만 돌려준다. `variables` 는 보이지 않는다.
#   그래서 에이전트는 검색으로 개념을 **찾을 수는** 있지만, 그 개념이 어느 컬럼을
#   가리키는지는 **열어 봐야만** 알 수 있다. 지식 원천을 실제로 읽는 일을 피할 수
#   없게 만든 것이다.
#
#   네 종류가 섞여 있다:
#     1. 신호(Signal)   — Y를 실제로 예측하는 컬럼을 가리킨다
#     2. 미끼(Decoy)    — 데이터에 있긴 하지만 예측력이 없는 컬럼을 가리킨다
#     3. 함정(Trap)     — 데이터에 아예 없는 코드를 가리킨다. 에이전트가 이것을
#                        고르면 "개념은 있는데 컬럼이 없다"는 상황이 만들어지고,
#                        파이프라인이 그 상황을 견디는지 알 수 있다
#     4. 메타데이터     — 아무 컬럼도 가리키지 않는다(코호트 설명, 측정 규약 등)

_CONCEPTS: list[tuple[str, str, str, list[str], list[str], str, str]] = [
    # -- 1. Signal -------------------------------------------------------
    #
    # ↑ 신호 개념 6개. 앞의 넷(glycemic_control, obesity_adiposity,
    #   hypertension_systolic, aging_demographics)이 TRUE_SIGNAL 을 가리키고,
    #   뒤의 둘(lipid_ldl, inflammatory_burden)이 WEAK_SIGNAL 을 가리킨다.
    #   본문에 적은 임상 설명은 사실에 가깝게 썼지만, 그 자체가 정답을 알려 주지는
    #   않는다 — 에이전트는 여전히 여러 후보 중에서 골라야 한다.
    (
        "glycemic_control",
        "risk_factor",
        "Glycemic control and adverse outcome risk",
        ["metabolic", "diabetes", "strong-evidence"],
        ["LBXGH"],
        "Glycated haemoglobin is the most consistently reported correlate of outcome risk across cohorts.",
        "Glycated haemoglobin reflects average blood glucose over the preceding two to three "
        "months. Observational studies repeatedly find outcome risk rising monotonically with "
        "each percentage point, and an independent contribution persists after adjusting for "
        "other metabolic markers.\n\n"
        "Related: [adiposity](obesity_adiposity), [inflammation](inflammatory_burden)",
    ),
    (
        "obesity_adiposity",
        "risk_factor",
        "Adiposity as a modifiable risk factor",
        ["metabolic", "anthropometric", "strong-evidence"],
        ["BMXBMI"],
        "Body mass index is the archetypal modifiable factor raising outcome risk through metabolic pathways.",
        "Body mass index is derived from height and weight and is present in almost every "
        "clinical record. It acts on outcome through insulin resistance and chronic "
        "inflammation. It overlaps with glycaemic markers but retains independent explanatory "
        "power.\n\nRelated: [glycemic control](glycemic_control)",
    ),
    (
        "hypertension_systolic",
        "risk_factor",
        "Systolic blood pressure and vascular risk",
        ["cardiovascular", "vital-sign", "strong-evidence"],
        ["BPXSY1"],
        "Systolic pressure indexes vascular load and is associated with outcome.",
        "Systolic blood pressure is a basic element of cardiovascular risk stratification. In "
        "older populations the systolic value discriminates outcome better than the diastolic "
        "one. Single readings vary considerably.",
    ),
    (
        "aging_demographics",
        "risk_factor",
        "Chronological age as a baseline risk axis",
        ["demographic", "baseline", "strong-evidence"],
        ["RIDAGEYR"],
        "Age explains baseline risk in nearly every outcome model.",
        "Age correlates broadly with the other risk factors, so omitting it inflates their "
        "apparent effects. For prediction it carries substantial explanatory power on its own.",
    ),
    (
        "lipid_ldl",
        "risk_factor",
        "LDL cholesterol in risk models",
        ["cardiovascular", "laboratory", "moderate-evidence"],
        ["LBDLDL"],
        "LDL cholesterol is associated with cardiovascular outcome, though the effect is moderate.",
        "LDL cholesterol has been studied for decades, but its independent contribution often "
        "shrinks once other metabolic markers enter the model. Statin use is a common "
        "confounder.",
    ),
    (
        "inflammatory_burden",
        "biomarker",
        "Systemic inflammation",
        ["inflammation", "laboratory", "moderate-evidence"],
        ["LBXCRP"],
        "C-reactive protein reflects systemic inflammatory burden and shows a weak association with outcome.",
        "C-reactive protein is heavily skewed, so a log transform is customary. It rises sharply "
        "during acute infection, which makes a single reading hard to interpret.",
    ),
    # -- 2. Decoys — real columns, no predictive value --------------------
    #
    # ↑ 미끼 개념 16개. 가리키는 컬럼은 데이터에 실제로 있고, 설명도 임상적으로
    #   말이 되지만, Y와는 무관하다. 이것들이 있어야 에이전트가 "OKF에 나온 것을
    #   전부 넣기"로 이길 수 없고, 실제로 골라야 하는 상황이 만들어진다.
    (
        "diastolic_pressure",
        "risk_factor",
        "Diastolic blood pressure",
        ["cardiovascular", "vital-sign"],
        ["BPXDI1"],
        "Diastolic pressure is part of the standard blood pressure pair.",
        "Diastolic pressure is recorded alongside systolic. Its prognostic value is weaker in "
        "older cohorts, where arterial stiffening lowers it while risk rises.",
    ),
    (
        "central_adiposity",
        "risk_factor",
        "Waist circumference as central adiposity",
        ["metabolic", "anthropometric"],
        ["BMXWAIST"],
        "Waist circumference is proposed as a measure of central fat distribution.",
        "Waist circumference is argued to capture visceral fat better than body mass index. "
        "Measurement protocols differ between studies, which limits comparability.",
    ),
    (
        "stature",
        "descriptor",
        "Standing height",
        ["anthropometric"],
        ["BMXHT"],
        "Standing height, a component of body mass index.",
        "Height is recorded as a component of body mass index. On its own it is rarely treated "
        "as a risk factor.",
    ),
    (
        "total_cholesterol",
        "risk_factor",
        "Total cholesterol",
        ["cardiovascular", "laboratory"],
        ["LBXTC"],
        "Total cholesterol aggregates the lipid fractions into one figure.",
        "Total cholesterol sums the lipid fractions and so obscures the opposing directions of "
        "the HDL and LDL components. Fraction-specific measures are usually preferred.",
    ),
    (
        "hdl_cholesterol",
        "risk_factor",
        "HDL cholesterol",
        ["cardiovascular", "laboratory"],
        ["LBDHDD"],
        "HDL cholesterol is conventionally described as protective.",
        "HDL cholesterol is inversely associated with cardiovascular events in observational "
        "data, though trials raising it have not reduced events.",
    ),
    (
        "triglycerides",
        "risk_factor",
        "Serum triglycerides",
        ["metabolic", "laboratory"],
        ["LBXTR"],
        "Triglycerides reflect recent dietary intake as much as chronic state.",
        "Triglycerides vary strongly with fasting status and recent meals, so a single "
        "measurement is noisy.",
    ),
    (
        "serum_albumin",
        "biomarker",
        "Serum albumin",
        ["laboratory", "nutrition"],
        ["LBXSAL"],
        "Albumin is used as a nutritional and hepatic synthetic marker.",
        "Albumin falls in inflammation and in liver disease, so it is nonspecific as a marker of "
        "any one condition.",
    ),
    (
        "liver_enzymes",
        "biomarker",
        "Hepatic transaminases",
        ["laboratory", "hepatic"],
        ["LBXSATSI", "LBXSASSI"],
        "Alanine and aspartate aminotransferase indicate hepatocellular injury.",
        "The transaminases rise with hepatocellular injury of any cause. Their ratio is sometimes "
        "used to suggest aetiology, with weak discrimination.",
    ),
    (
        "renal_function",
        "biomarker",
        "Serum creatinine",
        ["laboratory", "renal"],
        ["LBXSCR"],
        "Creatinine is the routine index of glomerular filtration.",
        "Creatinine depends on muscle mass as well as filtration, so it misclassifies at the "
        "extremes of body composition.",
    ),
    (
        "uric_acid",
        "biomarker",
        "Serum uric acid",
        ["laboratory", "metabolic"],
        ["LBXSUA"],
        "Uric acid has been proposed as a cardiometabolic marker.",
        "Uric acid is associated with metabolic syndrome components, but whether the association "
        "is causal remains contested.",
    ),
    (
        "leukocyte_count",
        "biomarker",
        "White blood cell count",
        ["laboratory", "inflammation"],
        ["LBXWBCSI"],
        "Leukocyte count is a coarse inflammatory index.",
        "White cell count rises in infection, in smoking and under stress, making it a blunt "
        "inflammatory marker compared with specific acute-phase proteins.",
    ),
    (
        "haemoglobin",
        "biomarker",
        "Haemoglobin concentration",
        ["laboratory", "haematology"],
        ["LBXHGB"],
        "Haemoglobin defines anaemia and varies with sex.",
        "Haemoglobin is used to define anaemia. Thresholds differ by sex, so an unadjusted value "
        "is hard to interpret.",
    ),
    (
        "platelets",
        "biomarker",
        "Platelet count",
        ["laboratory", "haematology"],
        ["LBXPLTSI"],
        "Platelet count relates to thrombotic and inflammatory states.",
        "Platelet count is elevated as an acute-phase response and reduced in hypersplenism, so "
        "it moves for many unrelated reasons.",
    ),
    (
        "electrolytes",
        "biomarker",
        "Serum sodium and potassium",
        ["laboratory"],
        ["LBXSNASI", "LBXSKSI"],
        "Sodium and potassium are the routine electrolyte pair.",
        "Electrolytes are tightly regulated, so values outside the reference range usually "
        "reflect acute illness or medication rather than chronic risk.",
    ),
    (
        "urinary_albumin",
        "biomarker",
        "Urinary albumin",
        ["laboratory", "renal"],
        ["URXUMA"],
        "Urinary albumin indicates glomerular leakage.",
        "Urinary albumin is highly variable between collections, so single untimed samples are "
        "unreliable.",
    ),
    (
        "bilirubin",
        "biomarker",
        "Total bilirubin",
        ["laboratory", "hepatic"],
        ["LBXSTB"],
        "Bilirubin reflects haem turnover and hepatic conjugation.",
        "Bilirubin rises in haemolysis and in hepatic dysfunction, and is mildly elevated in "
        "Gilbert syndrome, which is benign and common.",
    ),
    # -- 3. Traps — codes absent from the dataset -------------------------
    #
    # ↑ 함정 개념 4개. 운동량·나트륨 섭취·수면·소득 같은, 임상적으로는 그럴듯하고
    #   실제 논문에도 자주 나오는 변수들이다. 그런데 이 데이터셋에는 해당 컬럼이
    #   **없다**. 본문 끝의 "not present in every dataset" 이 유일한 경고다.
    #   에이전트가 이것을 고르면 파이프라인은 없는 컬럼을 요구받게 되고, 그 상황을
    #   조용히 넘기는지 아니면 제대로 보고하는지가 드러난다
    #   (집계의 `columns_missing_seen` 에 남는다).
    (
        "physical_activity",
        "risk_factor",
        "Weekly physical activity volume",
        ["lifestyle", "behavioral"],
        ["PAQ620"],
        "Weekly minutes of moderate activity are repeatedly reported to lower outcome risk.",
        "Activity volume shows a protective effect across cohorts, though self-report introduces "
        "considerable measurement error.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    (
        "dietary_sodium",
        "risk_factor",
        "Dietary sodium intake",
        ["lifestyle", "nutrition"],
        ["DR1TSODI"],
        "Daily sodium intake is thought to affect outcome through blood pressure.",
        "Twenty-four-hour urinary excretion is the reference measurement but is almost never "
        "present in clinical records.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    (
        "sleep_quality",
        "risk_factor",
        "Sleep duration and efficiency",
        ["lifestyle", "behavioral"],
        ["SLD012"],
        "Reduced sleep efficiency has been linked to worse metabolic outcomes.",
        "Sleep efficiency is measured by actigraphy or polysomnography. Most studies are small, "
        "so the evidence is weak.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    (
        "socioeconomic_status",
        "risk_factor",
        "Socioeconomic position",
        ["demographic", "social"],
        ["INDFMPIR"],
        "Income-to-poverty ratio is frequently named as a social determinant of outcome.",
        "Income position acts on outcome through access to care and health behaviours. "
        "Definitions differ between cohorts.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    # -- 4. Metadata — map to nothing -------------------------------------
    #
    # ↑ 메타데이터 개념 3개. `variables` 가 비어 있어 어떤 컬럼도 가리키지 않는다.
    #   코호트 구성, 측정 규약, 결측 양상처럼 **맥락**은 주지만 변수를 고르는 근거는
    #   되지 못하는 문서다. 실제 번들에도 이런 문서가 섞여 있으므로, 검색 결과에
    #   이런 것이 걸렸을 때 에이전트가 어떻게 하는지 보려고 넣었다.
    (
        "cohort_description",
        "metadata",
        "Cohort composition",
        ["study-design"],
        [],
        "Summary of the cohort this bundle refers to.",
        "A retrospective cohort of adult outpatients. Children and pregnant patients were "
        "excluded. Context, not grounds for selecting a variable.",
    ),
    (
        "measurement_protocol",
        "metadata",
        "Measurement protocol notes",
        ["study-design", "quality"],
        [],
        "How and when measurements were taken.",
        "Blood was drawn fasting. Blood pressure is the mean of two seated readings after five "
        "minutes of rest. Not grounds for selecting a variable.",
    ),
    (
        "missingness_notes",
        "metadata",
        "Missingness patterns",
        ["quality"],
        [],
        "Observations about the pattern of missing values.",
        "Laboratory tests are ordered on clinical indication, so missingness is unlikely to be at "
        "random. Not grounds for selecting a variable.",
    ),
]

_TRAP_IDS = {"physical_activity", "dietary_sodium", "sleep_quality", "socioeconomic_status"}
# ↑ 함정 개념의 아이디 모음. 나중에 "이 시행이 함정을 물었나"를 판정할 때 쓰라고
#   따로 모아 둔 것이다.


def write_okf_bundle(okf_dir: Path, stamp: str) -> None:
    """Write the concepts as OKF-shaped markdown files.

    Frontmatter keys are the ones core's OKF server reads (type / title / description /
    tags / generated / status) plus `variables`, which get_concept passes through
    untouched.

    ↑ 위의 개념 목록을 OKF 규격의 마크다운 파일로 하나씩 써 낸다. 개념 하나가
    파일 하나이고, 파일 이름은 `<개념 아이디>.md` 다.

    각 파일은 두 부분으로 되어 있다.
      - 머리말(frontmatter): 파일 맨 위 `---` 두 줄 사이에 오는 YAML 형식의 정보.
        core의 OKF 서버가 실제로 읽는 항목은 type / title / description / tags /
        generated / status 이고, 여기에 `variables` 를 하나 더 얹었다.
        `variables` 는 서버가 해석하지는 않지만 get_concept가 손대지 않고 그대로
        돌려주므로, 개념을 열어 본 에이전트에게는 보인다.
      - 본문: `#` 제목과 설명 문단.

    Args:
        okf_dir: 파일들을 쓸 폴더. 없으면 만든다.
        stamp: 머리말 `generated.at` 에 넣을 시각 문자열.
    """
    okf_dir.mkdir(parents=True, exist_ok=True)

    # 7칸 묶음을 하나씩 풀어서 마크다운 문자열로 조립한다.
    for cid, ctype, title, tags, variables, description, body in _CONCEPTS:
        # 태그를 YAML 목록 꼴("  - 태그")로 줄 단위 정렬한다.
        tag_lines = "\n".join(f"  - {t}" for t in tags)
        # 메타데이터 개념은 variables 가 비어 있다. 그럴 때는 `variables:` 키
        # 자체를 넣지 않는다 — 빈 목록을 남기면 "가리키는 컬럼이 없다"가 아니라
        # "목록이 비었다"로 읽힐 여지가 생긴다.
        var_block = ""
        if variables:
            var_lines = "\n".join(f"  - {v}" for v in variables)
            var_block = f"variables:\n{var_lines}\n"
        text = (
            "---\n"
            f"type: {ctype}\n"
            f"title: {title}\n"
            f"description: {description}\n"
            "tags:\n"
            f"{tag_lines}\n"
            f"{var_block}"
            "generated:\n"
            "  by: process:make_sample_data\n"
            f"  at: {stamp}\n"
            "status: draft\n"
            "---\n\n"
            f"# {title}\n\n"
            f"{body}\n"
        )
        (okf_dir / f"{cid}.md").write_text(text, encoding="utf-8")

    # index.md and log.md are the spec's special files. The OKF server does not count
    # them as concepts (_RESERVED_ROOT_STEMS), so writing them cannot pollute search.
    #
    # ↑ index.md(목차)와 log.md(변경 기록)는 OKF 규격이 정해 둔 특별한 파일이다.
    #   OKF 서버는 이 둘을 개념으로 세지 않으므로(_RESERVED_ROOT_STEMS 목록),
    #   이 파일들을 써도 검색 결과가 오염되지 않는다. 즉 개념은 31개 그대로다.
    listing = "\n".join(f"- [{t}]({c}) — {d}" for c, _tp, t, _tg, _v, d, _b in _CONCEPTS)
    (okf_dir / "index.md").write_text(
        f"# Sample OKF bundle\n\nSynthetic bundle holding {len(_CONCEPTS)} concepts.\n\n{listing}\n",
        encoding="utf-8",
    )
    (okf_dir / "log.md").write_text(
        f"# Change log\n\n- {stamp} · process:make_sample_data · bundle created "
        f"({len(_CONCEPTS)} concepts)\n",
        encoding="utf-8",
    )


def main() -> int:
    """명령줄에서 인자를 받아 데이터셋과 OKF 번들을 만들고, 무엇을 만들었는지 알린다.

    Returns:
        종료 코드. 항상 0(정상)이다.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1700, help="dataset row count")
    ap.add_argument("--seed", type=int, default=42)
    # Taken as an argument rather than read from the clock so re-running produces
    # byte-identical output.
    #
    # ↑ 시각을 시계에서 읽지 않고 인자로 받는다. 시계를 읽으면 돌릴 때마다 파일이
    #   달라져서, 내용은 같은데 diff에는 변경으로 잡힌다. 인자로 고정하면 다시
    #   돌려도 **바이트 단위로 똑같은** 결과가 나온다.
    ap.add_argument("--stamp", default="2026-08-10T00:00:00Z", help="OKF generated.at timestamp")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 표를 만들어 CSV로 저장하고, 이어서 개념 파일들을 쓴다.
    df = build_dataset(args.rows, args.seed)
    df.to_csv(DATASET, index=False)
    write_okf_bundle(OKF_DIR, args.stamp)

    # 아래 세 줄은 검산이다. 개념들이 언급한 컬럼 코드를 전부 모아서(described),
    # 그중 데이터에 실제로 있는 것(in_data)과 없는 것(absent = 함정)을 갈라 센다.
    # c[4] 는 7칸 묶음의 다섯 번째 칸, 즉 `variables` 다.
    described = {v for c in _CONCEPTS for v in c[4]}
    in_data = described & set(df.columns)
    absent = described - set(df.columns)

    # 아래는 사람이 보라고 찍는 요약이다. 무엇이 신호이고 무엇이 미끼인지 여기서
    # 한 번 드러내지만, 이 출력은 터미널에만 남고 에이전트에게는 가지 않는다.
    print(f"dataset: {DATASET}")
    print(f"  {len(df)} rows x {len(df.columns)} columns (Y included)")
    print(f"  Y='{Y_COLUMN}' positive rate: {df[Y_COLUMN].mean():.1%}")
    print(f"  true signal  : {', '.join(TRUE_SIGNAL)}")
    print(f"  weak signal  : {', '.join(WEAK_SIGNAL)}")
    print(f"  decoys       : {len(DECOY_COLUMNS)} described, non-predictive")
    print(f"  unlabelled   : XVAR001 ... XVAR{N_UNLABELLED_NOISE:03d}")
    print()
    print(f"OKF bundle: {OKF_DIR}")
    print(f"  {len(_CONCEPTS)} concepts + index.md + log.md")
    print(f"  describing {len(in_data)} columns that exist, {len(absent)} that do not (traps)")
    print()
    print("Column names carry no meaning — the only route from a code to its meaning is OKF.")
    print()
    # ↑ 이 한 줄이 이 데이터의 설계 의도를 요약한다: 컬럼 이름 자체는 아무 뜻도
    #   담지 않으며, 코드에서 의미로 가는 길은 OKF 하나뿐이다.
    print("Next — export the environment:")
    # ↑ 다음 단계 안내. 아래 세 환경변수를 내보내면 파이프라인이 방금 만든
    #   데이터와 번들을 찾아 쓴다.
    print(f'  export AGENTIC_OKF_BUNDLE_DIR="{OKF_DIR}"')
    print(f'  export MEMSTARA_DATASET_PATH="{DATASET}"')
    print(f'  export MEMSTARA_OUTPUT_DIR="{OUT_DIR}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
