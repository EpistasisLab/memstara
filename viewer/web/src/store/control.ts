import { create } from "zustand";
import { useViewer } from "./viewer";
import type { RunConfiguration } from "../types";

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
  configuration?: RunConfiguration;
  run_tag: string;
  run_dir: string;
  skill: string;
  pid: number;
  started: string;
}

/** The five stages a playbook can be attached to, in the order the form lays them out.
 *
 *  A third copy of `board.py:1138`'s tuple — the second is `PLAYBOOK_STAGES` in
 *  `src/memstara/control/request.py`, and `tests/test_control_request.py` compares that
 *  one against the driver. This copy is not compared against anything, and it does not
 *  need to be: a stage named here that the service does not know comes back as a 400
 *  naming the field, and a stage the service knows that is missing here simply does not
 *  appear on the form. Neither is silent.
 *
 *  **Which of them can actually take one is not decided here.** A prompt has to carry a
 *  `{{playbook}}` line, and `GET /control/playbooks` reads the prompt files to say which
 *  do. The form renders that answer, so marking a third prompt grows this form with no
 *  edit to this file. */
export const PLAYBOOK_STAGES = ["hypothesis", "data", "ml", "interpreter", "report"] as const;
export type PlaybookStage = (typeof PLAYBOOK_STAGES)[number];

/** The twelve fields a run takes. The same names the service's allow-list uses, so a typo
 *  here comes back as a 400 naming the field rather than being silently dropped. */
export type EvaluationPlan = { engine: string; seed: number; test_size: number; folds: number; replicates: number; search_trials: number };
export type SkillInfo = { evaluation?: Partial<EvaluationPlan>; id: string; title: string; stage: PlaybookStage; description: string; content: string; hash: string; source: string };
export type RunRequest = {
  question: string;
  evaluation: EvaluationPlan;
  skill: string;
  trials: number;
  waves: number;
  /** How many hypothesis workers seed the board at once, and **the only stage count on
   *  this form**. The meeting of 2026-08-26 fixed one data, one ml and one interpreter
   *  for V1, so those three are not offered here; they are still free on the command
   *  line, where whatever number results is drawn as one character with the count on it.
   *
   *  The ceiling of 8 is not enforced here. `src/memstara/control/request.py` holds it,
   *  and this form is deliberately not a validator — a 9 comes back as the service's own
   *  sentence naming the field, which is one place deciding what a legal request is
   *  instead of two. (It was 3 until `d34ebe7`, which is what the floor plan's fixed-step
   *  fan could draw; the fan now divides its envelope, so the drawing no longer caps the
   *  number.) */
  hypothesis_agents: number;
  interpret_agents: number;
  y_column: string;
  provider: string;
  model: string;
} & {
  /** One key per stage — `playbook_ml` — holding a playbook's stem or `""` for the
   *  prompt as written. Written as a mapped type rather than five lines so that the
   *  form can index it with a stage name it got from the service and still be checked.
   *
   *  Per-stage and not one `playbook` box because a run legitimately gives different
   *  stages different standards, and because the service refuses a standard aimed at a
   *  prompt that cannot receive one — a single box would have nowhere to say which
   *  stage it was for.
   *
   *  **`playbook_hypothesis` may hold several stems separated by commas, one per agent**
   *  (`A-32`): that stage provisions an agent per standard, so `hypothesis_agents: 3`
   *  with three names is three agents that can disagree. The type stays `string` for all
   *  five rather than becoming `string | string[]` for one, because the value is a
   *  command-line argument and `--playbook-hypothesis` takes one. `StartRun.tsx` is the
   *  only place that splits it. */
  [S in PlaybookStage as `playbook_${S}`]: string;
};

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
  question: "",
  evaluation: { engine: "xgboost", seed: 42, test_size: .25, folds: 0, replicates: 1, search_trials: 1 },
  skill: "",
  trials: 3,
  waves: 1,
  hypothesis_agents: 1,
  interpret_agents: 1,
  y_column: "HIV_DETECTABLE",
  provider: "azure_foundry",
  model: "claude-sonnet-4-6",
  // Empty is "the prompt as written", which is what every run before 2026-09-08 was and
  // what the form must still start as. A default playbook would make a standard the
  // silent condition of every run on this screen, and the run record would show it as
  // deliberate.
  playbook_hypothesis: "treatment-toxicity",
  playbook_data: "",
  playbook_ml: "ml_governance",
  playbook_interpreter: "interpreter_review_pending",
  playbook_report: "report_evidence",
};

interface ControlState {
  preview: boolean;
  catalog: SkillInfo[];
  editor: { stage: PlaybookStage; slot: number; add: boolean } | null;
  openEditor: (stage: PlaybookStage, slot?: number, add?: boolean) => void;
  closeEditor: () => void;
  /** Null until the first answer — "not asked yet" is not the same as "not there". */
  up: boolean | null;
  bundle: { path?: string; documents?: number; error?: string } | null;
  skills: Skill[];
  /** Every playbook on disk, by stem. **Null until the first answer** — a checkout with
   *  no playbooks answers `[]`, and the two have to be told apart or the poll re-asks on
   *  every tick. */
  playbooks: string[] | null;
  /** The stages whose prompts carry a `{{playbook}}` line. The service reads this off
   *  the prompt files, so it is the only honest source for it: offering a row for a
   *  stage that cannot receive one is a form that lies about what it can start. */
  playbookStages: PlaybookStage[];
  running: RunningRun | null;
  /** The last thing the service refused, shown next to the button that caused it. */
  error: string | null;
  /** A request is in flight; the button is disabled so one press is one run. */
  busy: boolean;

  /** What the run form currently says.
   *
   *  **It was `useState` inside `StartRun` until 2026-09-09**, and moving it here is not
   *  tidying: the two pipeline drawings now read it. Setting *Hypothesis* to 5 draws five
   *  cards, the ones with no worker behind them yet in the `planned` state
   *  (`lib/planned.ts`), and a panel cannot read another panel's local state. So the form
   *  became shared the moment something other than the form depended on it.
   *
   *  Held as one object, edited through `setForm`, because `RunRequest` is the shape the
   *  service takes and splitting it into twelve pieces of state would be twelve chances
   *  for the request sent to differ from the form shown. */
  form: RunRequest;
  setForm: (update: (form: RunRequest) => RunRequest) => void;

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
  loadPlaybooks: () => Promise<void>;
  startRun: (body: RunRequest) => Promise<void>;
  stopRun: () => Promise<void>;
  pollLog: () => Promise<void>;
}

/** How many lines the transcript keeps. A long run prints tens of thousands, and a
 *  browser holding every one of them in a scroll region is what makes a viewer that was
 *  fine for ten minutes unusable after an hour. */
const LOG_LINES = 2000;
let controlPollInFlight = false;

/** The service answers every refusal as `{"error": "..."}`, so the message a person
 *  reads is the one the service wrote rather than a status code. */
async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.error === "string") {
      // **A 404 from this service means the service is older than this page**, and it is
      // the one diagnosis the service cannot make about itself: a build that predates a
      // route has no code in it that knows the route was ever added, so the most it can
      // say is that the path is not one of the ones it has.
      //
      // The judgement therefore belongs here, where both versions are visible — the page
      // asked for a route it was built to expect, and got told there is no such thing.
      // This happened on 2026-09-09: `/control/playbooks` had existed in the checkout for
      // a day and the process answering had been up since the Thursday before, so the
      // Playbook row never rendered and the message under the button was
      // `no route /control/playbooks`, which names the symptom and no cure.
      //
      // The command is spelled out rather than described. The service is a **host**
      // process, not one of the containers `docker compose` restarts, so "restart the
      // viewer" is the wrong instinct and rebuilding the containers changes nothing.
      if (res.status === 404 && body.error.startsWith("no route")) {
        return (
          `${body.error} — the control service running on this machine is older than ` +
          `this page. It is a host process, not a container, so rebuilding the viewer ` +
          `will not replace it. Restart it: ` +
          `kill the \`python -m memstara.control\` process and run ` +
          `\`.venv/bin/python -m memstara.control\` again from the repository root.`
        );
      }
      return body.error;
    }
  } catch {
    /* not JSON; fall through to the status line */
  }
  return `${res.status} ${res.statusText}`;
}

export function applyRunConfiguration(form: RunRequest, config: RunConfiguration): RunRequest {
  return { ...form, ...Object.fromEntries(["question", "y_column", "provider", "model"].flatMap(k => {
    const value = config[k as keyof RunConfiguration]; return typeof value === "string" ? [[k, value]] : [];
  })), hypothesis_agents: config.hypotheses, interpret_agents: config.interpreters ?? 1, trials: config.trials, waves: config.waves,
    evaluation: { ...form.evaluation, ...config.evaluation } as EvaluationPlan,
    ...Object.fromEntries(PLAYBOOK_STAGES.map(stage => [`playbook_${stage}`, (config.books[stage] ?? []).join(",")])) };
}

function liveAgents(): boolean {
  return (useViewer.getState().snapshot?.scene.agents ?? []).some(a => a.state === "working" || a.state === "moving");
}

export const useControl = create<ControlState>((set, get) => ({
  preview: false,
  catalog: [],
  editor: null,
  openEditor: (stage, slot = 0, add = false) => { if (!get().running && !get().busy && !liveAgents()) set({ editor: { stage, slot, add } }); },
  closeEditor: () => set({ editor: null }),
  up: null,
  bundle: null,
  skills: [],
  playbooks: null,
  playbookStages: [],
  running: null,
  error: null,
  busy: false,

  form: (() => {
    try { const saved = JSON.parse(localStorage.getItem("memstara-draft-v1") ?? "null");
      return saved ? { ...DEFAULT_REQUEST, ...saved, evaluation: { ...DEFAULT_REQUEST.evaluation, ...saved.evaluation } } : DEFAULT_REQUEST;
    } catch { return DEFAULT_REQUEST; }
  })(),
  // An updater rather than a whole-object setter, because the two callers that already
  // existed in `StartRun` both computed the next form from the current one — one field at a
  // time, and one case (`hypothesis_agents`) that has to re-cut `playbook_hypothesis` in
  // the same breath so the number of agents and the number of standards can never be seen
  // disagreeing.
  setForm: (update) => {
    const state = get();
    const viewer = useViewer.getState();
    if (state.running || state.busy || liveAgents()) return;
    const config = !viewer.newRunMode ? viewer.snapshot?.run_configuration : null;
    const form = update(config ? applyRunConfiguration(state.form, config) : state.form);
    try { localStorage.setItem("memstara-draft-v1", JSON.stringify(form)); } catch { /* Session still works. */ }
    set({ form, preview: true });
    if (!viewer.newRunMode) viewer.setRunTag(null);
  },

  logTag: null,
  logLines: [],
  logTail: "",
  logSkipped: 0,
  logOffset: 0,

  poll: async () => {
    if (controlPollInFlight) return;
    controlPollInFlight = true;
    try {
      const res = await fetch("/control/health", { signal: AbortSignal.timeout(10000) });
      if (!res.ok) throw new Error(await readError(res));
      const body = await res.json();
      const wasDown = get().up !== true;
      // Live run metadata must never overwrite the user's independently saved draft.
      set({ up: true, bundle: body.bundle ?? null, running: body.running ?? null });
      // Only when it comes back, not on every tick: the branch list is one read of a
      // 312-document bundle and it does not change while a service is up.
      if (wasDown || get().skills.length === 0) void get().loadSkills();
      // Asked on the same edge, and the condition is `null` rather than `length === 0`
      // for a reason the skills do not have: a checkout with no playbooks answers `[]`
      // legitimately, and re-asking on an empty list would be a directory read every two
      // seconds forever. Null is "not asked"; `[]` is "asked, there are none".
      if (wasDown || get().playbooks === null) void get().loadPlaybooks();
    } catch {
      // No error message here. A control service nobody started is the normal state of
      // this screen, and writing "failed to fetch" under the dot every two seconds
      // would make the ordinary case look like a fault.
      set({ up: false });
    } finally { controlPollInFlight = false; }
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

  loadPlaybooks: async () => {
    try {
      const res = await fetch("/control/playbooks");
      if (!res.ok) throw new Error(await readError(res));
      const body = await res.json();
      // The stage names are narrowed against the list this file holds rather than
      // trusted. They arrive as strings and are about to be turned into object keys of
      // `RunRequest`; a name outside the five would build `playbook_whatever`, which the
      // service then refuses as an unknown field — a 400 about a key nobody typed.
      const stages: PlaybookStage[] = (body.stages ?? []).filter(
        (s: string): s is PlaybookStage => (PLAYBOOK_STAGES as readonly string[]).includes(s),
      );
      set({ playbooks: body.playbooks ?? [], catalog: body.catalog ?? [], playbookStages: stages });
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
      set({ running: run, preview: false });
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
      const selected = useViewer.getState().runTag || "latest";
      const offset = selected === get().logTag || selected === "latest" ? get().logOffset : 0;
      const res = await fetch(`/control/runs/${encodeURIComponent(selected)}/log?offset=${offset}`);
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
