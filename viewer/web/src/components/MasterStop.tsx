import { Square } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useControl } from '../store/control';
import MasterStart from './MasterStart';

/** Always reachable, including while reading reports or telemetry. */
export default function MasterStop() {
  const items=usePipelines(s=>s.items);
  const stopping=usePipelines(s=>s.stoppingAll);
  const starting=usePipelines(s=>s.startingAll);
  const error=usePipelines(s=>s.error);
  const legacy=useControl(s=>s.running);
  const canStop=items.some(p=>p.running&&!p.running.pause_requested)||!!(legacy&&!legacy.pause_requested);
  return <div className="master-run-controls">
    <MasterStart/>
    <button data-help="Stop all pipelines" data-help-description="Request a stop for every pipeline before its next agent call. Work already in progress may finish and incur cost. Saved progress remains available to resume." className="master-stop rounded-lg px-3 py-2" disabled={stopping||(!canStop&&!starting)}
      title="Stop every pipeline before its next agent call. In-flight work may still incur cost. Resume preserves progress."
      onClick={()=>void usePipelines.getState().stopAll()}><Square size={14} className="inline mr-2"/>{stopping?'Requesting stop…':'Stop all pipelines'}</button>
    {error&&<span role="alert" className="master-run-error break-words text-xs text-red-600">{error}</span>}
  </div>;
}
