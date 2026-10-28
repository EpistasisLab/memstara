import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch();
try{for(const width of [390,1200]){
 const page=await browser.newPage({viewport:{width,height:950}});let attempts=0,records=[];
 await page.route('**/control/**',route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  if(path.endsWith('/health'))return route.fulfill({json:{input_defaults:{dataset_available:true,knowledge_available:true,target_column:''}}});
  if(request.method()==='GET')return route.fulfill({json:{inputs:records}});
  if(path.endsWith('/upload'))return route.fulfill({json:{dataset_path:'/example.csv',rows:80,columns:['a','b','c','d','outcome'],missing_cells:0,columns_with_missing:{},binary_columns:['outcome'],nonfinite_columns:[],message:'No missing values found.'}});
  if(path.endsWith('/register')){
   attempts++;
   if(attempts===2)return route.fulfill({status:503,json:{error:'The data service is unavailable. Please try again.'}});
   const record={id:'a'.repeat(32),configuration:request.postDataJSON(),input_checks_passed:attempts===3,dataset:{rows:80,column_count:5,columns:['a','b','c','d','outcome'],missing_cells:0},knowledge:{documents:0},issues:attempts===1?[{code:'unmapped_target',message:'Target contains missing or unmapped labels; review the binary mapping'}]:[]};
   if(record.input_checks_passed)records=[record];return route.fulfill({json:record});
  }
  throw Error('Unexpected request '+path);
 });
 await page.goto('http://127.0.0.1:4177/tests/research-inputs.fixture.html?selector');
 await page.evaluate(()=>{const outer=document.createElement('dialog');outer.setAttribute('aria-label','Outer setup');outer.style.cssText='width:95vw;max-height:90vh;overflow:auto';document.body.append(outer);outer.append(document.querySelector('#root'));outer.showModal();});
 await page.getByRole('button',{name:'Upload new CSV',exact:true}).click();
 await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'test.csv',mimeType:'text/csv',buffer:Buffer.from('a,outcome\n1,0\n2,1')});
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 let feedback=page.getByRole('dialog',{name:'Review your data settings',exact:true});
 await expect(feedback).toContainText('Choose the outcome column');await expect(feedback).toContainText('Choose the outcome column');assert.equal(attempts,0);
 await page.keyboard.press('Escape');await expect(feedback).toHaveCount(0);await expect(page.getByRole('dialog',{name:'Outer setup'})).toBeVisible();
 await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'test.csv',mimeType:'text/csv',buffer:Buffer.from('a,outcome\n1,0\n2,1')});
 await page.getByLabel('Target column',{exact:true}).selectOption('outcome');
 await page.getByRole('radio',{name:'LLM only',exact:true}).check();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(feedback).toContainText('missing or unmapped labels');
 await feedback.screenshot({path:`/tmp/input-feedback-${width}-issues.png`});
 await feedback.getByRole('button',{name:'Back to settings'}).click();
 await expect(page.getByLabel('Target column',{exact:true})).toHaveValue('outcome');
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(feedback).toContainText('service is unavailable');await feedback.getByRole('button',{name:'Back to settings'}).click();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 feedback=page.getByRole('dialog',{name:'Your data is ready',exact:true});
 await expect(feedback).toContainText('Choose skills');await expect(page.getByLabel('Upload CSV',{exact:true})).toHaveCount(0);
 await feedback.screenshot({path:`/tmp/input-feedback-${width}-ready.png`});
 assert.equal(await feedback.evaluate(el=>el.scrollWidth>el.clientWidth+1),false);
 await feedback.getByRole('button',{name:'Got it'}).click();
 await expect(feedback).toHaveCount(0);await expect(page.getByLabel('Selected research configuration')).toContainText('a'.repeat(32));
 await expect(page.getByRole('button',{name:'Upload new CSV',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('button',{name:/Use saved data/})).toHaveAttribute('aria-pressed','false');
 await expect(page.locator('.research-source-options .research-badge')).toHaveCount(0);
 await page.getByRole('button',{name:'Edit data & target',exact:true}).click();
 await expect(page.getByRole('button',{name:'Upload new CSV',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'Cancel editing',exact:true}).click();
 await expect(page.getByRole('button',{name:'Upload new CSV',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:/Use saved data/}).click();
 await expect(page.getByRole('button',{name:/Use saved data/})).toHaveAttribute('aria-pressed','true');
 console.log(JSON.stringify({width,missingFields:true,serverIssues:true,serviceError:true,successAfterEditorCloses:true,escapePreservesParent:true}));await page.close();
}}finally{await browser.close();}
