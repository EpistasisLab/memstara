import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try {for(const width of [1440,390]){
 const page=await browser.newPage({viewport:{width,height:1000}});
 const run={run_tag:'activity-test',exit_code:0,configuration:{waves:1}};
 const p={id:'p',number:1,name:'Activity study',configuration:{waves:1},latest:run,running:null,progress:{iteration:1,stage:'report'}};
 await page.route('**/control/**',r=>{if(r.request().method()!=='GET')throw Error('Unexpected mutation');return r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:[p]}:{}});});
 await page.route('**/api/**',r=>{const url=new URL(r.request().url());
 if(url.pathname==='/api/telemetry')return r.fulfill({json:{run_tag:run.run_tag,telemetry:{loop:null},feed:[{key:'call',agent:'ml',name:'MLAgent',label:'ML',tool:'train_and_score',server:'ml',store:'board',at:'2026-10-21T12:00:00Z'}]}});
 if(url.pathname==='/api/telemetry/conversation')return r.fulfill({json:{run_tag:run.run_tag,loop:null,messages:[{id:'text',kind:'text',stage:'ml',name:'MLAgent',text:'LONG OUTPUT CONTENT '.repeat(100),at:'2026-10-21T12:01:00Z'},{id:'error',kind:'error',stage:'data',name:'DataAgent',text:'The selected column was not found.',at:'2026-10-21T12:02:00Z'}],limited:false}});
 return r.fulfill({json:{events:[],results:[],questions:[],reports:{}}});});
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('[aria-label="View navigation"]').getByRole('button',{name:'Floor plan',exact:true}).click();
 const expand=page.getByRole('button',{name:'Expand live log',exact:true});if(await expand.isVisible())await expand.click();
 const panel=page.getByRole('complementary',{name:'Clinical activity log'});
 await panel.getByRole('button',{name:'Browse activity',exact:true}).click();
 await expect(panel.locator('.compact-activity-row')).toHaveCount(3);
 await expect(panel.getByText('The selected column was not found.',{exact:true})).toBeVisible();
 await expect(panel.getByText('Call recorded',{exact:true})).toBeVisible();
 await expect(panel.getByText(/LONG OUTPUT CONTENT/)).toHaveCount(0);
 await expect(panel.getByLabel('Search activity')).toHaveCount(0);
 const output=panel.locator('.compact-activity-row').filter({hasText:'Output recorded'});await output.locator('summary').click();
 await expect(output.getByText(/LONG OUTPUT CONTENT/)).toBeVisible();await output.locator('summary').click();
 expect(await panel.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
 await panel.screenshot({path:'/tmp/activity-minimal-'+width+'.png'});
 await panel.getByRole('button',{name:'Back to live updates',exact:true}).click();await expect(panel.getByRole('button',{name:'Browse activity',exact:true})).toBeVisible();
 console.log(JSON.stringify({width,minimalActivity:true,details:true,errorsVisible:true,readOnly:true}));await page.close();
}}finally{await browser.close();}
