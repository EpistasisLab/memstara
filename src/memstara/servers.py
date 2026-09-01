"""The five MCP tool servers, named once.

Why this file exists
--------------------
The same five servers were spelled out in five places:

    02_mvp_pipeline.py:313-319    the launch table for the supervised pipeline
    03_board_pipeline.py:438-447  the launch table for the board pipeline
    preflight.py:213             the names it starts to prove they start
    debug_harness.py:85-134      the modules it pulls into one process
    bootstrap.py:139             the sources it scrapes for env-var reads

Four of the five built a command string out of an absolute path. The fifth used a
glob, which is how it came to be able to report success having read nothing (see
`SCANNED_MODULES` below).

The command strings are the worst of it, because they do not stay in the source.
`register_server` **writes them into motoro's database**, and `update_server` only
runs when the freshly built string differs from the stored one. A path that has
gone stale therefore survives in a row nobody is looking at until something
launches it and fails.

What is here and what is not
----------------------------
This file owns **how a server is launched**: its registered name, its module, and
the command. It does not own **which pipeline stage may talk to which server** —
that is `pipeline_core.BOARD_SERVERS`, a different question with a different
answer, kept under its own guard by `viewer/check_definitions.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

#: This package's own directory — `src/memstara/`. `source_of()` resolves the scanned
#: modules against it, so nothing here assumes where the checkout sits.
PACKAGE_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Server:
    """One MCP tool server.

    Attributes:
        name: The name core registers it under. This is the server's identity —
            `get_server_by_name` looks it up by this and nothing else — so it must
            match the `FastMCP(...)` name inside the module (`tools_data.py:57`).
        module: The importable module name.
        why: One line on what it is for, shown nowhere; it is here so that reading
            this table tells you what the five machines are.
    """

    name: str
    module: str
    why: str

    @property
    def source(self) -> Path:
        """The file the module is defined in.

        Used only for reading the source text — `memstara.env.allowlist_gaps()`
        scrapes it for `os.environ` reads — never for launching. Launching goes
        through `command()`.
        """
        return source_of(self.module)

    def command(self) -> str:
        """The command core stores and runs to start this server.

        `sys.executable` is the very Python running this process, so the five
        machines come up in the **same** environment as whatever started them.
        Core's allowlist requires the executable's basename to be one it knows
        (python/node/npx/...) and the command to contain no shell metacharacters;
        this satisfies both.

        The `-m` form is deliberate and is the fix for the stale-row problem in this
        file's header. A command built from an absolute path is *persisted* by
        `register_server`, so moving the file leaves a row pointing at a path that no
        longer exists, and nothing notices until something launches it. A module name
        does not encode where the file sits, so a future move cannot invalidate it.
        It also guarantees `memstara/__init__.py` runs in the child process before
        anything else, which is where `LITELLM_LOG` is set.
        """
        return f"{sys.executable} -m {self.module}"


#: The five, in the order the pipelines register them.
SERVERS: tuple[Server, ...] = (
    # okf runs core's own server through a wrapper rather than core's module directly.
    # The wrapper turns off one YAML behaviour so `list_concepts` stops failing on
    # bundles core did not write — this synthetic bundle, for one. Core's tools
    # themselves are unchanged; they are only wrapped. See mcp_servers/okf.py.
    Server("okf", "memstara.mcp_servers.okf", "knowledge lookup over the OKF bundle"),
    Server("memstara-data", "memstara.mcp_servers.data",
           "the cohort CSV: describe it, slice columns out of it"),
    Server("memstara-ml", "memstara.mcp_servers.ml", "train a model on a subset and score it"),
    Server("memstara-blackboard", "memstara.mcp_servers.blackboard",
           "the shared work board the agents read and write"),
    # PROTOTYPE semantic matcher: OKF concept name -> EcoXAI column name. Without it
    # the hypothesis agent picks column names by eye off `describe_dataset`, which is
    # the thing the matcher was built to replace — and the two pipelines then choose
    # columns by different means, so their AUCs are not comparable.
    # Needs the cache: `python scripts/build_matcher_cache.py`.
    Server("semantic-matcher", "memstara.mcp_servers.matcher",
           "OKF concept name -> cohort column name"),
)

#: `name -> Server`, for the callers that hold a name and want the rest.
BY_NAME = {s.name: s for s in SERVERS}


def launch_table() -> list[tuple[str, str]]:
    """`(name, command)` for every server, ready for `register_server`.

    Returns:
        The list the two pipelines used to write out by hand.
    """
    return [(s.name, s.command()) for s in SERVERS]


#: The sources `bootstrap.allowlist_gaps()` scrapes — the five servers, plus the
#: debug hook, which is not a server but is loaded into every one of them and reads
#: `MEMSTARA_DEBUGPY` itself. Leaving it out is exactly the omission that made the
#: debugger silently never open its port.
SCANNED_MODULES: tuple[str, ...] = (
    tuple(s.module for s in SERVERS) + ("memstara.mcp_servers.debug_hook",)
)


def source_of(module: str) -> Path:
    """The file a scanned module is defined in.

    Resolved from this file's own location rather than from `REPO_ROOT`, so it keeps
    working when the package is imported from an installed copy instead of the
    checkout. `memstara.mcp_servers.okf` -> `<this package>/mcp_servers/okf.py`.

    Args:
        module: A dotted name from `SCANNED_MODULES`, inside the `memstara` package.

    Returns:
        The path to its source.

    Raises:
        ValueError: If the name is not inside `memstara`.
    """
    prefix = f"{__package__}."
    if not module.startswith(prefix):
        raise ValueError(f"not a {__package__} module: {module!r}")
    relative = module[len(prefix):].split(".")
    return PACKAGE_ROOT.joinpath(*relative).with_suffix(".py")
