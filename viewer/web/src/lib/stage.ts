import type { StageId, StoreId } from "../types";

/** One colour per stage, shared by the character, its card and its edges, so a task
 *  keeps a single identity as it moves between places. */
export const STAGE_COLOR: Record<StageId, string> = {
  curator: "rgb(var(--stage-curator))",
  hypothesis: "rgb(var(--stage-hypothesis))",
  data: "rgb(var(--stage-data))",
  ml: "rgb(var(--stage-ml))",
  interpreter: "rgb(var(--stage-interpreter))",
  report: "rgb(var(--stage-report))",
};

export const STORE_LABEL: Record<StoreId, string> = {
  okf: "Knowledge source",
  matcher: "Semantic matcher",
  board: "Board",
  results: "Results table",
  dataset: "Dataset",
  ml: "Trainer",
  unknown: "—",
};

export const STATE_LABEL = {
  idle: "Idle",
  moving: "Carrying a task",
  working: "Working",
  unknown: "Unknown",
  // Not "Idle". An idle figure has a past — it ran, and stopped — and this one has none:
  // it is on screen because the run form asks for it (`lib/planned.ts`). The two need
  // opposite reactions from a reader, so they cannot share a word.
  planned: "Not started",
} as const;
