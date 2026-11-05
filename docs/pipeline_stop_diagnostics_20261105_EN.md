# Pipeline progress and stop diagnostics — November 5, 2026

## Observed incident

The completed-result count and the displayed current combination were measuring
different things. The initial execution completed combinations 1–28. Its selective
retry completed combinations 29–49: 28 + 21 = 49 saved results. Combination 50 had
a completed question-generation call, but no recorded downstream hypothesis/ML
call. The retry's 22nd attempt was combination 50, not combination 22.

The stop/finalization writer incorrectly used the number of journal entries as
the combination ID. Later Resume attempts also produced phantom journal entries
22 and 23 outside the frozen retry selection, 29–64. Historical artifacts are
retained; presentation now derives the original identity from the execution
manifest and counts only IDs in the frozen selection. New stop/finalization writes
use original IDs. The API exposes the recorded ordinal and identity source when
it derives a correction.

The inspected retry is `board_20261105T040348_495806`, under
`outputs/runs/2026-11-05T040348_495806_board_1trials/`. Its source execution is
`board_20261104T234655_177753`.

## Evidence for the interruption

All timestamps below are UTC. These observations describe the saved incident;
they do not establish that a completed agent call caused a later controller error.

| Saved evidence | Observation | Limit of the conclusion |
|---|---|---|
| `board_read_events.jsonl`, 06:27:20 → 06:27:51 | A read timed out, then recovered on attempt 2. | A transient read failure occurred. |
| Same journal, 06:28:21 and 06:28:52 | Further read timeouts preceded the stop. | The journal did not preserve the complete final MCP response. |
| Same journal, 13:26:43–13:27:52 | The subsequent Resume also encountered repeated timeouts; one read recovered on attempt 3. | Concurrent reads had no correlation IDs in this historical log. Their attempts cannot all be assigned to a single request. |
| `failure_frames.json` and execution manifest | The outer `ExceptionGroup` originated while restoring/producing the seed; the latest completed call was question generation for original combination 50. | The old recorder omitted child exceptions. Its exact final inner error/code cannot be reconstructed. |
| Runtime MCP timeout behavior | An MCP response timeout is raised as `McpError` with code 408, rather than Python `TimeoutError`. The previous recovery handler did not catch this wrapper. | This is a verified recovery gap; the historical missing child exception prevents proving the code of every past failure. |
| Scheduler polling implementation | Frequent reads requested all historical match traces, model evaluations and interpretation text. | This unnecessary transfer can increase work and latency. Its precise contribution to the observed timeout was not measured. |

At the 14:35 UTC follow-up inspection, the same execution had been resumed again
and reported combination 50. Another read timeout was appended at 14:35:35.
That live execution was not restarted or modified by this repair. The source
changes described below require a newly built application image.

## Changes

1. Scheduler state reads use a compact response containing only fields needed
   for scheduling, failure checks and interpretation fan-out. The ordinary full
   evidence read/export remains available.
2. Read-only recovery recognizes MCP code 408 as well as supported Python and
   database transient errors. It records bounded attempts and delays. It does
   not replay non-idempotent writes or whole agent runs.
3. Each read/tool operation receives a correlation ID, original combination ID,
   UTC timestamps, timeout, elapsed time, attempt information and final outcome.
   Invalid JSON/envelopes are recorded as failures, not completed operations.
4. Exception groups retain child causes, source locations, MCP codes, database
   SQLSTATE/errno and available provider request/status metadata. Normalized
   timeout exceptions retain the original MCP exception as their cause.
5. Stop incidents are appended across Resume attempts, and terminal status
   links to the corresponding incident. Pause, cancellation, startup rejection,
   execution-ownership loss, execution failure and cleanup warning have separate
   event types/codes. The first classified execution failure remains preserved.
   Registry reconciliation failures are recorded even when they occur during
   finalization after the main controller's exception handler has finished.
6. Progress closing/finalization uses original combination IDs. Presentation of
   old retry artifacts excludes phantom ordinals without overwriting evidence.

## Where to inspect

All paths are relative to the execution directory.

| File | Purpose |
|---|---|
| `pipeline_status.json` | Latest state and incident/diagnostic links for controller failures. |
| `stop_events.jsonl` | Chronological incident history across Resume attempts. `failure_detected` and `failed` can describe detection and terminal handling of the same incident; do not count rows as independent failed combinations. |
| `failure_frames.json` | Latest controller exception tree and last recorded call context. |
| `pipeline_failure.json` | First classified execution failure, including stage and original combination ID. |
| `board_read_events.jsonl` | Per-operation MCP/read attempts, timings, outcomes and structured failure metadata. |
| `request_events.jsonl` / `provider_diagnostics.jsonl` | Existing model-request and provider-response metadata, linked by run/request/Loop IDs where available. |
| `connection_health.json` / `infrastructure_status.json` | Existing execution-ownership/connection checks and infrastructure interruption classification. |
| `execution.json` / `iteration_outcomes.json` | Actual recorded calls and original scheduled combination outcomes. |

Structured diagnostics omit raw exception messages, tool arguments, prompt bodies,
patient values and credentials. Known reason codes and nested metadata supply
diagnostic detail without copying those payloads. Depth/child-count limits are
marked explicitly if reached. These improvements apply prospectively; missing
historical inner exceptions cannot be recovered by changing the recorder.

A hard process kill, host crash or unwritable/full filesystem can prevent a final
record. An absent terminal record means the evidence is incomplete. It must not
be interpreted as successful completion or automatically attributed to a user.

## Applying the repair

Build and restart the control service only during a confirmed idle period. Do
not reset execution history or databases to repair this incident. Retain the 49
saved results and their costs. Use the application's selective unfinished-
combination retry path to recover original combinations 50–64 after verifying
the saved state; do not force an incompatible checkpoint to resume under changed
code. A genuinely fresh experiment is a separate action and does not erase history.
