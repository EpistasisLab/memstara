/** Read-only metrics from recorded held-out confusion matrices, never predictions. */
export type Matrix = {tn:number;fp:number;fn:number;tp:number};
export type MetricValue = {value:number|null;reason?:string;infinite?:boolean};
export type Observation = {key:string;runTag:string;resultId:number|null;pipeline:number|null;replicate:number;
 skill:string;model:string;target:string;seed:number|null;threshold:number|null;matrix:Matrix;error:string|null};
type Context = Matrix & {n:number;p:number;q:number;r:number;s:number;beta:number};
export type Metric = {id:string;label:string;category:string;formula:string;description:string;
 direction:'higher'|'lower'|'context';domain?:[number,number];calculate:(c:Context)=>MetricValue};
const value=(n:number):MetricValue=>Number.isFinite(n)?{value:n}:{value:null,reason:'Non-finite result.',infinite:!Number.isNaN(n)};
const ratio=(a:number,b:number):MetricValue=>b===0?{value:null,reason:a===0?'Undefined: numerator and denominator are both zero.':'Positive infinity: denominator is zero.',infinite:a!==0}:value(a/b);
const combine=(a:MetricValue,b:MetricValue,fn:(a:number,b:number)=>number):MetricValue=>a.value===null?a:b.value===null?b:value(fn(a.value,b.value));
const tpr=(c:Context)=>ratio(c.tp,c.p), tnr=(c:Context)=>ratio(c.tn,c.q);
const ppv=(c:Context)=>ratio(c.tp,c.r), npv=(c:Context)=>ratio(c.tn,c.s);
const f=(c:Context,beta:number,negative=false)=>{
 const a=negative?c.tn:c.tp, b=negative?c.fn:c.fp, d=negative?c.fp:c.fn;
 return ratio((1+beta*beta)*a,(1+beta*beta)*a+beta*beta*d+b);
};
const weighted=(c:Context,a:MetricValue,b:MetricValue):MetricValue=>{
 if(!c.n)return ratio(0,0);
 if(c.p===0)return b;
 if(c.q===0)return a;
 return combine(a,b,(x,y)=>(c.p*x+c.q*y)/c.n);
};
const metric=(id:string,label:string,category:string,formula:string,description:string,
 calculate:Metric['calculate'],direction:Metric['direction']='higher',domain?:[number,number]):Metric=>
 ({id,label,category,formula,description,calculate,direction,domain});
const unit:[number,number]=[0,1];

export const confusionMetrics:Metric[]=[
 ...(['tn','fp','fn','tp'] as const).map(id=>metric(id,id.toUpperCase(),'Counts',id.toUpperCase(),
  {tn:'Actual negatives correctly predicted negative.',fp:'Actual negatives predicted positive.',fn:'Actual positives predicted negative.',tp:'Actual positives correctly predicted positive.'}[id],c=>value(c[id]),'context')),
 metric('n','Evaluated count','Counts','TN + FP + FN + TP','Number of evaluated observations.',c=>value(c.n),'context'),
 metric('actual_positive','Actual positive count','Counts','TP + FN','Actual positive support.',c=>value(c.p),'context'),
 metric('actual_negative','Actual negative count','Counts','TN + FP','Actual negative support.',c=>value(c.q),'context'),
 metric('predicted_positive','Predicted positive count','Counts','TP + FP','Number classified positive.',c=>value(c.r),'context'),
 metric('predicted_negative','Predicted negative count','Counts','TN + FN','Number classified negative.',c=>value(c.s),'context'),
 metric('correct','Correct count','Counts','TP + TN','Correct classifications.',c=>value(c.tp+c.tn),'context'),
 metric('incorrect','Incorrect count','Counts','FP + FN','Incorrect classifications.',c=>value(c.fp+c.fn),'context'),
 metric('sensitivity','Sensitivity / Recall / TPR','Core performance','TP / (TP + FN)','Fraction of actual positives detected.',tpr,'higher',unit),
 metric('specificity','Specificity / TNR','Core performance','TN / (TN + FP)','Fraction of actual negatives rejected.',tnr,'higher',unit),
 metric('precision','Precision / PPV','Core performance','TP / (TP + FP)','Fraction of positive predictions that are correct.',ppv,'higher',unit),
 metric('npv','Negative predictive value / NPV','Core performance','TN / (TN + FN)','Fraction of negative predictions that are correct.',npv,'higher',unit),
 metric('accuracy','Accuracy','Core performance','(TP + TN) / N','Fraction of all observations correctly classified.',c=>ratio(c.tp+c.tn,c.n),'higher',unit),
 metric('balanced_accuracy','Balanced accuracy','Core performance','(TPR + TNR) / 2','Equal-weight average of positive and negative recall.',c=>combine(tpr(c),tnr(c),(a,b)=>(a+b)/2),'higher',unit),
 metric('f1','F1 / Dice score','Core performance','2TP / (2TP + FP + FN)','Harmonic balance of positive precision and recall.',c=>f(c,1),'higher',unit),
 metric('mcc','Matthews correlation coefficient / Phi','Core performance','(TP×TN − FP×FN) / √[(TP+FP)(TP+FN)(TN+FP)(TN+FN)]','Correlation between actual and predicted labels. Undefined when a marginal support is zero.',c=>ratio(c.tp*c.tn-c.fp*c.fn,Math.sqrt(c.r*c.p*c.q*c.s)),'higher',[-1,1]),
 metric('kappa',"Cohen's kappa",'Core performance','(Accuracy − pe) / (1 − pe); pe = [(TP+FN)(TP+FP)+(TN+FP)(TN+FN)] / N²','Agreement beyond the chance agreement implied by the observed class marginals.',c=>{
  if(!c.n)return ratio(0,0);const pe=(c.p*c.r+c.q*c.s)/(c.n*c.n);return ratio((c.tp+c.tn)/c.n-pe,1-pe);
 },'higher',[-1,1]),
 metric('g_mean','G-mean: sensitivity × specificity','Core performance','√(TPR × TNR)','Geometric mean of positive and negative recall.',c=>combine(tpr(c),tnr(c),(a,b)=>Math.sqrt(a*b)),'higher',unit),
 metric('fmi','Fowlkes–Mallows index','Core performance','√(PPV × TPR)','Geometric mean of positive precision and recall.',c=>combine(ppv(c),tpr(c),(a,b)=>Math.sqrt(a*b)),'higher',unit),
 metric('youden','Youden J / Informedness / Adjusted balanced accuracy','Core performance','TPR + TNR − 1','Chance-adjusted separation of actual positive and negative classes.',c=>combine(tpr(c),tnr(c),(a,b)=>a+b-1),'higher',[-1,1]),
 metric('markedness','Markedness','Core performance','PPV + NPV − 1','Combined reliability of positive and negative predictions.',c=>combine(ppv(c),npv(c),(a,b)=>a+b-1),'higher',[-1,1]),
 metric('fnr','False negative rate / Miss rate','Error rates','FN / (TP + FN)','Fraction of actual positives missed.',c=>ratio(c.fn,c.p),'lower',unit),
 metric('fpr','False positive rate / Fall-out','Error rates','FP / (TN + FP)','Fraction of actual negatives falsely classified positive.',c=>ratio(c.fp,c.q),'lower',unit),
 metric('fdr','False discovery rate','Error rates','FP / (TP + FP)','Fraction of positive predictions that are false. Not a multiple-testing FDR estimate.',c=>ratio(c.fp,c.r),'lower',unit),
 metric('for','False omission rate','Error rates','FN / (TN + FN)','Fraction of negative predictions that are false.',c=>ratio(c.fn,c.s),'lower',unit),
 metric('error_rate','Error rate / Hamming loss','Error rates','(FP + FN) / N','Single-label binary misclassification proportion.',c=>ratio(c.fp+c.fn,c.n),'lower',unit),
 metric('balanced_error','Balanced error rate','Error rates','(FNR + FPR) / 2','Equal-weight average of the two class-specific error rates.',c=>combine(ratio(c.fn,c.p),ratio(c.fp,c.q),(a,b)=>(a+b)/2),'lower',unit),
 metric('f05','F0.5','F-scores and overlap','1.25TP / (1.25TP + 0.25FN + FP)','Weights precision more than recall.',c=>f(c,.5),'higher',unit),
 metric('f2','F2','F-scores and overlap','5TP / (5TP + 4FN + FP)','Weights recall more than precision.',c=>f(c,2),'higher',unit),
 metric('fbeta','Custom F-beta','F-scores and overlap','(1+β²)TP / [(1+β²)TP + β²FN + FP]','User-selected positive beta. Beta > 1 emphasizes recall; beta < 1 emphasizes precision.',c=>f(c,c.beta),'higher',unit),
 metric('negative_f1','Negative-class F1','F-scores and overlap','2TN / (2TN + FP + FN)','F1 treating the negative class as the class of interest.',c=>f(c,1,true),'higher',unit),
 metric('macro_f1','Macro F1','F-scores and overlap','(F1_positive + F1_negative) / 2','Unweighted average of class-specific F1 scores, not F1 of averaged precision/recall.',c=>combine(f(c,1),f(c,1,true),(a,b)=>(a+b)/2),'higher',unit),
 metric('weighted_f1','Support-weighted F1','F-scores and overlap','[(TP+FN)F1_positive + (TN+FP)F1_negative] / N','Class-specific F1 weighted by actual support.',c=>weighted(c,f(c,1),f(c,1,true)),'higher',unit),
 metric('macro_fbeta','Macro F-beta','F-scores and overlap','(Fβ_positive + Fβ_negative) / 2','Unweighted mean of class-specific F-beta using the selected beta.',c=>combine(f(c,c.beta),f(c,c.beta,true),(a,b)=>(a+b)/2),'higher',unit),
 metric('weighted_fbeta','Support-weighted F-beta','F-scores and overlap','[(TP+FN)Fβ_positive + (TN+FP)Fβ_negative] / N','Class-specific F-beta weighted by actual support using the selected beta.',c=>weighted(c,f(c,c.beta),f(c,c.beta,true)),'higher',unit),
 metric('micro_f1','Micro F1 / Micro precision / Micro recall','F-scores and overlap','(TP + TN) / N','Across both classes in single-label binary classification, these equal accuracy.',c=>ratio(c.tp+c.tn,c.n),'higher',unit),
 metric('jaccard','Jaccard / Threat score / CSI','F-scores and overlap','TP / (TP + FP + FN)','Intersection over union of actual and predicted positives.',c=>ratio(c.tp,c.tp+c.fp+c.fn),'higher',unit),
 metric('negative_jaccard','Negative-class Jaccard','F-scores and overlap','TN / (TN + FP + FN)','Intersection over union for the negative class.',c=>ratio(c.tn,c.tn+c.fp+c.fn),'higher',unit),
 metric('macro_jaccard','Macro Jaccard','F-scores and overlap','(Jaccard_positive + Jaccard_negative) / 2','Unweighted average over the two classes.',c=>combine(ratio(c.tp,c.tp+c.fp+c.fn),ratio(c.tn,c.tn+c.fp+c.fn),(a,b)=>(a+b)/2),'higher',unit),
 metric('weighted_jaccard','Support-weighted Jaccard','F-scores and overlap','[(TP+FN)Jaccard_positive + (TN+FP)Jaccard_negative] / N','Jaccard weighted by actual class support.',c=>weighted(c,ratio(c.tp,c.tp+c.fp+c.fn),ratio(c.tn,c.tn+c.fp+c.fn)),'higher',unit),
 metric('macro_precision','Macro precision','Class averages','(PPV + NPV) / 2','Unweighted class-specific precision.',c=>combine(ppv(c),npv(c),(a,b)=>(a+b)/2),'higher',unit),
 metric('weighted_precision','Support-weighted precision','Class averages','[(TP+FN)PPV + (TN+FP)NPV] / N','Class-specific precision weighted by actual support.',c=>weighted(c,ppv(c),npv(c)),'higher',unit),
 metric('macro_recall','Macro recall','Class averages','(TPR + TNR) / 2','Equivalent to balanced accuracy when both classes are represented.',c=>combine(tpr(c),tnr(c),(a,b)=>(a+b)/2),'higher',unit),
 metric('weighted_recall','Support-weighted recall','Class averages','(TP + TN) / N','Class recall weighted by support; equals accuracy for single-label binary classification.',c=>ratio(c.tp+c.tn,c.n),'higher',unit),
 metric('lr_positive','Positive likelihood ratio / LR+','Likelihood ratios','TPR / FPR','Relative frequency of positive predictions in actual positives versus actual negatives.',c=>likelihood(c,true)),
 metric('lr_negative','Negative likelihood ratio / LR−','Likelihood ratios','FNR / TNR','Relative frequency of negative predictions in actual positives versus actual negatives.',c=>likelihood(c,false),'lower'),
 metric('dor','Diagnostic odds ratio','Likelihood ratios','(TP × TN) / (FP × FN)','Cross-product odds ratio. Zero cells can make it infinite or undefined; no continuity correction is applied.',c=>ratio(c.tp*c.tn,c.fp*c.fn)),
 metric('prevalence','Actual positive proportion','Class proportions','(TP + FN) / N','Positive proportion in these evaluated rows, not a population prevalence estimate.',c=>ratio(c.p,c.n),'context',unit),
 metric('actual_negative_rate','Actual negative proportion','Class proportions','(TN + FP) / N','Negative proportion in the evaluation sample.',c=>ratio(c.q,c.n),'context',unit),
 metric('predicted_positive_rate','Predicted positive proportion','Class proportions','(TP + FP) / N','Fraction of evaluation rows classified positive.',c=>ratio(c.r,c.n),'context',unit),
 metric('predicted_negative_rate','Predicted negative proportion','Class proportions','(TN + FN) / N','Fraction of evaluation rows classified negative.',c=>ratio(c.s,c.n),'context',unit),
 ...(['tp','tn','fp','fn'] as const).map(id=>metric(id+'_proportion',id.toUpperCase()+' / evaluated count','Class proportions',id.toUpperCase()+' / N','Share of all evaluated rows in this confusion-matrix cell.',c=>ratio(c[id],c.n),'context',unit)),
];

function likelihood(c:Context,positive:boolean):MetricValue {
 const a=positive?tpr(c):ratio(c.fn,c.p),b=positive?ratio(c.fp,c.q):tnr(c);
 return a.value===null?a:b.value===null?b:ratio(a.value,b.value);
}

export function calculateMetric(metric:Metric,m:Matrix,beta=1,error?:string|null):MetricValue {
 if(error)return {value:null,reason:error};
 if(!Number.isFinite(beta)||beta<=0)return {value:null,reason:'Beta must be finite and greater than zero.'};
 if(Object.values(m).some(n=>!Number.isSafeInteger(n)||n<0))return {value:null,reason:'Counts must be recorded nonnegative safe integers.'};
 const n=m.tn+m.fp+m.fn+m.tp;
 if(!Number.isSafeInteger(n)||n===0)return {value:null,reason:'Confusion matrix has no evaluated rows or exceeds safe integer precision.'};
 return metric.calculate({...m,n,p:m.tp+m.fn,q:m.tn+m.fp,r:m.tp+m.fp,s:m.tn+m.fn,beta});
}

type RecordValue=Record<string,unknown>;
const object=(v:unknown):RecordValue=>v&&typeof v==='object'&&!Array.isArray(v)?v as RecordValue:{};
const text=(v:unknown)=>typeof v==='string'?v:'';
const number=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v:null;

export function confusionObservations(results:readonly unknown[]):Observation[] {
 const observations=new Map<string,Observation>();
 for(const raw of results){
  const result=object(raw),saved=object(result.evaluation),models=object(saved.model_results);
  const skills=object(saved.skills),ids=Array.isArray(skills.hypothesis)?skills.hypothesis.map(text).filter(Boolean):[];
  const skill=ids.join(' + ')||text(result.hypothesis_id)||'Not recorded';
  const sources=Object.keys(models).length?Object.entries(models):[[text(saved.model)||text(result.model)||'Not recorded',saved] as const];
  for(const [model,rawSource]of sources){
   const source=object(rawSource),evaluation=object(source.evaluation);
   const fits=Array.isArray(evaluation.replicates)?evaluation.replicates:[];
   const candidates=fits.length?fits:[{}];
   for(let index=0;index<candidates.length;index++){
    const fit=object(candidates[index]),test=object(object(fit.performance).test),point=object(fit.operating_point);
    const matrix=object(test.confusion_matrix),modern=Object.keys(matrix).length>0;
    const fields=modern?['tn','fp','fn','tp']:['true_negative','false_positive','false_negative','true_positive'];
    const input=modern?matrix:point;
    const values=fields.map(key=>number(input[key]));
    let error=!fits.length?'No per-fit held-out confusion matrix was recorded.':values.some(v=>v===null)?'Complete TN, FP, FN and TP were not recorded for this fit.':null;
    if(modern&&((matrix.rows&&matrix.rows!=='actual')||(matrix.columns&&matrix.columns!=='predicted')||
       (Array.isArray(matrix.labels)&&JSON.stringify(matrix.labels)!=='[0,1]')))
      error='Unsupported confusion-matrix orientation or positive-class encoding.';
    const m={tn:values[0]??NaN,fp:values[1]??NaN,fn:values[2]??NaN,tp:values[3]??NaN};
    if(!error&&values.some(v=>!Number.isSafeInteger(v)||v!<0))error='Confusion-matrix counts must be nonnegative integers.';
    const total=m.tn+m.fp+m.fn+m.tp,n=number(test.n)??number(fit.n_test);
    if(!error&&n!==null&&total!==n)error='Confusion-matrix total does not match the recorded test count.';
    const runTag=text(result.run_tag),resultId=number(result.result_id);
    // Unidentified rows cannot be safely deduplicated across polling; retain position in that case.
    const key=`${runTag}:${resultId??'unidentified-'+observations.size}:${model}:${index}`;
    observations.set(key,{key,runTag,resultId,pipeline:number(result.pipeline_number)??number(result.iteration)??
      (number(result.trial)!==null?Number(result.trial)+1:null),replicate:index+1,skill,model,
      target:text(result.y_column)||text(saved.y_column)||'Not recorded',seed:number(fit.seed)??number(saved.seed),
      threshold:number(test.threshold)??number(point.probability_cutoff),matrix:m,error});
   }
  }
 }
 return [...observations.values()];
}

/** Linear interpolation at (n−1)p, matching the usual inclusive sample quantile. */
export function quantile(sorted:number[],p:number):number {
 const index=(sorted.length-1)*p,lower=Math.floor(index),fraction=index-lower;
 return sorted[lower]+(sorted[Math.min(lower+1,sorted.length-1)]-sorted[lower])*fraction;
}
export function boxSummary(values:number[]) {
 const sorted=values.filter(Number.isFinite).sort((a,b)=>a-b);
 if(!sorted.length)return null;
 const q1=quantile(sorted,.25),median=quantile(sorted,.5),q3=quantile(sorted,.75),iqr=q3-q1;
 const inside=sorted.filter(v=>v>=q1-1.5*iqr&&v<=q3+1.5*iqr);
 return {n:sorted.length,q1,median,q3,low:inside[0],high:inside.at(-1)!,min:sorted[0],max:sorted.at(-1)!};
}

const csvCell=(v:unknown)=>{
 const raw=String(v??''),safe=typeof v==='string'&&/^[\t\r ]*[=+\-@]/.test(raw)?"'"+raw:raw;
 return '"'+safe.replaceAll('"','""')+'"';
};
export function metricCsv(observations:Observation[],metrics:Metric[],beta:number):string {
 const header=['Hypothesis skill','Target','Run tag','Result ID','Pipeline','Fit replicate','Model','Seed','Threshold','TN','FP','FN','TP','Metric','Formula','Beta','Value','Status / reason'];
 const rows=observations.flatMap(o=>metrics.map(m=>{
  const v=calculateMetric(m,o.matrix,beta,o.error);
  return [o.skill,o.target,o.runTag,o.resultId,o.pipeline,o.replicate,o.model,o.seed,o.threshold,
   o.matrix.tn,o.matrix.fp,o.matrix.fn,o.matrix.tp,m.label,m.formula,m.id.includes('fbeta')?beta:'',v.value,v.reason??'Finite'];
 }));
 return '\uFEFF'+[header,...rows].map(row=>row.map(v=>csvCell(typeof v==='number'&&!Number.isFinite(v)?'':v)).join(',')).join('\r\n')+'\r\n';
}
