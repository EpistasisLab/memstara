#!/usr/bin/env python3
"""The single place where the environment is set up.

Why this file exists
--------------------
"the environment differs depending on how you launched it" is the trap that caught
this project four times in one day.

    (1) sourcing only one file in the terminal — no LLM credentials, dead on the
        first call
    (2) VS Code's `envFile` accepting a single path — same symptom
    (3) `MEMSTARA_DEBUGPY` left out of the allowlist — the hook quietly did nothing
    (4) verifying along a path that was not the real one — fine from the terminal,
        broken under F5

All four share one root: **the code that set up the environment lived separately at
every entry point.** Separate copies always drift apart.

So it is gathered here. `02_mvp_pipeline.py`, `03_board_pipeline.py`,
`debug_harness.py` and `preflight.py` all call this file, and a new entry point
needs a single line: `load_env()`.

Why there are two `.env` files
------------------------------
    memstara/.env   MEMSTARA_* — this product's paths and settings
    agentic-core/.env           LLM credentials, AGENTIC_DATABASE_URL — core's own

They are not merged. Merging would put secrets in two places, and the copy would
fall behind whenever the original changed. **Both are read instead.**

환경을 세우는 **단 하나의** 자리.

왜 이 파일이 있나
------------------
"실행 방법마다 환경이 달라진다" 는 이 프로젝트에서 하루에 네 번 걸린 함정이다.

    ① 터미널에서 `source` 를 하나만 해서 — LLM 자격증명이 없어 첫 호출에서 죽음
    ② VS Code 의 `envFile` 이 파일 하나만 받아서 — 같은 증상
    ③ `MEMSTARA_DEBUGPY` 를 허용 목록에 안 넣어서 — 갈고리가 조용히 아무 일도 안 함
    ④ 내 검증이 실제 사용 경로와 달라서 — 터미널에서는 되는데 F5 로는 안 됨

전부 같은 뿌리다. **환경을 세우는 코드가 진입점마다 따로 있었다.** 따로 있으면
반드시 어긋난다.

그래서 여기 하나로 모은다. `02_mvp_pipeline.py` · `03_board_pipeline.py` ·
`debug_harness.py` · `preflight.py` 가 전부 이 파일을 부른다. 새 진입점을 만들 때도
`load_env()` 한 줄이면 된다.

`.env` 가 둘인 이유
-------------------
    memstara/.env   MEMSTARA_* — 이 제품의 경로와 설정
    agentic-core/.env           LLM 자격증명 · AGENTIC_DATABASE_URL — core 의 것

합치지 않는다. 합치면 비밀값이 두 곳에 생기고, 원본이 바뀔 때 사본이 뒤처진다.
대신 **둘 다 읽는다.**
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent.resolve()

# Turn litellm's request logging on **at import time**, not inside `load_env()`.
#
# litellm reads `LITELLM_LOG` while it is being imported (`litellm/_logging.py:80`),
# and by the time `load_env()` runs inside `main()` litellm has long since been
# imported by `pipeline_core`. Setting it later leaves the request bodies unlogged —
# which is exactly how this first failed, silently.
#
# So every entry point must import `bootstrap` **before** anything that pulls in
# agentic_core / litellm.
#
# litellm 의 요청 본문 로그를 **import 시점에** 켠다. `load_env()` 안이 아니다.
#
# litellm 은 import 되는 그 순간 `LITELLM_LOG` 을 읽는다(`litellm/_logging.py:80`).
# `load_env()` 는 `main()` 안에서 도는데, 그때는 `pipeline_core` 가 이미 litellm 을
# 끌어온 뒤다. 나중에 설정하면 요청 본문이 한 건도 안 남는다 — 아무 오류 없이.
# 실제로 그렇게 두 번 걸렸다.
#
# 그래서 모든 진입점은 agentic_core · litellm 을 끌어오는 것보다 **먼저**
# `bootstrap` 을 import 해야 한다.
#
# setdefault 라 셸이나 launch.json 이 준 값이 이긴다.
os.environ.setdefault("LITELLM_LOG", "DEBUG")

#: The `.env` files to read, **in priority order**.
#:
#: `load_dotenv` never overwrites a value that is already set (override=False is the
#: default), so whichever file is read first wins, and whatever the shell or
#: launch.json supplied beats both — which is what keeps "a different bundle for
#: this run only" working.
#:
#: 읽을 `.env` 들, **우선순위 순서대로**.
#:
#: `load_dotenv` 는 이미 있는 값을 덮지 않는다(override=False 가 기본). 그래서 먼저
#: 읽은 쪽이 이기고, 셸이나 launch.json 이 준 값은 둘 다보다 앞선다 — "이 실행에만
#: 다른 번들" 이라는 의도가 유지된다.
ENV_FILES = (
    HERE / ".env",                            # this product's first / 이 제품의 것이 먼저
    HERE / ".." / "agentic-core" / ".env",    # core fills the gaps / core 의 것으로 빈 자리를 채운다
)

#: Required for any run, whichever entry point started it.
#:
#: 어떤 실행이든 있어야 하는 것.
BASE_VARS = {
    "AGENTIC_OKF_BUNDLE_DIR": "지식원 폴더",
    "MEMSTARA_DATASET_PATH": "데이터 csv",
    "MEMSTARA_OUTPUT_DIR": "하위 데이터가 나갈 곳",
    "AGENTIC_DATABASE_URL": "core 의 DB — 에이전트와 실행 이력",
}

#: Extra keys each provider needs. Only the one picked with `--provider` is checked.
#:
#: Before this existed, empty credentials did not surface until the **first LLM
#: call** — by which point a seeding round had been spent and the board already
#: carried rows.
#:
#: provider 마다 더 있어야 하는 것. `--provider` 로 고른 것만 검사한다.
#:
#: 이것이 없던 동안은 자격증명이 비어도 **첫 LLM 호출까지 가서야** 터졌다. 그때는
#: 이미 씨뿌리기 한 번을 쓴 뒤이고 판에도 줄이 남는다.
PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def load_env() -> list[Path]:
    """Read the `.env` files and return the ones that were actually read.

    Safe to call repeatedly — existing values are never overwritten.

    `.env` 들을 읽는다. 읽힌 파일을 돌려준다.

    여러 번 불러도 안전하다 — 이미 있는 값은 안 덮는다.
    """
    read: list[Path] = []
    for path in ENV_FILES:
        if path.is_file():
            load_dotenv(path)
            read.append(path.resolve())
    return read


def missing_vars(provider: str = "") -> list[str]:
    """Return every missing environment variable **at once**. An empty list means ready.

    Reported together so that fixing one and re-running does not simply reveal the
    next one.

    빠진 환경변수를 **한꺼번에** 돌려준다. 빈 목록이면 준비된 것이다.

    하나 고치고 다시 돌려서 또 하나를 발견하는 일을 없애려고 모아서 준다.
    """
    problems = [f"{name} 이 없다 — {hint}"
                for name, hint in BASE_VARS.items()
                if not os.environ.get(name, "").strip()]
    problems += [f"{name} 이 없다 — --provider {provider} 에 필요하다. agentic-core/.env 를 확인하라."
                 for name in PROVIDER_KEYS.get(provider, ())
                 if not os.environ.get(name, "").strip()]
    return problems


def allowlist_gaps() -> list[str]:
    """Find environment variables the tool servers read that the allowlist omits.

    **This is the most valuable check in this file.**

    Core passes only the names listed in `mcp_allowed_env_vars` down to child
    processes. A name left off that list **never reaches the tool server, and
    nothing raises an error.** The tool simply falls back to a default, or quietly
    does nothing at all.

    That happened for real: `MEMSTARA_DEBUGPY` was missing from the list, so the
    debugger hook never opened its port, and the logs said nothing. Tracking down
    the cause took a long time.

    A hand-maintained list is guaranteed to drift, so **the sources are scanned and
    compared** instead.

    도구 서버가 읽는데 허용 목록에 없는 환경변수를 찾는다.

    **이것이 이 파일에서 가장 값어치 있는 검사다.**

    core 는 `mcp_allowed_env_vars` 에 적힌 것만 자식 프로세스에 넘긴다. 목록에
    빠뜨리면 그 변수는 도구 서버에 **도착하지 않고, 아무 오류도 안 난다.** 도구는
    그냥 기본값으로 동작하거나 조용히 아무 일도 안 한다.

    실제로 그렇게 당했다 — `MEMSTARA_DEBUGPY` 를 목록에 안 넣어서 디버거 갈고리가
    포트를 안 열었는데, 로그에는 아무것도 없었다. 원인을 찾는 데 한참 걸렸다.

    손으로 맞추는 목록은 반드시 어긋나므로, **소스를 읽어 대조한다.**
    """
    from settings import Settings

    allowed = {v.strip() for v in Settings().mcp_allowed_env_vars.split(",") if v.strip()}

    # Scrape the names the tool servers actually read straight out of the sources.
    # Catches both `os.environ.get("X")` and `os.environ["X"]`.
    #
    # 도구 서버들이 실제로 읽는 이름을 소스에서 긁는다.
    # `os.environ.get("X")` · `os.environ["X"]` 둘 다 잡는다.
    pattern = re.compile(r'os\.environ(?:\.get)?[\[(]\s*"([A-Z_][A-Z0-9_]*)"')
    read: set[str] = set()
    for path in sorted(HERE.glob("tools_*.py")) + [HERE / "debug_hook.py"]:
        if path.is_file():
            read |= set(pattern.findall(path.read_text(encoding="utf-8")))

    # Names core forwards by default — they arrive even when the list omits them.
    #
    # PYDEVD_* is set by debug_hook **inside its own process**, so it need not come
    # from the parent. PATH and friends are already on core's default list.
    #
    # core 가 기본으로 넘기는 것들. 목록에 없어도 도착한다.
    #
    # PYDEVD_* 는 debug_hook 이 **자기 프로세스 안에서 설정**하는 것이라 부모에게서
    # 받을 필요가 없다. PATH 같은 것도 core 의 기본 목록에 있다.
    always = {"AGENTIC_OKF_BUNDLE_DIR", "PATH", "HOME", "PYDEVD_DISABLE_FILE_VALIDATION"}

    return sorted(name for name in read - allowed - always)
