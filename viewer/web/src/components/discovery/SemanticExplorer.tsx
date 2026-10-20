import {useEffect, useRef, useState} from 'react';
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
 return <section className="universe-section" aria-label="Semantic question explorer">
  <h2>Explore related questions</h2>
  <p>Local deep-learning embeddings compare question wording. Cosine scores describe similarity; screen distance is a distorted projection, not a clinical relationship.</p>
  <form onSubmit={e=>{e.preventDefault();void load(true);}} className="universe-tools">
   <label>Search indexed questions<input aria-label="Semantic query" value={query} maxLength={1000} onChange={e=>setQuery(e.target.value)} placeholder="Describe a research topic"/></label>
   <button disabled={busy} type="submit">{busy?'Building / searching index…':'Search meaning'}</button>
   <button disabled={busy||selected===null} type="button" onClick={()=>{setQuery('');void load(true,true);}}>Find related questions</button>
   <button disabled={busy} type="button" onClick={()=>void load()}>Refresh semantic layout</button>
   <button type="button" onClick={()=>{request.current?.abort();setBusy(false);setData(null);onLayout(null);}}>Use decorative layout</button>
  </form>
  {error&&<p role="alert">{error}</p>}
  {data&&<><p role="status">Indexed {data.indexed_count??0} of {data.total_questions??0} active questions · {data.coverage}. New questions require refresh.</p>
   <p>{data.limitations}</p>
   <ol className="universe-list">{data.neighbors.map(n=><li key={n.question_id}><button onClick={()=>onChoose(n.question_id)}>{n.text || `Open question ${n.question_id}`} · cosine {n.similarity.toFixed(3)}</button></li>)}</ol>
   {!data.neighbors.length&&<p>No semantic neighbors returned. Enter a topic or select a question.</p>}
   <details><summary>Embedding provenance</summary><pre>{JSON.stringify({model:data.identity,index_hash:data.index_hash},null,2)}</pre></details></>}
 </section>;
}
