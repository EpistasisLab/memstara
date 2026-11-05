/** Accept retained ancestors only for the exact latest-execution request. */
export function liveOutputScope(heads:string[],loadedFor:string,groups:Record<string,string[]>={}) {
 const selected=[...new Set(heads)].sort();
 const tags=new Set(selected);
 if(loadedFor===selected.join(','))for(const head of selected)
  for(const tag of groups[head]??[])tags.add(tag);
 return tags;
}
