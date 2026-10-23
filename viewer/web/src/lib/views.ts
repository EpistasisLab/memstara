import {
  Stethoscope,
  BarChart3,
  Orbit,
  Boxes,
  Database,
  FileText,
  Layers,
  ListTree,
  Map,
  Terminal,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { ViewId } from "../store/viewer";

/**
 * What each swappable view is called and how it is drawn in a list.
 *
 * Kept here rather than in `ControlPanel` because two places need it and they must not
 * drift: the control panel's nav writes `view`, and `App`'s top-right slot titles the
 * panel it swaps in. If the nav said "Access map" and the panel above it said something
 * else, the screen would be arguing with itself.
 *
 */

export interface ViewMeta {
  label: string;
  description: string;
  icon: LucideIcon;
}

export const VIEWS: Record<ViewId, ViewMeta> = {
  discovery: { description: 'Explore generated research questions and follow their hypotheses, evidence and results as pipelines run.', label: "Question universe", icon: Orbit },
  results: { description: 'Review recorded model performance, feature contributions and interpretation for each analysis.', label: "Results", icon: BarChart3 },
  clinician: { description: 'Review research findings in clinical language, with supporting evidence and limitations.', label: "Clinician view", icon: Stethoscope },
  chain: { description: 'Track each pipeline’s current stage, replicate and completion status.', label: "Status", icon: Workflow },
  scene: { description: 'See parallel pipelines, their agents and resources, and follow live activity.', label: "Experiments", icon: Map },
  log: { description: 'Read detailed execution messages to investigate errors or stalled work.', label: "Run log", icon: Terminal },
  report: { description: 'Read and download the saved Explanation agent output for each pipeline.', label: "Conclusions", icon: FileText },
  board: { description: 'Inspect analysis tasks and see which are waiting, running or completed.', label: "Board", icon: Layers },
  task: { description: 'Follow one selected task through its analysis stages.', label: "Task life", icon: ListTree },
  agents: { description: 'Inspect agent calls, tool activity, usage and database records for troubleshooting.', label: "Usage", icon: Boxes },
  access: { description: 'See which agents have used each tool or data service.', label: "Access map", icon: Database },
};

/** The primary views shown in Control, in their display order.
 * Diagnostic views retain their metadata for existing internal navigation.
 */
export const VIEW_ORDER: ViewId[] = ["scene", "results", "report", "agents"];
