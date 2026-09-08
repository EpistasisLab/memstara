import type { SceneAgent, StageId } from "../types";

/**
 * The pipeline drawn as a chain: who follows whom, and how long each link has been at it.
 *
 * The floor plan (`ScenePanel`) answers "where is everyone standing". This answers the
 * different question of "how far along is the work", which needs the stages laid out in
 * the order they run rather than scattered around the stores they touch.
 *
 * What this deliberately does **not** have is a `complete` state. Nothing in the snapshot
 * says "this stage has finished" — an agent that has stopped and an agent that never
 * started both arrive here as `idle`, and drawing a tick beside one of them would be an
 * assertion the data does not support. Completion is derivable from the board's task
 * rows, which is a separate change; `stateOf` below is the one seam it will attach to.
 */

/**
 * The order work actually runs in, and the only place the frontend states it.
 *
 * It mirrors `viewer/api/stores.py:233-239` (`HOME`), whose comment says the same thing —
 * "in the order the pipeline runs them". Read from the snapshot's agent array instead,
 * the order would be whatever the API's dict iteration happened to give, which is right
 * today by accident rather than by contract.
 *
 * **Five cards for the pipeline's five stages.** There is a sixth stage key, `curator`,
 * and it is deliberately absent: the pipeline retired it on 2026-09-07, when writing the
 * wave's questions became the hypothesis agent's other job. Runs made before that are
 * still in the database, and `viewer/api/stores.py` (`DRAWN_AS`) folds them into the
 * hypothesis stage so they still appear; `stores.reported_as` carries the same fold into
 * the cost table, the access map and the feed, so no screen the frontend draws names the
 * curator. This array is about who gets a box drawn, nothing more. It has to agree with
 * the backend, because `ChainPanel` compares its length against the agents the API sent
 * and reports a shortfall as an error.
 */
export const CHAIN: StageId[] = [
  "hypothesis",
  "data",
  "ml",
  "interpreter",
  "report",
];

/** One entry per chain stage: the figure that stands for it, and how many are running. */
export interface ChainStep {
  agent: SceneAgent;
  /** How many workers of this stage the scene sent. 1 for an ordinary run. */
  workers: number;
}

/**
 * The stages in chain order, skipping any the API did not send.
 *
 * **The chain stays five cards however many workers run.** It answers "how far along is
 * the work", and three hypothesis workers are three hands on one step of the pipeline,
 * not three steps — laid out in a row they would push `data`, `ml`, `interpreter` and
 * `report` off to the right and make the picture say the pipeline had grown. The floor
 * plan is the screen that draws one figure per worker; this one counts them.
 *
 * Grouping by `stage` and not by `id` is also what keeps the hypothesis card on screen at
 * all: since 2026-09-08 a stage running several workers sends no agent whose id is
 * `hypothesis`, so a lookup by id would silently return nothing for exactly the stage
 * `--hypothesis-agents` multiplies.
 *
 * The representative is whichever worker is furthest along the state order — a stage with
 * one worker working and two idle is a stage that is working, and a card that showed
 * `idle` because that happened to be the first worker in the array would be wrong about
 * the only thing this panel is for.
 */
const STATE_RANK: Record<SceneAgent["state"], number> = {
  unknown: 3, working: 2, moving: 1, idle: 0,
};

export function chainAgents(agents: SceneAgent[]): ChainStep[] {
  return CHAIN.map((stage) => {
    const mine = agents.filter((a) => a.stage === stage);
    if (mine.length === 0) return null;
    const agent = mine.reduce((best, a) =>
      STATE_RANK[a.state] > STATE_RANK[best.state] ? a : best);
    return { agent, workers: mine.length };
  }).filter((s): s is ChainStep => s !== null);
}

/**
 * Whether a link of the chain is carrying work right now.
 *
 * It reads the **target's own state** and nothing else. The tempting alternative — walk
 * the chain from the front and light up whatever comes after the last finished stage — is
 * the thing that breaks: `src/memstara/pipeline/board.py:1506-1507` says outright that
 * "stages overlap as well as workers. data#1, data#2 and ml#1 all run at once", so several
 * links are genuinely live at once and any single "we are here" pointer is wrong most of
 * the time. n8n has this bug today
 * (n8n-io/n8n#22385): its live path goes blank on a fan-out because it is drawn by
 * traversal rather than by node state.
 */
export function linkIsLive(target: SceneAgent): boolean {
  return target.state === "working" || target.state === "moving";
}

/**
 * "4s", "1m 20s", "2h 5m" — or null when there is no time to measure from.
 *
 * The API sends UTC (`viewer/api/scene.py:139-143`), so the arithmetic is unambiguous, but
 * `now` is the browser's clock and the timestamp is the API container's. A machine whose
 * clock is behind would otherwise produce a negative age, so the seconds are floored at
 * zero rather than shown as a countdown.
 */
export function elapsedSince(iso: string | null, now: number): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;

  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  if (seconds < 60) return `${seconds}s`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;

  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
