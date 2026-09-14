import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { RunRequest } from './control';

export const setupStages = ['hypothesis', 'ml', 'interpreter', 'report'] as const;
export type SetupStage = typeof setupStages[number];
type Review = { paused: boolean; confirmed: Partial<Record<SetupStage, string>> };
export function skillSignature(config: RunRequest, stage: SetupStage) {
  return JSON.stringify([config[`playbook_${stage}`], stage === 'ml' ? config.evaluation : null]);
}
export const usePipelineSetup = create(persist<{
  reviews: Record<string, Review>;
  start: (id: string) => void;
  pause: (id: string, paused: boolean) => void;
  confirm: (id: string, stage: SetupStage, signature: string) => void;
  remove: (id: string) => void;
}>((set) => ({
  reviews: {},
  start: id => set(s => ({ reviews: { ...s.reviews, [id]: { paused: false, confirmed: {} } } })),
  pause: (id, paused) => set(s => ({ reviews: { ...s.reviews, [id]: { ...s.reviews[id], paused } } })),
  confirm: (id, stage, signature) => set(s => ({ reviews: { ...s.reviews,
    [id]: { paused: false, confirmed: { ...s.reviews[id]?.confirmed, [stage]: signature } } } })),
  remove: id => set(s => { const reviews = { ...s.reviews }; delete reviews[id]; return { reviews }; }),
}), { name: 'memstara.pipelineSkillReview.v1' }));
