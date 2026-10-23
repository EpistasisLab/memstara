import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
let data={run_tag:'cost-fixture',status:'partial',usd:.25,recorded_calls:2,unpriced_calls:1,expected_calls:2,coverage_note:'Recorded attempts only',groups:[{stage:'ml',model:'gpt-4o',calls:2,priced_calls:1,usd:.25,input_tokens:1000,output_tokens:200}],records:[{id:'one',stage:'ml',loop:1,model:'gpt-4o',usd:.25,source:'deployment_catalog',prompt_tokens:1000,completion_tokens:200,cache_read_input_tokens:0,cache_creation_input_tokens:0,price_receipt:{source:'https://prices.azure.com/api/retail/prices',retrieved_at:'2026-10-07',rates:{input:2,output:8},components_usd:{input:.002,output:.0016}}},{id:'two',stage:'ml',loop:1,model:'gpt-4o',usd:null,source:'unavailable',reason:'Request failed; provider may still bill usage'}]};
const billingRequests=[];page.on('request',r=>{if(r.url().includes('/api/azure-costs'))billingRequests.push(r.url());});
const requestedLoops=[];await page.route('**/api/cost-details?*',r=>{const loop=new URL(r.request().url()).searchParams.get('loop');requestedLoops.push(loop);return r.fulfill({json:{...data,loop:loop===null?null:Number(loop)}});});
for(const width of [1280,390]){
 await page.setViewportSize({width,height:900});
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/cost-evidence.fixture.html');
 await page.getByText('Not provided by Motoro.',{exact:true}).waitFor();
 assert.equal(await page.getByText('Execution LLM request subtotal: $0.2500 · recorded subtotal').isVisible(),false);
 await page.getByText('Estimated cost · Motoro LLM requests',{exact:true}).click();
 await page.getByText('Execution LLM request subtotal: $0.2500 · recorded subtotal').waitFor();
 await page.getByText('Request amounts, token usage and pricing sources',{exact:true}).click();
 await page.getByText('Request failed; provider may still bill usage',{exact:false}).waitFor();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download cost evidence (JSON)'}).click();assert.match((await download).suggestedFilename(),/cost-evidence.json$/);
}
data={...data,status:'unavailable',usd:0,recorded_calls:0,unpriced_calls:0,groups:[],records:[]};
await page.reload();await page.getByText('Estimated cost · Motoro LLM requests',{exact:true}).click();await page.getByText('Execution LLM request subtotal: Not available').waitFor();
await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/cost-evidence.fixture.html?loop=2');
await page.getByText('Estimated cost · Motoro LLM requests',{exact:true}).click();
await page.getByText('Pipeline 1 · Replicate 2 LLM request subtotal: Not available',{exact:true}).waitFor();
assert(requestedLoops.includes('2'));
assert.deepEqual(errors,[]);assert.deepEqual(billingRequests,[]);
console.log('Cost UI: desktop/mobile, partial subtotal, unknown billing, expandable receipts, download and legacy missing ledger passed.');
}finally{await browser.close();}
