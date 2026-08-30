#!/usr/bin/env python3
"""The hook that lets a debugger attach to a tool server (a child process).

Why it is needed
----------------
`03_board_pipeline.py:121 setup_tools()` starts four tool servers, **each in its own
process**. A debugger attached to the parent is a stranger to those children, so
breakpoints in `tools_*.py` never fire.

To attach, the child has to say "wait for a debugger" itself — and code that says so
unconditionally would **hang every normal run forever**. So it only switches on when
an environment variable asks for it.

Usage
-----
List the servers you want, comma-separated. With nothing set, nothing happens.

    MEMSTARA_DEBUGPY=data python 03_board_pipeline.py --trials 1 ...
    MEMSTARA_DEBUGPY=okf,ml python 03_board_pipeline.py ...

That server then stops on startup to wait for a debugger and prints to stderr::

    [debugpy] data 가 127.0.0.1:5679 에서 디버거를 기다린다

In VS Code, pick the "attach to child tool server" configuration matching that port
and press F5; from then on breakpoints in `tools_data.py` fire.

Ports
-----
One per server, so two can be enabled at once without colliding.

    okf                  5678
    memstara-data        5679
    memstara-ml          5680
    memstara-blackboard  5681

How long you have
-----------------
The parent waits `tool_timeout_seconds` — **300 seconds** in this project. Attach
within that window; miss it and the parent gives up with "MCP stdio connection
timed out".

Opening the port without waiting
--------------------------------
Add `MEMSTARA_DEBUGPY_WAIT=0` to open the port and carry straight on. Server startup
is not blocked, but you cannot stop on code that ran before you attached.

Nothing is ever written to stdout
---------------------------------
Tool servers **speak the MCP protocol over standard output.** A single stray
character there and the parent can no longer parse the messages. So every notice
goes to stderr.

도구 서버(자식 프로세스)에 디버거를 붙일 수 있게 하는 갈고리.

왜 필요한가
-----------
`03_board_pipeline.py:121 setup_tools()` 가 도구 서버 넷을 **각각 별도 프로세스**로
띄운다. 부모에 디버거를 붙여도 자식은 남남이라 `tools_*.py` 의 브레이크포인트는
걸리지 않는다.

붙으려면 자식이 스스로 "디버거를 기다린다" 고 말해야 하는데, 그 코드를 파일에 상주
시키면 **평소 실행이 영영 멈춘다.** 그래서 환경변수가 있을 때만 켜지게 한다.

쓰는 법
-------
켜고 싶은 서버 이름을 쉼표로 넣는다. 없으면 아무 일도 안 일어난다.

    MEMSTARA_DEBUGPY=data python 03_board_pipeline.py --trials 1 ...
    MEMSTARA_DEBUGPY=okf,ml python 03_board_pipeline.py ...

그러면 그 서버가 뜰 때 멈춰 서서 디버거를 기다리고, stderr 에 이렇게 찍는다::

    [debugpy] data 가 127.0.0.1:5679 에서 디버거를 기다린다

VS Code 에서 「자식 도구 서버에 attach」 구성 중 그 포트에 맞는 것을 골라 F5 를
누르면 붙고, 그때부터 `tools_data.py` 의 브레이크포인트가 걸린다.

포트
----
서버마다 다르다. 그래야 둘을 동시에 켜도 안 부딪힌다.

    okf                  5678
    memstara-data        5679
    memstara-ml          5680
    memstara-blackboard  5681

시간 여유
---------
부모는 `tool_timeout_seconds` 만큼 기다린다 — 이 프로젝트는 **300초**다. 그 안에
붙으면 된다. 못 붙으면 부모가 "MCP stdio connection timed out" 으로 포기한다.

기다리지 않고 열어만 두려면
---------------------------
`MEMSTARA_DEBUGPY_WAIT=0` 을 같이 주면 포트만 열고 그냥 진행한다. 서버 시작을 막지
않는 대신, 붙기 전에 지나간 코드에는 못 멈춘다.

stdout 에 아무것도 쓰지 않는다
------------------------------
도구 서버는 **표준출력으로 MCP 프로토콜을 주고받는다.** 거기에 한 글자라도 끼면
부모가 메시지를 파싱하지 못한다. 그래서 안내는 전부 stderr 로 나간다.
"""

from __future__ import annotations

import os
import sys

#: Server name to port. Each `tools_*.py` calls in with its own name.
#:
#: 서버 이름 → 포트. tools_*.py 가 자기 이름으로 부른다.
PORTS = {
    "okf": 5678,
    "memstara-data": 5679,
    "memstara-ml": 5680,
    "memstara-blackboard": 5681,
}

#: Short names, so `MEMSTARA_DEBUGPY=data` works too.
#:
#: 이름을 짧게 쓸 수 있게. `MEMSTARA_DEBUGPY=data` 로도 되게 한다.
ALIASES = {
    "data": "memstara-data",
    "ml": "memstara-ml",
    "blackboard": "memstara-blackboard",
    "board": "memstara-blackboard",
}


def quiet_child() -> None:
    """Silence the three things a tool server prints on startup that nobody reads.

    A tool server is a child process. Its stderr lands in the same terminal as the
    parent's, but the parent's logging configuration does not reach it — so these
    lines survive every filter set in `logging_setup.py` and repeat **once per
    server**, four times over.

    What is silenced, and why none of it is information:

        Debugger warning: frozen modules ...
            debugpy says breakpoints may be missed inside frozen standard-library
            modules. Everything worth stopping in is code in this folder.

        IncompleteFieldDefinitionWarning: Field 'lifespan' ...
            pydantic_settings, about FastMCP's own model. Not actionable from here.

        INFO Processing request of type ListToolsRequest
            the MCP server narrating every single call.

    Nothing is written to stdout — that is the MCP protocol channel.

    ↑ 도구 서버가 켜질 때 찍는, **아무도 안 읽는 세 가지**를 끈다.

      도구 서버는 자식 프로세스다. 그 stderr 가 부모와 같은 터미널로 나오는데,
      부모의 로그 설정은 자식에 닿지 않는다. 그래서 `logging_setup.py` 에서 걸러 둔
      것들이 여기서는 그대로 나오고, **서버마다 한 번씩 네 번** 반복된다.

      끄는 것과, 그것이 정보가 아닌 이유:

        · debugpy 의 "frozen modules" 경고 — 표준 라이브러리 **안쪽** 얘기다.
          우리가 멈추려는 코드는 전부 이 폴더에 있다
        · pydantic 의 'lifespan' 경고 — FastMCP 의 모델에 대한 것이라 **우리가
          고칠 수 있는 게 아니다**
        · "Processing request of type ..." — 호출마다 한 줄씩 나오는 중계 방송

      stdout 에는 아무것도 안 쓴다 — 그쪽은 MCP 프로토콜이 지나가는 길이다.
    """
    # debugpy's frozen-modules notice. Set before debugpy is imported anywhere.
    # debugpy 의 frozen-modules 안내. debugpy 가 import 되기 전에 정해 둬야 한다.
    os.environ.setdefault("PYDEVD_DISABLE_FILE_VALIDATION", "1")

    import warnings

    warnings.filterwarnings("ignore", message=".*incomplete definition.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic_settings.*")

    # The MCP server narrates every call at INFO. The same names are raised in
    # `logging_setup._NOISY_LOGGERS`, but that runs in the parent only.
    #
    # MCP 서버는 호출마다 INFO 로 중계한다. 같은 이름을 `logging_setup._NOISY_LOGGERS`
    # 에서도 올려 두었지만 그건 **부모에서만** 도는 설정이다.
    import logging

    for name in ("mcp.server.lowlevel.server", "mcp.server.fastmcp", "mcp", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def wait_for_debugger(server: str) -> None:
    """Block until a debugger attaches — but only when asked for by name.

    A tool server runs as a child process, so a debugger attached to the pipeline
    never reaches it. This lets one wait, gated on an environment variable, so a
    normal run is completely unaffected.

    *server* 가 `MEMSTARA_DEBUGPY` 에 들어 있으면 디버거를 기다린다.

    없으면 **아무 일도 하지 않는다.** 평소 실행에는 영향이 없다.
    """
    raw = os.environ.get("MEMSTARA_DEBUGPY", "")
    wanted = {ALIASES.get(n.strip(), n.strip()) for n in raw.split(",") if n.strip()}
    if server not in wanted:
        return

    port = PORTS.get(server)
    if port is None:
        print(f"[debugpy] {server} 는 포트가 정해져 있지 않다", file=sys.stderr)
        return

    # debugpy prints this warning on startup:
    #
    #     Debugger warning: It seems that frozen modules are being used, which may
    #     make the debugger miss breakpoints.
    #
    # It means breakpoints can be missed inside frozen standard-library modules.
    # Everything we want to stop in is code in this folder, so there is no real
    # effect. The warning is silenced only because it fills stderr and hides the
    # lines worth reading.
    #
    # To be certain of stopping inside the standard library, Python would have to be
    # started with `-Xfrozen_modules=off` — but the parent launches tool servers as
    # `sys.executable tools_x.py`, leaving nowhere to slip that flag in. Run the file
    # that way directly if it is ever needed.
    #
    # debugpy 가 뜰 때 이런 경고를 낸다:
    #
    #     Debugger warning: It seems that frozen modules are being used, which may
    #     make the debugger miss breakpoints.
    #
    # 얼어붙은(frozen) 표준 라이브러리 모듈 안에서는 브레이크포인트를 놓칠 수 있다는
    # 뜻이다. 우리가 멈추려는 곳은 전부 이 폴더의 코드이므로 실제 영향은 없다.
    # 경고만 끈다 — stderr 를 채워 정작 볼 것을 가리기 때문이다.
    #
    # 표준 라이브러리 안까지 확실히 멈추고 싶으면 파이썬을 `-Xfrozen_modules=off` 로
    # 띄워야 하는데, 도구 서버는 부모가 `sys.executable tools_x.py` 로 띄우므로
    # 그 옵션을 끼울 자리가 없다. 필요하면 그 파일을 직접 그렇게 실행하면 된다.
    os.environ.setdefault("PYDEVD_DISABLE_FILE_VALIDATION", "1")

    try:
        import debugpy
    except ImportError:
        # A missing debugger must not kill the server. Say so and move on.
        # 디버거가 없다고 서버를 죽이지는 않는다. 알리고 그냥 간다.
        print("[debugpy] debugpy 가 없다 — 그냥 진행한다", file=sys.stderr)
        return

    try:
        debugpy.listen(("127.0.0.1", port))
    except Exception as exc:  # noqa: BLE001 - port already in use, etc. / 포트가 이미 쓰이는 등
        print(f"[debugpy] {server} 포트 {port} 를 못 열었다: {exc}", file=sys.stderr)
        return

    # Waiting is the default; without it you cannot stop on code that already ran.
    # 기본은 기다린다. 안 기다리면 붙기 전에 지나간 코드에는 못 멈춘다.
    if os.environ.get("MEMSTARA_DEBUGPY_WAIT", "1").strip() != "0":
        print(f"[debugpy] {server} 가 127.0.0.1:{port} 에서 디버거를 기다린다", file=sys.stderr)
        sys.stderr.flush()
        debugpy.wait_for_client()
        print(f"[debugpy] {server} 에 디버거가 붙었다", file=sys.stderr)
    else:
        print(f"[debugpy] {server} 가 127.0.0.1:{port} 를 열어 뒀다 (기다리지 않음)", file=sys.stderr)
    sys.stderr.flush()
