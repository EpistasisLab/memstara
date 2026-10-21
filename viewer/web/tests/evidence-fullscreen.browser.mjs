import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try{for(const width of [1440,390,320]){
 const page=await browser.newPage({viewport:{width,height:800}});
 await page.route('**/control/**',r=>r.fulfill({json:{pipelines:[]}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'No records'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('[aria-label="View navigation"]').getByRole('button',{name:'Floor plan',exact:true}).click();
 for(const id of ['results','report']){
  const dock=page.locator(`#workspace-${id}`);
  const launch=page.getByRole('button',{name:`Open ${id==='results'?'Results':'Final report'} full screen`,exact:true});
  await expect(dock).toHaveCount(0);await launch.click();
  await expect(dock).toHaveClass(/is-evidence-fullscreen/);
  const box=await dock.boundingBox();expect(box.x).toBe(0);expect(box.y).toBe(0);expect(box.width).toBe(width);expect(box.height).toBe(800);
  await page.keyboard.press('Escape');await expect(dock).toHaveCount(0);
  await launch.click();await dock.getByRole('button',{name:/^Restore .* window$/}).click();await expect(dock).toHaveCount(0);
  await launch.click();await dock.getByRole('button',{name:/^Collapse /}).click();await expect(dock).toHaveCount(0);
  await expect(page.locator('.workspace-minimized-panels')).toHaveCount(0);await expect(launch).toBeVisible();
 }
 console.log(JSON.stringify({width,resultsAndReportFullscreen:true,escapeAndRestore:true}));await page.close();
}}finally{await browser.close();}
