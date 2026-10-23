import {test} from 'node:test';
import assert from 'node:assert/strict';
import {experimentHypothesis as heading} from '../src/lib/experimentHeading.ts';
const result=(iteration,text,run_tag='a')=>({run_tag,iteration,trial:iteration-1,hypothesis:text,result_id:iteration});
const event=(iteration,text,run_tag='a')=>({run_tag,iteration,trial:iteration-1,stage:'hypothesis',detail:text,at:'2026-10-23T12:00:00Z'});
test('advancing replicate hides previous hypothesis until current hypothesis is recorded',()=>{
 const results=[result(1,'First')];
 assert.equal(heading('a',1,true,1,[],results),'First');
 assert.equal(heading('a',2,true,1,[],results),'');
 assert.equal(heading('a',2,true,1,[event(2,'Second')],results),'Second');
});
test('isolates runs and ignores unconfirmed current position',()=>{
 assert.equal(heading('a',2,true,1,[event(2,'Wrong','b')],[result(1,'Old')]),'');
 assert.equal(heading('a',undefined,true,1,[event(2,'Second')],[]),'');
 assert.equal(heading('new',1,true,1,[event(1,'Old')],[]),'');
});
test('completed run uses last recorded iteration when progress is absent',()=>{
 assert.equal(heading('a',undefined,false,1,[],[result(1,'First'),result(2,'Second')]),'Second');
 assert.equal(heading('a',3,false,1,[],[result(2,'Second')]),'');
});
test('zero based trial mapping uses trials per iteration, not visible replicate count',()=>{
 assert.equal(heading('a',2,true,2,[],[{...result(1,'Current'),iteration:null,trial:2}]),'Current');
});
