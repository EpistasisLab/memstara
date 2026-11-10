import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const rows=[10,2,null,0].map((n,i)=>({result_id:i+1,run_tag:`run-${i}`,pipeline_name:`Experiment ${n??'unknown'}`,
  trial:i,iteration:i+1,hypothesis_id:`skill-${n??'unknown'}`,model:`model ${n??'unknown'}`,
  evaluation:{model:`model ${n??'unknown'}`,evaluation:{replicates:[{seed:n,auc:n===null?null:n/10,
    operating_point:{true_negative:n,false_positive:n,false_negative:n,true_positive:n}}]}}}));
const browser=await launchResponsiveBrowser();
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(/\/(api|control)\//.test(request.url()))requests.push(request.url());});
  await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/hypothesis-metrics.fixture.html`);
  await page.evaluate(rows=>window.deliverMetricResults(rows),rows);
  await page.getByRole('button',{name:/Compare hypothesis results/}).click();
  const table=page.getByRole('region',{name:'Scrollable hypothesis comparison'});
  const values=column=>table.locator(`tbody tr td:nth-child(${column})`).allTextContents();
  await expect(table.locator('tbody tr')).toHaveCount(4);
  for(const [label,column] of [['Seed',3],['AUROC',5],['TN',6],['FP',7],['FN',8],['TP',9]]) {
    await table.getByRole('button',{name:`${label}: sort ascending`,exact:true}).click();
    assert.deepEqual(await values(column),label==='AUROC'?['0.000','0.200','1.000','—']:['0','2','10','—']);
    await expect(table.locator('th[aria-sort="ascending"]')).toContainText(label);
    const header=table.getByRole('button',{name:`${label}: sort descending`,exact:true});
    await header.focus(); await page.keyboard.press('Enter');
    assert.deepEqual(await values(column),label==='AUROC'?['1.000','0.200','0.000','—']:['10','2','0','—']);
    await expect(table.locator('th[aria-sort="descending"]')).toContainText(label);
  }
  for(const [label,column,prefix] of [['Hypothesis skill',1,'skill '],['Pipeline / run',2,'Experiment '],['Model',4,'model ']]) {
    await table.getByRole('button',{name:`${label}: sort ascending`,exact:true}).click();
    const text=await values(column);
    assert(text[0].startsWith(`${prefix}0`) && text[1].startsWith(`${prefix}2`) && text[2].startsWith(`${prefix}10`));
  }
  await table.getByRole('button',{name:'Seed: sort ascending',exact:true}).click();
  await page.evaluate(rows=>window.deliverMetricResults([...rows,{...rows[0],result_id:5,
    evaluation:{evaluation:{replicates:[{seed:1,auc:.8}]}}}]),rows);
  await expect(table.locator('tbody tr')).toHaveCount(5);
  assert.deepEqual(await values(3),['0','1','2','10','—']);
  for(const theme of ['light','dark']) {
    await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
    const header=table.locator('th[aria-sort] button');
    await expect(header).toBeVisible();
    const contrast=await header.evaluate(el=>{const probe=document.createElement('span');
      probe.style.color='rgb(var(--accent))';el.append(probe);
      const same=getComputedStyle(probe).color===getComputedStyle(el).color;probe.remove();return same;});
    assert(contrast);
  }
  assert.deepEqual(errors,[]); assert.deepEqual(requests,[]);
  console.log('PASS: all nine columns sort; keyboard, missing-last, numeric zero, live updates and both themes; no backend requests');
} finally {await browser.close();}
