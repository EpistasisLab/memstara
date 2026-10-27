import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
const browser=await launchResponsiveBrowser();
const original='  # shared-shap\n\n| Metric | Confidence | Reproducibility | Robustness | Novelty |\n|---|---|---|---|---|\n| AUROC | original confidence | original reproducibility | original robustness | original novelty |\n\n```markdown\n# shared-lime\n```\n\n<img src=x onerror="window.unwanted=true">\n\n![Original image](/original.svg)\n\nEnd of original.\n';
const explanation=original.replace('shared-shap','shared-heart-failure-cardiovascular');
try{for(const width of [320,768,1440]){
 const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route(/\/(api|control)\//,r=>r.fulfill({status:503,json:{error:'Offline fixture'}}));
 await page.route('**/original.svg',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8"/></svg>'}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/agent-verbatim.fixture.html');
 await page.evaluate(([i,e])=>window.deliverOriginals(i,e),[original,explanation]);
 const results=page.locator('#results-panel');
 const interpreter=results.locator('[data-interpretation-slot] .report-markdown');
 const report=page.getByTestId('report-page');const expert=report.locator('[data-report-content] .report-markdown');
 for(const [body,title] of [[interpreter,'shared-shap'],[expert,'shared-heart-failure-cardiovascular']]){
  await expect(body.getByRole('heading',{name:title,exact:true})).toBeVisible();
  for(const label of ['Confidence','Reproducibility','Robustness','Novelty'])await expect(body.locator('th').filter({hasText:label})).toHaveCount(1);
  await expect(body.locator('code')).toHaveText('# shared-lime\n');
  await expect(body.getByRole('img',{name:'Original image'})).toHaveCount(1);
  await expect(body.locator('.assessment-badge,.report-table-hint')).toHaveCount(0);
  await expect(body).toContainText('<img src=x onerror="window.unwanted=true">');
  await expect(body).toContainText('End of original.');
  await expect(body).not.toContainText('WRONG');
 }
 for(const injected of ['Agent research proposal','Original hypothesis','Clinical interpretation','Model performance and technical details','Compare recorded analyses','Data allocation','Prediction target (not an input)','WRONG AGGREGATE'])await expect(results).not.toContainText(injected);
 await expect(interpreter).toHaveCount(1);
 assert.equal(await page.evaluate(()=>window.unwanted),undefined);
 const event=page.waitForEvent('download');await report.getByRole('button',{name:'Download Markdown'}).click();
 const download=await event;let saved='';for await(const chunk of await download.createReadStream())saved+=chunk;
 assert.equal(saved,explanation);
 // Change analyses and inspect two independent agent documents. Neither recorded
 // ML metrics nor a legacy aggregate may leak into this output-only panel.
 const lime='## LIME original\n\nConfusion matrix on test set\n\n| Actual / predicted | 0 | 1 |\n|---|---|---|\n| 0 | 12 | 3 |\n| 1 | 2 | 7 |\n\nAgent research proposal — quoted by the original agent.\n';
 const base={trial:0,perspective:'UNWANTED perspective',hypothesis:'UNWANTED hypothesis',interpretation:'WRONG AGGREGATE',columns_used:['age'],columns_missing:[],importance:{age:.1},y_column:'outcome',auc:.999,model:'lr',okf_concept_ids:[],created_at:'2026-10-27T00:00:00Z'};
 const rows=[{...base,result_id:101,evaluation:{interpretations:[
  {slot:1,worker:'interpret#1',skill:'shared-shap',status:'done',text:original,error:'',limitations:'UNWANTED separately stored limitations'},
  {slot:2,worker:'interpret#2',skill:'shared-lime',status:'done',text:lime,error:''}],
  model_results:{lr:{auc:.999,n_train:70,n_test:30,evaluation:{replicates:[]}}}}},
  {...base,result_id:102,trial:1,interpretation:'## Second replicate original\n\nExact saved result.',evaluation:{}},
  {...base,result_id:103,trial:2,interpretation:'',evaluation:{interpretations:[{slot:1,skill:'shared-shap',status:'pending',text:'',error:''}]}}];
 await page.evaluate(records=>window.deliverResults(records),rows);
 const select=results.getByRole('combobox',{name:'Analysis to inspect'});
 await select.selectOption('verbatim:101');
 await expect(results.locator('[data-interpretation-slot]')).toHaveCount(2);
 await expect(interpreter).toHaveCount(2);
 await expect(results.getByRole('heading',{name:'shared-shap',exact:true})).toHaveCount(1);
 await expect(results.getByRole('heading',{name:'LIME original',exact:true})).toHaveCount(1);
 await expect(results.locator('[data-interpretation-slot="2"] table')).toHaveCount(1);
 await expect(results).toContainText('Agent research proposal — quoted by the original agent.');
 await expect(results).not.toContainText('UNWANTED');
 await expect(results).not.toContainText('WRONG');
 await expect(results).not.toContainText('0.999');
 await expect(results.locator('.assessment-badge,.content-origin,details')).toHaveCount(0);
 await select.selectOption('verbatim:102');
 await expect(interpreter).toHaveCount(1);
 await expect(interpreter.getByRole('heading',{name:'Second replicate original'})).toBeVisible();
 await expect(results).not.toContainText('LIME original');
 await select.selectOption('verbatim:103');
 await expect(interpreter).toHaveCount(0);
 await expect(results).toContainText('This perspective is not yet available.');
 await expect(results).not.toContainText('0.999');
 await select.selectOption('verbatim:101');
 const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
 assert(geometry.scroll<=geometry.width+1,JSON.stringify(geometry));
 assert.deepEqual(errors,[]);
 await page.screenshot({path:`/private/tmp/memstara-verbatim-${width}.png`,fullPage:true});
 console.log(JSON.stringify({width,allColumns:true,originalNames:true,fencesPreserved:true,rawHtmlInert:true,downloadExact:true,onlyAgentOutputs:true,independentBranches:true,replicateSwitch:true,pendingHasNoFabricatedOutput:true,noOverflow:true}));
 await page.close();
}}finally{await browser.close();}
