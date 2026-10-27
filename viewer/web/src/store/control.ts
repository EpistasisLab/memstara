import {setMlSettingsSchema,type MlOverrides} from '../lib/mlOverrides';
import {setCorpusSkillBindings} from '../lib/researchSkills';
import { usePipelines } from "./pipelines";
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
  recoverable?: boolean;
  recovery_blocked?: string;
  connection_health?: {state: string; at: string; consecutive_failures?: number};
  infrastructure_status?: { status: string; message: string; results_preserved?: boolean };
  recovery_wave?: number;
  waiting_for_questions?: boolean;
  pause_requested?: boolean;
  resumable?: boolean;
  execution_state?: "running" | "stopping" | "paused";
  active_calls?: number;
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
  research_input_id?: string;
  knowledge_mode?: 'okf'|'llm_only';
  data_mode?: 'dataset'|'proposal';
  research_objective?: string;
  stage_models?: import("../lib/stageModels").StageProfiles;
  combination_plan?: import("../lib/replicateIdentity").Schedule | null;
  combination_skills?: Partial<Record<PlaybookStage,string[]>>;
  combination_repetitions?: number;
  combination_execution_order?: "all_pipelines_first" | "pipeline_replicates_first";
  combination_random_start?: boolean;
  combination_max_loops?: number | null;
  question: string;
  evaluation: EvaluationPlan;
  ml_overrides?: MlOverrides;
  baseline_columns?: string[];
  skill: string;
  trials: number;
  waves: number;
  continuous?: boolean;

  hypothesis_agents: number;
  interpret_agents: number;
  y_column: string;
  provider: string;
  model: string;
} & {

  [S in PlaybookStage as `playbook_${S extends "report" ? "explanation" : S}`]: string;
};

/** New drafts have no disease-specific target. Select a research contract before execution. */
export const DEFAULT_REQUEST: RunRequest = {
  baseline_columns: [],
  question: "",
  evaluation: { engine: "xgboost", seed: 42, test_size: .25, folds: 0, replicates: 1, search_trials: 1 },
  skill: "",
  trials: 3,
  waves: 1,
  continuous: false,
  hypothesis_agents: 1,
  interpret_agents: 1,
  y_column: "",
  provider: "",
  model: "",
  playbook_hypothesis: "hypothesis_general",
  playbook_data: "",
  playbook_ml: "ml_logistic_regression",
  playbook_interpreter: "shared-shap",
  playbook_explanation: "shared-addiction",
};

interface ControlState {
  preview: boolean;
  catalog: SkillInfo[];
  references: SkillInfo[];
  editor: { stage: PlaybookStage; slot: number; add: boolean } | null;
  openEditor: (stage: PlaybookStage, slot?: number, add?: boolean) => void;
  closeEditor: () => void;
  /** Null until the first answer — "not asked yet" is not the same as "not there". */
  up: boolean | null;
  bundle: { path?: string; documents?: number; error?: string } | null;
  skills: Skill[];
  skillsLoaded: boolean;
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


  form: RunRequest;
  setForm: (update: (form: RunRequest) => RunRequest) => void;

  /** Which run the transcript below belongs to. Null when this service has started
   *  nothing — which is not the same as a run that has printed nothing yet. */
  logTag: string | null;
  logError: string | null;
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
  pauseRun: (paused: boolean) => Promise<void>;
  pollLog: () => Promise<void>;
}

/** How many lines the transcript keeps. A long run prints tens of thousands, and a
 *  browser holding every one of them in a scroll region is what makes a viewer that was
 *  fine for ten minutes unusable after an hour. */
const LOG_LINES = 2000;
let logPolling = false;
let controlPollInFlight = false;

/** The service answers every refusal as `{"error": "..."}`, so the message a person
 *  reads is the one the service wrote rather than a status code. */
async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.error === "string") {
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
  return { ...form, ml_overrides:structuredClone(config.ml_overrides??{}), research_input_id:config.research_profile?.id??'', knowledge_mode:config.knowledge_mode??'okf', data_mode:config.data_mode??'dataset', research_objective:config.research_objective??'', question: "", ...Object.fromEntries(["skill", "y_column", "provider", "model"].flatMap(k => {
    const value = config[k as keyof RunConfiguration]; return typeof value === "string" ? [[k, value]] : [];
  })), hypothesis_agents: config.hypotheses, interpret_agents: config.interpreters ?? 1, trials: config.trials, waves: config.waves, continuous: config.continuous ?? false,
    baseline_columns: config.comparison_policy?.baseline_columns ?? [],
    evaluation: { ...form.evaluation, ...config.evaluation } as EvaluationPlan,
    ...Object.fromEntries(PLAYBOOK_STAGES.map(stage => [`playbook_${stage === "report" ? "explanation" : stage}`, (config.books[stage] ?? []).join(",")])) };
}

function liveAgents(): boolean {
  return (useViewer.getState().snapshot?.scene.agents ?? []).some(a => a.state === "working" || a.state === "moving");
}

export const useControl = create<ControlState>((set, get) => ({
  preview: false,
  catalog: [],
  references: [],
  editor: null,
  openEditor: (stage, slot = 0, add = false) => { if (!get().running && !get().busy && (!liveAgents() || usePipelines.getState().selected)) set({ editor: { stage, slot, add } }); },
  closeEditor: () => set({ editor: null }),
  up: null,
  bundle: null,
  skills: [], skillsLoaded: false,
  playbooks: null,
  playbookStages: [],
  running: null,
  error: null,
  busy: false,

  form: (() => {
    try { const saved = JSON.parse(localStorage.getItem("memstara-draft-v1") ?? "null");
      if (saved?.playbook_report !== undefined) { saved.playbook_explanation ??= saved.playbook_report; delete saved.playbook_report; }
      return saved ? { ...DEFAULT_REQUEST, ...saved, provider: "", model: "", question: "", evaluation: { ...DEFAULT_REQUEST.evaluation, ...saved.evaluation } } : DEFAULT_REQUEST;
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
    if (state.running || state.busy || (liveAgents() && !usePipelines.getState().selected)) return;
    const pipeline = usePipelines.getState().items.find(p => p.id === usePipelines.getState().selected);
    const config = !pipeline && !viewer.newRunMode ? viewer.snapshot?.run_configuration : null;
    const form = update(pipeline?.configuration ?? (config ? applyRunConfiguration(state.form, config) : state.form));
    if (pipeline) usePipelines.getState().save(pipeline.id, form);
    try { localStorage.setItem("memstara-draft-v1", JSON.stringify(form)); } catch { /* Session still works. */ }
    set({ form, preview: true });
    if (!viewer.newRunMode) viewer.setRunTag(null);
  },

  logTag: null,
  logError: null,
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
      const selectedPipeline = usePipelines.getState().items.find(p => p.id === usePipelines.getState().selected);
      set({ up: true, bundle: body.bundle ?? null, running: selectedPipeline ? selectedPipeline.running : body.running ?? null });
      // Only when it comes back, not on every tick: the branch list is one read of a
      // 312-document bundle and it does not change while a service is up.
      if (wasDown || !get().skillsLoaded) void get().loadSkills();
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
      set({ skills: body.skills ?? [], skillsLoaded: true });
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
      setCorpusSkillBindings(body.corpus_skill_bindings);
      setMlSettingsSchema(body.ml_settings);
      set({ playbooks: body.playbooks ?? [], catalog: body.catalog ?? [], references: body.references ?? [], playbookStages: stages });
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
        // The UI no longer exposes a research question. Do not send a hidden value
        // restored from an older draft or a previously selected run.
        body: JSON.stringify({ ...body, question: "" }),
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
    if (logPolling) return;
    const selected = useViewer.getState().runTag;
    if (!selected) {
      set({ logTag: null, logError: null, logLines: [], logTail: "", logSkipped: 0, logOffset: 0 });
      return;
    }
    logPolling = true;
    try {
      const offset = selected === get().logTag ? get().logOffset : 0;
      const res = await fetch(`/control/runs/${encodeURIComponent(selected)}/log?offset=${offset}`, {
        signal: AbortSignal.timeout(5000),
      });
      if (selected !== useViewer.getState().runTag) return;
      if (!res.ok) throw new Error(res.status === 404 ? "No console log is available for this run." : await readError(res));
      const body = await res.json();
      if (selected !== useViewer.getState().runTag || body.run_tag !== selected) return;
      set((s) => {
        const same = s.logTag === selected;
        const parts = ((same ? s.logTail : "") + body.text).split("\n");
        const tail = parts.pop() ?? "";
        const lines = [...(same ? s.logLines : []), ...parts];
        return {
          logTag: selected, logError: null,
          logLines: lines.slice(-LOG_LINES), logTail: tail,
          logSkipped: (same ? s.logSkipped : 0) + (body.skipped ?? 0),
          logOffset: body.offset ?? offset,
        };
      });
    } catch (e) {
      if (selected === useViewer.getState().runTag)
        set({ logError: e instanceof Error ? e.message : String(e) });
    } finally { logPolling = false; }
  },

  pauseRun: async (paused) => {
    const tag = get().running?.run_tag;
    if (!tag) return;
    set({ busy: true, error: null });
    try {
      const res = await fetch(`/control/runs/${encodeURIComponent(tag)}/${paused ? "pause" : "resume"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      if (!res.ok) throw new Error(await readError(res));
      await get().poll();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally { set({ busy: false }); }
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
