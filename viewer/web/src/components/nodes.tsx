import { skillLabel } from '../lib/displayText';
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { STAGE_ICON, STORE_ICON } from "../lib/icons";
import { STAGE_COLOR, STATE_LABEL } from "../lib/stage";
import type { SceneAgent, Place } from "../types";
import Help from "./Help";

const hiddenHandle = "!h-1 !w-1 !border-0 !bg-transparent";

/** Architectural layers with selectable pipeline rows behind their stations. */
function ZoneNode({ data }: NodeProps) {
  const onSelect=data.onSelect as (()=>void)|undefined;
  return <div role={onSelect?"button":undefined} tabIndex={onSelect?0:undefined}
    aria-label={onSelect?`Select ${String(data.title)}`:undefined}
    aria-pressed={onSelect?Boolean(data.selected):undefined}
    onClick={event=>{if(onSelect){event.stopPropagation();onSelect();}}}
    onKeyDown={event=>{if(onSelect&&(event.key==="Enter"||event.key===" ")){event.preventDefault();event.stopPropagation();onSelect();}}}
    className={`floor-zone ${data.execution ? "floor-zone-execution" : "floor-zone-resource"} ${onSelect?"pointer-events-auto cursor-pointer":"pointer-events-none"} ${data.selected?"floor-zone-selected":""} rounded-2xl border border-slate-200/80 bg-white/50`}
    style={{ width: Number(data.width), height: Number(data.height),
      background: data.execution ? 'linear-gradient(135deg, #f1f5f9 0%, #fafbf9 70%)' : '#f9fafb' }}>
    <div className="flex items-center gap-3 px-5 py-3">
      <span className="text-[12px] font-bold uppercase tracking-[0.18em] text-slate-500">{String(data.title)}</span>
      <span className="h-px flex-1 bg-slate-200" />
      <span className="text-[12px] text-slate-400">{String(data.caption)}</span>
      {Boolean(data.execution)&&"percent" in data&&<span className="floor-stage-caption">{String(data.stageLabel)}</span>}

    </div>
    {Boolean(data.execution)&&"percent" in data&&<div className={`floor-progress-rail ${data.failed?"needs-attention":""}`}
      aria-label={`${String(data.title)} progress`} role="progressbar"
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={typeof data.percent==="number"?data.percent:undefined}
      aria-valuetext={`${String(data.stageLabel)} · ${String(data.loopLabel ?? "Pipeline — · Replicate —")}. Stage-based progress, not a time estimate.`}>
      <div className="floor-progress-track"/>
      {[0,1,2,3,4].map(index=><i key={index} className="floor-progress-stop" style={{left:`${index*25}%`}}/>)}
      {typeof data.stageIndex==="number"&&data.stageIndex>=0&&<div className={`floor-progress-cursor ${data.stageIndex>=4?"is-last-stage":""}`}
        style={{left:`${Math.min(4,data.stageIndex)*25}%`}}
        title="Current stage of this pipeline. Percentage uses five equal stages, not elapsed time.">
        <span className="floor-progress-orb">P{String(data.number)}</span>
        <span className="floor-progress-caption"><strong>{typeof data.percent==="number"?`${data.percent}%`:"—"}</strong><span>{String(data.loopLabel ?? "Pipeline — · Replicate —")}</span></span>
      </div>}
    </div>}
  </div>;
}

export function PlaceNode({ data }: NodeProps) {
  const place = data.place as Place;
  const Icon = STORE_ICON[place.id];
  const activate=data.activate as (()=>void)|undefined;
  return <div role={activate?'button':undefined} tabIndex={activate?0:undefined} aria-label={activate?String(data.actionLabel):undefined}
    onClick={activate?event=>{event.stopPropagation();activate();}:undefined}
    onKeyDown={activate?event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate();}}:undefined}
    className={`floor-resource ${data.table?"floor-db-table":""} ${activate?'cursor-pointer':''} flex h-[76px] w-[152px] flex-col justify-between rounded-xl border border-slate-200 bg-white p-3 shadow-[0_2px_6px_rgba(15,23,42,0.04)] transition hover:border-slate-400 hover:shadow-md`}>
    <Handle type="target" position={Position.Bottom} className={hiddenHandle} />
    <div className="flex items-center gap-2">
      <div className="rounded-md border border-slate-100 bg-slate-50 p-1.5"><Icon size={14} className="text-slate-500" /></div>
      <span className="text-[12px] font-semibold leading-tight text-slate-700">{place.label}</span>
    </div>
    <span className="floor-resource-description text-[12px] text-slate-400" title={place.sub}>{place.sub}</span>
  </div>;
}

export function AgentNode({ data }: NodeProps) {
  const agent = data.agent as SceneAgent;
  const color = STAGE_COLOR[agent.stage];
  const busy = agent.state === "working";
  const planned = agent.state === "planned";
  const Icon = STAGE_ICON[agent.stage];
  const labels = { curator: 'Knowledge curator', hypothesis: `Hypothesis ${agent.slot + 1}`, data: 'Data', ml: 'Machine learning', interpreter: 'Interpreter', report: 'Explanation' };
  const summary = agent.playbook ? skillLabel(agent.playbook).replaceAll('-', ' ').replaceAll('_', ' ') : {
    curator: 'Review knowledge', hypothesis: 'Knowledge to hypothesis', data: 'Extract selected features', ml: 'Train & evaluate',
    interpreter: 'Explain the evidence', report: 'Synthesize findings',
  }[agent.stage];
  return <div
    className={`floor-agent ${data.guided ? "floor-agent-guided" : ""} ${busy ? "floor-agent-busy" : ""} ${data.selected ? "floor-agent-selected" : ""} relative h-[120px] w-[184px] overflow-hidden rounded-xl border bg-white transition hover:shadow-lg ${planned ? 'border-dashed' : ''}`}
    style={{ borderColor: busy ? color : '#dfe4e9', boxShadow: busy ? `0 0 0 3px color-mix(in srgb, ${color} 7%, transparent), 0 5px 18px color-mix(in srgb, ${color} 7%, transparent)` : '0 3px 10px #0f172a08' }}>
    <div className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color, opacity: planned ? .4 : 1 }} />
    <Handle type="target" position={Position.Left} className={hiddenHandle} />
    <Handle type="source" id="flow" position={Position.Right} className={hiddenHandle} />
    <Handle type="source" id="tool" position={Position.Top} className={hiddenHandle} />
    <div className="px-3 pt-3">
      <div className="flex items-center gap-2">
        <div className="floor-agent-glyph" aria-hidden="true" style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, borderColor:`color-mix(in srgb, ${color} 28%, transparent)`, color }}><Icon size={22} strokeWidth={1.8} /></div>
        <Help topic={agent.stage}><button type="button" className="min-w-0 flex-1 text-left text-[14px] font-bold leading-tight text-slate-700"
          aria-label={`Inspect ${labels[agent.stage]}`} onClick={event => { event.stopPropagation(); (data.inspect as (() => void))?.(); }}>{labels[agent.stage]}</button></Help>
      </div>
      <div className="mt-2 truncate text-[12px] text-slate-500" title={agent.playbook ? `Skill: ${skillLabel(agent.playbook)}` : summary}>{data.roleSummary ? String(data.roleSummary) : summary}</div>
    </div>
    <div className="absolute inset-x-0 bottom-0 flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-3 py-1.5 text-[12px]">
      <span className="flex items-center gap-1.5" style={{ color: busy ? color : 'rgb(var(--ink-soft))' }}>
        <span className={`h-1.5 w-1.5 rounded-full ${busy ? 'motion-safe:animate-pulse' : ''}`} style={{ background: busy ? color : agent.state === 'unknown' ? '#d97706' : '#cbd5e1' }} />
        {STATE_LABEL[agent.state]}
      </span>
      <span className="text-slate-400">{agent.carrying !== null ? `Task #${agent.carrying}` : agent.running > 1 ? `${agent.running} workers` : `0${Number(data.step)}`}</span>
    </div>
  </div>;
}

export const nodeTypes = { place: PlaceNode, agent: AgentNode, zone: ZoneNode };
