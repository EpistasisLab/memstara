import test from 'node:test';
import assert from 'node:assert/strict';
import {readDiscoveryResponse} from '../src/lib/discoveryRecords.ts';
test('HTML and malformed payloads cannot enter the Universe renderer',async()=>{
 await assert.rejects(readDiscoveryResponse(new Response('<html>Error</html>'),'/api/discovery/questions?before=0'),/unreadable/);
 await assert.rejects(readDiscoveryResponse(Response.json({questions:null}),'/api/discovery/questions?before=0'),/unavailable/);
});
test('question identity is checked and legacy tags are normalized',async()=>{
 await assert.rejects(readDiscoveryResponse(Response.json({question:{question_id:2,text:'Other'},tasks:[],results:[]}),'/api/discovery/questions/1'),/does not match/);
 const data=await readDiscoveryResponse(Response.json({questions:[{question_id:1,text:'Question',okf_tags:null}]}),'/api/discovery/questions?before=0');
 assert.deepEqual(data.questions[0].okf_tags,[]);
});
test('linked evidence for another question is rejected',async()=>{
 await assert.rejects(readDiscoveryResponse(Response.json({question:{question_id:1,text:'Question'},tasks:[],results:[{result_id:10,question_id:2}]}),'/api/discovery/questions/1'),/question/);
});
