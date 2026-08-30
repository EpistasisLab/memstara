"""The settings class every sandbox script shares.

Subclasses `CoreSettings` and picks an environment prefix. Core deliberately sets
no prefix of its own — that is a product concern, and here the product is this
sandbox.

The prefix is `AGENTIC_` because the repo's own `.env.example` already uses
`AGENTIC_DATABASE_URL` / `AGENTIC_REDIS_URL`. Reusing it avoids a second set of
names for the same things.

Provider credentials are the exception. `CoreSettings` gives them bare-name
validation aliases, so `ANTHROPIC_API_KEY` / `ANTHROPIC_FOUNDRY_API_KEY` /
`ANTHROPIC_FOUNDRY_RESOURCE` / `OPENAI_API_KEY` are read exactly as written,
*without* the prefix — they are conventional names other tooling already sets.


==============================================================================
 이 파일을 읽는 법
==============================================================================

 이 폴더의 모든 스크립트가 공유하는 설정 하나. core 의 `CoreSettings` 를 물려받아
 **core 의 기본값 중 이 프로젝트에 안 맞는 것만** 덮어쓴다.

 덮어쓰는 것 넷:

   mcp_allowed_env_vars        도구 서버(자식 프로세스)에 넘길 환경변수 목록
   llm_call_timeout_seconds    LLM 한 번 기다릴 시간
   hook_timeout_seconds        그 바깥 울타리 — core 기본값은 안팎이 뒤집혀 있다
   act_prior_result_max_chars  도구 결과를 몇 자에서 자를까

 접두사가 `AGENTIC_` 인 이유는 저장소의 `.env.example` 이 이미
 `AGENTIC_DATABASE_URL` 을 쓰기 때문이다. 같은 것에 이름을 두 벌 두지 않는다.

 다만 **자격증명은 접두사가 없다.** `ANTHROPIC_API_KEY` 같은 이름은 다른 도구들이
 이미 그렇게 쓰므로, core 가 그 이름 그대로 읽도록 별칭을 달아 두었다.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from agentic_core import CoreSettings


class Settings(CoreSettings):
    """Settings for the sandbox experiments.

    샌드박스 실험용 설정. 아래 네 개 말고는 전부 core 의 기본값을 그대로 쓴다.
    """

    model_config = SettingsConfigDict(env_prefix="AGENTIC_", env_file=".env", extra="ignore")

    # ------------------------------------------------------------------ #
    # MCP subprocess env allowlist — the tool servers die without this
    # 도구 서버에 넘길 환경변수 목록 — 이게 없으면 서버가 못 산다
    # ------------------------------------------------------------------ #
    #
    # Core does not hand an MCP subprocess the host environment wholesale. It
    # copies only what is on the allowlist (`build_subprocess_env` in
    # mcp/client.py). The point is isolation: secrets must not leak into a
    # server core does not control.
    #
    # ↑ core 는 자식 프로세스에 호스트 환경을 통째로 주지 않는다. **이 목록에 적힌
    #   것만** 복사한다. 목적은 격리다 — core 가 통제하지 못하는 서버로 비밀값이
    #   새면 안 되기 때문이다.
    #
    # Default allowlist: PATH · HOME · SHELL · TERM · USER · LOGNAME · LANG ·
    #                    LC_ALL · AGENTIC_OKF_BUNDLE_DIR (+ two ARES-specific)
    #
    # AGENTIC_OKF_BUNDLE_DIR is already there because core ships its own OKF
    # server. The three below belong to this sandbox's tool servers
    # (tools_data.py / tools_ml.py), so they have to be opened explicitly.
    # Without them the servers cannot find their paths, and the only symptom is
    # a connection failure that says nothing about the cause.
    #
    # ↑ **이 목록에서 빠뜨리면 조용히 실패한다.** 변수가 도구 서버에 도착하지 않고,
    #   오류도 안 난다. 증상은 "붙지 못했다" 한 줄뿐이라 원인을 가리키지 않는다.
    #   실제로 그렇게 두 번 당했다 — 경로 하나, 디버깅 스위치 하나.
    #   `preflight.py` 가 이제 소스를 읽어 이 목록과 대조한다.
    # MEMSTARA_DATABASE_URL is the fourth, and it is a different kind of entry.
    #
    # The default list leaves database credentials out on purpose — `build_subprocess_env`
    # in mcp/client.py says it is there to keep secrets from reaching *untrusted* MCP
    # server subprocesses. The blackboard server is not untrusted; it is this folder's
    # own file, and the 2026-08-12 alignment put the board in a table precisely so the
    # agents would reach it through a server rather than by querying a database.
    #
    # Extending this list is the mechanism core provides for exactly that — the
    # allowlist is assembled as "default + whatever the product configured"
    # (mcp/client.py:56). So this is the sanctioned path, not a way around a wall.
    # Only this one server needs it; the other three never read it.
    #
    # Note what is NOT here: `AGENTIC_DATABASE_URL`. The board has its own database now
    # (docker-compose.yml), and core's credentials have no business reaching a server
    # of ours. Passing them once is how the board ended up inside core's database.
    #
    # ↑ **여기 없는 것**에 주목하라 — `AGENTIC_DATABASE_URL`. 판은 이제 자기 DB 가
    #   있고(docker-compose.yml), core 의 자격증명이 우리 서버에 갈 이유가 없다.
    #   한 번 넘겨 준 것이 판이 core 의 DB 안에 들어가 있던 원인이었다.
    #
    # The last two are for debugging and carry no secret. A tool server runs as a child
    # process, so a debugger attached to the pipeline never reaches it; `debug_hook.py`
    # lets one wait for a debugger, but only when told to by name. Without these on the
    # list the variable never arrives and the hook silently does nothing — which is
    # exactly how it first failed here, with the port simply never opening.
    #
    #     MEMSTARA_DEBUGPY        which servers should wait: "data" or "okf,ml"
    #     MEMSTARA_DEBUGPY_WAIT   "0" opens the port without blocking startup
    #
    # Unset means unchanged behaviour: the hook returns immediately and nothing is
    # imported. Verified — a normal run shows four servers connected and no mention of
    # debugpy anywhere.
    mcp_allowed_env_vars: str = (
        "MEMSTARA_DATASET_PATH,MEMSTARA_OUTPUT_DIR,MEMSTARA_ML_ENGINE,MEMSTARA_DATABASE_URL,"
        "MEMSTARA_OUTCOME_COLUMN,"
        "MEMSTARA_DEBUGPY,MEMSTARA_DEBUGPY_WAIT,"
        # debugpy 가 자식 파이썬이 **시작하는 순간** 검사해서 경고를 찍는다. 코드
        # 안에서 끄면 이미 늦다(quiet_child 로 시도했다가 확인함). 부모가 미리 주고
        # 이 목록에 있어야 자식에게 도착한다. 비밀값이 아니다.
        "PYDEVD_DISABLE_FILE_VALIDATION"
    )

    # ------------------------------------------------------------------ #
    # Timeouts — core's shipped defaults are inverted
    # 시간 제한 — core 의 기본값은 안팎이 뒤집혀 있다
    # ------------------------------------------------------------------ #
    #
    # Core ships hook_timeout_seconds=30 while llm_call_timeout_seconds=120
    # (config.py:77,102). The outer bound is 4x tighter than the inner one, so a
    # slow completion always trips the hook first — and the abort message names
    # hook_timeout_seconds regardless of which timeout actually fired, which
    # points at the wrong knob.
    #
    # README.md:153-159 says to keep hook_timeout_seconds "comfortably above"
    # llm_call_timeout_seconds. The defaults contradict that. Observed here: at
    # concurrency 5 against Foundry, reason_act's pre_act hook exceeded 30s on
    # 5 of 8 trials.
    #
    # ↑ 안쪽(LLM 한 번)이 120초인데 바깥 울타리(hook)가 30초였다. 바깥이 안쪽보다
    #   좁으니 느린 응답은 **항상 바깥이 먼저** 끊는다. 게다가 오류 메시지는 어느
    #   쪽이 끊었든 hook_timeout_seconds 를 가리켜서 엉뚱한 손잡이를 돌리게 만든다.
    #   그래서 바깥을 300초로 넓혔다.
    llm_call_timeout_seconds: int = 120
    hook_timeout_seconds: int = 300

    # ------------------------------------------------------------------ #
    # Tool-result truncation — the shipped default cuts real OKF bodies in half
    # 도구 결과 자르기 — core 기본값은 진짜 논문 본문을 반으로 자른다
    # ------------------------------------------------------------------ #
    #
    # Core truncates a prior tool result at 4,000 characters (config.py:88). That is
    # fine for the synthetic sample bundle, whose concepts are a few hundred
    # characters, and wrong for anything written from real papers.
    #
    # Measured on the shared hiv-suppression bundle (142 paper concepts): median body
    # 8,145 characters, maximum 40,223, and **124 of 142 (87%) exceed 4,000**. The
    # predictor tables those concepts carry sit near the end of the body, so at the
    # default the agent opens a concept and receives everything except the part it
    # came for.
    #
    # 12,000 covers the median comfortably without carrying the longest outliers whole.
    #
    # ↑ core 는 이전 도구 결과를 4,000자에서 자른다. 합성 번들(수백 자)에는 맞지만
    #   진짜 논문에는 안 맞는다. reviewer 번들 142장의 중앙값이 8,145자이고 **124장(87%)
    #   이 4,000자를 넘는다.** 게다가 정작 필요한 예측인자 표가 본문 **끝**에 있어서,
    #   기본값이면 에이전트가 문서를 열고 **찾으러 온 부분만 빼고** 다 받는다.
    act_prior_result_max_chars: int = 12000

    # Sandbox-only fields go here. Core never sees them.
    # 샌드박스 전용 항목은 여기에. core 는 이것들을 모른다.
    #
    # For example:
    #   data_dir: str = "./sandbox/outputs"
    #   my_feature_flag: bool = False
    #
    # Overriding one from the environment takes the prefix — AGENTIC_DATA_DIR.
