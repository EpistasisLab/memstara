import { cleanLog } from "../lib/telemetry";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "../lib/cn";

/**
 * A console transcript that follows the end while it is being written.
 *
 * The driver already marks its own structure on stdout — `step`, `done` and `note` in
 * `src/memstara/pipeline/board.py:275-300` print a banner, a tick and a bullet — so the
 * work here is not to invent a format but to stop that structure from being flattened
 * into six hundred identical grey lines. Every shape below is one this component reads
 * back out; nothing is guessed at from the text.
 *
 * Following is abandoned the moment somebody scrolls up, and resumed when they scroll
 * back to the bottom. A log that yanks itself away while it is being read is worse than
 * one that does not move at all.
 */

type LogKind = "step" | "done" | "note" | "lap" | "plain" | "error";

/**
 * Which of the driver's printed shapes a line is.
 *
 * Every pattern here was checked against a real run's `console.log` rather than read off
 * the format strings, and two of them were wrong that way round: the lap line is indented
 * three spaces (`board.py:1482`) and not flush left, and the banner rule comes in more
 * than one width — a sample of one run had both 68 and 74 characters — so its length is
 * not part of the test.
 *
 * The rules themselves are dropped rather than drawn. They carry no content: they exist
 * to make a title findable in a terminal, and a title already styled as a heading does
 * not need seventy more characters to be findable.
 */
function kindOf(line: string): LogKind | null {
  if (/\b(error|failed|exception|traceback)\b/i.test(line)) return "error";
  if (/^=+$/.test(line.trimEnd())) return null;
  if (/^\s\(\d+'?\)\s/.test(line)) return "step";
  if (/^\s{3}✓/.test(line)) return "done";
  if (/^\s{3}·/.test(line)) return "note";
  if (/^\s{3}\[lap\s/.test(line)) return "lap";
  return "plain";
}

const KIND_CLASS: Record<LogKind, string> = {
  error: "font-semibold text-red-600",
  step: "mt-3 border-t border-paper-line pt-2 font-bold text-ink",
  done: "font-bold text-emerald-700",
  note: "text-ink-soft",
  lap: "text-sky-800",
  plain: "text-ink-faint",
};

export interface RunLogProps {
  lines: string[];
  /** Bytes the service jumped over. Drawn as a break in the transcript, because a
   *  transcript with a silent hole in it is the one thing a transcript may not be. */
  skipped: number;
  /** Shown grey at the end: written, but not yet terminated by a newline. */
  tail: string;
}

export default function RunLog({ lines, skipped, tail }: RunLogProps) {
  const box = useRef<HTMLDivElement>(null);
  const [following, setFollowing] = useState(true);
  const [showPolling, setShowPolling] = useState(false);
  const pollingCount = lines.filter(line => kindOf(cleanLog(line)) === "lap").length;

  // `useLayoutEffect`, not `useEffect`: the scroll has to happen in the same frame the
  // new lines are painted, or the transcript visibly jumps on every poll.
  useLayoutEffect(() => {
    if (following && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, tail, following]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onScroll = () => {
      // 24px of slack, so that a scrollbar a pixel or two off the floor still counts as
      // "at the end" — otherwise following switches itself off at random.
      setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <label className="flex items-center gap-2 border-b border-paper-line px-3 py-2 text-xs text-ink-soft"><input type="checkbox" checked={showPolling} onChange={e => setShowPolling(e.target.checked)} />Show routine polling messages ({pollingCount}{showPolling ? " shown" : " hidden"})</label>
      <div ref={box} className="min-h-0 flex-1 overflow-auto bg-ink/[0.02] px-3 py-2">
        {skipped > 0 && (
          <div className="mb-2 rounded-md border border-amber-300 bg-amber-50 px-2 py-1
                          text-[12px] font-bold text-amber-800">
            {skipped.toLocaleString()} bytes further back are not shown — the log outran
            what one response carries
          </div>
        )}

        {lines.length === 0 && !tail ? (
          <div className="py-6 text-[12px] text-ink-faint">Nothing has been printed yet.</div>
        ) : (
          <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-[1.45]">
            {lines.map((raw, i) => {
              const line = cleanLog(raw);
              const kind = kindOf(line);
              if (kind === null || (kind === "lap" && !showPolling)) return null;
              return (
                <div key={`${i}-${line}`} className={KIND_CLASS[kind]}>
                  {line || " "}
                </div>
              );
            })}
            {/* The half-written line, kept apart so it is never mistaken for a finished
                one and never classified — its shape is not decided yet. */}
            {tail && <div className="text-ink-faint opacity-60">{cleanLog(tail)}</div>}
          </pre>
        )}
      </div>

      {!following && (
        <button
          type="button"
          onClick={() => setFollowing(true)}
          className={cn(
            "absolute bottom-3 right-4 rounded-full bg-ink px-3 py-1.5 text-[12px]",
            "font-bold text-white shadow-lg hover:bg-ink/90",
          )}
        >
          Follow the end ↓
        </button>
      )}
    </div>
  );
}
