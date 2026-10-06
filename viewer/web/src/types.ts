/** Shapes returned by the API. Written by hand rather than generated: the surface is
 *  small, and a hand-written type is where a field's meaning can be recorded. */

/** What a figure is doing. Four of the five come from the API; `planned` never does.
 *
 *  **`planned` is the only state the browser invents**, and it is invented from something
 *  the browser genuinely knows: the run form asks for N hypothesis agents and only M of
 *  them exist yet, so the remaining N−M are drawn under this state (`lib/planned.ts`). It
 *  is not a guess about the database — it is the form, quoted back.
 *
 *  It has to be its own state rather than an `idle` card with a flag, for the same reason
 *  `unknown` is not a quiet `idle`: three tables are keyed exhaustively by this union
 *  (`STATE_LABEL`, `STATE_ICON`, `STATE_TONE`), so a new member makes every drawing site
 *  say what it looks like or fail to compile. Reusing `idle` would have drawn an agent
 *  that has run and stopped, which is a different and false claim. */
export type AgentState = "idle" | "moving" | "working" | "unknown" | "planned";
export type StoreId = "okf" | "matcher" | "board" | "results" | "dataset" | "ml" | "unknown";

export type StageId = "curator" | "hypothesis" | "data" | "ml" | "interpreter" | "report";

export interface Place {
  id: StoreId;
  label: string;
  sub: string;
  x: number;
  y: number;
}

export interface SceneAgent {
  last_status?: string | null;
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

  running: number;
  name: string;

  playbook: string;
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

export interface QuestionContract {
  version?: string; kind?: string; origin_wave?: number; parent_task_ids?: number[]; learning_goal?: string;
}

export interface ModelComparison {
  timing_status?: string; interpretation_limit?: string; baseline_source?: string; study_policy_sha256?: string;
  status: string; baseline_configured: boolean; baseline_columns: string[]; scope: string; parameters_policy: string;
  group_policy: string;
  variants: {id:string; label:string; features:string[]; removed_features:string[]; status:string; auc?:number;
    delta_from_full?:number; delta_from_baseline?:number; error_type?:string; reason?:string}[];
}
export interface SpecialistXai {
  status: string;
  items: Array<{method: string; model: string; replicate: number; status: string; error_type?: string;
    explainer?: string; output_scale?: string; explained_count?: number; reference_count?: number;
    seed: number; baseline?: number; max_additivity_error?: number;
    fidelity_r2?: {minimum: number; mean: number}; samples_per_row?: number;
    feature_summary?: Record<string, {mean_absolute: number; mean_signed: number}>;
    limitation?: string; artifact_path?: string; artifact_sha256?: string; explanation_id?: string}>;
}
export interface Result {
  run_tag?: string; pipeline_id?: string; pipeline_name?: string; iteration?: number | null;
  hypothesis_id?: string;
  evaluation?: {
    paired_models?: {primary_model: string; primary_selection: string; same_features: boolean; same_splits: boolean; xgboost_minus_lr_auc: number};
    ml_configuration?: {requested: unknown; effective: unknown; resource_limits: unknown};
    model_results?: Record<string, {auc: number; n_train: number; n_test: number; model: string;
      ml_configuration?: unknown; specialist_xai?: SpecialistXai; evaluation: {replicates: Array<{seed: number; auc: number;
        average_precision: number; operating_point: {true_negative: number; false_positive: number;
          false_negative: number; true_positive: number; probability_cutoff: number}}>;
        reproducibility?: {status: string; bundle_path: string}}}>;
    data_allocation?: {request: {skill: string; population: string}; agent_plan: {test_size: number; seed: number};
      exploration_count: number; reserved_count: number;
      replicates: {seed: number; n_train: number; n_test: number;
        train_class_counts: Record<string, number>; test_class_counts: Record<string, number>}[]};
    feature_selection?: {mode: "guided" | "random"; minimum: number; maximum: number;
      actual_count: number; features: string[]; seed: number | null; pool_size: number;
      pool_sha256: string; loop: number; combination: number};
    comparison?: ModelComparison;
    question_contract?: QuestionContract;
    hypothesis_policy?: { version?: string; kind?: string; validation_status?: string };
    interpretations_complete?: boolean;
    interpretations?: { slot: number; worker: string; skill: string; status: string; text: string; error: string }[];
    interpreter?: { worker: string; skill: string };
    seed?: number; test_size?: number; auc_std?: number;
    config_hash?: string;
    data_quality?: { preprocessing?: string; missing_predictor_cells?: number; warnings?: string[] };
    evaluation?: { plan?: Record<string, unknown>; duration_seconds?: number;
      score_scope?: string; validation_reserve?: {status?: string};
      replicates?: {seed: number; auc: number; split_id: string; cv_folds?: number}[];
      reproducibility?: {status: string; method?: string; scope?: string; bundle_path?: string;
        replicates?: {replicate: number; status: string}[] } };
    explanation?: { method?: string; scope?: string;
      evaluated_replicate?: number; total_replicates?: number; evaluated_seed?: number; evaluation_rows?: number;
      permutation?: {n_repeats: number; random_state?: number; scoring?: string; scope?: string;
        standard_deviation: Record<string, number>; repeat_values?: Record<string, number[]>}; actionability?: string; review_status?: string;
      operating_point?: { probability_cutoff: number; sensitivity: number; specificity: number; precision: number | null;
        true_positive?: number; true_negative?: number; precision_reason?: string | null;
        false_positive: number; false_negative: number; selection: string; status: string };
      feature_effects?: { feature: string; range_start: number; range_end: number; probability_before: number;
        probability_after: number; direction: string; validation_needed: string }[];
      shap?: { method?: string; units?: string; status?: string; reason?: string; mean_absolute?: Record<string, number>; mean_signed?: Record<string, number> };
      partial_dependence?: { feature: string; values: number[]; predicted_probability: number[] }[] };
  };
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
  question?: string;
  hypotheses?: number | null;
  trials?: number | null;
  waves?: number | null;
  model?: string | null;
  status?: string;
}

export interface Health {
  memstara: { up: boolean; error: string };
  core: { up: boolean; error: string };
}

export interface RunConfiguration {
  pipeline_id?: string; pipeline_name?: string;
  skill?: string | null;
  interpretation_mode?: string;
  interpreters?: number;
  question?: string; y_column?: string; provider?: string; model?: string;
  comparison_policy?: {baseline_columns: string[]};
  hypotheses: number; books: Record<string, string[]>; evaluation: Record<string, number | string>;
  trials: number; waves: number; continuous?: boolean;
}

export interface Snapshot {
  run_configuration?: RunConfiguration | null;
  scene_scope?: string;
  report?: { status: string; text: string; error?: string | null; specialist_explanation?: ExplanationEvidence | null } | null;
  pipeline?: { status: string; report_completed?: boolean; message?: string; reason?: string } | null;
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


export interface ExplanationEvidence {
  status: string;
  expert?: string;
  loop?: number | null;
  database_ids?: string[];
  interpretation_methods?: string[];
  task_ids?: number[];
  citations?: string[];
  reports?: ExplanationEvidence[];
  missing_loops?: number[];
  aggregation?: string;
}
