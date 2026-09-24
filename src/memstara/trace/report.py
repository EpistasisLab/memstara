#!/usr/bin/env python3
"""Read a run directory and say, in one file, whether the run went normally."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from memstara.pipeline.core import COLUMN_COUNT_MIN

# Ordered worst-first: the verdict is the first one whose condition holds. Turn the
# order around and a failed run settles down into "warning".
VERDICT_FAIL = "failed"    # not one trial succeeded
VERDICT_WARN = "warning"   # it ran, but something was caught
VERDICT_OK = "normal"      # nothing at all was caught


def _read_json(path: Path, default: Any) -> Any:
    """Read one JSON file. Return *default* if it is missing or broken.

    Stopping partway through the report because of one file would take the rest of the
    perfectly good information out of view with it.
    """
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a log file holding one JSON object per line."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a truncated last line on a killed run is not worth failing over
                # When a run is killed the last line is cut off mid-way. There is no
                # reason to give up the whole report over that one line, so it is
                # skipped quietly.
    return out


def collect(run_dir: Path) -> dict[str, Any]:
    """Everything the report needs, gathered from the four files in *run_dir*.

    It does not judge — that is judge()'s job. Keeping gathering and judging apart means
    the reading side does not have to be touched when the criteria change.
    """
    manifest = _read_json(run_dir / "manifest.json", {})   # what was run, and how
    rows = _read_json(run_dir / "todo_rows.json", [])      # the per-trial results
    summary = _read_json(run_dir / "summary.json", {})     # the overall summary
    records = _read_jsonl(run_dir / "run.jsonl")           # the structured log in full

    # Kept whole, not counted. A count tells you something happened; the text tells you
    # what, and that is the part that was missed last time. So the report carries the
    # text in full, uncut, too.
    problems = [r for r in records if r.get("level") in ("warning", "error", "critical")]

    executed = [r for r in records if r.get("event") == "mcp.tool.executed"]
    by_adapter = [r for r in executed
                  if str(r.get("logger", "")).endswith(".mcp.adapters")]
    # A log with no adapter side at all (an older run with a different setting) is
    # counted as it stands.
    executed = by_adapter or executed  # a log without the adapter side is counted as it is

    # The count per (tool name, whether it succeeded). The report's tool table is drawn
    # from this.
    tool_calls: Counter[tuple[str, bool]] = Counter()
    for r in executed:
        tool_calls[(str(r.get("tool")), bool(r.get("success", True)))] += 1
    tool_errors: Counter[str] = Counter(
        str(r.get("tool")) for r in records if r.get("event") == "mcp.tool.error_result"
    )

    # Cost comes from the rows when they carry it, because the log cannot be trusted for
    # this: `llm.call.completed` is emitted only by _complete and _complete_text
    # (llm_service.py:576, :1053), never by complete_with_tools — which is the path every
    # reason_act turn takes. Summing the log on a real 3-trial run caught 9 of 41 calls
    # and understated the cost roughly tenfold. Runs recorded before the rows carried
    # cost still get a number, pinned down in the report as the lower bound ("or more")
    # that it is.
    if any(row.get("cost") for row in rows):
        cost = sum(float(v) for row in rows for v in (row.get("cost") or {}).values())
        toks = [(row.get("tokens") or {}).values() for row in rows]
        prompt_tokens = sum(int(p[0]) for vs in toks for p in vs)
        completion_tokens = sum(int(p[1]) for vs in toks for p in vs)
        cost_source = "rows"
    else:
        llm = [r for r in records if r.get("event") == "llm.call.completed"]
        cost = sum(float(r.get("cost_usd") or 0) for r in llm)
        prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in llm)
        completion_tokens = sum(int(r.get("completion_tokens") or 0) for r in llm)
        cost_source = "log"

    # Only the case where the agent picked nothing at all is marked abnormal (there is
    # no upper bound).
    trials = []
    for row in rows:
        chosen = [c for c in (row.get("columns") or [])]
        trials.append(
            {
                "trial": row.get("trial"),
                "ok": row.get("auc") is not None,
                "auc": row.get("auc"),
                "n_columns": len(chosen),
                "columns": chosen,
                # Marked a violation only when not one column was picked.
                "out_of_range": bool(chosen) and len(chosen) < COLUMN_COUNT_MIN,
                "error": row.get("error") or "",
                "perspective": row.get("perspective") or "",
            }
        )

    return {
        "manifest": manifest,
        "summary": summary,
        "trials": trials,
        "problems": problems,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "n_records": len(records),
        "cost": cost,
        "cost_source": cost_source,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "n_runs": sum(len(row.get("run_ids") or {}) for row in rows),
    }


def judge(data: dict[str, Any]) -> tuple[str, list[str]]:
    """Return the verdict and the reasons for it. No reasons means it was clean.

    Four things are asked.
      · were as many trial records left as were requested
      · was there any log record at warning or above
      · did any tool call fail
      · was there a failed trial, or one that broke its own column-count promise
    """
    trials = data["trials"]
    failed = [t for t in trials if not t["ok"]]
    out_of_range = [t for t in trials if t["out_of_range"]]

    reasons: list[str] = []

    # A run whose trials all died before producing a row leaves an empty list, and an
    # empty list trips none of the checks below — it would be reported clean. Compare
    # against what was asked for instead of trusting what is there.
    requested = (data["manifest"].get("args") or {}).get("trials")
    if isinstance(requested, int) and len(trials) != requested:
        reasons.append(f"only {len(trials)} trial records — {requested} were requested")
        if not trials:
            return VERDICT_FAIL, reasons

    if data["problems"]:
        reasons.append(f"{len(data['problems'])} log records at warning or above")
    if data["tool_errors"]:
        detail = ", ".join(f"{t} ×{n}" for t, n in sorted(data["tool_errors"].items()))
        reasons.append(f"tool call failed — {detail}")
    if failed:
        reasons.append(f"{len(failed)} failed trials (#{', #'.join(str(t['trial']) for t in failed)})")
    if out_of_range:
        detail = ", ".join(f"#{t['trial']} {t['n_columns']} columns" for t in out_of_range)
        reasons.append(f"not one column picked — {detail}")

    # The verdict from here on. The worst case is looked at first.
    # No trial succeeded means failed; anything caught means warning; otherwise normal.
    if trials and not any(t["ok"] for t in trials):
        return VERDICT_FAIL, reasons or ["not one trial succeeded"]
    if reasons:
        return VERDICT_WARN, reasons
    return VERDICT_OK, []


def render(run_dir: Path, data: dict[str, Any], verdict: str, reasons: list[str]) -> str:
    """Turn what was gathered and the verdict into one lump of markdown. Writes no file.

    Lines are stacked one at a time into a list called L and joined at the end. That
    reads more easily line by line than building the prose by appending to a string, and
    it is visible which line belongs to which section.

    The sections: verdict -> 1 warnings and errors -> 2 tool calls -> 3 per trial ->
    4 cost and tokens -> 5 what else to look at.
    **The verdict and its reasons come first.** If you have to scroll down for it,
    nobody will look.
    """
    manifest = data["manifest"]
    result = manifest.get("result") or {}
    args = manifest.get("args") or {}
    L: list[str] = []

    L.append(f"# Run report — {run_dir.name}")
    L.append("")
    L.append(f"## Verdict: **{verdict}**")
    L.append("")
    if reasons:
        L.append("What was caught:")
        L.append("")
        for r in reasons:
            L.append(f"- {r}")
    else:
        L.append("Nothing caught — 0 warnings, 0 tool failures, 0 failed trials, 0 constraint violations.")
    L.append("")
    L.append(
        f"trials {result.get('n_succeeded', '?')}/{result.get('n_trials', '?')} succeeded · "
        f"mean AUC {result.get('mean_auc')} · "
        f"model {args.get('model', '?')} · "
        f"{manifest.get('started_at', '?')} → {manifest.get('finished_at', '?')}"
    )
    L.append("")
    L.append("---")
    L.append("")

    # --- warnings and errors ---------------------------------------------
    L.append(f"## 1. Warnings and errors — {len(data['problems'])}")
    L.append("")
    if not data["problems"]:
        L.append(f"**0** records at warning or above out of {data['n_records']} log lines.")
    else:
        L.append("**The text in full.** Nothing is cut.")
        L.append("")
        for p in data["problems"]:
            where = " · ".join(
                str(p[k]) for k in ("trial", "stage") if k in p and p[k] is not None
            )
            L.append(f"- `{p.get('level')}` **{p.get('event')}**" + (f" — trial {where}" if where else ""))
            for key in ("tool", "server", "content", "error", "reason"):
                if p.get(key):
                    L.append(f"  - {key}: `{p[key]}`")
    L.append("")

    # --- tools -----------------------------------------------------------
    L.append("## 2. Tool calls")
    L.append("")
    names = sorted({t for t, _ in data["tool_calls"]} | set(data["tool_errors"]))
    if not names:
        L.append("No record of any tool call.")
    else:
        L.append("| tool | succeeded | failed |")
        L.append("|---|---:|---:|")
        for name in names:
            ok = data["tool_calls"][(name, True)]
            bad = data["tool_calls"][(name, False)] + data["tool_errors"][name]
            mark = " **←failed**" if bad else ""
            L.append(f"| `{name}` | {ok} | {bad}{mark} |")
    L.append("")

    # --- trials ----------------------------------------------------------
    L.append("## 3. Per trial")
    L.append("")
    L.append("No column-count constraint — the agent decides for itself on the OKF grounds.")
    L.append("")

    # Only when this dataset carries the planted answer key — see memstara.pipeline.core.aggregate.
    # On any other dataset there is no answer key, and reporting one would be a
    # failure that did not happen.
    summary = data["summary"]
    if "planted_recall" in summary:
        L.append(
            f"planted signal recall **{summary['planted_recall']}** — "
            f"found {summary.get('planted_found_in_top6') or 'none'}"
        )
        L.append("")
    L.append("| # | result | AUC | columns | perspective |")
    L.append("|---|---|---:|---|---|")
    for t in data["trials"]:
        status = "succeeded" if t["ok"] else f"**failed** — {t['error']}"
        cols = f"{t['n_columns']}"
        if t["out_of_range"]:
            cols += " **←no columns**"
        L.append(f"| {t['trial']} | {status} | {t['auc']} | {cols} | {t['perspective']} |")
    L.append("")

    # --- cost ------------------------------------------------------------
    L.append("## 4. Cost and tokens")
    L.append("")
    if data["cost_source"] == "rows":
        L.append(f"- {data['n_runs']} agent runs")
        L.append(f"- tokens {data['prompt_tokens']:,} in / {data['completion_tokens']:,} out")
        L.append(f"- cost **${data['cost']:.4f}**")
    else:
        L.append(f"- cost **${data['cost']:.4f} or more** — the real figure is far larger")
        L.append(f"- tokens {data['prompt_tokens']:,} in / {data['completion_tokens']:,} out (the same lower bound)")
        L.append("")
        L.append(
            "> ⚠️ **This run has no accurate cost recorded.** core emits "
            "`llm.call.completed` only from `_complete` and `_complete_text`, never from "
            "`complete_with_tools`, which is what reason_act uses on every turn. "
            "On this run only 9 calls out of 41 were caught in the log. "
            "Later runs are accurate because `execute_run`'s return value is put into "
            "the trial records. "
            "The real values can be seen in `trace/`."
        )
    L.append("")

    # --- what next -------------------------------------------------------
    L.append("## 5. What else to look at")
    L.append("")
    L.append("| file | what |")
    L.append("|---|---|")
    L.append("| `trace/trialNN.txt` | every step of that trial — tool arguments and results in full |")
    L.append("| `console.log` | exactly what went to the terminal |")
    L.append("| `run.jsonl` | the structured log in full. Every line tagged with trial and stage |")
    L.append("")
    L.append("```bash")
    L.append(f"python -m memstara.trace.run --from {run_dir} --trial 0 --full")
    L.append("```")
    L.append("")

    return "\n".join(L)


def build_report(run_dir: Path) -> tuple[str, list[str], Path]:
    """Write REPORT.md into *run_dir*. Returns the verdict, its reasons and the path.

    This function is the one way in from outside. src/memstara/pipeline/mvp.py calls it at the end
    of every run, so a run directory carries its REPORT.md from the moment it is made.
    """
    data = collect(run_dir)
    verdict, reasons = judge(data)
    path = run_dir / "REPORT.md"
    path.write_text(render(run_dir, data, verdict, reasons), encoding="utf-8")
    return verdict, reasons, path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="a directory under outputs/runs/")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"!! not a directory: {run_dir}", file=sys.stderr)
        return 1

    verdict, reasons, path = build_report(run_dir)
    print(f"verdict: {verdict}")
    for r in reasons:
        print(f"  - {r}")
    print(f"{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
