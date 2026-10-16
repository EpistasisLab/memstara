import test from 'node:test';
import assert from 'node:assert/strict';
import {controlResponse} from '../src/lib/controlResponse.ts';
test('HTML proxy failures are uncertain and never expose JSON syntax errors', async()=>{
 await assert.rejects(controlResponse(new Response('<html>Bad gateway</html>',{status:502})), TypeError);
});
test('JSON proxy failures are uncertain; validation errors stay actionable',async()=>{
 await assert.rejects(controlResponse(new Response('{"error":"unavailable"}',{status:503})), TypeError);
 assert.deepEqual(await controlResponse(new Response('{"error":"invalid setting"}',{status:400})),{error:'invalid setting'});
 assert.deepEqual(await controlResponse(new Response('{"run_tag":"new"}')),{run_tag:'new'});
});
