import {useLoopLabel} from '../lib/useLoopLabel';
import {useEffect,useState} from 'react';
import {costLabel} from '../lib/loopUsage';
type Row={id:string;stage:string;loop:number|null;model:string;provider:string;usd:number|null;source:string;reason:string|null;prompt_tokens:number|null;completion_tokens:number|null;cache_read_input_tokens:number|null;cache_creation_input_tokens:number|null};
type Evidence={run_tag:string;loop?:number|null;missing_runs?:number;status:string;usd:number;recorded_calls:number;unpriced_calls:number;expected_calls:number;coverage_note:string;groups:{stage:string;model:string;calls:number;priced_calls:number;usd:number;input_tokens:number;output_tokens:number}[];records:Row[]};
export default function CostEvidence({runTag,loop=null,refreshRevision=0}:{runTag:string|null;loop?:number|null;refreshRevision?:number}){
 const labelReplicate=useLoopLabel();
 const [data,setData]=useState<Evidence|null>(null),[error,setError]=useState('');
 useEffect(()=>{let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
 setError('');
 const poll=async()=>{controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),6000);
 try{const paths=runTag?[`/api/cost-details?run_tag=${encodeURIComponent(runTag)}${loop===null?'':`&loop=${loop}`}`]:[];
 const values=await Promise.all(paths.map(async path=>{const r=await fetch(path,{signal:controller.signal});if(!r.ok)throw Error('Cost evidence could not be refreshed');return r.json();}));
 if(!disposed){setData(values[0]??null);setError('');}}
 catch{if(!disposed)setError('Cost evidence could not be refreshed. Any displayed values are the last retrieved snapshot.');}
 finally{clearTimeout(deadline);if(!disposed)timer=setTimeout(poll,10000);}};
 void poll();return()=>{disposed=true;clearTimeout(timer);controller?.abort();};},[runTag,loop,refreshRevision]);
 const current=data?.run_tag===runTag&&(data.loop??null)===loop?data:null;
 const download=()=>{if(!current)return;const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${current.run_tag}${loop===null?'':`-loop-${loop}`}-cost-evidence.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 return <section className="tm-cost-evidence space-y-3 rounded-lg border border-paper-line bg-paper p-3" aria-label="Cost evidence">
 <h3 className="font-bold">Motoro cost details</h3>
 {error&&<p role="alert" className="text-sm">{error}</p>}
 <p className="text-sm text-ink-soft">All cost information comes from Motoro. Memstara does not query billing providers or substitute local estimates.</p>
 <div className="rounded border border-paper-line p-3"><h4 className="font-bold">Actual billed amount</h4><p>Not provided by Motoro.</p><p className="text-xs text-ink-soft">The current Motoro records contain estimates, not actual charges. Missing billing evidence is not zero.</p></div>
 <details><summary className="cursor-pointer font-bold">Estimated cost · Motoro LLM requests</summary>
 {!runTag?<p>Select an execution to inspect its request costs.</p>:!current?<p role="status">{error?'Cost evidence is temporarily unavailable. Retrying automatically.':'Loading selected execution cost evidence…'}</p>:<>
 <p className="font-bold">{loop===null?'Execution':labelReplicate({iteration:loop,run_tag:runTag})} LLM request subtotal: {costLabel({usd:current.usd,status:current.status,missing_costs:current.unpriced_calls})}</p>
 <p className="text-sm">{current.recorded_calls} recorded LLM requests · {current.unpriced_calls} unpriced or unreadable records.</p>
 <p className="text-xs text-ink-soft">This subtotal uses saved LLM request records. Overview uses agent execution totals; the two may differ if request records are incomplete.</p>
 {(current.missing_runs??0)>0&&<p>{current.missing_runs} agent executions have no saved LLM request evidence.</p>}
 <p className="text-xs text-ink-soft">{current.coverage_note} These records do not establish an actual billed amount.</p>
 {current.records.length===0&&<p>No persisted Motoro call-cost records are available for this execution. No local estimates are substituted.</p>}
 {current.groups.length>0&&<div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="text-left">Recorded LLM requests by agent and model</caption><thead><tr>{['Agent','Model','Priced / recorded requests','Input / output tokens','Estimated USD'].map(h=><th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{current.groups.map(g=><tr key={`${g.stage}/${g.model}`}><td className="p-2">{g.stage}</td><td className="p-2 break-all">{g.model}</td><td className="p-2">{g.priced_calls} / {g.calls}</td><td className="p-2">{g.input_tokens.toLocaleString()} / {g.output_tokens.toLocaleString()}</td><td className="p-2">{costLabel({usd:g.usd,status:g.priced_calls===g.calls?'complete':'partial'})}</td></tr>)}</tbody></table></div>}
 <details><summary className="cursor-pointer font-bold">Request amounts, token usage and pricing sources</summary>
 {current.records.map(r=><div key={r.id} className="my-2 break-words rounded border border-paper-line p-2 text-sm"><p>{r.stage} · {r.loop==null?'Execution-wide':labelReplicate({iteration:r.loop,run_tag:runTag})} · {r.model} · {r.usd==null?'Unpriced':`USD ${r.usd.toFixed(6)} (estimate)`}</p><p>Input {r.prompt_tokens??'unknown'} · output {r.completion_tokens??'unknown'} · cache reads {r.cache_read_input_tokens??'unknown'} · cache writes {r.cache_creation_input_tokens??'unknown'}</p><p>Motoro pricing source: {r.source??'Not recorded'}. {r.reason}</p>
</div>)}</details>
 <button className="rounded border border-paper-line px-3 py-2 text-sm" onClick={download}>Download cost evidence (JSON)</button>
 </>}
 </details>
 </section>;
}
