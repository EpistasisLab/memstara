import {createRoot} from 'react-dom/client';
import * as Tooltip from '@radix-ui/react-tooltip';
import TelemetryPanel from '../src/panels/TelemetryPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';

const empty=new URLSearchParams(location.search).has('empty');
useViewer.setState({runTag:empty?null:'telemetry-alpha'});
usePipelines.setState({loaded:true,selected:empty?'pending':'alpha',items:[
  {id:'alpha',name:'Research pipeline — '+ 'Long descriptive name '.repeat(12),latest:{run_tag:'telemetry-alpha'},running:null,progress:{},configuration:{}},
  {id:'beta',name:'Second pipeline',latest:{run_tag:'telemetry-beta'},running:null,progress:{},configuration:{}},
  {id:'pending',name:'Not started',latest:null,running:null,progress:{},configuration:{}},
] as never});
createRoot(document.getElementById('root')!).render(<Tooltip.Provider><TelemetryPanel/></Tooltip.Provider>);
