import test from 'node:test';
import assert from 'node:assert/strict';
import { displayText, displayJson, skillLabel } from '../src/lib/displayText.ts';
import { displayMarkdown } from '../src/lib/displayMarkdown.ts';
import { agentDisplayName, cleanLog } from '../src/lib/telemetry.ts';

test('historical specialist IDs have role labels even with missing or old catalog titles', () => {
  for (const [role, label] of Object.entries({shap:'SHAP Interpretation',lime:'LIME Interpretation',addiction:'Addiction Expert Explanation',hiv:'HIV Expert Explanation'})) {
    assert.equal(skillLabel(`shared-${role}`), label);
    assert.equal(skillLabel(`shared-${role}`, `Anil ${role}`), label);
    assert.equal(displayText(`Skill: SHARED_ANIL_${role.toUpperCase()}`), `Skill: ${label}`);
  }
  assert.equal(skillLabel('custom-model', 'Custom model'), 'Custom model');
  assert.equal(skillLabel('constructor'), 'constructor');
  assert.equal(skillLabel(null, null, 'Default instructions'), 'Default instructions');
});

test('legacy attribution is omitted without changing clinical terms or numerical evidence', () => {
  assert.equal(displayText("Anil's rules; Phil and Jason; Hyunjun Choi"), "contributor's rules; contributor and contributor; contributor");
  assert.equal(displayText('Phil Freda, Jason Moore, Anil Saini, HyunjunA'), 'contributor, contributor, contributor, contributor');
  assert.equal(displayText('not an Anil-authored skill'), 'not a contributor-authored skill');
  assert.equal(displayText('SPECIALIST_SKILLS / anil_shared / phil_shared'), 'SPECIALIST_SKILLS / contributed-resources / contributed-resources');
  const scientific='Neutrophil count, aniline exposure, HIV, SHAP, LIME, AUROC 0.731, USD 0.11321064.';
  assert.equal(displayText(scientific), scientific);
  assert.equal(displayText(displayText("Anil's shared-shap")), displayText("Anil's shared-shap"));
});

test('JSON and console previews preserve the underlying reproducibility record', () => {
  const record = Object.freeze({skill:'shared-shap',seed:42,auc:0.731,cost:0.11321064,nested:Object.freeze({author:'Phil'})});
  const before=JSON.stringify(record);
  assert.deepEqual(JSON.parse(displayJson(record)), {skill:'SHAP Interpretation',seed:42,auc:0.731,cost:0.11321064,nested:{author:'contributor'}});
  assert.equal(JSON.stringify(record),before);
  assert.equal(cleanLog('\x1b[31mSkill: shared-shap\x1b[0m'), 'Skill: SHAP Interpretation');
  assert.equal(agentDisplayName('shared-lime · board_20261022T120000_123456'), 'LIME Interpretation');
});

test('Markdown display transforms visible prose, code and tooltips while retaining source links', () => {
  const url='https://example.org/anil_shared/SHAP-Interpretation.md';
  const tree={type:'root',children:[{type:'paragraph',children:[
    {type:'text',value:"Anil's "},{type:'inlineCode',value:'shared-shap'},
    {type:'link',url,title:"Phil's document",children:[{type:'text',value:'Anil skill'}]},
    {type:'image',url,alt:'Anil diagram',title:'Phil diagram'},
  ]},{type:'code',lang:'json',value:'{"skill":"shared-lime"}'}]};
  displayMarkdown()(tree);
  assert.equal(tree.children[0].children[0].value,"contributor's ");
  assert.equal(tree.children[0].children[1].value,'SHAP Interpretation');
  assert.equal(tree.children[0].children[2].url,url);
  assert.equal(tree.children[0].children[2].title,"contributor's document");
  assert.equal(tree.children[0].children[3].url,url);
  assert.equal(tree.children[0].children[3].alt,'contributor diagram');
  assert.equal(tree.children[1].value,'{"skill":"LIME Interpretation"}');
});
