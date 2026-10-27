import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch();
try{for(const width of [390,1200]){
 const page=await browser.newPage({viewport:{width,height:1000}});let posted;
 await page.route('**/control/**',route=>{
 const path=new URL(route.request().url()).pathname;
 if(path==='/control/health')return route.fulfill({json:{llm:{provider:'test',model:'test-model'}}});
 if(path.endsWith('/upload'))return route.fulfill({json:{dataset_path:'/uploaded.csv',columns:['age','outcome','code','constant'],rows:3,missing_cells:0,columns_with_missing:{},nonfinite_columns:[]}});
 if(path.endsWith('/register')){posted=route.request().postDataJSON();return route.fulfill({json:{id:'test',configuration:posted,input_checks_passed:true,dataset:{rows:3,column_count:4,missing_cells:0,columns:['age','outcome','code','constant']},knowledge:{documents:0},issues:[]}});}
 throw Error(path);
 });
 await page.goto('http://127.0.0.1:4177/tests/research-inputs.fixture.html');
 await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'study.csv',mimeType:'text/csv',buffer:Buffer.from('age,outcome,code,constant\n10,survived,0,1\n20,died,1,1\n30,survived,0,1\n')});
 await page.getByLabel('Target column',{exact:true}).selectOption('outcome');
 await expect(page.getByLabel('Evaluation class',{exact:true})).toHaveCount(0);
 await expect(page.getByText('Review data columns',{exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Other outcome',{exact:true})).toHaveCount(0);
 await page.getByRole('radio',{name:'LLM only',exact:true}).check();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Your data is ready'})).toBeVisible();
 assert.equal(posted.target.positive_label,'survived');assert.equal(posted.target.negative_label,'died');
 await page.getByRole('button',{name:'Got it',exact:true}).click();
 await page.getByLabel('Target column',{exact:true}).selectOption('code');
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Your data is ready'})).toBeVisible();
 assert.equal(posted.target.column,'code');assert.equal(posted.target.positive_label,'1');assert.equal(posted.target.negative_label,'0');
 await page.getByRole('button',{name:'Got it',exact:true}).click();
 for(const column of ['age','constant']){
 await page.getByLabel('Target column',{exact:true}).selectOption(column);
 await expect(page.getByRole('alert')).toContainText('exactly two distinct');
 await expect(page.getByLabel('Evaluation class',{exact:true})).toHaveCount(0);
 }
 await page.getByLabel('Target column',{exact:true}).selectOption('code');
 await expect(page.getByLabel('Other outcome',{exact:true})).toHaveCount(0);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await expect(page.getByText('Value meaning “Yes”',{exact:false})).toHaveCount(0);
 console.log(JSON.stringify({width,automaticClassMapping:true,textClasses:true,invalidTargetsBlocked:true,noOverflow:true}));await page.close();
}}finally{await browser.close();}
