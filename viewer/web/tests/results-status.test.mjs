import test from 'node:test';
import assert from 'node:assert/strict';
import {resultsStatus} from '../src/lib/resultsStatus.ts';
test('failure identifies the saved stage and loop without implying all pipelines failed',()=>{
 const notice=resultsStatus({status:'failed',stage:'question0-1',loop:1,message:'Tool correction failed.'});
 assert.match(notice.text,/This execution failed at Question generation \(Pipeline 1 · Replicate 1\)/);
 assert.match(notice.text,/Tool correction failed/);
 const legacy=resultsStatus({status:'failed',message:'Pipeline could not safely continue; inspect console.log and trace/.'});
 assert.match(legacy.text,/does not identify the cause/);
 assert.doesNotMatch(legacy.text,/console.log/);
});
test('active progress is not classified as failure and completion clears the notice',()=>{
 const running=resultsStatus({status:'running'});assert.equal(running.warning,false);assert.match(running.text,/Pipeline is running/);assert.doesNotMatch(running.text,/Check stage|needs attention/);
 for(const status of ['paused','pending','waiting','cancelled','stopped'])assert.equal(resultsStatus({status}).warning,false);
 assert.equal(resultsStatus({status:'completed'}),null);assert.equal(resultsStatus(null),null);
});
test('real failures and interruptions retain their diagnostic and incomplete-report warning',()=>{
 for(const status of ['failed','blocked','incomplete','interrupted']){
 const notice=resultsStatus({status,message:'Recorded diagnostic'});assert.equal(notice.warning,true);assert.match(notice.text,/Recorded diagnostic/);
 }
 assert.match(resultsStatus({status:'interrupted'}).text,/earlier completed replicates/);
 assert.match(resultsStatus({status:'unrecognized'}).text,/not been confirmed/);
});
test('a stale running record is not presented as current execution',()=>{
 const notice=resultsStatus({status:'running'},true);assert.equal(notice.warning,true);assert.match(notice.text,/Last recorded/);assert.doesNotMatch(notice.text,/Pipeline is running/);
});
test('Results follows controller pause without masking failure or stale data',()=>{
 const stopping={paused:false,stopping:true},paused={paused:true,stopping:false};
 assert.match(resultsStatus({status:'running'},false,stopping).text,/Pause requested/);
 assert.match(resultsStatus({status:'running'},false,paused).text,/Pipeline is paused/);
 assert.match(resultsStatus({status:'running'},true,paused).text,/Last recorded/);
 assert.match(resultsStatus({status:'failed',message:'actual failure'},false,paused).text,/actual failure/);
});

test('skipped combinations are disclosed without reporting full success or a crash',()=>{
 const partial=resultsStatus({status:'completed_with_skips'});
 assert.equal(partial.warning,false);
 assert.match(partial.text,/not counted as completed/);
 const empty=resultsStatus({status:'no_findings'});
 assert.equal(empty.warning,false);
 assert.match(empty.text,/no analysis or report/);
});
