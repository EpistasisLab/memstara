import {test} from 'node:test';
import assert from 'node:assert/strict';
import {confusionMetrics,calculateMetric,confusionObservations,boxSummary,metricCsv} from '../src/lib/confusionMetrics.ts';

const matrix={tn:50,fp:10,fn:5,tp:35};
const metric=id=>{const found=confusionMetrics.find(m=>m.id===id);assert(found,id);return found;};
const score=(id,m=matrix,beta=1)=>calculateMetric(metric(id),m,beta);
const near=(a,b)=>assert(Math.abs(a-b)<1e-12,`${a} != ${b}`);
const fit={seed:42,n_test:100,operating_point:{probability_cutoff:.4,true_negative:50,false_positive:10,false_negative:5,true_positive:35}};
const source={run_tag:'before-resume',result_id:7,trial:3,iteration:4,pipeline_number:4,y_column:'target',model:'lr',
 evaluation:{skills:{hypothesis:['recorded-skill']},evaluation:{replicates:[fit]}}};

test('numeric results agree with independent sklearn reference calculations',()=>{
 // sklearn 1.x reference: 60 negative / 40 positive labels and the stated matrix.
 const expected={accuracy:.85,balanced_accuracy:.8541666666666667,mcc:.6975184488828855,kappa:.6938775510204082,
 f05:.7954545454545454,f1:.8235294117647058,f2:.8536585365853658,macro_f1:.8465473145780051,
 weighted_f1:.8511508951406648,macro_jaccard:.7346153846153847,weighted_jaccard:.7415384615384616,
 weighted_precision:.8565656565656566};
 for(const [name,value]of Object.entries(expected))near(score(name).value,value);
 near(score('lr_positive').value,5.25);near(score('lr_negative').value,.15);near(score('dor').value,35);
 near(score('fbeta',matrix,2).value,expected.f2);
 near(score('macro_fbeta',matrix,1).value,expected.macro_f1);
 near(score('weighted_fbeta',matrix,1).value,expected.weighted_f1);
});
test('all metric definitions have unique identities and complementary quantities reconcile',()=>{
 assert(confusionMetrics.length>=50);assert.equal(new Set(confusionMetrics.map(m=>m.id)).size,confusionMetrics.length);
 for(const m of confusionMetrics){assert(m.label&&m.formula&&m.description&&m.category);assert(Number.isFinite(score(m.id).value),m.id);}
 for(const [a,b]of [['sensitivity','fnr'],['specificity','fpr'],['precision','fdr'],['npv','for'],['accuracy','error_rate'],['balanced_accuracy','balanced_error']])near(score(a).value+score(b).value,1);
 near(['tp','tn','fp','fn'].reduce((sum,id)=>sum+score(id+'_proportion').value,0),1);
 near(score('micro_f1').value,score('accuracy').value);near(score('weighted_recall').value,score('accuracy').value);
});
test('all-positive predictions preserve undefined values instead of fabricating zeros',()=>{
 const m={tn:0,fp:450,fn:0,tp:63};
 near(score('f1',m).value,.21875);near(score('balanced_accuracy',m).value,.5);
 assert.equal(score('npv',m).value,null);assert.equal(score('mcc',m).value,null);
 assert.equal(score('lr_negative',m).value,null);assert.equal(score('dor',m).value,null);
 assert(!score('dor',m).infinite);near(score('kappa',m).value,0);
 const negative={tn:450,fp:0,fn:63,tp:0};
 assert.equal(score('precision',negative).value,null);assert.equal(score('f1',negative).value,0);
});
test('perfect and inverted classifiers and zero-cell ratios remain distinct',()=>{
 const perfect={tn:60,fp:0,fn:0,tp:40};
 for(const id of ['mcc','kappa','accuracy','f1'])near(score(id,perfect).value,1);
 assert(score('lr_positive',perfect).infinite);assert(score('dor',perfect).infinite);
 assert.equal(score('lr_negative',perfect).value,0);
 near(score('mcc',{tn:0,fp:60,fn:40,tp:0}).value,-1);
});
test('invalid, empty and unrecorded matrices never become measured performance',()=>{
 for(const m of [{...matrix,tp:NaN},{...matrix,tn:-1},{...matrix,fp:.5},{tn:0,fp:0,fn:0,tp:0}])
  assert.equal(score('accuracy',m).value,null);
 assert.equal(score('fbeta',matrix,0).value,null);assert.equal(score('fbeta',matrix,Infinity).value,null);
 assert.equal(calculateMetric(metric('accuracy'),matrix,1,'Wrong partition').reason,'Wrong partition');
});
test('extracts original provenance, legacy operating points, all models and all fits once',()=>{
 const modern={...fit,performance:{test:{n:100,threshold:.7,confusion_matrix:{...matrix,labels:[0,1],rows:'actual',columns:'predicted'}}}};
 const multi={...source,evaluation:{...source.evaluation,model_results:{lr:{evaluation:{replicates:[modern,fit]}},xgb:{evaluation:{replicates:[fit]}}}}};
 const rows=confusionObservations([multi,multi]);assert.equal(rows.length,3);
 assert.equal(rows[0].runTag,'before-resume');assert.equal(rows[0].skill,'recorded-skill');assert.equal(rows[0].pipeline,4);
 assert.equal(rows[0].threshold,.7);assert.deepEqual(rows[0].matrix,matrix);assert.equal(rows[1].threshold,.4);
 assert.equal(rows[2].model,'xgb');assert.equal(rows[2].seed,42);
 assert.equal(confusionObservations([source])[0].error,null);
});
test('missing fits, partial or inconsistent matrices disclose reasons, including missing models',()=>{
 const missing=confusionObservations([{...source,evaluation:{...source.evaluation,model_results:{lr:{},xgb:{evaluation:{replicates:[fit]}}}}}]);
 assert.equal(missing.length,2);assert.match(missing[0].error,/No per-fit/);
 const wrong={...source,evaluation:{...source.evaluation,evaluation:{replicates:[{...fit,n_test:101}]}}};
 assert.match(confusionObservations([wrong])[0].error,/does not match/);
 const swapped={...source,evaluation:{...source.evaluation,evaluation:{replicates:[{performance:{test:{confusion_matrix:{...matrix,labels:[1,0]}}}}]}}};
 assert.match(confusionObservations([swapped])[0].error,/encoding/);
 const partial={...source,evaluation:{...source.evaluation,evaluation:{replicates:[{...fit,performance:{test:{confusion_matrix:{tn:50}}}}]}}};
 assert.match(confusionObservations([partial])[0].error,/Complete TN/);
});
test('joint skill conditions are not duplicated into independent skill groups',()=>{
 const row=confusionObservations([{...source,evaluation:{...source.evaluation,skills:{hypothesis:['a','b']}}}])[0];
 assert.equal(row.skill,'a + b');
});
test('quartiles and Tukey whiskers use observed inliers and keep singleton groups',()=>{
 assert.equal(boxSummary([]),null);
 assert.deepEqual(boxSummary([4]),{n:1,q1:4,median:4,q3:4,low:4,high:4,min:4,max:4});
 const stats=boxSummary([0,1,2,3,4,100]);assert.equal(stats.q1,1.25);assert.equal(stats.median,2.5);
 assert.equal(stats.q3,3.75);assert.equal(stats.high,4);assert.equal(stats.max,100);
});
test('CSV preserves exact values, original runs, non-finite reasons and formula-safe strings',()=>{
 const rows=confusionObservations([source]);rows[0].skill='=unsafe';
 const csv=metricCsv(rows,[metric('accuracy'),metric('fbeta')],2);
 assert(csv.includes('before-resume'));assert(csv.includes('"0.85"'));assert(csv.includes('"\'=unsafe"'));
 assert(csv.includes('"Custom F-beta"'));assert(csv.includes('"2"'));
 rows[0].matrix={tn:60,fp:0,fn:0,tp:40};const infinite=metricCsv(rows,[metric('dor')],1);
 assert(infinite.includes('Positive infinity'));assert(!infinite.includes('"Infinity"'));assert(!infinite.includes('"NaN"'));
});
