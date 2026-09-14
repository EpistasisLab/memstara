import { useState } from 'react';
import { useBoard, useViewer } from '../store/viewer';
import AgentsTab from '../tabs/AgentsTab';
import AccessTab from '../tabs/AccessTab';
import TaskTab from '../tabs/TaskTab';
import LogPanel from './LogPanel';
import FeedPanel from './FeedPanel';
import ResultsPanel from './ResultsPanel';
const panes={Agents:AgentsTab,Activity:FeedPanel,Logs:LogPanel,Access:AccessTab,Tasks:TaskTab,Results:ResultsPanel};
export default function TelemetryPanel(){
 const board=useBoard();
 const selected=useViewer(s=>s.selectedTask);
 const health=useViewer(s=>s.snapshot?.health);
 const [tab,setTab]=useState<keyof typeof panes>('Agents');const Body=panes[tab];
 return <div className="flex h-full min-h-0 flex-col"><nav className="flex flex-wrap gap-1 border-b border-paper-line p-2">{Object.keys(panes).map(name=><button key={name} aria-pressed={tab===name} className={`rounded px-3 py-1.5 text-xs ${tab===name?'bg-accent text-accent-contrast':'text-ink-soft'}`} onClick={()=>setTab(name as keyof typeof panes)}>{name}</button>)}</nav>{health && !health.core.up && tab!=="Agents" && <p role="alert" className="px-3 py-2 text-sm text-ink-soft">Agent telemetry is temporarily unavailable. Displayed records may be out of date.</p>}{tab==="Tasks" && <label className="p-3 text-sm">Task<select className="ml-2 max-w-full rounded border border-paper-line bg-paper p-2" value={selected??""} onChange={e=>useViewer.setState({selectedTask:e.target.value?Number(e.target.value):null})}><option value="">Select a task</option>{board?.tasks.map(t=><option key={t.task_id} value={t.task_id}>#{t.task_id} · Trial {t.trial} · {t.task_type} · {t.status}</option>)}</select></label>}<div className="min-h-0 flex-1 overflow-auto"><Body/></div></div>;
}
