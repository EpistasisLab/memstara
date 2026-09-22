import { agentStageLabel } from "./stage";
import type { PlaybookStage, RunRequest } from "../store/control";
import type { SceneAgent } from "../types";

/** Project telemetry onto the configured hypothesis slots. A telemetry run is one
 * LLM invocation, not another configured agent. History and repeated calls must never
 * grow the hypothesis column. The full telemetry remains available in Agents/Activity. */

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
  return Math.min(MAX_HYPOTHESIS_AGENTS, Math.max(1, Math.floor(form.hypothesis_agents) || 1));
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
export const MAX_HYPOTHESIS_AGENTS = 4;

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

/** Remove the chosen interpreter and its skill together, retaining at least one. */
export function withoutInterpreterSlot(form: RunRequest, slot: number): RunRequest {
  if (form.interpret_agents <= 1 || slot < 0 || slot >= form.interpret_agents) return form;
  const slots = asSlots(form.playbook_interpreter, form.interpret_agents);
  slots.splice(slot, 1);
  return { ...form, interpret_agents: form.interpret_agents - 1, playbook_interpreter: fromSlots(slots) };
}

/** What the form currently gives one card's slot — the reader `withPlaybookAt` writes.
 *
 *  Paired with it deliberately: a card's select shows this and sets that, so if the two ever
 *  cut the field differently the control would display something other than what it just
 *  set, which is the one way a select can be wrong without looking wrong. */
export function playbookAt(form: RunRequest, stage: PlaybookStage, slot: number): string {
  if (stage === "interpreter") return asSlots(form.playbook_interpreter, form.interpret_agents)[slot] ?? "";
  if (stage !== PLANNABLE) return form[`playbook_${stage === "report" ? "explanation" : stage}`];
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
  if (stage === "interpreter") {
    const slots = asSlots(form.playbook_interpreter, form.interpret_agents);
    if (slot < 0 || slot >= slots.length) return form;
    slots[slot] = book;
    return { ...form, playbook_interpreter: fromSlots(slots) };
  }
  if (stage !== PLANNABLE) return { ...form, [`playbook_${stage === "report" ? "explanation" : stage}`]: book };
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

/** Match the backend's durable identity, independent of the number of slots. */
function plannedAgentName(standards: string[], slot: number): string {
  const book = standards[slot];
  return book ? `${HYPOTHESIS_AGENT}-${book}` : HYPOTHESIS_AGENT;
}

/** One stable card per configured skill, preferring its active, newest invocation. */
export function withPlannedAgents(agents: SceneAgent[], form: RunRequest, preview = false): SceneAgent[] {
  if (preview) {
    agents = (["data", "ml", "report"] as const).map(stage => ({
      id: `planned:${stage}`, stage, label: agentStageLabel(stage), name: `memstara-board-${stage}`,
      worker: null, slot: 0, running: 0, playbook: form[`playbook_${stage === "report" ? "explanation" : stage}`], state: "planned",
      at: null, home: { x: 0, y: 0 }, carrying: null, run_id: null, since: null, last_tool: null, windows: [],
    }));
  }
  return ["hypothesis", "interpreter"].flatMap(stage => plannedStage(agents, form, stage as "hypothesis" | "interpreter"))
    .concat(agents.filter(a => a.stage !== "hypothesis" && a.stage !== "interpreter").map(a => ({ ...a,
      playbook: a.stage === "curator" ? a.playbook : form[`playbook_${a.stage === "report" ? "explanation" : a.stage}`] ?? a.playbook,
    })));
}

function plannedStage(agents: SceneAgent[], form: RunRequest, stage: "hypothesis" | "interpreter"): SceneAgent[] {
  const wanted = stage === "hypothesis" ? wantedAgents(form) : Math.min(4, Math.max(1, form.interpret_agents || 1));
  const standards = asSlots(form[`playbook_${stage}`], wanted);
  const observed = agents.filter(a => a.stage === stage);
  const used = new Set<string>();
  const priority = (a: SceneAgent) => a.state === "working" ? 3 : a.state === "moving" ? 2 : a.state === "unknown" ? 1 : 0;
  const time = (a: SceneAgent) => Date.parse(a.last_tool?.at ?? a.since ?? "") || 0;
  const hypotheses = standards.map((book, slot): SceneAgent => {
    const candidates = observed.filter(a => !used.has(a.id) && (a.playbook ?? "") === book)
      .sort((a,b) => priority(b) - priority(a) || time(b) - time(a) || a.id.localeCompare(b.id));
    const current = candidates[0];
    if (current) {
      used.add(current.id);
      return { ...current, slot, id: `configured:${stage}#${slot}` };
    }
    return {
      id: `configured:${stage}#${slot}`, stage,
      label: stage === "hypothesis" ? "Hypothesis" : "Interpreter", worker: null, slot, running: 0,
      name: stage === "hypothesis" ? plannedAgentName(standards, slot) : `memstara-board-interpreter${book ? `-${book}` : ""}`, playbook: book, state: "planned",
      at: null, home: observed[0]?.home ?? { x: 0, y: 0 }, carrying: null,
      run_id: null, since: null, last_tool: null, windows: [],
    };
  });
  return hypotheses;
}
