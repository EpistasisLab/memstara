import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
// All requests are mocked; no real pipeline or paid model run.
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 for(const width of [1440,390]) for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(20000);
  await page.addInitScript(()=>localStorage.setItem('memstara-draft-v1',JSON.stringify({stage_models:{non_explanation_agents:{provider:'openai',model:'qwen-old'},explanation_agent:{provider:'azure_foundry',model:'sonnet-old'}}})));
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
    posted=route.request().postDataJSON();assert.equal(posted.action,'add');for(const key of ['provider','model','stage_models'])assert.equal(Object.hasOwn(posted.configuration,key),false);
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
  await page.getByRole('navigation').getByRole('button',{name:'Floor plan',exact:true}).first().click();await page.getByRole('button',{name:/Add pipeline/i}).click();await page.getByRole('button',{name:/All Combinations/}).click();
  const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});await dialog.getByLabel('Deployment target column',{exact:true}).fill('fixture_target');await dialog.getByRole('button',{name:'Choose skills'}).click();
  const labels=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
  for(const [i,role] of roles.entries()){
   await dialog.getByRole('heading',{name:labels[i]+' skills',exact:true}).waitFor();
   const forward=dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+labels[i+1],exact:true});
   assert(await forward.isDisabled(),'Empty role must not advance');
   const choices=skills.filter(s=>s.stage===role);
   await dialog.locator('.comb-skill-picker > summary').click();
   for(const skill of choices)await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).check();
   assert(!(await forward.isDisabled()),'Selected role must advance');
   for(const skill of choices)await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).uncheck();
   assert(await forward.isDisabled(),'Removing all choices must disable Next');
   for(const skill of choices)await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).check();
   if(i<4){
    await forward.click();await dialog.getByRole('heading',{name:labels[i+1]+' skills',exact:true}).waitFor();
    await dialog.getByRole('button',{name:'Back',exact:true}).click();
    await dialog.locator('.comb-skill-picker > summary').click();
    for(const skill of choices)assert(await dialog.getByRole('checkbox',{name:new RegExp(skill.title)}).isChecked());
    await forward.click();
   }
  }
  await dialog.getByRole('button',{name:'Review plan'}).click();await dialog.getByLabel('Name',{exact:true}).fill('Random capped exploration');
  const maximum=dialog.getByLabel('Maximum Loops per execution',{exact:true});assert.equal(await maximum.inputValue(),'10');
  const consent=dialog.getByRole('checkbox',{name:/I reviewed/}),create=dialog.getByRole('button',{name:'Create combination design'});
  for(const invalid of ['0','10001','1.5','']){await maximum.fill(invalid);await consent.check();assert(await create.isDisabled());}
  await maximum.fill('10');await consent.check();await dialog.getByRole('checkbox',{name:/Random Start/}).check();assert(await create.isDisabled());
  await consent.check();assert(!(await create.isDisabled()));assert.match(await dialog.innerText(),/only part of the combination set/);
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+2));await dialog.screenshot({path:`/tmp/random-start-${width}-${theme}.png`});
  await create.click();await dialog.waitFor({state:'hidden'});await page.getByRole('navigation').getByRole('button',{name:'Floor plan',exact:true}).first().click();
  assert.equal(posted.configuration.combination_random_start,true);assert.equal(posted.configuration.combination_max_loops,10);assert.equal(posted.configuration.waves,10);assert.equal(posted.configuration.continuous,false);assert.equal(runPosts,0);
  rows[0].latest={run_tag:'frozen',exit_code:0,configuration:{waves:10}};await page.reload();await page.getByRole('navigation').getByRole('button',{name:'Floor plan',exact:true}).first().click();
  const studio=page.getByRole('region',{name:'Combination design',exact:true});await studio.waitFor();
  await page.getByText('Loop 1 / 10 · Latest execution',{exact:true}).waitFor();
  await studio.getByRole('button',{name:'Preview interpreter flavor 1',exact:true}).waitFor();
  assert.equal(await studio.getByRole('button',{name:'Preview interpreter flavor 1',exact:true}).getAttribute('aria-pressed'),'true');
  rows[0].progress={iteration:2};await page.getByText('Loop 2 / 10 · Latest execution',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('button[aria-label="Preview interpreter flavor 2"]')?.getAttribute('aria-pressed')==='true');
  assert.equal(await page.getByRole('button',{name:'Loop explorer',exact:true}).count(),0);
  assert.equal(await studio.getByRole('spinbutton',{name:'Combination Loop',exact:true}).count(),0);assert.deepEqual(errors,[]);assert.equal(runPosts,0);
  console.log(JSON.stringify({width,theme,limits:'pass',savedRandomStart:'pass',frozenCurrentLoop:'pass',noRunOnCreate:'pass'}));await page.close();
 }
} finally {await browser.close();}
