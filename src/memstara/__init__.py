"""The Memstara sandbox package.

This file is empty of imports on purpose, and must stay that way.

Why it holds a single `setdefault`
----------------------------------
litellm reads `LITELLM_LOG` **while it is being imported** (`litellm/_logging.py:80`).
Set it any later and the request bodies go unlogged — silently, which is exactly how
it first failed. `bootstrap.py:42-53` records the rule that came out of that:

    every entry point must import `bootstrap` **before** anything that pulls in
    motoro / litellm. This has caught us twice.

A rule every entry point must remember is a rule that will be forgotten a third time.
Here it stops being a convention: under `python -m memstara.<anything>`, the
interpreter cannot reach a submodule without executing this file first. The ordering
is no longer something to get right — it is something that cannot be got wrong.

That guarantee is worth exactly as much as this file's emptiness. **Import nothing
here.** One import of a module that itself imports litellm, and the line below runs
too late again, in a place nobody thinks to look.

It is a `setdefault`, so a value from the shell or from `launch.json` still wins.
"""

from __future__ import annotations

import os

os.environ.setdefault("LITELLM_LOG", "DEBUG")
