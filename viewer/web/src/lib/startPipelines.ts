type Item = {id:string; name:string; latest?:{recoverable?:boolean;recovery_blocked?:string}|null; running:{run_tag:string; pause_requested?:boolean; execution_state?:string} | null};
export type StartOutcome = {id:string; name:string; status:'started'|'resumed'|'skipped'|'failed'; detail:string};

/** Launch requests are short; each launched process runs independently. Stop can
 * cancel the remaining requests without rolling back successfully started work. */
export async function startPipelines(items:Item[], launch:(item:Item, resume:boolean)=>Promise<void>, cancelled:()=>boolean):Promise<StartOutcome[]> {
  const outcomes:StartOutcome[]=[];
  for(const item of items){
    if(cancelled()){outcomes.push({id:item.id,name:item.name,status:'skipped',detail:'Start cancelled by Stop all.'});continue;}
    if(!item.running&&(item.latest?.recoverable||item.latest?.recovery_blocked)){outcomes.push({id:item.id,name:item.name,status:'skipped',detail:'Review recovery in the pipeline list before starting another execution.'});continue;}
    if(!item.running&&item.latest){outcomes.push({id:item.id,name:item.name,status:'skipped',detail:'Choose additional analysis and its replicate count in the pipeline list.'});continue;}
    const resume=!!item.running&&(item.running.execution_state==='paused'||!!item.running.pause_requested);
    if(item.running&&!resume){outcomes.push({id:item.id,name:item.name,status:'skipped',detail:'Already running.'});continue;}
    try{await launch(item,resume);outcomes.push({id:item.id,name:item.name,status:resume?'resumed':'started',detail:resume?'Resumed existing execution.':'Started with saved settings and Replicate limit.'});}
    catch(e){outcomes.push({id:item.id,name:item.name,status:'failed',detail:String(e)});}
  }
  return outcomes;
}
