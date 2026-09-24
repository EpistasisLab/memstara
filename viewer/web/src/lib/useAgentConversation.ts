import { useEffect, useState } from 'react';
export type AgentMessage={id:string;run_id:string;stage:string;name:string;label:string;kind:string;kind_label:string;at:string|null;loop:number|null;text:string;truncated:boolean};
export function useAgentConversation(runTag:string|null,loop:number|null){
  const key=`${runTag}:${loop}`;
  const [record,setRecord]=useState<{key:string;messages:AgentMessage[];limited:boolean;note?:string}|null>(null);
  const [failure,setFailure]=useState<{key:string;text:string}|null>(null);
  useEffect(()=>{
    if(!runTag)return;
    let disposed=false;let timer:ReturnType<typeof setTimeout>;let controller:AbortController;
    const poll=async()=>{
      controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),10000);
      try{
        const r=await fetch(`/api/telemetry/conversation?run_tag=${encodeURIComponent(runTag)}${loop===null?'':`&loop=${loop}`}`,{signal:controller.signal});
        const body=await r.json();if(!r.ok)throw Error(body.detail||'Agent text is temporarily unavailable');
        if(body.run_tag!==runTag||body.loop!==loop)throw Error('Conversation scope mismatch');
        if(!disposed){setRecord({key,messages:body.messages,limited:body.limited,note:body.note});setFailure(null);}
      }catch(e){if(!disposed)setFailure({key,text:e instanceof Error?(e.name==='AbortError'?'Agent text timed out; retrying.':e.message):'Agent text unavailable'});}
      finally{clearTimeout(deadline);if(!disposed)timer=setTimeout(poll,4000);}
    };
    void poll();return()=>{disposed=true;clearTimeout(timer);controller?.abort();};
  },[runTag,loop,key]);
  return {data:record?.key===key?record:null,error:failure?.key===key?failure.text:''};
}
