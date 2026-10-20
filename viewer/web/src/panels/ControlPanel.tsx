import Help from "../components/Help";
import { cn } from "../lib/cn";
import { VIEWS, VIEW_ORDER } from "../lib/views";
import { useViewer } from "../store/viewer";

/** View navigation only; configuration lives beside its pipeline or resource. */
export default function ControlPanel() {
  const view=useViewer(s=>s.view),setView=useViewer(s=>s.setView);
  const collapsed=false;
  const wide=undefined;
  return <aside className="h-full min-h-0 overflow-y-auto rounded-xl bg-paper-panel" aria-label="View navigation">
        <nav className="flex flex-col gap-1 p-2">
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
            const button = (
              <button
                type="button"
                onClick={() => setView(id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm transition",
                  collapsed && "lg:justify-center",
                  active
                    ? "bg-accent font-bold text-accent-contrast"
                    : "text-ink-soft hover:bg-paper hover:text-ink",
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                <span className={cn("whitespace-normal text-left", wide)}>{item.label}</span>
              </button>
            );

            return <Help key={id} topic={item.label} description={item.description}>{button}</Help>;
          })}

        </nav>
  </aside>;
}
