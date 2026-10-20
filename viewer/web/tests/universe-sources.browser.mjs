import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try {
 for(const width of [1280,390]) {
  const page=await browser.newPage({viewport:{width,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const q=(id,source)=>({question_id:id,text:`${source} question ${id}`,rationale:'Recorded',okf_tags:[],origin_run:source,origin_wave:0,writer:'agent',times_used:0,best_auc:null,status:'open',created_at:''});
  const reads=[];
  await page.route('**/api/discovery/**',async r=>{
   const u=new URL(r.request().url());const source=u.searchParams.get('source')||'all';reads.push([u.pathname,source]);
   if(u.pathname.endsWith('/sources'))return r.fulfill({json:{sources:[{id:'all',label:'All sources',count:3},{id:'heart',label:'Heart source',count:1},{id:'hiv',label:'HIV source',count:1},{id:'unknown',label:'Source unknown',count:1}]}});
   if(u.pathname.endsWith('/questions')){
    let questions=source==='heart'?[q(1,'Heart')]:source==='hiv'?[q(2,'HIV')]:source==='unknown'?[q(3,'Unknown')]:[q(1,'Heart'),q(2,'HIV'),q(3,'Unknown')];
    const query=u.searchParams.get('query')||'';questions=questions.filter(v=>v.text.toLowerCase().includes(query.toLowerCase()));
    return r.fulfill({json:{questions,total:questions.length,next_before:null}});
   }
   if(u.pathname.endsWith('/novelty'))return r.fulfill({json:{items:[],total:0,next_offset:null}});
   if(u.pathname.endsWith('/semantic'))return r.fulfill({json:{status:'ready',points:[],neighbors:[],indexed_count:1,total_questions:1,coverage:'complete'}});
   return r.fulfill({json:{question:q(1,'Heart'),tasks:[],results:[]}});
  });
  await page.route('**/control/**',r=>r.fulfill({json:{pipelines:[]}}));
  await page.goto('http://127.0.0.1:4177/tests/question-universe.fixture.html');
  const source=page.getByRole('combobox',{name:'Knowledge source'});
  await source.selectOption('heart');
  await page.getByRole('button',{name:'View options',exact:true}).click();
  await page.getByRole('button',{name:'List',exact:true}).click();await page.keyboard.press('Escape');
  await expect(page.locator('.universe-list')).toContainText('Heart question');
  await expect(page.locator('.universe-list')).not.toContainText('HIV question');
  await page.getByRole('textbox',{name:'Search questions',exact:true}).fill('HIV');
  await expect(page.locator('.universe-list')).toContainText('No matching questions');
  await source.selectOption('hiv');
  await expect(page.getByRole('textbox',{name:'Search questions',exact:true})).toHaveValue('');
  await page.getByRole('button',{name:'View options',exact:true}).click();
  await page.getByRole('button',{name:'List',exact:true}).click();await page.keyboard.press('Escape');
  await expect(page.locator('.universe-list')).toContainText('HIV question');
  await expect(page.locator('.universe-list')).not.toContainText('Heart question');
  await page.getByRole('button',{name:'Explore questions',exact:true}).click();
  await page.getByRole('button',{name:'Novelty proxy ranking',exact:true}).click();
  await expect(page.getByText('No recorded hypotheses in this scope.')).toBeVisible();
  await page.getByRole('button',{name:'Close Universe panel',exact:true}).click();
  await page.getByRole('button',{name:'Explore questions',exact:true}).click();
  await page.getByRole('button',{name:'Related questions',exact:true}).click();
  await page.getByRole('button',{name:'Refresh semantic layout',exact:true}).click();
  await expect(page.getByText('Indexed 1 of 1 active questions',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Close Universe panel',exact:true}).click();
  await source.selectOption('unknown');
  await expect(page.locator('.universe-summary')).toContainText('1 of 1 questions');
  assert(reads.some(([p,s])=>p.endsWith('/semantic')&&s==='hiv'));
  assert(reads.some(([p,s])=>p.endsWith('/novelty')&&s==='hiv'));
  assert(await page.locator('.universe-page').evaluate(el=>el.scrollWidth<=el.clientWidth+2));
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Corpus selection, search isolation, reset, novelty/semantic scopes and mobile width passed.');
} finally {await browser.close();}
