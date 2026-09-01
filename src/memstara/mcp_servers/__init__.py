"""The five MCP tool servers, plus the debug hook they all load.

Each module here is a **separate process**. Core starts it over stdio, so nothing in
this package is imported by the pipeline that uses it — the connection is a command
string, and that string is `memstara.servers.Server.command()`. `servers.py` is where
they are named; this is where they live.

    okf.py         knowledge lookup over the OKF bundle
    data.py        the cohort CSV: describe it, slice columns out of it
    ml.py          train a model on a subset and score it
    blackboard.py  the shared work board — the server in front of memstara/blackboard.py
    matcher.py     OKF concept name -> cohort column name
    src/memstara/mcp_servers/debug_hook.py  not a server; the thing each one calls to wait for a debugger

`blackboard.py` appears twice in this package tree on purpose. `memstara/blackboard.py`
is the board itself — the table, the DSN, the run lock — and can be tested without
starting anything. This one is the MCP surface in front of it.
"""
