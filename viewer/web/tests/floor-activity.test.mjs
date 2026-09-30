import {test} from 'node:test';
import assert from 'node:assert/strict';
import {floorActivityRows, floorCallRole, floorCallStatus} from '../src/lib/floorActivity.ts';
const trace={calls:[{stage:'question6-1',status:'completed',skill:{stage:'hypothesis',id:'psychiatric'}},{stage:'hypothesis6',status:'completed',skill:{stage:'hypothesis',id:'psychiatric'}},{stage:'data#1',status:'started',skill:{stage:'data',id:'exact-features'}}],planned:{agents:[{stage:'ml',id:'governance'}]}};
test('log and floor use actual current-loop workers and distinguish planned skills',()=>{
 const rows=floorActivityRows({trace,live:true});
 assert.equal(rows[0].call.stage,'hypothesis6');
 assert.equal(rows[0].status,'Completed');
 assert.equal(rows[1].skill.id,'exact-features');
 assert.equal(rows[1].status,'Running');
 assert.equal(rows[2].skill.id,'governance');
 assert.equal(rows[2].call,undefined);
 assert.equal(rows[2].status,'Waiting · no call recorded');
 for(const row of rows)assert.equal(row.status,floorCallStatus(row.call,{live:true}));
});
test('stale, paused and historical records never claim active execution',()=>{
 assert.equal(floorActivityRows({trace,live:false})[1].status,'Last recorded: running');
 assert.equal(floorActivityRows({trace,live:true,error:'offline'})[1].status,'Last recorded: running');
 assert.equal(floorActivityRows({trace,paused:true})[1].status,'Paused');
 assert.equal(floorCallRole({stage:'interpret#1'}),'interpreter');
 assert.equal(floorCallRole({stage:'question6-1'}),'hypothesis');
 assert.equal(floorCallStatus({status:'failed'},{}),'failed');
});
