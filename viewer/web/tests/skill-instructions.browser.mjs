import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.setDefaultTimeout(15000);
  const roles=['hypothesis','data','ml','interpreter','report'];
  const catalog=roles.map(stage=>({id:`${stage}-fixture`,stage,title:`${stage} fixture`,hash:`current-${stage}`,
    description:`Description for ${stage}`,content:`# Current ${stage}\nCURRENT_ONLY_${stage}`,source:'fixture'}));
  const agents=catalog.map(s=>({...s,hash:`recorded-${s.stage}`}));
  const pipeline={id:'skill-inspection',number:1,name:'Skill inspection fixture',
    configuration:{combination_skills:Object.fromEntries(catalog.map(s=>[s.stage,[s.id]])),combination_repetitions:1},
    running:null,latest:{run_tag:'saved-run',exit_code:0},progress:{iteration:1}};
  let unavailable=false,requests=0;
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>r.fulfill({status:503,json:{error:'Offline fixture'}}));
  await page.route('**/control/**',r=>{
    assert.equal(r.request().method(),'GET');
    const u=new URL(r.request().url());
    if(u.pathname.endsWith('/skill-instructions')) {
      requests++;
      if(unavailable)return r.fulfill({status:404,json:{error:'Recorded instructions unavailable in fixture'}});
      const stage=u.searchParams.get('stage');
      assert.equal(u.searchParams.get('hash'),`recorded-${stage}`);
      return r.fulfill({json:{run_tag:'saved-run',stage,id:`${stage}-fixture`,hash:`recorded-${stage}`,
        prompt_hash:'saved-prompt-hash',content:`# Recorded ${stage}\nORIGINAL_ONLY_${stage}`}});
    }
    if(u.pathname.endsWith('/combinations'))return r.fulfill({json:{run_tag:'saved-run',planned:{combination:1,repetition:1,agents},calls:[]}});
    if(u.pathname==='/control/pipelines')return r.fulfill({json:{pipelines:[pipeline]}});
    if(u.pathname==='/control/playbooks')return r.fulfill({json:{catalog,stages:roles}});
    return r.fulfill({json:{}});
  });
  await page.goto(process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4183');
  await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();
  const studio=page.getByRole('region',{name:'Combination design',exact:true});
  await expect(studio.locator('.cf-desk.is-selected')).toHaveCount(5);
  for(const stage of roles) {
    await studio.getByRole('combobox',{name:'Focus floor plan agent',exact:true}).selectOption(stage);
    await studio.getByRole('button',{name:`Inspect ${stage} fixture instructions`,exact:true}).click();
    const dialog=page.getByRole('dialog',{name:`${stage} fixture`,exact:true});
    await expect(dialog.getByText(`ORIGINAL_ONLY_${stage}`,{exact:true})).toBeVisible();
    await expect(dialog.getByText(`CURRENT_ONLY_${stage}`,{exact:true})).not.toBeVisible();
    await dialog.getByText('View current library instructions',{exact:true}).click();
    await expect(dialog.getByText(`CURRENT_ONLY_${stage}`,{exact:true})).toBeVisible();
    await page.keyboard.press('Escape');
  }
  unavailable=true;
  await studio.getByRole('button',{name:'Inspect report fixture instructions',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'report fixture',exact:true});
  await expect(dialog.getByRole('alert')).toContainText('Recorded instructions unavailable');
  await dialog.getByText('View current library instructions',{exact:true}).click();
  await expect(dialog.getByText('CURRENT_ONLY_report',{exact:true})).toBeVisible();
  unavailable=false;await dialog.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(dialog.getByText('ORIGINAL_ONLY_report',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Skill architecture',exact:true}).click();
  const before=requests;
  for(const stage of roles) {
    await page.getByRole('combobox',{name:'Filter agent role',exact:true}).selectOption(stage);
    await studio.getByRole('button',{name:`Read ${stage} fixture skill`,exact:true}).click();
    await expect(page.getByRole('dialog').getByText(`CURRENT_ONLY_${stage}`,{exact:true})).toBeVisible();
    await page.keyboard.press('Escape');
  }
  assert.equal(requests,before,'Current catalog inspection must not request historical instructions');
  assert.deepEqual(errors,[]);
  console.log('All five roles: recorded versions, current versions, unavailable history and retry passed.');
} finally {await browser.close();}
