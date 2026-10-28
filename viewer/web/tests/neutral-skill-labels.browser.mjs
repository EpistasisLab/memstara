import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
const browser=await launchResponsiveBrowser();
const errors=[],writes=[];
try {
  const p=await browser.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(12000);
  p.on('pageerror',e=>errors.push(e.message));
  await p.route(/\/(api|control)\//,async r=>{
    const u=new URL(r.request().url());
    if(r.request().method()!=='GET'){
      assert.equal(u.pathname,'/control/pipelines');
      const body=r.request().postDataJSON();assert.equal(body.action,'update');assert.equal(body.id,'neutral');writes.push(body);
      return r.fulfill({json:{}});
    }
    if(u.pathname==='/api/motoro/execution')return r.fulfill({json:{calls:[{run_id:'invocation',stage:'interpreter',loop:1,seq:1,record:{status:'completed'}}],note:'Recorded model usage'}});
    if(u.pathname==='/api/motoro/run')return r.fulfill({json:{record:{input:{skill:'shared-shap',description:"Anil's instructions"},output:{auc:.731,cost:.11321064},started_at:'2026-10-22T12:00:00Z',completed_at:'2026-10-22T12:01:00Z'}}});
    if(u.pathname==='/api/developer/steps')return r.fulfill({json:{steps:[],next_offset:null}});
    return r.fulfill({status:503,json:{error:'No server in this fixture'}});
  });
  await p.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/neutral-skill-labels.fixture.html');
  const assertNeutral=async()=>{
    const visible=await p.evaluate(()=>[document.body.innerText,...[...document.querySelectorAll('[title],[aria-label]')].filter(e=>e.getClientRects().length).flatMap(e=>[e.getAttribute('title')||'',e.getAttribute('aria-label')||''])].join('\n'));
    assert(!/(?:anil|\bphil\b|\bjason\b)/i.test(visible),visible);
  };
  const before=await p.evaluate(()=>window.originalFixture());
  await p.getByRole('button',{name:'Skill architecture',exact:true}).click();
  for(const name of ['SHAP Interpretation','LIME Interpretation','Addiction Expert Explanation','HIV Expert Explanation']){
    await p.getByRole('button',{name:`Read ${name} skill`,exact:true}).click();
    const dialog=p.getByRole('dialog',{name,exact:true});await dialog.locator('.cs-markdown').waitFor();
    await expect(dialog).toContainText('Neutrophil');
    await dialog.getByText('File and version details',{exact:true}).click();await assertNeutral();
    await expect(dialog.getByRole('link',{name:'contributor reference'})).toHaveAttribute('href','https://example.org/anil_shared/SHAP.md');
    await p.keyboard.press('Escape');
  }
  await p.getByRole('button',{name:'Edit interpretation',exact:true}).click();
  const editor=p.getByRole('dialog');
  await expect(editor.getByLabel('Custom skill Markdown file')).toHaveCount(0);
  await expect(editor.getByRole('button',{name:'Write a custom skill'})).toHaveCount(0);
  await editor.getByLabel('Choose a skill').selectOption('shared-lime');
  await editor.getByText('Read full instructions and source',{exact:true}).click();
  await assertNeutral();
  await editor.getByRole('button',{name:'Save settings',exact:true}).click();
  await expect(editor).toHaveCount(0);
  assert.equal(writes.length,1);assert.equal(writes[0].configuration.playbook_interpreter,'shared-lime');
  const after=await p.evaluate(()=>window.originalFixture());
  assert.deepEqual(after.catalog,before.catalog,'Rendering must not mutate original skill text or hashes');
  assert.equal(after.configuration.playbook_interpreter,'shared-lime');
  for(const view of ['Results','Activity','Records']){
    await p.getByRole('navigation',{name:'Fixture views'}).getByRole('button',{name:view,exact:true}).click();
    if(view==='Results')await p.getByRole('article',{name:'Selected interpretation outputs'}).waitFor();
    if(view==='Records')await p.getByRole('combobox',{name:'Motoro agent invocation'}).selectOption('invocation');
    if(view==='Records')await p.getByText('Run input, output, state and configuration',{exact:true}).click();
    await p.locator('main details').evaluateAll(nodes=>nodes.forEach(e=>e.open=true));
    if(view==='Activity')await expect(p.locator('.compact-activity-detail')).toHaveCount(2);
    if(view==='Records')await expect(p.locator('main')).toContainText('0.11321064');
    if(view==='Results')await expect(p.getByRole('article',{name:'Selected interpretation outputs'})).toContainText("Anil's instructions adapted by Phil.");
    for(const width of [1440,390]){
      await p.setViewportSize({width,height:1000});if(view!=='Results')await assertNeutral();
    }
  }
  assert.deepEqual(errors,[]);
  console.log('Neutral skill cards, instructions, dialog provenance, results, Markdown, activity and Motoro previews passed. Original IDs, source links, skill hashes, metrics and save payload preserved. No model calls.');
} finally {await browser.close();}
