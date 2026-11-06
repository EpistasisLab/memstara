import {create} from 'zustand';
import {useEffect} from 'react';
import {clearExecutionStorage,historyRevisionKey,historyNoticeKey,historyRequestKey,type HistoryResetState} from '../lib/historyReset';
let reloadQueued=false;
let mutationVersion=0;
function applyRevision(state:HistoryResetState) {
  if(window.name===`memstara-history:${state.revision}`)return;
  let previous='initial';
  try {previous=localStorage.getItem(historyRevisionKey)??'initial';} catch {
    if(window.name.startsWith('memstara-history:'))previous=window.name.slice('memstara-history:'.length);
  }
  if(!state.revision || state.revision===previous || reloadQueued)return;
  reloadQueued=true;
  window.name=`memstara-history:${state.revision}`;
  try {
    if(state.state==='completed'&&sessionStorage.getItem(historyRequestKey)===state.request_id)
      sessionStorage.setItem(historyNoticeKey,JSON.stringify(state));
    clearExecutionStorage(localStorage,state.revision);
  } catch { /* Reload also drops in-memory output caches. */ }
  window.location.reload();
}
export const useHistoryReset=create<{
 state:HistoryResetState|null; error:string|null; submitting:boolean;
 poll:()=>Promise<void>; begin:(mode:'backup'|'no_backup',confirmation:string,requestId:string,scope?:'all'|'selected',pipelineId?:string)=>Promise<void>;
}>((set,get)=>({
 state:null,error:null,submitting:false,
 poll:async()=>{
  const version=mutationVersion;
  try {
   const response=await fetch('/control/history-reset',{cache:'no-store',signal:AbortSignal.timeout(8000)});
   if(!response.ok)return;
   const state=await response.json() as HistoryResetState;
   if(typeof state.state!=='string'||typeof state.revision!=='string')return;
   if(version!==mutationVersion||(state.updated_at??0)<(get().state?.updated_at??0))return;
   set({state});applyRevision(state);
  }catch { /* A lost response is not proof that clearing failed. */ }
 },
 begin:async(mode,confirmation,requestId,scope='all',pipelineId)=>{
  mutationVersion++;
  set({submitting:true,error:null});
  try {
   try{sessionStorage.setItem(historyRequestKey,requestId);}catch{/* Session still works. */}
   const response=await fetch('/control/history-reset',{method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({mode,confirmation,request_id:requestId,scope,...(scope==='selected'?{pipeline_id:pipelineId}:{})}),signal:AbortSignal.timeout(15000)});
   const body=await response.json();
   if(!response.ok)throw new Error(body.error||'History reset could not be requested.');
   set({state:body});applyRevision(body);
  }catch(error){set({error:error instanceof Error?error.message:'The request response was lost. Check the current job before retrying.'});}
  finally{set({submitting:false});}
 },
}));
/** A new server revision reloads all panels and all tabs, including hidden caches. */
export function useHistoryResetMonitor() {
 useEffect(()=>{
  let stopped=false,timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{if(!stopped){await useHistoryReset.getState().poll();if(!stopped)timer=setTimeout(poll,3000);}};
  const storage=(event:StorageEvent)=>{
   if(event.key===historyRevisionKey&&event.newValue&&!reloadQueued){
    reloadQueued=true;
    try{clearExecutionStorage(localStorage,event.newValue);}catch{/* Reload clears session output. */}
    window.location.reload();
   }
  };
  window.addEventListener('storage',storage);void poll();
  return()=>{stopped=true;clearTimeout(timer);window.removeEventListener('storage',storage);};
 },[]);
}
