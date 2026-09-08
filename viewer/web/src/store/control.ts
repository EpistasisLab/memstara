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

/** The seven fields a run takes. The same names the service's allow-list uses, so a typo
 *  here comes back as a 400 naming the field rather than being silently dropped. */
export interface RunRequest {
  skill: string;
  trials: number;
  waves: number;
  /** How many hypothesis workers seed the board at once, and **the only stage count on
   *  this form**. The meeting of 2026-08-26 fixed one data, one ml and one interpreter
   *  for V1, so those three are not offered here; they are still free on the command
   *  line, where whatever number results is drawn as one character with the count on it.
   *
   *  The ceiling of 3 is not enforced here. `src/memstara/control/request.py` holds it,
   *  and this form is deliberately not a validator — a 4 comes back as the service's own
   *  sentence naming the field, which is one place deciding what a legal request is
   *  instead of two. */
  hypothesis_agents: number;
  y_column: string;
  provider: string;
  model: string;
}

/** `y_column` is the cohort's real outcome column, not `board.py:1810`'s CLI default.
 *
 *  That default is the string `outcome`, which is a placeholder rather than a column: the
 *  dataset's 1394 headers are the matcher catalogue's 1393 features plus `HIV_DETECTABLE`,
 *  and nothing is called `outcome`. On the command line the placeholder is defensible —
 *  `check_environment` (`src/memstara/pipeline/board.py:390-410`) refuses the run and names
 *  the file, which forces the choice to be made explicitly. Copied into a form's initial
 *  value it is not: pressing Start with the field untouched failed every time with
 *  "--y-column 'outcome' is not a column in the dataset".
 *
 *  This is the one place it is legitimate to name that column. It is the target, and it is
 *  never a feature — the catalogue the data stage picks columns from does not contain it,
 *  which is what keeps it out of every agent's reach. */
export const DEFAULT_REQUEST: RunRequest = {
  skill: "",
  trials: 3,
  waves: 1,
  hypothesis_agents: 1,
  y_column: "HIV_DETECTABLE",
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

  /** Which run the transcript below belongs to. Null when this service has started
   *  nothing — which is not the same as a run that has printed nothing yet. */
  logTag: string | null;
  /** Complete lines only, oldest first, capped at `LOG_LINES`. */
  logLines: string[];
  /** The unterminated remainder of the last slice. A response ends on a byte boundary,
   *  not a line one, so the tail is held back until the newline that finishes it
   *  arrives — otherwise every poll would append half a line and then a whole one. */
  logTail: string;
  /** Bytes the service jumped over because the log outran one response. Shown, never
   *  swallowed: a gap in a transcript that does not announce itself is a lie. */
  logSkipped: number;
  /** Byte offset to ask from next. */
  logOffset: number;

  poll: () => Promise<void>;
  loadSkills: () => Promise<void>;
  startRun: (body: RunRequest) => Promise<void>;
  stopRun: () => Promise<void>;
  pollLog: () => Promise<void>;
}

/** How many lines the transcript keeps. A long run prints tens of thousands, and a
 *  browser holding every one of them in a scroll region is what makes a viewer that was
 *  fine for ten minutes unusable after an hour. */
const LOG_LINES = 2000;

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

  logTag: null,
  logLines: [],
  logTail: "",
  logSkipped: 0,
  logOffset: 0,

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

  /**
   * Fetch whatever the newest run has printed since the last time we asked.
   *
   * `latest` rather than a tag this store tracks: the service already knows which run is
   * going and which one finished most recently, and a tag chosen here would be a second
   * opinion about that — stale for exactly as long as it took the next poll to notice.
   * The answer names the tag it read, which is what the screen shows.
   *
   * The log is only ever the console of a run **this service started**. A pipeline
   * launched by hand in a terminal has a console.log of its own that this process has no
   * way to find, and `LogPanel` says so rather than showing an empty box.
   */
  pollLog: async () => {
    try {
      const res = await fetch(`/control/runs/latest/log?offset=${get().logOffset}`);
      if (res.status === 404) {
        // No run at all. Not an error: this is the state of the screen before anyone has
        // pressed Start, and it must not read as a fault.
        set({ logTag: null, logLines: [], logTail: "", logSkipped: 0, logOffset: 0 });
        return;
      }
      if (!res.ok) throw new Error(await readError(res));
      const body = await res.json();

      if (body.run_tag !== get().logTag) {
        // A different run than the transcript on screen. The offset we just sent was
        // measured against the previous run's file, so this slice may start anywhere in
        // the new one — it is dropped, and the next poll asks from the beginning. One
        // tick of delay, against the alternative of splicing two runs into one column.
        set({ logTag: body.run_tag, logLines: [], logTail: "", logSkipped: 0, logOffset: 0 });
        return;
      }

      set((s) => {
        const parts = (s.logTail + body.text).split("\n");
        const tail = parts.pop() ?? "";
        const lines = parts.length ? [...s.logLines, ...parts] : s.logLines;
        return {
          logLines: lines.length > LOG_LINES ? lines.slice(lines.length - LOG_LINES) : lines,
          logTail: tail,
          logSkipped: s.logSkipped + (body.skipped ?? 0),
          logOffset: body.offset ?? s.logOffset,
        };
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
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
