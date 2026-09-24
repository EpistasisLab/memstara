// Browser acceptance against the real production UI and an isolated fixture API.
// Set PUPPETEER_MODULE to an installed puppeteer ES module. No live LLM or patient data.
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
let liveRun = null;
let healthDown = false;
const server = http.createServer(async(req,res)=>{
 const route = req.url.split('?')[0];
 if(route.startsWith('/api/') || route.startsWith('/control/')){
  let body=''; for await(const chunk of req) body+=chunk;
  let data={};
  if(route==='/api/snapshot') data=snapshot;
  if(route==='/control/health') { data={running:liveRun,bundle:{documents:10}}; if(healthDown) res.statusCode=503; }
  if(route==='/control/skills') data={skills:[]};
  if(route==='/control/playbooks') {
   if(req.method==='POST') { const b=JSON.parse(body); const item={id:'user-uploaded',stage:b.stage,title:b.name,
    description:'Uploaded test skill',content:b.content,hash:'new-content-hash',source:'User supplied'};skills.push(item);data=item; }
   else data={playbooks:skills.map(x=>x.id),catalog:skills,stages};
  }
  if(route==='/control/runs' && req.method==='POST'){request=JSON.parse(body);data={error:'Fixture stops before execution'};res.statusCode=400;}
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
 browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/Applications/Chromium.app/Contents/MacOS/Chromium', headless:true});
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 await page.getByRole('button',{name:'Play',exact:true}).waitFor();
 assert.equal(await page.getByText('Exploration mode',{exact:true}).count(),0);
 assert.equal(await page.getByLabel('Hypotheses to investigate',{exact:true}).count(),0);
 const agentSettings = page.getByRole('region',{name:'Agent settings',exact:true});
 await agentSettings.waitFor();
 for (const stage of ['hypothesis','machine learning','interpreter','report']) {
   await agentSettings.getByRole('button',{name:`Configure ${stage} 1`,exact:true}).click();
   await page.getByRole('dialog').waitFor();
   await page.getByRole('button',{name:'Close settings',exact:true}).click();
 }
 await agentSettings.getByRole('button',{name:'Add hypothesis agent',exact:true}).click();
 await page.getByRole('dialog').waitFor();
 await page.getByRole('dialog').locator('select').first().selectOption('shared-anatomy');
 await page.getByRole('dialog').getByRole('button',{name:'Add hypothesis',exact:true}).click();
 await agentSettings.getByRole('button',{name:'Configure hypothesis 2',exact:true}).waitFor();
 await agentSettings.getByRole('button',{name:'Remove hypothesis 2',exact:true}).click();
 await agentSettings.getByRole('button',{name:'Keep agent',exact:true}).click();
 assert.equal(await agentSettings.getByRole('button',{name:'Configure hypothesis 2',exact:true}).count(),1);
 await agentSettings.getByRole('button',{name:'Remove hypothesis 2',exact:true}).click();
 await agentSettings.getByRole('button',{name:'Remove agent',exact:true}).click();
 assert.equal(await agentSettings.getByRole('button',{name:'Configure hypothesis 2',exact:true}).count(),0);
 assert.equal(await agentSettings.getByRole('button',{name:'Remove hypothesis 1',exact:true}).isDisabled(),true);
 await page.reload();
 await agentSettings.waitFor();
 assert.equal(await agentSettings.getByRole('button',{name:'Configure hypothesis 2',exact:true}).count(),0);
 await page.getByRole('button',{name:'Play',exact:true}).click();
 await page.getByText('Fixture stops before execution',{exact:true}).waitFor();
 assert.equal(request.continuous,true);
 assert.equal(request.trials,request.hypothesis_agents);
 assert.equal(request.question,'');
 assert.equal(request.waves,1);
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'/tmp/memstara-exploration-mobile.png',fullPage:true});
 console.log('PASS: simple Play control sends continuous exploration with an automatic work allocation');
} finally { if(browser) await browser.close(); await new Promise(r=>server.close(r)); }
