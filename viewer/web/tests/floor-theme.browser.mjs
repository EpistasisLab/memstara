import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try {
 for(const [width,theme] of [[1440,'light'],[1440,'dark'],[390,'light'],[390,'dark']]){
 const page=await browser.newPage({viewport:{width,height:800}});
 const item={id:'compact-settings',number:2,name:'Study with a long descriptive pipeline name',configuration:{waves:10,combination_skills:{ml:['ml_xgboost']}},running:null,latest:null,progress:{}};
 await page.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:[item]}:{}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'fixture'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('[aria-label="View navigation"]').getByRole('button',{name:'Floor plan',exact:true}).click();
 await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
 const show=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 const expand=page.getByRole('button',{name:'Expand live log',exact:true});if(await expand.isVisible())await expand.click();
 await page.waitForTimeout(400);
 const colors=await page.evaluate(()=>{const bg=s=>getComputedStyle(document.querySelector(s)).backgroundColor;return {list:bg(innerWidth<=900?'#pipeline-browser-content':'.pipeline-browser'),log:bg('.clinical-log'),room:bg('.cf-room'),shell:bg('.cf-floor-shell')};});
 expect(colors.list).toBe(colors.log);expect(colors.room).toBe(colors.list);
 await page.screenshot({path:'/tmp/floor-theme-'+theme+'-'+width+'.png'});
 console.log(JSON.stringify({width,theme,sharedSurfaces:colors}));await page.close();
 }
}finally{await browser.close();}
