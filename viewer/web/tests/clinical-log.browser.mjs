import {tmpdir} from 'node:os';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) for(const combination of [false,true]) {
  const page=await browser.newPage({viewport:{width,height:1100}});page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const roles=['hypothesis','data','ml','interpreter','report'];
  const skills=roles.map(stage=>({id:stage,stage,title:stage,hash:stage,content:'Fixture'}));
  let unavailable=false,traceUnavailable=false,added=false,slow=false,inFlight=0,maxInFlight=0;
  const requestTimes=[];
  const run={run_tag:'test-run',execution_state:'running',configuration:{waves:3}};
  const pipeline={id:'p1',number:1,name:'Research pipeline',configuration:{waves:3,combination_skills:combination?Object.fromEntries(roles.map(s=>[s,[s]])):{}},running:run,latest:run,progress:{stage:'ml',iteration:2,updated_at:new Date().toISOString()}};
  const event=i=>({id:`event-${i}`,revision:'1',run_tag:'test-run',pipeline_name:pipeline.name,stage:'hypothesis',title:'Saved hypothesis',detail:'Recorded detail '.repeat(50),at:null,iteration:2,status:'recorded'});
  await page.route('**/control/**',r=>{
   assert.equal(r.request().method(),'GET','Read-only log must not mutate execution');
   const path=new URL(r.request().url()).pathname;
   if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[pipeline]}});
   if(path==='/control/playbooks')return r.fulfill({json:{catalog:skills,stages:roles,playbooks:roles,references:[],max_hypotheses:4}});
   if(path.endsWith('/combinations')&&traceUnavailable)return r.fulfill({status:503,json:{error:'Fixture call records unavailable'}});
   if(path.endsWith('/combinations'))return r.fulfill({json:{total_loops:3,planned:{combination:1,agents:skills},calls:[{stage:'ml#1',status:'started',skill:skills[2]}]}});
   return r.fulfill({json:{}});
  });
  await page.route('**/api/**',async r=>{
   const url=new URL(r.request().url());
   if(url.pathname==='/api/telemetry') {
    assert.equal(url.searchParams.get('run_tag'),'test-run');assert(['2',null].includes(url.searchParams.get('loop')));
    return r.fulfill({json:{run_tag:'test-run',telemetry:{loop:url.searchParams.has('loop')?2:null},feed:[{key:'tool1',name:'HypothesisAgent',label:'Hypothesis',agent:'hypothesis',tool:'create_task',server:'board',store:'board',at:new Date().toISOString()}]}});
   }
   if(url.pathname==='/api/telemetry/conversation')return r.fulfill({json:{run_tag:'test-run',loop:url.searchParams.has('loop')?2:null,messages:[{id:'text1',stage:'hypothesis',name:'HypothesisAgent',label:'Hypothesis',text:'MATCHED HYPOTHESIS OUTPUT',at:new Date().toISOString(),loop:2},{id:'text2',stage:'ml',name:'MLAgent',text:'OTHER STAGE OUTPUT',at:new Date().toISOString(),loop:2}],limited:false}});
   if(url.pathname!=='/api/discovery/live')return r.fulfill({status:503,json:{error:'Fixture'}});
   if(unavailable)return r.fulfill({status:503,json:{error:'Fixture interruption'}});
   requestTimes.push(Date.now());inFlight++;maxInFlight=Math.max(maxInFlight,inFlight);
   if(slow)await new Promise(resolve=>setTimeout(resolve,900));
   try {await r.fulfill({json:{events:[...Array.from({length:12},(_,i)=>event(i)),{...event(99),run_tag:'other-run',detail:'UNRELATED OUTPUT'},...(added?[{...event(20),stage:'report'}]:[])],results:[],questions:[],reports:{},record_limit:200,generated_at:new Date().toISOString()}});} finally{inFlight--;}
  });
  await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');
  await page.evaluate(d=>document.documentElement.dataset.theme=d,combination?'dark':'light');
  const panel=page.getByRole('complementary',{name:'Clinical activity log'});
  if(width===390)await panel.getByRole('button',{name:'Expand live log'}).click();
  await panel.getByText(combination?'The task board is at model evaluation.':'Training and evaluating the prediction model.').waitFor();
  await panel.locator('.clinical-log-events li').first().waitFor({state:'attached'});
  if(combination){
   const row=panel.locator('[data-role=ml]');
   assert.equal(await row.locator('.clinical-agent-status').innerText(),'Running');
   assert.equal(await row.locator('.clinical-agent-link').count(),1);
   assert.match(await panel.locator('[data-role=data]').innerText(),/Not started/);
   await page.getByRole('button',{name:'Preview combinations',exact:true}).click();
   await panel.getByText('Configuration preview',{exact:true}).waitFor();
   assert.equal(await panel.locator('[data-role=ml]').count(),0);
   await page.getByRole('button',{name:'Follow execution',exact:true}).click();
   await panel.locator('[data-role=ml]').waitFor();
   await page.getByRole('button',{name:'Loop explorer',exact:true}).click();
   await panel.getByText('Loop 1 · Historical records',{exact:true}).waitFor();
   await panel.locator('[data-role=ml]').getByText('Last recorded: call open',{exact:true}).waitFor();
   assert.equal(await panel.locator('.clinical-log-events li').count(),0);
   await page.getByRole('navigation',{name:'Combination views'}).getByRole('button',{name:'Floor plan',exact:true}).click();
   await panel.locator('[data-role=ml]').getByText('Running',{exact:true}).waitFor();
   traceUnavailable=true;
   await panel.locator('[data-role=ml]').getByText('Last recorded: call open',{exact:true}).waitFor();
   assert.equal(await page.getByLabel('Machine learning stage is running').count(),0);
   traceUnavailable=false;
   await panel.locator('[data-role=ml]').getByText('Running',{exact:true}).waitFor();

  }

  pipeline.running={...run,pause_requested:true};
  await panel.getByText('Pausing after the current agent call finishes.',{exact:true}).waitFor();
  if(combination){
   await panel.locator('[data-role=ml]').getByText('Pause requested · finishing call',{exact:true}).waitFor();
   assert.equal(await page.locator('.cf-active-room,.cf-map .react-flow__edge.animated').count(),0);
   await page.locator('.cs-loop-status').getByText(/Pausing/).waitFor();
  }
  pipeline.running={...run,execution_state:'stopping'};
  await panel.getByText('Pausing after the current agent call finishes.',{exact:true}).waitFor();
  pipeline.running={...run,execution_state:'paused',pause_requested:true};
  await panel.getByText('Paused. The pipeline is waiting to resume.',{exact:true}).waitFor();
  await panel.getByText('Paused · saved activity',{exact:true}).waitFor();
  if(combination)assert.equal(await page.locator('.cf-active-room,.cf-map .react-flow__edge.animated').count(),0);
  pipeline.running={...run};
  await panel.getByText(combination?'The task board is at model evaluation.':'Training and evaluating the prediction model.').waitFor();
  assert.equal(await panel.locator('.clinical-log-events li').count(),12);
  await panel.getByText('Live · checks every 0.5 seconds',{exact:true}).waitFor();
  await page.waitForTimeout(1600);
  const gaps=requestTimes.slice(1).map((t,i)=>t-requestTimes[i]);
  assert(gaps.some(gap=>gap>=350&&gap<1200),'Active updates should arrive at subsecond polling cadence');
  assert(!((await panel.innerText()).includes('UNRELATED OUTPUT')));
  const boxes=await page.evaluate(()=>{
   const p=document.querySelector('.clinical-log'),floor=document.querySelector('.pipeline-detail-workspace');
   const a=p.getBoundingClientRect(),b=floor.getBoundingClientRect();
   return {right:a.left>=b.right-1,below:a.top>=b.bottom-1,overflow:p.scrollWidth>p.clientWidth+1};
  });
  assert.equal(boxes.overflow,false);assert(width===1440?boxes.right:boxes.below);
  assert.equal(await page.locator('#workspace-feed').count(),0);
  assert.equal(await panel.locator('.clinical-log-scroll').evaluate(e=>e.scrollTop),0,'Agent view must not auto-scroll to saved outputs');
  if(combination) {
   const geometry=await panel.locator('.clinical-agent-card').evaluateAll(es=>es.map(e=>({overflow:e.scrollWidth>e.clientWidth+1,height:e.clientHeight})));
   assert(geometry.every(g=>!g.overflow&&g.height>60));
  }
  await panel.screenshot({path:`${tmpdir()}/live-log-agents-${width}-${combination}.png`});
  await panel.getByRole('tab',{name:'Agent activity',exact:true}).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await panel.getByRole('tab',{name:/Saved outputs/}).getAttribute('aria-selected'),'true');
  await panel.getByRole('tab',{name:/Saved outputs/}).click();
  await panel.getByRole('button',{name:'View details',exact:true}).first().click();
  await panel.getByText('MATCHED HYPOTHESIS OUTPUT',{exact:true}).first().waitFor();
  assert(!((await panel.innerText()).includes('OTHER STAGE OUTPUT')));
  assert.equal(await panel.locator('.clinical-log-detail-view').evaluate(e=>e.scrollWidth>e.clientWidth+1),false);
  assert.equal(await panel.getByLabel('Filter activity by agent').count(),0);
  assert.equal(await panel.getByLabel('Filter activity by type').count(),0);
  assert.equal(await panel.getByLabel('Search activity').count(),0);
  assert.equal(await panel.locator('[data-activity-kind=text]').count(),1);
  assert.equal(await panel.getByText('No matching activity.',{exact:false}).count(),0);
  await panel.getByRole('button',{name:'Back to live updates'}).click();
  await panel.getByRole('tab',{name:'Agent activity',exact:true}).click();
  await panel.getByRole('button',{name:'Browse activity'}).click();
  await panel.getByText('OTHER STAGE OUTPUT',{exact:true}).first().waitFor();
  await panel.getByRole('button',{name:'Back to live updates'}).click();
  await panel.getByRole('tab',{name:/Saved outputs/}).click();
  const scroll=panel.locator('.clinical-log-scroll');await scroll.evaluate(e=>{e.scrollTop=0;e.dispatchEvent(new Event('scroll'));});
  await panel.getByRole('button',{name:'Follow latest updates'}).waitFor();
  added=true;await panel.getByText('The explanation record was updated.').waitFor();
  assert.equal(await scroll.evaluate(e=>e.scrollTop),0);
  await panel.getByRole('button',{name:'Follow latest updates'}).click();
  await page.waitForTimeout(100);assert(await scroll.evaluate(e=>e.scrollTop>0));
  slow=true;await page.waitForTimeout(2200);assert.equal(maxInFlight,1,'Slow reads must not overlap');
  unavailable=true;await panel.getByText('Updates interrupted',{exact:true}).waitFor();
  assert.equal(await panel.locator('.clinical-log-events li').count(),13);
  await panel.getByRole('button',{name:'Collapse live log'}).click();
  await panel.getByRole('button',{name:'Expand live log'}).click();
  assert.equal(await panel.locator('.clinical-log-events li').count(),13);
  await page.screenshot({path:`/tmp/clinical-log-${width}-${combination?'combinations':'selected'}.png`});
  pipeline.running=null;pipeline.latest={...run,exit_code:1};
  pipeline.failure={code:'model_message_format',message:'The model rejected the system-message format.'};
  await panel.getByText(pipeline.failure.message,{exact:true}).waitFor();
  pipeline.running={...run,run_tag:'new-run'};pipeline.latest=pipeline.running;pipeline.failure=null;
  await panel.getByText(combination?'The task board is at model evaluation.':'Training and evaluating the prediction model.').waitFor();
  assert.equal(await panel.getByText('The model rejected the system-message format.',{exact:true}).count(),0);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({width,combination,layout:'pass',scope:'pass',live:'pass',scroll:'pass',outage:'pass'}));await page.close();
 }
}finally{await browser.close();}
