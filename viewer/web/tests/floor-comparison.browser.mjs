import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const b=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{
 const p=await b.newPage();p.setDefaultTimeout(15000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
 const items=Array.from({length:30},(_,i)=>({id:'layout-'+i,number:i+1,name:'Research '+(i+1)+' — substance use and clinical outcomes',configuration:{skill:'test',waves:10,hypothesis_agents:1,interpreter_agents:1},running:null,
 latest:i%2?{run_tag:'fixture-'+i,exit_code:0,configuration:{waves:10},infrastructure_status:{status:'interrupted',message:'Recorded connection interruption. Previous results are retained for review.'}}:null,
 progress:{stage:'report',exploration:{outcome:'completed',completed:10,blocked:0}}}));
 await p.route('**/control/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/control/pipelines'?{pipelines:items}:{}}));
 await p.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Layout fixture'}}));
 items[0].configuration.combination_skills={hypothesis:['h'],data:['d'],ml:['m'],interpreter:['i'],report:['r']};
 await p.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 for(const width of [1440,390]){
 await p.setViewportSize({width,height:1000});
 if(width<900)await expect(p.locator('.pipeline-browser-toggle')).toHaveAttribute('aria-expanded','false');
 const show=p.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 await p.getByRole('checkbox',{name:'Compare '+items[0].name,exact:true}).check();
 await p.getByRole('checkbox',{name:'Compare '+items[1].name,exact:true}).check();
 await p.getByText('Comparing 2 pipelines',{exact:true}).waitFor();
 assert.equal(await p.locator('.floor-comparison-pane').count(),2);
 assert.equal(await p.locator('.floor-comparison-pane .combination-studio').count(),1);
 assert.equal(await p.locator('.floor-comparison-pane .cf-room').count(),5);
 assert.equal(await p.locator('.floor-comparison-standard .react-flow__node-station').count(),6);
 const grid=p.locator('.floor-comparison-grid');assert(await grid.isVisible());
 assert(await grid.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
 await p.getByRole('button',{name:'Exit comparison (2 selected)',exact:true}).click();
 await p.getByRole('region',{name:'Combination design',exact:true}).waitFor();
 console.log(JSON.stringify({width,mixedComparison:'passed',bothRowsVisible:'passed',exit:'passed'}));
 }
 assert.deepEqual(errors,[]);
}finally{await b.close();}
