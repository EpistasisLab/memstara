/** Shapes returned by the API. Written by hand rather than generated: the surface is
 *  small, and a hand-written type is where a field's meaning can be recorded. */

export type AgentState = "idle" | "moving" | "working" | "unknown";
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
  id: StageId;
  label: string;
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
  agent: StageId;
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
   *  run_tag, trial, perspective, hypothesis, columns_used, y_column and auc are here. */
  task_id: number | null;
  trial: number;
  perspective: string;
  hypothesis: string;
  columns_used: string[];
  /** What the AUC is an AUC *of*. Carried over from the board. */
  y_column: string;
  auc: number | null;
  interpretation: string;
  created_at: string;
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
