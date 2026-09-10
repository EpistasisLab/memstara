import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, type ComponentType } from "react";
import Panel from "./components/Panel";
import WindowWorkspace from "./components/WindowWorkspace";
import ThemeToggle from "./components/ThemeToggle";
import { VIEWS } from "./lib/views";
import ControlPanel from "./panels/ControlPanel";
import FeedPanel from "./panels/FeedPanel";
import NavigatorPanel from "./panels/NavigatorPanel";
import ResultsPanel from "./panels/ResultsPanel";
import ScenePanel from "./panels/ScenePanel";
import { useViewer, type ViewId } from "./store/viewer";
import ChainPanel from "./panels/ChainPanel";
import AgentConfigPanel from "./panels/AgentConfigPanel";
import LogPanel from "./panels/LogPanel";
import ClinicianPanel from "./panels/ClinicianPanel";
import ReportPanel from "./panels/ReportPanel";
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
const SECONDARY: Record<Exclude<ViewId, "chain" | "scene" | "log" | "clinician">, ComponentType> = {
  report: ReportPanel,
  board: BoardTab,
  task: TaskTab,
  agents: AgentsTab,
  access: AccessTab,
};

function TopRegion() {
  const view = useViewer((s) => s.view);
  const snapshot = useViewer((s) => s.snapshot);

  if (view === "clinician") return <ClinicianPanel />;
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
  const view = useViewer((s) => s.view);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  if (view === "clinician") return <Tooltip.Provider delayDuration={200}><ThemeToggle /><ClinicianPanel /></Tooltip.Provider>;

  return <Tooltip.Provider delayDuration={200}>
    <ThemeToggle />
    <AgentConfigPanel />
    <WindowWorkspace items={[
      { id: "control", title: "Control", content: <ControlPanel /> },
      ...(navOpen ? [{ id: "navigation", title: "Navigation", content: <NavigatorPanel /> }] : []),
      { id: "pipeline", title: "Analysis", content: <TopRegion /> },
      { id: "feed", title: "Activity feed", content: <FeedPanel /> },
      { id: "results", title: "Results", content: <ResultsPanel /> },
    ]} />
  </Tooltip.Provider>;
}
