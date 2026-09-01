import type { StageId, StoreId } from "../types";

/** One colour per stage, shared by the character, its card and its edges, so a task
 *  keeps a single identity as it moves between places. */
export const STAGE_COLOR: Record<StageId, string> = {
  curator: "#1f6f77",
  hypothesis: "#2f6b47",
  data: "#2a5f8f",
  ml: "#8a5f12",
  interpreter: "#6b3f8f",
  report: "#8f2f4f",
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
} as const;
