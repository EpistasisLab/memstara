import { usePipelines } from '../store/pipelines';
import { useViewer, useSnapshot } from '../store/viewer';

/** Label the records actually displayed, not a newly requested run still loading. */
export function useExecutionContext() {
  const snapshot = useSnapshot();
  const requested = useViewer(s => s.runTag);
  const items = usePipelines(s => s.items);
  const tag = snapshot?.run_tag ?? null;
  const owner = items.find(p => p.latest?.run_tag === tag);
  const name = owner?.name || snapshot?.run_configuration?.pipeline_name || 'Archived pipeline';
  const started = owner?.latest?.started;
  const date = started ? new Date(started) : null;
  const savedDate = tag?.match(/(?:^|_)(\d{4})(\d{2})(\d{2})T/)?.slice(1).join('-');
  const startedLabel = date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : savedDate ? `${savedDate} (saved run date)` : 'Start time unavailable';
  return { tag, name: tag ? name : 'No execution loaded', startedLabel, owner,
    loading: !!requested && requested !== tag,
    label: tag ? `${name} · ${startedLabel}` : 'No execution loaded' };
}

export default function ExecutionContext() {
  const context = useExecutionContext();
  const items = usePipelines(s => s.items);
  const error = useViewer(s => s.error);
  return <div className="execution-context">
    <div className="execution-context-row">
      <label>Pipeline to inspect
        <select aria-label="Pipeline to inspect" value={context.owner?.id ?? ''} onChange={e => usePipelines.getState().select(e.target.value)}>
          <option value="" disabled>{context.tag ? context.name : 'Choose a pipeline'}</option>
          {items.map(p => <option key={p.id} value={p.id}>{p.name}{p.latest ? '' : ' · not started'}</option>)}
        </select>
      </label>
      <div className="min-w-0"><p className="font-semibold">{context.name}</p>
        <p className="text-sm text-ink-soft">{context.tag ? `Execution started ${context.startedLabel} · local time` : 'Start a pipeline to record activity.'}</p></div>
    </div>
    <details className="mt-2 text-xs text-ink-soft"><summary className="cursor-pointer">What records am I viewing?</summary>
      <p className="mt-2">An execution is one session started with Play. It can contain many loops. These tabs follow the execution shown above. Selecting another pipeline opens its latest execution; this does not start or stop it. Results can also compare pipelines using its own scope buttons.</p>
      <p className="mt-2">Execution ID: <code>{context.tag || 'None'}</code></p>
    </details>
    {context.loading && <p role="status" className="mt-2 text-sm">Loading the requested execution. Records still shown belong to {context.label}.</p>}
    {error && <p role="status" className="mt-2 text-sm">Connection interrupted. Displayed records may be out of date.</p>}
  </div>;
}
