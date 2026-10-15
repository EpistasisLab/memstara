import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {setMlSettingsSchema,mlOverridesError,overridesForSkills,modelsForSkills,overrideCount} from '../src/lib/mlOverrides.ts';
const schema=JSON.parse(readFileSync(new URL('./ml-settings.fixture.json',import.meta.url),'utf8'));
setMlSettingsSchema(schema);
const settings={version:1,models:{logistic_regression:{parameters:{C:.25,solver:'liblinear',penalty:'l1'},threshold:.6},xgboost:{parameters:{n_estimators:40,learning_rate:.05}}},folds:2};
test('distinct settings match selected models; deselection removes hidden overrides',()=>{
 assert.deepEqual(modelsForSkills(['ml_logistic_regression','ml_xgboost']),['logistic_regression','xgboost']);
 const lr=overridesForSkills(settings,['ml_logistic_regression']);
 assert.equal(lr.models.xgboost,undefined);assert.equal(lr.models.logistic_regression.parameters.C,.25);
 assert.equal(mlOverridesError(lr,['ml_logistic_regression']),null);
 assert(mlOverridesError(settings,['ml_logistic_regression']));
 assert.equal(mlOverridesError(settings,['ml_logistic_regression','ml_xgboost']),null);
 assert.equal(overrideCount(settings),7);
 assert.deepEqual(overridesForSkills(settings,[]),{});
});
test('unsafe values and incompatible solver are blocked; fit counts use one selected model',()=>{
 for(const bad of [0,NaN,Infinity,20000])assert(mlOverridesError({version:1,models:{logistic_regression:{parameters:{C:bad}}}},['ml_logistic_regression']));
 assert(mlOverridesError({version:1,models:{xgboost:{parameters:{n_jobs:32}}}},['ml_xgboost']));
 assert(mlOverridesError({version:1,models:{logistic_regression:{parameters:{solver:'lbfgs',penalty:'l1'}}}},['ml_logistic_regression']));
 assert.equal(mlOverridesError({version:1,folds:5},['ml_logistic_regression'],10),null);
});
test('Auto defaults need no schema; custom values require supported server settings',()=>{
 setMlSettingsSchema();assert.equal(mlOverridesError({},['ml_logistic_regression']),null);
 assert(mlOverridesError(settings,['ml_logistic_regression','ml_xgboost']));setMlSettingsSchema(schema);
});
