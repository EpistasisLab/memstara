import { create } from 'zustand';
import {DEFAULT_TILE_FILTERS, type TileFilters} from '../lib/outputTileFilters';

/** Shared by all three output views; each execution keeps its own selection. */
export const useOutputNavigation = create<{
  selection: {tag: string; loop: number} | null;
  filters: Record<string, TileFilters>;
  setFilters: (scope: string, value: Partial<TileFilters>) => void;
  open: (tag: string, loop: number) => void;
  back: () => void;
}>(set => ({selection: null, filters: {},
  setFilters: (scope, value) => set(state => ({filters: {...state.filters, [scope]: {...(state.filters[scope] ?? DEFAULT_TILE_FILTERS), ...value}}})),
  open: (tag, loop) => set({selection: {tag, loop}}), back: () => set({selection: null})}));
