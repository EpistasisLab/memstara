import { useId } from 'react';
import { BarChart3 } from 'lucide-react';
import { useViewer } from '../store/viewer';
import { usePipelines } from '../store/pipelines';
import { unreadResults, useResultNotices } from '../store/resultNotices';

export default function ResultsNavigationButton({ open, active, className }: {
  open: () => void;
  active: boolean;
  className: string;
}) {
  const snapshot = useViewer(state => state.snapshot);
  const runTag = useViewer(state => state.runTag);
  const read = useResultNotices(state => state.read);
  const description = useId();
  // A delayed response for another execution must never light up this pipeline's button.
  const results = snapshot?.run_tag === runTag
    ? snapshot.results.map(result => ({ ...result, run_tag: snapshot.run_tag })) : [];
  const unread = unreadResults(results, read);
  const arrival = `${runTag}:${unread.map(result => result.result_id).sort((a, b) => a - b).join(',')}`;
  return <>
    <button type="button" aria-label="Results" aria-describedby={description}
      aria-current={active ? 'page' : undefined}
      className={className}
      onClick={() => { usePipelines.setState({ resultsScope: 'selected' }); open(); }}>
      <BarChart3 className="h-4 w-4 shrink-0" aria-hidden="true"/>
      <span>Results</span>
      {unread.length > 0 && <span key={arrival} className="results-new-badge ml-auto" aria-hidden="true"><i/>New</span>}
    </button>
    <span id={description} className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {unread.length ? `${unread.length} new ${unread.length === 1 ? 'result is' : 'results are'} ready for this execution. Open Results to review.` : 'Open the recorded results for this execution.'}
    </span>
  </>;
}
