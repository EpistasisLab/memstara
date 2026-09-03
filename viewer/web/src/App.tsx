import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, type ComponentType } from "react";
import Panel from "./components/Panel";
import { cn } from "./lib/cn";
import { VIEWS } from "./lib/views";
import ControlPanel from "./panels/ControlPanel";
import FeedPanel from "./panels/FeedPanel";
import NavigatorPanel from "./panels/NavigatorPanel";
import ResultsPanel from "./panels/ResultsPanel";
import ScenePanel from "./panels/ScenePanel";
import { useViewer, type ViewId } from "./store/viewer";
import ChainPanel from "./panels/ChainPanel";
import LogPanel from "./panels/LogPanel";
import AccessTab from "./tabs/AccessTab";
import AgentsTab from "./tabs/AgentsTab";
import BoardTab from "./tabs/BoardTab";
import TaskTab from "./tabs/TaskTab";

/**
 * The shell, and nothing else.
 *
 * Five regions in a fixed arrangement: the control panel down the left, the run navigator
 * beside it, agent state top-right, and the feed and results side by side beneath it.
 *
 *   ┌──────────────┬───────────┬──────────────────────────────┐
 *   │              │           │   ChainPanel   (agent state) │
 *   │ ControlPanel │ Navigator ├──────────────┬───────────────┤
 *   │   (left)     │  (tree)   │  FeedPanel   │ ResultsPanel  │
 *   └──────────────┴───────────┴──────────────┴───────────────┘
 *
 * Only the top-right region swaps. The feed and the results are always on screen, which
 * is the point of the layout: the feed keeps running while you read the access map.
 *
 * The navigator is a column rather than a view for the same reason — it says where you are
 * in the run, which is a question you have *while* looking at something else. It is
 * closable from the rail, because three columns beside the main area is a lot of width to
 * spend on a laptop, and `navOpen` in the store is where that choice lives.
 *
 * This file owns three things and no UI logic: the grid, the tooltip provider, and the
 * poller's lifecycle. Every panel reads the store for itself, so there is nothing to
 * pass down.
 */

/** The views that borrow the top-right slot. Three are absent because they bring their
 *  own chrome: `chain` and `scene` each own a React Flow canvas, and `log` owns a scroll
 *  region it has to control itself in order to follow the end. The rest are bodies that
 *  this file frames. */
const SECONDARY: Record<Exclude<ViewId, "chain" | "scene" | "log">, ComponentType> = {
  board: BoardTab,
  task: TaskTab,
  agents: AgentsTab,
  access: AccessTab,
};

function TopRegion() {
  const view = useViewer((s) => s.view);
  const snapshot = useViewer((s) => s.snapshot);

  if (view === "chain") return <ChainPanel />;
  if (view === "scene") return <ScenePanel />;
  if (view === "log") return <LogPanel />;

  const meta = VIEWS[view];
  const Body = SECONDARY[view];
  return (
    <Panel icon={meta.icon} title={meta.label} count={snapshot ? meta.count?.(snapshot) : undefined}>
      <Body />
    </Panel>
  );
}

export default function App() {
  const start = useViewer((s) => s.start);
  const stop = useViewer((s) => s.stop);
  const navOpen = useViewer((s) => s.navOpen);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  return (
    <Tooltip.Provider delayDuration={200}>
      {/* Above `lg` the page itself never scrolls — each panel scrolls inside its own
          body. Below it the regions stack and the page scrolls normally, because three
          columns on a narrow screen is four unreadable slivers. */}
      <div className="h-full overflow-y-auto lg:overflow-hidden">
        <div
          className={cn(
            "grid min-h-full gap-3 p-3 lg:h-full",
            navOpen ? "lg:grid-cols-[auto_auto_minmax(0,1fr)]" : "lg:grid-cols-[auto_minmax(0,1fr)]",
          )}
        >
          <ControlPanel />

          {/* Stacked, below `lg`, it is a full-width band like every other region; the
              height floor is what stops it collapsing to its header there. */}
          {navOpen && (
            <div className="grid min-h-[16rem] min-w-0 lg:min-h-0 lg:w-64">
              <NavigatorPanel />
            </div>
          )}

          <div className="grid min-h-0 min-w-0 gap-3 lg:grid-rows-[minmax(0,58fr)_minmax(0,42fr)]">
            {/* The stacked layout has no row heights to divide up, so each region needs a
                floor of its own — without one, ScenePanel's React Flow canvas measures
                its container at zero and draws nothing at all. */}
            <div className="grid min-h-[28rem] min-w-0 lg:min-h-0">
              <TopRegion />
            </div>

            <div className="grid min-h-0 min-w-0 gap-3 xl:grid-cols-2">
              <div className="grid min-h-[22rem] min-w-0 lg:min-h-0">
                <FeedPanel />
              </div>
              <div className="grid min-h-[22rem] min-w-0 lg:min-h-0">
                <ResultsPanel />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Tooltip.Provider>
  );
}
