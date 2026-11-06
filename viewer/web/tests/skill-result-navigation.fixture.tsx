import {createRoot} from 'react-dom/client';
import ResultsPanel from '../src/panels/ResultsPanel';
import ExecutionOutputsPanel from '../src/panels/ExecutionOutputsPanel';
import {useViewer} from '../src/store/viewer';
import {useControl} from '../src/store/control';
import type {Snapshot} from '../src/types';
import '../src/index.css';
import '../src/workspace-layout.css';

Object.assign(window,{deliverChartSnapshot(snapshot:Snapshot){useViewer.setState({snapshot,runTag:snapshot.run_tag,newRunMode:false,error:null,loading:false});}});
useControl.setState({catalog:[{id:'hiv-no-knowledge',title:'HIV — No Knowledge'},{id:'hiv-okf-whole-graph',title:'HIV — Whole Knowledge Graph'},
 {id:'addiction-psychiatric',title:'Addiction KB — Psychiatric disorders'},{id:'addiction-substance-use',title:'Addiction KB — Substance use disorders'}] as never});
createRoot(document.getElementById('root')!).render(<main style={{height:'100dvh',display:'grid',maxWidth:1360,margin:'0 auto',padding:12,boxSizing:'border-box'}}>{new URLSearchParams(location.search).has('tiles')?<ExecutionOutputsPanel view="results"/>:<ResultsPanel telemetry embedded/>}</main>);
