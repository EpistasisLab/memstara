// Only test fixtures can open retained views directly; the production menu stays MVP-only.
import {createRoot} from 'react-dom/client';
import FeatureContributionChart from '../src/components/FeatureContributionChart';
import type {Result} from '../src/types';
import App from '../src/App';
import {useEffect,useState} from 'react';
import PipelineMLSettings from '../src/components/PipelineMLSettings';
import {usePipelines} from '../src/store/pipelines';
import PipelineSettings from '../src/components/PipelineSettings';
import {useViewer} from '../src/store/viewer';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
Object.assign(window, {openRetainedView: useViewer.getState().setView});
function Fixture(){
  const [chart,setChart]=useState<Result|null>(null);
  const [settings,setSettings]=useState(false);
  const [ml,setMl]=useState(false);const pipeline=usePipelines(s=>s.items.find(p=>p.id===s.selected));
  useEffect(()=>{Object.assign(window,{openStudySettings:()=>setSettings(true),openMLSettings:()=>setMl(true),openFeatureChart:(result:Result)=>setChart(result)});},[]);
  return <>{chart?<FeatureContributionChart result={chart}/>:<App/>}{ml&&pipeline&&<PipelineMLSettings pipeline={pipeline} close={()=>setMl(false)}/>}{settings&&<PipelineSettings id="fixture" section="data" close={()=>setSettings(false)}/>}</>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
