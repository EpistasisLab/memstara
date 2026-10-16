import {novelty} from '../lib/novelty';
export default function NoveltyEvidence({value}: {value: unknown}) {
 const n = novelty(value);
 return <section className="my-3 rounded-lg border border-paper-line p-3" data-testid="novelty-evidence">
  <strong>KG novelty proxy · {n.score === null ? n.status : `${Math.round(n.score * 100)}% predicted-path share`}</strong>
  {n.score !== null && <meter aria-label="Predicted-path share" min={0} max={1} value={n.score} className="block w-full mt-2"/>}
  <p className="text-xs mt-2">Paths containing predicted edges / fully annotated paths. Higher values prioritize predicted-path hypotheses for review, not proven new discoveries. AUROC is separate.</p>
  <p className="text-xs">Annotation coverage: {Math.round(n.coverage*100)}% · {n.counts.map(c=>`${c.key}: ${c.count}`).join(' · ')}</p>
  <details className="mt-2"><summary>Inspect paths and calculation</summary>
   <p className="text-xs">Policy: predicted_path_fraction_v1. Mixed paths count once as containing predicted edges. Only complete evidence is ranked; missing evidence is not zero novelty. Path use is declared by the agent, checked against recorded source IDs, and still requires scientific review.</p>
   {n.diagnostics.length > 0 && <p className="text-xs">{n.diagnostics.join(', ')}</p>}
   {n.paths.map((p,i)=><article className="mt-2 border-t border-paper-line pt-2" key={i} style={{overflowWrap:'anywhere'}}>
    <strong>{p.status || 'unknown'} · {p.source} / {p.id}</strong><p>{p.label}</p><p>{p.rationale}</p>
    <small>{p.location} · {p.hash}</small>{p.diagnostic && <p>{p.diagnostic}</p>}
   </article>)}
   {!n.paths.length && <p>No path-level attribution was recorded for this hypothesis.</p>}
  </details>
 </section>;
}
