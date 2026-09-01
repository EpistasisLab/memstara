import { Boxes, Database, Layers, ListTree, Map, type LucideIcon } from "lucide-react";
import type { ViewId } from "../store/viewer";
import type { Snapshot } from "../types";

/**
 * What each swappable view is called and how it is drawn in a list.
 *
 * Kept here rather than in `ControlPanel` because two places need it and they must not
 * drift: the control panel's nav writes `view`, and `App`'s top-right slot titles the
 * panel it swaps in. If the nav said "Access map" and the panel above it said something
 * else, the screen would be arguing with itself.
 *
 * `count` reads straight off the snapshot, so the number beside a name is the same number
 * the view itself will show. Leaving it out means "no count for this one" rather than a
 * misleading zero — Task life is about a single task, so a count would be noise.
 */

export interface ViewMeta {
  label: string;
  icon: LucideIcon;
  count?: (s: Snapshot) => number;
}

export const VIEWS: Record<ViewId, ViewMeta> = {
  scene: { label: "Agent state", icon: Map, count: (s) => s.scene.agents.length },
  board: { label: "Board", icon: Layers, count: (s) => s.board.tasks.length },
  task: { label: "Task life", icon: ListTree },
  agents: { label: "Agents", icon: Boxes, count: (s) => s.agents.length },
  access: { label: "Access map", icon: Database, count: (s) => s.access.rows.length },
};

/** Nav order — pipeline first, then the ways of looking at it. A Record has no order of
 *  its own, so the list that renders needs one stated. */
export const VIEW_ORDER: ViewId[] = ["scene", "board", "task", "agents", "access"];
