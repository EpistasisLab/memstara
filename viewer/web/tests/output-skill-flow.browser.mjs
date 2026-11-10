import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const roles=['hypothesis','data','ml','interpreter','report'];
const skills=Object.fromEntries(roles.map(stage=>[stage,Array.from({length:stage==='hypothesis'?4:2},(_,i)=>({id:`${stage}-${i}`,title:`Recorded ${stage} ${i}`,hash:`saved-${stage}-${i}`}))]));
const plan={skills,combinations:64,total_loops:128,repetitions:2};
const catalog=roles.flatMap(stage=>skills[stage].map(skill=>({...skill,stage,
  description:`Exact saved description for ${skill.id}.`,content:`# ${skill.title}\n\nFull skill instructions.`,source:'fixture',
  ...(stage==='hypothesis'?{hash:'new-unrelated-version',description:'WRONG CURRENT DESCRIPTION'}:{})})));
const results=[1,2,65].map(loop=>({result_id:loop,trial:loop-1,iteration:loop,run_tag:'parent',
  interpretation:'Saved interpretation',columns_used:['age','treatment','HIV_DETECTABLE'],y_column:'HIV_DETECTABLE',auc:.690,model:'Logistic regression'}));
const snapshot={run_tag:'head',run_configuration:{trials:1,waves:128,combination_plan:{...plan,skills:{...skills,hypothesis:[{id:'new-head-skill',hash:'new'}]}}},
  skill_configurations:{parent:{combination_plan:plan,books:{}}},results,
  report:{run_tags:['parent','head'],explanation_outputs:results.map(result=>({loop:result.iteration,run_tag:'parent',result_id:result.result_id,status:'completed',text:'Saved explanation'}))},
  stale:false,health:{memstara:{up:true},core:{up:true}},board:{tasks:[]},scene:{places:[],agents:[],flashes:[]},agents:[],feed:[],access:{rows:[],windows:[]},runs:[]};
const browser=await launchResponsiveBrowser();
try {
  for(const width of [390,1440]) {
    const page=await browser.newPage({viewport:{width,height:1000}});
    const requests=[],errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/control/**',route=>route.fulfill({json:{pipelines:[],skills:[]}}));
    await page.route('**/control/runs/*/skill-instructions?*',route=>{
      const url=new URL(route.request().url());requests.push(url);
      return route.fulfill({json:{run_tag:'parent',stage:url.searchParams.get('stage'),id:url.searchParams.get('skill'),
        hash:url.searchParams.get('hash'),content:'# Original skill\n\nOriginal frozen hypothesis description.'}});
    });
    await page.route('**/api/**',route=>route.fulfill({json:{}}));
    await page.goto(`${process.env.TEST_BASE_URL??'http://127.0.0.1:4177'}/tests/execution-tiles.fixture.html`);
    await page.evaluate(({snapshot,catalog})=>{window.deliverOutputCatalog(catalog);window.deliverOutputs(snapshot);},{snapshot,catalog});
    const tiles=page.locator('.execution-output-tile');
    await expect(tiles).toHaveCount(3);
    const tile=tiles.first();
    await expect(tile.locator('.output-tile-overview')).toContainText('0.690');
    await expect(tile.locator('.output-tile-overview')).toContainText('Predictors:');
    await expect(tile.locator('.output-tile-overview > div:last-child dd')).toHaveText('2');
    await expect(tile.locator('.output-tile-overview')).not.toContainText('HIV_DETECTABLE');
    await expect(tile.locator('.output-skill-dot.is-selected')).toHaveCount(5);
    const hypothesisOptions=tile.locator('.output-skill-stage').first();
    await expect(hypothesisOptions.locator('.output-skill-dot')).toHaveCount(4);
    await expect(hypothesisOptions.locator('.output-skill-dot.is-selected')).toHaveCount(1);
    await expect(hypothesisOptions.locator('.output-skill-dot:not(.is-selected)')).toHaveCount(3);
    assert.equal(await hypothesisOptions.locator('.is-selected > span').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(0, 0, 0)');
    for(const removed of ['Pipeline','Ready','Recorded parameters','Prediction:','Agent skills','Other option','View results']) {
      assert(!(await tile.innerText()).includes(removed),`${removed} must not appear on the sketch tile`);
    }
    await expect(tile.locator('.output-tile-footer')).toHaveText('Rep: 1');
    assert.deepEqual(await tile.locator('.output-skill-stage-label').allTextContents(),['H','D','ML','I','E']);
    assert.equal(requests.length,0,'Do not fetch instructions for every tile on page load');
    const descriptions=['Generates a testable research hypothesis.','Selects and prepares predictors for evaluation.',
      'Trains and evaluates predictive models.','Interprets model results and feature contributions.','Explains findings in the study context.'];
    for(let index=0;index<5;index++) {
      const label=tile.locator('.output-skill-stage-label').nth(index);
      await label.hover();
      await expect(page.locator('.output-agent-role-popup')).toContainText(descriptions[index]);
      await page.keyboard.press('Escape');await page.mouse.move(0,0);
    }
    const roleLabel=tile.locator('.output-skill-stage-label').first();
    await roleLabel.focus();
    await expect(page.locator('.output-agent-role-popup')).toContainText(descriptions[0]);
    await page.keyboard.press('Escape');await roleLabel.blur();
    await roleLabel.click();
    await expect(page.locator('.output-agent-role-popup')).toContainText(descriptions[0]);
    await expect(tiles).toHaveCount(3);
    assert.equal(requests.length,0,'Agent roles are local descriptions, not saved skill requests');
    await page.keyboard.press('Escape');await roleLabel.blur();await page.mouse.move(0,0);
    const hypothesis=tile.getByRole('button',{name:/Hypothesis: Recorded hypothesis 0/});
    await hypothesis.hover();
    const popup=page.locator('.output-skill-popup');
    await expect(popup).toContainText('Original frozen hypothesis description.');
    await expect(popup).not.toContainText('WRONG CURRENT DESCRIPTION');
    await expect(tiles).toHaveCount(3);
    assert.equal(requests.length,1);
    assert.equal(requests[0].pathname,'/control/runs/parent/skill-instructions');
    assert.equal(requests[0].searchParams.get('hash'),'saved-hypothesis-0');
    await popup.hover();await expect(popup).toBeVisible();
    await page.keyboard.press('Escape');await expect(popup).toHaveCount(0);
    await page.mouse.move(0,0);await hypothesis.hover();
    await expect(popup).toContainText('Original frozen hypothesis description.');
    assert.equal(requests.length,1,'Reuse the verified frozen response');
    await page.keyboard.press('Escape');await page.mouse.move(0,0);
    // Keyboard and touch/click access must not open the result tile.
    const data=tile.getByRole('button',{name:/Data: Recorded data 0/});
    await data.scrollIntoViewIfNeeded();
    await data.focus();
    await expect(popup).toContainText('Exact saved description for data-0.');
    await page.keyboard.press('Escape');await data.blur();
    await data.click();
    await expect(popup).toBeVisible();
    await expect(tiles).toHaveCount(3);
    for(const theme of ['light','dark']) {
      await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
      await expect(popup).toBeVisible();
      const colors=await tile.evaluate(el=>{
        const chosen=el.querySelector('.output-skill-dot.is-selected > span');
        const hollow=el.querySelector('.output-skill-dot:not(.is-selected) > span');
        return {selected:getComputedStyle(chosen).backgroundColor,hollow:getComputedStyle(hollow).backgroundColor,
          border:getComputedStyle(hollow).borderTopColor,panel:getComputedStyle(el).backgroundColor};
      });
      const luminance=color=>color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{const s=v/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
      const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
      assert.equal(colors.hollow,colors.panel,'Unselected dots remain hollow in both themes');
      assert(contrast(colors.selected,colors.panel)>=4.5,'Selected dot must stand out from the tile');
      assert(contrast(colors.border,colors.panel)>=3,'Hollow dot outline must remain visible');
      const bounds=await popup.boundingBox();assert(bounds.x>=0 && bounds.x+bounds.width<=width+1);
      assert.equal(await page.evaluate(()=>document.body.scrollWidth>innerWidth+2),false);
      await page.screenshot({path:join(tmpdir(),`output-skill-flow-${width}-${theme}.png`),fullPage:true});
    }
    await popup.locator('summary').click();
    await expect(popup).toContainText('Full skill instructions.');
    await expect(popup).toBeVisible();
    await page.keyboard.press('Escape');
    await tile.screenshot({path:join(tmpdir(),`output-sketch-tile-${width}.png`)});
    await page.getByRole('navigation',{name:'Output views'}).getByRole('button',{name:'Conclusions',exact:true}).click();
    await expect(tiles.first().locator('.output-skill-dot.is-selected')).toHaveCount(5);
    // A missing archived response never falls back to today's content.
    await page.route('**/control/runs/*/skill-instructions?*',route=>route.fulfill({status:404,json:{error:'not saved'}}));
    const missing=structuredClone(snapshot);missing.results[0].evaluation={skills:{hypothesis:['unarchived']}};
    await page.getByRole('navigation',{name:'Output views'}).getByRole('button',{name:'Results',exact:true}).click();
    await page.evaluate(s=>window.deliverOutputs(s),missing);
    await tiles.first().getByRole('button',{name:/Hypothesis: unarchived/}).hover();
    await expect(popup).toContainText('version is not verified');
    await expect(popup).not.toContainText('WRONG CURRENT DESCRIPTION');
    await page.keyboard.press('Escape');await page.mouse.move(0,0);
    const unavailable=structuredClone(snapshot);
    unavailable.skill_configurations.parent.combination_plan.skills.hypothesis[0].hash=`unavailable-${width}`;
    await page.evaluate(s=>window.deliverOutputs(s),unavailable);
    await tiles.first().getByRole('button',{name:/Hypothesis: Recorded hypothesis 0/}).hover();
    await expect(popup).toContainText('Recorded skill instructions are unavailable.');
    await expect(popup).not.toContainText('WRONG CURRENT DESCRIPTION');
    assert.deepEqual(errors,[]);
    console.log(`PASS ${width}px: frozen role selections, retained source, lazy cached hover, keyboard/click, both themes, missing version and no tile navigation`);
    await page.close();
  }
} finally {await browser.close();}
