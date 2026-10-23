import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const b=await chromium.launch();
try{
 const p=await b.newPage({viewport:{width:1440,height:1000}});let stage='data',iteration=1,paused=false,delay=0,connection='healthy',historyError=false;
 const roles=['hypothesis','data','ml','interpreter','report'],counts=[2,3,2,2,1];
 const catalog=roles.flatMap((s,i)=>Array.from({length:counts[i]},(_,j)=>({stage:s,id:s+j,title:s+' skill '+j,hash:s+j})));
 const choices=Object.fromEntries(roles.map(s=>[s,catalog.filter(c=>c.stage===s).map(c=>c.id)]));
 const pipeline={id:'fixture',number:1,name:'Transition diagnosis',configuration:{combination_skills:choices,waves:48},running:{run_tag:'fixture-run',execution_state:'running'},latest:{run_tag:'fixture-run'},progress:{iteration:1,stage}};
 await p.route('**/api/**',r=>r.fulfill({json:{events:[],results:[],questions:[],reports:{}}}));
 await p.route('**/control/**',async r=>{
  if(r.request().method()!=='GET')return r.fulfill({status:409,json:{error:'Fixture action rejected'}});const path=new URL(r.request().url()).pathname;
  if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[{...pipeline,running:{...pipeline.running,execution_state:paused?'paused':'running',connection_health:{state:connection}},progress:{iteration,stage}}]}});
  if(path==='/control/playbooks')return r.fulfill({json:{catalog,stages:roles}});
  if(path.endsWith('/combinations')){if(historyError)return r.fulfill({status:503,json:{error:'Fixture history unavailable'}});if(delay)await new Promise(r=>setTimeout(r,delay));return r.fulfill({json:{run_tag:'fixture-run',total_loops:48,planned:{combination:1,repetition:1,agents:roles.map(s=>catalog.find(c=>c.stage===s))},calls:roles.slice(0,roles.indexOf(stage)+1).map(s=>({run_id:s,stage:s,skill:catalog.find(c=>c.stage===s),status:s===stage?'started':'completed'}))}});}
  return r.fulfill({json:{}});
 });
 await p.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
 await p.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 await expect(p.locator('.cf-active-room')).toContainText('Data');
 await p.getByRole('combobox',{name:'Focus floor plan agent'}).selectOption('data');
 await p.waitForTimeout(1000);
 const read=()=>p.locator('.cf-map').evaluate(e=>({transform:e.querySelector('.react-flow__viewport').style.transform,heights:[...e.querySelectorAll('.react-flow__node-room')].map(n=>({id:n.dataset.id,height:n.offsetHeight})),focus:e.querySelector('select').value}));
 const before=await read();
 const show=p.getByRole('button',{name:'Show pipeline list',exact:true});if(await show.isVisible())await show.click();
 await p.getByRole('button',{name:'Pause Transition diagnosis',exact:true}).click();await p.waitForTimeout(800);await expect(p.locator('.cf-active-room')).toContainText('Data');
await p.locator('.cf-map .react-flow__controls-zoomin').click();await p.waitForTimeout(500);const userZoom=await read();
 stage='ml';await expect(p.locator('.cf-active-room')).toContainText('Machine learning',{timeout:15000});await p.waitForTimeout(1000);const after=await read();assert.equal(after.transform,userZoom.transform,'agent transition preserves manual viewport');
 
 await p.locator('.cf-map .react-flow__controls-zoomin').click();await p.waitForTimeout(400);const prePause=await read();paused=true;
 await expect(p.locator('.cf-active-room')).toHaveCount(0,{timeout:15000});await p.waitForTimeout(500);const postPause=await read();assert.equal(postPause.transform,prePause.transform,'pause preserves viewport');
 await p.locator('.cf-map .react-flow__controls-zoomout').click();await p.waitForTimeout(400);const preResize=await read();await p.setViewportSize({width:1200,height:900});await p.waitForTimeout(1000);const postResize=await read();assert.equal(postResize.transform,preResize.transform,'resize preserves viewport');
 paused=false;delay=2000;iteration=2;
 await expect(p.getByText('Loading current Replicate…',{exact:true})).toBeVisible({timeout:15000});const unmounted=await p.locator('.cf-map').count();assert.equal(unmounted,1,'graph stays mounted during next-replicate loading');await expect(p.locator('.cf-active-room')).toHaveCount(0);
 await expect(p.locator('.cf-active-room')).toContainText('Machine learning',{timeout:15000});await p.waitForTimeout(500);const nextReplicate=await read();
 
 assert.equal(nextReplicate.focus,'data');assert.equal(nextReplicate.transform,postResize.transform);
 delay=0;connection='lost';await expect(p.locator('.cf-active-room')).toHaveCount(0,{timeout:15000});
 connection='healthy';await expect(p.locator('.cf-active-room')).toContainText('Machine learning',{timeout:15000});
 historyError=true;await expect(p.locator('.cs-error')).toContainText('Fixture history unavailable',{timeout:15000});await expect(p.locator('.cf-active-room')).toHaveCount(0);assert.equal((await read()).transform,nextReplicate.transform);
 historyError=false;await expect(p.locator('.cf-active-room')).toContainText('Machine learning',{timeout:15000});assert.equal((await read()).transform,nextReplicate.transform);
 await p.getByRole('button',{name:'Fit all',exact:true}).click();await expect.poll(async()=>(await read()).focus).toBe('all');assert.notEqual((await read()).transform,nextReplicate.transform);
 console.log('Transitions, pause, resize, replicate loading, connection loss, action error isolation, history recovery and explicit fit passed');


}finally{await b.close();}
