# memstara — 개인 실험 공간

> **이름이 바뀌었다.** `EcoXAI` 는 가제였고, 2026-08-18 팀 결정으로 **Memstara** 가
> 공식 이름이 됐다. 코드·문서·데이터베이스·도커·저장소 전부 같은 날 바꿨다.

> 적은 기록이라, 당시 쓰지도 않던 이름으로 바꾸면 기록이 아니게 된다.

`motoro`를 **라이브러리로 가져다 쓰는** 내 실험 스크립트와 요구사항을 두는 곳.
이름이 `agentic-core-`로 시작하는 것은 무엇에 대한 실험인지 폴더 이름만으로 알기
위해서다 — 라이브러리가 `motoro`로 개명된 뒤에도 이 저장소 이름은 그대로 두었다.

## 이 폴더의 성격 — git 저장소 밖에 있다

```
EcoXAI_Projects/              ← git 저장소가 아님
├── motoro/                   ← git 저장소 (upstream + 내 private fork)
└── memstara/     ← 여기. 저장소 밖
```

**어떤 git 저장소에도 속하지 않는다.** 그래서 실수로 커밋할 대상 자체가 없다.

처음에는 `motoro/sandbox/`에 두고 ignore 규칙 두 층(`.gitignore`,
`.git/info/exclude`)으로 막았지만, 그 방식은 규칙이 계속 맞아야만 안전하다.
특히 `.git/info/exclude`는 clone으로 전파되지 않아 다른 머신에서는 보호가 사라진다.
밖으로 옮기면서 그 의존이 없어졌고, **저장소는 upstream과 완전히 동일한 상태로 복구했다.**

여기에는 회의 기록과 사진이 들어 있다. 저장소 안으로 다시 옮기지 말 것.

대가: **백업도 동기화도 없다.** 이 머신에만 존재한다.

## 구조

`examples/`와 같은 **평평한(flat) 배치**다. 스크립트가 `from settings import Settings`로
같은 디렉터리의 설정을 읽기 때문에, 하위 폴더로 내리면 그 import가 깨진다.

**문서는 최상위에 두지 않는다.** `README.md` 하나만 남기고 성격에 맞는 폴더로
내린다 — 최상위에 여덟 개가 평평하게 놓여 있으면 어디부터 볼지를 읽는 사람이
매번 판단해야 한다. 코드가 평평한 것과는 다른 문제다.

```
memstara/
├── README.md              이 파일 — 유일한 최상위 문서
│
├── settings.py            CoreSettings 서브클래스 (모든 스크립트가 공유)
├── 01_hello_agent.py      동작 확인용 첫 스크립트
│
│                          ── MVP 파이프라인 ──
├── make_sample_data.py    합성 데이터셋 + 샘플 OKF 번들 생성 (최초 1회)
├── tools_data.py          MCP 서버 — describe_dataset · slice_columns
├── tools_ml.py            MCP 서버 — train_and_score
├── pipeline_core.py       에이전트 4종 · supervisor · 집계
├── 02_mvp_pipeline.py     진입점 — N회 시행 후 겹침 집계
├── logging_setup.py       로그 출력 설정 (콘솔 + JSONL)
├── trace_run.py           저장된 실행 기록 재생 뷰어
│

├── papers/                받아온 논문 (_INDEX.md에 목록)
├── spec/                  요구사항 명세서(SRS) + 컴포넌트 구현계획 10개 + 요구사항 템플릿

├── kg/alzkb/              AlzKB 지식그래프 실물 + 적재 스크립트
└── outputs/               데이터셋 · OKF 번들 · 실행 산출물 (README.md에 목록)
```


파일을 열지 않고도 판단이 되고, 색인도 각자 하나씩만 두면 된다.


`2026-08-12_AlzKB_구조_설명_KR.md`처럼. 언제 쓴 글인지가 목록에서 바로 보이고,
`ls`만으로 시간순이 잡힌다.

## 이 폴더가 Memstara 제품이 된다

`spec/Memstara_SRS_KR.md`가 **이 제품의 요구사항 명세서**다.
2026-08-11에 `Rebuild_2026/`에서 옮겨왔다 — 제품이 여기가 되기 때문이다.

명세서는 **승인 대기 중인 초안(0.3)** 이고, 미해결 항목 15건과
승인이 필요한 제안이 표기로 구분돼 있다. **손대기 전에 그 표기 규약을 볼 것.**

## 지금 무엇이 열려 있는가



의 네 질문에서, 보드 필드는 ASAREE Roadmap 에서 왔다. **아래 「읽는 순서」가
"무엇을 만드는가"라면 이쪽은 "지금 어디까지 왔는가"다.**

**`BACKLOG_KR.md`** 는 그 한국어 전문 대응판이다(요약 아님). **GitHub 이슈가 되는 것은
영문판이고, 둘이 어긋나면 영문판이 맞다.**

## 읽는 순서

1. **`spec/Memstara_SRS_KR.pdf`** — **무엇을 만들어야 하는가.**
   §2.3 사용자 특성과 §11 미해결 사항부터 보면 무엇이 정해졌고 무엇이 안 정해졌는지 잡힌다

   그 자리의 기록. 같은 날짜의 `_WHITEBOARD.HEIC`가 그 자리의 화이트보드다

   §2의 표("core가 주는 것 / 내가 만들 것")부터 보면 작업량이 바로 잡힌다.

   8/12 정렬 논의 대비 미완성 항목과 그 순서
5. **`01_hello_agent.py`** — 먼저 이것부터 돌려서 환경이 되는지 확인
6. **`02_mvp_pipeline.py`** — 4단계 파이프라인 전체



## MVP 파이프라인 실행

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro

# 준비 (최초 1회) — conda 환경을 켠다
conda activate memstara
python ../memstara/make_sample_data.py

# 환경변수 — 이것이 빠지면 MCP 도구 서버가 경로를 못 찾는다
set -a && . ./.env && set +a
export AGENTIC_OKF_BUNDLE_DIR="$PWD/../memstara/outputs/okf_synthetic_sample"
export MEMSTARA_DATASET_PATH="$PWD/../memstara/outputs/dataset.csv"
export MEMSTARA_OUTPUT_DIR="$PWD/../memstara/outputs"

# 스모크 3회 → 본 실행 20회
python ../memstara/02_mvp_pipeline.py --trials 3 --trace
python ../memstara/02_mvp_pipeline.py --trials 20
```

**합성 데이터에는 진짜 신호가 심어져 있습니다** — `hba1c` · `bmi` · `age` ·
`systolic_bp` 넷이 결과변수를 실제로 예측합니다(단변량 AUC 0.73/0.66/0.63/0.60,
잡음 컬럼은 0.51). 20회 집계에서 이 넷이 상위로 올라오면 파이프라인이 동작하는
것이고, 안 올라오면 어딘가 깨진 것입니다.

### 실제 운용 데이터 구성 (2026-08-23 확정)

합성 데이터로 스모크 테스트 통과 후, 아래 실제 데이터로 전환한다.

| 역할 | 경로 | 내용 |
|---|---|---|
| 지식원 (OKF) | `../shared/hiv-suppression/okf/` | HIV 억제 관련 논문 142편, 8개 도메인 폴더 |
| ML 데이터셋 | `../attri_shared/ecoxai_dataset_2.5pct_no_PHI.csv` | 1,707명 × 1,393 feature, outcome: `HIV_DETECTABLE` |

```bash
export AGENTIC_OKF_BUNDLE_DIR=../shared/hiv-suppression/okf
export MEMSTARA_DATASET_PATH=../attri_shared/ecoxai_dataset_2.5pct_no_PHI.csv
export MEMSTARA_OUTCOME_COLUMN=HIV_DETECTABLE
python 03_board_pipeline.py --trials 3 --trace
```

**데이터 역할 분담:**
- OKF → hypothesis 에이전트가 읽어 feature 선택 가설 생성
- EcoXAI CSV → data/ml 에이전트가 읽어 실제 ML 검증

OKF에는 **데이터셋에 없는 변수를 가리키는 함정 개념 4개**도 들어 있습니다. 지식원
개념명과 데이터셋 컬럼명이 어긋나는 것이 이 파이프라인에서 가장 먼저 터질
지점이라, 예시가 그것을 재현하도록 일부러 넣었습니다.

## 준비 (최초 1회)

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro

# 1) 인프라 — postgres :5453, redis :6381, 스키마 적용까지
cp .env.example .env          # 그리고 .env에 API 키를 채운다
docker compose up -d

# 2) 파이썬 환경 — conda. core는 editable로 들어간다
#    (샌드박스 폴더에서 실행한다. environment.yml이 ../motoro를 상대경로로 가리킨다)
conda env create -f ../memstara/environment.yml
conda activate memstara
```

> **core 는 전부 `motoro` 다** (2026-09-01, `v0.5.2` 기준).
> 파이썬 패키지 `motoro` (`from motoro import ...`), 로컬 폴더 `../motoro/`,
> 환경변수 접두사 `MOTORO_`, 도커 컨테이너 `motoro-postgres`/`motoro-redis`,
> 데이터베이스 `motoro`/`motoro_test`, alembic 버전표 `alembic_version_motoro`.
> `environment.yml` 과 `.vscode/launch.json` 이 `../motoro` 를 상대경로로 가리키므로
> **폴더 이름을 바꾸면 둘 다 같이 고쳐야 한다.**
>
> **두 이름은 이 규칙을 따르지 않는다.**
> 하나는 **이 저장소 자신의 이름 `memstara`** 로, 무엇에 대한 실험인지
> 폴더 이름만으로 알기 위해 그대로 두었다(맨 위 참조).
> 다른 하나는 **`AGENTIC_OKF_BUNDLE_DIR`** 로, 상류가 접두사를 거치지 않고 이 문자
> 그대로 읽는다 (`motoro/src/motoro/mcp_servers/okf.py:66`, `mcp/client.py:57`) —
> 접두사를 따라 바꾸면 **OKF 서버가 번들을 못 찾는다.**
>
> Postgres 역할 이름은 **`agentic` 그대로**다. 상류 자신이 `POSTGRES_USER=agentic`
> 을 쓰기 때문에(`motoro/.env.example:6`) 여기서 바꾸면 상류와 어긋난다.

파이썬은 **conda 환경 `memstara`** 하나로 통일돼 있다(3.12). `motoro`는
editable로 설치돼 있어 소스를 고치면 재설치 없이 반영된다. 도구 서버는
`sys.executable`로 뜨므로 자식 프로세스도 같은 환경을 쓴다.

VS Code는 `.vscode/settings.json`이 이 환경을 가리킨다. conda `base`를 고르면
`import asyncpg`부터 실패한다.

`.env`에 최소 하나의 프로바이더 자격증명이 필요하다:

```bash
ANTHROPIC_API_KEY=sk-ant-...
# 또는 Foundry — 둘 다 필수
ANTHROPIC_FOUNDRY_API_KEY=...
ANTHROPIC_FOUNDRY_RESOURCE=...
```

## 실행

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro
set -a && . ./.env && set +a          # .env를 환경변수로 올린다
python ../memstara/01_hello_agent.py --input "17 곱하기 23은?"
```

`set -a && . ./.env && set +a`를 잊으면 DB 접속이나 자격증명 해석에서 실패한다.

## 새 실험 스크립트를 추가할 때

1. 이 폴더에 `NN_이름.py`로 파일을 만든다 (번호는 순서를 보기 쉽게 하려는 것뿐).
2. 맨 위에서 `from settings import Settings` → `configure(Settings())`를 **가장 먼저** 호출한다.
   core 모듈이 설정을 읽기 시작한 뒤에 부르면 `RuntimeError`가 난다.
3. `01_hello_agent.py`를 복사해서 시작하는 것이 가장 빠르다.

## 참고

- 공개 API 전체와 사용 예시: 저장소 밖 `../AgenticCore_상세해설_KR.pdf` §4
- core가 제공하는 원본 예시: `../motoro/examples/` (provision / run / memory_run / mcp_run)

