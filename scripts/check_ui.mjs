// Browser acceptance against the real production UI and an isolated fixture API.
// Set PUPPETEER_MODULE to an installed puppeteer ES module. No live LLM or patient data.
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { default: puppeteer } = await import(process.env.PUPPETEER_MODULE || 'puppeteer');
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
try{
 browser=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--no-sandbox'],userDataDir:fs.mkdtempSync('/tmp/memstara-ui-')});
 const page=await browser.newPage();await page.setViewport({width:1440,height:1000});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'networkidle0'});
 const clickText=async text=>{await page.evaluate(text=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text);if(!b)throw Error(`Missing button ${text}`);b.click();},text);};
 const count=()=>page.$$eval('.react-flow__node-chain',x=>x.length);
 assert.equal(await count(),5);
 // Explanations open on hover/focus, dismiss on Escape, and do not alter settings.
 await page.hover('button[aria-label="Help: Trials"]');
 await page.waitForFunction(()=>[...document.querySelectorAll('[role="tooltip"]')].some(n=>n.textContent.includes('does not create 4 agents')));
 await page.screenshot({path:'/tmp/memstara-help-trials.png',fullPage:true});
 await page.keyboard.press('Escape');
 await page.waitForFunction(()=>!document.querySelector('[role="tooltip"]'));
 await page.mouse.move(0,0);
 await page.focus('button[aria-label="Help: Waves"]');
 await page.waitForFunction(()=>[...document.querySelectorAll('[role="tooltip"]')].some(n=>n.textContent.includes('rounds of hypothesis')));
 await page.keyboard.press('Escape');
 assert.equal(await count(),5);

 await page.click('.react-flow__node-chainAdd button');await page.waitForSelector('dialog[open]');
 assert.equal(await count(),5,'opening the panel does not add a slot');
 assert.equal(await page.$eval('dialog select option[value="treatment-toxicity"]',o=>o.disabled),true);
 await clickText('Cancel');assert.equal(await count(),5);
 await page.click('.react-flow__node-chainAdd button');await page.select('dialog select','shared-anatomy');await clickText('Add hypothesis');
 await page.waitForFunction(()=>document.querySelectorAll('.react-flow__node-chain').length===6);
 await page.click('.react-flow__node-chainAdd button');await page.select('dialog select','taxonomic');await clickText('Add hypothesis');
 await page.waitForFunction(()=>document.querySelectorAll('.react-flow__node-chain').length===7);
 assert.equal(await page.$eval('.react-flow__node-chainAdd button',b=>b.disabled),true);
 await page.reload({waitUntil:'networkidle0'});assert.equal(await count(),7,'draft survives reload');
 // Floor plan must fit all cards without overlaps, including three hypotheses.
 await page.evaluate(()=>[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('Floor plan')).click());
 await page.waitForSelector('.react-flow__node-place');
 for (const width of [1440,1100]) {
  await page.setViewport({width,height:1000});
  await new Promise(r=>setTimeout(r,600));
  const layout=await page.evaluate(()=>{
   const rect=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};};
   return {bounds:rect(document.querySelector('.react-flow')),nodes:[...document.querySelectorAll('.react-flow__node-agent, .react-flow__node-place')].map(rect),edges:document.querySelectorAll('.react-flow__edge').length};
  });
  assert.equal(layout.nodes.length,13);assert.equal(layout.edges,6,'three hypotheses converge, then three shared stage links');
  for(let i=0;i<layout.nodes.length;i++) {
   const a=layout.nodes[i],b=layout.bounds;
   assert(a.x>=b.x-1&&a.right<=b.right+1&&a.y>=b.y-1&&a.bottom<=b.bottom+1,'node fits canvas');
   for(const c of layout.nodes.slice(i+1)) assert(!(a.x<c.right&&a.right>c.x&&a.y<c.bottom&&a.bottom>c.y),'no node overlap');
  }
 }
 await page.setViewport({width:1440,height:1000});await new Promise(r=>setTimeout(r,500));
 await page.screenshot({path:'/tmp/memstara-floor-after.png',fullPage:true});
 await page.evaluate(()=>[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('Pipeline')).click());
 await page.waitForSelector('.react-flow__node-chain');
 await clickText('ml_governance');
 await page.click('dialog button[aria-label="Help: CV folds (0 = off)"]');
 await page.waitForFunction(()=>!!document.querySelector('dialog [role="tooltip"]'));
 await page.screenshot({path:'/tmp/memstara-help-dialog.png',fullPage:true});
 await page.keyboard.press('Escape');
 assert(await page.$('dialog[open]'),'Escape dismisses tooltip before closing settings');
 await page.select('dialog select[aria-label="Predictive model"]','random_forest');await clickText('Save settings');
 await page.screenshot({path:'/tmp/memstara-ui-configured.png',fullPage:true});
 await clickText('Start run');await page.waitForFunction(()=>document.body.textContent.includes('Fixture stops'));
 assert.equal(request.hypothesis_agents,3);assert.equal(request.evaluation.engine,'random_forest');
 assert.equal(request.playbook_hypothesis,'treatment-toxicity,shared-anatomy,taxonomic');
 // Delete the middle hypothesis, retaining the third one's skill.
 const removes=await page.$$('.react-flow__node-chain button[title^="Do not start"]');await removes[1].click();
 await page.waitForFunction(()=>document.querySelectorAll('.react-flow__node-chain').length===6);
 const draft=await page.evaluate(()=>JSON.parse(localStorage.getItem('memstara-draft-v1')));
 assert.equal(draft.playbook_hypothesis,'treatment-toxicity,taxonomic');
 await clickText('taxonomic');
 const upload=path.join(fs.mkdtempSync('/tmp/memstara-skill-'),'new-skill.md');
 fs.writeFileSync(upload,'# New perspective\nUse different biological evidence.');
 await (await page.$('dialog input[type="file"]')).uploadFile(upload);
 await page.waitForFunction(()=>document.querySelector('dialog select')?.value==='user-uploaded');
 await clickText('Save settings');
 const uploaded=await page.evaluate(()=>JSON.parse(localStorage.getItem('memstara-draft-v1')));
 assert.equal(uploaded.playbook_hypothesis,'treatment-toxicity,user-uploaded');
 // Reproduce the reported failure: three old trials plus two live configured
 // agents, then another LLM invocation for the first agent.
 const template=snapshot.scene.agents.find(a=>a.stage==='hypothesis');
 const make=(id,book,state)=>({...template,id,playbook:book,state,name:`memstara-board-hypothesis-${book}`,
  run_id:state==='working'?id:null,worker:id});
 snapshot.scene.agents=[...snapshot.scene.agents.filter(a=>a.stage!=='hypothesis'),
  ...[0,1,2].map(i=>make(`old-${i}`,'','idle')),
  make('live-first','treatment-toxicity','working'),make('live-second','user-uploaded','working'),
  make('repeat-first','treatment-toxicity','idle')];
 snapshot.scene.flashes=[{agent:'live-first',place:'okf',tool:'okf_read',at:new Date().toISOString()}];
 await page.waitForFunction(()=>[...document.querySelectorAll('.react-flow__node-chain')].filter(n=>n.textContent.includes('Working')).length===2);
 assert.equal(await count(),6,'two configured hypotheses remain two despite historical and repeated calls');
 await page.reload({waitUntil:'networkidle0'});assert.equal(await count(),6);
 await page.evaluate(()=>[...document.querySelectorAll('nav button')].find(b=>b.textContent.includes('Floor plan')).click());
 await page.waitForSelector('.react-flow__node-agent');
 assert.equal((await page.$$('.react-flow__node-agent')).length,6);
 assert.equal((await page.$$('.react-flow__edge')).length,6,'two hypothesis edges, three shared stage links and remapped live tool edge');
 await page.screenshot({path:'/tmp/memstara-two-hypotheses-regression.png',fullPage:true});
 snapshot.board.tasks=[{task_id:99,trial:9,status:'failed',task_type:'ml',error:'Target labels are missing; labels cannot be imputed',columns:[],columns_used:[],columns_missing:[],importance:{},attempts:1}];
 await page.waitForFunction(()=>document.querySelector('#results-panel')?.textContent.includes('labels cannot be imputed'));
 assert.match(await page.$eval('#results-panel',n=>n.textContent),/Failed trials have no reported performance/);
 await page.click('button[aria-label="Inspect Hypothesis 1"]');
 await page.waitForSelector('.floor-agent-selected');
 assert.match(await page.$eval('.floor-inspector',n=>n.textContent),/Skill:/);
 assert.match(await page.$eval('.floor-inspector',n=>n.textContent),/Last observed tool: okf_read/);
 await page.screenshot({path:'/tmp/memstara-floor-focus.png',fullPage:true});
 await clickText('Tool activity');
 assert.equal((await page.$$('.react-flow__edge')).length,5,'tool toggle preserves structural workflow');
 await page.click('button[aria-label="Pause flow animation"]');
 assert.equal((await page.$$('.react-flow__edge.animated')).length,0);
 await page.click('button[aria-label="Clear agent selection"]');
 assert.equal((await page.$$('.floor-agent-selected')).length,0);
 snapshot.run_tag='scoped-run';
 snapshot.run_configuration={hypotheses:3,books:{hypothesis:['treatment-toxicity','user-uploaded','shared-anatomy']},evaluation:{engine:'xgboost',seed:42,test_size:.25,folds:0,replicates:1,search_trials:1},trials:3,waves:1};
 snapshot.report={status:'completed',text:'# Verified report\n\n| Trial | AUC |\n| --- | --- |\n| 1 | 0.65 |\n\n**Saved evidence**, not invented metrics.'};
 liveRun={run_tag:'scoped-run',pid:123,run_dir:'fixture',started:new Date().toISOString(),skill:'',configuration:snapshot.run_configuration};
 await page.reload({waitUntil:'networkidle0'});
 await page.waitForFunction(()=>document.querySelectorAll('.react-flow__node-chain').length===7);
 assert.equal(await count(),7,'saved active run with three hypotheses overrides a two-hypothesis browser draft');
 await page.locator('[data-testid="final-report"] button[aria-expanded]').click();
 await page.waitForSelector('[data-testid="final-report"] table');
 assert.match(await page.$eval('[data-testid="final-report"]',n=>n.textContent),/Verified report/);
 await page.screenshot({path:'/tmp/memstara-final-report-component.png',fullPage:true});
 healthDown=true;
 await new Promise(r=>setTimeout(r,2600));
 assert.equal(await count(),7,'control outage must not erase the running configuration');
 assert.match(await page.$eval('[data-testid="final-report"]',n=>n.textContent),/scoped-run/);
 healthDown=false;
 snapshot.health.memstara={up:false,error:'Simulated outage'};
 snapshot.board={lanes:{},tasks:[]}; snapshot.results=[];
 await page.waitForFunction(()=>document.querySelector('#results-panel')?.textContent.includes('Connection interrupted'));
 assert.match(await page.$eval('#results-panel',n=>n.textContent),/labels cannot be imputed/);
 snapshot.health.memstara={up:true,error:''};
 assert.deepEqual(errors,[]);
 console.log('PASS: panel/cancel/distinct skills/add/cap/restore/model/submit/middle deletion/upload/history and repeated-call identity; no browser errors');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
