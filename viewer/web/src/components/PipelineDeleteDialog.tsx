import { useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { usePipelines, type PipelineDefinition } from '../store/pipelines';
import FloorDetailDialog from './FloorDetailDialog';

export default function PipelineDeleteDialog({pipeline, close, onDeleted}: {
  pipeline: PipelineDefinition; close: () => void; onDeleted?: () => void;
}) {
  const current = usePipelines(s => s.items.find(p => p.id === pipeline.id));
  const busy = usePipelines(s => s.busy);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState<string | null>(null);
  const [endRequestedTag, setEndRequestedTag] = useState<string | null>(null);
  const submitting = useRef(false);
  const p = current ?? pipeline;
  const waitingForEnd = !!p.running && endRequestedTag === p.running.run_tag;
  async function endExecution() {
    if (submitting.current || busy || !p.running) return;
    if (!confirmEnd) return;
    const tag = confirmEnd;
    submitting.current = true;
    setPending(true); setError(null);
    try {
      if (await usePipelines.getState().end(p.id, tag)) { setEndRequestedTag(tag); setConfirmEnd(null); }
      else setError(usePipelines.getState().error || 'Could not end this execution.');
    } finally { submitting.current = false; setPending(false); }
  }
  async function remove() {
    if (submitting.current || busy || p.running) return;
    submitting.current = true;
    setPending(true); setError(null);
    try {
      if (await usePipelines.getState().remove(p.id)) { onDeleted?.(); close(); }
      else setError(usePipelines.getState().error || 'Could not delete this pipeline. Please try again.');
    } finally { submitting.current = false; setPending(false); }
  }
  return <FloorDetailDialog title="Delete pipeline?" close={close} dismissible={!pending} initialFocus="[data-delete-cancel]" className="pipeline-management-dialog pipeline-delete-dialog">
    <div className="pipeline-management" aria-busy={pending}>
      <p>Are you sure you want to delete <strong className="pipeline-delete-name">{p.name}</strong>?</p>
      <p>Only this pipeline setup is removed. Saved analysis results remain available in Run history.</p>
      {p.running && <>
        <p role="alert">This pipeline still has an execution, even while paused. End it before deleting the setup. Saved results will remain available.</p>
        {waitingForEnd ? <p role="status">Ending execution… Waiting for the server to confirm it has stopped. Delete will become available afterward.</p> : confirmEnd ? <div role="group" aria-label="Confirm end before deletion">
          <p>End this execution now? This interrupts unfinished work and removes the option to resume it. It does not delete the pipeline or its saved results.</p>
          <button type="button" disabled={busy || pending} onClick={()=>setConfirmEnd(null)}>Keep execution</button>
          <button type="button" disabled={busy || pending} onClick={()=>void endExecution()}>{pending?'Ending…':'Confirm end execution'}</button>
        </div> : <button type="button" disabled={busy || pending} onClick={()=>setConfirmEnd(p.running!.run_tag)}>End execution…</button>}
      </>}
      {!p.running && endRequestedTag && <p role="status">Execution ended. You can now delete this pipeline setup; saved results will remain available.</p>}
      {error && <p role="alert">{error}</p>}
      <div className="pipeline-management-buttons">
        <button type="button" data-delete-cancel disabled={pending} onClick={close}>Cancel</button>
        <button type="button" className="pipeline-delete-confirm" disabled={busy || pending || !!p.running} onClick={()=>void remove()}><Trash2 size={16} aria-hidden="true"/>{pending && !p.running ? 'Deleting…' : 'Delete pipeline'}</button>
      </div>
    </div>
  </FloorDetailDialog>;
}
