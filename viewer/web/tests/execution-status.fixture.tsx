import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import ExecutionStatusNotice from '../src/components/ExecutionStatusNotice';
import '../src/index.css';
function Fixture(){
 const [mode,setMode]=useState('failed');
 return <><button onClick={()=>setMode('loading')}>Select another execution</button><button onClick={()=>setMode('completed')}>Load completed execution</button><ExecutionStatusNotice pipeline={{status:mode==='completed'?'completed':'failed',stage:'hypothesis2',loop:3,code:'model_connection',message:'The model connection failed or timed out. Saved results are retained; further execution was stopped.'}} label="test-1-all-comb · 2026-10-01 (saved run date)" runTag="board_20261001T102208_322628" loading={mode==='loading'}/></>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
