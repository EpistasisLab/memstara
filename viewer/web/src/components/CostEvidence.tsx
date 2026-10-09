import {useEffect,useState} from 'react';
import {costLabel} from '../lib/loopUsage';
type Receipt={source:string;retrieved_at:string;rates:Record<string,number>;components_usd:Record<string,number>;catalog_sha256:string};
type Row={id:string;stage:string;loop:number|null;model:string;provider:string;usd:number|null;source:string;reason:string|null;prompt_tokens:number|null;completion_tokens:number|null;cache_read_input_tokens:number|null;cache_creation_input_tokens:number|null;price_receipt:Receipt|null};
type Evidence={run_tag:string;status:string;usd:number;recorded_calls:number;unpriced_calls:number;expected_calls:number;coverage_note:string;groups:{stage:string;model:string;calls:number;priced_calls:number;usd:number;input_tokens:number;output_tokens:number}[];records:Row[]};
type Azure={status:string;retrieved_at?:string;period?:{from:string;to:string};scope_type?:string;totals?:Record<string,number>;basis:string};
export default function CostEvidence({runTag}:{runTag:string|null}){
 const [data,setData]=useState<Evidence|null>(null),[azure,setAzure]=useState<Azure|null>(null),[error,setError]=useState('');
 useEffect(()=>{let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
 setData(null);setAzure(null);setError('');
 const poll=async()=>{controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),6000);
 try{const paths=['/api/azure-costs',...(runTag?[`/api/cost-details?run_tag=${encodeURIComponent(runTag)}`]:[])];
 const values=await Promise.all(paths.map(async path=>{const r=await fetch(path,{signal:controller.signal});if(!r.ok)throw Error('Cost evidence could not be refreshed');return r.json();}));
 if(!disposed){setAzure(values[0]);setData(values[1]??null);setError('');}}
 catch{if(!disposed)setError('Cost evidence could not be refreshed. Any displayed values are the last retrieved snapshot.');}
 finally{clearTimeout(deadline);if(!disposed)timer=setTimeout(poll,10000);}};
 void poll();return()=>{disposed=true;clearTimeout(timer);controller?.abort();};},[runTag]);
 const current=data?.run_tag===runTag?data:null;
 const download=()=>{if(!current)return;const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${current.run_tag}-cost-evidence.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 return <section className="space-y-3 rounded-lg border border-paper-line bg-paper p-3" aria-label="Cost evidence">
 <h3 className="font-bold">Cost details and Azure reconciliation</h3>
 {error&&<p role="alert" className="text-sm">{error}</p>}
 <p className="text-sm text-ink-soft">Token-based estimates and Azure-reported costs have different scopes. They are never added together.</p>
 <div className="rounded border border-paper-line p-3"><h4 className="font-bold">Azure reported cost</h4>
 {azure?.status==='retrieved'?<><p>{Object.entries(azure.totals??{}).map(([currency,value])=>`${currency} ${value.toFixed(4)}`).join(' · ')||'No cost rows returned; reporting may be delayed.'}</p><p className="text-xs">{azure.scope_type} · {azure.period?.from} to {azure.period?.to}<br/>Retrieved {azure.retrieved_at}</p></>:<p>Not connected / no synchronized billing data</p>}
 <p className="text-xs text-ink-soft">{azure?.basis??'Actual costs require Azure Cost Management read access. An inference API key is not billing access.'}</p></div>
 {runTag&&<div className="rounded border border-paper-line p-3"><h4 className="font-bold">Selected execution · actual Azure charge</h4><p>Unavailable — no execution-attributed billing evidence.</p><p className="text-xs text-ink-soft">The Azure total above covers its stated scope and period. It is not this execution's charge. Missing billing data is not zero, and token estimates cannot replace it.</p></div>}
 <details><summary className="cursor-pointer font-bold">Optional token estimates — not actual Azure charges</summary>
 {!runTag?<p>Select an execution to inspect its request costs.</p>:!current?<p>Loading selected execution cost evidence…</p>:<>
 <p className="font-bold">Selected execution estimate: {costLabel({usd:current.usd,status:current.status,missing_costs:current.unpriced_calls})}</p>
 <p className="text-sm">{current.recorded_calls} recorded attempts · {current.unpriced_calls} unpriced or unreadable records · {current.expected_calls} calls in execution records.</p>
 <p className="text-xs text-ink-soft">{current.coverage_note} Infrastructure, taxes and contract discounts are excluded from token estimates.</p>
 {current.records.length===0&&<p>This execution has no detailed cost ledger. Its historical estimates remain in the totals above; no prices have been retroactively invented.</p>}
 {current.groups.length>0&&<div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="text-left">Recorded attempts by agent and model</caption><thead><tr>{['Agent','Model','Priced / recorded','Input / output tokens','Estimated USD'].map(h=><th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{current.groups.map(g=><tr key={`${g.stage}/${g.model}`}><td className="p-2">{g.stage}</td><td className="p-2 break-all">{g.model}</td><td className="p-2">{g.priced_calls} / {g.calls}</td><td className="p-2">{g.input_tokens.toLocaleString()} / {g.output_tokens.toLocaleString()}</td><td className="p-2">{costLabel({usd:g.usd,status:g.priced_calls===g.calls?'complete':'partial'})}</td></tr>)}</tbody></table></div>}
 <details><summary className="cursor-pointer font-bold">Request amounts, token usage and pricing sources</summary>
 {current.records.map(r=><div key={r.id} className="my-2 break-words rounded border border-paper-line p-2 text-sm"><p>{r.stage} · {r.loop==null?'Execution-wide':`Loop ${r.loop}`} · {r.model} · {r.usd==null?'Unpriced':`USD ${r.usd.toFixed(6)} (estimate)`}</p><p>Input {r.prompt_tokens??'unknown'} · output {r.completion_tokens??'unknown'} · cache reads {r.cache_read_input_tokens??'unknown'} · cache writes {r.cache_creation_input_tokens??'unknown'}</p><p>Source: {r.source}. {r.reason}</p>
 {r.price_receipt?<><p>Price source: {r.price_receipt.source} · retrieved {r.price_receipt.retrieved_at}</p><p>USD per million tokens: {Object.entries(r.price_receipt.rates).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p><p>Calculated components: {Object.entries(r.price_receipt.components_usd).map(([k,v])=>`${k}: $${v.toFixed(6)}`).join(' · ')}</p></>:<p className="text-ink-soft">No deployment-specific rate receipt. Library/override estimates are not verified Azure contract prices.</p>}</div>)}</details>
 <button className="rounded border border-paper-line px-3 py-2 text-sm" onClick={download}>Download cost evidence (JSON)</button>
 </>}
 </details>
 </section>;
}
