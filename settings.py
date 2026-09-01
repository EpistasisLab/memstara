"""The settings class every sandbox script shares.

The one settings object every script in this folder shares. It subclasses core's
`CoreSettings` and overrides **only those of core's defaults that do not suit this
project.** There are four:

    mcp_allowed_env_vars        which environment variables reach a tool server
                                (a child process)
    llm_call_timeout_seconds    how long to wait for one LLM call
    hook_timeout_seconds        the fence around that — core's defaults have the
                                inner and outer bounds the wrong way round
    act_prior_result_max_chars  how many characters before a tool result is cut

It also picks an environment prefix. Core deliberately sets no prefix of its own —
that is a product concern, and here the product is this sandbox.

The prefix is `AGENTIC_` because the repo's own `.env.example` already uses
`AGENTIC_DATABASE_URL` / `AGENTIC_REDIS_URL`. Reusing it avoids a second set of
names for the same things.

Provider credentials are the exception — **they carry no prefix.** `CoreSettings`
gives them bare-name validation aliases, so `ANTHROPIC_API_KEY` /
`ANTHROPIC_FOUNDRY_API_KEY` / `ANTHROPIC_FOUNDRY_RESOURCE` / `OPENAI_API_KEY` are
read exactly as written, *without* the prefix — they are conventional names other
tooling already sets.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from agentic_core import CoreSettings


class Settings(CoreSettings):
    """Settings for the sandbox experiments.

    Apart from the four fields below, every value is core's default, untouched.
    """

    model_config = SettingsConfigDict(env_prefix="AGENTIC_", env_file=".env", extra="ignore")

    # ------------------------------------------------------------------ #
    # MCP subprocess env allowlist — the tool servers die without this
    # ------------------------------------------------------------------ #
    #
    # Core does not hand an MCP subprocess the host environment wholesale. It
    # copies only what is on the allowlist (`build_subprocess_env` in
    # mcp/client.py). The point is isolation: secrets must not leak into a
    # server core does not control.
    #
    # Default allowlist: PATH · HOME · SHELL · TERM · USER · LOGNAME · LANG ·
    #                    LC_ALL · AGENTIC_OKF_BUNDLE_DIR (+ two ARES-specific)
    #
    # AGENTIC_OKF_BUNDLE_DIR is already there because core ships its own OKF
    # server. The three below belong to this sandbox's tool servers
    # (tools_data.py / tools_ml.py), so they have to be opened explicitly.
    #
    # **Leave a name off this list and it fails silently.** The variable never
    # reaches the tool server and nothing raises an error; the only symptom is a
    # one-line "could not connect", which does not point at the cause. That has
    # caught us twice — once a path, once a debugging switch. `preflight.py` now
    # reads the sources and checks them against this list.
    #
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
        # debugpy runs its check and prints its warning **the moment** the child
        # Python starts. Switching it off from inside the code is already too late
        # (tried that in quiet_child, and confirmed it). The parent has to set it
        # beforehand, and it has to be on this list to reach the child. Not a secret.
        "PYDEVD_DISABLE_FILE_VALIDATION"
    )

    # ------------------------------------------------------------------ #
    # Timeouts — core's shipped defaults are inverted
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
    # So the outer bound is widened to 300 seconds here.
    llm_call_timeout_seconds: int = 120
    hook_timeout_seconds: int = 300

    # ------------------------------------------------------------------ #
    # Tool-result truncation — the shipped default cuts real OKF bodies in half
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
    act_prior_result_max_chars: int = 12000

    # Sandbox-only fields go here. Core never sees them.
    #
    # For example:
    #   data_dir: str = "./sandbox/outputs"
    #   my_feature_flag: bool = False
    #
    # Overriding one from the environment takes the prefix — AGENTIC_DATA_DIR.
