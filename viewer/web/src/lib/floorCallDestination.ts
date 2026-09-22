/** Display categories are not SQL audit records. A tool can touch several tables. */
export function floorCallDestination(tool: string, place: string): string | null {
  if (['read_questions','read_question_catalog','propose_questions','claim_question','record_question_outcomes','submit_result','recover_interpretation'].includes(tool)) return 'database';
  if (tool === 'read_results') return 'results';
  if (['create_task','claim_task','read_board','count_waiting','attach_match_trace'].includes(tool)) return 'board';
  if (place === 'board' || place === 'results') return 'database';
  return ['okf','dataset','matcher','ml'].includes(place) ? place : null;
}
export function floorCallCategory(tool: string, place: string): string {
  const destination = floorCallDestination(tool, place);
  if (destination === 'database') return 'Memstara DB service · table scope depends on the call';
  return ({okf:'Knowledge access',dataset:'Dataset inspection / extraction',matcher:'Concept-to-column mapping',ml:'Model training / evaluation',board:'Task-board operations',results:'Completed-result retrieval'} as Record<string,string>)[destination??''] ?? 'Unclassified tool';
}
