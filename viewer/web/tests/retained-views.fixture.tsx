// Only test fixtures can open retained views directly; the production menu stays MVP-only.
import {createRoot} from 'react-dom/client';
import App from '../src/App';
import {useEffect,useState} from 'react';
import PipelineSettings from '../src/components/PipelineSettings';
import {useViewer} from '../src/store/viewer';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
Object.assign(window, {openRetainedView: useViewer.getState().setView});
function Fixture(){
  const [settings,setSettings]=useState(false);
  useEffect(()=>{Object.assign(window,{openStudySettings:()=>setSettings(true)});},[]);
  return <><App/>{settings&&<PipelineSettings id="fixture" section="data" close={()=>setSettings(false)}/>}</>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
