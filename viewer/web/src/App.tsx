import InterfaceHelp from './components/InterfaceHelp';
import { pipelineLoopLabel } from "./lib/pipelineProgress";
import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, Suspense, type ComponentType } from "react";
import Panel from "./components/Panel";
import WindowWorkspace from "./components/WindowWorkspace";
import { VIEWS } from "./lib/views";
import ControlPanel from "./panels/ControlPanel";
import PipelineWorkspace, { PipelineStatus } from "./panels/PipelineWorkspace";
// Load with the application so an open tab cannot request a retired deployment chunk.
import DiscoveryPanel from "./panels/DiscoveryPanel";
import TelemetryPanel from "./panels/TelemetryPanel";
import { usePipelines } from "./store/pipelines";
import { useViewer, type ViewId } from "./store/viewer";
import PipelineCreationDialog from "./panels/PipelineCreationDialog";
import AgentConfigPanel from "./panels/AgentConfigPanel";
import LogPanel from "./panels/LogPanel";
import ClinicianPanel from "./panels/ClinicianPanel";
import ReportPanel from "./panels/ReportPanel";
import ResultsPanel from "./panels/ResultsPanel";
import AccessTab from "./tabs/AccessTab";
import BoardTab from "./tabs/BoardTab";
import TaskTab from "./tabs/TaskTab";
import WorkspaceActions from "./components/WorkspaceActions";
import { useLiveOutputs } from "./store/liveOutputs";
import { IDLE_REFRESH_MS, LIVE_REFRESH_MS, pollContinuously } from './lib/liveRefresh';
import { useControl } from "./store/control";


const SECONDARY: Record<Exclude<ViewId, "chain" | "scene" | "log" | "clinician" | "results">, ComponentType> = {
  discovery: DiscoveryPanel,
  report: ReportPanel,
  board: BoardTab,
  task: TaskTab,
  agents: TelemetryPanel,
  access: AccessTab,
};

function TopRegion() {
  const view = useViewer((s) => s.view);

  if (view === "clinician") return <ClinicianPanel />;
  if (view === "results") return <ResultsPanel embedded />;
  if (view === "chain") return <div className="h-full overflow-auto"><PipelineStatus /></div>;
  if (view === "scene") return <PipelineWorkspace />;
  if (view === "log") return <LogPanel />;

  const meta = VIEWS[view];
  const Body = SECONDARY[view];
  return (
    <Panel embedded icon={meta.icon} title={meta.label}>
      <Suspense fallback={<p className="p-6 text-ink-soft">Loading view…</p>}><Body /></Suspense>
    </Panel>
  );
}

export default function App() {
  const start = useViewer((s) => s.start);
  const stop = useViewer((s) => s.stop);
  const view = useViewer((s) => s.view);
  const liveRefreshScope = usePipelines(s => s.items.map(p => `${p.running ? 'active' : 'idle'}:${(p.running ?? p.latest)?.run_tag ?? ''}`).join(','));
  useEffect(() => {
    return pollContinuously(() => useLiveOutputs.getState().poll(), () =>
      usePipelines.getState().items.some(p => p.running) && !useLiveOutputs.getState().error ? LIVE_REFRESH_MS : IDLE_REFRESH_MS);
  }, [liveRefreshScope]);
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
    return pollContinuously(() => usePipelines.getState().poll(), () =>
      usePipelines.getState().error ? IDLE_REFRESH_MS : LIVE_REFRESH_MS);
  }, []);

  return <Tooltip.Provider delayDuration={200}>
    <InterfaceHelp />
    <AgentConfigPanel />
    <PipelineCreationDialog />
    <WindowWorkspace toolbar={<WorkspaceActions only="history"/>} items={[
      { id: "control", title: "Control", content: <ControlPanel /> },
      { id: "pipeline", title: `${VIEWS[view].label}${pipeline && view !== "discovery" ? ` · ${pipeline.name}${view === "agents" ? "" : ` · ${pipelineLoopLabel(pipeline)}`}` : ""}`, content: <TopRegion /> },
    ]} />
  </Tooltip.Provider>;
}
