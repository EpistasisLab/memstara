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
  const submitting = useRef(false);
  const p = current ?? pipeline;
  async function remove() {
    if (submitting.current || busy) return;
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
      {p.deleting ? <p className="pipeline-delete-notice" role="status">The execution has been asked to stop. Memstara will remove the pipeline as soon as the server confirms it has exited.</p> : p.running ? <p className="pipeline-delete-notice" role="alert">This will interrupt the current execution, including a paused or resumable run, then remove the pipeline setup. Saved run artifacts are retained.</p> : <p>Only the pipeline setup is removed. Saved run artifacts are retained.</p>}
      {error && <p role="alert">{error}</p>}
      <div className="pipeline-management-buttons">
        <button type="button" data-delete-cancel disabled={pending} onClick={close}>Cancel</button>
        <button type="button" className="pipeline-delete-confirm" disabled={busy || pending} onClick={()=>void remove()}><Trash2 size={16} aria-hidden="true"/>{pending ? p.running ? 'Stopping and deleting…' : 'Deleting…' : p.running ? 'Stop & delete' : p.deleting ? 'Continue deletion' : 'Delete pipeline'}</button>
      </div>
    </div>
  </FloorDetailDialog>;
}
