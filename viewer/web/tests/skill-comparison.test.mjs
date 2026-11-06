import test from 'node:test';
import assert from 'node:assert/strict';
import {comparisonColor,comparisonLabel,labelLines,resultForObservation,swarmOffsets} from '../src/lib/skillComparison.ts';

test('a chart selection opens only its original execution and result',()=>{
 const earlier={run_tag:'before-resume',result_id:7},later={run_tag:'after-resume',result_id:7};
 assert.equal(resultForObservation([later,earlier],{runTag:'before-resume',resultId:7}),earlier);
 assert.equal(resultForObservation([earlier,later],{runTag:'after-resume',resultId:7}),later);
 assert.equal(resultForObservation([earlier],{runTag:'unknown',resultId:7}),undefined);
 assert.equal(resultForObservation([{result_id:7}],{runTag:'',resultId:7}),undefined);
 assert.equal(resultForObservation([earlier],{runTag:'before-resume',resultId:null}),undefined);
});

test('equal or nearby scores remain individually clickable without changing the vertical metric',()=>{
 const points=Array.from({length:40},(_,index)=>({key:String(index),value:index<20?.8:.801}));
 const y=value=>value*300,positions=swarmOffsets(points,y);
 assert.equal(positions.size,40);
 for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
  const distance=(positions.get(points[i].key)-positions.get(points[j].key))**2+(y(points[i].value)-y(points[j].value))**2;
  assert(distance>=18**2);
 }
 assert.deepEqual(swarmOffsets([...points].reverse(),y),positions);
});

test('display titles do not change identities and colours survive filtering or sorting',()=>{
 const skills=['hiv-no-knowledge','hiv-okf-whole-graph','addiction-psychiatric','addiction-substance-use'];
 const colors=new Map(skills.map(id=>[id,comparisonColor(id)]));
 for(const id of [...skills].reverse().slice(1))assert.equal(comparisonColor(id),colors.get(id));
 assert.equal(new Set(colors.values()).size,4);
 assert.equal(comparisonLabel('a + b',{a:'Recorded title',b:'Other title'}),'Recorded title + Other title');
 assert.equal(comparisonLabel('hiv-okf-whole-graph'),'HIV OKF Whole Graph');
 const original='HIV — Whole Knowledge Graph';assert.equal(labelLines(original).join(' '),original);
 assert(labelLines('One two three four five six seven eight nine ten eleven twelve thirteen',10).length<=3);
});
