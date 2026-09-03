import {
  BookOpen,
  ChartLine,
  CircleDashed,
  CircleDot,
  ClipboardList,
  Columns3,
  Cpu,
  Database,
  FileSpreadsheet,
  Library,
  Lightbulb,
  LoaderCircle,
  NotebookPen,
  PackageOpen,
  ScanSearch,
  TriangleAlert,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import type { AgentState, StageId, StoreId } from "../types";

/**
 * The pictogram vocabulary. Three tables, one file, so the same thing looks the same
 * wherever it is drawn.
 *
 * Why it is worth having a file for this. The scene, the feed and the access map all
 * name the same six stages and the same six stores. Picking an icon at each drawing
 * site means the knowledge source is a book in one panel and a database in another, and
 * a reader has to learn the picture twice. That has already happened once: `PLACE_ICON`
 * in `components/nodes.tsx` had no `matcher` entry, so the semantic matcher fell through
 * to the `Database` fallback and was drawn with **the same icon as the dataset** — two
 * different places, one picture, no error anywhere.
 *
 * Every name here exists in the installed lucide-react (1.32). That version renamed a
 * number of icons, so `LineChart` and `CircleHelp` — the obvious guesses — are not
 * there; `ChartLine` and `TriangleAlert` are. A missing export is a build error rather
 * than a blank space, which is the reason to keep the tables exhaustive over the id
 * types instead of reaching for a fallback.
 */

/** Who: one per pipeline stage. Chosen for the stage's job, not its name — the curator
 *  reads a corpus, the hypothesis stage proposes, the data stage cuts columns. */
export const STAGE_ICON: Record<StageId, LucideIcon> = {
  curator: Library,
  hypothesis: Lightbulb,
  data: Columns3,
  ml: ChartLine,
  interpreter: ScanSearch,
  report: NotebookPen,
};

/** Where: one per store. `unknown` is a real value from `stores.store_of()` — a tool the
 *  viewer has no mapping for — so it gets a picture of its own rather than a blank. */
export const STORE_ICON: Record<StoreId, LucideIcon> = {
  okf: BookOpen,
  matcher: Waypoints,
  board: ClipboardList,
  results: FileSpreadsheet,
  dataset: Database,
  ml: Cpu,
  unknown: CircleDashed,
};

/** What now. `unknown` must not read as a quiet `idle`: with core's database unreadable,
 *  "this agent is doing nothing" is an assertion that cannot be made (`api/scene.py:290-295`).
 *  So it is a warning glyph, and the panel colours it amber. */
export const STATE_ICON: Record<AgentState, LucideIcon> = {
  working: LoaderCircle,
  moving: PackageOpen,
  idle: CircleDot,
  unknown: TriangleAlert,
};
