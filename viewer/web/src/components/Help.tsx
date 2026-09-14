import * as Tooltip from "@radix-ui/react-tooltip";
import { CircleHelp } from "lucide-react";
import { useState, type ReactElement } from "react";
import { HELP } from "../lib/help";

/** Hover, keyboard focus, or tap the help icon. Keep dialog help in its top layer. */
export default function Help({ topic, children }: { topic: string; children?: ReactElement }) {
  const [open, setOpen] = useState(false);
  const [host, setHost] = useState<HTMLSpanElement | null>(null);
  if (!HELP[topic]) return children ?? null;
  return <span ref={setHost} className="contents">
    <Tooltip.Root open={open} onOpenChange={setOpen} delayDuration={350}>
      <Tooltip.Trigger asChild>{children ?? <button type="button"
        aria-label={`Help: ${topic}`} onClick={e => { e.preventDefault(); e.stopPropagation(); setOpen(true); }}
        className="nodrag nopan inline-flex shrink-0 align-middle rounded p-0.5 text-ink-faint hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink">
        <CircleHelp size={16} aria-hidden="true" />
      </button>}</Tooltip.Trigger>
      <Tooltip.Portal container={host?.closest('dialog') ?? undefined}>
        <Tooltip.Content side="right" sideOffset={8} collisionPadding={12}
          className="z-[200] max-w-[min(20rem,calc(100vw-24px))] rounded-lg border border-paper-line bg-white px-3 py-2.5 text-sm font-normal normal-case leading-relaxed tracking-normal text-ink shadow-lg">
          <div className="mb-1 font-bold">{topic}</div>
          <div className="text-ink-soft">{HELP[topic]}</div>
          <Tooltip.Arrow className="fill-white" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  </span>;
}
