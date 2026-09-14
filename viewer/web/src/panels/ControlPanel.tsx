import Help from "../components/Help";
import { usePipelines } from "../store/pipelines";
import { Compass } from "lucide-react";
import { cn } from "../lib/cn";
import { VIEWS, VIEW_ORDER } from "../lib/views";
import { useViewer } from "../store/viewer";

/** View navigation only; configuration lives beside its pipeline or resource. */
export default function ControlPanel() {
  const view=useViewer(s=>s.view),setView=useViewer(s=>s.setView);
  const snapshot=useViewer(s=>s.snapshot);
  const navOpen=useViewer(s=>s.navOpen),toggleNav=useViewer(s=>s.toggleNav);
  const pipelineCount=usePipelines(s=>s.items.length);
  const collapsed=false;
  const wide=undefined;
  return <aside className="h-full min-h-0 overflow-y-auto rounded-xl bg-paper-panel" aria-label="View navigation">
        <nav className="flex flex-col gap-1 p-3">
          <span
            className={cn(
              "px-1 pb-1 text-[12px] font-bold uppercase tracking-wider text-ink-faint",
              wide,
            )}
          >
            View
          </span>

          {VIEW_ORDER.map((id) => {
            const item = VIEWS[id];
            const active = view === id;
            const count = id === "chain" || id === "scene" ? pipelineCount : snapshot ? item.count?.(snapshot) : undefined;
            const button = (
              <button
                type="button"
                onClick={() => setView(id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-3 text-sm transition",
                  collapsed && "lg:justify-center",
                  active
                    ? "bg-accent font-bold text-accent-contrast"
                    : "text-ink-soft hover:bg-paper hover:text-ink",
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                <span className={cn("whitespace-normal text-left", wide)}>{item.label}</span>
                {count !== undefined && (
                  <span
                    className={cn(
                      "ml-auto shrink-0 font-mono text-[12px]",
                      active ? "text-accent-contrast" : "text-ink-faint",
                      wide,
                    )}
                  >
                    {count}
                  </span>
                )}
              </button>
            );

            return <Help key={id} topic={item.label}>{button}</Help>;
          })}

          {/* Not a view. The navigator is a column of its own that stays beside whichever
              view is showing, so it toggles rather than selects — putting it in the list
              above would make it look like a seventh thing that replaces the others. */}
          <Help topic="Navigator"><button
            type="button"
            onClick={toggleNav}
            aria-pressed={navOpen}
            title="Show or hide the pipeline overview"
            className={cn(
              "mt-1 flex w-full items-center gap-2 rounded-md border border-paper-line px-2",
              "py-1.5 text-sm transition",
              collapsed && "lg:justify-center",
              navOpen ? "text-ink" : "text-ink-faint hover:text-ink",
            )}
          >
            <Compass className="h-4 w-4 shrink-0" />
            <span className={cn("whitespace-normal text-left", wide)}>Exploration overview</span>
            <span className={cn("ml-auto shrink-0 text-[12px] text-ink-faint", wide)}>
              {navOpen ? "on" : "off"}
            </span>
          </button></Help>
        </nav>
  </aside>;
}
