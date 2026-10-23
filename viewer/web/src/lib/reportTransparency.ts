import { reportLoopText } from './reportLoopText';
import { reportMarkdown } from './reportMarkdown';

export const assessmentNotes = [
  ['Research priority is not clinical readiness', 'Memstara prioritizes informative next experiments. Limited clinical actionability does not by itself make a hypothesis low research priority. Consider its knowledge grounding, the uncertainty it could resolve and a feasible next test. A weak or null result can guide research without being positive evidence. Historical rankings have not been automatically reassessed under this guidance.'],
  ['Replicate references', 'Legacy numbered analysis references retain the original analysis ID and, when available, its schedule position. Pipeline and Replicate identities are shown separately from saved schedule metadata. Source records are unchanged.'],
  ['Measured results', 'AUC and other recorded ML metrics are calculated from model predictions and observed outcomes. They do not by themselves establish causation or clinical usefulness.'],
  ['Evidence strength', 'The explanation agent (LLM) interprets recorded performance, feature importance, knowledge sources, interpreter output and limitations. Labels such as High, Moderate or Low are qualitative judgments, not scores calculated by a fixed formula or standardized grading rubric.'],
  ['Clinical actionability', 'The LLM assesses possible clinical meaning and use from the available interpretation and supporting evidence. This is not an independently validated clinical rating, treatment recommendation or proof of a usable clinical threshold.'],
  ['Novelty', 'An LLM judgment relative to the knowledge sources actually consulted. It is not a systematic search of all published research and does not establish that a hypothesis is the first of its kind.'],
  ['How to use the recommendation', 'Rank, novelty and prioritization decisions also involve LLM interpretation. The same evidence may receive different judgments with different models, prompts or generations. Review the cited evidence and limitations; missing evidence must remain unknown rather than be treated as favorable.'],
] as const;

/** Added by Memstara, rather than attributed to the original report's author. */
export function transparentReportMarkdown(text: string, analysesPerLoop?: number): string {
  return '## How to read this report\n\n'
    + '*Memstara explanatory note — applies to both new and historical reports.*\n\n'
    + assessmentNotes.map(([title, body]) => `- **${title}:** ${body}`).join('\n')
    + '\n\n---\n\n' + reportLoopText(reportMarkdown(text), analysesPerLoop);
}
