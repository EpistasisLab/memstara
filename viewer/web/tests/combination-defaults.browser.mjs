import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';
const browser=await launchResponsiveBrowser();
try {for(const fallback of [false,true]) {
 const page=await browser.newPage({viewport:{width:390,height:750}});
 await page.route('**/control/**',r=>r.fulfill({json:{inputs:[],models:[],skills:[]}}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/responsive-scroll.fixture.html');
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:/Agent skills/}).click();
 const names=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
 for(let i=0;i<names.length;i++){
  await expect(dialog.locator('.comb-skill-card input:checked')).toHaveCount(1);
  if(i===0&&fallback)await dialog.locator('.comb-skill-card input:checked').uncheck();
  if(i===2){
   await expect(dialog.locator('.comb-ml-settings')).toHaveCount(0);
   if(fallback)await dialog.locator('.comb-skill-card input:checked').uncheck();
  }
  await dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+names[i+1],exact:true}).click();
 }
 await expect(dialog.getByRole('status',{name:'Pipeline replicate summary'})).toContainText('1total pipelines×1replicates per pipeline=1total replicates');
 if(fallback)await expect(dialog.locator('.comb-review-agents')).toContainText('Default scikit-learn Logistic Regression');
 await dialog.getByLabel('Name',{exact:true}).fill('Default setup');
 await dialog.getByRole('checkbox',{name:/I reviewed/}).check();
 await dialog.getByRole('button',{name:'Create combination design'}).click();
 const saved=JSON.parse(await page.locator('body').getAttribute('data-created'));
 assert.equal(saved.configuration.combination_skills.ml.length,fallback?0:1);
 assert.deepEqual(saved.configuration.ml_overrides,{});
 assert.equal(saved.configuration.waves,1);
 for(const role of ['hypothesis','data','interpreter','report'])assert.equal(saved.configuration.combination_skills[role].length,1);
 await page.close();
}} finally {await browser.close();}
