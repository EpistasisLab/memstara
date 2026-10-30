import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch();
try{for(const width of [390,1200]){
 const page=await browser.newPage({viewport:{width,height:1000}});let posted,runs=0;page.on('pageerror',error=>console.error(error.message));
 const roles=['hypothesis','data','ml','interpreter','report'];
 const skills=roles.map(stage=>({id:stage==='hypothesis'?'hypothesis_general':stage==='report'?'shared-heart-failure-cardiovascular':stage==='interpreter'?'shared-shap':`${stage}_fixture`,stage,title:`${stage} fixture`,hash:stage,content:'Test',source:'fixture'}));
 await page.route('**/control/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  if(path==='/control/playbooks')return route.fulfill({json:{catalog:skills,playbooks:skills.map(s=>s.id),stages:roles,references:[]}});
  if(path==='/control/skills')return route.fulfill({json:{skills:[]}});
  if(path==='/control/health')return route.fulfill({json:{input_defaults:{dataset_available:true,knowledge_available:true,target_column:''}}});
  if(path==='/control/research-inputs')return route.fulfill({json:{inputs:[{id:'available-study',input_checks_passed:true,configuration:{name:'Example dataset',dataset_path:'/data.csv',knowledge_mode:'llm_only',target:{column:'new_target',positive_label:'1',negative_label:'0',description:'',prediction_time:'',horizon:''},excluded_columns:[],missing_policy:'reject'}}]}});
  if(path==='/control/pipelines'&&req.method()==='POST'){posted=req.postDataJSON();return route.fulfill({json:{id:'created',name:posted.name,configuration:posted.configuration,number:2}});}
  if(path==='/control/runs'&&req.method()==='POST'){runs++;return route.fulfill({json:{run_tag:'mock-run',run_dir:'/mock',pid:1,started:'test'}});}
  if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[{id:'created',name:posted?.name,configuration:posted?.configuration,number:2,running:{run_tag:'mock-run'},latest:{run_tag:'mock-run'},progress:{}}]}});
  return route.fulfill({json:{}});
 });
 await page.route('**/api/**',r=>r.fulfill({json:{}}));
 await page.goto('http://127.0.0.1:4177/tests/fresh-experiment.fixture.html');
 const savedBefore=await page.getByLabel('Saved experiment configuration').textContent();
 const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});
 async function assertFresh(){await expect(dialog.getByRole('heading',{name:'Set up your research',exact:true})).toBeVisible();await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeDisabled();await expect(dialog.getByLabel('Selected dataset')).toHaveCount(0);await expect(dialog.getByText('Use server defaults',{exact:true})).toHaveCount(0);await expect(dialog.locator('.research-source-options .research-badge')).toHaveCount(0);}
 await page.getByRole('button',{name:'Add experiment',exact:true}).click();await assertFresh();
 assert.equal(await page.getByLabel('Saved experiment configuration').textContent(),savedBefore);
 await dialog.getByRole('button',{name:'Use Example dataset',exact:true}).click();
 await dialog.getByRole('button',{name:'Close pipeline details',exact:true}).click();
 await page.getByRole('button',{name:'Add experiment',exact:true}).click();await assertFresh();
 await dialog.getByRole('button',{name:'Use Example dataset',exact:true}).click();
 await dialog.getByRole('button',{name:'Choose skills',exact:true}).click();
 for(const label of ['Next: Data','Next: Machine learning','Next: Interpretation','Next: Explanation','Review plan'])await dialog.getByRole('button',{name:label,exact:true}).click();
 await dialog.getByLabel('Name',{exact:true}).fill('New experiment');
 await dialog.locator('input[type=checkbox]').last().check();
 await dialog.getByRole('button',{name:'Create combination design'}).click();await expect(dialog).toHaveCount(0);
 assert.equal(posted.configuration.evaluation.seed,42);assert.equal(posted.configuration.evaluation.test_size,.25);assert.equal(posted.configuration.research_input_id,'available-study');assert.deepEqual(posted.configuration.baseline_columns,[]);
 const createdBefore=await page.getByLabel('Saved experiment configuration').textContent();
 await page.getByRole('button',{name:'Run selected experiment',exact:true}).click();await expect.poll(()=>runs).toBe(1);
 await page.getByRole('button',{name:'Add experiment',exact:true}).click();await assertFresh();
 assert.equal(await page.getByLabel('Saved experiment configuration').textContent(),createdBefore);
 console.log(JSON.stringify({width,selectedSettingsIsolated:true,cancelReopensFresh:true,createRunReopensFresh:true,existingConfigurationPreserved:true}));await page.close();
}}finally{await browser.close();}
