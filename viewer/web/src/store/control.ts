import { create } from "zustand";
import { useViewer } from "./viewer";

/**
 * The one thing on this screen that is not read-only, kept in its own store.
 *
 * `/control/` is a different service from `/api/` — a small process on the host, in the
 * sandbox's own environment, because the viewer's container cannot launch a pipeline and
 * its API is deliberately SELECT-only. Two services means two ways to be down, and they
 * are worth telling apart: the viewer working while the control service is missing is
 * the ordinary case (nobody started it), and it must not look like the viewer is broken.
 *
 * So this store polls separately, holds its own error, and never touches the snapshot.
 * The one place the two meet is `start`: on success it hands the new run tag to the
 * viewer store, and the existing 2-second poll shows the run appearing by itself.
 */

export interface Skill {
  /** What `--skill` takes: `terminus_kind=sud`, or a crossing with a comma. */
  skill: string;
  label: string;
  field: string;
  documents: number;
}

export interface RunningRun {
  run_tag: string;
  run_dir: string;
  skill: string;
  pid: number;
  started: string;
}

/** The six fields a run takes. The same names the service's allow-list uses, so a typo
 *  here comes back as a 400 naming the field rather than being silently dropped. */
export interface RunRequest {
  skill: string;
  trials: number;
  waves: number;
  y_column: string;
  provider: string;
  model: string;
}

export const DEFAULT_REQUEST: RunRequest = {
  skill: "",
  trials: 3,
  waves: 1,
  y_column: "outcome",
  provider: "azure_foundry",
  model: "claude-sonnet-4-6",
};

interface ControlState {
  /** Null until the first answer — "not asked yet" is not the same as "not there". */
  up: boolean | null;
  bundle: { path?: string; documents?: number; error?: string } | null;
  skills: Skill[];
  running: RunningRun | null;
  /** The last thing the service refused, shown next to the button that caused it. */
  error: string | null;
  /** A request is in flight; the button is disabled so one press is one run. */
  busy: boolean;

  poll: () => Promise<void>;
  loadSkills: () => Promise<void>;
  startRun: (body: RunRequest) => Promise<void>;
  stopRun: () => Promise<void>;
}

/** The service answers every refusal as `{"error": "..."}`, so the message a person
 *  reads is the one the service wrote rather than a status code. */
async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.error === "string") return body.error;
  } catch {
    /* not JSON; fall through to the status line */
  }
  return `${res.status} ${res.statusText}`;
}

export const useControl = create<ControlState>((set, get) => ({
  up: null,
  bundle: null,
  skills: [],
  running: null,
  error: null,
  busy: false,

  poll: async () => {
    try {
      const res = await fetch("/control/health");
      if (!res.ok) throw new Error(await readError(res));
      const body = await res.json();
      const wasDown = get().up !== true;
      set({ up: true, bundle: body.bundle ?? null, running: body.running ?? null });
      // Only when it comes back, not on every tick: the branch list is one read of a
      // 312-document bundle and it does not change while a service is up.
      if (wasDown || get().skills.length === 0) void get().loadSkills();
    } catch {
      // No error message here. A control service nobody started is the normal state of
      // this screen, and writing "failed to fetch" under the dot every two seconds
      // would make the ordinary case look like a fault.
      set({ up: false, running: null });
    }
  },

  loadSkills: async () => {
    try {
      const res = await fetch("/control/skills");
      if (!res.ok) throw new Error(await readError(res));
      const body = await res.json();
      set({ skills: body.skills ?? [] });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  startRun: async (body) => {
    set({ busy: true, error: null });
    try {
      const res = await fetch("/control/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await readError(res));
      const run: RunningRun = await res.json();
      set({ running: run });
      // The one line where the two stores meet. The run has no rows on the board yet —
      // selecting it now means the poll that is already running shows it filling up,
      // instead of the person having to find it in the list a minute later.
      useViewer.getState().setRunTag(run.run_tag);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ busy: false });
    }
  },

  stopRun: async () => {
    const tag = get().running?.run_tag;
    if (!tag) return;
    set({ busy: true, error: null });
    try {
      const res = await fetch(`/control/runs/${encodeURIComponent(tag)}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) throw new Error(await readError(res));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ busy: false });
    }
  },
}));
