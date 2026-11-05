import {createRoot} from 'react-dom/client';
import {useEffect} from 'react';
import WorkspaceCost from '../src/components/WorkspaceCost';
import {useWorkspaceCost} from '../src/lib/useWorkspaceCost';
import {useHistoryResetMonitor} from '../src/store/historyReset';
import {usePipelines} from '../src/store/pipelines';
import {useLiveOutputs} from '../src/store/liveOutputs';
import {useViewer} from '../src/store/viewer';
import '../src/index.css';

function Fixture(){
 useHistoryResetMonitor();
 const state=useWorkspaceCost();
 const cached=useLiveOutputs(s=>s.results.length);
 const snapshot=useViewer(s=>s.snapshot);
 useEffect(()=>{void usePipelines.getState().poll();},[]);
 Object.assign(window,{seedCachedHistory:()=>{
  useLiveOutputs.setState({results:[{result_id:1,run_tag:'old-run'} as never]});
  useViewer.setState({snapshot:{run_tag:'old-run'} as never});
 }});
 return <main style={{maxWidth:700,padding:12,margin:'auto'}}>
  <WorkspaceCost state={state}/><p data-testid="cached-results">Cached results: {cached}</p>
  <p data-testid="cached-snapshot">Cached snapshot: {snapshot?'yes':'no'}</p>
 </main>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
