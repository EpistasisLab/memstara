import {openBuildModeFixture} from './build-mode.fixture.mjs';
// Mock every API write and generation: exercise UI contracts without paid model calls.
import {chromium, expect} from '@playwright/test';
import fs from 'node:fs';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
const roles=['hypothesis','data','ml','interpreter','report'];
const labels=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
try {
 for(const mode of ['Selected Pipelines','All Combinations']) {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[],calls=[],saves=[];
  page.on('pageerror',e=>errors.push(e.message));
  let releaseModels;
  let catalog=roles.map(stage=>({id:stage,stage,title:stage,content:'# Default',hash:stage,source:'Default'}));
  await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Offline fixture'}}));
  await page.route('**/control/**',async r=>{
   const path=new URL(r.request().url()).pathname;
   if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[]}});
   if(path==='/control/research-inputs')return r.fulfill({json:{inputs:[]}});
if(path==='/control/skills')return r.fulfill({json:{skills:[]}});
   if(path==='/control/skill-drafts/models'){
    await new Promise(resolve=>{releaseModels=resolve;});
    return r.fulfill({json:{agents:Object.fromEntries(['question','hypothesis','data','ml','interpretation','explanation'].map(role=>[role,{provider:'openai',model:'selected-model'}]))}});
   }
   if(path==='/control/skill-drafts'){calls.push(r.request().postDataJSON());return r.fulfill({status:202,json:{id:String(calls.length),status:'generating'}});}
   if(path.startsWith('/control/skill-drafts/'))return r.fulfill({json:{status:'ready',content:'# Draft',model:'selected-model',provider:'openai'}});
   if(path==='/control/playbooks'){
    if(r.request().method()==='GET')return r.fulfill({json:{catalog,playbooks:catalog.map(s=>s.id),stages:roles,references:[]}});
    const q=r.request().postDataJSON();saves.push(q);const skill={...q,id:'generated-'+saves.length,title:q.name,hash:'hash-'+saves.length,source:'User'};catalog.push(skill);return r.fulfill({json:skill});
   }
   if(r.request().method()!=='GET')throw Error('Unexpected mutation '+path);
   return r.fulfill({json:{}});
  });
  const base=process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:8070';
  const dist=new URL('../dist/',import.meta.url);
  await page.route(base+'/',r=>r.fulfill({path:new URL('index.html',dist).pathname,contentType:'text/html'}));
  await page.route('**/assets/**',r=>{const name=new URL(r.request().url()).pathname.split('/').at(-1);return r.fulfill({path:new URL('assets/'+name,dist).pathname,contentType:name.endsWith('.css')?'text/css':'application/javascript'});});
  await page.goto(base);await page.getByRole('button',{name:/Add pipeline/i,exact:true}).click();await openBuildModeFixture(page,mode);
  const d=page.getByRole('dialog',{name:mode==='Selected Pipelines'?'Create a pipeline':'All Combinations',exact:true});
  await d.getByLabel('Deployment target column',{exact:true}).fill('fixture_target');
if(mode==='Selected Pipelines'){await d.getByRole('checkbox',{name:/Use .* for this pipeline/}).check();await d.getByRole('button',{name:'Next',exact:true}).click();}
  else await d.getByRole('button',{name:'Choose skills',exact:true}).click();
  for(let i=0;i<roles.length;i++) {
   if(mode==='All Combinations'){
    await d.getByRole('navigation',{name:'Agent roles'}).getByRole('button',{name:new RegExp('^'+labels[i])}).click();
    await d.getByRole('button',{name:/^Create with AI/}).click();
   }
   await d.getByRole('button',{name:'Create a skill with AI',exact:true}).click();
   const assistant=d.locator('.hypothesis-skill-wizard:visible');
   await expect(assistant.getByLabel('Generation model / deployment')).toBeDisabled();
   await expect.poll(()=>typeof releaseModels).toBe('function');
   releaseModels();releaseModels=undefined;
   await expect(assistant.getByLabel('Generation model / deployment')).toBeEnabled();
   for(const input of await assistant.locator('fieldset').first().locator('textarea').all())await input.fill('General research priorities');
   await expect(assistant.getByLabel('Generation model / deployment')).toHaveValue('selected-model');
   await expect(assistant.getByLabel('Generation model / deployment')).not.toBeEditable();
   await assistant.getByRole('button',{name:'Generate skill draft',exact:true}).click();
   await expect(assistant.getByLabel('Generated Markdown skill')).toHaveValue('# Draft');
   const save=assistant.getByRole('button',{name:mode==='Selected Pipelines'?'Save and select for this pipeline':'Save and add to combinations'});
   await expect(save).toBeDisabled();await assistant.getByLabel('Generated skill name').fill('clinical-'+roles[i]);
   await assistant.getByLabel('Generated Markdown skill').fill('# Edited '+roles[i]);
   await assistant.getByRole('checkbox',{name:'I reviewed these instructions and want to use this skill.'}).check();await save.click();await expect(assistant.getByText('Saved and selected. Finish the pipeline review when ready.',{exact:true})).toBeVisible();await expect(save).toBeDisabled();
   if(calls.at(-1).stage!==roles[i]||saves.at(-1).stage!==roles[i]||calls.at(-1).model!=='selected-model'||saves.at(-1).content!=='# Edited '+roles[i])throw Error(JSON.stringify({role:roles[i],call:calls.at(-1),save:saves.at(-1)}));
   if(mode==='Selected Pipelines')await expect(d.getByRole('combobox',{name:labels[i]+' skill',exact:true})).toHaveValue('generated-'+saves.length);
   else {
    await expect(d.locator('.comb-selected-skills')).toContainText('clinical-'+roles[i]);
    await assistant.getByRole('button',{name:new RegExp('^Create another')}).click();await assistant.getByRole('button',{name:'Generate skill draft',exact:true}).click();
    await expect(assistant.getByLabel('Generated Markdown skill')).toHaveValue('# Draft');await assistant.getByLabel('Generated skill name').fill('second-'+roles[i]);
    await assistant.getByRole('checkbox',{name:'I reviewed these instructions and want to use this skill.'}).check();await save.click();await expect(assistant.getByText('Saved and selected. Finish the pipeline review when ready.',{exact:true})).toBeVisible();await expect(save).toBeDisabled();
    await expect(d.locator('.comb-selected-skills')).toContainText('second-'+roles[i]);
    if(saves.at(-1).stage!==roles[i])throw Error('Second skill role mismatch');
   }
   for(const theme of ['light','dark'])for(const width of [1440,390,320]){
    await page.setViewportSize({width,height:900});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
    const v=await d.evaluate(el=>{const f=el.querySelector('footer,.comb-footer').getBoundingClientRect();const nav=el.querySelector('.comb-roles');return {overflow:el.scrollWidth>el.clientWidth+2,footer:f.bottom<=innerHeight,navGrid:!nav||innerWidth>640||getComputedStyle(nav).display==='grid'};});
    if(v.overflow||!v.footer||!v.navGrid)throw Error(JSON.stringify({mode,i,width,theme,v}));
   }
   if(i===4)await page.screenshot({path:'/tmp/all-agent-skills-'+(mode==='Selected Pipelines'?'selected':'combinations')+'.png'});
   await page.setViewportSize({width:1440,height:1000});
   if(mode==='Selected Pipelines')await d.getByRole('button',{name:'Next',exact:true}).click();
  }
  if(mode==='Selected Pipelines')await expect(d.getByRole('textbox',{name:'Pipeline name',exact:true})).toBeVisible();
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({mode,roles:5,generations:calls.length,saves:saves.length,responsiveChecks:30,errors}));
  await page.unrouteAll({behavior:'ignoreErrors'});await page.close();
 }
}finally{await browser.close();}
