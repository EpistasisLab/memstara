import { Handle, Position, type NodeProps } from "@xyflow/react";
import { STAGE_ICON, STORE_ICON } from "../lib/icons";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import type { SceneAgent, Place } from "../types";
import Help from "./Help";

const hiddenHandle = "!h-1 !w-1 !border-0 !bg-transparent";

/** Noninteractive architectural layers, behind the actual nodes and their edges. */
function ZoneNode({ data }: NodeProps) {
  return <div className={`floor-zone ${data.execution ? "floor-zone-execution" : ""} pointer-events-none rounded-2xl border border-slate-200/80 bg-white/50`}
    style={{ width: Number(data.width), height: Number(data.height),
      background: data.execution ? 'linear-gradient(135deg, #f1f5f9 0%, #fafbf9 70%)' : '#f9fafb' }}>
    <div className="flex items-center gap-3 px-5 py-3">
      <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">{String(data.title)}</span>
      <span className="h-px flex-1 bg-slate-200" />
      <span className="text-[10px] text-slate-400">{String(data.caption)}</span>
    </div>
  </div>;
}

export function PlaceNode({ data }: NodeProps) {
  const place = data.place as Place;
  const Icon = STORE_ICON[place.id];
  return <div className="floor-resource flex h-[76px] w-[152px] flex-col justify-between rounded-xl border border-slate-200 bg-white p-3 shadow-[0_2px_6px_rgba(15,23,42,0.04)] transition hover:border-slate-400 hover:shadow-md">
    <Handle type="target" position={Position.Bottom} className={hiddenHandle} />
    <div className="flex items-center gap-2">
      <div className="rounded-md border border-slate-100 bg-slate-50 p-1.5"><Icon size={14} className="text-slate-500" /></div>
      <span className="text-[12px] font-semibold leading-tight text-slate-700">{place.label}</span>
    </div>
    <span className="truncate text-[10px] text-slate-400" title={place.sub}>{place.sub}</span>
  </div>;
}

export function AgentNode({ data }: NodeProps) {
  const agent = data.agent as SceneAgent;
  const color = STAGE_COLOR[agent.stage];
  const busy = agent.state === "working";
  const planned = agent.state === "planned";
  const Icon = STAGE_ICON[agent.stage];
  const labels = { curator: 'Knowledge curator', hypothesis: `Hypothesis ${agent.slot + 1}`, data: 'Data', ml: 'Machine learning', interpreter: 'Interpreter', report: 'Report' };
  const summary = agent.playbook ? agent.playbook.replaceAll('-', ' ').replaceAll('_', ' ') : {
    curator: 'Review knowledge', hypothesis: 'Knowledge to hypothesis', data: 'Extract selected features', ml: 'Train & evaluate',
    interpreter: 'Explain the evidence', report: 'Synthesize findings',
  }[agent.stage];
  return <div
    className={`floor-agent ${busy ? "floor-agent-busy" : ""} ${data.selected ? "floor-agent-selected" : ""} relative h-[108px] w-[184px] overflow-hidden rounded-xl border bg-white transition hover:shadow-lg ${planned ? 'border-dashed' : ''}`}
    style={{ borderColor: busy ? color : '#dfe4e9', boxShadow: busy ? `0 0 0 3px color-mix(in srgb, ${color} 7%, transparent), 0 5px 18px color-mix(in srgb, ${color} 7%, transparent)` : '0 3px 10px #0f172a08' }}>
    <div className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color, opacity: planned ? .4 : 1 }} />
    <Handle type="target" position={Position.Left} className={hiddenHandle} />
    <Handle type="source" id="flow" position={Position.Right} className={hiddenHandle} />
    <Handle type="source" id="tool" position={Position.Top} className={hiddenHandle} />
    <div className="px-3 pt-3">
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `color-mix(in srgb, ${color} 7%, transparent)`, color }}><Icon size={17} /></div>
        <button type="button" className="min-w-0 flex-1 text-left text-[14px] font-bold leading-tight text-slate-700"
          aria-label={`Inspect ${labels[agent.stage]}`} onClick={event => { event.stopPropagation(); (data.inspect as (() => void))?.(); }}>{labels[agent.stage]}</button>
        <Help topic={agent.stage} />
      </div>
      <div className="mt-2 truncate text-[10px] text-slate-500" title={agent.playbook || summary}>{summary}</div>
    </div>
    <div className="absolute inset-x-0 bottom-0 flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-3 py-1.5 text-[10px]">
      <span className="flex items-center gap-1.5" style={{ color: busy ? color : '#64748b' }}>
        <span className={`h-1.5 w-1.5 rounded-full ${busy ? 'motion-safe:animate-pulse' : ''}`} style={{ background: busy ? color : agent.state === 'unknown' ? '#d97706' : '#cbd5e1' }} />
        {STATE_LABEL[agent.state]}
      </span>
      <span className="text-slate-400">{agent.carrying !== null ? `Task #${agent.carrying}` : agent.running > 1 ? `${agent.running} workers` : `0${Number(data.step)}`}</span>
    </div>
  </div>;
}

export const nodeTypes = { place: PlaceNode, agent: AgentNode, zone: ZoneNode };
