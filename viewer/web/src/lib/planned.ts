import type { PlaybookStage, RunRequest } from "../store/control";
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

/** Slots back to the field — the other half of `asSlots`, and here for the same reason.
 *
 *  All-empty collapses to `""`, the prompt as written, which is what every run before
 *  playbooks was and what `build_argv` reads as *no flag at all*. A partly-filled set is
 *  joined as it stands, empties included, so the service sees the mismatch it is going to
 *  refuse and says so in words. Quietly dropping the empties would turn "two of three
 *  chosen" into a request for two agents, which is not what the form said.
 *
 *  It was in `StartRun.tsx` until 2026-09-09, when the pipeline cards became writers of the
 *  form too (`A-44`). Two functions joining one field the same way is how the two stop
 *  agreeing. */
export function fromSlots(slots: string[]): string {
  return slots.some((s) => s) ? slots.join(",") : "";
}

/** How many hypothesis figures the form is asking to see.
 *
 *  A number input yields `NaN` for the moment it is empty mid-edit, and 0 or a fraction is
 *  one keypress away. Every caller indexes with this, and `NaN` makes all of them quietly
 *  do nothing — a figure that stops responding while the field is being retyped.
 *
 *  This clamps the **drawing and the slot arithmetic**, not the request: `startRun` still
 *  posts what was typed and the service still refuses it in words, which is the rule this
 *  form keeps everywhere else. Never fewer than one, because the API never sends fewer. */
function wantedAgents(form: RunRequest): number {
  return Math.max(1, Math.floor(form.hypothesis_agents) || 1);
}

/** The most hypothesis agents the service will start — `_MAX_HYPOTHESIS_AGENTS`
 *  (`src/memstara/control/request.py:70`).
 *
 *  **This does not make the form a validator**, and the distinction is the whole reason it
 *  is safe to have the number here at all. The `Hypothesis` field still accepts a 9 and the
 *  service still refuses it in its own sentence naming the field, which keeps one place
 *  deciding what a legal request is. What this bounds is the `+` button, and a button is an
 *  offer rather than a check: one that reliably produced a 400 would be an offer worth
 *  nothing. Past the ceiling it says so instead of disappearing, because a control that
 *  vanishes explains nothing about why. */
export const MAX_HYPOTHESIS_AGENTS = 8;

/** The form asking for one more hypothesis agent, standards re-cut to match.
 *
 *  The same pairing `StartRun.tsx` does when the number field changes: the count and the
 *  standards are matched by position and the service refuses the pair when their lengths
 *  disagree, so they move together or not at all. Returns the form unchanged at the
 *  ceiling. */
export function withOneMoreAgent(form: RunRequest): RunRequest {
  const wanted = wantedAgents(form);
  if (wanted >= MAX_HYPOTHESIS_AGENTS) return form;
  return {
    ...form,
    hypothesis_agents: wanted + 1,
    playbook_hypothesis: fromSlots(asSlots(form.playbook_hypothesis, wanted + 1)),
  };
}

/**
 * The form with one hypothesis slot taken back out.
 *
 * Removes *that* slot rather than the last one, so the standards below it move up and the
 * card the `×` was on is the card that goes. Shrinking through the number field can only
 * ever drop the tail, which is why this is a separate function and not a decrement.
 *
 * Never below one — the station always draws at least one figure because the API never
 * sends fewer.
 */
export function withoutSlot(form: RunRequest, slot: number): RunRequest {
  const wanted = wantedAgents(form);
  if (wanted <= 1) return form;
  const slots = asSlots(form.playbook_hypothesis, wanted);
  if (slot < 0 || slot >= slots.length) return form;
  slots.splice(slot, 1);
  return {
    ...form,
    hypothesis_agents: wanted - 1,
    playbook_hypothesis: fromSlots(slots),
  };
}

/** What the form currently gives one card's slot — the reader `withPlaybookAt` writes.
 *
 *  Paired with it deliberately: a card's select shows this and sets that, so if the two ever
 *  cut the field differently the control would display something other than what it just
 *  set, which is the one way a select can be wrong without looking wrong. */
export function playbookAt(form: RunRequest, stage: PlaybookStage, slot: number): string {
  if (stage !== PLANNABLE) return form[`playbook_${stage}`];
  return asSlots(form.playbook_hypothesis, wantedAgents(form))[slot] ?? "";
}

/**
 * The form with one card's standard changed.
 *
 * The pipeline cards and the `Playbooks` disclosure in the left rail are two controls over
 * one value, and this is the single function both go through (`StartRun.tsx`,
 * `panels/ChainPanel.tsx`). Written as a pure function over `RunRequest` so neither
 * component has to know how the other spells the field: `playbook_hypothesis` is one
 * comma-separated string because `--playbook-hypothesis` is one argument, and the four
 * other stages are plain single values.
 *
 * `slot` is ignored off the hypothesis stage. Those stages provision one agent however many
 * workers claim from the board (`MULTI_PLAYBOOK_STAGES` in
 * `src/memstara/control/request.py`), so there is nothing for a second slot to mean and the
 * service refuses a second name there.
 */
export function withPlaybookAt(
  form: RunRequest,
  stage: PlaybookStage,
  slot: number,
  book: string,
): RunRequest {
  if (stage !== PLANNABLE) return { ...form, [`playbook_${stage}`]: book };
  const slots = asSlots(form.playbook_hypothesis, wantedAgents(form));
  // Out of range rather than clamped: a card's slot always comes from a figure this same
  // module put on the screen, so a slot past the end means the two have already disagreed
  // and writing at the wrong index would hide it behind a plausible value.
  if (slot < 0 || slot >= slots.length) return form;
  slots[slot] = book;
  return { ...form, playbook_hypothesis: fromSlots(slots) };
}

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
  // Shared with `withPlaybookAt`, and it has to be: the card at slot *i* writes to slot *i*
  // of the field, so the count that decides how many cards there are and the count that
  // decides how many slots the field is cut into must be the one number.
  const wanted = wantedAgents(form);

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
