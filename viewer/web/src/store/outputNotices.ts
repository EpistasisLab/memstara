import { create } from 'zustand';

const storageKey = 'memstara-output-read-v1';
type Receipts = Record<string, true>;
function restore(): Receipts {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey) || '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([key, read]) => read === true && /:(report|agents):\d+:[a-z0-9]+$/.test(key)));
  } catch { return {}; }
}

export const useOutputNotices = create<{read: Receipts; acknowledge: (keys: string[]) => void}>((set, get) => ({
  read: restore(),
  acknowledge: keys => {
    const unread = keys.filter(key => !get().read[key]);
    if (!unread.length) return;
    const read = {...get().read, ...Object.fromEntries(unread.map(key => [key, true as const]))};
    set({read});
    try { localStorage.setItem(storageKey, JSON.stringify(read)); } catch { /* Keep session receipts when storage is blocked. */ }
  },
}));

window.addEventListener('storage', event => {
  if (event.key === storageKey) useOutputNotices.setState({read: restore()});
});
