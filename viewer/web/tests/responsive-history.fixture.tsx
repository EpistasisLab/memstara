import {createRoot} from 'react-dom/client';
import {useState} from 'react';
import AgentConversation from '../src/components/AgentConversation';
import RunLog from '../src/components/RunLog';
import '../src/index.css';
import '../src/readability.css';
import '../src/workspace-layout.css';
function Fixture(){
 const [lines,setLines]=useState(Array.from({length:150},(_,i)=>`Recorded line ${i} ${'long_record_'.repeat(30)}`));
 const log=new URLSearchParams(location.search).has('log');
 return log?<main style={{height:'100dvh',display:'flex',flexDirection:'column',minWidth:0}}>
 <button onClick={()=>setLines(v=>[...v,`New recorded line ${v.length}`])}>Append record</button>
 <div style={{flex:1,minHeight:0}}><RunLog lines={lines} skipped={0} tail=""/></div>
 </main>:<main className="execution-logs" style={{height:'100dvh',overflow:'auto'}}><AgentConversation runTag="history-fixture" loop={null}/></main>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
