import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import * as Tooltip from '@radix-ui/react-tooltip';
import CombinationDesign from '../src/components/CombinationDesign';
import AgentConfigPanel from '../src/panels/AgentConfigPanel';
import ResultsPanel from '../src/panels/ResultsPanel';
import ReportBody from '../src/components/ReportBody';
import CompactActivityRow from '../src/components/CompactActivityRow';
import MotoroRecords from '../src/components/MotoroRecords';
import {InterpretationVoices} from '../src/components/discovery/EvidenceVisuals';
import {useControl, PLAYBOOK_STAGES} from '../src/store/control';
import {usePipelines} from '../src/store/pipelines';
import {useViewer} from '../src/store/viewer';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';

const prose="Anil's instructions adapted by Phil. This is not an Anil-authored adaptation. Neutrophil count is a predictor.\n\n`shared-anil-shap` and **shared-anil-lime**\n\n[Anil reference](https://example.org/anil_shared/SHAP.md \"Phil reference\")";
const specs=[['hypothesis','hypothesis_general','General hypothesis'],['data','data_training_heavy','Training heavy'],['ml','ml_logistic_regression','Logistic regression'],['interpreter','shared-anil-shap','Anil SHAP'],['interpreter','shared-anil-lime','Anil LIME'],['report','shared-anil-addiction','Anil addiction'],['report','shared-anil-hiv','Anil HIV']];
const catalog=specs.map(([stage,id,title],index)=>({stage,id,title,hash:String(index+1).repeat(64),description:"Anil's skill with Phil's instructions.",content:prose,source:'anil_shared/SHAP-Interpretation.md'}));
const configuration={...useControl.getState().form,playbook_interpreter:'shared-anil-shap',playbook_explanation:'shared-anil-addiction',combination_skills:Object.fromEntries(PLAYBOOK_STAGES.map(s=>[s,catalog.filter(c=>c.stage===s).map(c=>c.id)]))};
const pipeline={id:'neutral',number:1,name:'Research pipeline',configuration,running:null,latest:null,progress:{}};
const voices=[{slot:1,worker:'Anil interpreter',skill:'shared-anil-shap',status:'done',text:prose},{slot:2,worker:'Phil interpreter',skill:'shared-anil-lime',status:'done',text:prose}];
useControl.setState({catalog:catalog as never,form:configuration,loadPlaybooks:async()=>{},loadSkills:async()=>{}});
usePipelines.setState({items:[pipeline] as never,selected:'neutral',loaded:true,resultsScope:'selected'});
useViewer.setState({runTag:'neutral-run',newRunMode:false,snapshot:{
  run_tag:'neutral-run',run_configuration:{trials:1,pipeline_name:'Research pipeline'},generated_at:'2026-10-22T12:00:00Z',
  health:{core:{up:true},memstara:{up:true}},runs:[],scene:{places:[],agents:[],flashes:[]},board:{lanes:{},tasks:[]},feed:[],agents:[],access:{rows:[],windows:[]},report:null,
  results:[{result_id:1,task_id:1,trial:0,perspective:'SHAP analysis',hypothesis:'Neutrophil count predicts outcome.',columns_used:['neutrophil'],columns_missing:[],importance:{neutrophil:.1},okf_concept_ids:[],y_column:'outcome',auc:.731,model:'lr',interpretation:prose,created_at:'2026-10-22T12:00:00Z',evaluation:{interpreter:{worker:'Anil interpreter',skill:'shared-anil-shap'},interpretations:voices}}],
} as never});
Object.assign(window,{originalFixture:()=>({catalog:useControl.getState().catalog,configuration:usePipelines.getState().items[0].configuration})});
function App(){
  const [view,setView]=useState('Skills');
  const saved=usePipelines(s=>s.items[0]);
  return <Tooltip.Provider><nav aria-label="Fixture views">{['Skills','Results','Activity','Records'].map(v=><button key={v} onClick={()=>setView(v)}>{v}</button>)}</nav><main>
    {view==='Skills'&&<><button onClick={()=>useControl.setState({editor:{stage:'interpreter',slot:0,add:false}})}>Edit interpretation</button><CombinationDesign pipeline={saved}/><AgentConfigPanel/></>}
    {view==='Results'&&<><ResultsPanel/><InterpretationVoices voices={voices as never}/><ReportBody report text={prose}/></>}
    {view==='Activity'&&<ul><CompactActivityRow message={{id:'msg',stage:'interpreter',kind:'error',kind_label:'Saved message',name:'Anil interpreter',label:'Anil interpreter',text:prose,at:'2026-10-22T12:00:00Z'} as never}/><CompactActivityRow event={{key:'event',agent:'interpreter',label:'Anil interpreter',name:'shared-anil-lime',tool:'read_results',server:'anil_shared',store:'results',at:'2026-10-22T12:00:00Z'} as never}/></ul>}
    {view==='Records'&&<MotoroRecords tag="neutral-run" loop={1}/>}
  </main></Tooltip.Provider>;
}
createRoot(document.getElementById('root')!).render(<App/>);
