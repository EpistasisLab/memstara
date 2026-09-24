import { useState } from 'react';
import { MessageSquareText, Terminal } from 'lucide-react';
import AgentConversation from './AgentConversation';
import RunLog from './RunLog';
export default function ExecutionLogs({runTag,loop,lines,note}:{runTag:string;loop:number|null;lines:string[];note?:string|null}){
 const [view,setView]=useState<'outputs'|'console'>('outputs');
 return <div className="execution-logs"><div className="execution-log-switch" role="group" aria-label="Log content"><button aria-pressed={view==='outputs'} onClick={()=>setView('outputs')}><MessageSquareText size={17}/> Agent outputs</button><button aria-pressed={view==='console'} onClick={()=>setView('console')}><Terminal size={17}/> Console log</button></div>{view==='outputs'?<AgentConversation runTag={runTag} loop={loop}/>:<section className="p-4"><h3 className="font-bold">Pipeline console</h3><p className="mb-4 text-sm text-ink-soft">Technical execution messages for the selected pipeline and Loop scope.</p>{note&&<p className="mb-3 text-sm text-ink-soft">{note}</p>}{lines.length?<RunLog lines={lines} skipped={0} tail=""/>:<p>No attributable console messages are available for this scope.</p>}</section>}</div>;
}
