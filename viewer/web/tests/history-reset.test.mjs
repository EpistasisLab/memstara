import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clearExecutionStorage,resetActive,resetPhaseLabels,resetRequestId} from '../src/lib/historyReset.ts';
test('clears execution receipts but preserves every configuration key',()=>{
 const values=new Map(Object.entries({'memstara-selection-v1':'old-run','memstara-output-read-v1':'old',
 'memstara-results-read-v1':'old','memstara-draft-v1':'saved-model-config','memstara-pipeline-selection-v1':'pipeline',
 'memstara-theme-v2':'dark','unrelated':'preserve'}));
 clearExecutionStorage({removeItem:key=>values.delete(key),setItem:(key,value)=>values.set(key,value)},'new-revision');
 assert.equal(values.get('memstara-selection-v1'),'{"runTag":null}');
 assert.equal(values.get('memstara-draft-v1'),'saved-model-config');
 assert.equal(values.get('memstara-pipeline-selection-v1'),'pipeline');
 assert.equal(values.get('memstara-theme-v2'),'dark');
 assert(!values.has('memstara-output-read-v1')&&!values.has('memstara-results-read-v1'));
 assert.equal(values.get('memstara-history-revision-v1'),'new-revision');
});
test('active phases all have English status and failures remain terminal',()=>{
 for(const state of Object.keys(resetPhaseLabels))assert(resetActive({state,revision:'old'}));
 for(const state of ['completed','failed','idle'])assert(!resetActive({state,revision:'old'}));
});
test('request IDs are valid UUIDs without the secure-context randomUUID API',()=>{
 const ids=Array.from({length:20},resetRequestId);
 assert.equal(new Set(ids).size,20);
 assert(ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));
});
