import {useContext} from 'react';
import {createRoot} from 'react-dom/client';
import * as Tooltip from '@radix-ui/react-tooltip';
import WindowWorkspace from '../src/components/WindowWorkspace';
import {WorkspaceEvidenceContext} from '../src/components/WorkspaceEvidenceContext';
import ResultsPanel from '../src/panels/ResultsPanel';
import {useViewer} from '../src/store/viewer';
import {usePipelines} from '../src/store/pipelines';
import type {Snapshot} from '../src/types';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';

// Feed the production workspace saved snapshots without starting pollers or a backend.
Object.assign(window, {deliverResults(snapshot: Snapshot | null, requested = snapshot?.run_tag, error: string | null = null) {
  useViewer.setState({snapshot, runTag: requested ?? null, error, loading: !snapshot, newRunMode: false});
}});
usePipelines.setState({loaded: true, selected: 'alpha', resultsScope: 'selected', items: [
  {id:'alpha',number:1,name:'Alpha research',latest:{run_tag:'alpha-run'},running:null,progress:{},configuration:{}},
  {id:'beta',number:2,name:'Beta research',latest:{run_tag:'beta-run'},running:null,progress:{},configuration:{}},
] as never});
function Floor(){
  return <div className="floor-panel-toolbar">{useContext(WorkspaceEvidenceContext)}</div>;
}
createRoot(document.getElementById('root')!).render(<Tooltip.Provider><WindowWorkspace items={[
  {id:'control',title:'Control',content:<p>Fixture controls</p>},
  {id:'pipeline',title:'Floor plan',content:<Floor/>},
  {id:'results',title:'Results',content:<ResultsPanel/>},
  {id:'report',title:'Final report',content:<p>Saved report fixture</p>},
]}/></Tooltip.Provider>);
