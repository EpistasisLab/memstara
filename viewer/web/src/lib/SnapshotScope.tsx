import { createContext } from 'react';
import type { Snapshot } from '../types';
/** A scoped reader never mutates the global Floor plan or another open window. */
export const SnapshotScope = createContext<Snapshot | null | undefined>(undefined);
