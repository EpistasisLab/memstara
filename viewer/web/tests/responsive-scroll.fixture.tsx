import {Provider} from '@radix-ui/react-tooltip';
import {createRoot} from 'react-dom/client';
import CombinationWizard from '../src/components/CombinationWizard';
import AgentConfigPanel from '../src/panels/AgentConfigPanel';
import PipelineCreationDialog from '../src/panels/PipelineCreationDialog';
import {useControl,PLAYBOOK_STAGES} from '../src/store/control';
import {usePipelines} from '../src/store/pipelines';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
const catalog=PLAYBOOK_STAGES.flatMap(stage=>Array.from({length:16},(_,i)=>({
 id:`user-${stage}-${i}`,stage,title:`${stage} skill ${i} ${'LongTitle'.repeat(12)}`,
 hash:`${stage}-${i}`,content:Array.from({length:30},()=>`Synthetic instruction ${'long_identifier_'.repeat(20)}`).join('\n'),
 description:'Synthetic description '.repeat(30),source:'fixture'
})));
const initial=useControl.getState().form;
useControl.setState({catalog,form:{...initial,knowledge_mode:'llm_only',data_mode:'proposal',research_objective:'Synthetic research objective',research_input_id:'',skill:'',playbook_hypothesis:'user-hypothesis-0'},loadPlaybooks:async()=>{},loadSkills:async()=>{}});
usePipelines.setState({creationOpen:true,creationMode:null,closeCreation:()=>{document.body.dataset.closed='true';}} as Parameters<typeof usePipelines.setState>[0]);
const single=new URLSearchParams(location.search).has('single');
const editor=new URLSearchParams(location.search).has('editor');
if(editor)useControl.setState({editor:{stage:'hypothesis',slot:0,add:false}});
createRoot(document.getElementById('root')!).render(<Provider>{editor?<AgentConfigPanel/>:single?<PipelineCreationDialog/>:<CombinationWizard/>}</Provider>);
