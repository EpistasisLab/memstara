import type { EvaluationPlan } from '../store/control';
import { evaluationPlanError } from '../lib/evaluationPlan';

const field = 'mt-2 block w-full min-w-0 rounded-lg border border-paper-line bg-paper px-3 py-2 text-sm text-ink disabled:opacity-50';
export default function EvaluationSettings({value, onChange, disabled = false}: {
  value: EvaluationPlan; onChange: (value: EvaluationPlan) => void; disabled?: boolean;
}) {
  const error = evaluationPlanError(value);
  const update = (key: keyof EvaluationPlan, number: number) => onChange({...value, [key]: number});
  return <fieldset disabled={disabled} className="compact-evaluation min-w-0 space-y-3 rounded-lg border border-paper-line p-4" aria-label="ML evaluation settings">
    <legend className="px-1 text-sm font-semibold">Model and evaluation</legend>
    <p className="text-sm text-ink-muted">These settings are saved with the pipeline and used for its ML evaluations. Split evaluations and model candidates are additional fits within a Loop, not additional pipeline Loops.</p>
    <div className="grid gap-4" style={{gridTemplateColumns:'repeat(auto-fit, minmax(min(100%, 240px), 1fr))'}}>
      <label className="min-w-0 text-sm font-medium">ML model
        <select aria-label="ML model" className={field} value={value.engine} onChange={e=>onChange({...value,engine:e.target.value})}>
          <option value="xgboost">XGBoost</option><option value="random_forest">Random forest</option><option value="logistic_regression">Logistic regression</option>
        </select><span className="mt-1 block text-xs font-normal text-ink-muted">The predictive model trained on selected features, separate from the agents’ LLM.</span>
      </label>
      <label className="min-w-0 text-sm font-medium">Random seed
        <input aria-label="Random seed" className={field} type="number" required min={0} max={2147483647} step={1} value={Number.isFinite(value.seed)?value.seed:''} onChange={e=>update('seed',e.target.valueAsNumber)}/>
        <span className="mt-1 block text-xs font-normal text-ink-muted">Controls randomized splitting and model fitting. Default: 42. Additional split evaluations use successive seeds.</span>
      </label>
      <label className="min-w-0 text-sm font-medium">Hold-out data (%)
        <input aria-label="Hold-out data (%)" className={field} type="number" required min={10} max={50} step="any" value={Number.isFinite(value.test_size)?Number((value.test_size*100).toFixed(8)):''} onChange={e=>update('test_size',e.target.valueAsNumber/100)}/>
        <span className="mt-1 block text-xs font-normal text-ink-muted">10–50% of exploration data is held out per split for scoring. Default: 25%. This is separate from the 20% validation reserve.</span>
      </label>
      <label className="min-w-0 text-sm font-medium">Training cross-validation folds
        <select aria-label="Training cross-validation folds" className={field} value={value.folds} onChange={e=>update('folds',Number(e.target.value))}>
          <option value={0}>Automatic — only when searching</option>{[2,3,4,5,6,7,8,9,10].map(n=><option key={n} value={n}>{n} folds</option>)}
        </select><span className="mt-1 block text-xs font-normal text-ink-muted">Automatic means no CV for one candidate, or 3 training folds for multiple candidates. Small class counts may reduce folds or prevent search; actual execution is recorded.</span>
      </label>
      <label className="min-w-0 text-sm font-medium">Split evaluations
        <input aria-label="Split evaluations" className={field} type="number" required min={1} max={10} step={1} value={Number.isFinite(value.replicates)?value.replicates:''} onChange={e=>update('replicates',e.target.valueAsNumber)}/>
        <span className="mt-1 block text-xs font-normal text-ink-muted">1–10 train/test evaluations. More than one checks sensitivity to different splits. This is distinct from reproducing the same computation.</span>
      </label>
      <label className="min-w-0 text-sm font-medium">Hyperparameter candidates
        <input aria-label="Hyperparameter candidates" className={field} type="number" required min={1} max={10} step={1} value={Number.isFinite(value.search_trials)?value.search_trials:''} onChange={e=>update('search_trials',e.target.valueAsNumber)}/>
        <span className="mt-1 block text-xs font-normal text-ink-muted">1 uses the preset model settings. 2–10 compares predefined candidates using training CV, not hold-out performance.</span>
      </label>
    </div>
    <p className="text-xs text-ink-muted">More splits, folds and candidates increase computation. Baseline comparisons, ablations and reproducibility checks can add further fits. New executions reserve 20% of the dataset for later validation; these controls apply within the remaining exploration data.</p>
    <details className="text-sm"><summary className="cursor-pointer font-medium">Which model settings can change?</summary>
      <p className="mt-2 text-ink-muted">{value.engine==='xgboost'?'XGBoost uses predefined combinations of tree depth and tree count.':value.engine==='random_forest'?'Random forest uses predefined combinations of maximum depth and tree count.':'Logistic regression uses predefined regularization strengths (C), with a maximum of 2000 solver iterations.'} Individual hyperparameter values and the 0.5 prediction cutoff are not editable here. The selected values are recorded with each result.</p>
    </details>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </fieldset>;
}
