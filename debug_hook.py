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

    [debugpy] data is waiting for a debugger on 127.0.0.1:5679

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
"""

from __future__ import annotations

import os
import sys

#: Server name to port. Each `tools_*.py` calls in with its own name.
PORTS = {
    "okf": 5678,
    "memstara-data": 5679,
    "memstara-ml": 5680,
    "memstara-blackboard": 5681,
}

#: Short names, so `MEMSTARA_DEBUGPY=data` works too.
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
    """
    # debugpy's frozen-modules notice. Set before debugpy is imported anywhere.
    os.environ.setdefault("PYDEVD_DISABLE_FILE_VALIDATION", "1")

    import warnings

    warnings.filterwarnings("ignore", message=".*incomplete definition.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic_settings.*")

    # The MCP server narrates every call at INFO. The same names are raised in
    # `logging_setup._NOISY_LOGGERS`, but that runs in the parent only.
    import logging

    for name in ("mcp.server.lowlevel.server", "mcp.server.fastmcp", "mcp", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def wait_for_debugger(server: str) -> None:
    """Block until a debugger attaches — but only when asked for by name.

    A tool server runs as a child process, so a debugger attached to the pipeline
    never reaches it. This lets one wait, gated on an environment variable, so a
    normal run is completely unaffected.

    If *server* is listed in `MEMSTARA_DEBUGPY` it waits for a debugger. If it is not,
    **it does nothing at all.**
    """
    raw = os.environ.get("MEMSTARA_DEBUGPY", "")
    wanted = {ALIASES.get(n.strip(), n.strip()) for n in raw.split(",") if n.strip()}
    if server not in wanted:
        return

    port = PORTS.get(server)
    if port is None:
        print(f"[debugpy] {server} has no port assigned", file=sys.stderr)
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
    os.environ.setdefault("PYDEVD_DISABLE_FILE_VALIDATION", "1")

    try:
        import debugpy
    except ImportError:
        # A missing debugger must not kill the server. Say so and move on.
        print("[debugpy] debugpy is not installed — carrying on", file=sys.stderr)
        return

    try:
        debugpy.listen(("127.0.0.1", port))
    except Exception as exc:  # noqa: BLE001 - port already in use, etc.
        print(f"[debugpy] could not open port {port} for {server}: {exc}", file=sys.stderr)
        return

    # Waiting is the default; without it you cannot stop on code that already ran.
    if os.environ.get("MEMSTARA_DEBUGPY_WAIT", "1").strip() != "0":
        print(f"[debugpy] {server} is waiting for a debugger on 127.0.0.1:{port}", file=sys.stderr)
        sys.stderr.flush()
        debugpy.wait_for_client()
        print(f"[debugpy] a debugger attached to {server}", file=sys.stderr)
    else:
        print(f"[debugpy] {server} left 127.0.0.1:{port} open (not waiting)", file=sys.stderr)
    sys.stderr.flush()
