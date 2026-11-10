import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const columns=Array.from({length:24},(_,i)=>`LAB__${i}__Long recorded predictor name with its original punctuation, intact`);
const browser=await launchResponsiveBrowser();
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[],skills:[]}}));
  await page.route('**/api/**',route=>route.fulfill({json:{}}));
  await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/execution-tiles.fixture.html`);
  await page.evaluate(columns=>window.deliverOutputs({run_tag:'selected',run_configuration:{trials:1,waves:1},
    results:[{result_id:1,trial:0,iteration:1,run_tag:'selected',interpretation:'Saved interpretation',
      columns_used:[...columns,'target'],y_column:'target',auc:.8,model:'lr',
      evaluation:{model_results:{lr:{evaluation:{replicates:Array.from({length:8},(_,j)=>({seed:100+j,
        parameters:{C:1,max_iter:1000,solver:'lbfgs',class_weight:'balanced'},operating_point:{probability_cutoff:.45}}))}},
        rf:{evaluation:{replicates:[]}}},ml_configuration:{effective:{models:{rf:{parameters:{n_estimators:200}}}}}}}],
    report:null,stale:false,health:{memstara:{up:true},core:{up:true}},board:{tasks:[],lanes:{}},
    scene:{places:[],agents:[],flashes:[]},agents:[],feed:[],access:{rows:[],windows:[]},runs:[]}),columns);
  const tile=page.locator('.execution-output-tile');
  await expect(tile).toHaveCount(1);
  await expect(tile.locator('.output-record-meta')).toHaveCount(0);
  await tile.getByRole('button',{name:/Open Results/}).focus();
  await page.keyboard.press('Enter');
  await page.locator('.output-data-details summary').click();
  const detail=page.locator('.output-data-details');
  await expect(detail.locator('.output-predictor-meta dd')).toHaveText(columns.join(' ● '));
  await expect(detail).toContainText('Fit 8:');
  await expect(detail).toContainText('Recorded fit seed: 107');
  await expect(detail).toContainText('Decision threshold: 0.45');
  await expect(detail).toContainText('Configured (not verified as fitted): n_estimators=200');
  assert.deepEqual(errors,[]);
  console.log('PASS: sketch tiles omit metadata; keyboard-opened details preserve every predictor, fitted parameter, seed, threshold and configured-only label');
} finally {await browser.close();}
