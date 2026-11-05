import {createRoot} from 'react-dom/client';
import {useState} from 'react';
import HypothesisResultsTable from '../src/components/HypothesisResultsTable';
import '../src/index.css';
function Fixture(){
 const [results,setResults]=useState<unknown[]>([]);
 const [plannedSkills,setPlannedSkills]=useState<string[]>([]);
 Object.assign(window,{deliverMetricResults:(rows:unknown[])=>setResults(rows),deliverPlannedSkills:(skills:string[])=>setPlannedSkills(skills)});
 return <main style={{maxWidth:1360,width:'100%',padding:12,boxSizing:'border-box',margin:'0 auto'}}><HypothesisResultsTable results={results} runTag="continued-experiment" plannedSkills={plannedSkills}/></main>;
}
createRoot(document.getElementById('root')!).render(<Fixture/>);
