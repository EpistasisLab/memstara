import {scheduledLabel, type Schedule} from './replicateIdentity.ts';
import { displayText } from './displayText.ts';

/** Presentation only: stored identifiers remain unchanged. */
export function agentDisplayName(name: string): string {
  return displayText(name.replace(/[-· ]*board_\d{8}T\d{6}(?:_\d+)?$/, '').trim());
}
export const TOOL_ACTIONS: Record<string, string> = {
  propose_questions: 'Propose research questions', read_question_catalog: 'Check existing questions',
  claim_question: 'Select a question to investigate', create_task: 'Create an analysis task',
  describe_dataset: 'Inspect available data columns', match_concept: 'Map a clinical concept to data',
  match_concepts: 'Map clinical concepts to data', okf_list_domains: 'List knowledge topics',
  okf_search: 'Search knowledge sources', okf_read: 'Read supporting knowledge',
  claim_task: 'Pick up a task', slice_columns: 'Extract selected data columns',
  train_and_score: 'Train and evaluate a model', submit_result: 'Save results and hand off work',
  read_results: 'Read completed analysis results', read_board: 'Inspect analysis tasks',
};
export function cleanLog(text: string): string {
  // Strip terminal CSI / OSC formatting, never evaluate it as HTML.
  return displayText(text.replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, '')
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, ''));
}

/** Translate human console labels using that execution's frozen schedule only. */
export function executionLog(text:string, plan?:Schedule|null):string {
 return cleanLog(text).replace(/\bLoop (\d+)\b/g,(_,position:string)=>
  plan===undefined?`Scheduled run ${position}`:scheduledLabel(Number(position),plan))
  .replace(/\bLoops\b/g,'scheduled runs');
}
