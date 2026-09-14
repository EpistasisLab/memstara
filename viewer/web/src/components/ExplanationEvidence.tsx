import type { Result } from "../types";

const percent = (value: number | null) => value === null ? "Not estimable" : `${(value * 100).toFixed(1)}%`;

export default function ExplanationEvidence({ result }: { result: Result }) {
  const evidence = result.evaluation?.explanation;
  if (!evidence?.operating_point && !evidence?.review_status) return null;
  const point = evidence.operating_point;
  return <section className="my-3 rounded-xl border border-paper-line bg-paper-panel p-3 text-sm" aria-label="Explainability evidence">
    <h3 className="font-bold">How to interpret this hypothesis</h3>
    {evidence.review_status && <p role="note" className="my-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
      Replace with reviewer’s original specification. This implementation is provisional and has not been reviewed by reviewer.
    </p>}
    {point && <>
      <p className="mt-2 text-xs font-bold">Prediction cutoff: {point.probability_cutoff} · held-out cohort</p>
      <div className="my-2 grid grid-cols-3 gap-2">
        {[["Sensitivity", percent(point.sensitivity)], ["Specificity", percent(point.specificity)], ["Precision", percent(point.precision)]].map(([label, value]) =>
          <div key={label} className="rounded bg-white p-2"><span className="block text-[12px] text-ink-faint">{label}</span><strong>{value}</strong></div>)}
      </div>
      <p className="text-xs">False alerts: {point.false_positive} · Missed positive outcomes: {point.false_negative}</p>
      <p className="mt-1 text-xs text-ink-faint">{point.selection}. {point.status}.</p>
    </>}
    {evidence.feature_effects?.map(effect => <div key={effect.feature} className="mt-3 border-t border-paper-line pt-2">
      <p className="font-mono text-xs font-bold">{effect.feature}</p>
      <p className="text-xs">Over {effect.range_start.toPrecision(4)}–{effect.range_end.toPrecision(4)}, the model’s mean predicted probability changes from {percent(effect.probability_before)} to {percent(effect.probability_after)} ({effect.direction}).</p>
      <p className="mt-1 text-xs text-ink-faint">Exploratory training-data response, not a causal effect or clinical cutoff. {effect.validation_needed}</p>
    </div>)}
  </section>;
}
