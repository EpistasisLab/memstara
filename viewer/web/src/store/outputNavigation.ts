import { create } from 'zustand';

/** Shared by all three output views; each execution keeps its own selection. */
export const useOutputNavigation = create<{
  selection: {tag: string; loop: number} | null;
  open: (tag: string, loop: number) => void;
  back: () => void;
}>(set => ({selection: null, open: (tag, loop) => set({selection: {tag, loop}}), back: () => set({selection: null})}));
