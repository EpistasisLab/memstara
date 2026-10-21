import {lazy,Suspense,useState} from 'react';
import {ChevronDown} from 'lucide-react';
import type {FeedEvent} from '../types';
import type {AgentMessage} from '../lib/useAgentConversation';
import {agentDisplayName,TOOL_ACTIONS} from '../lib/telemetry';
import {clinicalRoles} from '../lib/clinicalLog';
import './compact-activity.css';
const ReportBody=lazy(()=>import('./ReportBody'));
export default function CompactActivityRow({event,message}:{event?:FeedEvent;message?:AgentMessage}) {
 const [open,setOpen]=useState(false);
 const stage=event?.agent??message?.stage??'';
 const agent=clinicalRoles[stage]??agentDisplayName(event?.label||message?.label||event?.name||message?.name||'Unknown agent');
 const at=event?.at??message?.at;
 const validTime=at&&!Number.isNaN(Date.parse(at));
 // A recorded tool call or agent statement is not evidence of successful execution.
 const failed=!!message&&['error','failed','failure'].includes(message.kind);
 const action=event?(TOOL_ACTIONS[event.tool]??'Tool call recorded'):(failed?'Agent error':message?.kind_label||'Agent output');
 return <li className="compact-activity-row" data-error={failed||undefined}><details onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary><div className="compact-activity-meta"><span>{agent}</span><time dateTime={validTime?at!:undefined} title={validTime?new Date(at!).toLocaleString():undefined}>{validTime?new Date(at!).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}):'Time unavailable'}</time></div>
   <div className="compact-activity-title"><span>{action}</span><ChevronDown size={14} aria-hidden="true"/></div>
   <span className="compact-activity-state">{failed?'Error':event?'Call recorded':'Output recorded'}</span>
   {failed&&<p className="compact-activity-error">{message?.text.slice(0,200)}{(message?.text.length??0)>200?'…':''}</p>}
  </summary>
  {open&&<div className="compact-activity-detail">{event?<><p>Call recorded; completion is not confirmed by this record.</p><dl><dt>Tool</dt><dd>{event.tool}</dd><dt>Service</dt><dd>{event.server||'Not recorded'}</dd><dt>Agent</dt><dd>{event.name||agent}</dd></dl></>:<><Suspense fallback={<p>Loading output…</p>}><ReportBody origin="mixed" text={message?.text??''}/></Suspense>{message?.truncated&&<p>Saved excerpt; output was truncated.</p>}</>}</div>}
 </details></li>;
}
