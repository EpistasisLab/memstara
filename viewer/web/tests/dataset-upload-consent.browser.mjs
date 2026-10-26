import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try{
 for(const width of [390,1440]){
  const page=await browser.newPage({viewport:{width,height:950}});
  let registered;
  await page.route('**/control/research-inputs**',async route=>{
   const request=route.request();
   if(request.method()==='GET')return route.fulfill({json:{inputs:[]}});
   if(request.url().endsWith('/upload'))return route.fulfill({status:201,json:{dataset_path:'/uploaded/dataset.csv',columns:['a','b','c','d','outcome'],rows:40,missing_cells:2,columns_with_missing:{a:2},nonfinite_columns:[],message:'Missing values found. Some classifiers cannot run without imputation.'}});
   registered=request.postDataJSON();
   const valid=registered.missing_policy==='impute_train_v1';
   return route.fulfill({json:{id:valid?'a'.repeat(32):undefined,configuration:registered,dataset:{rows:40,column_count:5,columns:['a','b','c','d','outcome'],missing_cells:2},knowledge:{documents:0},issues:valid?[]:[{code:'missing_values',message:'Selected columns contain missing values.'}],input_checks_passed:valid,execution_ready:false}});
  });
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html');
  await page.getByLabel('Knowledge mode',{exact:true}).selectOption('llm_only');
  await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'example.csv',mimeType:'text/csv',buffer:Buffer.from('a,b,c,d,outcome\n,1,2,3,0\n')});
  await expect(page.getByText('Missing values found. Some classifiers cannot run without imputation.',{exact:true})).toBeVisible();
  await expect(page.getByLabel('No — require complete input before starting.',{exact:true})).toBeChecked();
  await page.getByLabel('Target column',{exact:true}).selectOption('outcome');
  await page.getByRole('button',{name:'Check inputs',exact:true}).click();
  await expect(page.getByText('Resolve input issues before execution',{exact:true})).toBeVisible();
  await page.getByLabel('Yes — use training-only mean / most frequent values.',{exact:true}).check();
  await page.getByLabel('Other categorical predictor columns (one exact name per line)',{exact:true}).fill('d');
  await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
  await expect(page.getByText('Inputs are ready to use',{exact:true})).toBeVisible();
  expect(registered.missing_policy).toBe('impute_train_v1');
  expect(registered.categorical_columns).toEqual(['d']);
  await page.getByText('Use a server file instead of uploading',{exact:true}).click();
  await page.getByLabel('Dataset CSV path',{exact:true}).fill('/other.csv');
  await expect(page.getByLabel('No — require complete input before starting.',{exact:true})).toBeChecked();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.close();
 }
 console.log('Upload, automatic feedback, explicit consent, persistence and consent reset passed at 390/1440px.');
}finally{await browser.close();}
