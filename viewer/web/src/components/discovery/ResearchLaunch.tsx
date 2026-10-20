import {usePipelines} from '../../store/pipelines';
import {useViewer} from '../../store/viewer';
export default function ResearchLaunch() {
 const state=usePipelines();
 return <section className="universe-section research-launch" aria-label="Research workflow">
  <div className="universe-tools"><button disabled={state.busy} onClick={()=>void state.add()} aria-label="Add pipeline — set up research">New research</button>
   <button onClick={()=>useViewer.getState().setView('scene')}>View floor plan</button></div>
  {state.error&&<p role="alert">{state.error}</p>}
  <details className="research-controls"><summary>Pipeline controls · {state.items.length} configured · {state.items.filter(p=>p.running).length} active</summary><div className="research-pipelines">{state.items.map(p=><article key={p.id} className="universe-section">
   <strong>{p.name}</strong><p>{p.running?(p.running.pause_requested?'Pause requested':p.running.execution_state||'Running'):p.latest?'Saved execution · inspect its recorded status':'Ready to start'}</p>
   {!p.latest&&!p.running&&<button disabled={state.busy||!!state.pendingStart} onClick={()=>void state.play(p.id)}>Go · {p.name}</button>}
   {p.running&&<button disabled={state.busy} onClick={()=>void state.pause(p.id,!p.running?.pause_requested)}>{p.running.pause_requested?'Resume':'Pause'} · {p.name}</button>}
   <button onClick={()=>{state.select(p.id);useViewer.getState().setView('scene');}}>Inspect {p.name}</button>
  </article>)}</div></details>
  {!state.items.length&&<p>No pipelines configured yet. Set up research to select your inputs.</p>}
 </section>;
}
