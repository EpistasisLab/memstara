import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:process.env.MEMSTARA_BROWSER_EXECUTABLE});
try{
 const page=await browser.newPage();const writes=[],errors=[];let repaired=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route(/\/(api|control)\//,async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  if(request.method()==='POST'){
   writes.push(path);assert.equal(path,'/control/runs/last-attempt/rebuild-report');
   repaired=true;return route.fulfill({json:{combinations:64,model_calls:0,analyses_recomputed:0}});
  }
  if(path==='/control/pipelines')return route.fulfill({json:{pipelines:[{id:'example',name:'test-hiv-1',number:1,
   configuration:{},running:null,latest:{run_tag:'last-attempt',exit_code:1,report_recovered:repaired},
   progress:{exploration:{attempted:15,completed:15,blocked:0,outcome:'completed'}},
   failure:repaired?null:{code:'final_report_assembly_failed',stage:'report_assembly',loop:null,message:'Final report needs recovery'}}]}});
  return route.fulfill({json:{runs:[]}});
 });
 await page.goto((process.env.MEMSTARA_TEST_URL||'http://127.0.0.1:4189')+'/tests/report-recovery.fixture.html');
 await expect(page.getByTestId('report-state')).toHaveText('Analyses completed · Report needs attention');
 await expect(page.getByText('Retry unavailable: the failed replicate is not identified.')).not.toBeVisible();
 await page.getByRole('button',{name:'Rebuild report test-hiv-1',exact:true}).click();
 await expect(page.getByTestId('report-state')).toHaveText('Completed');
 await expect(page.getByTestId('original-exit')).toContainText('1');
 assert.deepEqual(writes,['/control/runs/last-attempt/rebuild-report']);assert.deepEqual(errors,[]);
 console.log('Report-only recovery shows Completed while retaining the actual original exit code; no experiment-start request sent.');
}finally{await browser.close();}
