import * as Tabs from "@radix-ui/react-tabs";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Activity, Database, Layers, Map, ListTree, BarChart3, Boxes } from "lucide-react";
import { useEffect } from "react";
import Scene from "./components/Scene";
import AccessTab from "./tabs/AccessTab";
import AgentsTab from "./tabs/AgentsTab";
import BoardTab from "./tabs/BoardTab";
import ResultsTab from "./tabs/ResultsTab";
import TaskTab from "./tabs/TaskTab";
import { cn } from "./lib/cn";
import { POLL_MS, useViewer, type TabId } from "./store/viewer";

const TABS: { id: TabId; label: string; icon: typeof Map }[] = [
  { id: "scene", label: "Scene", icon: Map },
  { id: "board", label: "Board", icon: Layers },
  { id: "task", label: "Task life", icon: ListTree },
  { id: "agents", label: "Agents", icon: Boxes },
  { id: "access", label: "Access map", icon: Database },
  { id: "results", label: "Results", icon: BarChart3 },
];

/** A store being down is shown, never hidden — a viewer that quietly drops half its
 *  data is worse than one that says which half is missing. */
function HealthDot({ up, label, error }: { up: boolean; label: string; error: string }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <span className="flex cursor-default items-center gap-1.5">
          <span className={cn("h-2 w-2 rounded-full", up ? "bg-emerald-500" : "bg-red-500 animate-pulse")} />
          <span className={up ? "text-ink-soft" : "font-bold text-red-700"}>{label}</span>
        </span>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          sideOffset={6}
          className="max-w-sm rounded-md bg-ink px-2.5 py-1.5 text-xs text-white shadow-lg"
        >
          {up ? "Healthy" : error || "Not connected"}
          <Tooltip.Arrow className="fill-ink" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export default function App() {
  const { tab, setTab, runTag, setRunTag, snapshot, loading, error, ticks, start, stop } = useViewer();

  useEffect(() => {
    start();
    return stop;
  }, [start, stop]);

  const health = snapshot?.health;

  return (
    <Tooltip.Provider delayDuration={200}>
      <div className="min-h-full">
        <header className="sticky top-0 z-10 border-b border-paper-line bg-paper-panel/95 backdrop-blur">
          <div className="flex items-center gap-4 px-6 py-3">
            <h1 className="flex items-center gap-2 text-lg font-bold">
              <Activity className="h-5 w-5" strokeWidth={2.2} /> Memstara Viewer
            </h1>

            <label className="ml-4 flex items-center gap-2 text-sm">
              <span className="text-ink-faint">Run</span>
              <select
                value={runTag ?? ""}
                onChange={(e) => setRunTag(e.target.value || null)}
                className="rounded-md border border-paper-line bg-white px-2 py-1 font-mono text-xs
                           focus:border-ink focus:outline-none"
              >
                {(snapshot?.runs ?? []).map((r) => (
                  <option key={r.run_tag} value={r.run_tag}>
                    {r.run_tag} — {r.tasks} tasks · {r.done} done
                  </option>
                ))}
              </select>
            </label>

            <div className="ml-auto flex items-center gap-4 text-xs">
              {health && (
                <>
                  <HealthDot up={health.memstara.up} label="memstara" error={health.memstara.error} />
                  <HealthDot up={health.core.up} label="core" error={health.core.error} />
                </>
              )}
              {/* A frozen poller would otherwise look identical to a quiet system. */}
              <span className="font-mono text-ink-faint">
                {error ? <span className="font-bold text-red-700">API lost</span>
                       : `every ${POLL_MS / 1000}s · ${ticks} polls`}
              </span>
            </div>
          </div>

          <Tabs.Root value={tab} onValueChange={(v) => setTab(v as TabId)}>
            <Tabs.List className="flex gap-1 px-6">
              {TABS.map((t) => (
                <Tabs.Trigger
                  key={t.id}
                  value={t.id}
                  className={cn(
                    "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition",
                    "border-transparent text-ink-soft hover:text-ink",
                    "data-[state=active]:border-ink data-[state=active]:font-bold data-[state=active]:text-ink",
                  )}
                >
                  <t.icon className="h-3.5 w-3.5" /> {t.label}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
          </Tabs.Root>
        </header>

        <main>
          {loading && !snapshot ? (
            <div className="p-8 text-ink-faint">Loading for the first time…</div>
          ) : (
            <>
              {tab === "scene" && <Scene />}
              {tab === "board" && <BoardTab />}
              {tab === "task" && <TaskTab />}
              {tab === "agents" && <AgentsTab />}
              {tab === "access" && <AccessTab />}
              {tab === "results" && <ResultsTab />}
            </>
          )}
        </main>
      </div>
    </Tooltip.Provider>
  );
}
