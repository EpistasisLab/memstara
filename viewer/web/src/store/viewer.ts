import { useContext } from 'react';
import { SnapshotScope } from '../lib/SnapshotScope';
import { create } from "zustand";
import type { Snapshot } from "../types";

const SELECTION_KEY = "memstara-selection-v1";
function restoredSelection(): string | null | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(SELECTION_KEY) ?? "{}");
    return value.runTag === null || typeof value.runTag === "string" ? value.runTag
      : localStorage.getItem("memstara-draft-v1") ? null : undefined;
  } catch { return undefined; }
}
const initialSelection = restoredSelection();

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
export type ViewId = "discovery" | "clinician" | "chain" | "scene" | "log" | "report" | "board" | "task" | "agents" | "access";

interface ViewerState {
  snapshot: Snapshot | null;
  /** Null until the first response; distinguishes "loading" from "empty". */
  loading: boolean;
  /** Set when the API itself is unreachable — different from a database being down. */
  error: string | null;
  runTag: string | null;
  knownRuns: Snapshot["runs"];
  /** True when the user is preparing a new run rather than browsing a saved one. */
  newRunMode: boolean;
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

  setView: (v: ViewId) => void;
  toggleRail: () => void;
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
  loading: initialSelection !== null,
  error: null,
  runTag: initialSelection ?? null,
  knownRuns: [],
  newRunMode: initialSelection === null,
  view: (() => {
    try { return "scene" as ViewId; }
    catch { return "scene" as ViewId; }
  })(),
  selectedTask: null,
  selectedAgent: null,
  ticks: 0,
  fetchedAt: null,
  railCollapsed: false,

  setView: (view) => {
    try { localStorage.setItem("memstara-workspace-v1", view === "clinician" ? "clinician" : "research"); } catch { /* Session still works. */ }
    set({ view });
  },
  toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
  setRunTag: (runTag) => {
    try { localStorage.setItem(SELECTION_KEY, JSON.stringify({ runTag })); } catch { /* Session still works. */ }
    set({
      knownRuns: get().snapshot?.runs ?? get().knownRuns,
      runTag,
      newRunMode: runTag === null,
      snapshot: null,
      // A null tag is an intentional "new run" state, not an API load.
      loading: runTag !== null,
      error: null,
      fetchedAt: null,
      selectedTask: null,
    });
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
    if (get().newRunMode) {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch("/api/runs", { signal: AbortSignal.timeout(10000) });
        if (response.ok) set({ knownRuns: (await response.json()).runs ?? [] });
      } catch { /* Retain the last run index; the draft does not depend on the API. */ }
      finally { inFlight = false; }
      return;
    }
    if (inFlight) return;
    inFlight = true;
    // Cleared here rather than after the request: a switch that arrives *during* this
    // fetch must still be honoured when it finishes.
    refetchWanted = false;
    // The run this request is for. `runTag` can change while it is open — that is exactly
    // what clicking the run selector does — and the response carries nothing that says
    // which of the two it answered, so the question has to be asked before sending.
    let askedFor = get().runTag;
    try {
      // Bootstrap through the lightweight run index. The old no-tag snapshot had to
      // discover the latest run and assemble all five panels in the same request; on a
      // cold refresh that could occupy the API worker long enough for the browser to
      // report `signal timed out`. Once the tag is known, the normal scoped snapshot is
      // both smaller and independently cacheable.
      if (!askedFor) {
        const runsRes = await fetch("/api/runs", { signal: AbortSignal.timeout(10000) });
        if (!runsRes.ok) throw new Error(`${runsRes.status} ${runsRes.statusText}`);
        const runs = (await runsRes.json()).runs as Array<{ run_tag?: string }>;
        if (get().newRunMode || get().runTag !== askedFor) return;
        const latest = runs[0]?.run_tag;
        if (latest) {
          askedFor = latest;
          set({ runTag: latest, newRunMode: false });
        }
      }
      const url = askedFor
        ? `/api/snapshot?run_tag=${encodeURIComponent(askedFor)}`
        : "/api/snapshot";
      // The API returns a structured degraded snapshot after four seconds. Keep the
      // browser timeout slightly above that ceiling so it never sits in Loading after
      // the API has already decided what happened.
      const res = await fetch(url, { signal: AbortSignal.timeout(12000) });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const snapshot: Snapshot = await res.json();
      // Left this run while its answer was in the air. Applying it would draw one run's
      // board, results and feed under another run's label, which reads as a wrong run
      // rather than as a late one.
      if (get().runTag !== askedFor) {
        refetchWanted = true;
        return;
      }
      const previous = get().snapshot;
      if (previous?.run_tag === snapshot.run_tag) {
        if (!snapshot.health.memstara.up) {
          snapshot.board = previous.board; snapshot.results = previous.results; snapshot.stale = true;
        }
        if (!snapshot.health.core.up) {
          snapshot.scene = previous.scene; snapshot.agents = previous.agents;
          snapshot.feed = previous.feed; snapshot.access = previous.access; snapshot.stale = true;
        }
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
export function useSnapshot() {
  const scoped = useContext(SnapshotScope);
  const global = useViewer(s => s.snapshot);
  return scoped === undefined ? global : scoped;
}
export const useScene = () => useSnapshot()?.scene ?? null;
export const useBoard = () => useSnapshot()?.board ?? null;
export const useHealth = () => useSnapshot()?.health ?? null;
export const useAccess = () => useSnapshot()?.access ?? null;
export const useResults = () => useSnapshot()?.results ?? null;
export const useAgentTotals = () => useSnapshot()?.agents ?? null;
export const useFeed = () => useSnapshot()?.feed ?? null;
