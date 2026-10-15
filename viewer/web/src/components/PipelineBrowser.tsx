import { useMemo, useState, useRef, useLayoutEffect, useEffect } from 'react';
import { Search, PanelLeftClose, PanelLeftOpen, ArrowUpRight, Trash2 } from 'lucide-react';
import type { PipelineDefinition } from '../store/pipelines';
import PipelineRowActions from './PipelineRowActions';
import PipelineDeleteDialog from './PipelineDeleteDialog';
import { pipelineLoopLabel } from '../lib/pipelineProgress';
import {researchSkillProfile} from '../lib/researchSkills';
import {useControl} from '../store/control';
import {pipelineState} from '../lib/pipelineState';
export default function PipelineBrowser({items, selected, onSelect, compare, onCompare, onSettings}: {
  items: PipelineDefinition[]; selected: string | null; onSelect: (id:string)=>void;
  compare: string[]; onCompare:(ids:string[])=>void; onSettings:(id:string)=>void;
}) {
  // Profile bindings arrive with the catalog; refresh the source label with it.
  useControl(s=>s.catalog);
  const browser=useRef<HTMLElement>(null);
  const [deleting,setDeleting]=useState<PipelineDefinition|null>(null);
  const [selectionRevision,setSelectionRevision]=useState(0);
  const choose=(id:string)=>{onSelect(id);setSelectionRevision(v=>v+1);if(browser.current&&browser.current.parentElement!.getBoundingClientRect().width<760)setOpen(false);};
  const [query,setQuery]=useState(''), [status,setStatus]=useState('All'), [sort,setSort]=useState('number');
  const [page,setPage]=useState(0), [open,setOpen]=useState(true);
  useEffect(()=>{
    const parent=browser.current?.parentElement;if(!parent)return;
    let previous=false;
    const observer=new ResizeObserver(([entry])=>{
      const compact=entry.contentRect.width<900;
      if(compact&&!previous)setOpen(false);
      previous=compact;
    });
    observer.observe(parent);return()=>observer.disconnect();
  },[]);
  const filtered=useMemo(()=>items.filter(p=>(status==='All'||pipelineState(p)===status)&&p.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>sort==='name'?a.name.localeCompare(b.name):a.number-b.number),[items,query,status,sort]);
  const pages=Math.max(1,Math.ceil(filtered.length/25)), current=Math.min(page,pages-1);
  useLayoutEffect(()=>{
    if(!open)return;
    const list=browser.current?.querySelector<HTMLElement>('.pipeline-browser-list');
    const card=list?.querySelector<HTMLElement>('.pipeline-browser-row.is-selected');
    if(!list||!card)return;
    // Align after the previous card collapses and the new one expands. Scroll
    // only this list; never move the page, canvas, or the user's keyboard focus.
    const top=list.scrollTop+card.getBoundingClientRect().top-list.getBoundingClientRect().top-2;
    list.scrollTo({top:Math.max(0,top),behavior:'instant'});
  },[selected,open,current,selectionRevision]);
  const activePipeline=items.find(p=>p.id===selected);
  return <aside ref={browser} className={`pipeline-browser ${open?'':'is-closed'}`} aria-label="Pipeline browser">
    <button className="pipeline-browser-toggle" aria-label={open?"Hide pipeline list":"Show pipeline list"} title={open?"Hide pipeline list":"Show pipeline list"} aria-expanded={open} aria-controls="pipeline-browser-content" onClick={()=>setOpen(!open)}>{open?<PanelLeftClose size={16}/>:<PanelLeftOpen size={16}/>}<span>{open?'Hide pipeline list':'Show pipeline list'}</span></button>
    <div id="pipeline-browser-content" hidden={!open}>
      <div className="pipeline-browser-heading"><h3>Pipelines</h3><span>{items.length} configured</span></div>
      <details className="pipeline-browser-search-tools"><summary>Search and filter</summary>
      <label className="pipeline-search"><Search size={16}/><input aria-label="Search pipelines" placeholder="Search by name…" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}}/></label>
      <div className="pipeline-browser-filters">
        <label>Status<select aria-label="Status" value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}>{['All','Running','Waiting','Paused','Stopping','Ready','Completed','Interrupted','Needs attention','Finished with skips','No findings'].map(s=><option key={s}>{s}</option>)}</select></label>
        <label>Sort<select aria-label="Sort pipelines" value={sort} onChange={e=>{setSort(e.target.value);setPage(0);}}><option value="number">Creation order</option><option value="name">Name</option></select></label>
      </div>
      <p className="pipeline-browser-help">Select a name to inspect. Check up to 3 pipelines to compare their diagrams.</p>
      </details>
      {selected&&!filtered.some(p=>p.id===selected)&&<p className="pipeline-browser-help">The selected pipeline is outside this filter. Its diagram remains visible.</p>}
      <div className="pipeline-browser-list" tabIndex={0} aria-label="Scrollable pipeline list">
        {filtered.slice(current*25,current*25+25).map(p=>{
          const state=pipelineState(p);
          const stageNames:Record<string,string>={hypothesis:'Hypothesis generation',data:'Data extraction',ml:'Model evaluation',interpret:'Interpretation',interpreter:'Interpretation',report:'Explanation'};
          return <div key={p.id} data-state={state.toLowerCase().replaceAll(' ','-')} className={`pipeline-browser-row ${selected===p.id?'is-selected':''}`}>
          <div className="pipeline-card-top pipeline-card-header">
            <button type="button" className="pipeline-card-identity pipeline-card-heading-select" aria-label={`Select pipeline ${p.number}: ${p.name}`} aria-pressed={selected===p.id} onClick={()=>choose(p.id)}>Pipeline {p.number}</button>
            <div className="pipeline-card-status-actions"><span className="pipeline-state-badge"><i aria-hidden="true"/>{state}</span>
            <button type="button" className="pipeline-card-delete" aria-label={`Delete ${p.name}`} title={`Delete ${p.name}`} aria-haspopup="dialog" onClick={()=>setDeleting(p)}><Trash2 size={16} aria-hidden="true"/></button>
            </div>
          </div>
          <button className="pipeline-card-select" data-help="Inspect this pipeline" data-help-description="Select this card to focus its diagram and view its execution controls. The Loop counter refers to this pipeline’s latest execution." aria-label={`Inspect ${p.name}`} aria-pressed={selected===p.id} onClick={()=>choose(p.id)}>
            <strong className="pipeline-card-name" title={p.name}>{p.name}</strong>
            <span className="pipeline-card-stage">Configured corpus: {researchSkillProfile(p.configuration).label}</span>
            <span className="pipeline-card-stage">{p.running?'Execution target':'Configured target'}: {p.running?.configuration?.y_column??p.configuration.y_column??'Not specified'}</span>
            <span className="pipeline-card-position"><span className="pipeline-card-loop">{pipelineLoopLabel(p)}</span><ArrowUpRight size={16} aria-hidden="true"/></span>
            <span className="pipeline-card-stage">{p.progress.stage ? `${p.running?'Current':'Last recorded'} stage: ${stageNames[p.progress.stage]??p.progress.stage}` : 'Ready to begin exploration'}</span>
          </button>
          <div className="pipeline-card-footer">
            <label className="pipeline-card-compare"><input type="checkbox" aria-label={`Compare ${p.name}`} checked={compare.includes(p.id)} disabled={!compare.includes(p.id)&&compare.length>=3} onChange={e=>onCompare(e.target.checked?[...compare,p.id]:compare.filter(id=>id!==p.id))}/><span>Compare in Floor plan</span></label>
          </div>

        </div>})}
        {!filtered.length&&<p className="pipeline-browser-help">No matching pipelines.</p>}
      </div>
      {deleting&&<PipelineDeleteDialog pipeline={deleting} close={()=>setDeleting(null)} onDeleted={()=>onCompare(compare.filter(id=>id!==deleting.id))}/>}
      {activePipeline&&<section className="pipeline-selected-controls" aria-label="Selected pipeline controls"><strong title={activePipeline.name}>{activePipeline.name}</strong><PipelineRowActions compact key={activePipeline.id} pipeline={activePipeline} onSettings={()=>onSettings(activePipeline.id)}/></section>}
      <div className="pipeline-browser-footer">{pages>1&&<div className="pipeline-browser-pagination"><button disabled={!current} onClick={()=>setPage(current-1)}>Previous</button><span>Page {current+1} of {pages}</span><button disabled={current===pages-1} onClick={()=>setPage(current+1)}>Next</button></div>}
      {!!compare.length&&<button className="pipeline-compare-clear" onClick={()=>onCompare([])}>Exit comparison ({compare.length} selected)</button>}
      </div>
    </div>
  </aside>;
}
