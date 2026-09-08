import type { StageId } from "../types";
import { CHAIN } from "./chain";

/**
 * The per-agent transcript, read back out of the driver's console.
 *
 * The console is not only the driver talking about itself. Every time an agent finishes,
 * `show_what_agent_did` (`src/memstara/pipeline/board.py:591-663`) prints a bordered block
 * of what that one agent actually did — every thought, every tool call with its arguments,
 * every result, and the final answer:
 *
 *     ┌─ what hypothesis1 did (19 steps · tokens 382172/4042 · $1.1352)
 *     │  think   I'll start by claiming my question and describing the dataset …
 *     │  tool    memstara-blackboard.claim_question({"run_tag": "loop_verify", …)
 *     │          → {"question_id": 98, "text": "from a metapath enumeration bou …
 *     │  answer  Both questions were accepted cleanly — no duplicates, no skips …
 *     │  req     9 LLM calls — what was sent is in trace/01_hypothesis1.llm.txt
 *     └─
 *
 * So the material for an agent-level log window was already arriving through
 * `/control/runs/latest/log`; what was missing was somebody reading it. This module is that
 * reader and nothing else — no React, no fetching, one array of lines in and one array of
 * blocks out.
 *
 * **Why the parser is safe against overlapping agents.** Several stages genuinely run at
 * once (`board.py:1506-1507`), so two blocks could in principle be printed at the same
 * time. They cannot interleave line by line, and that is a guarantee rather than a hope:
 * `board.py:559-562` says every print above happens after that call's two awaits with no
 * await in between, so one block reaches stdout in a single slice. Blocks arrive whole, in
 * some order. That is exactly what a line-oriented parser needs.
 *
 * **Three things it cannot give you**, each stated where the window can repeat it:
 *
 *  1. A block only exists **after** the agent has finished — `show_what_agent_did` is
 *     called on the line after `execute_run` returns (`board.py:542,562`). A stage that is
 *     working right now has no block yet, and that is not the same as having done nothing.
 *  2. Every line is **already truncated** by `_short()` at 88, 70 and 86 characters
 *     (`board.py:584-588,648-649`). The untruncated text is in `trace/NN_stage.txt`.
 *  3. What was *sent to the model* is never printed, on purpose (`board.py:656-658`) — a
 *     single request runs to tens of thousands of characters. Only the count comes through,
 *     with the name of the trace file that holds the rest.
 */

export type BlockEntryKind = "think" | "tool" | "result" | "answer" | "req";

export interface BlockEntry {
  kind: BlockEntryKind;
  /** One line, already flattened and shortened by the driver. */
  text: string;
}

export interface AgentBlock {
  /** Order of appearance in the transcript. Also the React key: two blocks for the same
   *  worker are ordinary (`data#1` runs once per lap) and must not collapse into one. */
  seq: number;
  /** The driver's own name for the worker — `curator0`, `hypothesis1`, `data#1`, `report`. */
  worker: string;
  /** Which chain stage that worker belongs to, or null if the name is one we do not know. */
  stage: StageId | null;
  steps: number;
  promptTokens: number;
  completionTokens: number;
  /** US dollars, as the driver computed it. */
  cost: number;
  entries: BlockEntry[];
  /** `trace/01_hypothesis1.llm.txt` — where the raw requests went. Null until the `req`
   *  line arrives, and absent entirely for a call that made no LLM request. */
  traceFile: string | null;
  /** The closing `└─` has not arrived. Either the agent is still being written out, or the
   *  transcript was cut off at the top by the line cap. Drawn as "still coming". */
  open: boolean;
}

/** The head of a block. `stage` is `\S+` rather than a known name because the driver writes
 *  `"?"` when it has none (`board.py:529`), and a block labelled `?` is still a real block. */
const HEAD = /^\s*┌─ what (\S+) did \((\d+) steps · tokens (\d+)\/(\d+) · \$([\d.]+)\)/;
const TAIL = /^\s*└─\s*$/;

/** Matched in this order. `→` is tested first so a result whose text happens to begin with
 *  a keyword cannot be mistaken for a new entry. */
const ENTRY: [BlockEntryKind, RegExp][] = [
  ["result", /^\s*│\s+→\s?(.*)$/],
  ["think", /^\s*│\s+think\s+(.*)$/],
  ["tool", /^\s*│\s+tool\s+(.*)$/],
  ["answer", /^\s*│\s+answer\s+(.*)$/],
  ["req", /^\s*│\s+req\s+(.*)$/],
];

/**
 * `hypothesis1` -> `hypothesis`, `data#1` -> `data`, `interpret#2` -> `interpreter`.
 *
 * The worker names carry a trailing index in two shapes — a bare number for the ones the
 * driver spawns by count (`board.py:1001,1374`) and `#N` for board workers (`:1559`) — so
 * both are stripped before the name is looked up.
 *
 * `interpret` is the one genuine mismatch in the whole vocabulary: the console says
 * `interpret#1` and the chain calls the stage `interpreter` (`lib/chain.ts:CHAIN`, mirroring
 * `viewer/api/stores.py:177-183`). It is aliased here rather than renamed on either side,
 * because both names are load-bearing where they are.
 */
export function workerStage(worker: string): StageId | null {
  const base = worker.replace(/#?\d+$/, "");
  const name = base === "interpret" ? "interpreter" : base;
  return CHAIN.includes(name as StageId) ? (name as StageId) : null;
}

/**
 * Split a console transcript into one block per finished agent, oldest first.
 *
 * Anything outside a block is dropped — that is the driver's own narration, which the
 * driver-mode window shows in full through `RunLog`. Anything inside a block that is not a
 * recognised entry is dropped too rather than closing the block: `console.log` carries
 * structlog lines from elsewhere in the process, and one of them landing mid-block must not
 * truncate the agent's transcript.
 */
export function parseAgentBlocks(lines: string[]): AgentBlock[] {
  const blocks: AgentBlock[] = [];
  let current: AgentBlock | null = null;

  for (const line of lines) {
    const head = HEAD.exec(line);
    if (head) {
      // A head while one is already open means the closing rule was lost — off the top of
      // the line cap, most likely. The open one is kept as it stands rather than discarded.
      current = {
        seq: blocks.length,
        worker: head[1],
        stage: workerStage(head[1]),
        steps: Number(head[2]),
        promptTokens: Number(head[3]),
        completionTokens: Number(head[4]),
        cost: Number(head[5]),
        entries: [],
        traceFile: null,
        open: true,
      };
      blocks.push(current);
      continue;
    }

    if (!current) continue;

    if (TAIL.test(line)) {
      current.open = false;
      current = null;
      continue;
    }

    for (const [kind, pattern] of ENTRY) {
      const found = pattern.exec(line);
      if (!found) continue;
      current.entries.push({ kind, text: found[1] });
      if (kind === "req") {
        const file = /trace\/\S+/.exec(found[1]);
        current.traceFile = file ? file[0] : null;
      }
      break;
    }
  }

  return blocks;
}

/** Just the blocks belonging to one stage, in the order they ran. */
export function blocksForStage(blocks: AgentBlock[], stage: StageId): AgentBlock[] {
  return blocks.filter((b) => b.stage === stage);
}
