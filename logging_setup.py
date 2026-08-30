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

LOG_DIR = Path(__file__).parent / "outputs" / "logs"
RUNS_DIR = Path(__file__).parent / "outputs" / "runs"

# Libraries that are chatty at INFO and say nothing a developer of this pipeline wants.
# Raising their floor is better than filtering the output afterwards: the noise never
# reaches either destination, and the interesting records are not caught in a grep that
# was aimed at something else.
#
# ↑ INFO 에서 수다스러운데 이 파이프라인을 만드는 사람에게는 쓸모없는 라이브러리들.
#   나중에 걸러 내는 것보다 **바닥을 올려 두는 편**이 낫다 — 소음이 애초에 어느
#   목적지에도 도착하지 않고, 나중에 다른 것을 찾는 grep 에 걸리지도 않는다.
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

# `LITELLM_LOG=DEBUG` 를 준 사람은 litellm 의 수다를 **일부러** 켠 것이다. 그런데 위
# 표가 그 로거를 WARNING 으로 눌러 버려서, 켜도 아무것도 안 나온다.
#
# 이게 중요한 이유는 하나다. litellm 은 DEBUG 에서 **모델에 보낸 요청 전체**를 curl
# 명령으로 찍는다 — messages 와 tools 정의까지. 그리고 그 요청은 **다른 어디에도
# 기록되지 않는다.** core 의 `run_steps.llm_call` 에는 모델 이름·토큰·비용·지연만
# 있고, 조립은 core 안에서 일어난다. 그러니 이 로그가 "LLM 에 무엇을 물었나" 를 볼
# 수 있는 유일한 창이다. API 키는 litellm 이 마스킹한다.
#
# 켜면 로그가 몇 배로 불어난다. 그래서 기본은 계속 눌러 두고, 명시적으로 요청한
# 경우에만 푼다.
def _litellm_levels() -> dict[str, int]:
    """litellm 로거를 열지 말지, **부를 때** 정한다.

    모듈을 읽는 시점에 정하면 안 된다 — 실제로 그렇게 만들었다가 걸렸다.
    `bootstrap.load_env()` 가 `LITELLM_LOG` 을 설정하는데 그것은 `main()` 안에서
    돌고, 이 모듈은 그보다 **먼저** import 된다. 그래서 읽을 때 검사하면 언제나
    "안 켜짐" 으로 판정되고, 요청 본문이 한 건도 안 모인다.

    여기서 로거를 DEBUG 로 여는 것은 **기록이 나오게** 하는 것뿐이다. 화면에 무엇이
    보일지는 `_LLMRequestOnly` 필터가 따로 정한다. 둘을 나눈 이유가 그것이다 —
    로거 수준 하나로는 "모으되 화면에는 안 보이게" 를 할 수 없다.
    """
    if os.environ.get("LITELLM_LOG", "").strip().upper() == "DEBUG":
        return {"LiteLLM": logging.DEBUG, "litellm": logging.DEBUG}
    return {}


# --------------------------------------------------------------------------- #
#  LLM 에 보낸 요청을 가로채 모은다
# --------------------------------------------------------------------------- #
#
# core 는 모델에 **보낸 메시지**를 저장하지 않는다. `run_steps.llm_call` 에 있는 것은
# 모델 이름·토큰 수·지연·비용뿐이고, 메시지 조립은 core 안에서 일어난다. 그러니
# "이 에이전트가 모델에게 무엇을 물었나" 를 볼 수 있는 창이 하나뿐이다 — litellm 이
# DEBUG 에서 찍는 요청 본문이다.
#
# 그런데 `LITELLM_LOG=DEBUG` 를 그냥 켜면 litellm 의 내부 수다가 통째로 쏟아진다.
# 실측: LLM 을 한 번 부르는 실행이 149줄 → 360줄. 전체 1시행은 LLM 을 19번 부르므로
# 대략 4,000줄이 되고, 단계 표시가 그 안에 묻힌다. **보려고 켠 화면이 못 쓰게 된다.**
#
# 그래서 요청 본문 **한 종류만** 남기고 나머지 litellm DEBUG 는 버린다. 그 한 줄은
# litellm_core_utils/litellm_logging.py:1090 에서 나오고, 로거는 `LiteLLM`,
# 메시지에 아래 표식이 들어간다.
_LLM_REQUEST_MARK = "POST Request Sent from LiteLLM"

#: 모아 둔 요청 본문. `drain_llm_requests()` 로 꺼내 비운다.
#:
#: `run.jsonl` 에는 안 넣는다 — 요청 하나가 수만 자라 JSONL 이 못 쓰게 커진다.
#: 원문은 03_board_pipeline.py 가 `trace/NN_단계.txt` 에 붙인다.
_llm_requests: list[str] = []


class _LLMRequestGate(logging.Filter):
    """litellm 의 기록을 **로거 문 앞에서** 받아, 요청 본문만 챙기고 나머지는 버린다.

    왜 손잡이(handler)가 아니라 문지기(filter)이고, 왜 로거에 다는가
    -----------------------------------------------------------------
    litellm 은 자기 화면 손잡이를 **직접** 단다(`litellm/_logging.py:81`). 그런데
    litellm 은 첫 LLM 호출 때에야 import 되므로, `setup_logging` 이 도는 시점에는
    **그 손잡이가 아직 없다.** 손잡이를 찾아 필터를 걸어 봐야 걸 대상이 없다.
    실제로 그렇게 해 보고 91줄이 그대로 새는 것을 확인했다.

    로거에 건 필터는 다르다. `Logger.handle` 이 **모든 손잡이보다 먼저** 부르므로,
    나중에 누가 손잡이를 몇 개를 달든 여기서 막힌다.

    문지기가 값을 챙기는 것이 이상해 보일 수 있는데, 그렇게 하는 이유가 있다.
    요청 본문은 **모으고 싶지만 화면에는 안 띄우고 싶다.** 통과시키면(True) litellm
    자기 손잡이가 그대로 화면에 쏟고(요청 하나가 수만 자다), 막으면(False) 아무도
    못 본다. 그래서 **여기서 챙긴 뒤 막는다.**

    `MEMSTARA_LLM_RAW=1` 이면 아무것도 안 막는다 — 진짜로 전부 보고 싶다는 뜻이다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.raw = os.environ.get("MEMSTARA_LLM_RAW", "").strip() == "1"

    def filter(self, record: logging.LogRecord) -> bool:
        if self.raw:
            return True
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - 로깅이 실행을 죽이면 안 된다
            return False
        if _LLM_REQUEST_MARK in msg:
            # 색 코드를 벗긴다. 파일에 그대로 쓸 수 있게.
            _llm_requests.append(re.sub(r"\x1b\[[0-9;]*m", "", msg))
        return False


def drain_llm_requests() -> list[str]:
    """모인 요청을 꺼내고 비운다.

    에이전트 호출이 끝날 때마다 부른다. 꺼내면서 비우므로 **다음 사람의 요청과
    안 섞인다** — 그 에이전트가 부른 만큼만 그 추적 파일에 들어간다.
    """
    out = list(_llm_requests)
    _llm_requests.clear()
    return out


class _LLMRequestOnly(logging.Filter):
    """litellm 이 낸 기록 중 **요청 본문만** 통과시킨다.

    litellm 이 아닌 로거는 건드리지 않고 그대로 보낸다. `MEMSTARA_LLM_RAW=1` 이면
    아무것도 안 거른다 — 진짜로 전부 보고 싶다는 뜻이므로.
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


# 화면에서만 감출 로거들. **파일에는 그대로 남는다.**
#
# 왜 로거 수준을 올리지 않고 필터를 쓰나 — 수준을 올리면 화면과 파일 **양쪽에서**
# 사라진다. 이 기록들은 나중에 되짚을 때 값어치가 있으므로 `run.jsonl` 에는 남겨야
# 한다. 화면에서만 빼려면 화면 손잡이에 필터를 다는 수밖에 없다.
#
# 무엇을 감추나 — 서버 넷이 붙고 끊길 때 나오는 12줄이다. 그 정보는 이미 화면의
# ② 단계가 한 줄로 말해 준다("논문 창고 · 데이터 기계 · 학습 기계 · 게시판 창구").
#
# `--verbose` 로 돌리면 이 필터가 안 붙는다 — 그때는 전부 보고 싶다는 뜻이므로.
# `agentic_core.mcp.adapters` 도 넣는다. 그것이 내는 `mcp.tool.executed` 는 도구를
# 부를 때마다 한 줄인데, 03 이 이미 그 호출을 **인자와 결과까지** 풀어서 보여 준다
# (show_what_agent_did). 같은 사실을 두 번 찍는 셈이라 화면에서만 뺀다.
_CONSOLE_HIDE = (
    "agentic_core.mcp.client",
    "agentic_core.mcp.registry",
    "agentic_core.mcp.adapters",
)


class _HideOnConsole(logging.Filter):
    """화면 손잡이에만 붙는 필터. 위 목록의 로거가 낸 기록을 화면에서 뺀다."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(_CONSOLE_HIDE)


def setup_logging(*, level: str = "INFO", log_file: Path | str | None = None) -> Path | None:
    """Configure structlog and stdlib logging. Returns the log file path, if any.

    Args:
        level: console level. "DEBUG" shows phase transitions, hook activity and every
            tool call; "INFO" shows only what a run's progress requires.
        log_file: JSONL destination. None disables file output.

    ↑ 요약: 화면과 파일을 함께 세운다. **화면 수준만** 인자로 받는다 — 파일은
      언제나 DEBUG 다. 화면을 조용히 하려고 파일까지 조용해지면, 정작 나중에
      되짚어 볼 것이 사라지기 때문이다.
    """
    console_level = getattr(logging, level.upper(), logging.INFO)

    # pydantic_settings emits IncompleteFieldDefinitionWarning for FastMCP's `lifespan`
    # field on every import of the mcp package. It is not actionable from here.
    #
    # ↑ mcp 패키지를 import 할 때마다 뜨는 경고인데 **우리가 고칠 수 있는 것이 아니다.**
    #   남의 라이브러리 안의 일이라 끄는 것 말고 할 수 있는 게 없다.
    warnings.filterwarnings("ignore", message=".*incomplete definition.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic_settings.*")

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        # The date is part of the stamp. Without it a file that accumulates across
        # days cannot be read in order — and these files do accumulate.
        #
        # ↑ 시각에 **날짜까지** 넣는다. 시:분:초만 있으면 며칠에 걸쳐 쌓인 파일을
        #   순서대로 읽을 수 없다 — 그리고 이 파일들은 실제로 쌓인다.
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": console_level,
            "formatter": "console",
            # 필터 둘. `llm_request_only` 는 litellm 의 수다를 잘라 내고 요청 본문만
            # 남긴다 — 이걸 안 붙이면 화면이 4,000줄이 된다.
            #
            # `hide_on_console` 은 --verbose 일 때만 뗀다. 그때는 전부 보고 싶다는 뜻이다.
            "filters": (["llm_request_only"] if console_level <= logging.DEBUG
                        else ["hide_on_console", "llm_request_only"]),
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
            #
            # ↑ 뿌리는 DEBUG 로 열어 둔다. 그래야 **파일이 전부 담을 수 있다.**
            #   화면은 자기 바닥(console_level)으로 알아서 걸러 낸다.
            "root": {"level": logging.DEBUG, "handlers": list(handlers)},
            # 부를 때 정해진 litellm 수준이 표의 기본값을 덮는다.
            "loggers": {name: {"level": lvl}
                        for name, lvl in {**_NOISY_LOGGERS, **_litellm_levels()}.items()},
        }
    )

    # 요청 본문을 모으는 손잡이를 `LiteLLM` 로거에 직접 단다.
    #
    # 뿌리가 아니라 그 로거에 다는 이유 — 뿌리에 달면 모든 기록이 이 손잡이를 거치고,
    # 매번 getMessage() 를 부르게 된다. 필요한 것은 한 로거뿐이다.
    # litellm 의 두 로거 문 앞에 문지기를 세운다. 손잡이가 아니라 **로거**에 다는
    # 이유는 위 `_LLMRequestGate` 설명에 있다 — litellm 은 나중에 import 되므로
    # 지금은 손잡이가 없다.
    _gate = _LLMRequestGate()
    for _name in ("LiteLLM", "litellm"):
        _lg = logging.getLogger(_name)
        # 두 번 달지 않는다 — setup_logging 이 두 번 불릴 수 있다.
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

    ↑ **이 모듈은 시계를 안 본다.** 시각은 부르는 쪽이 준다 — 같은 이름을 다시
      만들고 싶은 스크립트가 자기 값을 넣을 수 있어야 하기 때문이다.
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

    ↑ 실행 하나에 폴더 하나. 파일 하나에 영원히 덧붙이지 않는다 — `FileHandler` 는
      기본이 **덧붙이기** 라, 이름을 고정하면 여러 실행이 조용히 이어 붙는다.
      실제로 `mvp_1trials.jsonl` 하나에 세 시간에 걸친 별개 실행 391건이 경계 표시도
      없이 들어 있었다. 폴더로 나누면 그 경계가 **물리적으로** 생긴다.
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
def tee_console(path: Path | str) -> Iterator[Path]:
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
    with target.open("w", encoding="utf-8") as sink:
        sys.stdout = _Tee(saved_out, sink)  # type: ignore[assignment]
        sys.stderr = _Tee(saved_err, sink)  # type: ignore[assignment]
        try:
            yield target
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err
