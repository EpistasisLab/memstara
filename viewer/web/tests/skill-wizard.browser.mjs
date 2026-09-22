// All API writes and model generation mocked; no production mutation.
import {chromium,expect} from '@playwright/test';
console.log("Launching browser");
const b=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
console.log('Browser ready');
try{for(const mode of ['Selected Pipelines','All Combinations']){
const p=await b.newPage({viewport:{width:1280,height:900}});p.setDefaultTimeout(15000);let saves=[],calls=[],failure=true,n=0,transient=false;
const roles=['hypothesis','data','ml','interpreter','report'];let catalog=roles.map(stage=>({id:stage,stage,title:stage,content:'# Base',hash:stage,source:'Default'}));
p.on('pageerror',e=>console.log('PAGE ERROR',e.message));
await p.route('**/api/**',async r=>{const u=new URL(r.request().url());const response=await r.fetch({url:'http://127.0.0.1:8070'+u.pathname+u.search});return r.fulfill({response});});
await p.route('**/control/**',r=>{const path=new URL(r.request().url()).pathname;
if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[]}});
if(path==='/control/skills')return r.fulfill({json:{skills:[]}});
if(path==='/control/skill-drafts/models')return r.fulfill({json:{provider:'openai',default_model:'default-model',models:['default-model']}});
if(path==='/control/skill-drafts'){calls.push(r.request().postDataJSON());return r.fulfill({status:202,json:{id:String(++n),status:'generating'}});}
if(path.startsWith('/control/skill-drafts/')&&n===3&&!transient){transient=true;return r.fulfill({status:503,json:{error:'Temporary connection failure'}});}
if(path.startsWith('/control/skill-drafts/'))return r.fulfill({json:failure?{status:'failed',error:'Test failure'}:{status:'ready',content:'# Draft '+n,model:'chosen-model',provider:'openai'}});
if(path==='/control/playbooks'){if(r.request().method()==='GET')return r.fulfill({json:{catalog,playbooks:catalog.map(s=>s.id),stages:roles,references:[]}});const q=r.request().postDataJSON();saves.push(q);const s={...q,id:'saved-'+saves.length,title:q.name,hash:String(saves.length),source:'User'};catalog.push(s);return r.fulfill({json:s});}
if(r.request().method()==='POST')throw Error('Unexpected write '+path);return r.fulfill({json:{}});});
await p.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4175');await p.getByRole('button',{name:/Add Pipeline/}).click();await p.getByRole('button',{name:new RegExp(mode)}).click();
const d=p.getByRole('dialog',{name:mode==='Selected Pipelines'?'Create a pipeline':'All Combinations',exact:true});
if(mode==='Selected Pipelines'){await d.getByRole('checkbox',{name:/Use .* for this pipeline/}).check();await d.getByRole('button',{name:'Next',exact:true}).click();}else await d.getByRole('button',{name:'Choose skills'}).click();
await d.getByRole('button',{name:'Create a skill with AI'}).click();
for(const label of ['What is your clinical domain','What patient population','What clinical features','Are there any variables'])await d.getByLabel(new RegExp('^'+label)).fill('General clinical research');
await d.getByLabel('Generation model / deployment').fill('chosen-model');await d.getByRole('button',{name:'Generate skill draft',exact:true}).click();await d.getByRole('alert').filter({hasText:'Test failure'}).waitFor();
await expect(d.getByLabel(/^What is your clinical domain/)).toHaveValue('General clinical research');failure=false;
await d.getByRole('button',{name:'Generate skill draft',exact:true}).click();await expect(d.getByLabel('Generated Markdown skill')).toHaveValue('# Draft 2');if(saves.length)throw Error('Saved before review');
const save=d.getByRole('button',{name:mode==='Selected Pipelines'?'Save and select for this pipeline':'Save and add to combinations'});await expect(save).toBeDisabled();
await d.getByLabel('Generated skill name').fill('clinical-one');await d.getByLabel('Generated Markdown skill').fill('# Clinician edited');await d.getByRole('checkbox',{name:'I reviewed these instructions and want to use this skill.'}).check();await save.click();await expect(save).toBeDisabled();
if(saves[0]?.content!=='# Clinician edited'||calls.some(c=>c.model!=='chosen-model'))throw Error('Lost content/model');
if(mode==='Selected Pipelines')await expect(d.getByRole('combobox',{name:'Hypothesis skill',exact:true})).toHaveValue('saved-1');else{
await expect(d.getByRole('checkbox',{name:'clinical-one'})).toBeChecked();await d.getByRole('button',{name:'Create another Hypothesis skill'}).click();await d.getByRole('button',{name:'Generate skill draft',exact:true}).click();await d.getByRole('alert').filter({hasText:'Temporary connection failure'}).waitFor();await d.getByRole('button',{name:'Check generation status'}).click();await expect(d.getByLabel('Generated Markdown skill')).toHaveValue('# Draft 3');if(calls.length!==3)throw Error('Status retry caused a new paid generation');await d.getByLabel('Generated skill name').fill('clinical-two');await d.getByRole('checkbox',{name:'I reviewed these instructions and want to use this skill.'}).check();await save.click();await expect(d.getByRole('checkbox',{name:'clinical-two'})).toBeChecked();await expect(d.getByRole('checkbox',{name:'clinical-one'})).toBeChecked();}
for(const theme of ['light','dark']){await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);
for(const viewport of [{width:1280,height:900},{width:390,height:844},{width:900,height:500}]){
await p.setViewportSize(viewport);
const geometry=await d.evaluate(el=>{const body=el.querySelector('.comb-step-content,.pipeline-creation-body');const footer=el.querySelector('.comb-footer,.pipeline-creation-footer');const before=footer.getBoundingClientRect();body.scrollTop=body.scrollHeight;const after=footer.getBoundingClientRect();return {content:body.clientHeight,viewport:innerHeight,bottom:after.bottom,stable:Math.abs(before.top-after.top)<2,overflow:el.scrollWidth>el.clientWidth+2};});
if(geometry.content<geometry.viewport*.4||geometry.bottom>viewport.height||!geometry.stable||geometry.overflow)throw Error('Dialog layout failed '+JSON.stringify({viewport,geometry}));
}}
await p.setViewportSize({width:390,height:844});if(await d.evaluate(e=>e.scrollWidth>e.clientWidth+2))throw Error('Overflow');
if(mode==='All Combinations'){if(await d.getByRole('navigation',{name:'Agent roles'}).evaluate(e=>e.clientHeight>110))throw Error('Mobile role navigation is too tall');await d.getByRole('navigation',{name:'Agent roles'}).getByRole('button').nth(1).click();await expect(d.getByRole('button',{name:'Create a skill with AI'})).toHaveCount(0);}
await p.screenshot({path:'/tmp/memstara-skill-'+(mode==='Selected Pipelines'?'selected':'combinations')+'.png'});
console.log(mode+': failure recovery, selected model, review/edit/save, correct skill selection, narrow layout passed.');await p.unrouteAll({behavior:'ignoreErrors'});await p.close();
}}finally{await b.close();}
