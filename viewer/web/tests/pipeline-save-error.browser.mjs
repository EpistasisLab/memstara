import {preparedInputs,fixtureSkillId} from './current-research.fixture.mjs';
import {openBuildModeFixture} from './build-mode.fixture.mjs';
// Save failure must survive successful background polling; all writes mocked.
import {chromium} from '@playwright/test';
const b=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try{const p=await b.newPage({viewport:{width:1400,height:1000}});let items=[],starts=[],rejected=false,polls=0;
await p.addInitScript(()=>localStorage.setItem('memstara-draft-v1',JSON.stringify({stage_models:{qwen:{provider:'openai',model:'qwen-old'},sonnet:{provider:'azure_foundry',model:'sonnet-old'}}})));
await p.route('**/control/**',async r=>{const path=new URL(r.request().url()).pathname;
  if(path==='/control/research-inputs')return r.fulfill({json:preparedInputs});
if(path==='/control/playbooks'){const stages=['hypothesis','data','ml','interpreter','report'];const catalog=stages.map(stage=>({id:fixtureSkillId(stage),stage,title:stage+' test skill',content:'# Test instructions',hash:stage,description:'Synthetic fixture',source:'fixture'}));return r.fulfill({json:{catalog,stages,playbooks:catalog.map(s=>s.id),references:[],max_hypotheses:4}});}
if(path==='/control/pipelines'){if(r.request().method()==='GET'){polls++;return r.fulfill({json:{pipelines:items}});}if(!rejected){rejected=true;return r.fulfill({status:409,json:{error:'Configuration save failed: fixture conflict'}});}const q=r.request().postDataJSON();if(['provider','model','stage_models'].some(key=>Object.hasOwn(q.configuration,key)))throw Error('Old model assignment leaked into new pipeline');if(Object.keys(q.configuration.combination_skills??{}).length)throw Error('Combination settings leaked');const x={id:'selected-'+(items.length+1),number:items.length+1,name:q.name,configuration:q.configuration,running:null,latest:null,progress:{}};items.push(x);return r.fulfill({json:x});}
if(path==='/control/runs'&&r.request().method()==='POST'){const q=r.request().postDataJSON();starts.push(q.pipeline_id);return r.fulfill({json:{run_tag:'mock-'+q.pipeline_id}});}
if(r.request().method()==='POST')throw Error('Unexpected write');return r.continue();});
await p.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Isolated fixture'}}));
await p.goto(process.env.MEMSTARA_TEST_URL || 'http://localhost:8070');
for(let i=1;i<=1;i++){
await p.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();await p.getByRole('button',{name:/Add experiment/i}).click();await openBuildModeFixture(p);const d=p.getByRole('dialog',{name:'Create a pipeline',exact:true});await d.getByRole('button',{name:'Use CI dataset',exact:true}).click();await d.getByRole('checkbox',{name:/Use .* for this pipeline/}).check();await d.getByRole('button',{name:'Next',exact:true}).click();
for(const label of ['Hypothesis','Data','Machine learning','Interpretation','Explanation']){const c=d.getByRole('combobox',{name:label+' skill',exact:true});const value=await c.inputValue();if(!value){const option=await c.locator('option').evaluateAll(os=>os.find(o=>o.value)?.value);await c.selectOption(option);}await d.getByRole('button',{name:'Next',exact:true}).click();}
await d.getByLabel('Pipeline name',{exact:true}).fill('Selected '+i);await d.getByRole('button',{name:'Next',exact:true}).click();await d.getByRole('button',{name:'Create pipeline',exact:true}).click();const before=polls;
await p.waitForTimeout(4500);
if(polls<=before)throw Error('No successful background poll was observed');
if(await p.getByText(/Configuration save failed: fixture conflict/).count()===0)throw Error('Polling erased the save failure');
await d.getByRole('button',{name:'Create pipeline',exact:true}).click();
await d.waitFor({state:'hidden'});if(starts.length!==i-1)throw Error('Create started execution');}
if(items.length!==1||starts.length)throw Error('Design was not saved independently of execution');
await p.reload();await p.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
await p.getByRole('button',{name:'Run Selected 1',exact:true}).waitFor();
console.log('Save error survived polling; retry saved and reloaded a design without starting it. All requests mocked.');
}finally{await b.close();}
