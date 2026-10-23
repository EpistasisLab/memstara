import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try{for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:950}});
 const items=[{id:'a',number:1,name:'My experiment',configuration:{waves:10},running:null,latest:{run_tag:'a',configuration:{waves:10}},progress:{iteration:2}},{id:'b',number:2,name:'Waiting for hypothesis',configuration:{waves:10},running:null,latest:null,progress:{}}];
 const hypothesis='Blood pressure and exercise predict the recorded outcome. '.repeat(5);
 await page.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:items}:{}}));
 await page.route('**/api/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/api/discovery/live'?{events:[],questions:[],results:[{result_id:1,trial:1,run_tag:'a',hypothesis},{result_id:2,trial:1,run_tag:'unrelated',hypothesis:'Unrelated finding'}],reports:{},generated_at:new Date().toISOString(),record_limit:200}:{}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 const show=page.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 const first=page.getByRole('button',{name:'Inspect My experiment',exact:true});
 await expect(first.locator('.pipeline-card-name')).toContainText('Blood pressure and exercise',{timeout:25000});
 await expect(first).toContainText('Saved as: My experiment');
 await expect(first).not.toContainText('Unrelated finding');
 await expect(page.getByRole('button',{name:'Inspect Waiting for hypothesis',exact:true}).locator('.pipeline-card-name')).toHaveText('Waiting for hypothesis');
 await expect(first.locator('.pipeline-card-position')).toContainText('Replicate');
 await expect.poll(()=>first.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
 await page.close();
}}finally{await browser.close();}
