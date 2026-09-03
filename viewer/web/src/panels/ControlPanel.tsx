import * as Tooltip from "@radix-ui/react-tooltip";
import { Activity, Compass, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "../lib/cn";
import { VIEWS, VIEW_ORDER } from "../lib/views";
import { useControl } from "../store/control";
import { POLL_MS, useHealth, useViewer } from "../store/viewer";
import StartRun from "./StartRun";

/**
 * The control panel — the left column, and the only place on screen that *changes*
 * anything.
 *
 * It owns three decisions and nothing else: which run is being looked at, which view
 * fills the top-right slot, and how wide this rail is. Everything else here is status:
 * the three health dots and the poll counter. Those are not decoration. A database being
 * down and a poller being stuck both look exactly like a quiet system unless the screen
 * says otherwise, so this panel says so.
 *
 * Starting a run is `StartRun`, in its own file. It is the one control here that changes
 * something outside the browser, and it talks to a different service — see
 * `store/control.ts` for why that is a second process rather than a route on `/api/`.
 *
 * Note what is *not* in the nav: Results. `ResultsPanel` is permanently on screen at
 * bottom-right, so a nav entry for it would be a second door to a room that is already
 * open. See `ViewId` in store/viewer.ts.
 *
 * Collapsing is a `lg`-only affordance: below that width the panel is a full-width band
 * stacked above the rest, where an icon rail would save nothing. So the collapsed state
 * hides text with `lg:hidden` rather than by not rendering it — otherwise collapsing on
 * a wide screen and then narrowing it would leave unlabelled icons and no way back.
 */

/** A store being down is shown, never hidden — a viewer that quietly drops half its
 *  data is worse than one that says which half is missing. */
function HealthDot({ up, label, error }: { up: boolean; label: string; error: string }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <span className="flex cursor-default items-center gap-1.5">
          <span
            className={cn(
              "h-2 w-2 shrink-0 rounded-full",
              up ? "bg-emerald-500" : "animate-pulse bg-red-500",
            )}
          />
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

export default function ControlPanel() {
  const view = useViewer((s) => s.view);
  const setView = useViewer((s) => s.setView);
  const runTag = useViewer((s) => s.runTag);
  const setRunTag = useViewer((s) => s.setRunTag);
  const snapshot = useViewer((s) => s.snapshot);
  const error = useViewer((s) => s.error);
  const ticks = useViewer((s) => s.ticks);
  const collapsed = useViewer((s) => s.railCollapsed);
  const toggleRail = useViewer((s) => s.toggleRail);
  const navOpen = useViewer((s) => s.navOpen);
  const toggleNav = useViewer((s) => s.toggleNav);
  const health = useHealth();
  const controlUp = useControl((s) => s.up);

  /** Hidden only once the rail is narrow, which only happens at `lg` and up. */
  const wide = collapsed ? "lg:hidden" : undefined;

  return (
    <aside
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-xl border border-paper-line",
        "bg-paper-panel shadow-sm transition-[width] duration-200",
        collapsed ? "lg:w-14" : "lg:w-60",
      )}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-paper-line px-3 py-2.5">
        <Activity className="h-5 w-5 shrink-0" strokeWidth={2.2} />
        <h1 className={cn("truncate text-sm font-bold tracking-tight", wide)}>Memstara Viewer</h1>
        <button
          type="button"
          onClick={toggleRail}
          aria-label={collapsed ? "Expand the control panel" : "Collapse the control panel"}
          className="ml-auto hidden shrink-0 rounded-md p-1 text-ink-faint hover:bg-paper
                     hover:text-ink lg:block"
        >
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <section className={cn("border-b border-paper-line px-3 py-3", wide)}>
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-ink-faint">
              Run
            </span>
            <select
              value={runTag ?? ""}
              onChange={(e) => setRunTag(e.target.value || null)}
              className="mt-1 w-full rounded-md border border-paper-line bg-white px-2 py-1
                         font-mono text-xs focus:border-ink focus:outline-none"
            >
              {(snapshot?.runs ?? []).map((r) => (
                <option key={r.run_tag} value={r.run_tag}>
                  {r.run_tag} — {r.tasks} tasks · {r.done} done
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className={cn("border-b border-paper-line px-3 py-3", wide)}>
          <StartRun />
        </section>

        <nav className="flex flex-col gap-0.5 p-2">
          <span
            className={cn(
              "px-1 pb-1 text-[11px] font-bold uppercase tracking-wider text-ink-faint",
              wide,
            )}
          >
            View
          </span>

          {VIEW_ORDER.map((id) => {
            const item = VIEWS[id];
            const active = view === id;
            const count = snapshot ? item.count?.(snapshot) : undefined;
            const button = (
              <button
                type="button"
                onClick={() => setView(id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition",
                  collapsed && "lg:justify-center",
                  active
                    ? "bg-ink font-bold text-white"
                    : "text-ink-soft hover:bg-paper hover:text-ink",
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                <span className={cn("truncate", wide)}>{item.label}</span>
                {count !== undefined && (
                  <span
                    className={cn(
                      "ml-auto shrink-0 font-mono text-[11px]",
                      active ? "text-white/70" : "text-ink-faint",
                      wide,
                    )}
                  >
                    {count}
                  </span>
                )}
              </button>
            );

            // Once the rail is icons only, the label has to live somewhere or it becomes
            // a guessing game.
            return collapsed ? (
              <Tooltip.Root key={id}>
                <Tooltip.Trigger asChild>{button}</Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content
                    side="right"
                    sideOffset={6}
                    className="rounded-md bg-ink px-2.5 py-1.5 text-xs text-white shadow-lg"
                  >
                    {item.label}
                    <Tooltip.Arrow className="fill-ink" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            ) : (
              <div key={id}>{button}</div>
            );
          })}

          {/* Not a view. The navigator is a column of its own that stays beside whichever
              view is showing, so it toggles rather than selects — putting it in the list
              above would make it look like a seventh thing that replaces the others. */}
          <button
            type="button"
            onClick={toggleNav}
            aria-pressed={navOpen}
            title="Show or hide the run navigator"
            className={cn(
              "mt-1 flex w-full items-center gap-2 rounded-md border border-paper-line px-2",
              "py-1.5 text-sm transition",
              collapsed && "lg:justify-center",
              navOpen ? "text-ink" : "text-ink-faint hover:text-ink",
            )}
          >
            <Compass className="h-4 w-4 shrink-0" />
            <span className={cn("truncate", wide)}>Navigator</span>
            <span className={cn("ml-auto shrink-0 text-[11px] text-ink-faint", wide)}>
              {navOpen ? "on" : "off"}
            </span>
          </button>
        </nav>
      </div>

      <footer
        className={cn(
          "shrink-0 space-y-1.5 border-t border-paper-line px-3 py-2.5 text-[11px]",
          collapsed && "lg:flex lg:flex-col lg:items-center lg:gap-2 lg:space-y-0 lg:px-0",
        )}
      >
        {health && (
          <div className={cn("flex gap-3", collapsed && "lg:flex-col lg:gap-2")}>
            <HealthDot up={health.memstara.up} label="memstara" error={health.memstara.error} />
            <HealthDot up={health.core.up} label="core" error={health.core.error} />
            {/* The third dot is a different service from the other two, and the only one
                whose absence is normal: the viewer is complete without it, minus the
                ability to start anything. */}
            <HealthDot
              up={controlUp === true}
              label="control"
              error="Not running — `python -m memstara.control` on the host"
            />
          </div>
        )}

        {/* A frozen poller would otherwise look identical to a quiet system. */}
        {error ? (
          <div className="font-mono font-bold text-red-700">API lost</div>
        ) : (
          <div className="font-mono text-ink-faint">
            <span className={wide}>
              every {POLL_MS / 1000}s · {ticks} polls
            </span>
            {collapsed && <span className="hidden lg:inline">{ticks}</span>}
          </div>
        )}
      </footer>
    </aside>
  );
}
