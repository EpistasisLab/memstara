import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch();
try {for(const width of [390,1200]){
 const page=await browser.newPage({viewport:{width,height:1000}});let posted,registrations=0;
 await page.route('**/control/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/upload'))return route.fulfill({json:{dataset_path:'/uploaded.csv',columns:['measurement','stage','binary12','group','target'],rows:80,missing_cells:4,columns_with_missing:{measurement:1,stage:1,binary12:1,group:1},nonfinite_columns:[],nonnumeric_columns:['group'],column_kinds:{measurement:'numeric',stage:'numeric',binary12:'categorical',group:'categorical',target:'categorical'},type_confirmation_columns:['measurement','stage']}});
  if(path.endsWith('/register')){registrations++;posted=route.request().postDataJSON();return route.fulfill({json:{id:'typed',configuration:posted,input_checks_passed:true,dataset:{rows:80,column_count:5,missing_cells:4,columns:['measurement','stage','binary12','group','target']},knowledge:{documents:0},issues:[]}});}
  throw Error(path);
 });
 await page.goto('http://127.0.0.1:4177/tests/research-inputs.fixture.html');
 async function upload(){await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'types.csv',mimeType:'text/csv',buffer:Buffer.from('measurement,stage,binary12,group,target\n10,1,1,red,0\n20,2,2,blue,1\n30,3,2,green,0\n,,,,1\n')});}
 await upload();await page.getByLabel('Target column',{exact:true}).selectOption('target');
 await expect(page.getByRole('group',{name:'Confirm missing-value treatment'})).toHaveCount(0);
 await page.getByLabel('Fill missing values for me').check();
 await expect(page.getByRole('group',{name:'Confirm missing-value treatment'})).toBeVisible();
 await expect(page.getByLabel('binary12: Category codes',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('group: Category codes',{exact:true})).toHaveCount(0);
 await page.getByRole('radio',{name:'LLM only',exact:true}).check();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Review your data settings'})).toContainText('measurement');
 assert.equal(registrations,0);await page.getByRole('button',{name:'Back to settings'}).click();
 await page.getByLabel('measurement: Measurements',{exact:true}).check();
 await page.getByLabel('stage: Category codes',{exact:true}).check();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Your data is ready'})).toBeVisible();
 assert.deepEqual(posted.predictor_types,{measurement:'continuous',stage:'categorical'});
 assert.equal(posted.missing_policy,'impute_train_v1');assert.equal(posted.target.positive_label,'1');
 await page.getByRole('button',{name:'Got it'}).click();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await upload();await page.getByLabel('Target column',{exact:true}).selectOption('target');await page.getByLabel('Fill missing values for me').check();
 await expect(page.getByLabel('measurement: Measurements',{exact:true})).not.toBeChecked();
 console.log(JSON.stringify({width,ambiguousTypesRequired:true,onlyNecessaryFields:true,save:true,reset:true,noOverflow:true}));await page.close();
}}finally{await browser.close();}
