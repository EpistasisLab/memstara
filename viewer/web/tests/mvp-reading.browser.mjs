import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
const result={result_id:1,task_id:1,trial:0,auc:.65,model:'lr',perspective:'Recorded question',hypothesis:'Recorded hypothesis with a deliberately long unbroken identifier '+ 'feature'.repeat(35),interpretation:'## Clinical meaning\n\nRecorded interpretation, not a treatment recommendation.',columns_used:['age'],columns_missing:[],importance:{age:.1},y_column:'target',okf_concept_ids:[],created_at:'2026-10-23T12:00:00Z'};
const snap=(status,tag='alpha-run')=>({run_tag:tag,pipeline:{status},run_configuration:{pipeline_name:tag==='alpha-run'?'Alpha research':'Beta research',trials:1},results:[{...result}],report:{status:'completed',explanation_outputs:[{loop:1,result_id:1,status:'completed',text:`# Saved ${tag} explanation\n\nActual saved output for ${tag}.`}],text:`# Saved ${tag} explanation\n\nActual saved output for ${tag}.\n\n| Finding | Limitation |\n|---|---|\n| Observed association | Independent confirmation needed |`},stale:false,health:{memstara:{up:true},core:{up:true}},scene:{places:[],agents:[],flashes:[]},feed:[],agents:[],access:{rows:[],windows:[]},board:{tasks:[],lanes:{}},runs:[]});
const errors=[],writes=[];
try{
 for(const width of [1440,768,390,320])for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport:{width,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.route(/\/(api|control)\//,r=>{if(r.request().method()!=='GET'){writes.push(r.request().url());return r.abort();}return r.fulfill({status:503,json:{error:'No live services in this fixture'}});});
  await page.goto(root+'/tests/results-notices.fixture.html');await page.waitForFunction(()=>typeof window.deliverResults==='function');
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  const nav=page.getByRole('complementary',{name:'View navigation'});
  const current=name=>expect(nav.getByRole('button',{name,exact:true})).toHaveAttribute('aria-current','page');
  const go=name=>nav.getByRole('button',{name,exact:true}).click();
  const deliver=(value,requested=value.run_tag,error=null)=>page.evaluate(async({value,requested,error})=>{
    window.deliverResults(value,requested,error);
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  },{value,requested,error});
  // Loading historical completed data must not navigate.
  await deliver(snap('completed'));await current('Experiments');
  await deliver(snap('running'));await current('Experiments');
  const stale=snap('completed');stale.stale=true;await deliver(stale);await current('Experiments');
  // A successful live transition opens Results, even for a measured AUC of zero.
  const completed=snap('completed');completed.results[0].auc=0;
  await deliver(completed);await current('Results');
  const interpretation=page.getByRole('region',{name:'Clinical interpretation summary'});
  await expect(interpretation).toContainText('Recorded interpretation');
  const details=page.locator('details.analysis-technical-details').filter({has:page.getByText('Model performance and technical details',{exact:true})});
  await expect(details).not.toHaveAttribute('open','');
  assert(await interpretation.evaluate(e=>e.getBoundingClientRect().bottom<=e.parentElement.querySelector('.analysis-technical-details').getBoundingClientRect().top));
  await details.locator('summary').first().focus();await page.keyboard.press('Enter');
  await expect(details).toHaveAttribute('open','');await expect(details).toContainText('AUC 0.0000');
  await go('Experiments');await deliver(completed);await current('Experiments');
  // Completion in another reading view must not interrupt it.
  await go('Usage');await deliver(snap('running','beta-run'));await deliver(snap('completed','beta-run'));await current('Usage');
  await go('Experiments');await deliver(snap('completed','beta-run'));await current('Experiments');
  await deliver(snap('running','failed-run'));await deliver(snap('failed','failed-run'));await current('Experiments');
  // A mismatched response cannot cause navigation or consume this run's transition.
  await deliver(snap('running','selected-run'));await deliver(snap('completed','other-run'),'selected-run');await current('Experiments');
  await deliver(snap('completed','selected-run'));await current('Results');
  // Pipeline-scoped Explanation text and Markdown download.
  await deliver(snap('completed'));await go('Conclusions');
  const report=page.getByTestId('report-page');await expect(report.locator('[data-report-content]')).toContainText('Actual saved output for alpha-run');
  await expect(report.getByRole('heading',{level:2})).toContainText('Recorded hypothesis');
  const downloadEvent=page.waitForEvent('download');await report.getByRole('button',{name:'Download Markdown'}).click();
  const download=await downloadEvent;assert.equal(download.suggestedFilename(),'alpha-run_loop-1_result-1_conclusions.md');
  const stream=await download.createReadStream();let markdown='';for await(const data of stream)markdown+=data;assert.equal(markdown,snap('completed').report.explanation_outputs[0].text);
  const comparisonOnly=snap('completed');comparisonOnly.report.explanation_outputs=[];await deliver(comparisonOnly);await expect(report.locator('[data-report-content]')).toHaveCount(0);await deliver(snap('completed'));
  const multiple=snap('completed');multiple.report.explanation_outputs.push({loop:2,result_id:2,status:'completed',text:'Second loop exact narrative'});await deliver(multiple);await report.getByRole('combobox',{name:'Saved Explanation'}).selectOption('alpha-run:2:2');await expect(report.locator('[data-report-content]')).toHaveText('Second loop exact narrative');
  await report.getByRole('combobox',{name:'Pipeline conclusions'}).selectOption('beta');
  await deliver(snap('completed','beta-run'));await expect(report.locator('[data-report-content]')).toContainText('Actual saved output for beta-run');
  await expect(report.locator('[data-report-content]')).not.toContainText('Actual saved output for alpha-run');
  const partial=snap('running','beta-run');partial.report.status='partial';partial.report.error='One explanation is pending';
  await deliver(partial);await expect(report).toContainText('Report status: partial');await expect(report).toContainText('One explanation is pending');
  const missing=snap('running','beta-run');missing.report=null;await deliver(missing);await expect(report).toContainText('No Explanation output has been saved');await expect(report.getByRole('button',{name:'Download Markdown'})).toBeDisabled();
  await deliver(snap('completed','beta-run'));
  const geometry=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));assert(geometry.scroll<=geometry.width+1,JSON.stringify({width,theme,geometry}));
  assert(await report.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
  if(process.env.MEMSTARA_SCREENSHOT_DIR)await page.screenshot({path:`${process.env.MEMSTARA_SCREENSHOT_DIR}/mvp-conclusions-${theme}-${width}.png`});
  console.log(JSON.stringify({width,theme,completion:'observed only',interpretation:'first',metrics:'collapsed and readable',reports:'pipeline scoped, download, partial and missing'}));
  await page.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
}finally{await browser.close();}
