import type {Result} from '../types';
import {interpretationOutputs} from '../lib/interpretationOutputs';
import ReportBody from './ReportBody';

/** Status labels are UI metadata; each saved agent document is rendered verbatim. */
export default function InterpretationOutput({result, includeLimitations = true}: {result: Pick<Result, 'interpretation' | 'evaluation'>; includeLimitations?: boolean}) {
  const outputs = interpretationOutputs(result);
  if (!outputs.length) return <p>No interpretation was recorded for this analysis yet.</p>;
  return <>{outputs.map(output => <section key={output.slot} data-interpretation-slot={output.slot} className="min-w-0 border-t border-paper-line py-4 first:border-t-0 first:pt-0 last:pb-0">
    {(outputs.length > 1 || output.status !== 'done') && <p className="my-3 text-sm font-semibold">Interpreter {output.slot} · {output.skill} · {output.status}</p>}
    {output.text ? <ReportBody verbatim text={output.text}/> : <p>This perspective is not yet available.</p>}
    {includeLimitations && output.limitations && <details className="mt-3"><summary>Separately submitted limitations</summary><ReportBody verbatim text={output.limitations}/></details>}
  </section>)}</>;
}
