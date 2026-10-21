import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try {
 for(const width of [1440,768,390,320]){
 const page=await browser.newPage({viewport:{width,height:800}});
 const item={id:'compact-settings',number:2,name:'Study with a long descriptive pipeline name',configuration:{waves:10,combination_skills:{ml:['ml_xgboost']}},running:null,latest:null,progress:{}};
 await page.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:[item]}:{}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'fixture'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('[aria-label="View navigation"]').getByRole('button',{name:'Floor plan',exact:true}).click();
 const show=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 await expect(page.getByRole('button',{name:/^(Settings and more for|Execution details for)/})).toHaveCount(0);
 await page.getByRole('button',{name:'Delete '+item.name,exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText('Delete');
 console.log(JSON.stringify({width,minimalSettings:true,deleteConfirmation:true}));await page.close();
 }
}finally{await browser.close();}
