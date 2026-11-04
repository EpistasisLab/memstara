import {lazy, Suspense, useEffect, useState} from 'react';
import {displayText} from '../lib/displayText';
const SkillMarkdown = lazy(() => import('./SkillMarkdown'));

type Reference = {id:string;stage:string;hash?:string;origin?:'catalog'|'recorded'};
type Current = {id:string;hash:string;description:string;content:string};
type Saved = {id:string;stage:string;run_tag:string;hash?:string;content:string;prompt_hash:string};

function Instructions({content}:{content:string}) {
  return <div className="cs-markdown"><Suspense fallback={<p>Loading instructions…</p>}>
    <SkillMarkdown content={content}/>
  </Suspense></div>;
}

export default function SkillInstructions({reference,current,runTag}:{reference:Reference;current?:Current;runTag?:string}) {
  const recorded=reference.origin==='recorded';
  const [saved,setSaved]=useState<Saved|null>(null),[error,setError]=useState('');
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    setSaved(null);setError('');
    if(!recorded)return;
    if(!runTag){setError('The execution identifier is unavailable.');return;}
    const controller=new AbortController();
    let active=true;
    const timer=setTimeout(()=>controller.abort(),10000);
    const query=new URLSearchParams({stage:reference.stage,skill:reference.id,...(reference.hash?{hash:reference.hash}:{})});
    void (async()=>{
      try {
        const response=await fetch(`/control/runs/${encodeURIComponent(runTag)}/skill-instructions?${query}`,{signal:controller.signal});
        const data=await response.json();
        if(!response.ok)throw Error(data.error||'Could not read recorded instructions.');
        if(data.run_tag!==runTag||data.id!==reference.id||data.stage!==reference.stage||
           (reference.hash&&data.hash!==reference.hash)||typeof data.content!=='string'||!data.content.trim()) {
          throw Error('The returned instructions do not match this execution and skill.');
        }
        if(active)setSaved(data);
      } catch(e) {
        if(active)setError(e instanceof Error&&e.name==='AbortError'?'Recorded instructions did not respond in time.':String(e));
      } finally {clearTimeout(timer);}
    })();
    return()=>{active=false;clearTimeout(timer);controller.abort();};
  },[recorded,runTag,reference.id,reference.stage,reference.hash,attempt]);

  if(!recorded)return current?<>
    <p>Current skill instructions</p><p className="cs-document-description">{displayText(current.description)}</p>
    <Instructions content={current.content}/>
  </>:<p>This configured skill is not in the current library. Refresh the skill library or select an available skill.</p>;

  return <>
    <p>Recorded agent instructions</p>
    <p>Saved for this execution, including the skill and surrounding agent instructions.</p>
    {saved?<><Instructions content={saved.content}/><details><summary>Recorded prompt version</summary><code>{saved.prompt_hash}</code></details></>
      :error?<p role="alert">{error} <button onClick={()=>setAttempt(n=>n+1)}>Retry</button></p>
      :<p role="status">Loading recorded instructions…</p>}
    {current&&<details className="cs-current-skill"><summary>View current library instructions</summary>
      <p>This is the current library version, not a replacement for the recorded execution instructions.</p>
      <p className="cs-document-description">{displayText(current.description)}</p>
      <Instructions content={current.content}/><p>Current version: <code>{current.hash}</code></p>
    </details>}
  </>;
}
