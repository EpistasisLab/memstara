import type { RunRequest } from "../store/control";
import type { SceneAgent } from "../types";

/**
 * The agents the run form is asking for, drawn beside the ones that exist.
 *
 * **What this is for.** Until 2026-09-09 the two pipeline drawings answered only "what has
 * run", because both read `useScene()` and nothing else, and the scene is derived from
 * agent runs the database actually holds (`viewer/api/scene.py`). So setting *Hypothesis*
 * to 5 on the form changed no pixel: the picture caught up minutes later, one card at a
 * time, as each worker's run opened. A number field that the picture beside it ignores is
 * a form the screen is not connected to.
 *
 * **What it must not become.** `lib/chain.ts` refuses to draw a completion tick because
 * nothing in the snapshot says a stage has finished, and that rule is not suspended here.
 * The way out is not to draw a fake agent — it is to draw a **different thing**: a figure
 * in the `planned` state, which asserts exactly what is known, that the form asks for this
 * one and it has not started. See `AgentState` in `types.ts` for why that is its own member
 * of the union rather than an `idle` card wearing a flag.
 *
 * **Padding only, never truncating.** The count drawn is `max(observed, requested)`. Five
 * workers running while the form says two is an ordinary thing — the form is edited after
 * the run starts — and honouring the two would take three live workers off the screen.
 * Observed always wins; the form can only ever add.
 *
 * **Only the hypothesis station.** It is the one stage drawn per worker
 * (`viewer/api/stores.py`, `SPLITTABLE`) and the one whose count the form offers. The other
 * four are deliberately folded to a single figure carrying a count, so padding them would
 * invent a second `data` character the 2026-08-26 meeting asked to be drawn once.
 */

/** The comma-separated `playbook_hypothesis` field as one entry per agent, padded to
 *  *agents* and truncated to it.
 *
 *  The field is one string because `--playbook-hypothesis` is one argument; the form is
 *  several selects because a person choosing three standards is choosing three things.
 *  A pure function so neither side has to hold the other's state.
 *
 *  It lives here rather than in `StartRun.tsx`, where it was written, because the planned
 *  figures need the same split: the standard shown on a planned card has to be the one the
 *  select in that slot is showing, and two functions splitting one string the same way is
 *  how the two stop agreeing. */
export function asSlots(value: string, agents: number): string[] {
  const chosen = value.split(",");
  return Array.from({ length: agents }, (_, i) => chosen[i]?.trim() ?? "");
}

/** Which stage the form can ask for more of. One name, compared against, rather than a
 *  list to keep in step with `stores.SPLITTABLE` on the other side of the API. */
const PLANNABLE = "hypothesis" as const;

/** `BOARD_AGENT_NAMES["hypothesis"]` (`src/memstara/pipeline/core.py:380`). */
const HYPOTHESIS_AGENT = "memstara-board-hypothesis";

/** The durable agent name the run *would* provision for one slot.
 *
 *  A faithful copy of `hypothesis_agent_names` (`src/memstara/pipeline/core.py:476-507`),
 *  including the branch that is easy to miss: **fewer than two standards means the single
 *  unsuffixed name**, because one standard and none both update the same durable row in
 *  place, exactly as every run before playbooks did. Only from two upwards is an agent named
 *  for what it carries.
 *
 *  Copied rather than approximated because the alternative — a positional `-2` — is a name
 *  that function deliberately refuses to produce, and predicting one here would put a row on
 *  screen that no run will ever create. */
function plannedAgentName(standards: string[], slot: number): string {
  if (standards.length < 2) return HYPOTHESIS_AGENT;
  return `${HYPOTHESIS_AGENT}-${standards[slot] ?? ""}`;
}

/**
 * `agents` plus one `planned` figure for every hypothesis agent the form asks for and the
 * scene does not have.
 *
 * Returns the input array unchanged — the same reference — when there is nothing to add, so
 * the `useMemo` downstream of it does not see a new array on every poll.
 */
export function withPlannedAgents(agents: SceneAgent[], form: RunRequest): SceneAgent[] {
  const observed = agents.filter((a) => a.stage === PLANNABLE);
  const missing = form.hypothesis_agents - observed.length;
  if (missing <= 0) return agents;

  // Where the planned figures stand. The floor plan positions by `home`, and every figure
  // of one station shares it, so it is copied from a real figure rather than restated here
  // — `stores.HOME` is the API's to own. A station always sends at least one figure (a
  // resting one when it has nothing running), so there is one to copy from; the `??` is
  // for the frame before the first snapshot arrives, where the whole scene is empty
  // anyway and nothing is drawn.
  const home = observed[0]?.home ?? { x: 0, y: 0 };
  const label = observed[0]?.label ?? "Hypothesis";
  const standards = asSlots(form.playbook_hypothesis, form.hypothesis_agents);

  const planned: SceneAgent[] = Array.from({ length: missing }, (_, i) => {
    const slot = observed.length + i;
    return {
      // Namespaced so it can never collide with a worker's own id. React Flow draws two
      // nodes sharing an id as one node, silently, and `hypothesis#3` is a name a real
      // worker takes the moment a fourth one starts.
      id: `planned:${PLANNABLE}#${slot}`,
      stage: PLANNABLE,
      label,
      // Null, not `hypothesis#${slot}`: that string is what a worker calls *itself* on the
      // board, and writing it here would put a name into the board's namespace that the
      // board has never seen. The card says "Not started"; it does not need a worker name
      // to say it.
      worker: null,
      slot,
      // Zero runs stand behind it, which is the literal truth and also what keeps the
      // `×N` badge off the card.
      running: 0,
      // The durable agent this slot would be provisioned as — see `plannedAgentName`. It
      // is never shown on the card (the chain card draws `label`, `worker` and `playbook`),
      // and the panels do not let a planned figure be clicked through to an agent page,
      // because the row it names may not exist yet. It is here because `SceneAgent` has the
      // field and a plausible-looking wrong value is worse than a correct one nobody reads.
      name: plannedAgentName(standards, slot),
      playbook: standards[slot] ?? "",
      state: "planned",
      at: null,
      home,
      carrying: null,
      run_id: null,
      since: null,
      last_tool: null,
      windows: [],
    };
  });

  return [...agents, ...planned];
}
