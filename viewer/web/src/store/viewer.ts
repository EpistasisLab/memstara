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
/** Set when the store is knowingly holding data for the wrong run, so the fetch that is
 *  open right now re-runs the moment it finishes instead of waiting out the interval.
 *  Deliberately *not* set by an ordinary dropped tick: under load a snapshot can take
 *  several times POLL_MS, and re-firing for every tick it swallowed would turn a busy
 *  database into a continuously polled one. Only a run switch sets it. */
let refetchWanted = false;

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
    // A user action, so it must actually happen. If a request for the run being left is
    // still open, the call below is swallowed by `inFlight` and the new run would not be
    // asked for until the next tick — up to POLL_MS of the old run's board, results and
    // feed sitting under the new run's label.
    refetchWanted = true;
    void get().fetchOnce();
  },
  selectTask: (selectedTask) => set({ selectedTask, view: selectedTask ? "task" : get().view }),
  selectAgent: (selectedAgent) => set({ selectedAgent }),

  fetchOnce: async () => {
    if (inFlight) return;
    inFlight = true;
    // Cleared here rather than after the request: a switch that arrives *during* this
    // fetch must still be honoured when it finishes.
    refetchWanted = false;
    // The run this request is for. `runTag` can change while it is open — that is exactly
    // what clicking the run selector does — and the response carries nothing that says
    // which of the two it answered, so the question has to be asked before sending.
    const askedFor = get().runTag;
    try {
      const url = askedFor
        ? `/api/snapshot?run_tag=${encodeURIComponent(askedFor)}`
        : "/api/snapshot";
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const snapshot: Snapshot = await res.json();
      // Left this run while its answer was in the air. Applying it would draw one run's
      // board, results and feed under another run's label, which reads as a wrong run
      // rather than as a late one.
      if (get().runTag !== askedFor) {
        refetchWanted = true;
        return;
      }
      set((s) => ({
        snapshot,
        loading: false,
        error: null,
        ticks: s.ticks + 1,
        fetchedAt: Date.now(),
        // Adopt whichever run the API settled on, so the selector shows the truth
        // rather than staying null forever. `s.runTag` is `askedFor` by the check
        // above, so this only ever fires on the very first response.
        runTag: s.runTag ?? snapshot.run_tag,
      }));
    } catch (e) {
      // A failure belonging to a run nobody is looking at any more is not worth putting
      // a badge on the screen for; the retry below will produce a current one if the
      // API really is down.
      if (get().runTag !== askedFor) {
        refetchWanted = true;
        return;
      }
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    } finally {
      inFlight = false;
      // Terminates: the recursive call clears the flag before doing anything, and only a
      // user switching runs can set it again.
      if (refetchWanted) void get().fetchOnce();
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
