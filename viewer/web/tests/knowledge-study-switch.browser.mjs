import {retainedWorkspaceUrl} from './retained-views.mjs';
import {corpusSkillBindings} from './corpus-skill-bindings.fixture.mjs';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try {
 for(const combined of [false,true]) {
 const page=await browser.newPage({viewport:{width:1400,height:1000}});const errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 let item={id:'fixture',number:1,name:'Study switch fixture',configuration:{research_input_id:'hiv',knowledge_mode:'okf',data_mode:'dataset',y_column:'HIV_DETECTABLE',skill:'',waves:1,trials:1,continuous:false,hypothesis_agents:1,interpret_agents:1,baseline_columns:['old_predictor'],combination_skills:{},evaluation:{engine:'xgboost',seed:42,test_size:.25,folds:0,replicates:1,search_trials:1},playbook_hypothesis:'hypothesis_general',playbook_data:'data_training_heavy',playbook_ml:'ml_logistic_regression',playbook_interpreter:'shared-shap',playbook_explanation:'report_general'},running:null,latest:null,progress:{}};
 if(combined){item.configuration.combination_skills={hypothesis:['addiction-psychiatric','random_features'],data:['data_training_heavy'],ml:['ml_logistic_regression'],interpreter:['shared-shap'],report:['shared-hiv']};item.configuration.combination_max_loops=2;}
 const inputs=[['hiv','HIV study','HIV_DETECTABLE'],['heart','HeartFailure study','chronic_heart_failure']].map(([id,name,column])=>({id,input_checks_passed:true,configuration:{name,knowledge_mode:'okf',data_mode:'dataset',target:{column,description:name,prediction_time:'Unverified',positive_label:'1',negative_label:'0'}}}));
 await page.route('**/control/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/pipelines') {
   if(r.request().method()==='GET')return r.fulfill({json:{pipelines:[item]}});
   const body=r.request().postDataJSON();assert.equal(body.action,'update');writes.push(body);item={...item,configuration:body.configuration};return r.fulfill({json:item});
  }
  if(r.request().method()!=='GET')throw Error('Unexpected write or execution');
  if(path==='/control/research-inputs')return r.fulfill({json:{inputs}});
  if(path==='/control/health')return r.fulfill({json:{ok:true,bundle:{configured:false,documents:0},llm:{provider:'openai',model:'fixture'},input_defaults:{dataset_available:false,knowledge_available:false,target_column:''}}});
  if(path==='/control/playbooks')return r.fulfill({json:{corpus_skill_bindings:corpusSkillBindings,
   catalog:['data_training_heavy','data_balanced_stratified'].map(id=>({id,stage:'data',title:id,description:'Synthetic Data skill',content:'# Fixture',hash:id,source:'Fixture'})),
   playbooks:['data_training_heavy','data_balanced_stratified'],stages:['data'],references:[]}});
  return r.fulfill({json:{corpus_skill_bindings:corpusSkillBindings,skills:[],catalog:[],stages:[],playbooks:[],runs:[]}});
 });
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Fixture'}}));
 await page.addInitScript(()=>localStorage.setItem('memstara.pipelineSelection','fixture'));
 await page.goto(retainedWorkspaceUrl);await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 await page.getByRole('button',{name:'Select pipeline 1: Study switch fixture',exact:true}).click();
 await page.waitForFunction(()=>typeof window.openStudySettings==='function');await page.evaluate(()=>window.openStudySettings());
 let dialog=page.getByRole('dialog',{name:/Data & target$/});
 await dialog.getByText('Change dataset',{exact:false}).click();
 await dialog.getByRole('button',{name:'Use HeartFailure study',exact:true}).click();
 await dialog.getByLabel('Selected dataset').getByText('chronic_heart_failure',{exact:true}).waitFor();assert.equal(writes.length,0);
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(writes.length,0);
 await page.waitForFunction(()=>typeof window.openStudySettings==='function');await page.evaluate(()=>window.openStudySettings());
 dialog=page.getByRole('dialog',{name:/Data & target$/});
 await dialog.getByText('Change dataset',{exact:false}).click();
 await dialog.getByRole('button',{name:'Use HeartFailure study',exact:true}).click();
 await dialog.getByRole('button',{name:'Save settings',exact:true}).click();
 await dialog.waitFor({state:'hidden'});
 assert.equal(writes.length,1);
 assert.equal(item.configuration.research_input_id,'heart');assert.equal(item.configuration.y_column,'chronic_heart_failure');
 assert.deepEqual(item.configuration.baseline_columns,[]);
 if(combined){assert.deepEqual(item.configuration.combination_skills.hypothesis,[corpusSkillBindings.profiles.heart_failure.hypothesis[0]]);assert.deepEqual(item.configuration.combination_skills.report,['shared-hiv']);assert.deepEqual(item.configuration.combination_skills.ml,['ml_logistic_regression']);assert.equal(item.configuration.combination_max_loops,2);}else assert.deepEqual(item.configuration.combination_skills,{});
 await page.reload();await page.waitForFunction(()=>typeof window.openStudySettings==='function');await page.getByRole('button',{name:'Select pipeline 1: Study switch fixture',exact:true}).waitFor();await page.evaluate(()=>window.openStudySettings());
 const savedInputs=page.getByRole('dialog',{name:/Data & target$/});
 assert.match(await savedInputs.getByLabel('Selected dataset').innerText(),/HeartFailure study/);
 await savedInputs.getByLabel('Selected dataset').getByText('chronic_heart_failure',{exact:true}).waitFor();
 if(!combined)await savedInputs.getByRole('button',{name:'Cancel',exact:true}).click();
 if(!combined){
  await page.getByRole('button',{name:'Inspect Data',exact:true}).click();
  const editor=page.getByRole('dialog').filter({has:page.locator('#agent-skill-select')});
  const selector=editor.locator('#agent-skill-select');
  assert.deepEqual((await selector.locator('option').evaluateAll(options=>options.map(o=>o.value).filter(Boolean))).sort(),['data_balanced_stratified','data_training_heavy']);
  await selector.selectOption('data_balanced_stratified');
  await editor.getByRole('button',{name:'Save settings',exact:true}).click();
  await editor.waitFor({state:'hidden'});
  assert.equal(item.configuration.playbook_data,'data_balanced_stratified');
  assert.equal(item.configuration.research_input_id,'heart');
  assert.equal(item.configuration.y_column,'chronic_heart_failure');
 }
 assert.deepEqual(errors,[]);
 await page.close();
 }
 console.log('Retained study settings for selected and All Combinations pipelines switch HIV to HeartFailure with its target; cancel preserves settings, save/reload persists the whole study, no execution submitted. HTTP mocked.');
} finally {await browser.close();}
