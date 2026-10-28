import { displayText } from './displayText.ts';
import type { Result } from '../types';

/** A display heading quoted from saved AI output, never a new clinical claim or a rename. */
export function findingHeading(hypothesis: string | null | undefined): string {
  const text = displayText(hypothesis).replace(/\s+/g, ' ').trim();
  if (text.length <= 160) return text;
  const end = text.lastIndexOf(' ', 157);
  return `${text.slice(0, end > 100 ? end : 157)}…`;
}

/** The first recorded hypothesis gives an execution a stable descriptive heading. */
export function firstFinding(results: Result[], runTag: string): Result | undefined {
  return results.filter(r => r.run_tag === runTag && r.hypothesis?.trim())
    .sort((a, b) => a.trial - b.trial || a.result_id - b.result_id)[0];
}
