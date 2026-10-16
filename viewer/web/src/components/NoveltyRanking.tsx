import {useEffect, useState} from 'react';
import {novelty} from '../lib/novelty';
import NoveltyEvidence from './NoveltyEvidence';
interface Item {task_id:number; result_id:number; question_id:number; run_tag:string; trial:number; hypothesis:string; auc:number|null; novelty:unknown}
interface Page {items:Item[]; total:number; next_offset:number|null}
export default function NoveltyRanking({open}: {open:(question:number,result:number)=>void}) {
 const [page,setPage]=useState<Page|null>(null), [error,setError]=useState('');
 const [offset,setOffset]=useState(0), [run,setRun]=useState(''), [draft,setDraft]=useState('');
 useEffect(()=>{
  let stopped=false; const abort=new AbortController(); let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try {
   const r=await fetch(`/api/discovery/novelty?offset=${offset}&run_tag=${encodeURIComponent(run)}`,{signal:AbortSignal.any([abort.signal,AbortSignal.timeout(5000)])});
   if(!r.ok)throw Error('Novelty records are temporarily unavailable.');
   const data=await r.json(); if(!Array.isArray(data.items))throw Error('Invalid ranking response.');
   if(!stopped){setPage(data);setError('');}
  }catch(e){if(!stopped)setError(String(e));}finally{if(!stopped)timer=setTimeout(poll,10000);}};
  setPage(null);void poll();return()=>{stopped=true;abort.abort();clearTimeout(timer);};
 },[offset,run]);
 return <section aria-label="KG novelty ranking" className="my-4 rounded-xl border border-paper-line p-4">
  <h2 className="text-lg font-semibold">Novelty ranking · KG proxy</h2>
  <p className="text-sm">Highest predicted-path share first; ties use newest result. Latest result per hypothesis. Unscored hypotheses follow without a rank. Compare within the same corpus and study; scores across different knowledge sources are not equivalent.</p>
  <form className="flex flex-wrap gap-2 my-3" onSubmit={e=>{e.preventDefault();setOffset(0);setRun(draft.trim());}}>
   <input aria-label="Filter novelty by run ID" placeholder="Run ID (blank: all runs)" value={draft} onChange={e=>setDraft(e.target.value)} className="min-w-0 flex-1 border rounded p-2"/><button type="submit">Apply run filter</button>
  </form>
  {error&&<p role="status">{error}</p>}
  {!page&&!error&&<p>Loading recorded scores…</p>}
  {page?.items.map((item,index)=>{const n=novelty(item.novelty);return <article key={item.task_id} className="my-3 rounded-lg border border-paper-line p-3">
   <div className="flex flex-wrap justify-between gap-2"><strong>{n.score===null?'Unscored':`#${offset+index+1}`} · Q{item.question_id} / Task {item.task_id}</strong><span>AUROC: {typeof item.auc==='number'?item.auc.toFixed(3):'Unavailable'}</span></div>
   <p className="my-2">{item.hypothesis}</p><small style={{overflowWrap:'anywhere'}}>{item.run_tag} · Trial {item.trial+1}</small>
   <NoveltyEvidence value={item.novelty}/><button onClick={()=>open(item.question_id,item.result_id)}>Open agent outputs</button>
  </article>;})}
  {page&&!page.items.length&&<p>No recorded hypotheses in this scope.</p>}
  <div className="flex flex-wrap gap-4"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous</button><span>{page?.total??0} hypotheses</span><button disabled={page?.next_offset==null} onClick={()=>setOffset(page?.next_offset??0)}>Next</button></div>
 </section>;
}
