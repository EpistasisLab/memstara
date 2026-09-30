import {test} from 'node:test';
import assert from 'node:assert/strict';
import {costLabel, usageCost, loopUsageMarkdown} from '../src/lib/loopUsage.ts';

test('missing pricing is not free and positive partial cost remains a subtotal',()=>{
 assert.equal(costLabel({usd:0,status:'partial',missing_costs:50}),'Not available');
 assert.equal(costLabel({usd:0,status:'partial'}),'Not available');
 assert.equal(costLabel({usd:3.25,status:'partial',missing_costs:2}),'$3.2500 · recorded subtotal');
 assert.equal(costLabel({usd:0,status:'complete',missing_costs:0}),'$0.0000');
 assert.equal(costLabel({usd:3.25,status:'complete'}),'$3.2500');
 assert.equal(costLabel({usd:NaN,status:'complete'}),'Not available');
 assert.equal(costLabel(undefined),'Not available');
 assert.equal(usageCost({usd:0,status:'partial'}),'Not available');
});
test('exported loop cost shares missing-pricing behavior with UI',()=>{
 const text=loopUsageMarkdown({run_tag:'fixture',loops:[{number:1,status:'completed',seconds:5,tokens:100,cost:{usd:0,status:'partial',missing_costs:1}}],unassigned:{calls:0,tokens:0,cost:{usd:0,status:'complete'}}});
 assert.match(text,/100 \| Not available/);
 assert.doesNotMatch(text,/0\.0000.*partial/);
});
