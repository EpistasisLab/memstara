import test from 'node:test';
import assert from 'node:assert/strict';
import {resultsStatus} from '../src/lib/resultsStatus.ts';
test('active progress is not classified as failure and completion clears the notice',()=>{
 const running=resultsStatus({status:'running'});assert.equal(running.warning,false);assert.match(running.text,/Pipeline is running/);assert.doesNotMatch(running.text,/Check stage|needs attention/);
 for(const status of ['paused','pending','waiting','cancelled','stopped'])assert.equal(resultsStatus({status}).warning,false);
 assert.equal(resultsStatus({status:'completed'}),null);assert.equal(resultsStatus(null),null);
});
test('real failures and interruptions retain their diagnostic and incomplete-report warning',()=>{
 for(const status of ['failed','blocked','incomplete','interrupted']){
 const notice=resultsStatus({status,message:'Recorded diagnostic'});assert.equal(notice.warning,true);assert.match(notice.text,/Recorded diagnostic/);
 }
 assert.match(resultsStatus({status:'interrupted'}).text,/earlier completed loops/);
 assert.match(resultsStatus({status:'unrecognized'}).text,/not been confirmed/);
});
test('a stale running record is not presented as current execution',()=>{
 const notice=resultsStatus({status:'running'},true);assert.equal(notice.warning,true);assert.match(notice.text,/Last recorded/);assert.doesNotMatch(notice.text,/Pipeline is running/);
});
