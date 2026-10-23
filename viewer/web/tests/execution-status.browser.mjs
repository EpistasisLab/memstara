import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try{
 for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:5179')+'/tests/execution-status.fixture.html');
  const panel=page.getByRole('status');
  await panel.getByText(/Saved execution outcome.*2026-10-01/).waitFor();
  assert(!(await panel.innerText()).includes('The model connection failed or timed out.'));
  await panel.getByRole('button',{name:'Show execution details'}).click();
  await panel.getByText(/This execution failed at Hypothesis generation \(Pipeline 1 · Replicate 3\)/).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.getByRole('button',{name:'Select another execution'}).click();
  await page.getByText(/Loading the selected execution/).waitFor();
  assert.equal(await page.getByRole('button',{name:'Hide execution details'}).count(),0);
  await page.getByRole('button',{name:'Load completed execution'}).click();
  assert.equal(await page.getByRole('status').count(),0);
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Scoped historical failure, retained diagnostic, selection transition, completion, and mobile overflow checks passed.');
}finally{await browser.close();}
