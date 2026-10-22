import {createRoot} from 'react-dom/client';
import * as Tooltip from '@radix-ui/react-tooltip';
import WindowWorkspace from '../src/components/WindowWorkspace';
import ControlPanel from '../src/panels/ControlPanel';
import {VIEWS} from '../src/lib/views';
import ResultsPanel from '../src/panels/ResultsPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import type {Snapshot} from '../src/types';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';

// Feed the production workspace saved snapshots without starting pollers or a backend.
Object.assign(window, {deliverResults(snapshot: Snapshot | null, requested = snapshot?.run_tag, error: string | null = null) {
  useViewer.setState({snapshot, runTag: requested ?? null, error, loading: !snapshot, newRunMode: false});
}});
usePipelines.setState({loaded: true, selected: 'alpha', resultsScope: 'selected', items: [
  {id:'alpha',number:1,name:'Alpha research',latest:{run_tag:'alpha-run'},running:null,progress:{},configuration:{}},
  {id:'beta',number:2,name:'Beta research',latest:{run_tag:'beta-run'},running:null,progress:{},configuration:{}},
] as never});
function Workspace(){
  const view=useViewer(s=>s.view);
  return <WindowWorkspace items={[
    {id:'control',title:'Control',content:<ControlPanel/>},
    {id:'pipeline',title:VIEWS[view].label,content:view==='results'?<ResultsPanel embedded/>:<p>{VIEWS[view].label}</p>},
  ]}/>;
}
createRoot(document.getElementById('root')!).render(<Tooltip.Provider><Workspace/></Tooltip.Provider>);
