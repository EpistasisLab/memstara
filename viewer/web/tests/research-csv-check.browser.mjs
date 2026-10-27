import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try {for(const width of [360,1200]){for(const missing of [0,1]){
 const page=await browser.newPage({viewport:{width,height:1000}});let checked=0,registered=0,submitted;
 const columns=['age','stage','b','c','target'];
 const preset={name:'Heart failure study',target:{column:'target',positive_label:'1',negative_label:'0',description:'Documented demo outcome',prediction_time:'Timing unverified',horizon:''},categorical_columns:['stage'],knowledge_path:'/app/examples/heart-failure/okf'};
 const csv={dataset_path:'/uploaded.csv',columns,rows:80,missing_cells:missing,columns_with_missing:missing?{age:1}:{},nonfinite_columns:[],nonnumeric_columns:[],binary_columns:['target'],message:missing?'Missing values found.':'No missing values found.',setup_options:{knowledge_sources:[{label:'Heart failure research library',path:'/app/examples/heart-failure/okf'}],preset}};
 await page.route('**/control/**',r=>{
  const path=new URL(r.request().url()).pathname;
 if(path==='/control/health')return r.fulfill({json:{llm:{provider:'test',model:'test-model'}}});
  if(path.endsWith('/upload'))return r.fulfill({json:csv});
  if(path.endsWith('/check-csv')){checked++;assert.deepEqual(r.request().postDataJSON(),{dataset_path:'/uploaded.csv'});return r.fulfill({json:csv});}
  if(path.endsWith('/register')){registered++;submitted=r.request().postDataJSON();return r.fulfill({json:{id:'test',configuration:submitted,input_checks_passed:true,dataset:{rows:80,column_count:5,columns,missing_cells:missing},knowledge:{documents:0},issues:[]}});}
  throw Error('Unexpected endpoint '+path);
 });
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html');
 await page.evaluate(()=>document.querySelector('section').classList.add('research-input-shell'));
 await expect(page.getByRole('button',{name:'Check inputs',exact:true})).toHaveCount(0);
 await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'heart.csv',mimeType:'text/csv',buffer:Buffer.from('age,target\n,1\n55,0\n')});
 if(missing){await expect(page.getByLabel('Target column',{exact:true})).toHaveCount(0);await page.getByLabel('Fill missing values for me').check();}
 await expect(page.getByLabel('Target column',{exact:true})).toBeVisible();assert.equal(checked,0);
 await expect(page.getByLabel('Research document folder path')).toHaveCount(0);
 await expect(page.getByLabel('Prediction objective and target meaning')).not.toBeVisible();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Outcome column');assert.equal(registered,0);await page.getByRole('button',{name:'Back to settings',exact:true}).click();
 await page.getByLabel('Target column',{exact:true}).selectOption('target');
 await expect(page.getByLabel('Other outcome',{exact:true})).toHaveCount(0);
 await page.getByRole('radio',{name:'Heart Failure example',exact:true}).check();
 await expect(page.getByLabel('Research document folder path')).toHaveCount(0);
 const libraryDetails=page.locator('details').filter({has:page.getByText('View library folder path',{exact:true})});
 await expect(libraryDetails).not.toHaveAttribute('open','');
 await libraryDetails.locator('summary').click();
 await expect(libraryDetails).toContainText('/app/examples/heart-failure/okf');
 if(missing)await page.getByLabel('Fill missing values for me').check();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await page.getByRole('button',{name:'Got it',exact:true}).click();
 assert.equal(submitted.knowledge_path,'/app/examples/heart-failure/okf');
 assert.equal(submitted.knowledge_mode,'okf');
 await page.getByRole('radio',{name:'My research folder',exact:true}).check();
 await page.getByLabel('Research document folder path').fill('/custom/research/okf');
 await expect(page.getByText('What path should I enter?',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await page.getByRole('button',{name:'Got it',exact:true}).click();
 assert.equal(submitted.knowledge_path,'/custom/research/okf');
 await page.getByRole('radio',{name:'LLM only',exact:true}).check();
 if(missing)await expect(page.getByLabel('Fill missing values for me')).toBeChecked();
 await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
 await expect(page.getByText('Inputs are ready to use',{exact:true})).toBeVisible();assert.equal(registered,3);assert.equal(submitted.knowledge_path,'');assert.equal(submitted.knowledge_mode,'llm_only');await page.getByRole('button',{name:'Got it',exact:true}).click();
 assert.equal(submitted.target.positive_label,'1');assert.equal(submitted.target.negative_label,'0');assert.equal(submitted.target.description,'');assert.equal(submitted.target.prediction_time,'');assert.equal(submitted.target.horizon,'');
 assert.equal(submitted.missing_policy,missing?'impute_train_v1':'reject');
 await expect(page.getByText('Using the Heart Failure example?',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Use Heart Failure settings',exact:true})).toHaveCount(0);
 await page.getByLabel('Target column',{exact:true}).selectOption('age');
 await expect(page.getByRole('alert')).toContainText('exactly two distinct');
 await page.getByRole('radio',{name:'My research folder',exact:true}).check();
 await expect(page.getByLabel('Research document folder path')).toBeVisible();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await page.screenshot({path:`/tmp/research-setup-${width}-${missing}.png`,fullPage:true});
 console.log(JSON.stringify({width,missing,csvOnly:true,knowledgeSourceSwitching:true,collapsedPaths:true,noOverflow:true}));await page.close();
}}}finally{await browser.close();}
