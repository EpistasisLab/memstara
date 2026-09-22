import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, lazy, Suspense, type ComponentType } from "react";
import Panel from "./components/Panel";
import WindowWorkspace from "./components/WindowWorkspace";
import { VIEWS } from "./lib/views";
import ControlPanel from "./panels/ControlPanel";
import PipelineWorkspace, { PipelineStatus, PipelineOverview } from "./panels/PipelineWorkspace";
const DiscoveryPanel = lazy(() => import("./panels/DiscoveryPanel"));
import TelemetryPanel from "./panels/TelemetryPanel";
import { usePipelines } from "./store/pipelines";
import { useViewer, type ViewId } from "./store/viewer";
import PipelineCreationDialog from "./panels/PipelineCreationDialog";
import AgentConfigPanel from "./panels/AgentConfigPanel";
import LogPanel from "./panels/LogPanel";
import ClinicianPanel from "./panels/ClinicianPanel";
import ReportPanel from "./panels/ReportPanel";
import FeedPanel from "./panels/FeedPanel";
import ResultsPanel from "./panels/ResultsPanel";
import AccessTab from "./tabs/AccessTab";
import BoardTab from "./tabs/BoardTab";
import TaskTab from "./tabs/TaskTab";
import WorkspaceActions from "./components/WorkspaceActions";
import { useLiveOutputs } from "./store/liveOutputs";
import { useControl } from "./store/control";

/**
 * Preserve the existing resizable workspace and shared editors.
 * reviewer's Floor Plan contains independently owned pipeline rows and their Status view.
 * Reports follow the selected run; technical panels remain accessible in Telemetry.
 */
const SECONDARY: Record<Exclude<ViewId, "chain" | "scene" | "log" | "clinician">, ComponentType> = {
  discovery: DiscoveryPanel,
  report: ReportPanel,
  board: BoardTab,
  task: TaskTab,
  agents: TelemetryPanel,
  access: AccessTab,
};

function TopRegion() {
  const view = useViewer((s) => s.view);
  const snapshot = useViewer((s) => s.snapshot);

  if (view === "clinician") return <ClinicianPanel />;
  if (view === "chain") return <div className="h-full overflow-auto"><PipelineStatus /></div>;
  if (view === "scene") return <PipelineWorkspace />;
  if (view === "log") return <LogPanel />;

  const meta = VIEWS[view];
  const Body = SECONDARY[view];
  return (
    <Panel icon={meta.icon} title={meta.label} count={snapshot ? meta.count?.(snapshot) : undefined}>
      <Suspense fallback={<p className="p-6 text-ink-soft">Loading view…</p>}><Body /></Suspense>
    </Panel>
  );
}

export default function App() {
  const start = useViewer((s) => s.start);
  const stop = useViewer((s) => s.stop);
  const navOpen = useViewer((s) => s.navOpen);
  const view = useViewer((s) => s.view);
  useEffect(() => {
    void useLiveOutputs.getState().poll();
    const timer = setInterval(() => { void useLiveOutputs.getState().poll(); }, 3000);
    return () => clearInterval(timer);
  }, []);
  const pipeline = usePipelines(s => s.items.find(p => p.id === s.selected));

  useEffect(() => {
    const poll=()=>{if(!document.hidden)void useControl.getState().poll();};
    poll();const timer=setInterval(poll,2000);return()=>clearInterval(timer);
  },[]);

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  useEffect(() => {
    const poll = () => { if (!document.hidden) void usePipelines.getState().poll(); };
    poll(); const timer = setInterval(poll, 2500); return () => clearInterval(timer);
  }, []);

  return <Tooltip.Provider delayDuration={200}>
    <AgentConfigPanel />
    <PipelineCreationDialog />
    <WindowWorkspace toolbar={<WorkspaceActions only="history"/>} items={[
      { id: "control", title: "Control", content: <ControlPanel /> },
      ...(navOpen ? [{ id: "navigation", title: "Exploration overview", content: <PipelineOverview /> }] : []),
      { id: "pipeline", title: `${VIEWS[view].label}${pipeline ? ` · ${pipeline.name} · Iteration ${pipeline.progress.iteration ?? "—"}` : ""}`, content: <TopRegion /> },
      { id: "feed", title: "Activity feed", content: <FeedPanel /> },
      { id: "results", title: "Results", content: <ResultsPanel /> },
      { id: "report", title: `Final Report${pipeline ? ` · ${pipeline.name}` : ""}`, content: <ReportPanel /> },
    ]} />
  </Tooltip.Provider>;
}
