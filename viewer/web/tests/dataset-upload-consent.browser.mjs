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
  await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'example.csv',mimeType:'text/csv',buffer:Buffer.from('a,b,c,d,outcome\n,1,2,3,0\n2,1,2,3,1\n')});
  await expect(page.getByText('Missing values found',{exact:true})).toBeVisible();
  await expect(page.getByLabel('I’ll fix the CSV',{exact:true})).toBeChecked();
  await expect(page.getByLabel('Target column',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('radio',{name:'LLM only',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Check & use this data',exact:true})).toHaveCount(0);
  expect(registered).toBeUndefined();
  await page.getByLabel('Fill missing values for me',{exact:true}).check();
  await page.getByLabel('Target column',{exact:true}).selectOption('outcome');
  await page.getByRole('radio',{name:'LLM only',exact:true}).check();
  await expect(page.getByText('Review category columns',{exact:true})).toHaveCount(0);
  await expect(page.getByText('How filling works',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Values are calculated from training data only. Your original CSV stays unchanged.',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Check & use this data',exact:true}).click();
  await expect(page.getByText('Inputs are ready to use',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Got it',exact:true}).click();
  expect(registered.missing_policy).toBe('impute_train_v1');
  expect(registered.categorical_columns).toEqual([]);
  expect(registered.target.positive_label).toBe('1');
  expect(registered.target.negative_label).toBe('0');
  await page.getByLabel('Upload CSV',{exact:true}).setInputFiles({name:'another.csv',mimeType:'text/csv',buffer:Buffer.from('a,b,c,d,outcome\n,1,2,3,0\n2,1,2,3,1\n')});
  await expect(page.getByLabel('I’ll fix the CSV',{exact:true})).toBeChecked();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.close();
 }
 console.log('Upload, automatic feedback, explicit consent, persistence and consent reset passed at 390/1440px.');
}finally{await browser.close();}
