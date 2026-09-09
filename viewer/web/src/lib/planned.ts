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
 * **The form decides the count; a figure that is not resting is never removed.** The first
 * version of this padded only — `max(observed, requested)` — and it was wrong in the case
 * anyone sees first. `LAST_ROSTER` keeps the previous run's workers on the snapshot however
 * long ago it ran (`A-41`), so a fresh page with the form at its default of 1 drew **three**
 * hypothesis cards: the three from yesterday's run, all `idle`, outnumbering the form and
 * winning. The number said one and the picture said three, which is the same complaint as
 * `A-41` seen from the other side.
 *
 * So the rule is a single one, and it is the one a reader already assumes: **the hypothesis
 * column shows the number on the form.** The exception exists to protect work, not history —
 * a figure that is `working`, `moving` or `unknown` is kept even past the form's count,
 * because dropping it would take a running worker off the screen, and because with the core
 * database unreadable (`unknown`) there is no basis for dropping anything at all. Only a
 * figure positively known to be resting is trimmed.
 *
 * Trimming and padding can therefore never both happen: whatever survives the trim is at
 * least the form's count, so there is nothing left to pad.
 *
 * The cost is worth stating. The form resets to `DEFAULT_REQUEST` on reload, so reloading
 * after a three-agent run shows one card until the number is set back to three. That is the
 * price of the picture answering to the control beside it, and it is paid where it is
 * cheapest to undo — one field, one keystroke.
 *
 * **Only the hypothesis station.** It is the one stage drawn per worker
 * (`viewer/api/stores.py`, `SPLITTABLE`) and the one whose count the form offers. The other
 * four are deliberately folded to a single figure carrying a count, so padding them would
 * invent a second `data` character the 2026-08-26 meeting asked to be drawn once — and
 * trimming them would remove the only figure a stage has.
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

/** A figure the form is not allowed to take off the screen.
 *
 *  `working` and `moving` are workers with something in hand or a run open — removing one
 *  because a number changed would hide work that is happening. `unknown` is the core
 *  database being unreadable, which is the state that exists precisely so the screen does
 *  not assert things it cannot check; "this one is surplus to the form" is such an
 *  assertion. `idle` is the only state that says, on the record, that this figure is doing
 *  nothing. See `viewer/api/scene.py:793-812` for where the four are decided. */
function isResting(agent: SceneAgent): boolean {
  return agent.state === "idle";
}

/**
 * `agents`, with the hypothesis station showing what the run form asks for.
 *
 * Short of the form's count it gains `planned` figures; past it, resting figures are
 * dropped and busy ones are not (see `isResting`).
 *
 * Returns the input array unchanged — the same reference — when neither is needed, so the
 * `useMemo` downstream of it does not see a new array on every poll.
 */
export function withPlannedAgents(agents: SceneAgent[], form: RunRequest): SceneAgent[] {
  const observed = agents.filter((a) => a.stage === PLANNABLE);
  // A number input yields `NaN` for the moment it is empty mid-edit, and 0 or a fraction is
  // one keypress away. Every branch below indexes with this, and `NaN` makes all of them
  // quietly do nothing — a figure that stops responding while the field is being retyped.
  //
  // This clamps the **drawing**, not the request: `startRun` still posts what was typed and
  // the service still refuses it in words, which is the rule this form keeps everywhere
  // else. The station is never drawn with fewer than one figure because the API never sends
  // fewer than one.
  const wanted = Math.max(1, Math.floor(form.hypothesis_agents) || 1);

  // Trimmed from the tail, by id rather than by rebuilding the list, so that every other
  // stage keeps the order and the identity the API gave it.
  const surplus = new Set(
    observed.filter((a, i) => i >= wanted && isResting(a)).map((a) => a.id),
  );
  if (surplus.size) return agents.filter((a) => !surplus.has(a.id));

  // Nothing was trimmed, so every observed figure is still here and the next free slot is
  // the count of them — which is what the padding below indexes from.
  const missing = wanted - observed.length;
  if (missing <= 0) return agents;

  // Where the planned figures stand. The floor plan positions by `home`, and every figure
  // of one station shares it, so it is copied from a real figure rather than restated here
  // — `stores.HOME` is the API's to own. A station always sends at least one figure (a
  // resting one when it has nothing running), so there is one to copy from; the `??` is
  // for the frame before the first snapshot arrives, where the whole scene is empty
  // anyway and nothing is drawn.
  const home = observed[0]?.home ?? { x: 0, y: 0 };
  const label = observed[0]?.label ?? "Hypothesis";
  // `wanted`, not the raw field, for the same reason — and it is also the number of selects
  // the Playbooks disclosure is showing, so slot *i* here is the standard select *i* has.
  const standards = asSlots(form.playbook_hypothesis, wanted);

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
