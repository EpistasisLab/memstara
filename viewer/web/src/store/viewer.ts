import { create } from "zustand";
import type { Snapshot } from "../types";

/**
 * One store, one poller.
 *
 * Six screens each fetching their own slice would send six requests every tick and
 * could disagree with each other about the same run. Instead the store polls
 * `/api/snapshot` once and every screen selects from that single object, so what the
 * scene shows and what the board tab shows can never be from different moments.
 *
 * Polling stops when the tab is hidden. A viewer left open overnight otherwise keeps
 * two databases busy for nobody.
 */

export const POLL_MS = 2000;

export type TabId = "scene" | "board" | "task" | "agents" | "access" | "results";

interface ViewerState {
  snapshot: Snapshot | null;
  /** Null until the first response; distinguishes "loading" from "empty". */
  loading: boolean;
  /** Set when the API itself is unreachable — different from a database being down. */
  error: string | null;
  runTag: string | null;
  tab: TabId;
  selectedTask: number | null;
  selectedAgent: string | null;
  /** Counts responses, so a stuck poller is visible rather than silently frozen. */
  ticks: number;

  setTab: (t: TabId) => void;
  setRunTag: (t: string | null) => void;
  selectTask: (id: number | null) => void;
  selectAgent: (id: string | null) => void;
  fetchOnce: () => Promise<void>;
  start: () => void;
  stop: () => void;
}

let timer: ReturnType<typeof setInterval> | null = null;
let visibilityBound = false;
/** Guards against overlapping requests when a tick is slower than the interval. */
let inFlight = false;

export const useViewer = create<ViewerState>((set, get) => ({
  snapshot: null,
  loading: true,
  error: null,
  runTag: null,
  tab: "scene",
  selectedTask: null,
  selectedAgent: null,
  ticks: 0,

  setTab: (tab) => set({ tab }),
  setRunTag: (runTag) => {
    set({ runTag, loading: true, selectedTask: null });
    void get().fetchOnce();
  },
  selectTask: (selectedTask) => set({ selectedTask, tab: selectedTask ? "task" : get().tab }),
  selectAgent: (selectedAgent) => set({ selectedAgent }),

  fetchOnce: async () => {
    if (inFlight) return;
    inFlight = true;
    try {
      const { runTag } = get();
      const url = runTag ? `/api/snapshot?run_tag=${encodeURIComponent(runTag)}` : "/api/snapshot";
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const snapshot: Snapshot = await res.json();
      set((s) => ({
        snapshot,
        loading: false,
        error: null,
        ticks: s.ticks + 1,
        // Adopt whichever run the API settled on, so the selector shows the truth
        // rather than staying null forever.
        runTag: s.runTag ?? snapshot.run_tag,
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    } finally {
      inFlight = false;
    }
  },

  start: () => {
    if (timer) return;
    void get().fetchOnce();
    timer = setInterval(() => void get().fetchOnce(), POLL_MS);

    if (!visibilityBound) {
      visibilityBound = true;
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) get().stop();
        else get().start();
      });
    }
  },

  stop: () => {
    if (timer) clearInterval(timer);
    timer = null;
  },
}));

// Selectors. Components subscribe to the slice they draw, so a board update does not
// re-render the results table.
export const useScene = () => useViewer((s) => s.snapshot?.scene ?? null);
export const useBoard = () => useViewer((s) => s.snapshot?.board ?? null);
export const useHealth = () => useViewer((s) => s.snapshot?.health ?? null);
export const useAccess = () => useViewer((s) => s.snapshot?.access ?? null);
export const useResults = () => useViewer((s) => s.snapshot?.results ?? null);
export const useAgentTotals = () => useViewer((s) => s.snapshot?.agents ?? null);
