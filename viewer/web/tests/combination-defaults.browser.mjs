import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';
const browser=await launchResponsiveBrowser();
try {for(const fallback of [false,true]) {
 const page=await browser.newPage({viewport:{width:390,height:750}});
 await page.route('**/control/**',r=>r.fulfill({json:{inputs:[{id:'default-data',input_checks_passed:true,configuration:{name:'Default dataset',dataset_path:'/data.csv',knowledge_mode:'okf',knowledge_path:'/okf',data_mode:'dataset',target:{column:'outcome',positive_label:'1',negative_label:'0'},excluded_columns:[],missing_policy:'reject'}}],models:[],skills:[]}}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/responsive-scroll.fixture.html');
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Use Default dataset',exact:true}).click();await dialog.getByRole('button',{name:/Agent skills/}).click();
 const names=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
 for(let i=0;i<names.length;i++){
  await expect(dialog.locator('.comb-skill-card input:checked')).toHaveCount(1);
  if(i===1&&fallback)await dialog.getByLabel('Set the split myself',{exact:true}).check();
  if([0,3,4].includes(i)&&fallback)await dialog.locator('.comb-skill-card input:checked').uncheck();
  if(i===2){
   await expect(dialog.locator('.comb-ml-settings')).toHaveCount(0);
   if(fallback)await dialog.locator('.comb-skill-card input:checked').uncheck();
  }
  await dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+names[i+1],exact:true}).click();
 }
 await expect(dialog.getByRole('status',{name:'Pipeline replicate summary'})).toContainText('1total pipelines×1replicates per pipeline=1total runs');
 if(fallback)await expect(dialog.locator('.comb-review-agents')).toContainText('Default scikit-learn Logistic Regression');
 await dialog.getByLabel('Name',{exact:true}).fill('Default setup');
 await dialog.getByRole('checkbox',{name:/I reviewed/}).check();
 await dialog.getByRole('button',{name:'Create combination design'}).click();
 const saved=JSON.parse(await page.locator('body').getAttribute('data-created'));
 assert.equal(saved.configuration.combination_skills.ml.length,fallback?0:1);
 assert.deepEqual(saved.configuration.ml_overrides,{});
 assert.equal(saved.configuration.waves,1);
 for(const role of ['hypothesis','data','interpreter','report'])assert.equal(saved.configuration.combination_skills[role].length,role==='data'&&fallback?0:1);
 await page.close();
}} finally {await browser.close();}
