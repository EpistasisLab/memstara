import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const question={question_id:1,text:'Synthetic provenance question',okf_tags:[],rationale:'Fixture',origin_run:'fixture',origin_wave:0,writer:'fixture',times_used:1,status:'done'};
  const result={result_id:1,task_id:1,question_id:1,run_tag:'fixture',trial:0,hypothesis:'Synthetic hypothesis',columns_used:[],columns_missing:[],importance:{},auc:0.6,model:'LR',evaluation:{knowledge_provenance:{version:'hypothesis_provenance_v1',sources:[{id:'test/source',status:'mixed',provenance:{parsed_source_sha256:'a'.repeat(64),diagnostics:[],path_inventory:{version:'path_inventory_v1',row_count:19}}}]}}};
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/api/discovery/novelty')return route.fulfill({json:{items:[{task_id:1,result_id:1,question_id:1,run_tag:'fixture',trial:0,hypothesis:'Synthetic ranked hypothesis',auc:.6,novelty:{policy:'predicted_path_fraction_v1',rankable:true,coverage:1,score:.5,counts:{observed:1,predicted:1},paths:[{source_id:'test/source',path_id:'p1',status:'predicted',rationale:'Synthetic path support'}]}},{task_id:2,result_id:2,question_id:1,run_tag:'fixture',trial:0,hypothesis:'Unscored historical hypothesis',auc:null,novelty:null}],total:2,next_offset:null}});
   if(path==='/api/discovery/questions')return route.fulfill({json:{questions:[question],next_before:null}});
   if(path==='/api/discovery/questions/1')return route.fulfill({json:{question,tasks:[],results:[result],record_limit:100}});
   if(path.startsWith('/control/'))return route.fulfill({json:path==='/control/pipelines'?{pipelines:[]}:{}});
   if(path.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Unrelated fixture endpoint unavailable'}});
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/index.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://localhost/');
  await page.getByRole('button',{name:/Question universe/}).first().click();
  await page.getByRole('button',{name:'View options',exact:true}).click();await page.getByRole('button',{name:'List',exact:true}).click();await page.getByRole('button',{name:'View options',exact:true}).click();
  await page.locator('.universe-list button').first().click();
  await page.getByText('Source and run details',{exact:true}).click();
  const evidence=page.locator('[data-testid="knowledge-provenance"]');
  await evidence.locator(':scope > summary').click();
  await page.getByText('Mixed relations declared',{exact:true}).waitFor();
  assert.match(await evidence.innerText(),/not a novelty score/);
  assert.match(await evidence.innerText(),/test\/source/);
  assert.match(await evidence.innerText(),/19 path rows identified/);
  assert.equal(await evidence.evaluate(el=>el.scrollWidth>el.clientWidth+2),false);
  assert.deepEqual(errors,[]);
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'Explore questions',exact:true}).click();await page.getByRole('button',{name:'Novelty proxy ranking',exact:true}).click();
  const ranking=page.getByRole('region',{name:'KG novelty ranking'});
  await ranking.getByText('Synthetic ranked hypothesis').waitFor();
  assert.match(await ranking.innerText(),/50% predicted-path share/);
  assert.match(await ranking.innerText(),/Unscored/);
  await ranking.getByText('Inspect paths and calculation').first().click();
  assert.match(await ranking.innerText(),/Synthetic path support/);
  assert.equal(await ranking.evaluate(el=>el.scrollWidth>el.clientWidth+2),false);
  await ranking.getByRole('button',{name:'Open agent outputs'}).first().click();
  await page.getByRole('button',{name:'Hypothesis',exact:true}).first().waitFor();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width,provenance:'visible',overflow:false,errors}));
  await page.close();
 }
} finally {await browser.close();}
