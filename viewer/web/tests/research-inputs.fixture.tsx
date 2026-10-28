import React, {useState} from 'react';
import '../src/index.css';
import {createRoot} from 'react-dom/client';
import ResearchInputs from '../src/components/ResearchInputs';
import ResearchInputSelect from '../src/components/ResearchInputSelect';
import type {RunRequest} from '../src/store/control';
function Selector(){const [value,setValue]=useState<Partial<RunRequest>>({skill:'old-source',baseline_columns:['old-feature'],y_column:'old_target'});
 return <><ResearchInputSelect value={value} onChange={patch=>setValue(v=>({...v,...patch}))}/><output className="block break-all" aria-label="Selected research configuration">{JSON.stringify(value)}</output></>;}
createRoot(document.getElementById('root')!).render(location.search==='?selector'?<Selector/>:location.search==='?editor'?<main className="research-input-shell" style={{maxWidth:960,margin:'16px auto',padding:'0 12px'}}><div className="research-input-editor"><ResearchInputs/></div></main>:<ResearchInputs disabled={location.search==='?disabled'}/>);
