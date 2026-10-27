import type {Result} from '../types.ts';

export function interpretationOutputs(result: Pick<Result, 'interpretation' | 'evaluation'>) {
  const branches = result.evaluation?.interpretations;
  if (branches?.length) return branches;
  return result.interpretation ? [{slot: 1, worker: '', skill: '', status: 'done',
    text: result.interpretation, error: '', limitations: result.evaluation?.interpretation_limitations ?? ''}] : [];
}
