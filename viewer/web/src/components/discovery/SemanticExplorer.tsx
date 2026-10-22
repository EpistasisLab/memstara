import { displayJson } from '../../lib/displayText';
import {useEffect, useRef, useState} from 'react';
import {Search, ArrowUpRight, Network, LoaderCircle} from 'lucide-react';
import type {SemanticData} from '../../lib/semanticLayout';
export default function SemanticExplorer({selected, onLayout, onChoose, source='all'}: {
 source?:string; selected:number|null; onLayout:(data:SemanticData|null)=>void; onChoose:(id:number)=>void;
}) {
 const [data,setData]=useState<SemanticData|null>(null),[query,setQuery]=useState('');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 const request=useRef<AbortController|null>(null);
 useEffect(()=>()=>request.current?.abort(),[]);
 const load=async(neighbors=false, selectedOnly=false)=>{
  request.current?.abort();const controller=new AbortController();request.current=controller;
  setBusy(true);setError('');
  const params=new URLSearchParams({source});
  if(query.trim()&&!selectedOnly)params.set('query',query.trim());
  else if(neighbors&&selected!==null)params.set('question_id',String(selected));
  try {
   let response:Response;
   do {
    response=await fetch('/api/discovery/semantic?'+params,{signal:controller.signal});
    if(response.status===202)await new Promise<void>((resolve,reject)=>{
     const abort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
     const timer=setTimeout(()=>{controller.signal.removeEventListener('abort',abort);resolve();},2000);
     controller.signal.addEventListener('abort',abort,{once:true});
     if(controller.signal.aborted)abort();
    });
   }while(response.status===202&&!controller.signal.aborted);
   if(!response.ok)throw Error('Semantic view is unavailable. The regular question list remains available.');
   const result=await response.json() as SemanticData;
   if(!Array.isArray(result.points)||!Array.isArray(result.neighbors)||result.neighbors.some(n=>!Number.isSafeInteger(n.question_id)||!Number.isFinite(n.similarity)))throw Error('Invalid semantic index response.');
   if(controller.signal.aborted)return;
   setData(result);onLayout(result);
  }catch(e){if(!controller.signal.aborted)setError(String(e));}
  finally{if(!controller.signal.aborted)setBusy(false);}
 };
 return <section className="related-questions flex flex-col gap-5" aria-label="Semantic question explorer" aria-busy={busy}>
  <p className="related-intro">Find questions with similar meaning within the selected knowledge source.</p>
  <form onSubmit={e=>{e.preventDefault();if(query.trim())void load(true);}} className="related-search flex flex-col gap-3">
   <label htmlFor="semantic-query" className="text-sm font-medium">Research topic</label>
   <textarea id="semantic-query" aria-label="Semantic query" rows={3} value={query} maxLength={1000} onChange={e=>setQuery(e.target.value)} placeholder="Describe the question or topic you want to explore"/>
   <button className="related-primary inline-flex items-center justify-center gap-2" disabled={busy||!query.trim()} type="submit">{busy?<LoaderCircle size={16} className="animate-spin"/>:<Search size={16}/>}Search meaning</button>
  </form>
  {selected!==null&&<div className="related-selected flex flex-wrap items-center justify-between gap-3"><span>Selected question <strong>Q{selected}</strong></span><button disabled={busy} type="button" onClick={()=>{setQuery('');void load(true,true);}}>Find related questions<ArrowUpRight size={15}/></button></div>}
  {busy&&<p role="status" className="related-status">Comparing question meanings… You can close this panel to cancel.</p>}
  {error&&<p className="related-error" role="alert">{error}</p>}
  {!data&&!busy&&!error&&<div className="related-empty"><Search size={24} aria-hidden="true"/><p>Start with a research topic</p><span>Related questions will appear here. Open a result to see its recorded evidence.</span></div>}
  {data&&<div className="related-results flex flex-col gap-3">
   <div className="flex items-center justify-between gap-3"><h3>Related questions</h3><span className="related-count">{data.neighbors.length} results</span></div>
   <p className="related-status" role="status">Indexed {data.indexed_count??0} of {data.total_questions??0} active questions · {data.coverage}</p>
   <ol className="related-result-list flex flex-col gap-2">{data.neighbors.map(n=><li key={n.question_id}><button aria-label={`${n.text || `Open question ${n.question_id}`} · cosine ${n.similarity.toFixed(3)}`} onClick={()=>onChoose(n.question_id)}><span className="related-result-meta"><span>Q{n.question_id}</span><span title="Cosine similarity compares wording, not clinical evidence.">Similarity {n.similarity.toFixed(3)}</span></span><span className="related-result-title">{n.text || `Open question ${n.question_id}`}<ArrowUpRight size={17}/></span></button></li>)}</ol>
   {!data.neighbors.length&&<p className="related-empty">No related questions returned. Try another topic or a selected question.</p>}
  </div>}
  <details className="related-settings"><summary><Network size={16}/>Map layout &amp; method</summary><div className="flex flex-col gap-3 pt-3">
   <p>Similarity compares question wording, not clinical relationships. Map distance is an approximate projection.</p>
   <div className="related-layout-actions grid grid-cols-1 gap-2 sm:grid-cols-2"><button disabled={busy} type="button" onClick={()=>void load()}>Refresh semantic layout</button><button type="button" onClick={()=>{request.current?.abort();setBusy(false);setData(null);onLayout(null);}}>Use decorative layout</button></div>
   {data&&<><p>{data.limitations}</p><details><summary>Embedding provenance</summary><pre>{displayJson({model:data.identity,index_hash:data.index_hash})}</pre></details></>}
  </div></details>
 </section>;
}
