import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try {
 for(const width of [390,1280]) for(const knowledge of ['okf','llm_only']) for(const data of ['dataset','proposal']) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/control/**',async route=>{
   const request=route.request();
   if(request.method()==='GET') return route.fulfill({json:{inputs:[]}});
   assert.ok(new URL(request.url()).pathname.startsWith('/control/research-inputs/'));
   const configuration=request.postDataJSON();requests.push(configuration);
   return route.fulfill({json:{configuration,input_checks_passed:true,execution_ready:false,
    execution_note:'Preparation only; no execution started.',issues:[],
    dataset:{rows:data==='dataset'?120:0,column_count:data==='dataset'?6:0,columns:[],missing_cells:0},
    knowledge:{documents:knowledge==='okf'?1:0,domains:[]}}});
  });
  const initial={name:'Synthetic mode matrix',dataset_path:data==='dataset'?'/synthetic/data.csv':'',knowledge_path:'',knowledge_mode:'llm_only',data_mode:data,excluded_columns:[],missing_policy:'reject',target:{column:data==='dataset'?'event':'',positive_label:'yes',negative_label:'no',description:'Predict a synthetic future event',prediction_time:'',horizon:''}};
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html?initial='+encodeURIComponent(JSON.stringify(initial)));
  await page.getByRole('radio',{name:knowledge==='okf'?'My research folder':'LLM only',exact:true}).check();
  assert.equal(await page.getByLabel('Dataset CSV path',{exact:true}).count(),0);
  assert.equal(await page.getByLabel('Research document folder path',{exact:true}).count(),knowledge==='okf'?1:0);
  assert.equal(await page.getByLabel('Target column',{exact:true}).count(),data==='dataset'?1:0);
  if(knowledge==='okf') await page.getByLabel('Research document folder path',{exact:true}).fill('/synthetic/okf');
  await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
  await page.getByText('Inputs are ready to use',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Got it',exact:true}).click();
  assert.equal(requests.length,1);
  assert.equal(requests[0].knowledge_mode,knowledge);
  assert.equal(requests[0].data_mode,data);
  assert.equal(requests[0].target.description,'Predict a synthetic future event');
  if(data==='proposal') assert.equal(requests[0].target.column,'');
  // An implicit textarea label can include its current value in its accessible name.
  if(data==='proposal')await page.getByLabel('Prediction objective and target meaning').fill('A new objective');
  else await page.getByLabel('Target column',{exact:true}).fill('new_event');
  assert.equal(await page.getByText('Inputs are ready to use',{exact:true}).count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  await page.close();
 }
 console.log('Four research modes at desktop/mobile: visibility, target payload, stale-inspection reset and no overflow passed. Backend responses mocked; no execution writes.');
} finally {await browser.close();}
