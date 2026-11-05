import {createRoot} from 'react-dom/client';
import PipelineRowActions from '../src/components/PipelineRowActions';
import {usePipelines} from '../src/store/pipelines';
import {pipelineState} from '../src/lib/pipelineState';
import '../src/index.css';
function Fixture(){
 const p=usePipelines(s=>s.items[0]);
 if(!p)return <p>Loading</p>;
 return <main><h1>{p.name}</h1><p data-testid="report-state">{pipelineState(p)}</p>
  <p data-testid="original-exit">Original process exit: {p.latest?.exit_code}</p><PipelineRowActions pipeline={p}/></main>;
}
void usePipelines.getState().poll();
createRoot(document.getElementById('root')!).render(<Fixture/>);
