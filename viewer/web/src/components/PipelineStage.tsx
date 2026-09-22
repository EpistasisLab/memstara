import type { NodeProps } from "@xyflow/react";

export default function PipelineStage({ data }: NodeProps) {
  const { title, purpose, color, height, step } = data as {
    title: string; purpose: string; color: string; count: number; height: number; step: number;
  };
  return <div className="pointer-events-none w-[312px] rounded-2xl border" style={{ height, borderColor: `color-mix(in srgb, ${color} 13%, transparent)`, background: `linear-gradient(180deg, color-mix(in srgb, ${color} 4%, transparent), color-mix(in srgb, ${color} 1%, transparent))` }}>
    <div className="flex items-center gap-2 border-b px-4 py-3" style={{ borderColor: `color-mix(in srgb, ${color} 9%, transparent)` }}>
      <span className="flex h-6 w-6 items-center justify-center rounded-md font-mono text-xs font-bold" style={{ color, background: `color-mix(in srgb, ${color} 7%, transparent)` }}>{step}</span>
      <div className="min-w-0 flex-1"><h3 className="text-sm font-bold" style={{ color }}>{title}</h3><p className="mt-0.5 text-[12px] text-ink-soft">{purpose}</p></div>
    </div>
  </div>;
}
