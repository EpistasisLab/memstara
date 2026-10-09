import TelemetryTotals, { useTelemetryTotals } from '../components/TelemetryTotals';
import ExperimentRegistry from '../components/ExperimentRegistry';
import ExecutionLogs from '../components/ExecutionLogs';
import ExecutionContext from '../components/ExecutionContext';
import Help from '../components/Help';
import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useViewer } from '../store/viewer';
import { SnapshotScope } from '../lib/SnapshotScope';
import { loopLabel } from '../lib/loopLabel';
import type { Snapshot } from '../types';
import AgentsTab from '../tabs/AgentsTab';
import AccessTab from '../tabs/AccessTab';
import TaskTab from '../tabs/TaskTab';
import FeedPanel from './FeedPanel';
import ResultsPanel from './ResultsPanel';

type Tab = 'Experiments' | 'Totals' | 'Agents' | 'Activity' | 'Logs' | 'Access' | 'Tasks' | 'Results';
type Loop = { number: number; status: string; tasks: number; results: number };
type LoopSnapshot = Snapshot & {
  telemetry: {loop: number | null; loops: Loop[]; legacy_attribution: boolean; unassigned_calls: number};
  loop_log: {lines: string[]; note: string; truncated: boolean};
};
const descriptions: Record<Tab, string> = {
  Experiments:'Database-backed experiment, combination and execution evidence across all registered runs.',
  Totals:'Pipeline, Loop, pipeline totals and totals across all pipelines.',
  Agents:'Agent calls, reasoning steps and usage for the selected scope.',
  Activity:'Recorded tool actions and agent text within the selected scope, shown in local time.',
  Logs:'Agent answers and console messages within the selected scope. Original wording is preserved.',
  Access:'Tools and resources accessed within the selected scope.',
  Tasks:'Tasks within the selected scope. Select one to inspect its evidence and handoffs.',
  Results:'Recorded results within the selected scope. Select a finding to review its evidence.',
};
export default function TelemetryPanel() {
  const totals=useTelemetryTotals();
  const runTag = useViewer(s => s.runTag);
  const [selection,setSelection] = useState<{tag:string|null;loop:number|null}>({tag:null,loop:null});
  const loop = selection.tag === runTag ? selection.loop : null;
  const [tab,setTab] = useState<Tab>('Agents');
  const [chosenTask,setChosenTask] = useState<number|null>(null);
  const [record,setRecord] = useState<{key:string;data:LoopSnapshot}|null>(null);
  const [failure,setFailure] = useState<{key:string;text:string}|null>(null);
  const [catalog,setCatalog] = useState<{tag:string;loops:Loop[]}|null>(null);
  const key = `${runTag ?? ''}:${loop ?? 'all'}:${tab}`;
  const data = record?.key === key ? record.data : null;
  const error = failure?.key === key ? failure.text : '';
  const choices = catalog?.tag === runTag ? catalog.loops : [];
  const selectLoop = (value:number|null) => {setChosenTask(null);setSelection({tag:runTag,loop:value});};
  useEffect(() => {
    if(!runTag||tab==='Experiments')return;
    let disposed=false;let timer:ReturnType<typeof setTimeout>;let request:AbortController|null=null;
    const poll=async()=>{
      request=new AbortController();let retryDelay=4000;const deadline=setTimeout(()=>request?.abort(),10000);
      try {
        const response=await fetch(`/api/telemetry?run_tag=${encodeURIComponent(runTag)}${loop===null?'':`&loop=${loop}`}&view=${encodeURIComponent(tab)}`,{signal:request.signal});
        const body=await response.json();
        if(response.status===202&&body.detail?.status==='loading'&&body.detail.run_tag===runTag&&body.detail.loop===loop){retryDelay=1000;if(!disposed)setFailure(null);return;}
        if(!response.ok)throw Error(body.detail||'Telemetry is temporarily unavailable.');
        if(body.run_tag!==runTag||body.telemetry?.loop!==loop)throw Error('The response did not match the selected scope.');
        if(!disposed){setRecord({key,data:body});setCatalog({tag:runTag,loops:body.telemetry.loops});setFailure(null);}
      }catch(e){if(!disposed)setFailure({key,text:e instanceof Error?e.name==='AbortError'?'Telemetry timed out. Retrying automatically.':e.message:'Telemetry is temporarily unavailable.'});}
      finally{clearTimeout(deadline);if(!disposed)timer=setTimeout(poll,retryDelay);}
    };
    void poll();return()=>{disposed=true;clearTimeout(timer);request?.abort();};
  },[runTag,loop,key,tab]);
  const scope = loop===null?'All loops':`Loop ${loop}`;
  const index = choices.findIndex(c=>c.number===loop);
  const taskId = data?.board.tasks.some(t=>t.task_id===chosenTask)?chosenTask:null;
  return <SnapshotScope.Provider value={data ?? undefined}><div className="telemetry-workspace flex h-full min-h-0 flex-col">
    <div className="telemetry-scope-region" role="region" aria-label="Pipeline and loop selection" tabIndex={0}><ExecutionContext/>
      <div className="telemetry-loop-controls">
        <label>Loop<select aria-label="Loop to inspect" disabled={!runTag||!choices.length} value={loop??'all'} onChange={e=>selectLoop(e.target.value==='all'?null:Number(e.target.value))}>
          <option value="all">All loops</option>
          {choices.map(c=><option key={c.number} value={c.number}>Loop {c.number} · {c.status.replaceAll('_',' ')} · {c.results} result{c.results===1?'':'s'}</option>)}
        </select></label>
        <div className="flex gap-2"><button aria-label="Previous loop" disabled={index<=0} onClick={()=>selectLoop(choices[index-1].number)}><ChevronLeft size={16}/>Previous</button>
          <button aria-label="Next loop" disabled={!choices.length||index>=choices.length-1} onClick={()=>selectLoop(choices[index+1].number)}>Next<ChevronRight size={16}/></button></div>

      </div>
    </div>
    <nav aria-label="Telemetry tabs" className="flex flex-wrap gap-1 border-b border-paper-line p-2">{(Object.keys(descriptions) as Tab[]).map(name=><Help key={name} topic={name} description={descriptions[name]}><button aria-pressed={tab===name} className={`rounded px-3 py-1.5 text-xs ${tab===name?'bg-accent text-accent-contrast':'text-ink-soft'}`} onClick={()=>setTab(name)}>{name}</button></Help>)}</nav>
    <p className="border-b border-paper-line px-3 py-2 text-sm text-ink-soft"><strong>{scope}</strong> · {descriptions[tab]}</p>
    {error&&<p role="alert" className="px-3 py-2 text-sm text-ink-soft">{error}{data?' Showing the last available records for this same scope.':''}</p>}
    {data?.stale&&<p role="status" className="px-3 py-2 text-sm text-ink-soft">{data.health.core.up && data.health.memstara.up ? 'Refreshing this scope. Previously loaded records remain visible until the update finishes.' : 'Updates are delayed. This is not confirmation of an empty or completed loop.'}</p>}
    {data?.telemetry.legacy_attribution&&<p className="px-3 py-2 text-xs text-ink-soft">Legacy archive: agent calls are grouped using recorded loop start times. New executions record the loop directly.</p>}
    {!!data?.telemetry.unassigned_calls&&<p className="px-3 py-1 text-xs text-ink-soft">{data.telemetry.unassigned_calls} execution-wide or unassigned calls are included only in All loops.</p>}
    <div key={tab==='Experiments'?'experiments':key} tabIndex={0} role="region" aria-label="Telemetry details" className="telemetry-tab-body min-h-0 flex-1 overflow-auto">
      {tab==='Experiments'?<ExperimentRegistry/>:tab==='Totals'?<TelemetryTotals data={totals.data} error={totals.error} runTag={runTag} loop={loop}/>:!runTag?<p className="p-5">Choose a pipeline with a recorded execution.</p>:!data?<p role="status" className="p-5">{error?'Waiting to retry this selection…':`Preparing ${scope.toLowerCase()} history. Large executions take longer on their first load…`}</p>:<>
        {tab==='Agents'&&<AgentsTab/>}{tab==='Activity'&&<FeedPanel/>}{tab==='Access'&&<AccessTab/>}
        {tab==='Results'&&<ResultsPanel telemetry/>}
        {tab==='Tasks'&&<><label className="block p-3 text-sm">Task<select aria-label="Task in selected loop" className="ml-2 max-w-full rounded border border-paper-line bg-paper p-2" value={taskId??''} onChange={e=>setChosenTask(e.target.value?Number(e.target.value):null)}><option value="">Select a task</option>{data.board.tasks.map(t=><option key={t.task_id} value={t.task_id}>#{t.task_id} · {loopLabel(t,data.run_configuration?.trials)} · {t.task_type} · {t.status}</option>)}</select></label><TaskTab taskId={taskId}/></>}
        {tab==='Logs'&&<ExecutionLogs runTag={runTag} loop={loop} lines={data.loop_log.lines} note={data.loop_log.note}/>}
      </>}
    </div>
  </div></SnapshotScope.Provider>;
}
