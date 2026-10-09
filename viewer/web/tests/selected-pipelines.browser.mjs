// Browser regression: all writes mocked, no real execution.
import {chromium} from '@playwright/test';
const b=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{const p=await b.newPage({viewport:{width:1400,height:1000}});let items=[],starts=[];
await p.route('**/control/**',async r=>{const path=new URL(r.request().url()).pathname;
if(path==='/control/playbooks'){const stages=['hypothesis','data','ml','interpreter','report'];const catalog=stages.map(stage=>({id:stage+'-fixture',stage,title:stage+' test skill',content:'# Test instructions',hash:stage,description:'Synthetic fixture',source:'fixture'}));return r.fulfill({json:{catalog,stages,playbooks:catalog.map(s=>s.id),references:[],max_hypotheses:4}});}
if(path==='/control/pipelines'){if(r.request().method()==='GET')return r.fulfill({json:{pipelines:items}});const q=r.request().postDataJSON();if(Object.keys(q.configuration.combination_skills??{}).length)throw Error('Combination settings leaked');const x={id:'selected-'+(items.length+1),number:items.length+1,name:q.name,configuration:q.configuration,running:null,latest:null,progress:{}};items.push(x);return r.fulfill({json:x});}
if(path==='/control/runs'&&r.request().method()==='POST'){const q=r.request().postDataJSON();starts.push(q.pipeline_id);return r.fulfill({json:{run_tag:'mock-'+q.pipeline_id}});}
if(r.request().method()==='POST')throw Error('Unexpected write');return r.continue();});
await p.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Isolated fixture'}}));
await p.goto(process.env.MEMSTARA_TEST_URL || 'http://localhost:8070');
for(let i=1;i<=4;i++){
await p.getByRole('button',{name:/Add pipeline/i}).click();await p.getByRole('button',{name:/Selected Pipelines/}).click();const d=p.getByRole('dialog',{name:'Create a pipeline',exact:true});await d.getByRole('checkbox',{name:/Use .* for this pipeline/}).check();await d.getByRole('button',{name:'Next',exact:true}).click();
for(const label of ['Hypothesis','Data','Machine learning','Interpretation','Explanation']){const c=d.getByRole('combobox',{name:label+' skill',exact:true});const value=await c.inputValue();if(!value){const option=await c.locator('option').evaluateAll(os=>os.find(o=>o.value)?.value);await c.selectOption(option);}await d.getByRole('button',{name:'Next',exact:true}).click();}
await d.getByLabel('Pipeline name',{exact:true}).fill('Selected '+i);await d.getByRole('button',{name:'Next',exact:true}).click();await d.getByRole('button',{name:'Create pipeline',exact:true}).click();await d.waitFor({state:'hidden'});if(starts.length!==i-1)throw Error('Create started execution');const run=p.getByRole('button',{name:'Run Selected '+i,exact:true});
await run.waitFor();
if(!await run.evaluate(e=>!!e.closest('.pipeline-selected-controls')&&!e.closest('.pipeline-browser-list')))throw Error('Run is inside the scrolling list');
await p.locator('.pipeline-browser-list').evaluate(e=>{e.scrollTop=e.scrollHeight;});
const box=await run.boundingBox();if(!box||box.y<0||box.y+box.height>1000)throw Error('Run is offscreen');
await run.click();await p.waitForTimeout(300);if(starts.at(-1)!=='selected-'+i)throw Error('Wrong pipeline started');}
if(items.length!==4)throw Error('Fourth pipeline was not created');
console.log('Four Selected Pipelines created and explicitly started; no automatic starts; all writes mocked.');
}finally{await b.close();}
