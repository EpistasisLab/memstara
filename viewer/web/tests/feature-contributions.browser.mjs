import {chromium} from '@playwright/test';
import {build} from 'esbuild';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const webRoot=fileURLToPath(new URL('../',import.meta.url));
const dir=await mkdtemp(join(tmpdir(),'contributions-'));
const source=`import React,{useState} from 'react';import{createRoot}from'react-dom/client';import Chart from './src/components/FeatureContributionChart';
const modern={y_column:'target',model:'xgboost',importance:{positive:.02,negative:-.08,zero:0,target:99},evaluation:{explanation:{method:'holdout_permutation_auc',scope:'Explanation of the final replicate; AUC summary spans all replicates.',evaluated_replicate:2,total_replicates:2,evaluated_seed:43,evaluation_rows:80,permutation:{n_repeats:3,standard_deviation:{positive:.01,negative:.02,zero:0},repeat_values:{positive:[.01,.02,.03]}},shap:{units:'log-odds',mean_absolute:{positive:.1,negative:.9,zero:0}}}}};
function App(){const[k,set]=useState('modern');const r=k==='modern'?modern:k==='empty'?{importance:{},evaluation:{}}:{model:'xgboost',importance:{positive:.02,negative:-.08}};return <><button onClick={()=>set('legacy')}>Legacy fixture</button><button onClick={()=>set('empty')}>Empty fixture</button><Chart result={r}/></>};createRoot(document.getElementById('root')).render(<App/>);`;
await build({stdin:{contents:source,resolveDir:webRoot,loader:'tsx'},bundle:true,format:'esm',jsx:'automatic',outfile:join(dir,'app.js')});
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{
 for(const width of [1200,390])for(const theme of ['light','dark']){
 const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async r=>{const path=new URL(r.request().url()).pathname;if(path==='/app.js'||path==='/app.css')return r.fulfill({body:await readFile(join(dir,path.slice(1))),contentType:path.endsWith('js')?'application/javascript':'text/css'});return r.fulfill({body:`<html data-theme="${theme}"><head><link rel="stylesheet" href="/app.css"><style>:root{--ink:${theme==='dark'?'230 240 245':'30 40 50'};--ink-soft:120 130 140;--line:140 150 160;--accent:30 130 125}body{color:rgb(var(--ink));background:${theme==='dark'?'#17212c':'white'};font:14px sans-serif;padding:12px}.result-feature-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px}.result-feature-track{grid-column:1/-1;position:relative;background:#ddd}.result-feature-track>span{position:absolute;top:0;bottom:0}</style></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>`,contentType:'text/html'});});
 await page.goto('http://fixture.local/');await page.getByRole('heading',{name:'Prediction performance contribution'}).waitFor();
 const order=()=>page.locator('[data-feature]').evaluateAll(es=>es.map(e=>e.dataset.feature));
 assert.deepEqual(await order(),['positive','zero','negative']);assert.equal(await page.locator('.contribution-whisker').count(),3);
 assert.match(await page.locator('.contribution-scope').innerText(),/seed 43/);
 await page.getByRole('button',{name:'SHAP magnitude',exact:true}).click();assert.deepEqual(await order(),['negative','positive','zero']);assert.equal(await page.locator('.contribution-whisker').count(),0);
 assert.match(await page.locator('.result-chart-card').innerText(),/does not show whether/);
 await page.getByRole('button',{name:'Legacy fixture'}).click();assert(await page.getByRole('button',{name:'SHAP magnitude',exact:true}).isDisabled());assert.match(await page.locator('.result-chart-card').innerText(),/Method and units not recorded/);assert(!/gain importance/.test(await page.locator('.result-chart-card').innerText()));
 await page.getByRole('button',{name:'Empty fixture'}).click();assert.match(await page.locator('.result-chart-card').innerText(),/No feature contribution/);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);await page.close();
 console.log(JSON.stringify({width,theme,sorting:true,uncertainty:true,legacy:true,empty:true}));
 }
}finally{await browser.close();await rm(dir,{recursive:true,force:true});}
