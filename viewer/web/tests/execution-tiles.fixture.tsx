import {createRoot} from 'react-dom/client';
import * as Tooltip from '@radix-ui/react-tooltip';
import WindowWorkspace from '../src/components/WindowWorkspace';
import ControlPanel from '../src/panels/ControlPanel';
import ExecutionOutputsPanel from '../src/panels/ExecutionOutputsPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import {useLiveOutputs} from '../src/store/liveOutputs';
import type {Snapshot} from '../src/types';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
Object.assign(window,{setOutputOwnerName:(name:string)=>usePipelines.setState(state=>({items:state.items.map(item=>({...item,name}))}))});
Object.assign(window,{setExperimentProgress:(progress:NonNullable<ReturnType<typeof usePipelines.getState>['items'][number]['experiment_progress']>,tag:string)=>usePipelines.setState(state=>({items:state.items.map(item=>({...item,experiment_progress:progress,latest:{...item.latest!,run_tag:tag}}))}))});

Object.assign(window, {deliverLiveOutputs: (value:Partial<ReturnType<typeof useLiveOutputs.getState>>) => useLiveOutputs.setState(value), deliverOutputs(snapshot: Snapshot, error: string | null = null, requested = snapshot.run_tag) {
  useViewer.setState({snapshot, runTag:requested, error, loading:false, newRunMode:false});
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
