import Help from "../components/Help";
import { cn } from "../lib/cn";
import { VIEWS, VIEW_ORDER } from "../lib/views";
import { useViewer } from "../store/viewer";
import ResultsNavigationButton from '../components/ResultsNavigationButton';

/** View navigation only; configuration lives beside its pipeline or resource. */
export default function ControlPanel() {
  const view=useViewer(s=>s.view),setView=useViewer(s=>s.setView);
  return <aside className="h-full min-h-0 overflow-y-auto rounded-xl bg-paper-panel" aria-label="View navigation">
        <nav className="flex flex-col gap-1 p-2 max-[760px]:flex-row max-[760px]:overflow-x-auto max-[760px]:overscroll-x-contain">
          <span className="px-1 pb-1 text-[12px] font-bold uppercase tracking-wider text-ink-faint max-[760px]:hidden">
            View
          </span>

          {VIEW_ORDER.map((id) => {
            const item = VIEWS[id];
            const active = view === id;
            const className = cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition max-[760px]:w-auto max-[760px]:shrink-0",
              active ? "bg-accent font-bold text-accent-contrast" : "text-ink-soft hover:bg-paper hover:text-ink",
            );
            if (id === 'results') return <ResultsNavigationButton key={id} active={active} className={className} open={() => setView(id)} />;
            const button = (
              <button
                type="button"
                onClick={() => setView(id)}
                aria-current={active ? "page" : undefined}
                className={className}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                <span className="whitespace-normal text-left max-[760px]:whitespace-nowrap">{item.label}</span>
              </button>
            );

            return <Help key={id} topic={item.label} description={item.description}>{button}</Help>;
          })}

        </nav>
  </aside>;
}
