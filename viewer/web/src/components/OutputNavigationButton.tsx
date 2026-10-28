import { useId } from 'react';
import { useViewer } from '../store/viewer';
import { useOutputNotices } from '../store/outputNotices';
import { outputNoticeKeys, type NoticeView } from '../lib/outputNotices';
import { VIEWS } from '../lib/views';
import { useTelemetryTotals } from './TelemetryTotals';

export default function OutputNavigationButton({view, open, active, className}: {
  view: NoticeView; open: () => void; active: boolean; className: string;
}) {
  const snapshot = useViewer(state => state.snapshot);
  const runTag = useViewer(state => state.runTag);
  const read = useOutputNotices(state => state.read);
  const totals = useTelemetryTotals(view === 'agents');
  const usage = totals.data?.executions.find(execution => execution.run_tag === runTag);
  const keys = snapshot?.run_tag === runTag ? outputNoticeKeys(snapshot, usage, view) : [];
  const unread = keys.filter(key => !read[key]);
  const description = useId();
  const {label, icon: Icon} = VIEWS[view];
  return <>
    <button type="button" aria-label={label} aria-describedby={description}
      aria-current={active ? 'page' : undefined} className={className} onClick={open}>
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true"/><span>{label}</span>
      {unread.length > 0 && <span key={unread.join('|')} className="results-new-badge ml-auto" aria-hidden="true"><i/>New</span>}
    </button>
    <span id={description} className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {unread.length ? `${unread.length} new ${label.toLowerCase()} ${unread.length === 1 ? 'update is' : 'updates are'} ready for this execution. Open ${label} to review.` : `Open the recorded ${label.toLowerCase()} for this execution.`}
    </span>
  </>;
}
