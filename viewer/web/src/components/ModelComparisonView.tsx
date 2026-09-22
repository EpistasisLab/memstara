import type { ModelComparison } from '../types';
export default function ModelComparisonView({comparison:c}:{comparison?:ModelComparison}) {
  if(!c)return <section className="result-chart-card"><h4>Incremental hypothesis value</h4><p>No paired model comparison was recorded for this historical result.</p></section>;
  return <section className="result-chart-card model-comparison" aria-label="Paired model comparisons"><h4>Did the hypothesis add predictive value?</h4>
    <p>{c.baseline_configured?'Compared against your fixed clinical predictors.':'Clinical baseline not configured. The reference uses training prevalence only.'} {c.status==='partial'?'Some comparisons failed; completed measurements are retained.':''}</p>
    <div className="space-y-4">{c.variants.map(v=><div key={v.id} className="border-b border-paper-line py-3">
      <div className="flex flex-wrap justify-between gap-2"><strong>{v.label}</strong><span>{v.status==='completed'&&Number.isFinite(v.auc)?`AUC ${v.auc!.toFixed(3)}`:v.status.replaceAll('_',' ')}</span></div>
      {v.auc!=null&&Number.isFinite(v.auc)&&<div className="result-rate-track mt-2" aria-hidden="true"><i style={{width:`${Math.max(0,Math.min(1,v.auc))*100}%`}}/></div>}
      {v.delta_from_baseline!=null&&<p className="text-sm">Added value over baseline: {v.delta_from_baseline>=0?'+':''}{v.delta_from_baseline.toFixed(3)} AUC</p>}
      {v.id.startsWith('ablation')&&v.delta_from_full!=null&&<p className="text-sm">After removing this group: {v.delta_from_full>=0?'+':''}{v.delta_from_full.toFixed(3)} AUC relative to the full model. A negative value means performance fell.</p>}
      <details className="mt-2 text-sm"><summary className="cursor-pointer">{v.features.length} predictors · View exact inputs</summary><ul className="mt-2 space-y-1">{v.features.map(f=><li key={f} className="break-words">{f}</li>)}</ul>{!v.features.length&&<p>No predictor columns.</p>}{v.reason&&<p>{v.reason}</p>}{v.error_type&&<p>Comparison failed ({v.error_type}); no delta is inferred.</p>}</details>
    </div>)}</div>
    <p className="result-caveat mt-3">{c.parameters_policy}. {c.group_policy}. {c.scope}. Differences are descriptive and do not establish statistical significance.</p>
  </section>;
}
