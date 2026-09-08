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
 * It mirrors `viewer/api/stores.py:174-180` (`HOME`), whose comment says the same thing —
 * "in the order the pipeline runs them". Read from the snapshot's agent array instead,
 * the order would be whatever the API's dict iteration happened to give, which is right
 * today by accident rather than by contract.
 *
 * **Five links for six stages.** The curator is not here because it is not drawn as a
 * character of its own: `viewer/api/stores.py:202` (`DRAWN_AS`) folds it into the
 * hypothesis stage, which is why that link is labelled "Hypothesis · Curator". The
 * curator stage is still in the pipeline, still has its own agent, and still appears
 * under its own name in the feed and the cost table — this array is about who gets a box
 * drawn, nothing more. It has to agree with the backend, because `ChainPanel` compares
 * its length against the agents the API sent and reports a shortfall as an error.
 */
export const CHAIN: StageId[] = [
  "hypothesis",
  "data",
  "ml",
  "interpreter",
  "report",
];

/** The agents in chain order, skipping any the API did not send. */
export function chainAgents(agents: SceneAgent[]): SceneAgent[] {
  const byId = new Map(agents.map((a) => [a.id, a]));
  return CHAIN.map((id) => byId.get(id)).filter((a): a is SceneAgent => a !== undefined);
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
 * The API sends UTC (`viewer/api/scene.py:99-103`), so the arithmetic is unambiguous, but
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
