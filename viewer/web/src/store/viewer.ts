import { create } from "zustand";
import type { Snapshot } from "../types";

/**
 * One store, one poller.
 *
 * Every panel fetching its own slice would send a request each per tick and they could
 * disagree with each other about the same run. Instead the store polls `/api/snapshot`
 * once and every panel selects from that single object, so what the scene shows, what
 * the feed shows and what the results panel shows can never be from different moments.
 * That matters most for the feed: a row appearing there but not in the scene would look
 * like a bug in the scene.
 *
 * Polling stops when the tab is hidden. A viewer left open overnight otherwise keeps
 * two databases busy for nobody.
 */

export const POLL_MS = 2000;

/** What the main area shows. Results is not here on purpose: ResultsPanel is always on
 *  screen at bottom-right, so a nav entry for it would be a second door to one room. */
export type ViewId = "chain" | "scene" | "log" | "board" | "task" | "agents" | "access";

interface ViewerState {
  snapshot: Snapshot | null;
  /** Null until the first response; distinguishes "loading" from "empty". */
  loading: boolean;
  /** Set when the API itself is unreachable — different from a database being down. */
  error: string | null;
  runTag: string | null;
  view: ViewId;
  selectedTask: number | null;
  selectedAgent: string | null;
  /** Counts responses, so a stuck poller is visible rather than silently frozen. */
  ticks: number;
  /** `Date.now()` at the last successful response — the browser's clock at both ends, so
   *  "how stale is this screen" stays answerable when the API container's clock disagrees
   *  with this machine's. Null until the first response. */
  fetchedAt: number | null;
  /** Collapses the control panel to an icon rail. */
  railCollapsed: boolean;
  /** Whether the run navigator has a column of its own. On by default: it is the only
   *  place the run's shape — trials, and the stages inside them — is drawn, and a panel
   *  nobody knows to switch on may as well not exist. It is closable because three
   *  columns plus the main area is a lot of width to spend on a laptop. */
  navOpen: boolean;

  setView: (v: ViewId) => void;
  toggleRail: () => void;
  toggleNav: () => void;
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
  view: "chain",
  selectedTask: null,
  selectedAgent: null,
  ticks: 0,
  fetchedAt: null,
  railCollapsed: false,
  navOpen: true,

  setView: (view) => set({ view }),
  toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
  toggleNav: () => set((s) => ({ navOpen: !s.navOpen })),
  setRunTag: (runTag) => {
    set({ runTag, loading: true, selectedTask: null });
    void get().fetchOnce();
  },
  selectTask: (selectedTask) => set({ selectedTask, view: selectedTask ? "task" : get().view }),
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
        fetchedAt: Date.now(),
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
export const useFeed = () => useViewer((s) => s.snapshot?.feed ?? null);
