import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try {
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const items=[1,2].map(i=>({id:'card-'+i,number:i,name:'Study '+i,configuration:{waves:1},running:null,latest:null,progress:{}}));
 items[0].configuration.combination_skills={hypothesis:['a','b'],data:['c','d']};
 items[0].configuration.combination_repetitions=10;
 const starts=[];
 await page.route('**/control/**',route=>{const path=new URL(route.request().url()).pathname;
 if(path==='/control/runs'&&route.request().method()==='POST'){starts.push(route.request().postDataJSON().pipeline_id);return route.fulfill({json:{run_tag:'fixture'}});}
 return route.fulfill({json:path==='/control/pipelines'?{pipelines:items}:{}});
 });
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'fixture'}}));
 await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await page.locator('[aria-label="View navigation"]').getByRole('button',{name:'Experiments',exact:true}).click();
 await page.getByRole('button',{name:'Inspect Study 1',exact:true}).click();
 await expect(page.getByRole('button',{name:'Inspect Study 1',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('button',{name:/^(Settings and more for|Execution details for)/})).toHaveCount(0);
 const counters=page.locator('.pipeline-browser-row').first().locator('.pipeline-card-counter');
 await expect(counters).toHaveCount(2);
 const boxes=await counters.evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return {top:r.top,left:r.left,right:r.right,overflow:e.scrollWidth>e.clientWidth+1}}));
 if(boxes[0].top!==boxes[1].top||boxes[0].right>boxes[1].left||boxes.some(b=>b.overflow))throw Error('Counters must occupy aligned, non-overlapping columns: '+JSON.stringify(boxes));
 const second=page.getByRole('group' ,{name:'Actions for Study 2',exact:true});
 await second.getByRole('button',{name:'Run Study 2',exact:true}).click();
 await expect.poll(()=>starts).toEqual(['card-2']);
 await expect(page.getByRole('button',{name:'Inspect Study 2',exact:true})).toHaveAttribute('aria-pressed','true');
 console.log('PASS: unselected card starts its own pipeline, not selected pipeline; all requests mocked.');
}finally{await browser.close();}
