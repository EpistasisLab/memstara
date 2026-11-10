import test from 'node:test';
import assert from 'node:assert/strict';
import {hypothesisSummaryRows,hypothesisSummaryCsv,sortHypothesisSummaryRows} from '../src/lib/hypothesisSummary.ts';

const result={run_tag:'run-1',pipeline_name:'HIV H1',iteration:2,result_id:9,task_id:4,trial:1,hypothesis_id:'hypothesis#1',hypothesis:'Recorded hypothesis',model:'logistic_regression',evaluation:{skills:{hypothesis:['hiv-h1']},evaluation:{replicates:[{seed:731,n_train:77,n_test:23,auc:.82,average_precision:.74,f1:.71,operating_point:{probability_cutoff:.5,true_negative:12,false_positive:3,false_negative:2,true_positive:6,sensitivity:.75,specificity:.8,precision:.667}},{seed:732,n_train:77,n_test:23,auc:.84,operating_point:{true_negative:13,false_positive:2,false_negative:3,true_positive:5}}]}}};

test('hypothesis table creates one evidence row per evaluation replicate',()=>{
 const rows=hypothesisSummaryRows([result]);assert.equal(rows.length,2);
 assert.equal(rows[0].hypothesisSkill,'hiv-h1');assert.equal(rows[0].subjects,100);assert.equal(rows[0].seed,731);assert.equal(rows[0].trueNegative,12);assert.equal(rows[1].auroc,.84);
});

test('hypothesis table CSV includes the photographed comparison fields and full metrics',()=>{
 const csv=hypothesisSummaryCsv(hypothesisSummaryRows([result]));
 for(const field of ['Hypothesis Skill','Pipeline','Subjects','Seed','AUROC','TN','FP','FN','TP','Average Precision','Hypothesis'])assert(csv.includes(`"${field}"`));
 assert(csv.includes('"hiv-h1"'));assert(csv.includes('"731"'));assert(csv.includes('"0.82"'));
});

test('table sorting compares numbers numerically, preserves ties and leaves missing values last',()=>{
 const base=hypothesisSummaryRows([result])[0];
 const rows=Object.freeze([2,null,10,2,NaN].map((value,i)=>Object.freeze({...base,resultId:i,truePositive:value})));
 const asc=sortHypothesisSummaryRows(rows,{column:'truePositive',direction:'ascending'});
 const desc=sortHypothesisSummaryRows(rows,{column:'truePositive',direction:'descending'});
 assert.deepEqual(asc.map(r=>r.resultId),[0,3,2,1,4]);
 assert.deepEqual(desc.map(r=>r.resultId),[2,0,3,1,4]);
 assert.deepEqual(rows.map(r=>r.resultId),[0,1,2,3,4]);
 assert.equal(asc[0],rows[0]);
});

test('text sorting handles numbered labels and sorts new rows without changing evidence',()=>{
 const base=hypothesisSummaryRows([result])[0];
 const rows=['Skill 10','Not recorded','Skill 2'].map((name,i)=>({...base,hypothesisSkill:name,resultId:i}));
 const sort={column:'hypothesisSkill',direction:'ascending'};
 assert.deepEqual(sortHypothesisSummaryRows(rows,sort).map(r=>r.resultId),[2,0,1]);
 assert.deepEqual(sortHypothesisSummaryRows(rows,{...sort,direction:'descending'}).map(r=>r.resultId),[0,2,1]);
 const added={...base,hypothesisSkill:'Skill 1',resultId:3};
 assert.deepEqual(sortHypothesisSummaryRows([...rows,added],sort).map(r=>r.resultId),[3,2,0,1]);
 assert.deepEqual(sortHypothesisSummaryRows(rows,null),rows);
});
