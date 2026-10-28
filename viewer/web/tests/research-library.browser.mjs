import {chromium, expect} from '@playwright/test';
const browser=await chromium.launch();
try {
 for(const width of [390,1280]) {
  const page=await browser.newPage({viewport:{width,height:950}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const config={name:'A long saved study name for responsive research input selection',dataset_path:'/inputs/heart/dataset.csv',knowledge_path:'/inputs/heart/okf',data_mode:'dataset',knowledge_mode:'okf',missing_policy:'reject',excluded_columns:[],target:{column:'outcome',description:'Synthetic study',positive_label:'1',negative_label:'0',prediction_time:'Baseline',horizon:''}};
  const ready={id:'ready',configuration:config,input_checks_passed:true};
  const incomplete={id:'incomplete',configuration:{...config,name:'Target needs setup',target:{...config.target,column:''}},input_checks_passed:false,issues:[{code:'target',message:'Choose the prediction target.'}]};
  await page.route('**/control/health',r=>r.fulfill({json:{input_defaults:{dataset_available:false,knowledge_available:false,target_column:''}}}));
  await page.route('**/control/research-inputs',r=>r.fulfill({json:{inputs:[ready,incomplete]}}));
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html?selector');
  await expect(page.getByRole('region',{name:'Saved research inputs'})).toBeVisible();
  await expect(page.getByText('Choose the prediction target.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:`Use ${config.name}`,exact:true}).click();
  await expect(page.getByLabel('Selected dataset')).toContainText(config.name);
  await page.getByText('Change dataset',{exact:false}).click();
  await page.getByRole('button',{name:'Review Target needs setup',exact:true}).click();
  await expect(page.getByLabel('Target column',{exact:true})).toHaveValue('');
  expect(JSON.parse(await page.getByLabel('Selected research configuration').textContent()).research_input_id).toBe('ready');
  await page.getByRole('button',{name:'Cancel editing',exact:true}).click();
  await expect(page.getByLabel('Selected dataset')).toContainText(config.name);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect(errors).toEqual([]);
  await page.close();
 }
 console.log('Saved-study library: selection, incomplete-study review, cancellation preservation and responsive layout passed at 390/1280px.');
} finally {await browser.close();}
