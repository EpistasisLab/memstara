import { Radio } from "lucide-react";
import Panel from "../components/Panel";
import { STAGE_COLOR, STORE_LABEL } from "../lib/stage";
import { useFeed } from "../store/viewer";
import type { FeedEvent } from "../types";

/**
 * The feed — what just happened, in order, newest first.
 *
 * Two things about its scope are said on screen rather than left to be discovered:
 *
 * 1. **All runs.** Only create_task/claim_task/submit_result carry a run_tag at all
 *    (api/queries.py, TASK_TOUCHES), so filtering by the run the control panel selects
 *    would silently drop most of the feed — a curator's okf_read would never appear. The
 *    header says "All runs" instead of pretending.
 * 2. **Both driving paths.** The scene draws board agents only; the supervisor path did
 *    the larger share of the tool calls. A board-only feed would understate the system by
 *    roughly fivefold, so supervisor rows are shown and marked.
 *
 * A row whose agent the viewer cannot name is kept, not dropped — `agent` is null, the
 * dot goes grey, and `label` falls back to the raw agent name. A call it cannot name is
 * exactly the thing someone would want to see.
 *
 * This body is deliberately plain: every field of `FeedEvent`, one row each, no
 * animation and no visual treatment beyond the stage colour. The presentation is left to
 * be designed rather than guessed at here.
 */

/** `at` is a UTC ISO string from the API (api/scene._iso), shown in local time.
 *  `tabular-nums` keeps the column from shifting as the digits change. */
function clock(at: string): string {
  return new Date(at).toLocaleTimeString(undefined, { hour12: false });
}

function Row({ event }: { event: FeedEvent }) {
  return (
    <li className="flex items-baseline gap-2 border-b border-paper-line px-4 py-1.5 text-xs last:border-0">
      <span className="shrink-0 font-mono tabular-nums text-ink-faint">{clock(event.at)}</span>

      <span
        className="mt-1 h-2 w-2 shrink-0 self-start rounded-full"
        style={{ backgroundColor: event.agent ? STAGE_COLOR[event.agent] : "#8a8880" }}
      />

      <span className="w-24 shrink-0 truncate text-ink-soft" title={event.name}>
        {event.label}
      </span>

      <span className="min-w-0 flex-1 truncate font-mono font-bold" title={event.tool}>
        {event.tool}
      </span>

      <span className="shrink-0 truncate text-ink-faint" title={event.server}>
        {event.server}
      </span>

      <span className="w-28 shrink-0 truncate text-right text-ink-faint">
        {STORE_LABEL[event.store]}
      </span>

      {/* Marked, not hidden: these calls are real work the scene does not draw. */}
      {event.path === "supervisor" && (
        <span className="shrink-0 rounded bg-paper px-1.5 py-0.5 text-[10px] text-ink-faint">
          supervisor
        </span>
      )}
    </li>
  );
}

export default function FeedPanel() {
  const feed = useFeed();

  return (
    <Panel
      icon={Radio}
      title="Activity feed"
      count={feed?.length}
      status={<span>All runs</span>}
      bodyClassName="p-0"
    >
      {!feed ? (
        <div className="p-8 text-ink-faint">Loading…</div>
      ) : feed.length === 0 ? (
        <div className="p-8 text-ink-faint">No tool calls recorded yet.</div>
      ) : (
        <ul>
          {feed.map((e) => (
            <Row key={e.key} event={e} />
          ))}
        </ul>
      )}
    </Panel>
  );
}
