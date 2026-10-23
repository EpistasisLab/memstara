import {createRoot} from 'react-dom/client';
import {useEffect,useState} from 'react';
import App from '../src/App';
import * as Tooltip from '@radix-ui/react-tooltip';
import {CreationWizard} from '../src/panels/PipelineCreationDialog';
import {usePipelines} from '../src/store/pipelines';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
usePipelines.setState({creationOpen:true});
function Fixture(){
 const [legacy,setLegacy]=useState(true);
 useEffect(()=>usePipelines.subscribe(s=>{if(!s.creationOpen){history.replaceState(null,'','/');setLegacy(false);}}),[]);
 return legacy?<Tooltip.Provider><CreationWizard/></Tooltip.Provider>:<App/>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
