import {useEffect,useState} from 'react';

type ModelRate={id:string;provider:string;model:string;roles:string[];enabled:boolean;
  rates:{input?:number;output?:number;cache_read?:number};source:string;valid_until:string};
type Settings={models:ModelRate[];read_only:boolean};

async function read(response:Response):Promise<Settings>{
  if(!response.headers.get('content-type')?.includes('application/json'))throw Error('Pricing settings are unavailable. Try again after the server is ready.');
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'Pricing request failed');
  return data;
}

export default function ManualPricingSettings(){
  const [settings,setSettings]=useState<Settings|null>(null);
  const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{const controller=new AbortController();
    void fetch('/control/pricing',{signal:controller.signal}).then(read).then(setSettings).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return()=>controller.abort();
  },[]);
  const update=(id:string,patch:Partial<ModelRate>)=>{setMessage('');setSettings(s=>s?{...s,models:s.models.map(m=>m.id===id?{...m,...patch}:m)}:s);};
  return <section aria-label="Manual cost estimates" className="space-y-3">
    <p>Optional USD token rates for this installation. No pricing JSON is required. These are estimates, never actual Azure charges. Azure billing remains separate.</p>
    <p>Leave manual rates off unless you have verified prices. Missing or expired rates are not treated as zero. Disabling manual rates does not disable other clearly labeled estimate sources.</p>
    {settings?.read_only&&<p role="status">An advanced pricing override is active in .env. Remove MEMSTARA_PRICING_JSON / MEMSTARA_PRICING_PATH and restart to use this editor. Existing overrides are not overwritten here.</p>}
    {!settings&&!error&&<p>Loading configured models…</p>}
    {settings?.models.map(m=><fieldset key={m.id} disabled={busy||settings.read_only} className="space-y-2 rounded border border-paper-line p-3">
      <legend>{m.model} · {m.provider}</legend>
      <p>{m.roles.map(r=>({question:'Question',hypothesis:'Hypothesis',data:'Data',ml:'ML',interpretation:'Interpretation',explanation:'Explanation',explanation_agent:'Explanation',non_explanation_agents:'Other agents'} as Record<string,string>)[r]||r).join(' · ')}</p>
      <label className="flex gap-2"><input type="checkbox" checked={m.enabled} onChange={e=>update(m.id,{enabled:e.target.checked})}/>Use manually verified rates</label>
      {m.enabled&&<>
        {(['input','output','cache_read'] as const).map(kind=><label key={kind} className="block">{{input:'Input',output:'Output',cache_read:'Cache read (optional)'}[kind]} · USD per 1 million tokens
          <input className="workspace-input" type="number" min="0" step="any" value={m.rates[kind]??''} onChange={e=>update(m.id,{rates:{...m.rates,[kind]:e.target.value===''?undefined:e.target.valueAsNumber}})}/>
        </label>)}
        <label className="block">Verified rate source (HTTPS URL)<input className="workspace-input" type="url" value={m.source} onChange={e=>update(m.id,{source:e.target.value})}/></label>
        <label className="block">Expires at start of this date (UTC)<input className="workspace-input" type="date" value={m.valid_until.slice(0,10)} onChange={e=>update(m.id,{valid_until:e.target.value?`${e.target.value}T00:00:00+00:00`:''})}/></label>
        <p>Use only a flat token rate applicable to this deployment. Tiered, long-context or managed-compute pricing is not represented by this form. Requests with cache writes cannot be estimated here because their TTL is unknown.</p>
      </>}
    </fieldset>)}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <button type="button" className="workspace-action" disabled={!settings||settings.read_only||busy} onClick={async()=>{
      setBusy(true);setError('');setMessage('');
      try{
        const updated=await read(await fetch('/control/pricing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({models:settings!.models})}));
        setSettings(updated);setMessage('Manual rates saved for subsequent requests. Existing cost records and Azure billing are unchanged.');
      }catch(e){setError(String(e));}finally{setBusy(false);}
    }}>{busy?'Saving…':'Save manual rates'}</button>
  </section>;
}
