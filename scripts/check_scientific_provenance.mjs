import assert from 'node:assert/strict';
import { scientificProvenance } from '../viewer/web/src/lib/scientificProvenance.ts';
assert.match(scientificProvenance(undefined, false).label, /pending/);
for (const evaluation of [undefined, {}, {hypothesis_policy:{}},
  {hypothesis_policy:{version:'legacy',kind:'primary_knowledge_driven'}},
  {hypothesis_policy:{version:'knowledge_only_v1',kind:'evidence_enriched'}}]) {
  assert.match(scientificProvenance(evaluation).label, /not recorded or unrecognized/);
}
const valid={hypothesis_policy:{version:'knowledge_only_v1',kind:'primary_knowledge_driven'}};
assert.equal(scientificProvenance(valid).label, 'Knowledge-driven primary hypothesis');
assert.match(scientificProvenance(valid).detail, /does not establish independent validation/);
console.log('Passed: pending, legacy, unknown and non-primary records cannot acquire a primary or independently validated label.');
