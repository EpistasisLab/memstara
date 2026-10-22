import { useCallback, useId, useLayoutEffect, useRef, useState } from 'react';
import { ArrowUpRight, ChevronDown, X } from 'lucide-react';
import { usePipelines } from '../store/pipelines';
import { useViewer } from '../store/viewer';
import { costLabel } from '../lib/loopUsage';
import type { WorkspaceCostState } from '../lib/useWorkspaceCost';
import './workspace-cost.css';

export default function WorkspaceCost({state}: {state: WorkspaceCostState}) {
  const pipelines = usePipelines(s => s.items);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const id = useId();
  const {cost, value, status, description, delayed, partial} = state;

  const place = useCallback(() => {
      if (!panel.current || !trigger.current) return;
      const anchor = trigger.current.getBoundingClientRect();
      const width = Math.min(400, window.innerWidth - 24);
      const top = Math.max(12, Math.min(anchor.bottom + 8, window.innerHeight - 132));
      panel.current.style.width = `${width}px`;
      panel.current.style.left = `${Math.max(12, Math.min(anchor.right - width, window.innerWidth - width - 12))}px`;
      panel.current.style.top = `${top}px`;
      panel.current.style.maxHeight = `${window.innerHeight - top - 12}px`;
  }, []);
  useLayoutEffect(() => {
    if (!open) return;
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
  }, [open, place]);

  // Inline scope and pricing explanations replace the automatic hover tooltip here.
  return <div className="workspace-cost" data-context-help-managed>
    <button ref={trigger} type="button" className="workspace-cost-trigger" popoverTarget={id}
      aria-haspopup="dialog" aria-controls={id} aria-expanded={open}
      aria-describedby={`${id}-amount ${id}-scope`}
      aria-label="Estimated total. Show pipeline cost breakdown">
      <span className="workspace-cost-heading"><span>Estimated total</span><strong id={`${id}-amount`}>{value}</strong><ChevronDown size={13} aria-hidden="true"/></span>
      <span id={`${id}-scope`} className="workspace-cost-scope">Latest executions · USD{status && <span className={delayed || partial ? 'cost-notice' : ''}>{status}</span>}</span>
    </button>
    <div ref={panel} id={id} popover="auto" role="dialog" aria-labelledby={`${id}-title`}
      className="workspace-cost-popover" onBeforeToggle={event => { if (event.newState === 'open') place(); }}
      onToggle={event => setOpen(event.newState === 'open')}>
      <header><h2 id={`${id}-title`}>Pipeline costs</h2><button type="button" popoverTarget={id} popoverTargetAction="hide" aria-label="Close pipeline costs"><X size={16}/></button></header>
      <p>Latest execution of each pipeline.</p>
      {(delayed || partial) && <p className="workspace-cost-notice" role="status">{description}</p>}
      <div className="workspace-cost-rows">
        <table><caption className="sr-only">Estimated costs in USD for the latest executions</caption>
          <thead><tr><th scope="col">Pipeline</th><th scope="col">Estimated cost</th></tr></thead>
          <tbody>{pipelines.map(pipeline => {
            const execution = cost?.executions.find(item => item.run_tag === pipeline.latest?.run_tag);
            const amount = execution ? costLabel(execution).replace(' · recorded subtotal', '') : pipeline.latest ? 'Not available' : 'Not started';
            return <tr key={pipeline.id}><th scope="row">{pipeline.name}</th><td>{amount}{execution?.status === 'partial' && <small>Partial estimate</small>}</td></tr>;
          })}</tbody>
          <tfoot><tr><th scope="row">{partial ? 'Recorded subtotal' : 'Total'}</th><td>{value}</td></tr></tfoot>
        </table>
      </div>
      {!pipelines.length && <p>No pipeline executions yet.</p>}
      {!!cost?.shared_agent_runs && <p>Shared agent execution records are counted once in the total.</p>}
      <footer><p>Motoro estimates, not actual charges.</p><button type="button" onClick={() => {
        panel.current?.hidePopover();
        useViewer.getState().setView('agents');
      }}>View in Telemetry<ArrowUpRight size={14}/></button></footer>
    </div>
  </div>;
}
