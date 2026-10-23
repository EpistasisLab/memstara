/** Match the execution iteration, never a previous replicate or another run. */
export function experimentHypothesis(
  runTag: string, iteration: number | undefined, active: boolean, trials: number | undefined,
  events: {run_tag:string; iteration:number|null; trial:number|null; stage:string; detail:string; at:string|null}[],
  results: {run_tag?:string; iteration?:number|null; trial:number; hypothesis:string; result_id:number}[],
): string {
  const position = (value:number|null|undefined, trial:number|null) =>
    value ?? (trial !== null && trial >= 0 && trials && trials > 0 ? Math.floor(trial / trials) + 1 : undefined);
  const candidates = [
    ...events.filter(e=>e.run_tag===runTag && e.stage==='hypothesis' && e.detail.trim())
      .map(e=>({iteration:position(e.iteration,e.trial),text:e.detail,time:Date.parse(e.at??'')||0,id:0})),
    ...results.filter(r=>r.run_tag===runTag && r.hypothesis.trim())
      .map(r=>({iteration:position(r.iteration,r.trial),text:r.hypothesis,time:0,id:r.result_id})),
  ];
  const current = iteration && iteration > 0 ? iteration : active ? undefined :
    Math.max(0,...candidates.map(c=>c.iteration??0));
  if (!runTag || !current) return '';
  return candidates.filter(c=>c.iteration===current)
    .sort((a,b)=>b.time-a.time || b.id-a.id)[0]?.text ?? '';
}
