import {tmpdir} from 'node:os';
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const browser=await chromium.launch({headless:true});
try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1100}});
  const errors=[],api=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.startsWith('/api/')||path.startsWith('/control/')){api.push(path);return route.abort();}
   const file=path.startsWith('/assets/')?resolve(root,'dist/assets',basename(path)):resolve(root,'dist/developer.html');
   return route.fulfill({body:await readFile(file),contentType:path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://localhost/developer.html');
  const inspector=page.getByRole('complementary',{name:'File inspector'});
  await inspector.getByRole('heading',{name:'App.tsx',exact:true}).waitFor();
  const count=await page.locator('.file-list button').count();assert.ok(count>300);
  const search=page.getByRole('textbox',{name:'Search files, symbols or endpoints'});
  await search.fill('question_contract');await page.locator('.file-list button').filter({hasText:'question_contract.py'}).first().click();
  await inspector.getByRole('heading',{name:'question_contract.py',exact:true}).waitFor();
  assert.ok(new URL(page.url()).searchParams.get('file').endsWith('question_contract.py'));
  await page.getByRole('button',{name:'Dependencies',exact:true}).click();
  await page.locator('.react-flow__node').first().waitFor();
  assert.ok(await page.locator('.react-flow__node').count()>1);
  const neighbor=page.locator('.react-flow__node').filter({hasNotText:'question_contract.py'}).first();
  const nextId=await neighbor.getAttribute('data-id');await neighbor.click();
  await page.waitForFunction(path=>new URL(location.href).searchParams.get('file')===path,nextId);
  await search.fill('propose_questions');assert.ok(await page.locator('.file-list button').count()>0);
  await search.fill('/api/snapshot');assert.ok(await page.locator('.file-list button').count()>0);
  await search.fill('there-is-no-such-symbol');await page.getByText('No matching source files.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Clear search',exact:true}).click();
  await page.getByRole('combobox',{name:'Filter by layer'}).selectOption('api');
  assert.ok(await page.locator('.file-list button').count()>0);
  for(const text of await page.locator('.file-list small').allTextContents())assert.ok(text.startsWith('viewer/api'));
  await page.getByRole('button',{name:'Reading paths',exact:true}).click();
  await page.getByRole('button',{name:'Ground a hypothesis',exact:true}).click();
  await page.locator('.reading-paths li button').first().click();
  await inspector.getByRole('heading',{name:'hypothesis.md',exact:true}).waitFor();
  assert.match(await inspector.getByRole('link',{name:'Source at commit'}).getAttribute('href'),/github.com\/HyunjunA\/memstara\/blob\/[a-f0-9]{40}\//);
  await page.reload();await inspector.getByRole('heading',{name:'hypothesis.md',exact:true}).waitFor();
  await page.getByRole('combobox',{name:'Filter by layer'}).selectOption('all');
  await page.evaluate(()=>scrollTo(0,0));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'No horizontal page overflow');
  assert.deepEqual(api,[],'Developer page must not contact application APIs');assert.deepEqual(errors,[]);
  await page.screenshot({path:`${tmpdir()}/memstara-code-atlas-${width}.png`,fullPage:true});
  console.log(JSON.stringify({width,files:count,navigation:'pass',search:'pass',apiCalls:0,errors}));await page.close();
 }
}finally{await browser.close();}
