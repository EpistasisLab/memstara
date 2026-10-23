import {useState} from 'react';
import FloorDetailDialog from './FloorDetailDialog';
import {usePipelines, type PipelineDefinition} from '../store/pipelines';

export default function PipelineRetryDialog({pipeline:p,close}:{pipeline:PipelineDefinition;close:()=>void}) {
  const [source]=useState({tag:p.latest?.run_tag??'',replicate:p.failure?.loop});
  const busy=usePipelines(s=>s.busy),error=usePipelines(s=>s.error);
  const changed=!!p.running||p.latest?.run_tag!==source.tag||p.failure?.loop!==source.replicate;
  const valid=Number.isInteger(source.replicate)&&Number(source.replicate)>0;
  return <FloorDetailDialog title="Retry remaining replicates" close={()=>{if(!busy)close();}} className="pipeline-management-dialog">
    <div className="pipeline-management">
      <h3>{p.name}</h3>
      <p>Start a new execution at Replicate {source.replicate}. Earlier completed results and the failed attempt stay saved.</p>
      <p>The failed replicate runs again with fresh model training and new data partitioning. This is not checkpoint resume. Model calls may incur cost.</p>
      {changed&&<p role="alert">The execution changed. Close this window and review the pipeline again.</p>}
      {error&&<p role="alert">{error}</p>}
      <div className="pipeline-management-buttons">
        <button disabled={busy} onClick={close}>Cancel</button>
        <button disabled={busy||changed||!valid} onClick={async()=>{if(await usePipelines.getState().play(p.id,{mode:'retry',expectedRunTag:source.tag}))close();}}>{busy?'Starting…':`Retry from Replicate ${source.replicate}`}</button>
      </div>
    </div>
  </FloorDetailDialog>;
}
