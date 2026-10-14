import { lazy, Suspense, useEffect, useState } from 'react';
import { agentDisplayName, TOOL_ACTIONS } from '../lib/telemetry';
import { Radio, ChevronDown, Search } from 'lucide-react';
import EmptyState from '../components/EmptyState';
import DetailPreview from '../components/DetailPreview';
import Panel from '../components/Panel';
import { useExecutionContext } from '../components/ExecutionContext';
import { STAGE_COLOR, STORE_LABEL } from '../lib/stage';
import { useFeed, useSnapshot } from '../store/viewer';
import { useAgentConversation, type AgentMessage } from '../lib/useAgentConversation';
import { matchesActivityStage } from '../lib/activityScope';
import type { FeedEvent } from '../types';

const ReportBody=lazy(()=>import('../components/ReportBody'));

function TextRow({message}:{message:AgentMessage}){
  const agent=agentDisplayName(message.label||message.name||message.stage);
  return <li className="telemetry-event" data-activity-kind="text"><details>
    <summary className="telemetry-event-summary">
      <span className="telemetry-event-dot" style={{backgroundColor:'rgb(var(--accent))'}}/>
      <span className="telemetry-event-content"><span className="telemetry-event-action">{message.kind_label||'Agent text'} · LLM output</span>
        <span className="telemetry-event-agent">{agent}</span>
        <span className="mt-1 line-clamp-2 whitespace-pre-wrap break-words text-sm text-ink">{message.text}</span>
      </span>
      <span className="telemetry-event-meta"><time dateTime={message.at??undefined}>{message.at?new Date(message.at).toLocaleTimeString():'Time unavailable'}</time><span>Read output <ChevronDown size={14}/></span></span>
    </summary>
    <div className="telemetry-event-details min-w-0"><p className="mb-3 text-xs text-ink-soft">Recorded agent text · {message.stage} · {message.loop===null?'Execution-wide':`Loop ${message.loop}`}. Agent statements do not by themselves confirm successful analysis.</p>
      <Suspense fallback={<p>Loading output…</p>}><ReportBody origin="mixed" text={message.text}/></Suspense>
      {message.truncated&&<p>Display limited to 50,000 characters.</p>}
    </div>
  </details></li>;
}

/** Activity records are scoped server-side. Never imply a call proves success. */
function Row({ event }: { event: FeedEvent }) {
  const action = TOOL_ACTIONS[event.tool] ?? event.tool;
  const agent = agentDisplayName(event.label ?? event.name ?? 'Unknown agent');
  const time = new Date(event.at).toLocaleString();
  const resource = STORE_LABEL[event.store] ?? event.store;
  const explanation = `${agent}: ${action}. Resource: ${resource}. Tool: ${event.tool}. Server: ${event.server}. Recorded ${time} (local time). Full agent identifier: ${event.name ?? 'Not recorded'}.`;
  return <li className="telemetry-event">
    <details>
      <DetailPreview title="Recorded activity" text={explanation}>
        <summary className="telemetry-event-summary">
          <span className="telemetry-event-dot" style={{backgroundColor: event.agent ? STAGE_COLOR[event.agent] : 'rgb(var(--ink-soft))'}} />
          <span className="telemetry-event-content">
            <span className="telemetry-event-action">{action}</span>
            <span className="telemetry-event-agent">{agent}</span>
            <span className="telemetry-event-resource">Resource: {resource}</span>
          </span>
          <span className="telemetry-event-meta"><time dateTime={event.at}>{new Date(event.at).toLocaleTimeString()}</time><span>Details <ChevronDown size={14}/></span></span>
        </summary>
      </DetailPreview>
      <div className="telemetry-event-details">
        <p>This is a recorded tool call. It does not by itself confirm that an analysis or loop completed.</p>
        <dl><dt>Action</dt><dd>{action}</dd><dt>Agent</dt><dd>{event.label ?? event.name ?? 'Unknown agent'}</dd>
          <dt>Agent identifier</dt><dd><code>{event.name || 'Not recorded'}</code></dd>
          <dt>Tool</dt><dd><code>{event.tool}</code></dd><dt>Service</dt><dd>{event.server}</dd>
          <dt>Resource</dt><dd>{resource}</dd><dt>Recorded at</dt><dd>{time} · local time</dd>
          <dt>Execution method</dt><dd>{event.path === 'supervisor' ? 'Legacy supervisor' : 'Pipeline task coordination'}</dd></dl>
      </div>
    </details>
  </li>;
}

export default function FeedPanel({stage, compact = false}: {stage?: string; compact?: boolean} = {}) {
  const feed = useFeed();
  const snapshot=useSnapshot();
  const loop=(snapshot as (typeof snapshot & {telemetry?:{loop:number|null}}))?.telemetry?.loop??null;
  const conversation=useAgentConversation(snapshot?.run_tag||null,loop);
  const context = useExecutionContext();
  const [query,setQuery] = useState('');
  const [agent,setAgent] = useState('');
  const [kind,setKind] = useState('all');
  const records=[...(feed??[]).map(event=>({kind:'tool' as const,key:event.key,at:event.at,name:event.name,label:event.label,event})),
    ...(conversation.data?.messages??[]).map(message=>({kind:'text' as const,key:`text:${message.id}`,at:message.at,name:message.name,label:message.label,message}))]
    .sort((a,b)=>(b.at?Date.parse(b.at):0)-(a.at?Date.parse(a.at):0)||a.key.localeCompare(b.key));
  useEffect(()=>{setQuery('');setAgent('');setKind('all');},[snapshot?.run_tag,loop,stage]);
  const scoped=records.filter(e=>matchesActivityStage(e.kind==='text'?e.message.stage:e.event.agent,stage,e.kind));
  const names=[...new Set(scoped.map(e=>e.name||'Unknown agent'))];
  const needle=compact?'':query.trim().toLowerCase();
  const activeAgent=!compact&&names.includes(agent)?agent:'';
  const activeKind=compact?'all':kind;
  const matching=scoped.filter(e=>(!activeAgent||(e.name||'Unknown agent')===activeAgent)&&
    (activeKind==='all'||e.kind===activeKind)&&[e.name,e.label,...(e.kind==='text'?[e.message.text,e.message.kind_label,e.message.stage]:[e.event.tool,e.event.server,STORE_LABEL[e.event.store],TOOL_ACTIONS[e.event.tool]])].join(' ').toLowerCase().includes(needle));
  return <Panel icon={Radio} title="Activity" bodyClassName="p-0">
    <div className="telemetry-activity-controls">
      {!compact&&stage==='question'&&<p className="text-sm">Question-generation tool calls share the Hypothesis agent identity. Related Hypothesis tool calls in this loop are included; agent text is restricted to question generation.</p>}
      {!compact&&<><p className="text-sm"><strong>{context.name}</strong> · {context.startedLabel} · {loop===null?'All loops':`Loop ${loop}`}</p>
      <p className="text-sm text-ink-soft">Tool actions and actual agent text, newest first. Expand an entry to read its full output. Text appears when recorded, rather than token by token.</p>
      <div className="telemetry-filter-row">
        <label><span><Search size={15}/>Search activity</span><input aria-label="Search activity" placeholder="Agent text, action, agent or resource" value={query} onChange={e=>setQuery(e.target.value)}/></label>
        <label><span>Agent</span><select aria-label="Filter activity by agent" value={names.includes(agent)?agent:''} onChange={e=>setAgent(e.target.value)}><option value="">All agents in this scope</option>{names.map(name=><option key={name} value={name}>{agentDisplayName(records.find(e=>e.name===name)?.label || name)}</option>)}</select></label>
        <label><span>Activity type</span><select aria-label="Filter activity by type" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">All activity</option><option value="tool">Tool actions</option><option value="text">Agent text</option></select></label>
      </div>
      </>}
      {conversation.error&&<p role="alert" className="text-sm text-ink-soft">{conversation.error}. Tool actions remain available.{conversation.data?' Showing last available text for this scope.':''}</p>}
      {!conversation.data&&!conversation.error&&snapshot?.run_tag&&<p className="text-xs text-ink-soft">Loading recorded agent text…</p>}
      {conversation.data?.limited&&<p className="text-xs text-ink-soft">{conversation.data.note || 'Agent text is limited to recent message-bearing steps.'}</p>}
      {!compact && feed && <p className="text-xs text-ink-soft">Showing {matching?.length ?? 0} of {scoped.length} recent records · times are local. This list is a recent window, not the full history for this scope.</p>}
    </div>
    {!feed&&!conversation.data ? <EmptyState what="the activity records"/> : !matching.length ? <div className="p-6 text-sm text-ink-soft">{!compact&&(needle || activeAgent || activeKind!=='all') ? <>No matching activity. <button className="underline" onClick={()=>{setQuery('');setAgent('');setKind('all');}}>Clear filters</button></> : 'No tool actions or agent text have been recorded for this scope yet.'}</div> : <ul aria-label="Recorded activities">{matching.map(e=>e.kind==='tool'?<Row key={e.key} event={e.event}/>:<TextRow key={e.key} message={e.message}/>)}</ul>}
  </Panel>;
}
