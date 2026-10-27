import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Provider} from '@radix-ui/react-tooltip';
import CombinationFloor from '../src/components/CombinationFloor';
import ReportPanel from '../src/panels/ReportPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import {PLAYBOOK_STAGES} from '../src/store/control';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
const skills=PLAYBOOK_STAGES.map(stage=>[{id:stage,stage,title:`${stage} test skill`}]);
const outputs=[1,2,3,4].map(loop=>({loop,result_id:loop,status:'completed',text:`Saved Explanation ${loop}. Exact source narrative.`}));
const results=outputs.map(o=>({result_id:o.loop,trial:o.loop-1,run_tag:'audit-run',hypothesis:`Question for pipeline ${o.loop%2?1:2}`,evaluation:null}));
useViewer.setState({runTag:'audit-run',snapshot:{run_tag:'audit-run',results,report:{status:'completed',text:'Do not substitute aggregate',explanation_outputs:outputs},run_configuration:{trials:1,combination_plan:{combinations:2,repetitions:2,total_loops:4,execution_order:'all_pipelines_first'}},health:{memstara:{up:true}}} as never});
usePipelines.setState({selected:'audit',items:[{id:'audit',number:1,name:'Saved experiment name',progress:{},configuration:{},latest:{run_tag:'audit-run'},running:null}] as never});
function Fixture(){
 const [stage,setStage]=useState(0),[paused,setPaused]=useState(false);
 Object.assign(window,{changeStage(index:number,pause=false){setStage(index);setPaused(pause);}});
 const calls=PLAYBOOK_STAGES.slice(0,stage+1).map((role,i)=>({stage:role,status:i===stage?'started':'completed',skill:skills[i][0]}));
 return <Provider><div style={{height:500,overflow:'hidden',position:'relative'}}><CombinationFloor skills={skills} calls={calls} activeSkills={skills.flat()} currentStage={PLAYBOOK_STAGES[stage]} recorded live={!paused} paused={paused} inspect={()=>{}}/></div><div style={{height:650}}><ReportPanel/></div></Provider>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
