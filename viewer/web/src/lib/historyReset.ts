/** Execution selections and receipts only; settings/drafts/theme are preserved. */
export const historyRevisionKey = 'memstara-history-revision-v1';
export const historyNoticeKey = 'memstara-history-clear-notice-v1';
export const historyRequestKey = 'memstara-history-clear-request-v1';
export const executionStorageKeys = ['memstara-selection-v1', 'memstara-output-read-v1', 'memstara-results-read-v1'];
/** crypto.randomUUID is unavailable on the installation's plain HTTP LAN origin. */
export function resetRequestId() {
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function clearExecutionStorage(storage: Pick<Storage,'removeItem'|'setItem'>, revision:string) {
  for (const key of executionStorageKeys) storage.removeItem(key);
  storage.setItem('memstara-selection-v1', JSON.stringify({runTag:null}));
  storage.setItem(historyRevisionKey,revision);
}
export type HistoryResetState = {
  id?:string; request_id?:string; state:string; mode?:'backup'|'no_backup'; revision:string;
  scope?:'all'|'selected'; pipeline_id?:string|null; pipeline_name?:string|null; execution_count?:number;
  message?:string; blocked?:boolean; deletion_started?:boolean; failed_phase?:string;
  error_code?:string; error_type?:string; updated_at?:number;
  backup?:{id:string;location:string;download:string};
};
export const resetActive = (state?:HistoryResetState|null) => !!state &&
  ['stopping','validating','backing_up','clearing_databases','clearing_files','verifying'].includes(state.state);
export const resetPhaseLabels:Record<string,string> = {
  stopping:'Ending active executions safely…', validating:'Checking deletion scope and preserved settings…',
  backing_up:'Backing up and verifying both databases and execution files…',
  clearing_databases:'Clearing execution database records…', clearing_files:'Removing execution files…',
  verifying:'Verifying the selected history is cleared and settings are unchanged…',
};
