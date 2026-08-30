#!/usr/bin/env python3
"""Smallest possible check — create one agent and execute one run.

Copying this file and editing it is the quickest way to start a new experiment.

The repo's `examples/` deliberately splits provisioning (provision.py) and execution
(run.py) into two files, because in a product the two run at different frequencies —
an agent is created once, a run is created per request. Here the point is to try it
solo, so both live in one file; agent creation stays **idempotent by name** so the
second invocation reuses what the first created.

Usage::

    cd <repo root>
    set -a && . ./.env && set +a
    python sandbox/01_hello_agent.py
    python sandbox/01_hello_agent.py --input "What is 17 * 23?" --trace


==============================================================================
 이 파일을 읽는 법
==============================================================================

 이 폴더에서 **가장 단순한 예제**다. 에이전트를 하나 만들고, 실행을 하나 만들고,
 그 실행을 한 번 돌린 뒤 결과를 찍는다. 그게 전부다.

 함수는 둘뿐이다.

   provision(provider, model)   에이전트를 만든다. **이름이 같으면 다시 만들지 않는다**
   main()                       설정 → 에이전트 → 실행 만들기 → 실행 → 결과 출력

 놓치기 쉬운 것 셋:

   · 에이전트 이름에 provider 와 model 을 **일부러 박아 넣는다**. 이름이 하나로
     고정돼 있으면 --provider 를 바꿔도 예전 에이전트를 그대로 쓰게 되고, 모델은
     만들 때 굳으므로 **옛 모델로 조용히 계속 돈다**.
   · `configure(Settings())` 는 core 의 어떤 모듈이 설정을 읽기 **전에**, 프로세스당
     한 번 불러야 한다.
   · 실행을 **만드는 것**(create_run)과 **돌리는 것**(execute_run)이 따로다. 혼자
     쓸 때는 이어 붙이면 되지만, 제품에서는 만들어만 두고 일꾼이 나중에 돌린다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from logging_setup import default_log_path, setup_logging
from settings import Settings

from agentic_core import configure
from agentic_core.runner import (
    create_agent,       # 에이전트를 새로 만든다
    create_run,         # 실행 한 건을 만든다 — 아직 돌지 않는다
    execute_run,        # 만들어 둔 실행을 실제로 돌린다
    get_agent_by_name,  # 이름으로 이미 있는 에이전트를 찾는다
    get_run_steps,      # 다 돌고 나서 남은 단계 기록을 읽는다
)
from agentic_core.schemas.agent import LLMProvider, ModelConfig


async def provision(provider: str, model: str) -> Any:
    """Idempotent by name — reuse the agent if it already exists.

    Agent names are unique per owner over live rows, so without this check the second
    invocation would violate the constraint.

    Putting the provider and model in the name matters. With one fixed name, changing
    --provider would **silently reuse the existing agent** and keep running on the old
    model_config, because an agent is a durable resource whose model config was frozen
    at creation time.

    ↑ **이름이 같으면 다시 만들지 않는다**(멱등). 에이전트 이름은 소유자 안에서
      유일해야 해서, 이 확인이 없으면 두 번째 실행에서 곧바로 막힌다.

      이름에 provider 와 model 을 넣는 것이 요점이다. 이름이 하나로 고정돼 있으면
      --provider 를 바꿔 돌려도 **기존 에이전트를 말없이 다시 쓰고**, 옛 모델 설정
      그대로 돈다. 에이전트는 오래 남는 자원이고 모델 설정은 만들 때 굳기 때문이다.
      바꿔 실험한 줄 알았는데 실은 아무것도 안 바뀐 상태 — 알아채기 어렵다.
    """
    name = f"sandbox-hello-{provider}-{model}"
    existing = await get_agent_by_name(name)
    if existing is not None:
        return existing

    # No api_key here: ModelConfig.api_key is exclude=True, so it does not survive
    # being persisted with the agent. Credentials resolve at call time from the
    # environment (or from a resolver you install).
    #
    # ↑ 여기에 api_key 를 적지 않는다. ModelConfig.api_key 는 저장에서 제외되도록
    #   돼 있어서, 적어 봐야 에이전트와 함께 남지 않는다. 열쇠는 부를 때마다
    #   환경변수(또는 따로 붙인 해석기)에서 가져온다. 비밀을 데이터베이스에
    #   눕히지 않기 위한 설계다.
    return await create_agent(
        name=name,
        goal="Answer the user's question accurately and concisely.",
        description="Smoke-test agent for the sandbox.",
        model_config=ModelConfig(provider=LLMProvider(provider), model=model, max_tokens=2048),
        # Leaving this None would use the orchestrator default, reason_act. Naming it
        # explicitly makes it easy to swap and compare later.
        #
        # ↑ 비워 두면 어차피 기본값 reason_act 가 쓰인다. 그래도 적어 두는 이유는
        #   나중에 다른 방식으로 바꿔 비교하기 쉽게 하기 위해서다. 기본값에 기대면
        #   무엇이 쓰였는지 코드만 봐서는 알 수 없다.
        pattern_config={"execution_pattern": "reason_act"},
    )


async def main() -> int:
    # 명령줄 옵션. 아무것도 안 주면 기본값으로 곱셈 문제 하나를 묻는다.
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="What is 17 * 23? Show your reasoning briefly.")
    ap.add_argument("--provider", default="azure_foundry", choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--trace", action="store_true", help="print the persisted SRPA steps")
    ap.add_argument("--verbose", action="store_true", help="console DEBUG: phases, hooks, tool calls")
    ap.add_argument("--log-file", default=None, help="JSONL log path (default: outputs/logs/hello.jsonl)")
    args = ap.parse_args()

    # Once per process, and necessarily before any core module reads a setting —
    # the equivalent of a web app's startup / lifespan hook.
    #
    # ↑ 프로세스당 한 번, 그리고 반드시 core 의 어떤 모듈이 설정을 읽기 **전에**
    #   불러야 한다. 웹 앱의 시작 훅과 같은 자리다. 순서가 뒤집히면 설정이 반영되지
    #   않은 채로 돌면서도 오류는 나지 않는다.
    configure(Settings())
    setup_logging(level="DEBUG" if args.verbose else "INFO",
                  log_file=args.log_file or default_log_path("hello"))

    agent = await provision(args.provider, args.model)
    print(f"agent: {agent.id}  ({agent.name})")

    # Two calls rather than one: a product can return the run id here and hand
    # execution to a worker. Running solo, chaining them inline is fine.
    #
    # ↑ 한 번이 아니라 두 번 부르는 이유. 제품에서는 여기서 실행 id 만 돌려주고
    #   실제 실행은 일꾼 프로세스에 넘길 수 있다. 혼자 돌릴 때는 이렇게 바로
    #   이어 붙여도 된다.
    run = await create_run(agent_id=agent.id, user_input=args.input)
    print(f"run:   {run.id}  status={run.status.value}\n")

    # 여기서 실제로 모델을 부른다. 이 줄이 시간과 돈을 쓰는 유일한 줄이다.
    result = await execute_run(run_id=run.id)

    print(f"status: {result.status}")
    print(f"steps:  {len(result.steps)}")
    print(f"tokens: {result.total_prompt_tokens} prompt / {result.total_completion_tokens} completion")
    print(f"cost:   ${result.total_cost:.6f}")
    if result.error:
        print(f"error:  {result.error}", file=sys.stderr)
        return 1
    print(f"\n{result.output}")

    # --trace 를 주면, 방금 실행이 어떤 단계를 밟았는지 저장된 기록에서 읽어 온다.
    # 화면에 흘러간 로그가 아니라 **데이터베이스에 남은 것**이라, 한참 뒤에도 같은
    # 것을 볼 수 있다. 더 자세히 보려면 trace_run.py 를 쓴다.
    if args.trace:
        print("\npersisted trace:")
        for step in await get_run_steps(run.id):
            extra = f"  tool_call={step.tool_call}" if step.tool_call else ""
            print(f"  {step.sequence}  {step.phase.value}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
