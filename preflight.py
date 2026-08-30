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

돌리기 전에 전부 확인한다. 실패하면 **무엇을 고쳐야 하는지까지** 말한다.

    python preflight.py                 # 기본 provider 로
    python preflight.py --provider openai
    python preflight.py --quick         # 도구 서버는 안 띄운다 (몇 초)

왜 이 파일이 있나
------------------
이 프로젝트에서 환경 문제는 **한참 뒤에, 엉뚱한 얼굴로** 나타난다.

    LLM 자격증명이 없다     → 씨뿌리기 한 번을 쓴 뒤 "api_base 가 필요하다"
    허용 목록에 빠졌다      → 아무 오류 없이 도구가 기본값으로 동작
    DB 가 안 떠 있다        → 에이전트 안에서 알 수 없는 도구 오류
    도구 서버가 못 뜬다     → "tools available: []" 한 줄

전부 **원인에서 멀리 떨어진 곳**에서 보인다. 그래서 원인을 찾는 데 시간이 든다.

이 파일은 그 확인을 **앞으로 당긴다.** LLM 을 한 번도 부르지 않으므로 돈이 안 들고,
판에도 아무것도 쓰지 않는다.

무엇을 보나
-----------
    1. `.env` 두 개가 읽혔나
    2. 필요한 환경변수가 다 있나 (provider 자격증명 포함)
    3. 가리키는 파일·폴더가 실제로 있나
    4. 두 DB 에 붙나
    5. **허용 목록이 도구가 읽는 것을 다 덮나** — 조용히 실패하는 그 자리
    6. 매처 카탈로그가 지금 코호트에 대해 아직 유효한가
    7. 도구 서버 다섯이 실제로 뜨고 도구를 내놓나

7번은 자식 프로세스를 띄우므로 20초쯤 걸린다. `--quick` 으로 건너뛸 수 있다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

# **First of all.** The imports below read the environment, so it must be set up first.
# **맨 먼저.** 아래 import 들이 환경을 읽으므로 그 전에 세워야 한다.
from bootstrap import HERE, PROVIDER_KEYS, allowlist_gaps, load_env, missing_vars

_LOADED = load_env()

OK, BAD, WARN = "  \033[32m✓\033[0m", "  \033[31m✗\033[0m", "  \033[33m!\033[0m"
_failures: list[str] = []


def check(label: str, passed: bool, detail: str = "", fix: str = "") -> bool:
    """Print one check line, remember the failure, and return whether it passed.

    한 줄짜리 점검 결과를 찍고, 실패면 기록해 둔 뒤 통과 여부를 돌려준다.
    """
    print(f"{OK if passed else BAD} {label}" + (f"  —  {detail}" if detail else ""))
    if not passed:
        _failures.append(label)
        if fix:
            print(f"      고치는 법: {fix}")
    return passed


def check_env_files() -> None:
    """[1] Were both `.env` files found where they are expected.

    [1] `.env` 두 개가 있어야 할 자리에 있나.
    """
    print("\n[1] .env")
    for path in (HERE / ".env", HERE / ".." / "agentic-core" / ".env"):
        check(f".env — {path.parent.name}/", path.is_file(), str(path.resolve()),
              f"{path} 를 만들어라 (.env.example 참고)")


def check_vars(provider: str) -> None:
    """[2] Are all required variables set, including this provider's credentials.

    [2] 필요한 변수가 다 있나 — 고른 provider 의 자격증명까지 포함해서.
    """
    print("\n[2] 환경변수")
    problems = missing_vars(provider)
    check("필요한 변수가 다 있다", not problems,
          "없음" if not problems else f"{len(problems)}개 빠짐",
          "위 .env 두 개를 확인하라")
    for p in problems:
        print(f"      - {p}")
    print(f"      provider={provider} → {', '.join(PROVIDER_KEYS.get(provider, ())) or '(자격증명 불필요)'}")


def check_paths() -> None:
    """[3] Do the knowledge source, dataset and output folder really exist.

    [3] 지식원 · 데이터 csv · 출력 폴더가 실제로 있나.
    """
    print("\n[3] 가리키는 것이 실제로 있나")
    bundle = os.environ.get("AGENTIC_OKF_BUNDLE_DIR", "").strip()
    dataset = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    outdir = os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip()

    check("지식원 폴더", bool(bundle) and Path(bundle).is_dir(), bundle or "(안 정해짐)")
    if bundle and Path(bundle).is_dir():
        # Do not reimplement the counting here; call `tools_okf._load` itself. A
        # separate count is certain to drift, and drift means "the check passes but
        # there are really 0 documents".
        # (That happened: a flat bundle came out as 0 documents in the tool and
        # nobody noticed.)
        #
        # 세는 방식을 여기서 다시 짜지 않는다. `tools_okf._load` 를 그대로 부른다 —
        # 따로 세면 반드시 어긋나고, 어긋나면 "점검은 통과인데 실제로는 0장" 이 된다.
        # (실제로 그렇게 당했다: 평평한 번들이 도구에서 0장으로 나오는데 아무도 몰랐다.)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("tools_okf", HERE / "tools_okf.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules["tools_okf"] = mod
            spec.loader.exec_module(mod)
            docs, skipped = mod._load(Path(bundle))
            layout = "도메인 폴더" if any("/" in d.address for d in docs) else "평평"
            check("지식원에 문서가 있다", bool(docs),
                  f"{len(docs)}장 · {layout} 배치" + (f" · 걸러짐 {len(skipped)}" if skipped else ""),
                  "번들 안의 .md 에 frontmatter 의 `title` 이 있는지 확인하라")
            for s in skipped[:3]:
                print(f"      걸러짐: {s['path']} — {s['why'][:60]}")
        except Exception as e:  # noqa: BLE001
            check("지식원에 문서가 있다", False, f"{type(e).__name__}: {e}")
    check("데이터 csv", bool(dataset) and Path(dataset).is_file(), dataset or "(안 정해짐)",
          "make_sample_data.py 나 prep_*.py 를 먼저 돌려라")
    check("출력 폴더", bool(outdir) and Path(outdir).is_dir(), outdir or "(안 정해짐)")


async def check_databases() -> None:
    """[4] Can both databases be connected to — the board's and core's.

    [4] 두 DB 에 붙나 — 판의 것과 core 의 것.
    """
    print("\n[4] 데이터베이스")
    import re

    import asyncpg

    async def reachable(label: str, url: str, hint: str) -> None:
        if not url:
            check(label, False, "주소가 없다", hint)
            return
        dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            # Show the DSN with the password masked.
            # 비밀번호는 가리고 보여 준다.
            check(label, True, re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn))
        except Exception as e:  # noqa: BLE001
            check(label, False, type(e).__name__, hint)

    from blackboard import dsn as board_dsn

    await reachable("판 DB (memstara)", board_dsn(), "docker compose up -d")
    await reachable("core DB (agentic_core)", os.environ.get("AGENTIC_DATABASE_URL", ""),
                    "agentic-core 폴더에서 docker compose up -d")


def check_allowlist() -> None:
    """[5] Does the MCP allowlist cover every variable the tools read.

    [5] 도구가 읽는 변수를 MCP 허용 목록이 다 덮나.
    """
    print("\n[5] MCP 허용 목록")
    # This is the quietest failure in the whole project — see the comments on
    # bootstrap.allowlist_gaps.
    # 이것이 가장 조용히 실패하는 자리다 — bootstrap.allowlist_gaps 의 주석 참고.
    gaps = allowlist_gaps()
    check("도구가 읽는 변수를 목록이 다 덮는다", not gaps,
          "빠짐 없음" if not gaps else f"빠진 것: {', '.join(gaps)}",
          "settings.py 의 mcp_allowed_env_vars 에 위 이름을 더하라")


def check_matcher_catalog() -> None:
    """[6] Is the built matcher catalog — and its embedding matrix — still current.

    A stale catalog does not crash. It answers every concept against a vocabulary
    the cohort no longer has, and the agent concludes the columns it wants are
    simply absent. That is the failure this step exists to make impossible.
    """
    print("\n[6] 매처 카탈로그 캐시")
    try:
        from matcher_impl import config as matcher_cfg
        from matcher_impl.catalog import load_catalog, verify_catalog
        from matcher_impl.embedder import embeddings_stale
        from matcher_impl.service import build_run_config, current_fingerprint
    except Exception as e:  # noqa: BLE001
        check("matcher_impl 을 import 한다", False, f"{type(e).__name__}: {e}",
              "memstara 환경인지, numpy 가 깔려 있는지 확인하라")
        return

    # Nothing here loads a model. `current_fingerprint` reads the CSV *header*,
    # and both staleness checks compare stored hashes, so this step costs
    # milliseconds and runs even under --quick.
    try:
        run_config = build_run_config()
        fingerprint = current_fingerprint(run_config)
    except Exception as e:  # noqa: BLE001
        check("카탈로그 지문을 계산한다", False, f"{type(e).__name__}: {e}",
              "MEMSTARA_DATASET_PATH 와 MEMSTARA_OUTCOME_COLUMN 을 확인하라")
        return

    # No `fix` is passed below: `verify_catalog` and `embeddings_stale` each end
    # their message with the rebuild command already — that is why the hint was
    # hoisted into them rather than repeated at every call site.
    stale = verify_catalog(matcher_cfg.CATALOG_JSON, fingerprint)
    if not check("카탈로그가 지금 코호트와 맞는다", stale is None,
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
    check("임베딩 행렬이 카탈로그와 맞는다", stale_matrix is None,
          stale_matrix or f"{len(entries)}개 항목")


def check_servers() -> None:
    """[7] Do all five tool server files import cleanly in a fresh process.

    [7] 도구 서버 파일 다섯이 새 프로세스에서 탈 없이 import 되나.
    """
    print("\n[7] 도구 서버가 실제로 뜨나")
    # Just import each file. Started as a server it would sit waiting on stdio and
    # never return, so **only the import** runs, which catches startup errors — where
    # nearly all the failures happen.
    #
    # 각 파일을 그냥 import 해 본다. 서버로 띄우면 stdio 를 기다리며 안 끝나므로,
    # **import 만** 해서 시작 단계의 오류를 잡는다. 대부분의 실패가 거기서 난다.
    for name in ("tools_okf", "tools_data", "tools_ml", "tools_blackboard", "tools_matcher"):
        r = subprocess.run(
            [sys.executable, "-c",
             f"import importlib.util,sys;"
             f"s=importlib.util.spec_from_file_location('{name}','{HERE / (name + '.py')}');"
             f"m=importlib.util.module_from_spec(s);sys.modules['{name}']=m;s.loader.exec_module(m);"
             f"print(len([x for x in dir(m) if not x.startswith('_')]))"],
            capture_output=True, text=True, cwd=HERE, timeout=120,
        )
        ok = r.returncode == 0
        detail = "" if ok else (r.stderr.strip().splitlines() or ["?"])[-1][:90]
        check(f"{name}.py", ok, detail, f"python {name}.py 로 직접 띄워 보면 진짜 오류가 보인다")


def main() -> int:
    """Run every check in order and return 0 only when all of them passed.

    점검을 순서대로 전부 돌리고, 다 통과했을 때만 0 을 돌려준다.
    """
    ap = argparse.ArgumentParser(description="돌리기 전 환경 점검. LLM 을 부르지 않는다.")
    ap.add_argument("--provider", default="azure_foundry",
                    choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--quick", action="store_true", help="도구 서버 기동 검사를 건너뛴다")
    args = ap.parse_args()

    print("=" * 66)
    print("  실행 전 점검 — LLM 을 부르지 않고 판에도 쓰지 않는다")
    print("=" * 66)
    print(f"  읽은 .env: {', '.join(str(p) for p in _LOADED) or '(없음)'}")
    print(f"  파이썬:    {sys.executable}")

    check_env_files()
    check_vars(args.provider)
    check_paths()
    asyncio.run(check_databases())
    check_allowlist()
    check_matcher_catalog()
    if not args.quick:
        check_servers()
    else:
        print("\n[7] 도구 서버 — 건너뜀 (--quick)")

    print("\n" + "=" * 66)
    if _failures:
        print(f"  실패 {len(_failures)}건: {', '.join(_failures)}")
        print("  위의 '고치는 법' 을 먼저 처리하라. 지금 돌리면 도중에 죽는다.")
        return 1
    print("  전부 통과 — 돌려도 된다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
