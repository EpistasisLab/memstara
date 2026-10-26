import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
async function drop(page,names) {
 const transfer=await page.evaluateHandle(names=>{const dt=new DataTransfer();for(const name of names)dt.items.add(new File(['a,b,target\n1,,0\n'],name,{type:'text/csv'}));return dt;},names);
 await page.getByRole('group',{name:'CSV upload area'}).dispatchEvent('drop',{dataTransfer:transfer});
 await transfer.dispose();
}
try {
 for(const width of [390,1280]) {
  const page=await browser.newPage({viewport:{width,height:950}});
  let calls=0,release;
  await page.route('**/control/research-inputs/upload',async route=>{
   calls++;
   expect(route.request().postDataJSON().filename).toBe('valid.csv');
   await new Promise(resolve=>release=resolve);
   await route.fulfill({json:{dataset_path:'/uploaded/data.csv',columns:['a','b','target'],rows:1,missing_cells:1,columns_with_missing:{b:1},nonfinite_columns:[],message:'Missing values found. Some classifiers cannot run without imputation.'}});
  });
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html');
  await drop(page,['one.csv','two.csv']);
  await expect(page.getByRole('alert')).toHaveText('Drop one CSV file at a time.');
  await drop(page,['not-csv.txt']);
  await expect(page.getByRole('alert')).toContainText('Choose a CSV file.');
  expect(calls).toBe(0);
  await drop(page,['valid.csv']);
  await expect.poll(()=>calls).toBe(1);
  await drop(page,['ignored-while-busy.csv']);
  expect(calls).toBe(1);
  release();
  await expect(page.getByText('Missing values found. Some classifiers cannot run without imputation.',{exact:true})).toBeVisible();
  await expect(page.getByLabel('No — require complete input before starting.',{exact:true})).toBeChecked();
  await expect(page.getByLabel('Target column',{exact:true})).toHaveValue('');
  await page.getByLabel('Upload CSV',{exact:true}).focus();
  await expect(page.getByLabel('Upload CSV',{exact:true})).toBeFocused();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/research-inputs.fixture.html?disabled');
  await drop(page,['valid.csv']);
  expect(calls).toBe(1);
  await expect(page.getByLabel('Upload CSV',{exact:true})).toBeDisabled();
  await page.close();
 }
 console.log('CSV drop: real File/DataTransfer events, one-file/type guards, busy/disabled guards, automatic inspection, default refusal and mobile/desktop layout passed. API mocked.');
} finally {await browser.close();}
