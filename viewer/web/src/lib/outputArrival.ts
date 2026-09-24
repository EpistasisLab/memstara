/** Polling the same record twice must not create a second arrival. */
export function outputArrivals<T extends { id:string; revision:string }>(versions:Map<string,string>, incoming:T[], receivedAt:number, fresh:boolean) {
  const next=new Map(versions);
  const arrivals=incoming.filter(event=>{
    const changed=next.get(event.id)!==event.revision;
    next.set(event.id,event.revision);
    return changed;
  }).map(event=>({...event,receivedAt,fresh}));
  if(next.size>6000)for(const key of [...next.keys()].slice(0,next.size-4000))next.delete(key);
  return {arrivals,versions:next};
}
