// A checked input is required before choosing skills; server defaults are not a dataset.
export const preparedInputs={inputs:[{id:'ci-data',input_checks_passed:true,configuration:{
 name:'CI dataset',dataset_path:'/fixture/data.csv',knowledge_mode:'llm_only',data_mode:'dataset',
 target:{column:'outcome',description:'Synthetic outcome',positive_label:'1',negative_label:'0'},
 excluded_columns:[],missing_policy:'reject',
}}]};
export function fixtureSkillId(stage,index=0){
 if(stage==='interpreter')return ['shared-shap','shared-lime'][index];
 if(stage==='report')return ['shared-addiction','shared-hiv','shared-heart-failure-cardiovascular','shared-heart-failure-comorbidity'][index];
 if(stage==='hypothesis')return index?'user-hypothesis-fixture-'+index:'hypothesis_general';
 return stage+'_'+index;
}
