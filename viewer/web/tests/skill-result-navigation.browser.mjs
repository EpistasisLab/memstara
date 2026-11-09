import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const skills=['hiv-no-knowledge','hiv-okf-whole-graph','addiction-psychiatric','addiction-substance-use'];
const fit=(seed,tn,tp)=>({seed,performance:{test:{n:100,threshold:.5,confusion_matrix:{tn,fp:60-tn,fn:40-tp,tp,labels:[0,1],rows:'actual',columns:'predicted'}}}});
const rows=skills.flatMap((skill,index)=>['before-resume','after-resume'].map((tag,j)=>({
 run_tag:tag,result_id:index+1,task_id:index+1,trial:index*2+j,iteration:index*2+j+1,pipeline_number:index+1,
 pipeline_name:'Formal HIV study',hypothesis_id:skill,model:'lr',y_column:'HIV_DETECTABLE',auc:.8,
 created_at:`2026-11-05T12:0${index*2+j}:00Z`,interpretation:`Original ${tag} interpretation for result ${index+1}.`,
 evaluation:{skills:{hypothesis:[skill]},model_results:{lr:{evaluation:{replicates:[fit(42,50+j,30+index),fit(43,48+j,32+index)]}},xgb:{evaluation:{replicates:[fit(44,52+j,31+index)]}}}},
})));
const snapshot=results=>({run_tag:'after-resume',generated_at:'2026-11-05T14:00:00Z',stale:false,
 health:{core:{up:true},memstara:{up:true}},runs:[],board:{tasks:[],lanes:{}},scene:{places:[],agents:[],flashes:[]},feed:[],agents:[],access:{rows:[],windows:[]},
 results,run_configuration:{pipeline_name:'Formal HIV study',trials:1},report:{status:'done',run_tags:['before-resume','after-resume']}});
const browser=await chromium.launch({headless:true,...(process.env.MEMSTARA_BROWSER_EXECUTABLE?{executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE}:{})});
try{for(const [width,theme] of [[1440,'light'],[768,'dark'],[390,'light'],[320,'dark']]){
 const page=await browser.newPage({viewport:{width,height:950},reducedMotion:'reduce'}),errors=[],requests=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route(/\/(api|control)\//,route=>{requests.push(route.request().method());return route.abort();});
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/skill-result-navigation.fixture.html`);
 await page.waitForFunction(()=>typeof window.deliverChartSnapshot==='function');
 await page.evaluate(({rows,theme})=>{document.documentElement.dataset.theme=theme;window.deliverChartSnapshot(rows);},{rows:snapshot(rows),theme});
 const panel=page.locator('#results-panel'),comparison=page.getByRole('region',{name:'Hypothesis skill performance distributions'});
 await comparison.getByRole('button',{name:/Compare performance by hypothesis skill/}).click();
 const card=panel.getByRole('article',{name:'Selected interpretation outputs'});
 await expect(comparison).toContainText('24 evaluations');
 await expect(card).toContainText('Original after-resume interpretation for result 4.');
 const point=comparison.getByRole('button',{name:/^hiv-no-knowledge; pipeline 1; result 1; fit 2; lr;.*before-resume$/});
 await point.scrollIntoViewIfNeeded();await point.hover();
 await expect(page.getByRole('tooltip')).toContainText('HIV — No Knowledge');
 await expect(page.getByRole('tooltip')).toContainText('Fit 2');
 await point.click();
 await expect(card).toContainText('Original before-resume interpretation for result 1.');
 await expect(card).toContainText('Result 1 · lr · Fit 2 · Seed 43');
 await expect(card).toHaveAttribute('data-chart-selected','true');await expect(card).toBeFocused();
 const heading=card.locator('.result-chart-context');await expect(heading).toBeInViewport();
 await card.getByRole('button',{name:'Back to comparison'}).click();
 await expect(panel.locator('.result-comparison-anchor')).toBeFocused();
 await expect(comparison.getByText('Compare performance by hypothesis skill',{exact:true})).toBeInViewport();
 // Identical numeric IDs in different attempts must select the correct saved document.
 const later=comparison.getByRole('button',{name:/^hiv-no-knowledge; pipeline 1; result 1; fit 1; xgb;.*after-resume$/});
 await later.focus();await later.press('Enter');
 await expect(card).toContainText('Original after-resume interpretation for result 1.');
 await expect(card).toContainText('Result 1 · xgb · Fit 1 · Seed 44');
 // New results and polling do not overwrite an explicitly selected original result.
 await page.evaluate(rows=>window.deliverChartSnapshot(rows),snapshot([...rows].reverse()));
 await expect(card).toContainText('Original after-resume interpretation for result 1.');
 await panel.getByLabel('Analysis to inspect').selectOption('before-resume:2');
 await expect(card).toContainText('Original before-resume interpretation for result 2.');
 await expect(card).not.toHaveAttribute('data-chart-selected','true');
 await comparison.getByRole('button',{name:'MCC',exact:true}).click();
 await expect(comparison.getByLabel('Performance metric')).toHaveValue('mcc');
 await comparison.getByText('Comparison options',{exact:true}).click();
 const color=await comparison.locator('.hmc-skill-name').filter({hasText:'HIV — No Knowledge'}).locator('i').evaluate(element=>element.style.background);
 await comparison.getByLabel('Skill order').selectOption('high');
 assert.equal(await comparison.locator('.hmc-skill-name').filter({hasText:'HIV — No Knowledge'}).locator('i').evaluate(element=>element.style.background),color);
 await comparison.getByLabel('Comparison model').selectOption('lr');
 await expect(comparison.getByLabel('Comparison coverage')).toContainText('16');
 await comparison.getByLabel('Skill order').selectOption('name');
 await comparison.getByLabel('Performance metric').selectOption('balanced_accuracy');
 await comparison.getByText('Comparison options',{exact:true}).click();
 if(width===1440){
  await comparison.getByRole('button',{name:/Show all \d+ metric charts/}).click();
  const gallery=comparison.getByRole('article',{name:'F1 / Dice score distribution',exact:true});
  const galleryPoint=gallery.getByRole('button',{name:/^addiction-psychiatric; pipeline 3; result 3; fit 1; lr;.*before-resume$/});
  await galleryPoint.focus();await galleryPoint.press('Space');
  await expect(card).toContainText('Original before-resume interpretation for result 3.');
  await expect(card).toBeFocused();await expect(comparison.getByLabel('Performance metric')).toHaveValue('f1');
  await card.getByRole('button',{name:'Back to comparison'}).click();
  await comparison.getByRole('button',{name:'Hide all metric charts'}).click();
  await comparison.getByLabel('Performance metric').selectOption('balanced_accuracy');
 }
 await comparison.scrollIntoViewIfNeeded();
 assert.equal(await page.evaluate(()=>document.body.scrollWidth>innerWidth+1),false);
 assert.equal(await comparison.evaluate(element=>element.scrollWidth>element.clientWidth+1),false);
 await page.screenshot({path:join(tmpdir(),`memstara-skill-comparison-${width}-${theme}.png`)});
 assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
 console.log(`PASS ${width}px ${theme}: original run/result, model/fit, mouse and keyboard, focus/scroll/highlight, polling, stable colours, filters, no overflow or backend requests`);
 await page.close();
}
for(const width of [1440,390]){
 const page=await browser.newPage({viewport:{width,height:950},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route(/\/(api|control)\//,route=>route.fulfill({json:{experiments:[],executions:[],pipelines:[]}}));
 await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/skill-result-navigation.fixture.html?tiles=1`);
 await page.waitForFunction(()=>typeof window.deliverChartSnapshot==='function');
 await page.evaluate(value=>window.deliverChartSnapshot(value),snapshot(rows));
 const panel=page.getByTestId('execution-outputs');
 await panel.getByText('Compare performance by hypothesis skill',{exact:true}).click();
 await expect(panel.locator('.execution-output-tile')).toHaveCount(8);
 const comparison=page.getByRole('region',{name:'Hypothesis skill performance distributions'});
 const earlier=comparison.getByRole('button',{name:/^hiv-no-knowledge; pipeline 1; result 1; fit 2; lr;.*before-resume$/});
 await earlier.click();
 const article=panel.getByRole('article',{name:'Interpretation output for analysis 1',exact:true});
 await expect(article).toContainText('Original before-resume interpretation for result 1.');
 await expect(article).toContainText('Result 1 · lr · Fit 2 · Seed 43');
 await expect(article).toBeFocused();await expect(article).toHaveAttribute('data-chart-selected','true');
 await expect(article.locator('.result-chart-context')).toBeInViewport();
 await article.getByRole('button',{name:'Back to comparison'}).click();
 await expect(panel.locator('.result-comparison-anchor')).toBeFocused();
 const later=comparison.getByRole('button',{name:/^hiv-no-knowledge; pipeline 1; result 1; fit 1; xgb;.*after-resume$/});
 await later.focus();await later.press('Enter');
 await expect(article).toContainText('Original after-resume interpretation for result 1.');
 await expect(article).toContainText('Result 1 · xgb · Fit 1 · Seed 44');
 await expect(article).toBeFocused();
 assert.deepEqual(errors,[]);
 console.log(`PASS ${width}px: primary Results tiles also follow the chart's original execution/result and exact fit`);
 await page.close();
}
}finally{await browser.close();}
