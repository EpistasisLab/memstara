import {expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {launchResponsiveBrowser} from './responsive-browser.mjs';
const temperature={supports_temperature:true,supports_effort:false,effort_levels:[],default_effort:null,default_temperature:.7};
const reasoning={supports_temperature:false,supports_effort:true,effort_levels:['low','high'],default_effort:'high'};
const profiles=[
 {role:'question',roles:['question','hypothesis','data','interpretation'],provider:'openai',model:'gpt-4o',api_base:'',region:'',auth_type:'',settings:{temperature:.2,max_tokens:7000},capabilities:temperature,credentials_available:true},
 {role:'explanation',roles:['explanation'],provider:'azure_foundry',model:'clinical-deployment',api_base:'https://clinical.example',region:'',auth_type:'',settings:{effort:'low',max_tokens:11000},capabilities:reasoning,credentials_available:true},
 {role:'ml',roles:['ml'],provider:'azure_foundry',model:'unlisted-deployment',api_base:'https://clinical.example',region:'',auth_type:'',settings:{temperature:1},capabilities:{supports_temperature:null,supports_effort:null,effort_levels:null,default_effort:null},credentials_available:true},
];
const catalog={source:'motoro',version:'test',controls:{temperature:{default:null,minimum:0,maximum:2},max_tokens:{default:4096,exclusiveMinimum:0,maximum:200000}},providers:[
 {id:'openai',label:'OpenAI',custom_model_name:false,can_list_models:true,models:[{id:'openai:gpt-4o',model:'gpt-4o',label:'GPT-4o',capabilities:temperature}]},
 {id:'azure_foundry',label:'Azure Foundry',custom_model_name:true,can_list_models:false,models:[]},
]};
const browser=await launchResponsiveBrowser();
try {for(const width of [320,390,768,1280]) {
 const page=await browser.newPage({viewport:{width,height:1100}});const errors=[];const submitted=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/control/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/control/model-catalog')return route.fulfill({json:catalog});
  if(path==='/control/model-defaults')return route.fulfill({json:{source:'project_env',profiles}});
  if(path==='/control/model-capabilities')return route.fulfill({json:{capabilities:temperature}});
  if(path==='/control/model-connections/models'){
   const payload=route.request().postDataJSON();assert.equal(payload.default_role,'question');assert(!payload.api_key);
   return route.fulfill({json:{models:[],truncated:false}});
  }
  if(path==='/control/model-connections/check'){
   const data=route.request().postDataJSON();submitted.push(data);
   return route.fulfill({status:201,json:{connection:{id:'c'.repeat(32),provider:data.provider,model:data.model,api_base:data.api_base||'',region:'',checked_at:'2026-10-28T00:00:00Z'}}});
  }
  return route.fulfill({json:{llm:{},stage_models:Object.fromEntries(profiles.flatMap(p=>p.roles.map(role=>[role,{provider:p.provider,model:p.model}]))),inputs:[{id:'manual-data',input_checks_passed:true,configuration:{name:'Manual dataset',dataset_path:'/data.csv',knowledge_mode:'llm_only',data_mode:'dataset',target:{column:'outcome',positive_label:'1',negative_label:'0'},excluded_columns:[],missing_policy:'reject'}}],models:[],skills:[]}});
 });
 await page.goto(`${process.env.TEST_BASE_URL??process.env.MEMSTARA_FIXTURE_URL??'http://127.0.0.1:4177'}/tests/responsive-scroll.fixture.html`);
 const dialog=page.getByRole('dialog'),settings=dialog.locator('.experiment-model-settings');
 await expect(settings.getByRole('radio',{name:/Use current model/})).toBeChecked();
 await expect(settings.locator('.experiment-default-card')).toHaveCount(3);
 await expect(settings.locator('.experiment-default-card').first()).toContainText('Interpretation');
 await expect(settings.locator('.experiment-default-card').nth(1)).toContainText('Explanation');
 await settings.locator('.experiment-default-card').nth(1).locator('summary').click();
 await expect(settings.locator('.experiment-default-card').nth(1)).toContainText('https://clinical.example');
 await expect(settings.locator('.experiment-default-card').nth(1)).toContainText('11000');
 await expect(settings.locator('input[type=password]')).toHaveCount(0);
 await dialog.getByRole('button',{name:'Use Manual dataset',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeEnabled();
 await settings.getByRole('radio',{name:/Set up a model/}).check();
 await expect(settings.locator('#experiment-model-provider')).toHaveValue('openai');
 await expect(settings.locator('#experiment-model-choice')).toHaveValue('openai:gpt-4o');
 await expect(settings.getByRole('checkbox',{name:/Use configured credentials/})).toBeChecked();
 await expect(settings.locator('#experiment-api-key')).toHaveCount(0);
 await settings.locator('.experiment-model-advanced summary').click();
 await expect(settings.locator('#experiment-temperature')).toHaveValue('0.2');
 await expect(settings.locator('#experiment-max-tokens')).toHaveValue('7000');
 await settings.getByRole('button',{name:'Load provider models'}).click();
 await expect(settings.locator('.experiment-model-listing')).toContainText('0 models loaded');
 await settings.getByRole('button',{name:'Check & use model'}).click();
 await expect(settings).toContainText('Model ready');
 assert.equal(submitted[0].default_role,'question');assert(!submitted[0].api_key);
 assert.deepEqual(submitted[0].settings,{temperature:.2,max_tokens:7000});
 await expect(dialog.getByRole('button',{name:'Choose skills',exact:true})).toBeEnabled();
 await settings.getByRole('button',{name:'Change',exact:true}).click();
 await settings.locator('#experiment-default-profile').selectOption('explanation');
 await expect(settings.locator('#experiment-model-provider')).toHaveValue('azure_foundry');
 await expect(settings.locator('#experiment-model-id')).toHaveValue('clinical-deployment');
 await expect(settings.locator('#experiment-model-endpoint')).toHaveValue('https://clinical.example');
 const advanced=settings.locator('.experiment-model-advanced');
 if(!await advanced.evaluate(e=>e.open))await advanced.locator('summary').click();
 await expect(settings.locator('#experiment-effort')).toHaveValue('low');
 await expect(settings.locator('#experiment-max-tokens')).toHaveValue('11000');
 await settings.locator('#experiment-model-endpoint').fill('https://another.example');
 await expect(settings.getByRole('checkbox',{name:/Use configured credentials/})).toHaveCount(0);
 await expect(settings.locator('#experiment-api-key')).toBeVisible();
 await expect(settings.getByRole('button',{name:'Check & use model'})).toBeDisabled();
 await settings.locator('#experiment-default-profile').selectOption('ml');
 await expect(settings.locator('.experiment-model-advanced')).toContainText('Server defaults: temperature 1.');
 await settings.getByRole('button',{name:'Check & use model'}).click();
 await expect(settings).toContainText('Model ready');
 assert.equal(submitted[1].default_role,'ml');
 assert.deepEqual(submitted[1].settings,{max_tokens:4096});
 await settings.getByRole('button',{name:'Change',exact:true}).click();
 await settings.locator('.experiment-model-advanced summary').click();
 await settings.locator('#experiment-default-profile').selectOption('question');
 await settings.locator('#experiment-temperature').fill('0.4');
 await settings.getByRole('radio',{name:/Use current model/}).check();
 await settings.getByRole('radio',{name:/Set up a model/}).check();
 await expect(settings.locator('#experiment-temperature')).toHaveValue('0.2');
 await expect(settings.locator('#experiment-max-tokens')).toHaveValue('7000');
 assert(await settings.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({width,envDefaults:true,roleOverrides:true,noKeyInBrowser:true,reusedKey:true,endpointChangeRequiresKey:true,resetToDefaults:true,noOverflow:true}));
 await page.close();
}}finally{await browser.close();}
