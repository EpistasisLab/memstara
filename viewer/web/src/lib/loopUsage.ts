import type { ExecutionUsage } from '../components/TelemetryTotals';
export function usageDuration(seconds:number|null|undefined):string {
  if(seconds==null||!Number.isFinite(seconds))return 'Not recorded';
  const total=Math.round(seconds);
  return total<60?`${total}s`:`${Math.floor(total/60)}m ${total%60}s`;
}
export const usageCost=(value:{usd:number;status:string})=>`$${value.usd.toFixed(4)}${value.status==='complete'?'':' (partial)'}`;
export function loopUsageMarkdown(execution:ExecutionUsage|undefined,updatedAt?:string,error?:string):string {
  const title='\n\n---\n\n## Measured Loop performance and usage\n\n';
  if(!execution)return title+'System telemetry was unavailable for this execution at export. Missing usage is not zero.\n';
  const s=execution.loop_summary;
  const mean=s?.sample_count?`Completed-Loop averages (n=${s.sample_count}): ${usageDuration(s.seconds?.mean)}, $${s.usd?.mean.toFixed(4)} estimated USD, ${Math.round(s.tokens?.mean??0).toLocaleString()} tokens.\n\n`:'No fully measured completed Loops are available for an average.\n\n';
  return title+`Execution: ${execution.run_tag}\n\nRecorded LLM: ${execution.model??"not recorded"}\n\nUsage snapshot: ${updatedAt??'not recorded'}${error?' (last available; refresh failed)':''}.\n\n`+mean+
    '| Loop | Outcome | Wall-clock time | Tokens | Estimated cost (USD) | Measurement |\n| --- | --- | --- | --- | --- | --- |\n'+execution.loops.map(l=>`| ${l.number} | ${l.status} | ${usageDuration(l.seconds)} | ${l.tokens.toLocaleString()}${l.tokens_status==='partial'?' (partial)':''} | ${usageCost(l.cost)} | ${l.duration_basis}; ${l.attribution??'unknown'} attribution |`).join('\n')+
    `\n\n${s?.basis??''}\n\nExecution-wide or unassigned calls (excluded from Loop averages): ${execution.unassigned?.calls??0}; estimated cost ${usageCost(execution.unassigned?.cost??{usd:0,status:'partial'})}.\n\nCosts are recorded LLM estimates, not invoices or total infrastructure cost. Tokens include recorded input and output usage, including retries. Parallel agent-call durations are not added together. Final execution-wide reporting is shown separately when it has no Loop attribution.\n`;
}
