import {preparedInputs,fixtureSkillId} from './current-research.fixture.mjs';
import {openBuildModeFixture} from './build-mode.fixture.mjs';
// Browser regression: all writes are mocked; no pipeline or paid LLM call is started.
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const roles=['hypothesis','data','ml','interpreter','report'],counts=[3,2,2,2,2];
 const skills=roles.flatMap((stage,i)=>Array.from({length:counts[i]},(_,j)=>({id:fixtureSkillId(stage,j),stage,title:`${stage} flavor ${j+1}`,hash:`hash-${stage}-${j}`,content:'# Test instructions',description:'Test only',source:'Test fixture'})));
 let rows=[],posted=null,runPosts=0;
 await page.route('**/control/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/research-inputs')return r.fulfill({json:preparedInputs});
  if(path==='/control/playbooks'&&r.request().method()==='GET')return r.fulfill({json:{catalog:skills,playbooks:skills.map(s=>s.id),stages:roles,references:[],max_hypotheses:4}});
  if(path==='/control/pipelines'){
   if(r.request().method()==='GET')return r.fulfill({json:{pipelines:rows}});
   posted=r.request().postDataJSON();
   const config={...posted.configuration};for(const role of roles)config[`playbook_${role}`]=config.combination_skills[role][0];
   const item={id:'combination-ui-test',number:1,name:posted.name,configuration:config};rows=[{...item,running:null,latest:null,progress:{}}];return r.fulfill({json:item});
  }
  if(path.endsWith('/combinations')) {const n=Number(new URL(r.request().url()).searchParams.get('loop')); return r.fulfill({json:{total_loops:48,run_tag:'frozen-execution',planned:{combination:(n-1)%24+1,repetition:Math.floor((n-1)/24)+1,agents:roles.map(stage=>skills.find(s=>s.stage===stage))},calls:[{run_id:'record-'+n,stage:'hypothesis'+n,status:'completed',skill:{stage:'hypothesis',id:'actual-'+n,title:'Actual skill '+n,hash:'abc123'}}]}});}
  if(r.request().method()==='POST'){if(path==='/control/runs')runPosts++;return r.abort();}
  return r.continue();
 });
 await page.goto(process.env.MEMSTARA_TEST_URL || 'http://localhost:8070');
 await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();await page.getByRole('button',{name:/Add experiment/i}).click();
 await openBuildModeFixture(page);
 await page.getByRole('combobox',{name:'Knowledge sources'}).waitFor();
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:/Add experiment/i}).click();

 const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});
 const budget=dialog.getByRole('status',{name:'Pipeline replicate summary'});await expect(budget).toHaveCount(0);
 await dialog.getByRole('button',{name:'Use CI dataset',exact:true}).click();await dialog.getByRole('button',{name:'Choose skills'}).click();
 for(const role of roles){ await dialog.getByRole('navigation',{name:'Agent roles'}).getByRole('button').nth(roles.indexOf(role)).click(); await dialog.locator('.comb-skill-card input').first().waitFor({state:'visible'}); for(const box of await dialog.locator('.comb-skill-card input').all())await box.check(); }
 await expect(budget).toHaveCount(0);await expect(dialog.locator('.comb-selected-skills')).toHaveCount(0);
 await dialog.locator('.floor-detail-dialog-body').evaluate(e=>e.scrollTop=0); await page.screenshot({path:'/tmp/combinations-light.png'});
 await page.evaluate(()=>document.documentElement.dataset.theme='dark');
 await page.waitForTimeout(400); await page.screenshot({path:'/tmp/combinations-dark.png'});
 await dialog.getByRole('button',{name:'Review plan'}).click();
 await dialog.getByRole('heading',{name:'Review your design',exact:true}).waitFor();
 await expect(dialog.getByText('One selected model',{exact:true})).toHaveCount(0);
 await dialog.getByLabel('Replicates per pipeline').fill('10');
 await expect(budget).toBeVisible();await expect(budget).toContainText('48total pipelines×10replicates per pipeline=480total runs');
 await dialog.getByLabel('Name',{exact:true}).fill('Combination test');
 await dialog.getByRole('checkbox',{name:/I reviewed/}).check();
 await dialog.getByText('How execution works',{exact:true}).click();await dialog.getByText(/The schedule contains 480 total runs/).waitFor();
 await page.setViewportSize({width:390,height:844});
 if(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth+2))throw Error('Wizard overflow');
 await dialog.getByRole('button',{name:'Create combination design'}).click();
 await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
 const grid=page.getByRole('region',{name:'Combination design'});
 const hide=page.getByRole('button',{name:'Hide pipeline list',exact:true});if(await hide.isVisible())await hide.click();await grid.waitFor();
 await grid.locator('.cf-room').first().waitFor();if(await grid.locator('.cf-room').count()!==5)throw Error('Missing agent role');if(await grid.locator('.cf-desk').count()!==11)throw Error('Missing skill variants');
 if(runPosts)throw Error('Creating unexpectedly started an execution');
 if(posted.configuration.combination_repetitions!==10||posted.configuration.combination_max_loops!==null||posted.configuration.waves!==480)throw Error('Replicate schedule not saved');
 await page.getByRole('button',{name:'Run combinations'}).waitFor();
 await expect(page.getByRole('status',{name:'Saved pipeline replicate summary'})).toHaveCount(0);
 if(await page.getByRole('button',{name:'Loop explorer',exact:true}).count())throw Error('Removed Loop explorer is visible');
 rows[0].latest={run_tag:'frozen-execution',exit_code:0,configuration:{combination_plan:{combinations:24,total_loops:48}}};rows[0].progress={iteration:48};await page.reload();
 await page.getByText('Pipeline 24 · Replicate 2 · Latest execution',{exact:true}).waitFor();await expect(page.getByRole('status',{name:'Saved pipeline replicate summary'})).toHaveCount(0);await grid.getByText('Actual skill 48',{exact:true}).first().waitFor();
 rows[0].progress={iteration:1};await page.getByText('Pipeline 1 · Replicate 1 · Latest execution',{exact:true}).waitFor();await grid.getByText('Actual skill 1',{exact:true}).first().waitFor();
 if(await grid.getByText('Actual skill 48',{exact:true}).count())throw Error('Stale Loop content');
 console.log('Current-loop frozen skills verified; Selected workflow opens; 48 pipelines/10 replicates per pipeline/480 total runs; legacy archived 24-pipeline schedule/5 roles; narrow layout valid; create does not run; all writes mocked.');
}finally{await browser.close();}
