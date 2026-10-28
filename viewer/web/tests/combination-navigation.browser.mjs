import {preparedInputs,fixtureSkillId} from './current-research.fixture.mjs';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
// All requests are mocked; no real pipeline or paid model run.
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(20000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const roles=['hypothesis','data','ml','interpreter','report'],counts=[2,3,2,2,1];
  const skills=roles.flatMap((stage,i)=>Array.from({length:counts[i]},(_,n)=>({id:fixtureSkillId(stage,n),stage,title:`${stage} flavor ${n+1}`,hash:`${stage}-${n}`,content:'# Fixture',description:'Test instructions',source:'fixture'})));
  let rows=[],posted,runPosts=0;
  await page.route('**/control/**',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;
   if(path==='/control/research-inputs')return route.fulfill({json:preparedInputs});
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
  await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();await page.getByRole('button',{name:/Add experiment/i}).click();
  const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});await dialog.getByRole('button',{name:'Use CI dataset',exact:true}).click();await dialog.getByRole('button',{name:'Choose skills'}).click();
  const labels=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
  for(const [i,role] of roles.entries()){
   await dialog.getByRole('heading',{name:i===1?'Data settings':labels[i]+' skills',exact:true}).waitFor();
   const forward=dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+labels[i+1],exact:true});
   assert(!(await forward.isDisabled()),'Default role must advance');
   assert.equal(await dialog.locator('.comb-skill-card input:checked').count(),1,'Exactly one default skill');
   const choices=skills.filter(s=>s.stage===role);
   await dialog.locator('.comb-skill-card input').first().waitFor({state:'visible'});
   assert(await dialog.locator('.comb-skill-picker').evaluate(e=>e.open),'Every agent skill picker opens by default');
   // Hypothesis selection must not open automatic hover or focus help.
   if(i===0){
    const targets=[dialog.getByRole('heading',{name:'Choose Hypothesis skills',exact:true}),
     dialog.locator('.comb-skill-picker > summary'),
     dialog.getByRole('checkbox',{name:new RegExp(choices[0].title)})];
    for(const target of targets){
     await target.hover();await page.waitForTimeout(550);
     assert.equal(await page.locator('[role="tooltip"]').count(),0);
    }
    await targets[2].focus();await page.waitForTimeout(350);
    assert.equal(await page.locator('[role="tooltip"]').count(),0);
    await dialog.locator('.comb-skill-card details > summary').first().click();
    assert(await dialog.locator('.comb-skill-card pre').first().isVisible());
   }
   for(const box of await dialog.locator('.comb-skill-card input').all())await box.check();
   assert(!(await forward.isDisabled()),'Selected role must advance');
   for(const box of await dialog.locator('.comb-skill-card input').all())await box.uncheck();
   assert.equal(await forward.isDisabled(),false,'Empty skill selections use defaults; an empty Data selection enables a valid manual split');
   if(role==='data')await dialog.getByRole('radio',{name:'Use data skills',exact:true}).check();
   for(const box of await dialog.locator('.comb-skill-card input').all())await box.check();
   if(i<4){
    await forward.click();await dialog.getByRole('heading',{name:i===0?'Data settings':labels[i+1]+' skills',exact:true}).waitFor();
    await dialog.getByRole('button',{name:'Back',exact:true}).click();
    await dialog.locator('.comb-skill-card input').first().waitFor({state:'visible'});
    for(const box of await dialog.locator('.comb-skill-card input').all())assert(await box.isChecked());
    await forward.click();
   }
  }
  await dialog.getByRole('button',{name:'Review plan'}).click();
  await dialog.getByRole('heading',{name:'Review your design'}).waitFor();
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  assert.deepEqual(errors,[]);assert.equal(runPosts,0);
  console.log(JSON.stringify({width,theme,stepNavigation:'pass',selectionRetained:'pass',noRun:'pass'}));await page.close();
 }
} finally {await browser.close();}
