import { useEffect } from "react";
import { Terminal } from "lucide-react";
import Panel from "../components/Panel";
import RunLog from "../components/RunLog";
import { useControl } from "../store/control";
import { POLL_MS } from "../store/viewer";

/**
 * The driver's own console, live.
 *
 * Everything else on this screen is read out of the two databases, and the databases only
 * ever hear about the agents. The steps the driver takes around them — calling the five
 * agents up, switching the tool servers on, each wave, each lap of the board — are printed
 * and nowhere else (`src/memstara/pipeline/board.py:275-300`). This panel is the only
 * place they are visible, which is why "nothing is happening" and "the driver is between
 * waves" stopped being the same picture.
 *
 * It reads a file, not a stream. The service hands back a byte offset and the next request
 * asks from there, so a run printing steadily costs one small response every two seconds
 * rather than the whole log each time. Server-sent events would be tidier and would mean
 * a second kind of connection through nginx for one panel; the polling this viewer already
 * does everywhere else is enough for a log nobody reads faster than it is written.
 *
 * **It can only show a run this viewer started.** A pipeline launched by hand in a
 * terminal writes its own `console.log` under `outputs/runs/`, and the control service has
 * no way to know which directory that is. The panel says so rather than showing an empty
 * box that looks like a broken feed.
 */

export default function LogPanel() {
  const up = useControl((s) => s.up);
  const logTag = useControl((s) => s.logTag);
  const lines = useControl((s) => s.logLines);
  const tail = useControl((s) => s.logTail);
  const skipped = useControl((s) => s.logSkipped);
  const running = useControl((s) => s.running);

  // Only while this panel is on screen. The log is the one thing here that grows without
  // limit, and polling it from behind another view would be paying for a transcript
  // nobody is reading.
  useEffect(() => {
    const tick = () => {
      if (!document.hidden) void useControl.getState().pollLog();
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  const live = running !== null && running.run_tag === logTag;

  return (
    <Panel
      icon={Terminal}
      title="Run log"
      count={lines.length || undefined}
      status={
        logTag ? (
          <>
            <span className="font-mono">{logTag}</span>
            <span className={live ? "font-bold text-emerald-700" : undefined}>
              {live ? "live" : "ended"}
            </span>
          </>
        ) : undefined
      }
      bodyClassName="overflow-hidden p-0"
    >
      {up === false ? (
        <div className="p-8 text-[13px] text-ink-faint">
          <p>The control service is not running, and it is the only thing that holds the
             driver's console. Start it on the host:</p>
          <code className="mt-2 block font-mono text-[11px] text-ink">
            python -m memstara.control
          </code>
        </div>
      ) : logTag === null ? (
        <div className="p-8 text-[13px] text-ink-faint">
          <p className="font-bold text-ink">No run has been started from this screen.</p>
          <p className="mt-1 leading-snug">
            Press Start on the left and the driver's steps appear here as it prints them.
            A pipeline started by hand keeps its console in its own{" "}
            <code className="font-mono text-[11px]">outputs/runs/…/console.log</code>, which
            this service cannot find.
          </p>
        </div>
      ) : (
        <RunLog lines={lines} skipped={skipped} tail={tail} />
      )}
    </Panel>
  );
}
