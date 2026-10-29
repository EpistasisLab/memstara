import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const caps={supports_temperature:true,supports_effort:false,effort_levels:[],default_effort:null};
const browser=await launchResponsiveBrowser();
try {for(const width of [390,1280]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[],submitted=[];page.on('pageerror',e=>errors.push(e.message));
  let saved=null, unavailable=false;
  await page.route('**/control/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/control/model-defaults')return route.fulfill({json:{profiles:[],current_allowed:!!saved&&!unavailable,setup_required:!saved||unavailable,...(unavailable?{current_error:'Saved current model is unavailable. Set up and check a model again.'}:saved?{source:'saved_connection',connection:saved}:{})}});
    if(path==='/control/model-catalog')return route.fulfill({json:{source:'motoro',version:'test',providers:[{id:'azure_foundry',label:'Azure Foundry',custom_model_name:true,can_list_models:false,models:[{id:'openai:gpt-4o',model:'gpt-4o',label:'GPT-4o',capabilities:caps}]}],controls:{temperature:{default:.7,minimum:0,maximum:2},max_tokens:{default:4096,exclusiveMinimum:0,maximum:200000}}}});
    if(path==='/control/model-capabilities')return route.fulfill({json:{capabilities:caps}});
    if(path==='/control/model-connections/check'){
      const body=route.request().postDataJSON();submitted.push(body);
      if(body.api_key==='bad-key')return route.fulfill({status:400,json:{error:'Authentication failed'}});
      saved={id:'b'.repeat(32),provider:body.provider,model:body.model,api_base:body.api_base,settings:body.settings};
      return route.fulfill({status:201,json:{connection:saved}});
    }
    return route.fulfill({json:{llm:{},stage_models:{},inputs:[{id:'manual-data',input_checks_passed:true,configuration:{name:'Manual dataset',dataset_path:'/data.csv',knowledge_mode:'llm_only',data_mode:'dataset',target:{column:'outcome',positive_label:'1',negative_label:'0'},excluded_columns:[],missing_policy:'reject'}}],models:[],skills:[]}});
  });
  await page.goto(`${process.env.MEMSTARA_FIXTURE_URL??'http://127.0.0.1:4177'}/tests/responsive-scroll.fixture.html`);
  const dialog=page.getByRole('dialog'),settings=dialog.locator('.experiment-model-settings');
  await expect(settings.getByRole('radio',{name:/Set up a model/})).toBeChecked();
  await expect(settings.getByRole('radio',{name:/Use current model/})).toBeDisabled();
  await expect(settings).toContainText('No server model is ready');
  await dialog.getByRole('button',{name:'Use Manual dataset',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeDisabled();
  await expect(settings.locator('#experiment-model-choice')).toHaveCount(0);
  await settings.locator('#experiment-model-id').fill('my-deployment');
  await settings.locator('#experiment-model-endpoint').fill('https://fixture.services.ai.azure.com');
  await expect(settings.getByRole('button',{name:'Check & use model'})).toBeDisabled();
  await settings.locator('#experiment-api-key').fill('synthetic-key');
  await settings.getByRole('button',{name:'Check & use model'}).click();
  await expect(settings).toContainText('Model ready');
  await expect(settings.getByRole('radio',{name:/Use current model/})).toBeChecked();
  await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeEnabled();
  assert.equal(submitted.length,1);assert.equal(submitted[0].model,'my-deployment');
  assert.equal(submitted[0].api_key,'synthetic-key');
  assert(await settings.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  // A fresh wizard restores the server's checked connection, even with an empty .env.
  await page.reload();
  await expect(settings.getByRole('radio',{name:/Use current model/})).toBeChecked();
  await expect(settings).toContainText('my-deployment');
  await expect(settings.locator('#experiment-api-key')).toHaveCount(0);
  await dialog.getByRole('button',{name:'Use Manual dataset',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeEnabled();
  assert.equal(submitted.length,1); // Restoring a model makes no extra provider check.
  // A failed replacement leaves the last checked model usable.
  await settings.getByRole('radio',{name:/Set up a model/}).check();
  await expect(settings.locator('#experiment-model-choice')).toHaveCount(0);
  await settings.locator('#experiment-model-id').fill('bad-deployment');
  await settings.locator('#experiment-model-endpoint').fill('https://fixture.services.ai.azure.com');
  await settings.locator('#experiment-api-key').fill('bad-key');
  await settings.getByRole('button',{name:'Check & use model'}).click();
  await expect(settings.getByRole('alert')).toContainText('Authentication failed');
  await settings.getByRole('radio',{name:/Use current model/}).check();
  await expect(settings).toContainText('my-deployment');
  await dialog.getByRole('button',{name:'Choose skills',exact:true}).click();
  for(const name of ['Next: Data','Next: Machine learning','Next: Interpretation','Next: Explanation','Review plan'])await dialog.getByRole('button',{name,exact:true}).click();
  await dialog.getByLabel('Name',{exact:true}).fill('Remembered model');
  await dialog.getByRole('checkbox',{name:/I reviewed/}).check();
  await dialog.getByRole('button',{name:'Create combination design'}).click();
  const created=JSON.parse(await page.locator('body').getAttribute('data-created'));
  assert.equal(created.configuration.model_connection_id,saved.id);
  assert(!JSON.stringify(created).includes('synthetic-key'));
  // Missing saved records require setup instead of silently selecting another model.
  unavailable=true;await page.reload();
  await expect(settings.getByRole('radio',{name:/Set up a model/})).toBeChecked();
  await expect(settings.getByRole('radio',{name:/Use current model/})).toBeDisabled();
  await expect(settings).toContainText('Saved current model is unavailable');
  assert.deepEqual(errors,[]);await page.close();
}}finally{await browser.close();}
