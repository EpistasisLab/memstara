import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const metric={calls:1,tokens:100,tokens_status:'complete',cost:{usd:.01,status:'complete',missing_costs:0},seconds:1,status:'completed'};
const results=Array.from({length:120},(_,i)=>({result_id:i+1,trial:i,iteration:i+1,run_tag:'selected',
  interpretation:`Interpretation ${i+1}`,auc:(i+1)/121,columns_used:['age','target'],y_column:'target',
  evaluation:{skills:{hypothesis:[i%2?'whole':'no-knowledge']}}}));
const snapshot={run_tag:'selected',run_configuration:{trials:1,waves:120,books:{hypothesis:['whole','no-knowledge','unused']},
  combination_plan:{combinations:120,total_loops:120,repetitions:1}},results,
  report:{explanation_outputs:results.map(r=>({loop:r.iteration,result_id:r.result_id,status:'completed',text:`Explanation ${r.result_id}`}))},
  stale:false,health:{memstara:{up:true},core:{up:true}},board:{tasks:[]},scene:{places:[],agents:[],flashes:[]},agents:[],feed:[],access:{rows:[],windows:[]},runs:[]};
const totals={executions:[{...metric,run_tag:'selected',loops:results.map(r=>({...metric,number:r.iteration,pipeline_number:r.iteration,replicate_number:1})),unassigned:{...metric,calls:0}}],pipelines:[],total:metric};
const browser=await launchResponsiveBrowser();
try {for(const width of [390,1440]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',route=>route.fulfill({json:route.request().url().includes('/telemetry/totals')?totals:{}}));
  await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[],skills:[]}}));
  await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/execution-tiles.fixture.html`);
  await page.evaluate(s=>window.deliverOutputs(s),snapshot);
  const panel=page.getByTestId('execution-outputs');
  const tiles=panel.locator('.execution-output-tile');
  const filter=panel.getByLabel('Filter tiles by hypothesis skill');
  const sort=panel.getByLabel('Sort output tiles',{exact:true});
  const firstLoop=()=>tiles.first().locator('[data-loop]').getAttribute('data-loop');
  await expect(tiles).toHaveCount(100);
  await panel.getByLabel('Output page',{exact:true}).selectOption({value:'1'});
  await expect(panel.getByLabel('Output page',{exact:true})).toHaveValue('1');
  await expect(tiles).toHaveCount(20);
  await sort.selectOption('auroc_desc');
  await expect(tiles).toHaveCount(100);
  assert.equal(await firstLoop(),'120'); // Sort across all pages, not just the previous page.
  await filter.selectOption('whole');
  await expect(tiles).toHaveCount(60);
  assert.equal(await firstLoop(),'120');
  for(const view of ['Conclusions','Usage','Results']) {
    await panel.getByRole('navigation',{name:'Output views'}).getByRole('button',{name:view,exact:true}).click();
    await expect(filter).toHaveValue('whole');
    await expect(sort).toHaveValue('auroc_desc');
    await expect(tiles).toHaveCount(60);
    assert.equal(await firstLoop(),'120');
  }
  await sort.selectOption('auroc_asc');
  assert.equal(await firstLoop(),'2');
  await tiles.first().getByRole('button',{name:/Open Results/}).click();
  await expect(panel.locator('.output-documents')).toContainText('Interpretation 2');
  await panel.getByRole('button',{name:'Back to Results',exact:true}).click();
  await expect(filter).toHaveValue('whole');
  await filter.selectOption('unused');
  await expect(tiles).toHaveCount(0);
  await expect(panel).toContainText('No completed tiles match this hypothesis skill');
  await panel.getByRole('button',{name:'Reset tile view'}).click();
  await expect(tiles).toHaveCount(100);
  assert.equal(await firstLoop(),'1');
  for(const theme of ['light','dark']) {
    await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
    assert.equal(await panel.evaluate(el=>el.scrollWidth>el.clientWidth+2),false);
    const controls=panel.getByRole('region',{name:'Filter and sort output tiles'});
    await controls.scrollIntoViewIfNeeded();
    await controls.screenshot({path:`${process.env.TMPDIR}/output-tile-filters-${width}-${theme}.png`});
  }
  assert.deepEqual(errors,[]);
  await page.close();
  console.log(`PASS ${width}px: full-history sorting, skill filtering, shared three-view selection, details, reset and responsive themes`);
}} finally {await browser.close();}
