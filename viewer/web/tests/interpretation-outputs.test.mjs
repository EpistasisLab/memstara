import {test} from 'node:test';
import assert from 'node:assert/strict';
import {interpretationOutputs} from '../src/lib/interpretationOutputs.ts';
test('historic fanout displays all saved originals, not its generated aggregate',()=>{
 const branches=[{slot:1,status:'done',text:'  shared-shap\n'}, {slot:2,status:'done',text:'```markdown\nshared-lime\n```\n'}];
 assert.deepEqual(interpretationOutputs({interpretation:'## Interpreter 1 — old wrapper',evaluation:{interpretations:branches}}),branches);
});
test('legacy non-fanout text including whitespace and fences remains untouched',()=>{
 const text='  ```markdown\n| Confidence | Robustness |\n|---|---|\n| 1 | 2 |\n```\n';
 assert.equal(interpretationOutputs({interpretation:text})[0].text,text);
 assert.deepEqual(interpretationOutputs({interpretation:''}),[]);
});

import {savedReportText} from '../src/lib/savedReportText.ts';
test('alternate report views use original saved calls instead of historical wrappers',()=>{
 const text='  # shared-hiv\n\n';
 assert.equal(savedReportText({text:'## Loop 1 — generated wrapper',explanation_outputs:[{text}]}),text);
 assert.equal(savedReportText({text}),text);
 assert.equal(savedReportText(null),'');
});
