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
    python -m memstara.pipeline.hello
    python -m memstara.pipeline.hello --input "What is 17 * 23?" --trace

The **simplest example in this folder**. It makes one agent, makes one run, runs it
once, and prints the result. That is all of it.

There are only two functions.

    provision(provider, model)   makes the agent. **Same name, no second one made**
    main()                       settings → agent → make a run → run it → print

Three things that are easy to miss:

  · The provider and model are put into the agent name **on purpose**. With one
    fixed name, changing --provider would go on using the old agent, and since the
    model is frozen at creation time it would **quietly keep running on the old
    model**.
  · `configure(Settings())` has to be called once per process, and **before** any
    core module reads a setting.
  · **Making** a run (create_run) and **running** it (execute_run) are separate.
    Solo, you can chain them; in a product you make it and a worker runs it later.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from memstara.logging_setup import default_log_path, setup_logging
from memstara.config import Settings

from motoro import configure
from motoro.runner import (
    create_agent,       # make a new agent
    create_run,         # make one run — it does not execute yet
    execute_run,        # actually run a run that was made earlier
    get_agent_by_name,  # find an agent that already exists, by name
    get_run_steps,      # after it has finished, read the step record it left
)
from motoro.schemas.agent import LLMProvider, ModelConfig


async def provision(provider: str, model: str) -> Any:
    """Idempotent by name — reuse the agent if it already exists.

    Agent names are unique per owner over live rows, so without this check the second
    invocation would violate the constraint.

    Putting the provider and model in the name matters. With one fixed name, changing
    --provider would **silently reuse the existing agent** and keep running on the old
    model_config, because an agent is a durable resource whose model config was frozen
    at creation time. You would believe you had changed the experiment while in fact
    nothing had changed — and that is hard to notice.
    """
    name = f"sandbox-hello-{provider}-{model}"
    existing = await get_agent_by_name(name)
    if existing is not None:
        return existing

    # No api_key here: ModelConfig.api_key is exclude=True, so it does not survive
    # being persisted with the agent. Credentials resolve at call time from the
    # environment (or from a resolver you install). The design exists so that no
    # secret is ever laid down in the database.
    return await create_agent(
        name=name,
        goal="Answer the user's question accurately and concisely.",
        description="Smoke-test agent for the sandbox.",
        model_config=ModelConfig(provider=LLMProvider(provider), model=model, max_tokens=2048),
        # Leaving this None would use the orchestrator default, reason_act. Naming it
        # explicitly makes it easy to swap and compare later. Lean on the default and
        # you cannot tell from the code alone which pattern was used.
        pattern_config={"execution_pattern": "reason_act"},
    )


async def main() -> int:
    # Command-line options. Given nothing, it asks one multiplication question.
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="What is 17 * 23? Show your reasoning briefly.")
    ap.add_argument("--provider", default="azure_foundry", choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--trace", action="store_true", help="print the persisted SRPA steps")
    ap.add_argument("--verbose", action="store_true", help="console DEBUG: phases, hooks, tool calls")
    ap.add_argument("--log-file", default=None, help="JSONL log path (default: outputs/logs/hello.jsonl)")
    args = ap.parse_args()

    # Once per process, and necessarily before any core module reads a setting —
    # the equivalent of a web app's startup / lifespan hook. Get the order the wrong
    # way round and it runs with the settings unapplied — and raises no error.
    configure(Settings())
    setup_logging(level="DEBUG" if args.verbose else "INFO",
                  log_file=args.log_file or default_log_path("hello"))

    agent = await provision(args.provider, args.model)
    print(f"agent: {agent.id}  ({agent.name})")

    # Two calls rather than one: a product can return the run id here and hand
    # execution to a worker. Running solo, chaining them inline is fine.
    run = await create_run(agent_id=agent.id, user_input=args.input)
    print(f"run:   {run.id}  status={run.status.value}\n")

    # This is where the model is actually called. It is the only line here that
    # spends time and money.
    result = await execute_run(run_id=run.id)

    print(f"status: {result.status}")
    print(f"steps:  {len(result.steps)}")
    print(f"tokens: {result.total_prompt_tokens} prompt / {result.total_completion_tokens} completion")
    print(f"cost:   ${result.total_cost:.6f}")
    if result.error:
        print(f"error:  {result.error}", file=sys.stderr)
        return 1
    print(f"\n{result.output}")

    # With --trace, read back from the stored record which steps the run just took.
    # Not the log that scrolled past on screen but **what stayed in the database**, so
    # the same thing is still there much later. For more detail, use src/memstara/trace/run.py.
    if args.trace:
        print("\npersisted trace:")
        for step in await get_run_steps(run.id):
            extra = f"  tool_call={step.tool_call}" if step.tool_call else ""
            print(f"  {step.sequence}  {step.phase.value}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
