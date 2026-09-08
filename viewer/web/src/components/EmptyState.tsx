import { cn } from "../lib/cn";
import { useViewer } from "../store/viewer";

/**
 * What a panel says when the slice it draws is not there.
 *
 * It exists because that judgement was being made eight times, identically and wrongly:
 * every panel wrote `if (!x) return <div>Loading…</div>`, which reads a network failure,
 * a 500, a stale container and an actual first load as the same thing and tells the
 * reader the most reassuring of the four. Someone watching a screen that says "Loading…"
 * has no reason to suspect anything is broken, so the message hid the failure it was
 * standing in for. That cost a long diagnosis once already.
 *
 * The store has carried `error` since it was written; the panels simply never read it.
 * Reading it here means one place decides, and a panel adds a case by naming its slice.
 *
 * **When each branch can be true.** Every slice is `snapshot?.something ?? null`, and the
 * store keeps the last snapshot through a failed poll (`store/viewer.ts:106-107`). So a
 * missing slice means there has been no successful response *at all* — not that the last
 * one failed. That is why the third branch can be so specific: `snapshot()` puts every
 * key in every 200 (`viewer/api/scene.py:972-986`), so an answer arriving without one did
 * not come from this code, which in practice means a container older than the source.
 *
 * Not for a panel that fetches for itself. `tabs/TaskTab.tsx` has its own request and its
 * own error state, and already tells the two apart; pointing it at the store's error
 * would make it report a failure that was not its own.
 */

export default function EmptyState({
  /** The slice, as a noun phrase: "the board", "the pipeline". It is read straight into
   *  a sentence, so it wants an article. */
  what,
  /** Padding and type size, when a panel's own are not the usual ones. */
  className,
}: {
  what: string;
  className?: string;
}) {
  const error = useViewer((s) => s.error);
  const loading = useViewer((s) => s.loading);

  if (error !== null)
    return (
      <div className={cn("p-8 text-amber-700", className)}>The API did not answer: {error}</div>
    );

  if (loading)
    return <div className={cn("p-8 text-ink-faint", className)}>Loading {what}…</div>;

  return (
    <div className={cn("p-8 text-amber-700", className)}>
      The API answered without {what} — the running container is probably older than the
      code.
    </div>
  );
}
