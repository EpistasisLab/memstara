"""Configure log output for the sandbox scripts.

Core deliberately does not do this. `CoreSettings` declares `log_level` and every core
module calls `structlog.get_logger()`, but nothing anywhere configures a renderer or a
handler — wiring the output is the product's job, and here the product is this sandbox.

Three destinations, because they answer different questions:

- **Console** — terse at INFO so a run is readable without piping through grep; full
  detail at DEBUG.
- **JSONL file** — always DEBUG. The console stays scannable while nothing is lost.
- **Console mirror** — the same text the console got, without the colour escapes. A
  terminal window is not a record: close it and the failure message is gone.

Two log streams are unified. Core uses structlog; litellm, httpx and the mcp package use
stdlib `logging`. Routing both through one renderer means a run reads as a single
sequence rather than two interleaved formats.
"""

from __future__ import annotations

import logging
import logging.config
import os
import re
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog

# These two were `Path(__file__).parent / "outputs" / ...` with no override of any
# kind — the single most dangerous line to leave alone during a move. `.gitignore:21`
# is `outputs/*`, which git anchors to the repository root, so an `outputs/` created
# anywhere else is not ignored and every run record from the cohort would be sitting
# untracked inside the source tree. memstara/paths.py pins them to the root.
from memstara.paths import LOG_DIR, RUNS_DIR

# Libraries that are chatty at INFO and say nothing a developer of this pipeline wants.
# Raising their floor is better than filtering the output afterwards: the noise never
# reaches either destination, and the interesting records are not caught in a grep that
# was aimed at something else.
_NOISY_LOGGERS = {
    # The MCP server logs "Processing request of type ListToolsRequest" per call.
    "mcp.server.lowlevel.server": logging.WARNING,
    "mcp.server.fastmcp": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "LiteLLM": logging.WARNING,
    "litellm": logging.WARNING,
    "asyncio": logging.WARNING,
    "urllib3": logging.WARNING,
    "sentence_transformers": logging.WARNING,
}


# Someone who set `LITELLM_LOG=DEBUG` turned litellm's chatter on **deliberately.** But
# the table above pins that logger to WARNING, so turning it on produces nothing.
#
# This matters for one reason. At DEBUG, litellm prints **the entire request sent to the
# model** as a curl command — messages and tool definitions included. And that request is
# **recorded nowhere else.** core's `run_steps.llm_call` holds only the model name, the
# tokens, the cost and the latency; the assembling happens inside core. So this log is the
# only window onto "what was the LLM actually asked". The API key is masked by litellm.
#
# Turned on, the log swells several times over. So it stays pinned by default and is
# released only when explicitly asked for.
def _litellm_levels() -> dict[str, int]:
    """Decide **at call time** whether to open the litellm loggers.

    It must not be decided when the module is read — that was in fact built that way once
    and it was caught. `bootstrap.load_env()` sets `LITELLM_LOG`, but that runs inside
    `main()`, and this module is imported **before** it. So checking at read time always
    comes out as "not on", and not one request body is collected.

    Opening the logger to DEBUG here only makes the records **come out.** What is visible
    on screen is decided separately by the `_LLMRequestOnly` filter. That is why the two
    are split — a logger level alone cannot do "collect it but keep it off the screen".
    """
    if os.environ.get("LITELLM_LOG", "").strip().upper() == "DEBUG":
        return {"LiteLLM": logging.DEBUG, "litellm": logging.DEBUG}
    return {}


# --------------------------------------------------------------------------- #
#  Intercept and collect the requests sent to the LLM
# --------------------------------------------------------------------------- #
#
# core does not store **the messages sent** to the model. What is in
# `run_steps.llm_call` is only the model name, the token counts, the latency and the
# cost; the messages are assembled inside core. So there is exactly one window onto "what
# did this agent ask the model" — the request body litellm prints at DEBUG.
#
# But simply switching `LITELLM_LOG=DEBUG` on pours out the whole of litellm's internal
# chatter. Measured: a run with a single LLM call went from 149 lines to 360. A full
# one-trial run calls the LLM 19 times, so that is roughly 4,000 lines, and the phase
# markers get buried in them. **The screen you turned it on to watch becomes unusable.**
#
# So **one kind of record only** — the request body — is kept and the rest of litellm's
# DEBUG is thrown away. That one line comes from
# litellm_core_utils/litellm_logging.py:1090, its logger is `LiteLLM`, and its message
# carries the marker below.
_LLM_REQUEST_MARK = "POST Request Sent from LiteLLM"

#: The collected request bodies. `drain_llm_requests()` takes them out and empties this.
#:
#: They do not go into `run.jsonl` — one request is tens of thousands of characters, which
#: would grow the JSONL past usefulness. The text itself is appended by
#: src/memstara/pipeline/board.py into `trace/NN_stage.txt`.
_llm_requests: list[str] = []
_llm_requests_by_run: dict[str, list[str]] = {}


class _LLMRequestGate(logging.Filter):
    """Take litellm's records **at the logger's door**, keep the request bodies, drop the rest.

    Why a filter rather than a handler, and why attached to the logger
    -----------------------------------------------------------------
    litellm attaches its own console handler **itself** (`litellm/_logging.py:81`). But
    litellm is not imported until the first LLM call, so at the moment `setup_logging`
    runs **that handler does not exist yet.** Going looking for the handler to hang a
    filter on it finds nothing to hang it on. That was actually tried, and 91 lines were
    seen leaking straight through.

    A filter on the logger is different. `Logger.handle` calls it **before any handler**,
    so however many handlers someone attaches later, it is stopped here.

    A filter keeping a value may look odd, but there is a reason for it. The request body
    is something we **want to collect but do not want on the screen.** Pass it (True) and
    litellm's own handler pours it onto the screen (one request is tens of thousands of
    characters); block it (False) and nobody gets it at all. So it is **kept here and then
    blocked.**

    With `MEMSTARA_LLM_RAW=1` nothing is blocked — that means you really do want all of it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.raw = os.environ.get("MEMSTARA_LLM_RAW", "").strip() == "1"

    def filter(self, record: logging.LogRecord) -> bool:
        if self.raw:
            return True
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - logging must not kill the run
            return False
        if _LLM_REQUEST_MARK in msg:
            # Strip the colour codes, so it can be written to a file as it is.
            from memstara.pipeline.diagnostics import call_context

            context = call_context.get()
            destination = _llm_requests_by_run.setdefault(context[1], []) if context else _llm_requests
            destination.append(re.sub(r"\x1b\[[0-9;]*m", "", msg))
        return False


def drain_llm_requests(run_id: str | None = None) -> list[str]:
    """Take out the collected requests and empty the list.

    Board calls use their run ID, captured from the task-local diagnostic context.
    Concurrent calls therefore cannot consume each other's requests. Calls without
    an ID drain only legacy unscoped records, never records owned by another call.
    """
    if run_id is not None:
        return _llm_requests_by_run.pop(run_id, [])
    out = list(_llm_requests)
    _llm_requests.clear()
    return out


class _LLMRequestOnly(logging.Filter):
    """Of the records litellm emits, pass **only the request bodies.**

    Loggers other than litellm's are left alone and passed straight through. With
    `MEMSTARA_LLM_RAW=1` nothing is filtered — that means you really do want all of it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.raw = os.environ.get("MEMSTARA_LLM_RAW", "").strip() == "1"

    def filter(self, record: logging.LogRecord) -> bool:
        if self.raw or not record.name.startswith(("LiteLLM", "litellm")):
            return True
        try:
            return _LLM_REQUEST_MARK in record.getMessage()
        except Exception:  # noqa: BLE001
            return False


# Loggers hidden on the console only. **They stay in the file as they are.**
#
# Why a filter rather than raising the logger level — raising the level makes them
# disappear from **both** the console and the file. These records are worth having when
# retracing later, so they have to stay in `run.jsonl`. Taking them off the console alone
# leaves no option but a filter on the console handler.
#
# What is hidden — the 12 lines emitted as the four servers connect and disconnect. That
# information is already said in one line by step (2) on screen ("paper store · data
# machine · learning machine · board window").
#
# Run with `--verbose` and this filter is not attached — that means you want all of it.
# `motoro.mcp.adapters` is in here too. The `mcp.tool.executed` it emits is one line
# per tool call, but 03 already lays that call out **with its arguments and its result**
# (show_what_agent_did). It amounts to printing the same fact twice, so it comes off the
# console only.
_CONSOLE_HIDE = (
    "motoro.mcp.client",
    "motoro.mcp.registry",
    "motoro.mcp.adapters",
)


class _HideOnConsole(logging.Filter):
    """A filter attached to the console handler only. Takes the loggers listed above off the screen."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(_CONSOLE_HIDE)


def setup_logging(*, level: str = "INFO", log_file: Path | str | None = None) -> Path | None:
    """Configure structlog and stdlib logging. Returns the log file path, if any.

    Args:
        level: console level. "DEBUG" shows phase transitions, hook activity and every
            tool call; "INFO" shows only what a run's progress requires.
        log_file: JSONL destination. None disables file output.

    Only **the console level** is taken as an argument — the file is always DEBUG. If
    quietening the console also quietened the file, the very thing you would go back and
    retrace with would be gone.
    """
    console_level = getattr(logging, level.upper(), logging.INFO)

    # pydantic_settings emits IncompleteFieldDefinitionWarning for FastMCP's `lifespan`
    # field on every import of the mcp package. It is not actionable from here — it
    # happens inside someone else's library, so there is nothing to do but silence it.
    warnings.filterwarnings("ignore", message=".*incomplete definition.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic_settings.*")

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        # The date is part of the stamp. Without it a file that accumulates across
        # days cannot be read in order — and these files do accumulate.
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": console_level,
            "formatter": "console",
            # Two filters. `llm_request_only` cuts litellm's chatter away and keeps only
            # the request bodies — without it the screen becomes 4,000 lines.
            #
            # `hide_on_console` comes off only with --verbose. That means you want all of it.
            "filters": (
                ["llm_request_only"] if console_level <= logging.DEBUG else ["hide_on_console", "llm_request_only"]
            ),
        }
    }
    formatters: dict[str, Any] = {
        "console": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True, pad_event=28),
            ],
            "foreign_pre_chain": shared,
        }
    }

    path: Path | None = None
    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        formatters["jsonl"] = {
            "()": structlog.stdlib.ProcessorFormatter,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
            "foreign_pre_chain": shared,
        }
        handlers["file"] = {
            "class": "logging.FileHandler",
            "level": logging.DEBUG,
            "formatter": "jsonl",
            "filename": str(path),
            "encoding": "utf-8",
        }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "hide_on_console": {"()": _HideOnConsole},
                "llm_request_only": {"()": _LLMRequestOnly},
            },
            "formatters": formatters,
            "handlers": handlers,
            # The root logger is set to DEBUG so the file can capture everything; each
            # handler applies its own floor.
            "root": {"level": logging.DEBUG, "handlers": list(handlers)},
            # The litellm levels decided at call time override the table's defaults.
            "loggers": {name: {"level": lvl} for name, lvl in {**_NOISY_LOGGERS, **_litellm_levels()}.items()},
        }
    )

    # Post the gate at the door of litellm's two loggers.
    #
    # Why on those loggers rather than on the root — on the root every record in the
    # program would pass through it and call getMessage() each time. Only one logger is
    # needed. And why on the **logger** rather than on a handler is explained in
    # `_LLMRequestGate` above — litellm is imported later, so right now it has no handler.
    _gate = _LLMRequestGate()
    for _name in ("LiteLLM", "litellm"):
        _lg = logging.getLogger(_name)
        # Do not attach it twice — setup_logging can be called twice.
        if not any(isinstance(f, _LLMRequestGate) for f in _lg.filters):
            _lg.addFilter(_gate)

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return path


def default_log_path(prefix: str) -> Path:
    """A per-invocation log path under outputs/logs/.

    The caller supplies the timestamp portion; this module does not read the clock, so
    that a script wanting reproducible filenames can pass its own.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"{prefix}.jsonl"


def new_run_dir(prefix: str, stamp: str) -> Path:
    """A directory for everything one invocation produces: outputs/runs/<stamp>_<prefix>/.

    One folder per run, rather than one file appended to forever. A `FileHandler`
    defaults to append mode, so a fixed filename silently concatenates invocations —
    outputs/logs/mvp_1trials.jsonl holds 391 records spanning three hours of separate
    runs with nothing marking where one ends. A directory makes the boundary physical.

    The caller supplies *stamp* for the same reason `default_log_path` takes its name
    from the caller: this module does not read the clock.
    """
    path = RUNS_DIR / f"{stamp}_{prefix}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Strips the SGR colour escapes that ConsoleRenderer emits. A file full of "\x1b[2m" is
# harder to read than no file at all.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _Tee:
    """Write to the original stream and to a file at the same time."""

    def __init__(self, stream: Any, sink: Any) -> None:
        self._stream = stream
        self._sink = sink

    def write(self, text: str) -> int:
        self._sink.write(_ANSI_RE.sub("", text))
        return self._stream.write(text)

    def flush(self) -> None:
        self._sink.flush()
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        # isatty, encoding, fileno and friends — let the real stream answer.
        return getattr(self._stream, name)


@contextmanager
def tee_console(path: Path | str, *, append: bool = False) -> Iterator[Path]:
    """Mirror stdout and stderr into *path* for the duration of the block.

    A logging handler would not do: the pipeline reports its results with `print`, so
    the aggregate summary — the part someone actually goes back to read — never reaches
    the logging machinery at all. Teeing the streams catches both, interleaved in the
    order they were written.

    Install this *before* `setup_logging`: dictConfig's StreamHandler resolves
    `sys.stderr` when it is constructed, so a tee installed afterwards would not be
    seen by it.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    saved_out, saved_err = sys.stdout, sys.stderr
    with target.open("a" if append else "w", encoding="utf-8") as sink:
        sys.stdout = _Tee(saved_out, sink)
        sys.stderr = _Tee(saved_err, sink)
        try:
            yield target
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err
