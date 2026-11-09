# Cumulative execution synchronization audit

Issue: https://github.com/HyunjunA/memstara/issues/238

## Observations before changes

Measurements below use recorded start/end times from one continuation, avoiding a
controller restart between the compared groups. One Loop is one replicate, not one
LLM request. Each group includes different skill combinations, so the comparison
is evidence of growing overhead, not a controlled performance benchmark.

| Loops | Approximate pipeline range | Mean elapsed seconds per Loop | Sum of recorded agent seconds per Loop | Difference | Mean gap between calls within a Loop |
| --- | --- | ---: | ---: | ---: | ---: |
| 39–64 | 20–32 | 249.7 | 210.8 | 38.9 | 4.2 |
| 65–96 | 33–48 | 363.2 | 230.5 | 132.7 | 14.7 |
| 97–128 | 49–64 | 508.8 | 254.0 | 254.8 | 27.9 |

The difference is time outside the recorded agent execution intervals; it includes
orchestration, evidence collection, synchronization and other work. It is not a
direct measurement of registry synchronization alone. Before interruption, the
latest ten question calls averaged 14.34 seconds of agent execution, while nine
inter-call gaps averaged 64.48 seconds. The execution checkpoint containing the
full call roster was approximately 43 MB, with more than 830 calls recorded.

Loop 129 also repeatedly declined to propose a question. That is a separate
scientific-instruction/recovery problem: repetition increases total requests and
tokens, whereas registry mirroring does not itself make LLM requests. The minimal
Whole Knowledge Graph V2 change addresses that separate interpretation issue.

## Source inventory before optimization

Locations below identify functions rather than assuming line numbers remain
stable after implementation.

| Location | Repeated work | Frequency and implication |
| --- | --- | --- |
| `pipeline/board.py::_call_agent_uncontrolled` | Awaits `_trace_one`, `sync_after_agent`, and console output after recording `duration_seconds` | Every agent completion; this work delays the next call but is absent from the agent's recorded duration |
| `pipeline/board.py::write_execution_manifest` | Serializes all `_CALLS` into a compact viewer manifest and a full, fsynced `calls_checkpoint.json` | Start, completion, exception and trace publication; the full checkpoint includes prior prompts/evidence |
| `experiment_registry.py::_sync` | Loads all call checkpoint records and parses the complete cost ledger | Every routine mirror and explicit reconciliation |
| `experiment_registry.py::_sync` | Calls Motoro `get_run` and `get_run_steps` for every historical agent | Cumulative database reads, followed by evidence serialization |
| `experiment_registry.py::_sync` | Upserts all agent evidence and inserts/reads every historical cost receipt | Cumulative database round trips even when old records are unchanged |
| `experiment_registry.py::_sync` | Fetches all blackboard evaluations for the execution | Includes prior task evidence when only the current Loop changed |
| `experiment_registry.py::artifacts` | Recursively enumerates the execution and referenced analysis files; reads every file to recompute SHA-256 | Rehashes historical request payloads, traces and growing journals on every mirror |
| `experiment_registry.py::sync` | Retries the entire mirror transaction up to five times on selected transient errors | A retry may repeat the cumulative work, but must never rerun the agent |
| `experiment_registry.py::sync_after_agent` | On exhausted permission failures, re-reads and verifies every completed call's evidence | Exceptional recovery path, not normal overhead; integrity checks must remain |
| `specialist_explanation.py::finish` | Reads every `explanation_io/model-*.json` to select one agent's model records; matching files are parsed twice | Grows with prior Explanation calls |
| `pipeline/proposal.py::execute_stage/save_calls` | Rewrites cumulative call lists and mirrors the execution after each proposal stage | A separate execution mode with the same scaling risk |
| `pipeline/checkpoint.py::Checkpoint.save` | Atomically stores driver phase/control state | Required for safe resume; distinct from copying full historical prompts or Motoro step evidence |

## Work that must not be confused with the cumulative mirror

- `_trace_one` and `show_what_agent_did` read the current agent, not all historical
  agents. Some current-agent queries are duplicated, but this alone does not explain
  history-dependent growth.
- `write_traces` skips already exported traces and performs final inventory work.
  Full final reconciliation remains necessary for independent completeness checks.
- Startup/recovery may need one full backfill. It must not become a full backfill
  after every ordinary completion.
- Viewer cost/export endpoints can read execution history when the user requests
  it; they are not direct calls from the agent completion path.
- Specialist XAI uses the selected task's manifest and evidence files. This audit
  did not find the Explanation-style whole-directory model-record scan there.

## Implementation requirements

1. Publish durable per-agent call records, retain compact viewer compatibility,
   and recover old aggregate checkpoints without rewriting historical runs.
2. Mirror only changed call records and newly appended cost receipts during normal
   execution. Advance derived synchronization state only after transaction commit.
3. Index changed evidence and current task artifacts, without rehashing historical
   files after every call. Keep full final/manual reconciliation as the integrity
   and completeness check.
4. Preserve pending work on failure and safely backfill after process restart or
   invalidated incremental state. Serialize concurrent mirrors of the same run.
5. Store Explanation model receipts by agent identity; retain a legacy reading path.
6. Record separate timings and item/byte counts for trace export, database mirroring,
   artifact indexing and console reporting. Do not report non-model overhead as
   LLM latency or claim elapsed time alone establishes one cause.
7. Test scaling, rollback, restart, concurrency, cost conflicts, evidence integrity,
   old-format recovery and the final complete export.

## Implemented changes

| Location | Resulting behavior |
| --- | --- |
| `execution_journal.py`; `board.py::write_execution_manifest` | Writes the changed agent to `call_records/<run-id>.json`. Retains the compact `execution.json` interface. Full legacy call snapshots are written at finalization, not every call. Recovery and audit scripts merge the legacy snapshot with durable per-agent records. |
| `experiment_registry.py::sync_incremental` | Serializes same-run mirrors; performs an initial backfill when disposable state is absent; commits only changed call/evidence records and appended receipts on subsequent calls. Failure invalidates the cache so pending work is backfilled safely. |
| `experiment_registry.py::appended_costs` | Reads complete JSONL records from the committed byte offset. Holds incomplete trailing records for the next read; replacement/truncation triggers a backfill. Validates newly encountered receipts against stored values in a batch. |
| `artifact_changes.py`; `checkpoint.py::atomic_json`; `request_evidence.py::write_private` | Tracks published file changes until the mirror transaction commits. Changes that occur during synchronization remain pending. |
| `experiment_registry.py::artifacts` | Normal mirrors hash changed candidate files and recently referenced task artifacts, reusing metadata fingerprints for unchanged files. Full reconciliation still traverses and hashes the complete execution. |
| `experiment_registry.py::_sync` | Limits routine blackboard evaluation reads to the current and preceding call's Loops. Preserves full reads for explicit full reconciliation and calls without a Loop identity. |
| `checkpoint.py::Checkpoint.phase` | Stores completed phase results in hash-verified `checkpoint_phases/` files; the driver checkpoint keeps references instead of repeatedly serializing historical result payloads. Old inline results remain readable. |
| `specialist_explanation.py::record_model/model_records` | Stores model receipts under the agent's own directory and reads only that directory. Keeps a fallback for historical flat-layout records. |
| `pipeline/proposal.py` | Uses the same per-agent journal and incremental mirror for routine completed stages. Retains explicit initial/final/error reconciliation. |
| `trace/diagnose.py`; audit scripts | Recognize the new journal and phase evidence locations. The live acceptance monitor reads the compact manifest instead of full historical prompts. |

`registry_metrics.jsonl` now records synchronization mode, changed-call count,
Motoro evidence reads, cost receipts read, artifact bytes hashed, board rows, and
phase durations. Agent postprocessing records separately time trace export,
registry synchronization and console output. These counters contain no model
prompts, credentials or patient records.

The compact viewer manifest, checkpoint control metadata and in-memory indexes
still grow with the number of recorded identities. The change removes repeated
historical payload reads, Motoro evidence retrieval and wholesale artifact hashing;
it does not claim that every bookkeeping operation is constant time.

Full backfill after restart or mirror failure and full final/manual reconciliation
are intentional. Historical receipt tampering is still detected by full validation;
normal append processing does not reread unchanged historical receipt bytes on
every call. This distinction preserves auditing without reinstating the bottleneck.

## Validation

The tests used synthetic evidence and a disposable PostgreSQL database reachable
only through a private local Unix socket. No production database was modified and
no model requests were made.

| Existing calls | Next-call Motoro run/step pairs fetched | New receipts read | Old execution recursively scanned? | Normal mirror seconds | First normal mirror after simulated restart/backfill |
| ---: | ---: | ---: | --- | ---: | ---: |
| 5 | 1 | 1 | No | 0.048 | 0.047 |
| 100 | 1 | 1 | No | 0.048 | 0.048 |
| 1,000 | 1 | 1 | No | 0.046 | 0.046 |

These timings describe small synthetic records on local PostgreSQL, with mocked
Motoro readers returning synthetic records. They are not a promised production
latency or a controlled speedup measurement against the old production run. Tests
assert the processing counts and forbid historical file reads/full-directory scans
during routine synchronization, rather than depending on timing thresholds.

Additional checks covered real transaction rollback after a conflicting receipt,
subsequent recovery of unmirrored calls, concurrent completions, changed-artifact
updates, incomplete ledger records, old-format journal recovery, tampered phase
results, process-death checkpoint recovery, and final historical receipt validation.
A large synthetic phase result remained outside the control checkpoint, whose
size stayed below 4 KB in that test.

- Main targeted regression command: 261 tests passed.
- Additional compatibility command with integration tests enabled: 49 tests passed
  (includes repeated incremental regression checks).
- The initial compatibility run exposed synthetic-input tests inheriting the local
  installation allowlist. The fixture was isolated from that installation policy;
  production source restrictions were not changed.

## Deployment and the stopped experiment

Production has not been updated: container runtime operations were rejected by the
execution environment. The affected experiment is stopped and its saved evidence
is retained. A normal `./start.sh` rebuild retains history; the reset flag is not
part of this operation.

The minimal Whole Knowledge Graph V2 is prepared under the same skill ID with a
new content hash and visible V2 title. The explicit `retry_updated_skills` mode
permits a changed hypothesis skill only if it was not scheduled before the retry
boundary. Other skills, schedule order, data and saved seed policy stay fixed.
Source execution files are never rewritten. The new attempt records old/new skill
identities in its frozen configuration and `retry_lineage.json`.

For the reviewed stopped execution, a local dry validation selected Loop 129 through
160 and found exactly one changed skill: Whole Knowledge Graph V2. A private helper
checks the deployed skill hash and expected latest execution before submitting the
continuation. It has not been run to start a new experiment.
