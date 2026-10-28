import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';

const browser=await launchResponsiveBrowser();
try {
 for(const width of [390,1280]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/control/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/control/model-defaults')return route.fulfill({json:{profiles:[
    {provider:'openai',model:'unsupported',roles:['ml'],role:'ml',settings:{},credentials_available:true},
   ],current_allowed:false}});
   if(path==='/control/model-catalog')return route.fulfill({json:{source:'motoro',version:'test',providers:[
    {id:'openai',label:'OpenAI',models:[]},
    {id:'azure_foundry',label:'Azure Foundry',custom_model_name:true,can_list_models:false,models:[]},
   ],controls:{temperature:{minimum:0,maximum:2},max_tokens:{default:4096,exclusiveMinimum:0,maximum:200000}}}});
   return route.fulfill({json:{llm:{},stage_models:{},inputs:[{id:'manual-data',input_checks_passed:true,configuration:{name:'Manual dataset',dataset_path:'/data.csv',knowledge_mode:'llm_only',data_mode:'dataset',target:{column:'outcome',positive_label:'1',negative_label:'0'},excluded_columns:[],missing_policy:'reject'}}],models:[],skills:[]}});
  });
  await page.goto(`${process.env.MEMSTARA_FIXTURE_URL??'http://127.0.0.1:4177'}/tests/responsive-scroll.fixture.html`);
  const dialog=page.getByRole('dialog'),settings=dialog.locator('.experiment-model-settings');
  await dialog.getByRole('button',{name:'Use Manual dataset',exact:true}).click();
  await expect(settings.getByRole('radio',{name:/Use current model/})).toBeDisabled();
  await expect(settings.getByRole('alert')).toContainText('Only Azure Foundry');
  await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeDisabled();
  await expect(settings).not.toContainText('unsupported');
  await settings.getByRole('radio',{name:/Set up a model/}).check();
  await expect(settings.locator('#experiment-model-provider')).toBeDisabled();
  await expect(settings.locator('#experiment-model-provider')).toHaveValue('azure_foundry');
  assert.deepEqual(await settings.locator('#experiment-model-provider option').evaluateAll(nodes=>nodes.map(n=>n.value)),['azure_foundry']);
  await expect(settings.getByRole('checkbox',{name:/Use configured credentials/})).toHaveCount(0);
  await expect(settings.locator('#experiment-api-key')).toBeVisible();
  assert(await settings.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
  assert.deepEqual(errors,[]);
  await page.close();
 }
}finally{await browser.close();}
