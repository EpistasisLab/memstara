// Browser regression: all writes are mocked; no pipeline or paid LLM call is started.
import {chromium} from '@playwright/test';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
try {
 const page=await browser.newPage({viewport:{width:1300,height:900}});let uploads=[],skills=[];
 await page.route('**/control/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path==='/control/pipelines')return r.fulfill({json:{pipelines:[]}});
  if(path==='/control/research-inputs')return r.fulfill({json:{inputs:[]}});
  if(path==='/control/health')return r.fulfill({json:{input_defaults:{dataset_available:true,knowledge_available:true}}});
  if(path==='/control/playbooks'){
   if(r.request().method()==='GET')return r.fulfill({json:{catalog:skills,playbooks:[],stages:['hypothesis','data','ml','interpreter','report'],references:[]}});
   const b=r.request().postDataJSON();uploads.push(b);
   if(b.name==='server-fail')return r.fulfill({status:500,json:{error:'Test upload rejected'}});
   const s={id:b.stage+'-'+b.name,stage:b.stage,title:b.name,content:b.content,description:'Custom',hash:b.stage+b.name,source:'Custom'};skills.push(s);return r.fulfill({json:s});
  }
  if(r.request().method()==='POST')throw Error('Unexpected mutation '+path);
  return r.continue();
 });
 await page.goto(process.env.MEMSTARA_TEST_URL || 'http://localhost:8070');await page.getByRole('navigation').getByRole('button',{name:'Experiments',exact:true}).first().click();await page.getByRole('button',{name:/Add pipeline/i}).click();
 const d=page.getByRole('dialog',{name:'All Combinations',exact:true});
 await d.getByLabel('Deployment target column',{exact:true}).fill('outcome');
 await d.getByRole('button',{name:'Choose skills'}).click();
 for(let i=0;i<5;i++){
  await d.getByRole('navigation',{name:'Agent roles'}).getByRole('button').nth(i).click();
  await d.getByRole('button',{name:/^Upload or write/}).click();
  await d.getByLabel('Custom skill Markdown file').setInputFiles([
   {name:'alpha.md',mimeType:'text/markdown',buffer:Buffer.from('# Alpha skill')},
   {name:'bad.txt',mimeType:'text/plain',buffer:Buffer.from('Invalid')},
   {name:'server-fail.md',mimeType:'text/markdown',buffer:Buffer.from('# Fails')},
   {name:'beta.md',mimeType:'text/markdown',buffer:Buffer.from('# Beta skill')},
  ]);
  await d.getByText(/beta.md · Uploaded/).waitFor();
  if(!await d.locator('.comb-selected-skills').getByRole('button',{name:'Remove alpha',exact:true}).isVisible()||!await d.locator('.comb-selected-skills').getByRole('button',{name:'Remove beta',exact:true}).isVisible())throw Error('Successes not selected');
  await d.getByRole('alert').filter({hasText:'Test upload rejected'}).waitFor();
 }
 if(uploads.length!==15||uploads.some(x=>x.name==='bad'))throw Error('Wrong upload validation');
 await d.getByRole('button',{name:'Review plan'}).click();await d.getByLabel('Maximum Loops per execution').fill('32');await d.getByText('How execution works',{exact:true}).click();await d.getByText(/^Stops after at most 32 Loops\./).waitFor();
 console.log('All five roles: multiple files selected, invalid extension rejected locally, server failure shown, later successes retained; 32 combinations. No real writes.');
} finally {await browser.close();}
