import { create } from 'zustand';
import type { Result } from '../types';

const storageKey = 'memstara-results-read-v1';
type ReadResults = Record<string, true>;
const key = (result: Result) => `${result.run_tag}:${result.result_id}`;

/** Only persisted, measured results can make the Results button announce readiness. */
export function measuredResults(results: Result[] = []) {
  return results.filter(result => result.run_tag && Number.isInteger(result.result_id) && result.result_id > 0
    && typeof result.auc === 'number' && Number.isFinite(result.auc) && result.auc >= 0 && result.auc <= 1);
}

export function unreadResults(results: Result[], read: ReadResults) {
  return measuredResults(results).filter(result => !read[key(result)]);
}

export function newestResult(results: Result[] = []) {
  return results.reduce<Result | undefined>((latest, result) => !latest ||
    (Date.parse(result.created_at) || 0) > (Date.parse(latest.created_at) || 0) ||
    ((Date.parse(result.created_at) || 0) === (Date.parse(latest.created_at) || 0) && result.result_id > latest.result_id)
    ? result : latest, undefined);
}

function restore(): ReadResults {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey) || '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([id, seen]) => seen === true && /:\d+$/.test(id)));
  } catch { return {}; }
}

export const useResultNotices = create<{
  read: ReadResults;
  acknowledge: (results: Result[]) => void;
}>((set, get) => ({
  read: restore(),
  acknowledge: results => {
    const unread = unreadResults(results, get().read);
    if (!unread.length) return;
    const read = { ...get().read, ...Object.fromEntries(unread.map(result => [key(result), true as const])) };
    set({ read });
    // Store identifiers only. Experimental records and server state are never changed.
    try { localStorage.setItem(storageKey, JSON.stringify(read)); } catch { /* Session acknowledgement still works. */ }
  },
}));

window.addEventListener('storage', event => {
  if (event.key === storageKey) useResultNotices.setState({ read: restore() });
});
