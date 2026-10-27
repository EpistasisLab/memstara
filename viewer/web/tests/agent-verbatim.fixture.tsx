import {createRoot} from 'react-dom/client';
import {Provider} from '@radix-ui/react-tooltip';
import ResultsPanel from '../src/panels/ResultsPanel';
import ReportPanel from '../src/panels/ReportPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
Object.assign(window,{deliverResults(results:unknown[]){
  useViewer.setState(state=>({snapshot:{...state.snapshot,results} as never}));
},deliverOriginals(interpretation:string,explanation:string){
  useViewer.setState({runTag:'verbatim',snapshot:{run_tag:'verbatim',results:[{
    result_id:225,trial:0,perspective:'Saved question',hypothesis:'Original hypothesis',
    interpretation:'## Interpreter 1 — synthetic legacy header\n\nWRONG AGGREGATE',
    evaluation:{interpretations:[{slot:1,worker:'interpret#1',skill:'shared-shap',status:'done',text:interpretation,error:''}]},
    columns_used:['age'],columns_missing:[],importance:{age:.1},y_column:'outcome',auc:.65,model:'lr',okf_concept_ids:[],created_at:'2026-10-27T00:00:00Z'
  }],report:{status:'completed',text:'WRONG FINAL COMPARISON',explanation_outputs:[{loop:1,result_id:225,text:explanation,status:'completed'}]},
  run_configuration:{trials:1,pipeline_name:'Originals',combination_plan:{combinations:1,repetitions:1,total_loops:1}},
  health:{memstara:{up:true}},board:{tasks:[]},pipeline:{status:'completed'},stale:false} as never});
}});
usePipelines.setState({resultsScope:'selected',selected:'originals',items:[{id:'originals',number:1,name:'Originals',latest:{run_tag:'verbatim'},progress:{},configuration:{},running:null}] as never});
createRoot(document.getElementById('root')!).render(<Provider><main style={{minWidth:0}}><ResultsPanel embedded/><ReportPanel/></main></Provider>);
