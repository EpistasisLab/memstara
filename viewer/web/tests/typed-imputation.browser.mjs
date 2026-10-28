import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch();
try {for(const width of [320,390,768,1200,1280]){
 const page=await browser.newPage({viewport:{width,height:1000}});let posted,registrations=0,cleanUpload=false;
 await page.route('**/control/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/control/health')return width===768?route.fulfill({status:503,json:{}}):route.fulfill({json:{llm:{provider:'test_provider',model:'configured-test-model'},...(width===390?{stage_models:{non_explanation_agents:{provider:'test_provider',model:'analysis-model'},explanation_agent:{provider:'test_provider',model:'explanation-model'}}}:{})}});
  if(path.endsWith('/upload'))return route.fulfill({json:{dataset_path:'/uploaded.csv',columns:['measurement_recorded_before_admission_with_a_very_long_column_name','stage','binary12','group','target'],rows:80,missing_cells:cleanUpload?0:4,columns_with_missing:cleanUpload?{}:{measurement_recorded_before_admission_with_a_very_long_column_name:1,stage:1,binary12:1,group:1},nonfinite_columns:[],nonnumeric_columns:['group'],column_kinds:{measurement_recorded_before_admission_with_a_very_long_column_name:'numeric',stage:'numeric',binary12:'categorical',group:'categorical',target:'categorical'},type_confirmation_columns:['measurement_recorded_before_admission_with_a_very_long_column_name'],suggested_predictor_types:{stage:'categorical',binary12:'categorical',group:'categorical'},column_examples:{measurement_recorded_before_admission_with_a_very_long_column_name:[10,20,30],stage:[1,2,3]}}});
  if(path.endsWith('/register')){registrations++;posted=route.request().postDataJSON();return route.fulfill({json:{id:'typed',configuration:posted,input_checks_passed:true,dataset:{rows:80,column_count:5,missing_cells:4,columns:['measurement_recorded_before_admission_with_a_very_long_column_name','stage','binary12','group','target']},knowledge:{documents:0},issues:[]}});}
  throw Error(path);
 });
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/research-inputs.fixture.html?editor`);
 if(width===1280)await page.evaluate(()=>{document.querySelector('main').style.maxWidth='480px';document.documentElement.dataset.theme='dark';});
 async function upload(){await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'types.csv',mimeType:'text/csv',buffer:Buffer.from('measurement_recorded_before_admission_with_a_very_long_column_name,stage,binary12,group,target\n10,1,1,red,0\n20,2,2,blue,1\n30,3,2,green,0\n,,,,1\n')});}
 await upload();
 await expect(page.getByLabel('I’ll fix the CSV',{exact:true})).toBeChecked();
 await expect(page.getByRole('heading',{name:'What do you want to predict?',exact:true})).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'Knowledge source',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Check & use this data',exact:true})).toHaveCount(0);
 await page.getByLabel('Fill missing values for me').check();
 await expect(page.getByRole('heading',{name:'What do you want to predict?',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Knowledge source',exact:true})).toBeVisible();
 await page.getByLabel('Target column',{exact:true}).selectOption('target');
 await page.getByLabel('I’ll fix the CSV',{exact:true}).check();
 await expect(page.getByLabel('Target column',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('group',{name:'Knowledge source',exact:true})).toHaveCount(0);
 await page.getByLabel('Fill missing values for me').check();
 await expect(page.getByLabel('Target column',{exact:true})).toHaveValue('target');
 await expect(page.getByText('One quick check',{exact:true})).toHaveCount(0);
 await expect(page.getByText('See or change how empty cells are filled',{exact:true})).toHaveCount(0);
 await expect(page.locator('.research-type-choice,.research-fill-ready,.research-methods')).toHaveCount(0);
 await page.getByRole('radio',{name:'LLM only',exact:true}).check();
 await expect(page.getByLabel('Configured language model')).toHaveText(width===768?'Model information unavailable':width===390?'Models: analysis-model (test provider) · explanation-model (test provider)':'Model: configured-test-model (test provider)');
 await expect(page.getByText(/Still needed: Column type/)).toHaveCount(0);
 await page.getByText('View columns with missing values',{exact:true}).click();
 await page.screenshot({path:`/tmp/memstara-imputation-${width}.png`,fullPage:true});
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Your data is ready'})).toBeVisible();
 assert.deepEqual(posted.predictor_types,{measurement_recorded_before_admission_with_a_very_long_column_name:'continuous',stage:'categorical',binary12:'categorical',group:'categorical'});
 assert.equal(posted.missing_policy,'impute_train_v1');assert.equal(posted.target.positive_label,'1');
 await page.getByRole('button',{name:'Got it'}).click();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 assert.equal(await page.locator('.research-upload-status').evaluate(e=>e.scrollWidth>e.clientWidth+1),false);
 await upload();await expect(page.getByLabel('Target column',{exact:true})).toHaveCount(0);await page.getByLabel('Fill missing values for me').check();await page.getByLabel('Target column',{exact:true}).selectOption('target');
 await expect(page.locator('.research-type-choice,.research-methods')).toHaveCount(0);
 cleanUpload=true;await upload();
 await expect(page.getByRole('heading',{name:'What do you want to predict?',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Knowledge source',exact:true})).toBeVisible();
 await expect(page.getByLabel('Fill missing values for me',{exact:true})).toHaveCount(0);
 console.log(JSON.stringify({width,cleanCsvShowsQuestions:true,outcomeAndKnowledgeGatedByConsent:true,automaticTypes:true,settingsSectionRemoved:true,save:true,reset:true,noOverflow:true}));await page.close();
}}finally{await browser.close();}
