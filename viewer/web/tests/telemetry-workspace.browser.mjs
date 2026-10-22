import {expect} from '@playwright/test';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import assert from 'node:assert/strict';

const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
const browser=await launchResponsiveBrowser();
const metric={calls:12,tokens:241800,tokens_status:'partial',cost:{usd:1.25,status:'partial',missing_costs:2},seconds:1625,duration_basis:'Observed agent span, including pauses and overlapping agent calls.',duration_status:'recorded'};
const summary={sample_count:0,completed_count:2,excluded_completed:2,other_loops:0,seconds:null,usd:null,tokens:null,basis:'Only fully measured, completed loops are included.'};
const loops=[{...metric,number:1,calls:5,status:'completed'},{...metric,number:2,calls:7,status:'completed'}];
const alpha={...metric,run_tag:'telemetry-alpha',pipeline_id:'alpha',model:'fixture-model',provider:'fixture-provider',loops,loop_summary:summary,unassigned:{...metric,calls:0}};
const beta={...alpha,run_tag:'telemetry-beta',pipeline_id:'beta',tokens:0,tokens_status:'unavailable',seconds:null,cost:{usd:0,status:'unavailable',missing_costs:12},loops:[]};
const totals={scope:'All registered executions',updated_at:'2026-10-22T12:34:00Z',total:metric,pipelines:[{...metric,id:'alpha',name:'Research pipeline',executions:1},{...beta,id:'beta',name:'Second pipeline',executions:1}],executions:[alpha,beta],loop_summary:summary};
function snapshot(tag,loop){
  const label=tag==='telemetry-alpha'?'Alpha':'Beta';
  return {run_tag:tag,generated_at:totals.updated_at,stale:false,runs:[],health:{core:{up:true},memstara:{up:true}},scene:{places:[],agents:[],flashes:[]},
    board:{lanes:{},tasks:[]},agents:[{name:`${label}-ml`,id:'ml',path:'board',label:`${label} ML`,runs:2,completed:2,open_runs:0,tokens:{prompt:2000,completion:400},cost:.25,avg_iterations:4,last_run_at:null}],
    access:{rows:[{agent:'ml',agent_label:`${label} ML`,name:'ml',path:'board',server:'ml',tool:'train_and_score',store:'results',calls:2}],windows:[]},results:[],
    feed:[{key:'call',at:totals.updated_at,name:`${label}-ml`,label:`${label} ML`,agent:'ml',tool:'train_and_score',server:'ml',store:'results',path:'board'}],
    telemetry:{loop,loops:loops.map(l=>({...l,tasks:0,results:0})),legacy_attribution:false,unassigned_calls:0},loop_log:{lines:[`${label} recorded console line`],note:'Saved console',truncated:false}};
}
let totalsFail=false,scopeFail=false,slowAlpha=false,pending=false,registryReads=0,costReads=0;
const errors=[],writes=[],billing=[];
let page;
try{
  page=await browser.newPage({viewport:{width:1440,height:900}});
  page.setDefaultTimeout(10000);
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(/\/(api|control)\//,async r=>{
    const u=new URL(r.request().url()),path=u.pathname;
    if(r.request().method()!=='GET'){writes.push(path);return r.abort();}
    if(path.includes('azure-cost'))billing.push(path);
    if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[
      {id:'alpha',name:'Research pipeline — '+ 'Long descriptive name '.repeat(12),latest:{run_tag:'telemetry-alpha'},running:null,configuration:{},progress:{}},
      {id:'beta',name:'Second pipeline',latest:{run_tag:'telemetry-beta'},running:null,configuration:{},progress:{}},
      {id:'pending',name:'Not started',latest:null,running:null,configuration:{},progress:{}},
    ]}});
    if(path==='/api/telemetry/totals')return r.fulfill(totalsFail?{status:503,json:{detail:'Fixture unavailable'}}:{json:totals});
    const tag=u.searchParams.get('run_tag'),loop=u.searchParams.has('loop')?Number(u.searchParams.get('loop')):null;
    if(path==='/api/telemetry'){
      if(scopeFail)return r.fulfill({status:503,json:{detail:'Fixture scoped records unavailable'}});
      if(pending)return r.fulfill({status:202,json:{detail:{status:'loading',run_tag:tag,loop}}});
      if(slowAlpha&&tag==='telemetry-alpha')await new Promise(resolve=>setTimeout(resolve,700));
      return r.fulfill({json:snapshot(tag,loop)}).catch(()=>{});
    }
    if(path==='/api/cost-details'){costReads++;return r.fulfill({json:{run_tag:tag,loop,status:'partial',usd:1.25,recorded_calls:3,unpriced_calls:1,expected_calls:4,groups:[],records:[],coverage_note:'Fixture partial evidence'}});}
    if(path==='/api/telemetry/conversation')return r.fulfill({json:{run_tag:tag,loop,messages:[],limited:false}});
    if(path==='/api/motoro/execution')return r.fulfill({json:{calls:[],note:'Saved runtime records'}});
    if(path==='/api/experiments'){registryReads++;return r.fulfill({json:[{id:'fixture-experiment',combinations:2,executions:2},{id:'other-experiment',combinations:1,executions:1}]});}
    if(path==='/api/experiments/combinations')return r.fulfill({json:[{id:'combination-1',run_tag:u.searchParams.get('experiment_id')==='fixture-experiment'?'experiment-a':'experiment-b',status:'completed',agent_seconds:120,estimated_usd:.25,unpriced_calls:0,definition:{},metrics:[]}]});
    if(path==='/api/experiments/execution'){
      if(tag==='experiment-a')await new Promise(resolve=>setTimeout(resolve,700));
      return r.fulfill({json:{run_tag:tag,configuration:{},prompts:[],agents:[],results:[],costs:[],artifacts:[],report:'Saved report',outcome:{}}}).catch(()=>{});
    }
    return r.fulfill({json:{}});
  });
  const goto=()=>page.goto(root+'/tests/telemetry-workspace.fixture.html');
  await goto();
  const pane=page.locator('.telemetry-workspace'),cards=page.locator('.telemetry-key-metrics');
  await expect(cards).toContainText('27m 5s');
  await expect(cards).toContainText('$1.2500');
  await expect(cards).toContainText('Recorded subtotal · incomplete');
  await expect(cards).toContainText('241,800');
  assert.equal(costReads,0,'Request evidence should load only when opened');
  for(const [width,height] of [[360,600],[390,844],[768,700],[1024,768],[1440,900],[1920,1080]]){
    await page.setViewportSize({width,height});
    const geometry=await pane.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth,wide:[...e.querySelectorAll('*')].filter(n=>n.clientWidth>0&&n.scrollWidth>n.clientWidth+1).slice(0,12).map(n=>({tag:n.tagName,class:n.className,width:n.clientWidth,scroll:n.scrollWidth,overflow:getComputedStyle(n).overflow})),overflow:[...e.querySelectorAll('*')].filter(n=>n.getBoundingClientRect().right>e.getBoundingClientRect().right+1).slice(0,12).map(n=>({tag:n.tagName,class:n.className,width:n.getBoundingClientRect().width,text:n.textContent?.slice(0,50)}))}));
    assert(geometry.scroll<=geometry.width+1,`No horizontal page overflow at ${width}: ${JSON.stringify(geometry)}`);
    const boxes=await cards.locator(':scope > div').evaluateAll(items=>items.map(e=>{const b=e.getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,bottom:b.bottom};}));
    for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++)assert(boxes[i].right<=boxes[j].x||boxes[j].right<=boxes[i].x||boxes[i].bottom<=boxes[j].y||boxes[j].bottom<=boxes[i].y,'Metric cards must not overlap');
    if(process.env.MEMSTARA_SCREENSHOT_DIR&&[390,1440].includes(width))await page.screenshot({path:`${process.env.MEMSTARA_SCREENSHOT_DIR}/telemetry-${width}.png`,fullPage:true});
  }
  await page.setViewportSize({width:1440,height:900});
  await page.evaluate(()=>document.documentElement.dataset.theme='dark');
  if(process.env.MEMSTARA_SCREENSHOT_DIR)await page.screenshot({path:`${process.env.MEMSTARA_SCREENSHOT_DIR}/telemetry-dark.png`});
  await page.evaluate(()=>document.documentElement.dataset.theme='light');
  await page.getByRole('button',{name:'Next loop',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Loop to inspect'})).toHaveValue('1');
  await page.getByRole('button',{name:'Next loop',exact:true}).click();
  await expect(page.getByRole('button',{name:'Next loop',exact:true})).toBeDisabled();
  await expect(cards.locator(':scope > div').last()).toContainText('7');
  await page.getByRole('button',{name:'Previous loop'}).click();
  await expect(cards.locator(':scope > div').last()).toContainText('5');
  await page.getByRole('combobox',{name:'Loop to inspect'}).selectOption('all');
  await page.getByText('Usage & cost details',{exact:true}).click();
  await expect.poll(()=>costReads).toBeGreaterThan(0);
  await page.getByText('Not provided by Motoro.',{exact:true}).waitFor();
  await page.getByText('Usage & cost details',{exact:true}).click();
  await page.getByRole('button',{name:'Agents',exact:true}).click();
  await page.getByRole('cell',{name:'Alpha ML',exact:false}).waitFor();
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await page.getByRole('list',{name:'Recorded activities'}).waitFor();
  await expect(page.getByRole('list',{name:'Recorded activities'})).toContainText('Train and evaluate a model');
  await page.getByRole('combobox',{name:'Detailed records'}).selectOption('Access');
  await page.getByRole('heading',{name:'Pipeline agent calls'}).waitFor();
  await page.getByRole('combobox',{name:'Detailed records'}).selectOption('Tasks');
  await page.getByRole('combobox',{name:'Task in selected loop'}).waitFor();
  await page.getByRole('combobox',{name:'Detailed records'}).selectOption('Results');
  await page.getByRole('heading',{name:'Results',exact:true}).first().waitFor();
  await page.getByRole('combobox',{name:'Detailed records'}).selectOption('Logs');
  await page.getByRole('button',{name:'Console log',exact:true}).click();
  await page.getByText('Alpha recorded console line',{exact:false}).waitFor();
  // A loading response must not be presented as an empty/completed history.
  pending=true;
  await page.getByRole('button',{name:'Agents',exact:true}).click();
  await page.getByRole('heading',{name:'Loading all loops',exact:true}).waitFor();
  pending=false;scopeFail=true;
  await page.getByRole('button',{name:'Refresh telemetry'}).click();
  await page.getByRole('alert').filter({hasText:'Server temporarily unavailable'}).waitFor();
  await expect(page.getByRole('cell',{name:'Alpha ML',exact:false})).toHaveCount(0);
  scopeFail=false;
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await page.getByRole('cell',{name:'Alpha ML',exact:false}).waitFor();
  // A late response from another pipeline cannot overwrite the current selection.
  slowAlpha=true;
  await page.getByRole('button',{name:'Refresh telemetry'}).click();
  await page.getByRole('combobox',{name:'Pipeline to inspect'}).selectOption('beta');
  await page.getByRole('cell',{name:'Beta ML',exact:false}).waitFor();
  await new Promise(resolve=>setTimeout(resolve,900));
  await expect(page.getByRole('cell',{name:'Alpha ML',exact:false})).toHaveCount(0);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(cards).toContainText('Not recorded');
  await expect(cards.getByText('Not available',{exact:true})).toHaveCount(2);
  await expect(cards).not.toContainText('$0.0000');
  await expect(page.getByRole('combobox',{name:'Loop to inspect'})).toHaveValue('all');
  totalsFail=true;
  await page.getByRole('button',{name:'Refresh telemetry'}).click();
  await page.getByText('Updates delayed',{exact:true}).waitFor();
  await expect(cards).toBeVisible();
  totalsFail=false;
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(page.getByText('Updates delayed',{exact:true})).toHaveCount(0);
  await page.getByRole('combobox',{name:'Detailed records'}).selectOption('Experiments');
  await page.getByRole('combobox',{name:'Experiment',exact:true}).waitFor();
  await expect(page.getByRole('combobox',{name:'Pipeline to inspect'})).toBeDisabled();
  await expect(page.getByRole('combobox',{name:'Loop to inspect'})).toBeDisabled();
  const before=registryReads;
  await page.getByRole('button',{name:'Refresh telemetry'}).click();
  await expect.poll(()=>registryReads).toBeGreaterThan(before);
  await page.getByRole('combobox',{name:'Experiment',exact:true}).selectOption('fixture-experiment');
  await page.getByRole('button',{name:'Inspect',exact:true}).click();
  await page.getByRole('combobox',{name:'Experiment',exact:true}).selectOption('other-experiment');
  await page.getByRole('button',{name:'Inspect',exact:true}).click();
  await page.getByRole('heading',{name:'experiment-b',exact:true}).waitFor();
  await new Promise(resolve=>setTimeout(resolve,900));
  await expect(page.getByRole('heading',{name:'experiment-a',exact:true})).toHaveCount(0);
  await page.goto(root+'/tests/telemetry-workspace.fixture.html?empty=1');
  await page.getByRole('heading',{name:'Choose an execution',exact:true}).waitFor();
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);assert.deepEqual(billing,[]);
  console.log('Telemetry: six widths, dark theme, all eight views, partial/missing usage, lazy evidence, loop navigation, pending/error/retry, late response isolation, global registry refresh and empty selection passed. No writes or billing queries.');
}catch(error){if(page&&process.env.MEMSTARA_SCREENSHOT_DIR)await page.screenshot({path:`${process.env.MEMSTARA_SCREENSHOT_DIR}/telemetry-failure-${process.env.MEMSTARA_BROWSER||'chromium'}-${process.env.MEMSTARA_BROWSER_ZOOM||1}.png`});console.error(JSON.stringify({errors,screen:await page?.locator('body').innerText()},null,2));throw error;}
finally{await browser.close();}
