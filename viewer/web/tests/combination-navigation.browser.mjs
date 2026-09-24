import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
// All requests are mocked; no real pipeline or paid model run.
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(20000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const roles=['hypothesis','data','ml','interpreter','report'],counts=[2,3,2,2,1];
  const skills=roles.flatMap((stage,i)=>Array.from({length:counts[i]},(_,n)=>({id:`${stage}_${n}`,stage,title:`${stage} flavor ${n+1}`,hash:`${stage}-${n}`,content:'# Fixture',description:'Test instructions',source:'fixture'})));
  let rows=[],posted,runPosts=0;
  await page.route('**/control/**',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;
   if(path==='/control/playbooks')return route.fulfill({json:{catalog:skills,playbooks:skills.map(s=>s.id),stages:roles,references:[],max_hypotheses:4}});
   if(path==='/control/skills')return route.fulfill({json:{skills:[]}});
   if(path==='/control/pipelines') {
    if(route.request().method()==='GET')return route.fulfill({json:{pipelines:rows}});
    posted=route.request().postDataJSON();assert.equal(posted.action,'add');
    const item={id:'fixture-design',number:1,name:posted.name,configuration:posted.configuration};rows=[{...item,running:null,latest:null,progress:{}}];return route.fulfill({json:item});
   }
   if(path.endsWith('/combinations')) {
    const loop=Number(url.searchParams.get('loop')),combination=(22+loop-1)%24+1;let rest=combination-1;const agents=[];
    for(let i=4;i>=0;i--){agents.unshift({...skills.filter(s=>s.stage===roles[i])[rest%counts[i]]});rest=Math.floor(rest/counts[i]);}
    return route.fulfill({json:{run_tag:'frozen',total_loops:10,planned:{combination,repetition:1,start_combination:23,selection_policy:'random_start_then_cycle_v1',agents},calls:[]}});
   }
   if(path==='/control/runs'&&route.request().method()==='POST')runPosts++;
   return route.fulfill({json:{}});
  });
  await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Fixture'}}));
  await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  await page.getByRole('button',{name:/Add Pipeline/}).click();await page.getByRole('button',{name:/All Combinations/}).click();
  const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});await dialog.getByRole('button',{name:'Choose skills'}).click();
  const labels=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
  for(const [i,role] of roles.entries()){
   await dialog.getByRole('heading',{name:labels[i]+' skills',exact:true}).waitFor();
   const forward=dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+labels[i+1],exact:true});
   assert(await forward.isDisabled(),'Empty role must not advance');
   const choices=skills.filter(s=>s.stage===role);
   for(const skill of choices)await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).check();
   assert(!(await forward.isDisabled()),'Selected role must advance');
   for(const skill of choices)await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).uncheck();
   assert(await forward.isDisabled(),'Removing all choices must disable Next');
   for(const skill of choices)await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).check();
   if(i<4){
    await forward.click();await dialog.getByRole('heading',{name:labels[i+1]+' skills',exact:true}).waitFor();
    await dialog.getByRole('button',{name:'Back',exact:true}).click();
    for(const skill of choices)assert(await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).isChecked());
    await forward.click();
   }
  }
  await dialog.getByRole('button',{name:'Review plan'}).click();
  await dialog.getByRole('heading',{name:'Review before creating'}).waitFor();
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  assert.deepEqual(errors,[]);assert.equal(runPosts,0);
  console.log(JSON.stringify({width,theme,stepNavigation:'pass',selectionRetained:'pass',noRun:'pass'}));await page.close();
 }
} finally {await browser.close();}
