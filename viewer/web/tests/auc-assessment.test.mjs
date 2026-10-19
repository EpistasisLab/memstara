import test from 'node:test';
import assert from 'node:assert/strict';
import {aucAssessment} from '../src/lib/aucAssessment.ts';
test('AUC boundaries and invalid measurements are distinct',()=>{
 for(const x of [null,undefined,NaN,Infinity,-.1,1.1,'0.9'])assert.equal(aucAssessment(x).kind,'unavailable');
 for(const x of [0,.499999])assert.equal(aucAssessment(x).kind,'below');
 assert.equal(aucAssessment(.5).kind,'chance');
 for(const x of [.500001,1])assert.equal(aucAssessment(x).kind,'above');
});
