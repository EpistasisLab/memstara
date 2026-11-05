import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {validateLinkedExport,linkedResultsCsv,linkedCompleteCsv,linkedExportFiles,zipFiles,crc32,readLinkedExport} from '../src/lib/linkedOutputExport.ts';

const fixture=()=>({schema_version:'linked_agent_outputs_v1',generated_at:'2026-11-05T05:00:00Z',
 requested_run_tags:['retry'],run_tags:['old','retry'],warnings:[],
 results:[{result_uid:'r1',run_tag:'old',result_id:1,trial:0,model:'lr',auc:.7,
  interpretation_output_ids:['i1','i2'],explanation_output_ids:['e1'],interpretation_status:'complete',explanation_status:'complete',
  evaluation:{skills:{hypothesis:['hiv-no-knowledge']},evaluation:{replicates:[{seed:42,auc:.7},{seed:43,auc:.8}]}}},
  {result_uid:'r2',run_tag:'retry',result_id:2,trial:1,interpretation_output_ids:[],explanation_output_ids:[],interpretation_status:'not_recorded'}],
 interpretations:[{output_id:'i1',run_tag:'old',text:'\n# Exact 한글\n',result_uids:['r1']},
  {output_id:'i2',run_tag:'old',text:'Second output\n',result_uids:['r1']}],
 explanations:[{output_id:'e1',run_tag:'old',text:'**Explanation**\n',result_uids:['r1']}],
 executions:[{run_tag:'old',results:[]},{run_tag:'retry',results:[]}]});

test('stable foreign keys survive CSV quoting, multiple fits and exact narrative JSON',()=>{
 const bundle=fixture();validateLinkedExport(bundle);
 const files=linkedExportFiles(bundle),csv=linkedResultsCsv(bundle);
 assert(csv.includes('interpretation_output_ids'));assert(csv.includes('[""i1"",""i2""]'));
 assert(csv.includes('r1'));assert(!csv.includes('Exact 한글'));
 assert.equal(JSON.parse(files['interpretations.json'])[0].text,bundle.interpretations[0].text);
 assert.equal(JSON.parse(files['manifest.json']).counts.results,2);
 const complete=linkedCompleteCsv({...bundle,executions:bundle.run_tags.map(t=>({run_tag:t,results:bundle.results.filter(r=>r.run_tag===t)}))});
 assert(complete.includes('"old"'));assert(complete.includes('"retry"'));assert(complete.includes('r1'));assert(complete.includes('explanation_output_ids'));
});

test('rejects dangling, cross-execution, duplicate and incomplete relationships',()=>{
 for(const mutate of [b=>b.results[0].interpretation_output_ids.push('missing'),
  b=>b.interpretations[0].run_tag='retry',b=>b.interpretations.push(b.interpretations[0]),
  b=>b.interpretations[0].result_uids=[],b=>b.results.push(b.results[0]),b=>delete b.requested_run_tags]){
  const b=fixture();mutate(b);assert.throws(()=>validateLinkedExport(b));
 }
 const orphan=fixture();orphan.explanations.push({output_id:'orphan',run_tag:'old',text:'Unlinked legacy output',result_uids:[]});
 validateLinkedExport(orphan);assert.equal(JSON.parse(linkedExportFiles(orphan)['manifest.json']).counts.unlinked_explanations,1);
});

test('ZIP CRC and contents round-trip through independent Python zipfile',()=>{
 assert.equal(crc32(new TextEncoder().encode('123456789')),0xcbf43926);
 const files=linkedExportFiles(fixture()),zip=zipFiles(files);
 const output=execFileSync('python3',['-c',
  'import io,sys,zipfile,json; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; print(json.dumps({n:z.read(n).decode("utf-8") for n in z.namelist()}))'],{input:zip,encoding:'utf8'});
 assert.deepEqual(JSON.parse(output),files);
 assert.throws(()=>zipFiles({'../escape.txt':'x'}));
});

test('reader requests continued scope and fails closed on unavailable API',async()=>{
 const original=globalThis.fetch;const calls=[];
 try{
  globalThis.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>fixture()};};
  const bundle=await readLinkedExport(['retry','retry'],true);
  assert.equal(bundle.results.length,2);assert(calls[0].includes('include_evidence=true'));
  globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'Archive unavailable'})});
  await assert.rejects(()=>readLinkedExport(['retry']),/Archive unavailable/);
 }finally{globalThis.fetch=original;}
});
