import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
const browser=await launchResponsiveBrowser();
try{for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];page.setDefaultTimeout(10000);
 page.on('pageerror',e=>errors.push(e.message));
 await page.route(/\/(api|control)\//,r=>r.fulfill({status:503,json:{error:'Offline fixture'}}));
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:26797')+'/tests/meeting-ui.fixture.html');
 await expect(page.locator('.cf-room')).toHaveCount(5);
 await page.getByLabel('Focus floor plan agent').selectOption('ml');
 await page.waitForTimeout(300);
 const geometry=()=>page.locator('.react-flow').evaluate(e=>({viewport:e.querySelector('.react-flow__viewport').style.transform,nodes:[...e.querySelectorAll('.cf-room')].map(n=>({width:n.offsetWidth,height:n.offsetHeight}))}));
 const before=await geometry();
 for(let index=1;index<5;index++){
  await page.evaluate(i=>window.changeStage(i),index);
  await expect(page.locator('.cf-active-room')).toHaveCount(1);
  await page.waitForTimeout(150);
  assert.deepEqual(await geometry(),before,`Stage ${index} changed node size or user zoom at ${width}`);
 }
 await page.evaluate(()=>window.changeStage(4,true));
 await expect(page.locator('.cf-active-room')).toHaveCount(0);
 assert.deepEqual(await geometry(),before,'Pause changed viewport');
 const report=page.getByTestId('report-page');
 await expect(report.getByRole('heading',{level:2})).toContainText('Pipeline 1 · Question for pipeline 1');
 await expect(report.locator('[data-report-content]')).toContainText('Saved Explanation 1');
 await expect(report.locator('[data-report-content]')).toContainText('Saved Explanation 3');
 await expect(report.locator('[data-report-content]')).not.toContainText('Saved Explanation 2');
 await report.getByLabel('Pipeline report',{exact:true}).selectOption('audit-run:2');
 await expect(report.getByRole('heading',{level:2})).toContainText('Pipeline 2 · Question for pipeline 2');
 await expect(report.locator('[data-report-content]')).toContainText('Saved Explanation 2');
 await expect(report.locator('[data-report-content]')).toContainText('Saved Explanation 4');
 const downloadButton=report.getByRole('button',{name:'Download Markdown'});
 await downloadButton.scrollIntoViewIfNeeded();
 const download=page.waitForEvent('download',{timeout:10000}).catch(()=>null);await downloadButton.click();
 const file=await download;
 if(!file){await page.screenshot({path:'/tmp/meeting-download-failure.png'});console.log(await downloadButton.evaluate(e=>({disabled:e.disabled,rect:JSON.stringify(e.getBoundingClientRect()),html:e.outerHTML})));}
 assert(file,'Download did not start');assert(file.suggestedFilename().includes('pipeline-2'));
 await page.screenshot({path:`/tmp/meeting-ui-${width}.png`});assert.deepEqual(errors,[]);console.log(JSON.stringify({width,stageTransitions:'stable',pause:'stable',pipelineReports:'isolated',download:true}));await page.close();
}}finally{await browser.close();}
