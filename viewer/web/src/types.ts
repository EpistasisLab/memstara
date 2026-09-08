/** Shapes returned by the API. Written by hand rather than generated: the surface is
 *  small, and a hand-written type is where a field's meaning can be recorded. */

export type AgentState = "idle" | "moving" | "working" | "unknown";
export type StoreId = "okf" | "matcher" | "board" | "results" | "dataset" | "ml" | "unknown";
/** The five stages the pipeline has, plus one it used to. `curator` was retired on
 *  2026-09-07 — writing the wave's questions is the hypothesis agent's other job now —
 *  and the API never sends it: `stores.reported_as` folds it into `hypothesis` on every
 *  screen. It stays in the union because the databases still hold runs recorded against
 *  it, and because a stage the API cannot name is better handled by a `Record` that has
 *  a key for it than by an undefined lookup. */
export type StageId = "curator" | "hypothesis" | "data" | "ml" | "interpreter" | "report";

export interface Place {
  id: StoreId;
  label: string;
  sub: string;
  x: number;
  y: number;
}

export interface SceneAgent {
  /** One **worker**, not one stage — so this is not a `StageId`.
   *
   *  A stage that runs a single worker keeps the stage's own id (`hypothesis`), which is
   *  what makes a default run look exactly as it did before `--hypothesis-agents` could
   *  put more than one figure on the floor. Run two or more and each gets the name it
   *  called itself by on the board instead: `hypothesis#1`, `hypothesis#2`.
   *
   *  Unique across the scene, and React Flow depends on that — two nodes with one id
   *  draw as one node, silently. Use `stage` for anything keyed by the five stages. */
  id: string;
  /** Which of the five stages this figure is one of. Every `Record<StageId, ...>` table
   *  — the colours, the pictograms — is keyed by this and not by `id`. */
  stage: StageId;
  label: string;
  /** The name this worker called itself, or null when it never said. It is the same
   *  string the board records in `claimed_by`, which is what makes a figure on the floor
   *  traceable to a row in the task list. Null for a single-worker stage. */
  worker: string | null;
  /** Which of its stage's figures this is, from 0. The floor plan offsets by it so two
   *  workers of one stage do not stand on the same spot. */
  slot: number;
  /** How many runs **this figure** stands for — 0 when it is resting.
   *
   *  Only `hypothesis` is drawn as one figure per worker (`stores.SPLITTABLE`), so there
   *  this is 1 on each. The other four are one figure however many run behind them, which
   *  is what the meeting of 2026-08-26 asked for, and there this is the whole count. That
   *  is why folding them is not the same as hiding them: `--data-agents 2` draws one data
   *  character with a 2 on it, not two characters and not a silent one. */
  running: number;
  name: string;
  state: AgentState;
  /** Which place it is standing at, or null when resting at home. */
  at: StoreId | null;
  home: { x: number; y: number };
  /** task_id it is holding — claimed but not yet submitted. */
  carrying: number | null;
  run_id: string | null;
  since: string | null;
  last_tool: { server: string; tool: string; store: StoreId; at: string } | null;
  /** The windows this stage is allowed to hold, from BOARD_TOOLS. */
  windows: string[];
}

export interface Flash {
  /** A `SceneAgent["id"]`, so a worker rather than a stage — the line has to land on the
   *  figure that made the call, and with several workers at one station there is no
   *  figure called `hypothesis` for a stage-keyed flash to reach. */
  agent: string;
  place: StoreId;
  tool: string;
  server: string;
  at: string;
}

/** One row of the feed: a single tool call, newest first.
 *
 *  Unlike `Flash` this has no time window — the feed is "the last N calls, whenever
 *  they were", so a quiet system shows its last activity instead of showing nothing.
 *  `agent` is null when the viewer does not recognise the agent name; the row is still
 *  shown, because a call it cannot name is exactly what someone would want to see. */
export interface FeedEvent {
  /** Stable across polls — step id plus the call's position within its batch. */
  key: string;
  name: string;
  agent: StageId | null;
  label: string;
  path: "board" | "supervisor" | "other";
  server: string;
  tool: string;
  store: StoreId;
  at: string;
}

export interface Task {
  task_id: number;
  run_tag: string;
  trial: number;
  perspective: string;
  status: "ready" | "in_progress" | "done" | "failed";
  task_type: "hypothesis" | "data" | "ml" | "interpret";
  attempts: number;
  hypothesis: string;
  columns: string[];
  /** What the chosen columns predict. On the task, not in a prompt — so a finished
   *  row records what its AUC is an AUC *of*. */
  y_column: string;
  columns_used: string[];
  columns_missing: string[];
  auc: number | null;
  importance: Record<string, number>;
  interpretation: string;
  error: string;
  claimed_at: string | null;
  created_at: string;
  updated_at: string;
  /** Claims beyond the stages passed — a real retry, not normal progress. */
  retried: number;
}

export interface AgentTotals {
  name: string;
  id: StageId | null;
  path: "board" | "supervisor" | "other";
  label: string;
  runs: number;
  completed: number;
  open_runs: number;
  tokens: { prompt: number; completion: number };
  cost: number;
  avg_iterations: number | null;
  last_run_at: string | null;
}

export interface AccessRow {
  agent: StageId | string;
  agent_label: string;
  name: string;
  path: "board" | "supervisor" | "other";
  server: string;
  tool: string;
  store: StoreId;
  calls: number;
  last_at: string;
}

export interface Window {
  tool: string;
  holder: string;
  store: StoreId;
  calls: number;
  /** False for read_board and count_waiting — and that is the correct picture. */
  called_by_agent: boolean;
}

export interface Result {
  result_id: number;
  /** Null once the board row has been cleaned up. The result still describes itself —
   *  everything below is on the result row, so none of it depends on the board. */
  task_id: number | null;
  trial: number;
  perspective: string;
  hypothesis: string;
  /** What the data stage could actually cut from the cohort. */
  columns_used: string[];
  /** What it could not. The data stage's own list — **not** the columns the hypothesis
   *  agent asked for minus `columns_used`; see the RESULTS comment in api/queries.py for
   *  the three rows that prove those are different claims. */
  columns_missing: string[];
  /** Column name -> contribution. Same name and meaning as `Task.importance`, but read
   *  from the result, which outlives the board row. Can be negative. */
  importance: Record<string, number>;
  /** OKF document ids the hypothesis agent relied on to justify those columns. */
  okf_concept_ids: string[];
  /** What the AUC is an AUC *of*. Carried over from the board. */
  y_column: string;
  auc: number | null;
  /** The engine that produced `importance`, and therefore the **scale those numbers are
   *  on**. `sklearn_hgb` reaches the permutation route and its numbers are AUC deltas;
   *  `random_forest` and `xgboost` carry `feature_importances_` and theirs are impurity
   *  or gain, summing to about 1. Ranking one against the other is reading an AUC delta
   *  against a fraction of impurity, which is why this field travels with the map.
   *
   *  `""` means **not recorded**, not "unknown engine" — the column is
   *  `TEXT NOT NULL DEFAULT ''` and every result stored before 2026-09-08 takes it,
   *  because the engine was read from the environment inside the call and never written
   *  down. It cannot be backfilled and the screen says so rather than guessing. */
  model: string;
  interpretation: string;
  created_at: string;
}

/** One candidate the matcher offered for a concept. */
export interface TraceCandidate {
  column: string;
  feature_type: string;
  /** Cosine similarity to the concept. Null only if the matcher omitted it. */
  score: number | null;
  /** The agent asked for this column. Judged against `columns` — what was asked for —
   *  and not against `columns_used`, so a column the cohort turned out not to have is
   *  still shown as chosen. See scene._trace_groups. */
  chosen: boolean;
  /** …and it also survived into the model. */
  present: boolean;
}

/** What the matcher offered for one concept, chosen and rejected alike. */
export interface TraceGroup {
  tool: string;
  concept: string;
  /** The matcher's own reason for an empty group — "nothing was close enough" is worth
   *  rewording for, "a code this cohort does not carry" is not. */
  note: string;
  candidates: TraceCandidate[];
}

/** `/api/result/{id}` — one result with the matcher record behind its columns.
 *
 *  Not part of `Snapshot`. `match_trace` is 598 kB across the stored results against
 *  89 kB for every explanation column the snapshot carries, and the snapshot is polled
 *  every two seconds, so this is fetched once when a person opens a result. */
export interface ResultDetail extends Result {
  run_tag: string;
  /** What the hypothesis agent asked for, against `columns_used` which is what arrived. */
  columns: string[];
  match_trace: TraceGroup[];
  /** Calls stored before flattening. A trace that unwraps to no groups still differs
   *  from a task the matcher was never called for, and those need opposite fixes. */
  match_trace_calls: number;
}

export interface RunSummary {
  run_tag: string;
  tasks: number;
  done: number;
  first_seen: string;
  last_seen: string;
}

export interface Health {
  memstara: { up: boolean; error: string };
  core: { up: boolean; error: string };
}

export interface Snapshot {
  run_tag: string;
  runs: RunSummary[];
  /** The API gave up waiting for a fresh computation and re-sent its previous answer.
   *  A 200 whose contents are older than `generated_at` suggests — so a screen that
   *  ignores this reports a stale picture as current. See api/scene.snapshot. */
  stale: boolean;
  generated_at: string;
  health: Health;
  scene: { places: Place[]; agents: SceneAgent[]; flashes: Flash[] };
  board: { lanes: Record<string, number>; tasks: Task[] };
  agents: AgentTotals[];
  access: { rows: AccessRow[]; windows: Window[] };
  /** Every run and both driving paths — not just the selected run. See api/scene._feed. */
  feed: FeedEvent[];
  results: Result[];
}
