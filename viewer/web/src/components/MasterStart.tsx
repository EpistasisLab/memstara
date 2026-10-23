import {Play} from 'lucide-react';
import {usePipelines} from '../store/pipelines';

export default function MasterStart(){
  const {items,loaded,busy,startingAll,stoppingAll,startOutcomes,playAll}=usePipelines();
  const available=items.some(p=>(!p.running&&!p.latest)||p.running?.pause_requested||p.running?.execution_state==='paused');
  return <div className="master-start-group">
    <button type="button" data-help="Start all pipelines" data-help-description="Start pipelines that have not run yet and resume paused ones. Already running pipelines are left running. Finished pipelines require an additional Replicate count from the pipeline list." disabled={!loaded||busy||stoppingAll||!available}
      className="flex items-center gap-2 rounded-lg border border-paper-line bg-accent px-3 py-2 text-sm font-medium text-accent-contrast disabled:opacity-40"
      title="Start pipelines that have not run yet, and resume paused ones. Finished pipelines require an explicit additional Replicate count from the pipeline list."
      onClick={()=>void playAll()}><Play size={14}/>{startingAll?'Starting pipelines…':'Start all pipelines'}</button>
    {startOutcomes.length>0&&<details className="batch-start-results text-xs" aria-label="Start all results">
      <summary className="cursor-pointer" role="status">{startOutcomes.filter(r=>r.status==='started'||r.status==='resumed').length} started / resumed · {startOutcomes.filter(r=>r.status==='skipped').length} skipped · {startOutcomes.filter(r=>r.status==='failed').length} failed</summary>
      <ul className="mt-2 space-y-1 rounded-lg border border-paper-line bg-paper-panel p-3">{startOutcomes.map(r=><li className="break-words" key={r.id}><strong>{r.name}</strong>: {r.detail}{r.status==='failed'&&' Check pipeline status before retrying; an interrupted request may still have started.'}</li>)}</ul>
    </details>}
  </div>;
}
