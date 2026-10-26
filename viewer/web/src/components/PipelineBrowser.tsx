import {createPortal} from 'react-dom';
import { useMemo, useState, useRef, useLayoutEffect, useEffect } from 'react';
import { PanelLeftClose, PanelLeftOpen, Trash2 } from 'lucide-react';
import type { PipelineDefinition } from '../store/pipelines';
import PipelineRowActions from './PipelineRowActions';
import PipelineDeleteDialog from './PipelineDeleteDialog';
import { pipelineLoopLabel } from '../lib/pipelineProgress';
import {researchSkillProfile} from '../lib/researchSkills';
import {useControl} from '../store/control';
import {usePipelines} from '../store/pipelines';
import {pipelineState} from '../lib/pipelineState';
import {useLiveOutputs} from '../store/liveOutputs';
import HypothesisHeading from './HypothesisHeading';
import {displayText} from '../lib/displayText';
import {experimentHypothesis} from '../lib/experimentHeading';
export default function PipelineBrowser({items, selected, onSelect, compare, onCompare,toggleHost}: {
  toggleHost:HTMLElement|null; items: PipelineDefinition[]; selected: string | null; onSelect: (id:string)=>void;
  compare: string[]; onCompare:(ids:string[])=>void;
}) {
  // Profile bindings arrive with the catalog; refresh the source label with it.
  useControl(s=>s.catalog);
  const pendingStart=usePipelines(s=>s.pendingStart);
  const findings=useLiveOutputs(s=>s.results);
  const events=useLiveOutputs(s=>s.events);
  const browser=useRef<HTMLElement>(null);
  const [deleting,setDeleting]=useState<PipelineDefinition|null>(null);
  const [selectionRevision,setSelectionRevision]=useState(0);
  const choose=(id:string)=>{onSelect(id);setSelectionRevision(v=>v+1);if(browser.current&&browser.current.parentElement!.getBoundingClientRect().width<760)setOpen(false);};
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
  const ordered=useMemo(()=>[...items].sort((a,b)=>a.number-b.number),[items]);
  const pages=Math.max(1,Math.ceil(ordered.length/25)), current=Math.min(page,pages-1);
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
  return <aside ref={browser} className={`pipeline-browser ${open?'':'is-closed'}`} aria-label="Pipeline browser">
    {toggleHost&&createPortal(<button className="floor-panel-toggle" aria-label={open?"Hide pipeline list":"Show pipeline list"} aria-expanded={open} aria-pressed={open} aria-controls="pipeline-browser-content" onClick={()=>setOpen(!open)}>{open?<PanelLeftClose size={16}/>:<PanelLeftOpen size={16}/>}<span>Experiments</span><span className="floor-panel-count">{items.length}</span></button>,toggleHost)}
    <div className="pipeline-browser-heading"><h3>Experiments</h3><span>{items.length}</span></div>
    <div id="pipeline-browser-content" hidden={!open}>
      <div className="pipeline-browser-list" tabIndex={0} aria-label="Scrollable pipeline list">
        {ordered.slice(current*25,current*25+25).map(p=>{
          const state=pipelineState(p,pendingStart?.pipelineId===p.id);
          const stageNames:Record<string,string>={hypothesis:'Hypothesis generation',data:'Data extraction',ml:'Model evaluation',interpret:'Interpretation',interpreter:'Interpretation',report:'Explanation'};
          const corpus=researchSkillProfile(p.configuration).label;
          const target=p.running?.configuration?.y_column??p.configuration.y_column??'Not specified';
          const execution=p.running??p.latest;
          const fullHypothesis=displayText(experimentHypothesis(execution?.run_tag??'',p.progress.iteration,!!p.running,execution?.configuration?.trials,events,findings)).replace(/\s+/g,' ').trim();
          const heading=fullHypothesis;
          const title=heading||(p.running?'Generating hypothesis…':p.name);
          return <div key={p.id} data-state={state.toLowerCase().replaceAll(' ','-')} className={`pipeline-browser-row ${selected===p.id?'is-selected':''}`}>
          <div className="pipeline-card-top pipeline-card-header">
            <button type="button" className="pipeline-card-identity pipeline-card-heading-select" aria-label={`Select pipeline ${p.number}: ${p.name}`} aria-pressed={selected===p.id} onClick={()=>choose(p.id)}>Experiment {p.number}</button>
            <div className="pipeline-card-status-actions"><span className="pipeline-state-badge"><i aria-hidden="true"/>{state}</span>
            <button type="button" className="pipeline-card-delete" aria-label={`Delete ${p.name}`} title={`Delete ${p.name}`} aria-haspopup="dialog" onClick={()=>setDeleting(p)}><Trash2 size={16} aria-hidden="true"/></button>
            </div>
          </div>
          <button className="pipeline-card-select" aria-label={`Inspect ${p.name}`} aria-pressed={selected===p.id} onClick={()=>choose(p.id)}>
            <HypothesisHeading text={title}/>
            {(heading||p.running)&&<span className="pipeline-card-context text-xs text-ink-soft" title={p.name}>Saved as: {p.name}</span>}
            <span className="pipeline-card-stage pipeline-card-context" title={`Corpus: ${corpus} · Target: ${target}`}>{corpus} · {target}</span>
            <span className="pipeline-card-position"><span className="pipeline-card-loop">{pipelineLoopLabel(p)}</span></span>
            {p.progress.stage&&<span className="pipeline-card-stage">{p.running?'Current':'Last'}: {stageNames[p.progress.stage]??p.progress.stage}</span>}
          </button>
          <PipelineRowActions compact pipeline={p}/>
        </div>})}
        {!ordered.length&&<p className="pipeline-browser-help">No pipelines yet.</p>}
      </div>
      {deleting&&<PipelineDeleteDialog pipeline={deleting} close={()=>setDeleting(null)} onDeleted={()=>onCompare(compare.filter(id=>id!==deleting.id))}/>}
      <div className="pipeline-browser-footer" hidden={pages===1&&!compare.length}>{pages>1&&<div className="pipeline-browser-pagination"><button disabled={!current} onClick={()=>setPage(current-1)}>Previous</button><span>Page {current+1} of {pages}</span><button disabled={current===pages-1} onClick={()=>setPage(current+1)}>Next</button></div>}
      {!!compare.length&&<button className="pipeline-compare-clear" onClick={()=>onCompare([])}>Exit comparison ({compare.length} selected)</button>}
      </div>
    </div>
  </aside>;
}
