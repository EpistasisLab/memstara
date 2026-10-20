import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const b=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{for(const width of [390,1440]){
 const p=await b.newPage({viewport:{width,height:900}});let items=[],created=[],starts=0;
 const errors=[];p.on('pageerror',e=>errors.push(e.message));
 const catalog=[['guided','hypothesis'],['data_training_heavy','data'],['ml_logistic_regression','ml'],['shared-anil-shap','interpreter'],['explain','report']].map(([id,stage])=>({id,stage,title:id,hash:id,content:'# Fixture'}));
 await p.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Offline fixture'}}));
 await p.route('**/control/**',r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/research-inputs')return r.fulfill({json:{inputs:[{id:'example',corpus_skill_profile:'custom',input_checks_passed:true,configuration:{name:'Bundled example',dataset_path:'/fixture.csv',knowledge_path:'/fixture',data_mode:'dataset',knowledge_mode:'okf',target:{column:'outcome',description:'Predict the recorded outcome',positive_label:'yes',negative_label:'no'}}}]}});
  if(path==='/control/playbooks')return r.fulfill({json:{catalog,corpus_skill_bindings:{default:'general',profiles:{custom:{label:'Example',hypothesis:['guided'],report:['explain']}},research:{example:'custom'}}}});
  if(path==='/control/pipelines'){
   if(r.request().method()==='GET')return r.fulfill({json:{pipelines:items}});
   const body=r.request().postDataJSON();assert.equal(body.action,'add');created.push(body);
   const item={id:'one',number:1,name:body.name,configuration:body.configuration,running:null,latest:null,progress:{}};items=[item];return r.fulfill({json:item});
  }
  if(path==='/control/runs'&&r.request().method()==='POST'){
   starts++;assert.equal(r.request().postDataJSON().pipeline_id,'one');
   if(starts===1)return r.fulfill({status:400,json:{error:'Fixture: deployment temporarily unavailable'}});
   const run={run_tag:'fixture-run',configuration:items[0].configuration,execution_state:'running'};items[0].running=run;items[0].latest=run;return r.fulfill({json:run});
  }
  if(r.request().method()!=='GET')throw Error('Unexpected mutation '+path);
  return r.fulfill({json:{skills:[],runs:[],ok:true}});
 });
 await p.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await p.getByRole('button',{name:'Add pipeline — set up research',exact:true}).click();
 assert.equal(await p.getByRole('button',{name:'All Combinations',exact:true}).isVisible(),false);
 await p.getByRole('button',{name:/^Start a guided study/}).click();
 const d=p.getByRole('dialog',{name:'Start a guided study',exact:true});
 await d.getByLabel('Guided study',{exact:true}).selectOption('example');
 await d.getByRole('button',{name:'Review study',exact:true}).click();
 await d.getByText('outcome',{exact:true}).waitFor();
 assert.equal(created.length,0);assert.equal(starts,0);
 await d.getByRole('checkbox').check();await d.getByRole('button',{name:'Create one-run pipeline',exact:true}).click();
 await d.getByRole('heading',{name:'Ready for one run'}).waitFor();assert.equal(created.length,1);assert.equal(starts,0);
 const config=created[0].configuration;assert.equal(config.waves,1);assert.equal(config.combination_max_loops,1);assert.equal(config.stage_models,undefined);assert.deepEqual(config.combination_skills.ml,['ml_logistic_regression']);
 await d.getByRole('button',{name:'Start one run',exact:true}).click();await d.getByRole('alert').filter({hasText:'deployment temporarily unavailable'}).waitFor();
 assert.equal(created.length,1);await d.getByRole('button',{name:'Start one run',exact:true}).click();
 await d.getByRole('button',{name:'Track progress',exact:true}).waitFor();assert.equal(starts,2);assert.equal(created.length,1);
 assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await d.getByRole('button',{name:'Track progress',exact:true}).click();assert.equal(await d.count(),0);
 assert.deepEqual(errors,[]);await p.close();console.log(`Guided study ${width}px: one saved pipeline, explicit paid-start boundary, rejected-start retry, progress navigation passed`);
}}finally{await b.close();}
