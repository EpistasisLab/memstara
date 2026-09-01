import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

/**
 * The chrome every panel shares: a bordered card with a fixed header strip and a body
 * that scrolls **inside itself**.
 *
 * That last part is the reason this component exists rather than each panel styling its
 * own box. The scroll rule is `flex flex-col` on the card, `shrink-0` on the header and
 * `min-h-0 flex-1 overflow-auto` on the body. Get `min-h-0` wrong in one place and that
 * panel stops scrolling and pushes the whole layout taller instead — which, in a fixed
 * four-region screen, silently shoves the other three panels off the bottom. Written
 * once, it cannot be got wrong once per panel.
 */

export interface PanelProps {
  /** Set only when something needs to scroll to or point at this panel by name. */
  id?: string;
  icon: LucideIcon;
  title: string;
  /** How many rows the body holds. Shown beside the title so an empty panel reads as
   *  "nothing to show" rather than "still loading". */
  count?: number;
  /** The header's right-hand slot: a scope note, a warning, a live indicator. */
  status?: ReactNode;
  /** Applied to the scroll region. Pass `overflow-hidden p-0` for a panel that manages
   *  its own surface, such as the React Flow canvas. */
  bodyClassName?: string;
  children: ReactNode;
}

export default function Panel({
  id,
  icon: Icon,
  title,
  count,
  status,
  bodyClassName,
  children,
}: PanelProps) {
  return (
    <section
      id={id}
      className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border
                 border-paper-line bg-paper-panel shadow-sm"
    >
      <header
        className="flex shrink-0 items-center gap-2 border-b border-paper-line
                   bg-paper-panel/95 px-4 py-2.5 backdrop-blur"
      >
        <Icon className="h-4 w-4 shrink-0 text-ink-soft" strokeWidth={2.2} />
        <h2 className="truncate text-sm font-bold tracking-tight">{title}</h2>
        {count !== undefined && (
          <span className="shrink-0 rounded-full bg-paper px-2 py-0.5 font-mono text-[11px] text-ink-soft">
            {count}
          </span>
        )}
        {status !== undefined && (
          <div className="ml-auto flex shrink-0 items-center gap-2 text-[11px] text-ink-faint">
            {status}
          </div>
        )}
      </header>

      <div className={cn("min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}
