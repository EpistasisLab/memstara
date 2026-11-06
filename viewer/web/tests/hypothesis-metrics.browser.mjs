import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const skills=['addiction-psychiatric','addiction-substance-use','hiv-no-knowledge','hiv-okf-whole-graph'];
const matrices=[{tn:50,fp:10,fn:5,tp:35},{tn:60,fp:0,fn:0,tp:40},{tn:0,fp:60,fn:0,tp:40},
 {tn:55,fp:5,fn:10,tp:30},{tn:45,fp:15,fn:20,tp:20},{tn:40,fp:20,fn:2,tp:38}];
const results=skills.flatMap((skill,g)=>matrices.map((matrix,i)=>({
 run_tag:i<4?'before-resume':'after-resume',result_id:g*6+i+1,trial:g*6+i,iteration:g*6+i+1,y_column:'HIV_DETECTABLE',model:i%2?'xgboost':'logistic_regression',
 evaluation:{skills:{hypothesis:[skill]},model:i%2?'xgboost':'logistic_regression',evaluation:{replicates:[{
  seed:i+100,n_test:100,performance:{test:{n:100,threshold:.42,confusion_matrix:{...matrix,labels:[0,1],rows:'actual',columns:'predicted'}}}}]}}
})));
const browser=await chromium.launch({headless:true,...(process.env.MEMSTARA_BROWSER_EXECUTABLE?{executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE}:{})});
try{for(const width of [320,768,1440]){
 const page=await browser.newPage({viewport:{width,height:1000},acceptDownloads:true});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/hypothesis-metrics.fixture.html`);
 if(width===768)await page.evaluate(()=>document.documentElement.dataset.theme='dark');
 await page.evaluate(rows=>window.deliverMetricResults(rows),results);
 const component=page.getByRole('region',{name:'Hypothesis skill performance distributions'});
 await expect(component.getByRole('group',{name:/by hypothesis skill/})).toHaveCount(1);
 await expect(component.getByRole('button',{name:/^addiction-psychiatric; pipeline 1;/})).toHaveCount(1);
 await component.getByRole('button',{name:/^addiction-psychiatric; pipeline 1;/}).click();
 await expect(component.getByRole('region',{name:'Selected evaluation evidence'})).toContainText('before-resume');
 await expect(component.getByRole('region',{name:'Selected evaluation evidence'})).toContainText('50 / 10 / 5 / 35');
 await component.getByLabel('Performance metric').selectOption('npv');
 await component.getByRole('region',{name:'Metric coverage and skill summary'}).scrollIntoViewIfNeeded();
 await expect(component.getByRole('region',{name:'Metric coverage and skill summary'})).toContainText('5 / 6');
 await component.getByLabel('Performance metric').selectOption('dor');
 await component.getByText('Recorded values and calculation reasons',{exact:true}).click();
 await expect(component).toContainText('Positive infinity: denominator is zero.');
 await expect(component).toContainText('Undefined: numerator and denominator are both zero.');
 await component.getByLabel('Comparison model').selectOption('logistic_regression');
 await expect(component.getByRole('region',{name:'Metric coverage and skill summary'})).toContainText('2 / 3');
 await component.getByLabel('Performance metric').selectOption('fbeta');
 await component.getByText('Comparison options',{exact:true}).click();
 await component.getByLabel('F-beta weight').fill('2');
 const pending=page.waitForEvent('download');await component.getByRole('button',{name:'Download all metrics CSV'}).click();
 const file=await pending,stream=await file.createReadStream();const chunks=[];for await(const c of stream)chunks.push(c);
 const csv=Buffer.concat(chunks).toString();assert(csv.includes('before-resume'));assert(csv.includes('after-resume'));assert(csv.includes('Custom F-beta'));
 assert(!csv.includes('"NaN"'));assert(!csv.includes('"Infinity"'));
 await component.getByLabel('F-beta weight').fill('0');await expect(component.getByRole('alert')).toContainText('greater than 0');
 await expect(component.getByRole('button',{name:'Download all metrics CSV'})).toBeDisabled();
 await component.getByLabel('F-beta weight').fill('1');
 await component.getByLabel('Comparison model').selectOption('all');
 await component.getByLabel('Performance metric').selectOption('balanced_accuracy');
 const overflow=await page.evaluate(()=>({body:document.body.scrollWidth>innerWidth+2,component:document.querySelector('.hypothesis-metric-comparison').scrollWidth>document.querySelector('.hypothesis-metric-comparison').clientWidth+2}));
 assert.deepEqual(overflow,{body:false,component:false});
 await page.screenshot({path:join(tmpdir(),`memstara-hypothesis-metrics-${width}.png`),fullPage:true});
 await component.getByRole('button',{name:/Show all \d+ metric charts/}).click();
 assert(await component.getByRole('group',{name:/by hypothesis skill/}).count()>=50);
 await component.getByRole('button',{name:'Hide all metric charts'}).click();
 await page.evaluate(skills=>window.deliverPlannedSkills([...skills,'not-yet-evaluated']),skills);
 await expect(component.getByRole('row',{name:/Not Yet Evaluated 0 \/ 0/})).toHaveCount(1);
 // Updates replace the same evaluation rather than duplicating it.
 await page.evaluate(rows=>window.deliverMetricResults([...rows,rows[0]]),results);
 await expect(component.getByRole('region',{name:'Metric coverage and skill summary'})).toContainText('6 / 6');
 assert.deepEqual(errors,[]);
 console.log(`PASS ${width}px: boxes, prior-run evidence, undefined/infinite coverage, model filter, beta, CSV, all charts, no overflow`);
 await page.close();
}}finally{await browser.close();}
