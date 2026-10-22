import { displayJson } from '../lib/displayText';
import type {SpecialistXai} from '../types';

export default function SpecialistEvidence({evidence}:{evidence?:SpecialistXai}) {
  if(!evidence)return null;
  return <section aria-label="Specialist attribution evidence" className="mt-3 space-y-3">
    {evidence.items.map(item=><div key={`${item.method}-${item.replicate}`} className="min-w-0 border-t border-paper-line pt-2">
      <strong>{item.method.toUpperCase()} · {item.model} · split {item.replicate}</strong>
      {item.status!=='completed'?<p role="status">Explanation unavailable ({item.error_type ?? item.status}). Do not infer feature effects.</p>:<>
        <p>{item.explainer} · {item.output_scale}</p>
        <p>{item.explained_count} sampled evaluation rows · {item.reference_count} training reference rows · seed {item.seed}.</p>
        {item.baseline!=null&&<p>SHAP baseline: {item.baseline.toFixed(5)}. Maximum additivity error: {item.max_additivity_error?.toExponential(2)}.</p>}
        {item.fidelity_r2&&<p>LIME local fidelity R²: mean {item.fidelity_r2.mean.toFixed(4)}, minimum {item.fidelity_r2.minimum.toFixed(4)}. {item.samples_per_row} neighborhood samples per row. This is not classifier accuracy.</p>}
        <p className="text-xs">Magnitude ranks describe this sample only. Signed averages show direction relative to the method’s reference; they do not establish causal effects.</p>
        <table className="w-full table-fixed text-xs" aria-label={`${item.method} ${item.model} attribution summary`}>
          <thead><tr><th className="w-1/2 text-left">Feature</th><th>Mean |value|</th><th>Signed mean</th></tr></thead>
          <tbody>{Object.entries(item.feature_summary??{}).sort((a,b)=>b[1].mean_absolute-a[1].mean_absolute).map(([name,v])=><tr key={name}>
            <td className="break-all">{name}</td><td className="text-center">{v.mean_absolute.toPrecision(4)}</td><td className="text-center">{v.mean_signed.toPrecision(4)}</td>
          </tr>)}</tbody>
        </table>
        <p className="mt-2 text-xs">{item.limitation}</p>
        <details><summary>Saved explanation identity and local artifact</summary><pre className="max-h-48 whitespace-pre-wrap break-all text-xs">{displayJson({id:item.explanation_id,path:item.artifact_path,sha256:item.artifact_sha256})}</pre></details>
      </>}
    </div>)}
  </section>;
}
