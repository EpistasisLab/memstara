// Browser acceptance against the real production UI and an isolated fixture API.
// Uses Playwright Chromium (or CHROME_PATH). No live LLM, patient data, or workspace writes.
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
import { chromium } from '../viewer/web/node_modules/@playwright/test/index.mjs';
const skills = [
 ['treatment-toxicity','hypothesis'],['shared-anatomy','hypothesis'],['taxonomic','hypothesis'],
 ['ml_governance','ml'],['interpreter_clinical','interpreter'],['report_evidence','report'],
].map(([id,stage])=>({id,stage,title:id,description:`Description of ${id}`,content:`# ${id}\nMeasured evidence.`,hash:id,source:'Test fixture'}));
const stages = ['hypothesis','data','ml','interpreter','report'];
const snapshot = {run_tag:'', runs:[], stale:false, generated_at:new Date().toISOString(),
 health:{memstara:{up:true,error:''},core:{up:true,error:''}},
 scene:{places:["okf","matcher","board","results","dataset","ml"].map(id=>({id,label:id,sub:id,x:0,y:0})), flashes:[],agents:stages.map((stage,i)=>({id:stage,stage,label:stage,worker:null,slot:0,
  running:0,name:`memstara-board-${stage}`,playbook:'',state:'idle',at:null,home:{x:i*240,y:0},
  carrying:null,run_id:null,since:null,last_tool:null,windows:[]}))},
 board:{lanes:{},tasks:[]}, agents:[],access:{rows:[],windows:[]},feed:[],results:[]};
let request;
let pipelines=[];let writes=0;let failCreation=false;let starts=0;
let liveRun = null;
let healthDown = false;
const server = http.createServer(async(req,res)=>{
 const route = req.url.split('?')[0];
 if(route.startsWith('/api/') || route.startsWith('/control/')){
  let body=''; for await(const chunk of req) body+=chunk;
  let data={};
  if(route==='/api/runs') data={runs:[]};
  if(route==='/control/pipelines'){
    if(req.method==='POST'){writes++;const b=JSON.parse(body);if(failCreation){res.statusCode=503;data={error:'Fixture save failed'};}else{data={id:'created',number:1,name:b.name,configuration:b.configuration,running:null,latest:null,progress:{}};pipelines.push(data);}}
    else data={pipelines};
  }
  if(route==='/api/snapshot') data=snapshot;
  if(route==='/control/health') { data={running:liveRun,bundle:{documents:10}}; if(healthDown) res.statusCode=503; }
  if(route==='/control/skills') data={skills:[]};
  if(route==='/control/playbooks') {
   if(req.method==='POST') { const b=JSON.parse(body); const item={id:'user-uploaded',stage:b.stage,title:b.name,
    description:'Uploaded test skill',content:b.content,hash:'new-content-hash',source:'User supplied'};skills.push(item);data=item; }
   else data={playbooks:skills.map(x=>x.id),catalog:skills,stages};
  }
  if(route==='/control/runs' && req.method==='POST'){starts++;request=JSON.parse(body);data={error:'Fixture stops before execution'};res.statusCode=400;}
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));return;
 }
 const relative=route==='/'?'index.html':route.slice(1);
 const target=path.resolve(root,'viewer/web/dist',relative);
 if(!target.startsWith(path.resolve(root,'viewer/web/dist')+path.sep)){res.writeHead(403).end();return;}
 try{res.setHeader('Content-Type',target.endsWith('.js')?'application/javascript':target.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(target));}
 catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));

let browser;
try {
 browser = await chromium.launch({executablePath:process.env.CHROME_PATH,headless:true});
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 const add=page.getByRole('button',{name:/Add Pipeline/}).first();
 await add.click();
 const dialog=page.getByRole('dialog',{name:'Create a pipeline',exact:true});
 assert.equal(await dialog.evaluate(e=>e.matches(':modal')),true);
 for(let i=0;i<10;i++){await page.keyboard.press('Tab');assert.equal(await dialog.evaluate(e=>e.contains(document.activeElement)),true);}
 await dialog.getByLabel('Pipeline name').fill('Discard me');
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 assert.equal(writes,0);
 await page.keyboard.press('Escape');
 assert.equal(await dialog.count(),0);
 assert.equal(pipelines.length,0);
 await add.click();
 assert.equal(await dialog.getByLabel('Pipeline name').inputValue(),'');
 await dialog.getByLabel('Pipeline name').fill('My treatment study');
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 await dialog.getByLabel('Hypothesis skill', {exact:true}).selectOption('shared-anatomy');
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 await dialog.getByLabel('ML model', {exact:true}).selectOption('random_forest');
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 await dialog.getByLabel('Interpretation skill', {exact:true}).selectOption('interpreter_clinical');
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 await dialog.getByRole('button',{name:'Next',exact:true}).click();
 assert.equal(writes,0);
 for(const [width,height] of [[390,600],[844,390],[1440,850]]){
  await page.setViewportSize({width,height});
  for(const theme of ['dark','light']){
   await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
   assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth+1),false);
   assert.equal(await dialog.locator('footer').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}),true);
  }
 }
 await page.screenshot({path:'/tmp/memstara-pipeline-creation-review.png'});
 failCreation=true;
 await dialog.getByRole('button',{name:'Create pipeline',exact:true}).click();
 await dialog.getByRole('alert').filter({hasText:'Fixture save failed'}).waitFor();
 assert.equal(pipelines.length,0);
 assert.equal(await dialog.getByText('My treatment study',{exact:true}).count(),1);
 failCreation=false;
 await dialog.getByRole('button',{name:'Create pipeline',exact:true}).click();
 await dialog.waitFor({state:'detached'});
 assert.equal(pipelines.length,1);
 assert.equal(pipelines[0].name,'My treatment study');
 assert.equal(pipelines[0].configuration.playbook_hypothesis,'shared-anatomy');
 assert.equal(pipelines[0].configuration.evaluation.engine,'random_forest');
 assert.equal(pipelines[0].configuration.playbook_interpreter,'interpreter_clinical');
 assert.equal(pipelines[0].configuration.question,'');
 assert.equal(starts,0);
 assert.deepEqual(errors,[]);
 console.log('PASS: draft cancellation, stage selection, responsive themes, failed-save retry, atomic creation, no automatic run');
} finally {await browser?.close();await new Promise(r=>server.close(r));}
