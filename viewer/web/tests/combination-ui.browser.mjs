// Browser regression: all writes are mocked; no pipeline or paid LLM call is started.
import {chromium} from '@playwright/test';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const roles=['hypothesis','data','ml','interpreter','report'],counts=[2,3,2,2,1];
 const skills=roles.flatMap((stage,i)=>Array.from({length:counts[i]},(_,j)=>({id:`${stage}_${j}`,stage,title:`${stage} flavor ${j+1}`,hash:`hash-${stage}-${j}`,content:'# Test instructions',description:'Test only',source:'Test fixture'})));
 let rows=[],posted=null,runPosts=0;
 await page.route('**/control/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/playbooks'&&r.request().method()==='GET')return r.fulfill({json:{catalog:skills,playbooks:skills.map(s=>s.id),stages:roles,references:[],max_hypotheses:4}});
  if(path==='/control/pipelines'){
   if(r.request().method()==='GET')return r.fulfill({json:{pipelines:rows}});
   posted=r.request().postDataJSON();
   const config={...posted.configuration,waves:48};for(const role of roles)config[`playbook_${role}`]=config.combination_skills[role][0];
   const item={id:'combination-ui-test',number:1,name:posted.name,configuration:config};rows=[{...item,running:null,latest:null,progress:{}}];return r.fulfill({json:item});
  }
  if(path.endsWith('/combinations')) {const n=Number(new URL(r.request().url()).searchParams.get('loop')); return r.fulfill({json:{total_loops:48,run_tag:'frozen-execution',planned:{combination:(n-1)%24+1,repetition:Math.floor((n-1)/24)+1,agents:roles.map(stage=>skills.find(s=>s.stage===stage))},calls:[{run_id:'record-'+n,stage:'hypothesis'+n,status:'completed',skill:{stage:'hypothesis',id:'actual-'+n,title:'Actual skill '+n,hash:'abc123'}}]}});}
  if(r.request().method()==='POST'){if(path==='/control/runs')runPosts++;return r.abort();}
  return r.continue();
 });
 await page.goto(process.env.MEMSTARA_TEST_URL || 'http://localhost:8070');
 await page.getByRole('button',{name:/Add pipeline/i}).click();
 await page.getByRole('button',{name:/Selected Pipelines/}).click();
 await page.getByRole('combobox',{name:'Knowledge sources'}).waitFor();
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:/Add pipeline/i}).click();
 await page.getByRole('button',{name:/All Combinations/}).click();
 const dialog=page.getByRole('dialog',{name:'All Combinations',exact:true});
 await dialog.getByRole('button',{name:'Choose skills'}).click();
 for(const role of roles){ await dialog.getByRole('navigation',{name:'Agent roles'}).getByRole('button').nth(roles.indexOf(role)).click(); await dialog.locator('.comb-skill-picker > summary').click(); for(const s of skills.filter(s=>s.stage===role))await dialog.getByRole('checkbox',{name:new RegExp(s.title)}).check(); }
 await dialog.locator('.floor-detail-dialog-body').evaluate(e=>e.scrollTop=0); await page.screenshot({path:'/tmp/combinations-light.png'});
 await page.evaluate(()=>document.documentElement.dataset.theme='dark');
 await page.waitForTimeout(400); await page.screenshot({path:'/tmp/combinations-dark.png'});
 await dialog.getByRole('button',{name:'Review plan'}).click();
 await dialog.getByText(/Guided and random hypothesis skills each use 4–20/).waitFor();
 await dialog.getByLabel('Maximum Loops per execution').fill('48');
 await dialog.getByLabel('Name',{exact:true}).fill('Combination test');
 await dialog.getByRole('checkbox',{name:/I reviewed/}).check();
 await dialog.getByText('Stops after at most 48 Loops.',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});
 if(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth+2))throw Error('Wizard overflow');
 await dialog.getByRole('button',{name:'Create combination design'}).click();
 const grid=page.getByRole('region',{name:'Combination design'});
 const hide=page.getByRole('button',{name:'Hide pipeline list',exact:true});if(await hide.isVisible())await hide.click();await grid.waitFor();
 await grid.locator('.cf-room').first().waitFor();if(await grid.locator('.cf-room').count()!==5)throw Error('Missing agent role');if(await grid.locator('.cf-desk').count()!==10)throw Error('Missing skill variants');
 if(runPosts)throw Error('Creating unexpectedly started an execution');
 if(posted.configuration.combination_max_loops!==48)throw Error('Loop limit not saved');
 await page.getByRole('button',{name:'Run combinations'}).waitFor();
 await page.getByRole('button',{name:'Loop explorer',exact:true}).click();await grid.getByRole('spinbutton',{name:'Combination Loop',exact:true}).fill('48'); await grid.getByText('Combination 24 · cycle 2',{exact:true}).waitFor(); await grid.getByText(/Actual skill 48/).first().waitFor(); await grid.getByRole('spinbutton',{name:'Combination Loop',exact:true}).fill('1'); await grid.getByText(/Actual skill 1/).first().waitFor(); if(await grid.getByText(/Actual skill 48/).count())throw Error('Stale Loop content');
 console.log('Frozen 48-Loop history selection verified; Selected workflow opens; 24 combinations/48 Loops/5 roles; narrow layout valid; create does not run; all writes mocked.');
}finally{await browser.close();}
