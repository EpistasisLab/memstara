import {createRoot} from 'react-dom/client';
import HeaderStatus from '../src/components/HeaderStatus';
import ExplorationSummary from '../src/components/ExplorationSummary';
import {useLiveOutputs} from '../src/store/liveOutputs';
import {usePipelines} from '../src/store/pipelines';
import '../src/index.css';

Object.assign(window,{
  setCountLive:(value:Partial<ReturnType<typeof useLiveOutputs.getState>>)=>useLiveOutputs.setState(value),
  setCountPipelines:(value:Partial<ReturnType<typeof usePipelines.getState>>)=>usePipelines.setState(value),
  pollCounts:()=>useLiveOutputs.getState().poll(),
});
usePipelines.setState({loaded:true,error:null,items:[{id:'example',name:'Study',latest:{run_tag:'head'},running:null,progress:{}}] as never});
createRoot(document.getElementById('root')!).render(<>
  <HeaderStatus onOpen={()=>{}}/>
  <ExplorationSummary costState={{label:'Unavailable',description:'Synthetic fixture',delayed:false,partial:false} as never}/>
</>);
