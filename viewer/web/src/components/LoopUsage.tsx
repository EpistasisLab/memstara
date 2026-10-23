import {identityLabel} from '../lib/replicateIdentity';
import { Clock3, Coins, Hash } from 'lucide-react';
import type { ExecutionUsage } from './TelemetryTotals';
import { costLabel, usageDuration, usageCost } from '../lib/loopUsage';
export default function LoopUsage({execution,error,updatedAt}:{execution?:ExecutionUsage;error?:string;updatedAt?:string}) {
  const summary=execution?.loop_summary;
  return <section className="loop-usage" aria-label="Replicate performance and usage">
    <header><h3>Replicate performance & usage</h3><p>Measured time, estimated LLM cost and input + output tokens for this execution.</p></header>
    {error&&<p role="status" className="loop-usage-note">Usage refresh unavailable. {execution?'Showing the last available measurements.':'Missing measurements are not zero.'}</p>}
    {execution?.model&&<p className="loop-usage-note">Recorded LLM: {execution.model}{execution.provider?` · ${execution.provider}`:""}</p>}
    {!execution?<p className="loop-usage-note">{updatedAt?'No matching usage record for this execution.':'Loading usage measurements…'}</p>:<>
      <p className="loop-usage-cohort"><strong>Average per completed Replicate</strong> · {summary?.sample_count??0} fully measured of {summary?.completed_count??0} completed Replicates</p>
      <dl className="loop-usage-averages">{[
        {label:'Wall-clock time',icon:Clock3,value:summary?.seconds?usageDuration(summary.seconds.mean):'Not available',range:summary?.seconds?`${usageDuration(summary.seconds.min)}–${usageDuration(summary.seconds.max)}`:''},
        {label:'Estimated cost / Replicate',icon:Coins,value:summary?.usd?costLabel({usd:summary.usd.mean,status:'complete'}):'Not available',range:summary?.usd?`$${summary.usd.min.toFixed(4)}–$${summary.usd.max.toFixed(4)}`:''},
        {label:'Tokens / Replicate',icon:Hash,value:summary?.tokens?Math.round(summary.tokens.mean).toLocaleString():'Not available',range:summary?.tokens?`${summary.tokens.min.toLocaleString()}–${summary.tokens.max.toLocaleString()}`:''},
      ].map(m=><div key={m.label}><dt><m.icon size={16}/>{m.label}</dt><dd>{m.value}{m.range&&<small className="block">Observed range: {m.range}</small>}</dd></div>)}</dl>
      <p className="loop-usage-note">{summary?.basis} {summary?.excluded_completed??0} completed Replicates lack full measurement; {summary?.other_loops??0} other Replicates are excluded.</p>
      <div className="loop-usage-table" tabIndex={0} role="region" aria-label="Replicate usage table; scroll for more rows or columns"><table><caption>Every recorded Replicate · {execution.loops.length} Replicates</caption><thead><tr>{['Pipeline · Replicate','Outcome','Wall-clock time','Estimated USD','Tokens'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{execution.loops.map(l=><tr key={l.number}><th scope="row">{identityLabel(l)}</th><td>{l.status==='recorded'?'Archived · outcome unknown':l.status?.replaceAll('_',' ')}</td><td>{usageDuration(l.seconds)}<small>{l.duration_basis?.includes('approximate')?'Approximate span':l.status==='running'||l.status==='analysis_complete'?'Elapsed so far':'Recorded boundaries'}</small></td><td>{usageCost(l.cost)}{l.cost.missing_costs>0&&<small>{l.cost.missing_costs} unpriced agent executions</small>}{l.attribution==='approximate'&&<small>Legacy attribution</small>}</td><td>{l.tokens.toLocaleString()}{l.tokens_status==='partial'&&<small>Partial usage</small>}</td></tr>)}</tbody></table></div>
      {!!execution.unassigned?.calls&&<p className="loop-usage-note"><strong>Execution-wide / unassigned usage:</strong> {execution.unassigned.calls} agent executions · {costLabel(execution.unassigned.cost)} · {execution.unassigned.tokens.toLocaleString()} tokens{execution.unassigned.tokens_status==='partial'?' (partial)':''}. Includes reporting without a Replicate assignment; excluded from Replicate averages.</p>}
      <footer>Cost is an estimate, not an invoice or an infrastructure bill. Averages describe this recorded sample, not a guaranteed runtime or price. Updated {updatedAt?new Date(updatedAt).toLocaleString():'not recorded'} · refreshes every 6 seconds.</footer>
    </>}
  </section>;
}
