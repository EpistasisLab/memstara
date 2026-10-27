import React from 'react';
import {TooltipProvider} from '@radix-ui/react-tooltip';
import {createRoot} from 'react-dom/client';
import '../src/index.css';
import {useControl,DEFAULT_REQUEST} from '../src/store/control';
import {usePipelines} from '../src/store/pipelines';
import PipelineCreationDialog from '../src/panels/PipelineCreationDialog';
const previous={...structuredClone(DEFAULT_REQUEST),research_input_id:'old-study',y_column:'old_target',knowledge_mode:'llm_only' as const,research_objective:'Old objective',baseline_columns:['old_feature'],question:'old question',evaluation:{...DEFAULT_REQUEST.evaluation,seed:987,test_size:.4},combination_repetitions:12};
usePipelines.setState({loaded:true,items:[{id:'previous',number:1,name:'Previous experiment',configuration:previous,running:null,latest:null,progress:{}}]});
usePipelines.getState().select('previous');
function Fixture(){const p=usePipelines();const form=useControl(s=>s.form);return <><button onClick={()=>void p.add()}>Add experiment</button><button onClick={()=>void p.play(p.selected!)}>Run selected experiment</button><output aria-label="Saved experiment configuration">{JSON.stringify(form)}</output><PipelineCreationDialog/></>}
createRoot(document.getElementById('root')!).render(<TooltipProvider><Fixture/></TooltipProvider>);
