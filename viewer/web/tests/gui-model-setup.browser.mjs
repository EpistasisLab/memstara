import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const caps={supports_temperature:true,supports_effort:false,effort_levels:[],default_effort:null};
const browser=await launchResponsiveBrowser();
try {for(const width of [390,1280]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[],submitted=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/control/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/control/model-defaults')return route.fulfill({json:{profiles:[],current_allowed:false,setup_required:true}});
    if(path==='/control/model-catalog')return route.fulfill({json:{source:'motoro',version:'test',providers:[{id:'azure_foundry',label:'Azure Foundry',custom_model_name:true,can_list_models:false,models:[{id:'openai:gpt-4o',model:'gpt-4o',label:'GPT-4o',capabilities:caps}]}],controls:{temperature:{default:.7,minimum:0,maximum:2},max_tokens:{default:4096,exclusiveMinimum:0,maximum:200000}}}});
    if(path==='/control/model-connections/check'){
      const body=route.request().postDataJSON();submitted.push(body);
      return route.fulfill({status:201,json:{connection:{id:'b'.repeat(32),provider:body.provider,model:body.model,api_base:body.api_base}}});
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
  await settings.locator('#experiment-model-choice').selectOption('openai:gpt-4o');
  await settings.locator('#experiment-model-id').fill('my-deployment');
  await settings.locator('#experiment-model-endpoint').fill('https://fixture.services.ai.azure.com');
  await expect(settings.getByRole('button',{name:'Check & use model'})).toBeDisabled();
  await settings.locator('#experiment-api-key').fill('synthetic-key');
  await settings.getByRole('button',{name:'Check & use model'}).click();
  await expect(settings).toContainText('Model ready');
  await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeEnabled();
  assert.equal(submitted.length,1);assert.equal(submitted[0].model,'my-deployment');
  assert.equal(submitted[0].api_key,'synthetic-key');
  assert(await settings.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  assert.deepEqual(errors,[]);await page.close();
}}finally{await browser.close();}
