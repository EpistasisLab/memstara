import {hypothesisSummaryRows,hypothesisSummaryCsv} from './hypothesisSummary.ts';
import {evidenceCollectionToCsv} from './evidenceCsv.ts';

type JsonRecord=Record<string,unknown>;
export type LinkedDocument=JsonRecord & {output_id:string;run_tag:string;text:string;result_uids:string[]};
export type LinkedResult=JsonRecord & {result_uid:string;run_tag:string;result_id:number;
 interpretation_output_ids:string[];explanation_output_ids:string[]};
export type LinkedExport={schema_version:'linked_agent_outputs_v1';generated_at:string;requested_run_tags:string[];
 run_tags:string[];results:LinkedResult[];interpretations:LinkedDocument[];explanations:LinkedDocument[];
 executions:JsonRecord[];warnings:JsonRecord[]};

export function validateLinkedExport(value:LinkedExport):void {
 if(value.schema_version!=='linked_agent_outputs_v1'||!Array.isArray(value.results)||
    !Array.isArray(value.interpretations)||!Array.isArray(value.explanations)||!Array.isArray(value.run_tags)||
    !Array.isArray(value.requested_run_tags)||!Array.isArray(value.executions)||!Array.isArray(value.warnings))
  throw Error('Linked output export is incomplete. No substitute file was downloaded.');
 const results=new Map(value.results.map(r=>[r.result_uid,r]));
 if(results.size!==value.results.length)throw Error('Export contains duplicate result identities.');
 for(const [key,foreign]of [['interpretations','interpretation_output_ids'],['explanations','explanation_output_ids']] as const){
  const documents=new Map(value[key].map(d=>[d.output_id,d]));
  if(documents.size!==value[key].length)throw Error('Export contains duplicate output identities.');
  for(const document of documents.values())if(typeof document.text!=='string'||!Array.isArray(document.result_uids))
   throw Error('An output document is invalid.');
  for(const row of value.results){
   if(!Array.isArray(row[foreign]))throw Error('Result output references are missing.');
   for(const id of row[foreign]){
    const document=documents.get(id);
    if(!document||document.run_tag!==row.run_tag||!document.result_uids.includes(row.result_uid))
     throw Error('An output reference does not match its original result and execution.');
   }
  }
  for(const document of documents.values()){
   if(typeof document.text!=='string'||!Array.isArray(document.result_uids))throw Error('An output document is invalid.');
   for(const id of document.result_uids){
    const row=results.get(id);
    if(!row||row.run_tag!==document.run_tag||!row[foreign].includes(document.output_id))
     throw Error('An output document references a result outside this export.');
   }
  }
 }
}

export async function readLinkedExport(tags:string[],includeEvidence=false,signal?:AbortSignal):Promise<LinkedExport>{
 const selected=[...new Set(tags.filter(Boolean))];
 if(!selected.length)throw Error('Choose a recorded execution first.');
 const query=new URLSearchParams({run_tags:selected.join(','),include_evidence:String(includeEvidence)});
 const response=await fetch(`/api/experiments/linked-export?${query}`,{signal:signal??AbortSignal.timeout(60000)});
 const body=await response.json();
 if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Linked evidence could not be exported.');
 validateLinkedExport(body);
 if(selected.some(t=>!body.requested_run_tags.includes(t)))throw Error('Export execution scope did not match the request.');
 return body;
}

export function linkedResultsCsv(bundle:LinkedExport):string {
 validateLinkedExport(bundle);
 return hypothesisSummaryCsv(hypothesisSummaryRows(bundle.results));
}

export function linkedCompleteCsv(bundle:LinkedExport):string {
 validateLinkedExport(bundle);
 if(!bundle.executions.length)throw Error('Complete evidence was not requested.');
 return evidenceCollectionToCsv(bundle.executions);
}

export function linkedExportFiles(bundle:LinkedExport):Record<string,string>{
 validateLinkedExport(bundle);
 const json=(v:unknown)=>JSON.stringify(v,null,2)+'\n';
 const unresolved=bundle.explanations.filter(d=>!d.result_uids.length).length;
 return {
  'results.csv':linkedResultsCsv(bundle),
  'results.json':json(bundle.results),
  'interpretations.json':json(bundle.interpretations),
  'explanations.json':json(bundle.explanations),
  ...(bundle.executions.length?{'complete_evidence.csv':linkedCompleteCsv(bundle),'complete_evidence.json':json(bundle.executions)}:{}),
  'manifest.json':json({schema_version:bundle.schema_version,generated_at:bundle.generated_at,
   requested_run_tags:bundle.requested_run_tags,run_tags:bundle.run_tags,
   counts:{results:bundle.results.length,interpretations:bundle.interpretations.length,explanations:bundle.explanations.length,unlinked_explanations:unresolved},
   relationships:{result_key:'result_uid',output_key:'output_id',interpretation_foreign_keys:'interpretation_output_ids',explanation_foreign_keys:'explanation_output_ids'},
   warnings:bundle.warnings}),
  'README.txt':`Linked experiment results and agent outputs\n\nSchema: ${bundle.schema_version}\nExported: ${bundle.generated_at}\n\n`+
   'Each results.csv row is an evaluation replicate. result_uid identifies its saved result across those rows.\n'+
   'interpretation_output_ids and explanation_output_ids are JSON arrays of foreign keys, not document text.\n'+
   'Resolve each ID against output_id in interpretations.json or explanations.json. The output result_uids list provides the reverse relationship.\n'+
   'Outputs attach to saved results, not automatically to one fitted model or split. Multiple evaluation rows may share the same result and output IDs.\n'+
   'All IDs include the original execution identity; output IDs also identify the saved content revision. Unchanged documents keep the same IDs on later downloads.\n'+
   'Narratives are exported verbatim in JSON strings, preserving whitespace, Markdown and Unicode. No new agent call or summary was generated.\n'+
   'Missing text has an empty ID list and a not_recorded/partial status. See interpretation_pending for recorded empty or failed branches.\n'+
   'An Explanation may link to several results through recorded result/task IDs. A legacy per-loop output links automatically only when exactly one result exists in that same execution and loop.\n'+
   'Ambiguous or unmatched Explanations remain in explanations.json with no result_uids and a manifest warning. No relationship is guessed from a neighbouring execution.\n'+
   'results.json includes result-level metadata. Complete evidence files include registered configuration, agent, cost and artifact metadata for every continued execution. Registry gaps are explicit in manifest warnings.\n'+
   'This is a read-time snapshot of saved records. Running experiments may have outputs that are not yet recorded. CSV cells use standard quoting; spreadsheet-formula-like strings are escaped. Use JSON for exact text analysis.\n',
 };
}

// Standard ZIP "store" entries: no dependency, no compression worker or server write.
export function crc32(data:Uint8Array):number{
 let crc=0xffffffff;
 for(const byte of data){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}
 return (crc^0xffffffff)>>>0;
}
export function zipFiles(files:Record<string,string>):Uint8Array<ArrayBuffer>{
 const encoder=new TextEncoder(),local:Uint8Array[]=[],central:Uint8Array[]=[];
 let offset=0,centralSize=0;
 const entries=Object.entries(files);
 if(entries.length>65535)throw Error('ZIP contains too many files.');
 for(const [name,content]of entries){
  if(name.includes('..')||name.startsWith('/')||name.includes('\\'))throw Error('Invalid export filename.');
  const filename=encoder.encode(name),data=encoder.encode(content),checksum=crc32(data);
  if(filename.length>65535||data.length>0xffffffff||offset>0xffffffff)throw Error('Export exceeds ZIP32 limits.');
  const header=new Uint8Array(30+filename.length),h=new DataView(header.buffer);
  h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x800,true);h.setUint16(12,33,true);
  h.setUint32(14,checksum,true);h.setUint32(18,data.length,true);h.setUint32(22,data.length,true);h.setUint16(26,filename.length,true);header.set(filename,30);
  const directory=new Uint8Array(46+filename.length),d=new DataView(directory.buffer);
  d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint16(8,0x800,true);d.setUint16(14,33,true);
  d.setUint32(16,checksum,true);d.setUint32(20,data.length,true);d.setUint32(24,data.length,true);d.setUint16(28,filename.length,true);d.setUint32(42,offset,true);directory.set(filename,46);
  local.push(header,data);central.push(directory);offset+=header.length+data.length;centralSize+=directory.length;
 }
 if(offset+centralSize+22>0xffffffff)throw Error('Export exceeds ZIP32 limits.');
 const end=new Uint8Array(22),e=new DataView(end.buffer);
 e.setUint32(0,0x06054b50,true);e.setUint16(8,entries.length,true);e.setUint16(10,entries.length,true);e.setUint32(12,centralSize,true);e.setUint32(16,offset,true);
 const output=new Uint8Array(offset+centralSize+end.length);let position=0;
 for(const chunk of [...local,...central,end]){output.set(chunk,position);position+=chunk.length;}
 return output;
}
