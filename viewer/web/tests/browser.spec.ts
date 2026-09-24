import {test} from '@playwright/test';
import {execFile} from 'node:child_process';
import {readdir} from 'node:fs/promises';
import {promisify} from 'node:util';

// These two diagnostics require an existing deployment and are run explicitly.
const deploymentOnly=new Set(['app-ux-audit.browser.mjs','telemetry-live.browser.mjs']);
const files=(await readdir(new URL('.',import.meta.url)))
  .filter(name=>name.endsWith('.browser.mjs')&&!deploymentOnly.has(name)).sort();
for(const file of files) {
 test(file,async({},info)=>{
  try {
   const result=await promisify(execFile)(process.execPath,[`tests/${file}`],{
    timeout:110_000,maxBuffer:4*1024*1024,
    env:{...process.env,MEMSTARA_TEST_URL:'http://127.0.0.1:4175'},
   });
   await info.attach('output',{body:result.stdout+'\n'+result.stderr,contentType:'text/plain'});
  } catch(error) {
   const failure=error as Error&{stdout?:string;stderr?:string};
   await info.attach('output',{body:(failure.stdout||'')+'\n'+(failure.stderr||''),contentType:'text/plain'});
   throw error;
  }
 });
}
