import {createRoot} from 'react-dom/client';
import * as Tooltip from '@radix-ui/react-tooltip';
import WindowWorkspace from '../src/components/WindowWorkspace';
import ControlPanel from '../src/panels/ControlPanel';
import ExecutionOutputsPanel from '../src/panels/ExecutionOutputsPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import type {Snapshot} from '../src/types';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';

Object.assign(window, {deliverOutputs(snapshot: Snapshot, error: string | null = null) {
  useViewer.setState({snapshot, runTag:snapshot.run_tag, error, loading:false, newRunMode:false});
}});
usePipelines.setState({loaded:true,selected:'example',items:[{id:'example',number:1,name:'Heart Failure study',latest:{run_tag:'selected'},running:null,progress:{},configuration:{}}] as never});
useViewer.setState({view:'results'});
function Workspace(){
  const view=useViewer(s=>s.view);
  return <WindowWorkspace items={[
    {id:'control',title:'Control',content:<ControlPanel/>},
    {id:'pipeline',title:'Experiment outputs',content:<ExecutionOutputsPanel view={view==='report'||view==='agents'?view:'results'}/>},
  ]}/>;
}
createRoot(document.getElementById('root')!).render(<Tooltip.Provider><Workspace/></Tooltip.Provider>);
