import { lazy, Suspense } from "react";
import { precisionExplanation, splitEvidence } from '../lib/metricEvidence';
import ValidationStatus from './ValidationStatus';
const ReportBody = lazy(() => import("./ReportBody"));

function FormattedNote({text}:{text:string}) { return <Suspense fallback={<p>{text}</p>}><ReportBody origin="rule" text={text} /></Suspense>; }
import type { Result } from "../types";

const percent = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? "Not estimable" : `${(value * 100).toFixed(1)}%`;

export default function ExplanationEvidence({ result }: { result: Result }) {
  const evidence = result.evaluation?.explanation;
  const recorded = result.evaluation?.evaluation;
  const reproducibility = recorded?.reproducibility;
  const splits = splitEvidence(result);
  const reproducibilityNote = <div className="my-3 rounded-xl border border-paper-line bg-paper-panel p-4 text-sm">
    <h3 className="font-bold">ML reproducibility: {reproducibility?.status === "verified" ? "Verified refit" : reproducibility ? "Not verified" : "Not recorded"}</h3>
    <p className="mt-2 text-ink-soft">{reproducibility?.status === "verified"
      ? "Independent training with the same input, split and model settings produced exactly the same hold-out predictions in the recorded environment."
      : "There is no successful recorded refit verification for this result. This does not by itself establish that it cannot be reproduced."}</p>
    <p className="mt-2 text-ink-soft"><strong>Robustness across splits:</strong> {splits.summary}</p>
    <p className="mt-2 text-xs text-ink-soft">Requested evaluations: {typeof splits.requested === 'number' ? splits.requested : 'not recorded'} · Recorded: {splits.runs.length} · Distinct splits: {splits.unique}</p>
    {splits.runs.length > 0 && <details className="mt-2"><summary className="cursor-pointer font-semibold">Recorded split evaluations</summary><ul className="mt-2 space-y-1">{splits.runs.map((r,i) => <li key={i}>Split evaluation {i+1} · seed {r.seed} · AUC {r.auc.toFixed(4)} · training CV folds {r.cv_folds ?? 'not recorded'}</li>)}</ul></details>}
    <p className="mt-2 text-xs text-ink-soft">ML verification does not verify regenerated agent text or clinical validity. Historical report wording is preserved.</p>
  </div>;
  if (!evidence) return <><ValidationStatus result={result}/>{reproducibilityNote}<p className="mt-3 text-sm text-ink-soft">No detailed explainability evidence was recorded for this analysis.</p></>;
  const point = evidence.operating_point;
  return <section className="explanation-evidence my-3 rounded-xl border border-paper-line bg-paper-panel p-4 text-sm" aria-label="Explainability evidence">
    <h3 className="font-bold">How to interpret this hypothesis</h3>
    <ValidationStatus result={result}/>
    {reproducibilityNote}

    {point && <>
      <p className="mt-2 text-xs font-bold">Prediction cutoff: {point.probability_cutoff} · held-out cohort</p>
      <div className="explanation-metric-grid">
        {[["Sensitivity", percent(point.sensitivity)], ["Specificity", percent(point.specificity)], ["Precision", percent(point.precision)]].map(([label, value]) =>
          <div key={label} className="rounded bg-white p-2"><span className="block text-[12px] text-ink-faint">{label}</span><strong>{value}</strong></div>)}
      </div>
      <p className="text-xs">False alerts: {point.false_positive} · Missed positive outcomes: {point.false_negative}</p>
      {precisionExplanation(point) && <p className="mt-2 text-sm" data-testid="precision-reason"><strong>Why precision is unavailable: </strong>{precisionExplanation(point)}</p>}
      <FormattedNote text={[point.selection, point.status].filter(Boolean).join("\n\n")} />
    </>}
    {evidence.feature_effects?.map(effect => <div key={effect.feature} className="mt-3 border-t border-paper-line pt-2">
      <p className="break-words text-sm font-semibold">{effect.feature}</p>
      <p className="text-xs">Over {(Number.isFinite(effect.range_start) ? effect.range_start.toPrecision(4) : "not recorded")}–{(Number.isFinite(effect.range_end) ? effect.range_end.toPrecision(4) : "not recorded")}, the model’s mean predicted probability changes from {percent(effect.probability_before)} to {percent(effect.probability_after)} ({effect.direction}).</p>
      <p className="mt-2 text-sm text-ink-soft">Exploratory training-data response, not a causal effect or clinical cutoff.</p><FormattedNote text={effect.validation_needed || "Validation requirements were not recorded."} />
    </div>)}
    {evidence.scope && <FormattedNote text={evidence.scope} />}
    {evidence.actionability && <><h4 className="mt-4 font-semibold">Applicability and limitations</h4><FormattedNote text={evidence.actionability} /></>}
  </section>;
}
