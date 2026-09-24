import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:8070');
  await page.getByRole('button',{name:'Clinician view',exact:true}).click();
  await page.getByTestId('clinician-view').waitFor();
  assert.equal(await page.locator('.react-flow').count(),0);
  const runs=await page.evaluate(async()=> (await (await fetch('/api/runs')).json()).runs);
  const run=runs.find(r=>r.done>0);assert(run,'A completed analysis is needed for this read-only verification');
  await page.getByRole('combobox',{name:'Clinical analysis'}).selectOption(run.run_tag);
  await page.getByRole('article',{name:'Selected hypothesis evidence'}).waitFor();
  await page.getByRole('textbox',{name:'Search clinical findings'}).fill('definitely-no-matching-feature-xyz');
  await page.getByText('No findings match your search.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('article',{name:'Selected hypothesis evidence'}).count(),0);
  await page.getByRole('textbox',{name:'Search clinical findings'}).fill('');
  await page.getByRole('article',{name:'Selected hypothesis evidence'}).waitFor();
  await page.screenshot({path:'/tmp/memstara-clinician.png'});
  const download=page.getByRole('button',{name:'Download report (.md)',exact:true});
  if(await download.isEnabled()) {
    const [artifact]=await Promise.all([page.waitForEvent('download'),download.click()]);
    assert(artifact.suggestedFilename().endsWith('_report.md'));
  }
  await page.reload();
  await page.getByTestId('clinician-view').waitFor();
  assert.equal(await page.getByRole('combobox',{name:'Clinical analysis'}).inputValue(),run.run_tag);
  const fixture=await page.evaluate(async tag=>await(await fetch(`/api/snapshot?run_tag=${encodeURIComponent(tag)}`)).json(),run.run_tag);
  fixture.report={status:'pending',text:''};fixture.stale=true;
  fixture.results=[{...fixture.results[0],auc:null,interpretation:'',evaluation:{explanation:{review_status:'reviewer original required'}}}];
  await page.route('**/api/snapshot*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixture)}));
  await page.reload();
  await page.getByText('No report recommendation is available yet.',{exact:false}).waitFor();
  await page.getByText('reviewer original required: the explainability specification is provisional and must be replaced with reviewer’s original material.',{exact:true}).waitFor();
  await page.getByText('Updates interrupted.',{exact:false}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(500);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Mobile page must not overflow horizontally');
  await page.getByRole('combobox',{name:'Clinical analysis'}).selectOption('');
  await page.getByRole('heading',{name:'Choose an analysis to review',exact:true}).waitFor();
  assert.equal(await page.getByRole('article',{name:'Selected hypothesis evidence'}).count(),0);
  await page.getByRole('button',{name:'Research workspace',exact:true}).click();
  await page.getByRole('button',{name:'Clinician view',exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: clinician navigation, real evidence, search, Markdown export, refresh persistence, mobile layout, empty state and research return. No analysis started.');
} finally {await browser.close();}
