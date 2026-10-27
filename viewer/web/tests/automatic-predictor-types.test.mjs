import {test} from 'node:test';
import assert from 'node:assert/strict';
import {automaticPredictorTypes} from '../src/components/automaticPredictorTypes.ts';
test('automatic types retain semantic suggestions and resolve otherwise unclassified numeric columns',()=>{
 assert.deepEqual(automaticPredictorTypes({column_kinds:{age_years:'categorical',previous_events_count:'categorical',stage:'numeric',measurement:'numeric',group:'categorical',binary:'categorical',empty:'empty'},suggested_predictor_types:{age_years:'continuous',previous_events_count:'continuous',stage:'categorical'}}),{age_years:'continuous',previous_events_count:'continuous',stage:'categorical',measurement:'continuous',group:'categorical',binary:'categorical'});
});
test('a new upload has only its own detected columns and needs no manual confirmation',()=>{
 automaticPredictorTypes({column_kinds:{old:'numeric'}});
 assert.deepEqual(automaticPredictorTypes({column_kinds:{fresh:'categorical'}}),{fresh:'categorical'});
 assert.deepEqual(automaticPredictorTypes({}),{});
});
