import { lazy, Suspense, useEffect, useState } from 'react';
import { MessageSquareText, Search, ArrowDownToLine, FileText, Lightbulb, Database, BrainCircuit, ScanSearch } from 'lucide-react';
import { useAgentConversation } from '../lib/useAgentConversation';
const ReportBody=lazy(()=>import('./ReportBody'));
const stageNames:Record<string,string>={hypothesis:'Hypothesis',question:'Question generation',data:'Data extraction',ml:'Machine learning',interpreter:'Interpretation',report:'Explanation'};
const icons:Record<string,typeof FileText>={hypothesis:Lightbulb,question:Lightbulb,data:Database,ml:BrainCircuit,interpreter:ScanSearch,report:FileText};
const time=(value:string|null)=>value?new Date(value).toLocaleString(): 'Time not recorded';
const preview=(text:string)=>text.replace(/[#*`>|]/g,'').replace(/\s+/g,' ').trim();
export default function AgentConversation({runTag,loop}:{runTag:string;loop:number|null}){
  const {data,error}=useAgentConversation(runTag,loop);
  const [query,setQuery]=useState('');const [stage,setStage]=useState('');const [kind,setKind]=useState('');
  const [selection,setSelection]=useState<{scope:string;id:string}|null>(null);
  const scope=`${runTag}:${loop}`;
  const messages=data?.messages??[];
  const filtered=messages.filter(m=>(!stage||m.stage===stage)&&(!kind||m.kind===kind)&&`${m.text} ${m.label} ${m.name}`.toLowerCase().includes(query.toLowerCase()));
  const selected=filtered.find(m=>selection?.scope===scope&&m.id===selection.id)??filtered.at(-1);
  useEffect(()=>{if(selected&&(selection?.scope!==scope||selection.id!==selected.id))setSelection({scope,id:selected.id});},[scope,selected?.id,selection]);
  const latest=filtered.at(-1);const Icon=icons[selected?.stage??'']??MessageSquareText;
  return <section className="agent-reader" aria-label="Agent output reader">
    <header className="agent-reader-heading"><div><h3>Inside the agents’ work</h3><p>Read the notes and answers recorded by each agent. New saved outputs refresh automatically.</p></div><span className="agent-reader-count">{messages.length} recorded outputs</span></header>
    {error&&<p role="alert" className="agent-reader-notice">{error}{data?' Showing the last available messages.':''}</p>}
    <div className="agent-reader-tools"><label className="agent-reader-search"><Search size={17} aria-hidden="true"/><input aria-label="Search agent outputs" placeholder="Search the full text of outputs…" value={query} onChange={e=>setQuery(e.target.value)}/></label><select aria-label="Filter outputs by agent" value={stage} onChange={e=>setStage(e.target.value)}><option value="">All agents</option>{[...new Set(messages.map(m=>m.stage))].map(s=><option key={s} value={s}>{stageNames[s]??s}</option>)}</select><select aria-label="Filter output type" value={kind} onChange={e=>setKind(e.target.value)}><option value="">All output types</option>{[...new Map(messages.map(m=>[m.kind,m.kind_label])).entries()].map(([k,label])=><option key={k} value={k}>{label}</option>)}</select></div>
    {!data?<p className="agent-reader-empty" role="status">Loading recorded agent outputs…</p>:!filtered.length?<div className="agent-reader-empty"><MessageSquareText size={30}/><h4>{messages.length?'No matching outputs':'No agent text recorded yet'}</h4><p>{messages.length?'Try another search or filter.':'Outputs appear here when agents save their notes or answers for this scope.'}</p>{messages.length>0&&<button onClick={()=>{setQuery('');setStage('');setKind('');}}>Clear filters</button>}</div>:<div className="agent-reader-layout">
      <nav className="agent-reader-list" aria-label="Recorded agent outputs"><div className="agent-reader-list-heading">{filtered.length} outputs · newest first</div>{[...filtered].reverse().map(m=>{const ItemIcon=icons[m.stage]??MessageSquareText;return <button key={m.id} aria-current={selected?.id===m.id?'true':undefined} className="agent-reader-item" onClick={()=>setSelection({scope,id:m.id})}><span className="agent-reader-item-top"><ItemIcon size={17}/><strong>{stageNames[m.stage]??m.stage}</strong><span>{m.loop===null?'Execution':`Loop ${m.loop}`}</span></span><span className="agent-reader-item-kind">{m.kind_label}</span><span className="agent-reader-preview">{preview(m.text)}</span><time dateTime={m.at??undefined}>{time(m.at)}</time></button>})}</nav>
      {selected&&<article className="agent-reader-document" key={selected.id}><header><div className="agent-reader-document-title"><span className="agent-reader-icon"><Icon size={24}/></span><div><span className="agent-reader-eyebrow">{selected.loop===null?'Execution-wide':`Loop ${selected.loop}`} · {selected.kind_label}</span><h4>{stageNames[selected.stage]??selected.stage}</h4></div></div><p>{selected.label||selected.name} · {time(selected.at)}</p>{latest&&latest.id!==selected.id&&<button className="agent-reader-latest" onClick={()=>setSelection({scope,id:latest.id})}><ArrowDownToLine size={15}/> Go to latest output</button>}</header><div className="agent-reader-body"><Suspense fallback={<p>Preparing output…</p>}><ReportBody origin="mixed" text={selected.text}/></Suspense></div>{selected.truncated&&<p className="agent-reader-notice">This output is limited to the first 50,000 characters.</p>}<footer>Original agent output · Tool calls are listed in Activity.</footer></article>}
    </div>}
    {data?.limited&&<p className="agent-reader-notice">{data.note || 'Showing outputs from up to 200 recent records.'}</p>}
  </section>;
}
