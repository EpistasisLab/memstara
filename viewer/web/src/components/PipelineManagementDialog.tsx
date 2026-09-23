import { useState } from 'react';
import { Settings2, Trash2 } from 'lucide-react';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
import FloorDetailDialog from './FloorDetailDialog';
import AdditionalAnalysisDialog from './AdditionalAnalysisDialog';
import PipelineNameEditor from './PipelineNameEditor';
import PipelineDeleteDialog from './PipelineDeleteDialog';
import PipelineSetupGuide from './PipelineSetupGuide';

export default function PipelineManagementDialog({pipeline:p,onSettings,close}:{pipeline:PipelineDefinition;onSettings:()=>void;close:()=>void}) {
  const busy=usePipelines(s=>s.busy), error=usePipelines(s=>s.error);
  const [fresh,setFresh]=useState(false);
  const [confirm,setConfirm]=useState<'delete'|'end'|null>(null);
  const combinations=!!p.configuration.combination_skills&&Object.keys(p.configuration.combination_skills).length>0;
  const paused=!!p.running&&(p.running.pause_requested||p.running.execution_state==='paused');
  if(confirm==='delete')return <PipelineDeleteDialog pipeline={p} close={()=>setConfirm(null)} onDeleted={close}/>;
  if(fresh)return <AdditionalAnalysisDialog pipeline={p} fresh close={()=>setFresh(false)}/>;
  return <FloorDetailDialog title="Pipeline settings and actions" close={close} className="pipeline-management-dialog">
    <div className="pipeline-management">
      <div className="pipeline-management-identity"><span>Pipeline {p.number}</span><h3>{p.name}</h3></div>
      <section aria-label="General settings"><h3>General settings</h3><p>Update the execution settings or give this research pipeline a recognizable name.</p>
        <div className="pipeline-management-buttons"><button disabled={busy||combinations} aria-label={`Settings for ${p.name}`} onClick={()=>{close();onSettings();}}><Settings2 size={16}/>Execution settings</button><PipelineNameEditor pipeline={p} buttonLabel="Rename pipeline"/></div>
      </section>
      <section aria-label="Agent skills"><h3>Agent skills</h3><p>Review the instructions for the hypothesis, machine learning, interpreter and explanation agents.</p>{combinations?<p>Review all selected flavors in the combination grid. To change the combination schedule, create a new design; saved execution schedules stay fixed.</p>:<PipelineSetupGuide/>}</section>
      <section className="pipeline-management-danger" aria-label="Execution and removal"><h3>Execution and removal</h3>
        <p>{p.running?'End this execution before deleting the pipeline. Saved analysis results are retained.':'Deleting removes this pipeline setup. Saved analysis results are retained.'}</p>
        <div className="pipeline-management-buttons">{!p.running&&p.latest&&<button disabled={busy} onClick={()=>setFresh(true)}>Start a new execution…</button>}{paused&&<button disabled={busy} onClick={()=>setConfirm('end')}>End execution</button>}
          <button disabled={busy||!!p.running} aria-label={`Delete ${p.name}`} onClick={()=>setConfirm('delete')}><Trash2 size={16}/>Delete pipeline</button></div>
        {confirm==='end'&&<div className="pipeline-management-confirm" role="group" aria-label={`Confirm ${confirm} ${p.name}`}>
          <p>{`End the execution for “${p.name}”? Resume will no longer be available. Saved results remain.`}</p>
          <div className="pipeline-management-buttons"><button disabled={busy} onClick={()=>setConfirm(null)}>Cancel</button><button disabled={busy} onClick={async()=>{await usePipelines.getState().end(p.id);setConfirm(null);}}>Confirm end</button></div>
        </div>}
      </section>
      {error&&<p role="alert">{error}</p>}
    </div>
  </FloorDetailDialog>;
}
