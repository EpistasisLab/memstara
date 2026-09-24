"""`python -m memstara.control` — the control service, on the loopback interface.

    python -m memstara.control            # 127.0.0.1:8072
    python -m memstara.control --port 9072


`src/memstara/__init__.py` run first, and that file is the only place `LITELLM_LOG` is
set before litellm can read it. Nothing here imports litellm today — the child does,
and the child inherits this process's environment.
"""

from __future__ import annotations

import argparse

from memstara.control.service import serve


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m memstara.control")
    ap.add_argument("--port", type=int, default=8072,
                    help="the port on 127.0.0.1 (default 8072). The address is not "
                         "configurable; see serve() for why")
    args = ap.parse_args()
    serve(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
