import {openBuildModeFixture} from './build-mode.fixture.mjs';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const schema=JSON.parse(readFileSync(new URL('./ml-settings.fixture.json',import.meta.url),'utf8'));
const browser=await chromium.launch({headless:true});let page;
try{
 page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(8000);const errors=[];let items=[],starts=0;
 page.on('console',message=>{if(message.type()==='error'&&!message.text().includes('503'))console.error('UI console:',message.text());});
 page.on('pageerror',e=>{errors.push(e.message);console.log('Browser error:',e.message);});
 const catalog=[['hypothesis_general','hypothesis','General hypothesis'],['data_training_heavy','data','Training-heavy'],['ml_logistic_regression','ml','Logistic Regression (LR)'],['ml_xgboost','ml','XGBoost'],['shared-anil-shap','interpreter','SHAP'],['report_general','report','General explanation']].map(([id,stage,title])=>({id,stage,title,hash:id,content:'# Synthetic fixture',description:'Synthetic instructions',source:'Fixture'}));
 await page.route('**/control/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/playbooks')return r.fulfill({json:{ml_settings:schema,catalog,playbooks:catalog.map(x=>x.id),stages:['hypothesis','data','ml','interpreter','report'],references:[]}});
  if(path==='/control/health')return r.fulfill({json:{ok:true,llm:{provider:'openai',model:'fixture'},input_defaults:{dataset_available:true,knowledge_available:true,target_column:'Y'}}});
  if(path==='/control/research-inputs')return r.fulfill({json:{inputs:[]}});
  if(/^\/control\/pipelines\/[^/]+\/combinations$/.test(path))return r.fulfill({status:503,json:{error:'No recorded activity in this fixture'}});
  if(path==='/control/pipelines'){
   if(r.request().method()==='GET')return r.fulfill({json:{pipelines:items}});
   const body=r.request().postDataJSON();
   if(body.action==='add'){const item={id:'model-'+(items.length+1),number:items.length+1,name:body.name,configuration:body.configuration,running:null,latest:null,progress:{}};items.push(item);return r.fulfill({json:item});}
   if(body.action==='update'){items=items.map(p=>p.id===body.id?{...p,configuration:body.configuration}:p);return r.fulfill({json:items.find(p=>p.id===body.id)});}
   throw Error('Unexpected mutation');
  }
  if(r.request().method()!=='GET'){starts++;throw Error('No inference or execution permitted');}
  return r.fulfill({json:{skills:[],runs:[]}});
 });
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Isolated fixture'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 await page.getByRole('button',{name:/Add pipeline/i}).click();await openBuildModeFixture(page);
 let dialog=page.getByRole('dialog',{name:'Create a pipeline',exact:true});
 await dialog.getByLabel('Deployment target column').fill('Y');await dialog.getByRole('checkbox',{name:/Use .* for this pipeline/}).check();
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 for(const role of ['Hypothesis','Data']){const choice=dialog.getByRole('combobox',{name:role+' skill',exact:true});if(!await choice.inputValue())await choice.selectOption(role==='Hypothesis'?'hypothesis_general':'data_training_heavy');await dialog.getByRole('button',{name:'Next',exact:true}).click();}
 await dialog.getByRole('combobox',{name:'Machine learning skill',exact:true}).selectOption('ml_logistic_regression');
 assert.equal(await dialog.evaluate(el=>{const advanced=[...el.querySelectorAll('button')].find(b=>b.textContent.startsWith('Advanced model settings'));const evaluation=el.querySelector('[aria-label="ML evaluation settings"]');return !!(advanced.compareDocumentPosition(evaluation)&Node.DOCUMENT_POSITION_FOLLOWING);}),true);
 await dialog.getByText(/^Advanced model settings/).click();
 assert.equal(await dialog.getByRole('group',{name:'XGBoost settings',exact:true}).count(),0);
 await dialog.getByLabel('Logistic Regression (LR) C',{exact:true}).fill('.25');
 await dialog.getByLabel('Logistic Regression (LR) max_iter',{exact:true}).fill('3000');
 assert.equal(await dialog.getByRole('button',{name:'Next',exact:true}).isEnabled(),false);
 await dialog.getByLabel('Logistic Regression (LR) max_iter',{exact:true}).fill('500');
 await dialog.getByLabel('Logistic Regression (LR) penalty',{exact:true}).selectOption(JSON.stringify('l1'));
 await dialog.getByLabel('Logistic Regression (LR) solver',{exact:true}).selectOption(JSON.stringify('lbfgs'));
 assert.equal(await dialog.getByRole('button',{name:'Next',exact:true}).isEnabled(),false);
 await dialog.getByLabel('Logistic Regression (LR) solver',{exact:true}).selectOption(JSON.stringify('liblinear'));
 await dialog.getByLabel('Logistic Regression (LR) prediction threshold',{exact:true}).fill('.6');
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 for(const role of ['Interpretation','Explanation']){const choice=dialog.getByRole('combobox',{name:role+' skill',exact:true});if(!await choice.inputValue())await choice.selectOption(role==='Interpretation'?'shared-anil-shap':'report_general');await dialog.getByRole('button',{name:'Next',exact:true}).click();}
 await dialog.getByLabel('Pipeline name',{exact:true}).fill('Advanced LR fixture');await dialog.getByRole('button',{name:'Next',exact:true}).click();await dialog.getByRole('button',{name:'Create pipeline',exact:true}).click();await dialog.waitFor({state:'hidden'});
 assert.equal(items[0].configuration.ml_overrides.models.logistic_regression.parameters.C,.25);
 await page.reload();await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();await page.getByRole('button',{name:'Inspect Machine learning',exact:true}).click();
 dialog=page.getByRole('dialog').filter({has:page.locator('#agent-skill-select')});await dialog.getByText(/^Advanced model settings/).click();
 assert.equal(await dialog.getByLabel('Logistic Regression (LR) C',{exact:true}).inputValue(),'0.25');
 await dialog.getByLabel('Logistic Regression (LR) C',{exact:true}).fill('.5');await dialog.getByRole('button',{name:'Save settings',exact:true}).click();await dialog.waitFor({state:'hidden'});
 assert.equal(items[0].configuration.ml_overrides.models.logistic_regression.parameters.C,.5);
 await page.getByRole('button',{name:/Add pipeline/i}).click();
 dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});await dialog.getByRole('button',{name:'Choose skills',exact:true}).click();
 for(const role of ['Hypothesis','Data','Machine learning','Interpretation','Explanation']){
  await dialog.locator('.comb-roles button').filter({hasText:role}).click();await dialog.locator('.comb-skill-card input').first().waitFor({state:'visible'});
  const choices=dialog.getByRole('group',{name:role+' skill options',exact:true});
  await choices.getByRole('checkbox').first().check();if(role==='Machine learning')await choices.getByRole('checkbox').nth(1).check();
 }
 await dialog.locator('.comb-roles button').filter({hasText:'Machine learning'}).click();
 if(!await dialog.locator('.comb-ml-settings').evaluate(el=>el.open))await dialog.getByText('Evaluation and advanced model settings',{exact:true}).click();await dialog.getByText(/^Advanced model settings/).click();
 await dialog.getByLabel('Logistic Regression (LR) C',{exact:true}).fill('1.5');await dialog.getByLabel('XGBoost n_estimators',{exact:true}).fill('40');
 await dialog.getByLabel('XGBoost prediction threshold',{exact:true}).fill('.4');
 for(const width of [390,1440]){await page.setViewportSize({width,height:1000});assert.equal(await dialog.evaluate(el=>el.scrollWidth>el.clientWidth+2),false);}
 await dialog.locator('.comb-roles button').filter({hasText:'Explanation'}).click();await dialog.getByRole('button',{name:'Review plan',exact:true}).click();
 await dialog.getByLabel('Name',{exact:true}).fill('Advanced paired fixture');await dialog.getByRole('checkbox',{name:/I reviewed the pipelines, replicates/}).check();await dialog.getByRole('button',{name:'Create combination design',exact:true}).click();await dialog.waitFor({state:'hidden'});
 const paired=items[1].configuration.ml_overrides;
 assert.equal(paired.models.logistic_regression.parameters.C,1.5);assert.equal(paired.models.xgboost.parameters.n_estimators,40);assert.equal(paired.models.xgboost.threshold,.4);
 assert.equal(await page.getByRole('button',{name:/^Settings and more for /}).count(),0);
 assert.equal(starts,0);assert.deepEqual(errors,[]);
 console.log('Selected LR and paired-combination advanced settings validated, saved during creation; separate models; mobile layout; zero executions. HTTP mocked.');
}catch(error){throw new Error(String(error)+'\nFixture body:\n'+(await page.locator('body').innerText()).slice(0,7500));}finally{await browser.close();}
