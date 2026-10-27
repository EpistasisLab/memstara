// Read exact class values from the uploaded CSV; server validation remains authoritative.
// Keep at most two values per column, never retain patient rows or high-cardinality values.
export function csvClassValues(text:string):Record<string,string[]> {
 const missing=new Set(['','?','na','nan','null','none','n/a']);
 const result:Record<string,string[]>=Object.create(null);
 let headers:string[]|null=null, row:string[]=[], field='', quoted=false;
 const overflow=new Set<string>();
 function finishRow(){
  row.push(field);field='';
  if(!headers){headers=row;for(const column of headers)result[column]=[];}
  else {for(let i=0;i<headers.length;i++){
   const column=headers[i],value=row[i]??'';
   if(overflow.has(column)||missing.has(value.trim().toLowerCase()))continue;
   if(!result[column].includes(value))result[column].push(value);
   if(result[column].length>2){result[column]=[];overflow.add(column);}
  }}
  row=[];
 }
 text=text.replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){
  const char=text[i];
  if(quoted){if(char==='"'){if(text[i+1]==='"'){field+='"';i++;}else quoted=false;}else field+=char;}
  else if(char==='"'&&field==='')quoted=true;
  else if(char===','){row.push(field);field='';}
  else if(char==='\r'||char==='\n'){finishRow();if(char==='\r'&&text[i+1]==='\n')i++;}
  else field+=char;
 }
 if(field!==''||row.length)finishRow();
 return result;
}
