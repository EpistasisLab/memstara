import { displayText } from '../lib/displayText';
import type {ExplanationEvidence} from '../types';

export default function ExpertExplanationEvidence({evidence}:{evidence?:ExplanationEvidence|null}) {
  if(!evidence)return null;
  const reports=evidence.reports??[evidence];
  return <section aria-label="Explanation provenance" className="min-w-0 space-y-2 px-3 pb-3 text-xs">
    <p>Explanation evidence: {evidence.status}</p>
    {evidence.aggregation&&<p>{evidence.aggregation}</p>}
    {!!evidence.missing_loops?.length&&<p role="status">Incomplete Explanation Loops: {evidence.missing_loops.join(', ')}</p>}
    {reports.map((item,index)=><details key={`${item.loop}-${item.expert}-${index}`} className="min-w-0">
      <summary>{item.expert==='addiction'?'Addiction Expert':item.expert==='hiv'?'HIV Expert':'Explanation'}{item.loop!=null?` · Loop ${item.loop}`:''} · {item.status}</summary>
      <p className="break-all">Knowledge sources: {displayText(item.database_ids?.join(', '))||'Not available'}</p>
      <p>Interpretation methods: {item.interpretation_methods?.map(s=>s.toUpperCase()).join(', ')||'Not available'} · selected model</p>
      <p>Source task IDs: {item.task_ids?.join(', ')||'Not available'}</p>
      <p className="break-all">Retrieved references: {displayText(item.citations?.join(', '))||'Not available'}</p>
      <p>References identify retrieved evidence; they do not establish clinical validation.</p>
    </details>)}
  </section>;
}
