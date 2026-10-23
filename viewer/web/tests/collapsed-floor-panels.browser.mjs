import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try {
 for(const width of [1440,768,390,320]){
 const page=await browser.newPage({viewport:{width,height:800}});
 const item={id:'compact-settings',number:2,name:'Study with a long descriptive pipeline name',configuration:{waves:10,combination_skills:{ml:['ml_xgboost']}},running:null,latest:null,progress:{}};
 await page.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:[item]}:{}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'fixture'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('[aria-label="View navigation"]').getByRole('button',{name:'Experiments',exact:true}).click();
 const show=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 const hide=page.getByRole('button',{name:'Hide pipeline list',exact:true});if(await hide.isVisible())await hide.click();
 const collapse=page.getByRole('button',{name:'Collapse live log',exact:true});if(await collapse.isVisible())await collapse.click();
 for(const selector of ['.pipeline-browser.is-closed','.clinical-log.is-collapsed'])await expect(page.locator(selector)).toBeHidden();
 const toggles=page.getByRole('group',{name:'Workspace panels',exact:true});
 await expect(toggles.getByRole('button',{name:'Show pipeline list',exact:true})).toBeVisible();
 await expect(toggles.getByRole('button',{name:'Expand live log',exact:true})).toBeVisible();
 expect(await toggles.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
 await page.screenshot({path:'/tmp/collapsed-panels-'+width+'.png'});
 await page.getByRole('button',{name:'Show pipeline list',exact:true}).click();await expect(page.getByRole('button',{name:'Hide pipeline list',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Expand live log',exact:true}).click();await expect(page.getByRole('button',{name:'Collapse live log',exact:true})).toBeVisible();
 console.log(JSON.stringify({width,compactCollapsedPanels:true,reopen:true}));await page.close();
 }
}finally{await browser.close();}
