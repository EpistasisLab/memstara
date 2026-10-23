export default function BaselineSettings({value,onChange}:{value:string[];onChange:(value:string[])=>void}) {
  return <div className="baseline-settings space-y-2 rounded-lg border border-paper-line p-3">
    <label className="block text-sm font-semibold">Fixed baseline (optional, opt-in)
      <textarea aria-label="Fixed clinical baseline columns" rows={3} className="mt-2 block w-full min-w-0 rounded border border-paper-line bg-paper px-3 py-2 text-sm text-ink"
        value={value.join('\n')} onChange={e=>onChange(e.target.value.split('\n'))} placeholder="One exact dataset column name per line"/>
    </label>
    <p className="text-xs text-ink-soft">These predictors stay fixed across replicates. Do not include the prediction target. Column names are checked before execution. Blank lines are ignored.</p>
    <p className="text-xs text-ink-soft">Each replicate compares this baseline, baseline + hypothesis predictors, and removal of each mapped concept group using the same evaluation conditions. Leave this blank to train on hypothesis-selected predictors only. The reference predicts training prevalence only. The applied predictors are recorded in the results.</p>
    <p className="text-xs text-ink-soft">Additional model fits take time. More features are not automatically better; follow-up questions may add, retain, replace or remove justified concepts.</p>
  </div>;
}
