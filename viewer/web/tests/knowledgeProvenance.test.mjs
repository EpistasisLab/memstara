import test from 'node:test';
import assert from 'node:assert/strict';
import {knowledgeProvenance} from '../src/lib/knowledgeProvenance.ts';

test('legacy and malformed records do not invent novelty',()=>{
  for(const value of [null, undefined, [], 'wrong', {version:'future'}]) assert.equal(knowledgeProvenance(value), null);
  const result=knowledgeProvenance({version:'hypothesis_provenance_v1',sources:[null,{status:'constructor'},{status:'mixed',id:'source'}]});
  assert.match(result.sources[0].label,/Unverified/);
  assert.match(result.sources[1].label,/Unverified/);
  assert.equal(result.sources[2].label,'Mixed relations declared');
});
test('literature is not treated as low novelty and details are bounded',()=>{
 const result=knowledgeProvenance({version:'hypothesis_provenance_v1',sources:Array.from({length:80},()=>({status:'not_applicable',id:'literature'}))});
 assert.equal(result.total,80); assert.equal(result.sources.length,50);
 assert.match(result.sources[0].label,/not applicable/);
 assert.equal(knowledgeProvenance({version:'hypothesis_provenance_v1',status:'no_declared_sources'}).empty,true);
});
test('path inventory count is optional and never a novelty rating',()=>{
 const decode = inventory => knowledgeProvenance({version:'hypothesis_provenance_v1',sources:[{provenance:{path_inventory:inventory}}]}).sources[0];
 assert.equal(decode({version:'path_inventory_v1',row_count:19}).pathCount,19);
 assert.equal(decode({version:'path_inventory_v1',row_count:0}).pathCount,0);
 for (const row_count of [-1, 1.5, '19', Infinity]) assert.equal(decode({version:'path_inventory_v1',row_count}).pathCount,null);
 assert.equal(decode({version:'future',row_count:19}).pathCount,null);
});
