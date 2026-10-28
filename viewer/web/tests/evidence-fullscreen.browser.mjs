// Evidence now fills the primary workspace; legacy floating/fullscreen launchers are absent.
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try{for(const width of [1440,390,320]){
 const page=await browser.newPage({viewport:{width,height:800}});
 await page.route('**/control/**',r=>r.fulfill({json:{pipelines:[]}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'No records'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 const nav=page.getByRole('complementary',{name:'View navigation'});
 for(const name of ['Results','Conclusions']){
  await nav.getByRole('button',{name,exact:true}).click();
  await expect(page.locator('#workspace-pipeline>.window-titlebar')).toContainText(name);
  await expect(page.locator('#workspace-results, #workspace-report, .is-evidence-fullscreen, .workspace-minimized-panels')).toHaveCount(0);
  await expect(page.getByRole('button',{name:/Open (Results|Conclusions) full screen/})).toHaveCount(0);
  const content=name==='Results'?page.getByTestId('execution-outputs'):page.getByTestId('execution-outputs');
  await expect(content).toBeVisible();
  const box=await content.boundingBox(),workspace=await page.locator('#workspace-pipeline').boundingBox();
  expect(box.width).toBeGreaterThan(workspace.width*.9);
  await nav.getByRole('button',{name:'Experiments',exact:true}).click();
  await expect(content).toHaveCount(0);
 }
 console.log(JSON.stringify({width,primaryEvidenceViews:true,noDuplicateFloatingPanels:true}));await page.close();
}}finally{await browser.close();}
