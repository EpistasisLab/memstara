import {test} from '@playwright/test';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
for(const file of ['combination-review','responsive-scroll','responsive-reading','responsive-history','telemetry-workspace','results-notices','universe-workspace','pipeline-list-layout','responsive-touch']){
 test(file,async({},info)=>{
  const [engine,percent]=info.project.name.split('-');
  test.skip(file==='responsive-touch'&&(engine==='firefox'||!!percent),'Touch emulation is covered separately in Chromium and WebKit');
  // The floor-plan minimum canvas height check is at normal zoom; other suites cover zoom.
  test.skip(file==='pipeline-list-layout'&&!!percent,'Normal-zoom floor-plan layout matrix');
  try{
   const result=await promisify(execFile)(process.execPath,[`tests/${file}.browser.mjs`],{
    timeout:160_000,maxBuffer:4*1024*1024,
    env:{...process.env,MEMSTARA_BROWSER:engine,MEMSTARA_BROWSER_ZOOM:String(percent?Number(percent)/100:1),MEMSTARA_FIXTURE_URL:'http://127.0.0.1:4177',MEMSTARA_TEST_URL:'http://127.0.0.1:4175'},
   });
   await info.attach('checks',{body:result.stdout+'\n'+result.stderr,contentType:'text/plain'});
  }catch(error){
   const failure=error as Error&{stdout?:string;stderr?:string};
   await info.attach('checks',{body:(failure.stdout||'')+'\n'+(failure.stderr||''),contentType:'text/plain'});throw error;
  }
 });
}
