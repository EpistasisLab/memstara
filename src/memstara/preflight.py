#!/usr/bin/env python3
"""Check everything before a run, and on failure say **what to fix**.

    python preflight.py                 # with the default provider
    python preflight.py --provider openai
    python preflight.py --quick         # do not start the tool servers (seconds)

Why this file exists
--------------------
In this project an environment problem shows up **much later, wearing the wrong
face**.

    no LLM credentials      -> "api_base is required", after a seeding round is spent
    missing from allowlist  -> no error at all; the tool just uses its default
    database not up         -> an opaque tool error from inside the agent
    tool server won't start -> one line saying "tools available: []"

Every one of them surfaces **far away from its cause**, which is what makes the
cause expensive to find.

This file pulls those checks **forward**. It never calls an LLM, so it costs
nothing, and it writes nothing to the board.

What it looks at
----------------
    1. were both `.env` files read
    2. is every required variable present (provider credentials included)
    3. do the files and folders they point at actually exist
    4. are both databases reachable
    5. **does the allowlist cover everything the tools read** — the silent-failure spot
    6. is the built matcher catalog still current for this cohort
    7. do all five tool servers really start and offer their tools

Step 7 spawns child processes and takes roughly 20 seconds; `--quick` skips it.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

# **First of all.** The imports below read the environment, so it must be set up first.
from memstara.env import PROVIDER_KEYS, allowlist_gaps, load_env, missing_vars
from memstara.paths import ENV_FILES, REPO_ROOT
from memstara.servers import BY_NAME, SERVERS

_LOADED = load_env()

OK, BAD, WARN = "  \033[32m✓\033[0m", "  \033[31m✗\033[0m", "  \033[33m!\033[0m"
_failures: list[str] = []


def check(label: str, passed: bool, detail: str = "", fix: str = "") -> bool:
    """Print one check line, remember the failure, and return whether it passed."""
    print(f"{OK if passed else BAD} {label}" + (f"  —  {detail}" if detail else ""))
    if not passed:
        _failures.append(label)
        if fix:
            print(f"      how to fix: {fix}")
    return passed


def check_env_files() -> None:
    """[1] Were both `.env` files found where they are expected."""
    print("\n[1] .env")
    for path in ENV_FILES:
        check(f".env — {path.parent.name}/", path.is_file(), str(path.resolve()),
              f"create {path} (see .env.example)")


def check_vars(provider: str) -> None:
    """[2] Are all required variables set, including this provider's credentials."""
    print("\n[2] environment variables")
    problems = missing_vars(provider)
    check("every required variable is present", not problems,
          "none missing" if not problems else f"{len(problems)} missing",
          "check the two .env files above")
    for p in problems:
        print(f"      - {p}")
    print(f"      provider={provider} → {', '.join(PROVIDER_KEYS.get(provider, ())) or '(no credentials needed)'}")


def check_paths() -> None:
    """[3] Do the knowledge source, dataset and output folder really exist."""
    print("\n[3] does what is pointed at really exist")
    bundle = os.environ.get("AGENTIC_OKF_BUNDLE_DIR", "").strip()
    dataset = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    outdir = os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip()

    check("knowledge-source folder", bool(bundle) and Path(bundle).is_dir(), bundle or "(not set)")
    if bundle and Path(bundle).is_dir():
        # Do not reimplement the counting here; call `tools_okf._load` itself. A
        # separate count is certain to drift, and drift means "the check passes but
        # there are really 0 documents".
        # (That happened: a flat bundle came out as 0 documents in the tool and
        # nobody noticed.)
        try:
            # Imported by name, not loaded from a path. The module is importable
            # because the package is installed, so this no longer depends on the two
            # files being neighbours.
            import importlib
            mod = importlib.import_module(BY_NAME["okf"].module)
            docs, skipped = mod._load(Path(bundle))
            layout = "domain folders" if any("/" in d.address for d in docs) else "flat"
            check("the knowledge source has documents", bool(docs),
                  f"{len(docs)} docs · {layout} layout" + (f" · {len(skipped)} filtered out" if skipped else ""),
                  "check that the .md files in the bundle have a `title` in their frontmatter")
            for s in skipped[:3]:
                print(f"      filtered out: {s['path']} — {s['why'][:60]}")
        except Exception as e:  # noqa: BLE001
            check("the knowledge source has documents", False, f"{type(e).__name__}: {e}")
    check("data csv", bool(dataset) and Path(dataset).is_file(), dataset or "(not set)",
          "run make_sample_data.py or prep_*.py first")
    check("output folder", bool(outdir) and Path(outdir).is_dir(), outdir or "(not set)")


async def check_databases() -> None:
    """[4] Can both databases be connected to — the board's and core's."""
    print("\n[4] databases")
    import re

    import asyncpg

    async def reachable(label: str, url: str, hint: str) -> None:
        if not url:
            check(label, False, "no address", hint)
            return
        dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            # Show the DSN with the password masked.
            check(label, True, re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn))
        except Exception as e:  # noqa: BLE001
            check(label, False, type(e).__name__, hint)

    from memstara.blackboard import dsn as board_dsn

    await reachable("board DB (memstara)", board_dsn(), "docker compose up -d")
    await reachable("core DB (motoro)", os.environ.get("MOTORO_DATABASE_URL", ""),
                    "docker compose up -d in the motoro folder")


def check_allowlist() -> None:
    """[5] Does the MCP allowlist cover every variable the tools read."""
    print("\n[5] MCP allowlist")
    # This is the quietest failure in the whole project — see the comments on
    # bootstrap.allowlist_gaps.
    gaps = allowlist_gaps()
    check("the list covers every variable the tools read", not gaps,
          "nothing missing" if not gaps else f"missing: {', '.join(gaps)}",
          "add the names above to mcp_allowed_env_vars in settings.py")


def check_matcher_catalog() -> None:
    """[6] Is the built matcher catalog — and its embedding matrix — still current.

    A stale catalog does not crash. It answers every concept against a vocabulary
    the cohort no longer has, and the agent concludes the columns it wants are
    simply absent. That is the failure this step exists to make impossible.
    """
    print("\n[6] matcher catalog cache")
    try:
        from memstara.matcher import config as matcher_cfg
        from memstara.matcher.catalog import load_catalog, verify_catalog
        from memstara.matcher.embedder import embeddings_stale
        from memstara.matcher.service import build_run_config, current_fingerprint
    except Exception as e:  # noqa: BLE001
        check("import matcher_impl", False, f"{type(e).__name__}: {e}",
              "check you are in the memstara environment and that numpy is installed")
        return

    # Nothing here loads a model. `current_fingerprint` reads the CSV *header*,
    # and both staleness checks compare stored hashes, so this step costs
    # milliseconds and runs even under --quick.
    try:
        run_config = build_run_config()
        fingerprint = current_fingerprint(run_config)
    except Exception as e:  # noqa: BLE001
        check("compute the catalog fingerprint", False, f"{type(e).__name__}: {e}",
              "check MEMSTARA_DATASET_PATH and MEMSTARA_OUTCOME_COLUMN")
        return

    # No `fix` is passed below: `verify_catalog` and `embeddings_stale` each end
    # their message with the rebuild command already — that is why the hint was
    # hoisted into them rather than repeated at every call site.
    stale = verify_catalog(matcher_cfg.CATALOG_JSON, fingerprint)
    if not check("the catalog matches the current cohort", stale is None,
                 stale or f"{matcher_cfg.CATALOG_JSON.name} · {fingerprint['columns_sha1'][:8]}"):
        return

    # Checked separately because `Matcher.from_catalog` REFUSES a stale matrix
    # rather than re-embedding it (matcher.py:216). Without this line preflight
    # passes and the run still dies — at the first match_concepts call, minutes in.
    entries = load_catalog(matcher_cfg.CATALOG_JSON)
    stale_matrix = embeddings_stale(
        matcher_cfg.CATALOG_JSON,
        match_texts=[e.match_text for e in entries],
        cfg=run_config.embedding,
    )
    check("the embedding matrix matches the catalog", stale_matrix is None,
          stale_matrix or f"{len(entries)} entries")


def check_servers() -> None:
    """[7] Do all five tool server files import cleanly in a fresh process."""
    print("\n[7] do the tool servers really start")
    # Just import each file. Started as a server it would sit waiting on stdio and
    # never return, so **only the import** runs, which catches startup errors — where
    # nearly all the failures happen.
    for server in SERVERS:
        r = subprocess.run(
            [sys.executable, "-c",
             f"import importlib;m=importlib.import_module('{server.module}');"
             f"print(len([x for x in dir(m) if not x.startswith('_')]))"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=120,
        )
        ok = r.returncode == 0
        detail = "" if ok else (r.stderr.strip().splitlines() or ["?"])[-1][:90]
        check(server.module, ok, detail,
              f"starting it directly with `python -m {server.module}` shows the real error")


def main() -> int:
    """Run every check in order and return 0 only when all of them passed."""
    ap = argparse.ArgumentParser(description="pre-run environment check. Does not call an LLM.")
    ap.add_argument("--provider", default="azure_foundry",
                    choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--quick", action="store_true", help="skip the tool-server startup check")
    args = ap.parse_args()

    print("=" * 66)
    print("  pre-run check — calls no LLM and writes nothing to the board")
    print("=" * 66)
    print(f"  .env read: {', '.join(str(p) for p in _LOADED) or '(none)'}")
    print(f"  python:    {sys.executable}")

    check_env_files()
    check_vars(args.provider)
    check_paths()
    asyncio.run(check_databases())
    check_allowlist()
    check_matcher_catalog()
    if not args.quick:
        check_servers()
    else:
        print("\n[7] tool servers — skipped (--quick)")

    print("\n" + "=" * 66)
    if _failures:
        print(f"  {len(_failures)} failed: {', '.join(_failures)}")
        print("  deal with the 'how to fix' lines above first. Run now and it dies partway.")
        return 1
    print("  everything passed — you can run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
