import {test} from 'node:test';
import assert from 'node:assert/strict';
import {floorCallDestination, floorCallCategory} from '../src/lib/floorCallDestination.ts';
test('question and multi-table calls never pretend to touch just the task board',()=>{
 for(const tool of ['read_question_catalog','propose_questions','claim_question','submit_result','recover_interpretation']) assert.equal(floorCallDestination(tool,'board'),'database');
});
test('specific known operations retain their table targets',()=>{
 assert.equal(floorCallDestination('read_results','results'),'results');
 assert.equal(floorCallDestination('claim_task','board'),'board');
 assert.equal(floorCallDestination('future_db_tool','board'),'database');
});
test('mapping is a concept-to-column capability and unknown calls are not invented',()=>{
 assert.equal(floorCallDestination('match_concepts','matcher'),'matcher');
 assert.equal(floorCallCategory('match_concepts','matcher'),'Concept-to-column mapping');
 assert.equal(floorCallDestination('unknown_tool','unknown'),null);
});
