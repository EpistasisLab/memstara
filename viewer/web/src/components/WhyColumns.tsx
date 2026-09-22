import { useEffect, useState } from "react";
import type { ResultDetail, TraceGroup } from "../types";

/**
 * Why these columns — the matcher's record for one result.
 *
 * Every other panel reads from the snapshot. This one does not, and cannot: `match_trace`
 * is 598 kB across the 81 stored results against 89 kB for every explanation column the
 * snapshot does carry, and the snapshot is polled every two seconds. So it is fetched
 * from `/api/result/{id}`, once, and only when someone actually opens the section — the
 * `open` guard below is the whole reason this is a component and not an inline block.
 *
 * What it shows that nothing else can: the candidates that **lost.** The board and the
 * results table keep only the columns that were chosen, so "the agent picked HBA1C" was
 * on screen already and "it picked HBA1C over GLUCOSE, which scored 0.72" was nowhere.
 */

export default function WhyColumns({ resultId }: { resultId: number }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ResultDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Not fetched until opened, and not fetched twice. `data` in the guard is what makes
    // closing and reopening free; a person comparing two results should not re-download
    // 23 kB to look at the same one again.
    if (!open || data) return;
    fetch(`/api/result/${resultId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((d) => setData(d.result))
      .catch((e) => setError(String(e)));
  }, [open, data, resultId]);

  return (
    <details className="mt-3" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-sm font-bold hover:text-ink-soft">
        Why these columns
      </summary>
      {error ? (
        <p className="mt-2 text-sm text-red-700">Could not load the matcher record — {error}</p>
      ) : !data ? (
        <p className="mt-2 text-sm text-ink-faint">Loading…</p>
      ) : data.match_trace.length === 0 ? (
        // The two cases are told apart on purpose. No stored calls means the matcher was
        // never asked; stored calls that unwrap to nothing means the record is there and
        // unreadable. They need opposite fixes, and one message for both hides that.
        <p className="mt-2 text-sm text-ink-faint">
          {data.match_trace_calls === 0
            ? "No matcher record — this result's columns were not chosen through the matcher, or the run predates the trace being kept."
            : `${data.match_trace_calls} matcher call${data.match_trace_calls === 1 ? "" : "s"} stored, none readable as a concept group.`}
        </p>
      ) : (
        <div className="mt-2">
          <p className="mb-3 text-xs text-ink-faint">
            Matching scores are computed by the matcher, not LLM confidence ratings. Concepts originate from agent requests. What the matcher offered for each concept, in the order it was asked. A blue
            row is a column the agent went on to ask for. The rest are the candidates it
            passed over — the part of the reasoning that exists nowhere else.
          </p>
          <div className="space-y-3">
            {data.match_trace.map((g, i) => (
              <Group key={`${g.concept}-${i}`} group={g} />
            ))}
          </div>
          {/* Said plainly rather than left for someone to notice. The driver files the
              turn's whole matcher record on every task that turn created, so a concept
              here may belong to a sibling analysis. Hiding those would be tidier and would
              misrepresent the record. */}
          <p className="mt-3 text-xs text-ink-faint">
            {data.match_trace.length} concept{data.match_trace.length === 1 ? "" : "s"} from{" "}
            {data.match_trace_calls} matcher call{data.match_trace_calls === 1 ? "" : "s"}. The
            record is filed per agent turn, not per analysis, so a concept with nothing chosen
            was probably matched for another analysis of the same wave.
          </p>
        </div>
      )}
    </details>
  );
}

function Group({ group }: { group: TraceGroup }) {
  const chosen = group.candidates.filter((c) => c.chosen).length;

  return (
    <section className="rounded-lg border border-paper-line p-3">
      <header className="flex items-baseline justify-between gap-3">
        <h5 className="text-sm font-bold">{group.concept}</h5>
        <span className="font-mono text-[12px] text-ink-faint">
          {group.candidates.length} offered · {chosen} taken
        </span>
      </header>

      {group.note && <p className="mt-1 text-xs text-ink-soft">{group.note}</p>}

      <ol className="mt-2 space-y-1">
        {group.candidates.map((c) => (
          <li
            key={c.column}
            className={`flex items-baseline justify-between gap-3 font-mono text-[12px] ${
              c.chosen ? "font-bold text-stage-data" : "text-ink-faint"
            }`}
          >
            <span className="truncate">
              {c.column}
              {/* Chosen and absent from the cohort is its own outcome, and the same red
                  the panels use for "this is the direction that hurt". Without it the row
                  reads as a column that made it into the model. */}
              {c.chosen && !c.present && (
                <span className="ml-2 font-sans font-normal text-[#c0392b]">not in the cohort</span>
              )}
            </span>
            <span className="shrink-0">{c.score?.toFixed(3) ?? "—"}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
