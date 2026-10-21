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
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/research-inputs.fixture.html');
  await page.getByLabel('Knowledge mode',{exact:true}).selectOption(knowledge);
  await page.getByLabel('Data mode',{exact:true}).selectOption(data);
  assert.equal(await page.getByLabel('Dataset CSV path',{exact:true}).count(),data==='dataset'?1:0);
  assert.equal(await page.getByLabel('OKF bundle folder (contains index.md)',{exact:true}).count(),knowledge==='okf'?1:0);
  await page.getByLabel('Research name',{exact:true}).fill('Synthetic mode matrix');
  await page.getByLabel('Prediction objective and target meaning',{exact:true}).fill('Predict a synthetic future event');
  if(data==='dataset') {
   await page.getByLabel('Dataset CSV path',{exact:true}).fill('/synthetic/data.csv');
   await page.getByLabel('Target column',{exact:true}).fill('event');
   await page.getByLabel('Positive-class value (exact CSV value)',{exact:true}).fill('yes');
   await page.getByLabel('Negative-class value (exact CSV value)',{exact:true}).fill('no');
  } else await page.getByText('Without a dataset, this creates an analysis plan, not measured results.',{exact:false}).waitFor();
  if(knowledge==='okf') await page.getByLabel('OKF bundle folder (contains index.md)',{exact:true}).fill('/synthetic/okf');
  await page.getByRole('button',{name:'Inspect inputs',exact:true}).click();
  await page.getByText('Input checks passed; select this saved version in a pipeline',{exact:true}).waitFor();
  assert.equal(requests.length,1);
  assert.equal(requests[0].knowledge_mode,knowledge);
  assert.equal(requests[0].data_mode,data);
  assert.equal(requests[0].target.description,'Predict a synthetic future event');
  if(data==='proposal') assert.equal(requests[0].target.column,'');
  // An implicit textarea label can include its current value in its accessible name.
  await page.getByLabel('Prediction objective and target meaning').fill('A new objective');
  assert.equal(await page.getByText('Input checks passed; select this saved version in a pipeline',{exact:true}).count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.deepEqual(errors,[]);
  await page.close();
 }
 console.log('Four research modes at desktop/mobile: visibility, target payload, stale-inspection reset and no overflow passed. Backend responses mocked; no execution writes.');
} finally {await browser.close();}
