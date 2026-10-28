// Render saved selection provenance and measured columns; every API response is synthetic.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const features=['age','bmi','marker','history'];
  const result={result_id:1,task_id:1,trial:0,iteration:1,run_tag:'fixture',pipeline_name:'Fixture',pipeline_number:2,pipeline_count:4,replicate_number:1,replicate_count:1,
   hypothesis:'Synthetic random control',columns_used:[...features,'target'],columns_missing:[],y_column:'target',
   auc:.6,importance:{age:.1},created_at:'2026-10-06',evaluation:{feature_selection:{mode:'random',minimum:4,
    maximum:20,actual_count:4,features,seed:12345,pool_size:30,pool_sha256:'fixture',loop:1,combination:2},
    data_allocation:{request:{skill:'data_balanced_stratified',population:'exploration'},
      agent_plan:{test_size:.5,seed:7},exploration_count:160,reserved_count:40,
      replicates:[{seed:7,n_train:80,n_test:80,train_class_counts:{0:64,1:16},test_class_counts:{0:64,1:16}}]}}};
  result.evaluation.paired_models={primary_model:'logistic_regression',primary_selection:'Before fitting',
    same_features:true,same_splits:true,xgboost_minus_lr_auc:.1};
  result.evaluation.ml_configuration={requested:{rationale:'Synthetic fixture'},effective:{},resource_limits:{threads:1}};
  result.evaluation.model_results=Object.fromEntries(['logistic_regression','xgboost'].map((name,i)=>[name,{
    specialist_xai:{status:'completed',items:['shap','lime'].map(method=>({method,model:name,replicate:1,
      status:'completed',seed:7,explainer:method==='shap'?'TreeExplainer':'LimeTabularExplainer',
      output_scale:method==='shap'?'positive-class log-odds':'positive-class probability',explained_count:8,
      reference_count:32,feature_summary:{age:{mean_absolute:.2,mean_signed:-.1},bmi:{mean_absolute:.1,mean_signed:.03}},
      ...(method==='lime'?{fidelity_r2:{minimum:.6,mean:.8},samples_per_row:512}:{baseline:-.3,max_additivity_error:1e-7}),
      limitation:'Synthetic sampled evidence only',explanation_id:`${name}-${method}`,artifact_path:'/synthetic/xai.json'}))},
    model:name,auc:.6+i*.1,n_train:80,n_test:80,ml_configuration:{parameters:{fixture:1}},
    evaluation:{replicates:[{seed:7,auc:.6+i*.1,average_precision:.55+i*.1,
      operating_point:{true_negative:50,false_positive:14,false_negative:6,true_positive:10,probability_cutoff:.5}}],
      reproducibility:{status:'verified',bundle_path:'/synthetic/replay/'+name}}
  }]));
  result.interpretation='# Saved feature analysis\n\nFour selected predictors: age, bmi, marker, history.\n\nOriginal agent score: 0.600123.';
  const snapshot={run_tag:'fixture',run_configuration:{pipeline_name:'Fixture',trials:1,waves:1},results:[result],report:null,stale:false,health:{core:{up:true},memstara:{up:true}},board:{tasks:[],lanes:{}},scene:{places:[],agents:[],flashes:[]},runs:[],feed:[],agents:[],access:{rows:[],windows:[]}};
  await page.route(/\/(api|control)\//,r=>r.fulfill({status:503,json:{error:'Isolated fixture'}}));
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/execution-tiles.fixture.html');
  await page.waitForFunction(()=>typeof window.deliverOutputs==='function');
  await page.evaluate(snapshot=>window.deliverOutputs(snapshot),snapshot);
  const tile=page.locator('.execution-output-tile');await expect(tile).toHaveCount(1);
  const predictors=tile.locator('.output-predictor-meta');
  await expect(predictors).toContainText('Predictors · 4');
  for(const name of features)await expect(predictors).toContainText(name);
  await expect(predictors).not.toContainText('target');
  await expect(tile.locator('.output-test-metric')).toContainText('0.600');
  await tile.click();
  const evidence=page.locator('.output-documents');
  await expect(evidence).toContainText('Original agent score: 0.600123.');
  await expect(evidence).not.toContainText('Synthetic random control');
  await expect(evidence).not.toContainText('allowed 4–20');
  await expect(evidence.locator('table')).toHaveCount(0);
  await page.getByText('Data columns & recorded metrics',{exact:true}).click();
  for(const name of features)await expect(page.locator('.output-data-details')).toContainText(name);
  assert(await evidence.evaluate(el=>el.scrollWidth<=el.clientWidth+2));
  assert.deepEqual(errors,[]);
  result.evaluation.model_results.xgboost.specialist_xai.items[1]={method:'lime',model:'xgboost',replicate:1,
    status:'failed',error_type:'RuntimeError',seed:7};
  // Failure evidence must not cause the UI to invent or replace the saved agent narrative.
  await page.evaluate(snapshot=>window.deliverOutputs(snapshot),snapshot);
  await expect(evidence).toContainText('Original agent score: 0.600123.');
  await expect(evidence).not.toContainText('RuntimeError');
  assert.deepEqual(errors,[]);
  console.log(`Saved selection and evaluated predictor display passed at ${width}px; all APIs mocked.`);
  await page.close();
 }
} finally {await browser.close();}
