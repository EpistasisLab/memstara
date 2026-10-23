import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
const browser=await launchResponsiveBrowser();
const root=process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177';
try{for(const [width,height,theme] of [[1440,900,'light'],[390,700,'light'],[390,500,'dark'],[768,700,'dark']]){
 const page=await browser.newPage({viewport:{width,height}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/control/**',r=>r.fulfill({json:{inputs:[],models:[],skills:[]}}));
 await page.goto(root+'/tests/responsive-scroll.fixture.html');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:/Agent skills/}).click();
 const stages=['Hypothesis','Data','Machine learning','Interpretation','Explanation'];
 for(let i=0;i<5;i++){
  await expect(dialog.locator('.comb-guidance')).toContainText(`Agent ${i+1} of 5`);
  await expect(dialog.locator('#comb-next-help')).toContainText(`Select at least one ${stages[i]} skill.`);
  await expect(dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+stages[i+1],exact:true})).toBeDisabled();
  await dialog.locator('.comb-skill-card input').first().waitFor({state:'visible'});await dialog.locator('.comb-skill-card input').first().check();await expect(dialog.locator('#comb-next-help')).toContainText('Ready to continue');
  await dialog.getByRole('button',{name:i===4?'Review plan':'Next: '+stages[i+1],exact:true}).click();
 }
 await expect(dialog.getByRole('heading',{name:'Review your design'})).toBeVisible();
 await expect(dialog.locator('.comb-review-agents>li')).toHaveCount(5);
 await expect(dialog.locator('#comb-next-help')).toContainText('Enter a name');
 await dialog.getByLabel('Name',{exact:true}).fill('Reviewed design');
 const limit=dialog.getByLabel('Replicates per pipeline',{exact:true});await limit.fill('4');
 const consent=dialog.getByRole('checkbox',{name:/I reviewed/});const create=dialog.getByRole('button',{name:'Create combination design'});
 await expect(create).toBeDisabled();await consent.check();await expect(create).toBeEnabled();
 await dialog.getByRole('checkbox',{name:/Random Start/}).check();await expect(consent).not.toBeChecked();
 await dialog.getByRole('button',{name:'Edit Data skills',exact:true}).click();
 await dialog.locator('.comb-skill-card input').first().waitFor({state:'visible'});await expect(dialog.locator('.comb-skill-card input').first()).toBeChecked();
 await dialog.locator('.comb-skill-card input').nth(1).check();
 await dialog.getByRole('button',{name:/Review & create/}).click();await expect(consent).not.toBeChecked();await expect(limit).toHaveValue('4');
 await dialog.getByRole('button',{name:'Edit model settings'}).click();await expect(dialog.locator('.comb-ml-settings')).toBeVisible();
 await dialog.getByRole('button',{name:/Review & create/}).click();
 for(const invalid of ['0','1.5','10001','']){await limit.fill(invalid);await consent.check();await expect(create).toBeDisabled();}
 await limit.fill('4');await consent.check();await expect(create).toBeEnabled();
 assert(await dialog.evaluate(d=>d.scrollWidth<=d.clientWidth+2),'Review horizontal overflow');
 await dialog.locator('.comb-step-content').evaluate(e=>e.scrollTop=0);
 await page.screenshot({path:join(tmpdir(),`combination-review-${width}-${height}-${theme}.png`)});
 await create.focus();await expect(create).toBeInViewport();await page.keyboard.press('Enter');
 const saved=JSON.parse(await page.locator('body').getAttribute('data-created'));
 assert.equal(saved.name,'Reviewed design');assert.equal(saved.configuration.waves,8);assert.equal(saved.configuration.combination_random_start,true);assert.equal(saved.configuration.combination_skills.data.length,2);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({width,height,theme,review:true,editRetainsSettings:true,confirmation:true,savedConfiguration:true}));await page.close();
}}finally{await browser.close();}
