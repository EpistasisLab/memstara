# Experiment history clearing and report-only recovery

Tracking issue: https://github.com/HyunjunA/memstara/issues/237

## Deploy after active experiments have ended

Development and local verification do not deploy changes or clear history.
From the installation directory, use the ordinary startup command:

```sh
./start.sh
```

Do not add `--reset-execution-history` merely to install the new UI. Normal startup
preserves execution history. Refresh the browser after deployment to load the new
UI code. The control, API and web images all need the changes.

## Clear button

**Clear**, immediately before **Estimated total**, opens an installation-wide
dialog. Choose **Back up and clear** or **Clear without backup**, then type
`CLEAR ALL HISTORY`. This affects every configured pipeline, not only the selected
one. Running drivers are asked to end; the job refuses deletion if they remain
active. A shared/exclusive lease blocks start/delete races, including CLI drivers.
Inherited ML-worker leases are checked independently before deletion.

The retained items are pipeline/workspace/model settings, research registrations,
CSV datasets, OKF knowledge, skills and `.env`. The deletion allowlist covers
execution/results/question records, experiment registry history, scoped Motoro
runs/messages/steps/memories, run folders, runtime logs and derived execution
workspaces. Unknown foreign-key dependents or unsafe filesystem paths abort the
operation; no unknown cascade is accepted. Agents and schemas are retained.

Backup mode uses matching PostgreSQL 16 `pg_dump`/`pg_restore` clients inside the
control image. It saves both complete database archives and the execution files.
PostgreSQL archive listing, a full file-archive read and SHA256 verification must
finish before deletion. Partial backups have no `COMPLETE.json` marker and never
authorize deletion. Backups live under `outputs/history-backups/<job-id>/` and a
verified bundle can be downloaded through the authenticated UI. Cluster roles are
not included; a full restore is not automatically rehearsed. Existing backups are
not removed by later clears.

The asynchronous job is recorded in `outputs/history-reset-state.json`. A partial
destructive failure is reported honestly and blocks new launches until an explicit
retry succeeds. The two databases and filesystem are not one distributed
transaction, so failures after a commit can leave a partial clear. The job never
reports success until deletion and preservation checks pass.

On success, `runs/history_epoch.json` changes revision. Each API worker drops old
caches/background refreshes and rejects responses from a previous revision. Open
browser tabs clear execution selections/receipts and reload, while preserving
settings/drafts/theme. The initial UI shows zero results/executions and `$0.0000`.
No new experiment is started by clearing.

## One experiment across continuation attempts

The source run and its explicit retries form one logical experiment. Original
attempt folders, IDs, output text, costs, configurations and failure logs remain
unchanged. `experiment_index.json` maps each original combination to its verified
Explanation receipt and source attempt. Its stable logical ID is the oldest
explicit source execution; matching pipeline names alone never join experiments.

Aggregation checks the pipeline, dataset, target, frozen combination schedule and
knowledge hashes. Cycles, ambiguous/missing sources, redirected receipts, invalid
hashes and incomplete outputs fail visibly. When more than one valid attempt
exists for a combination, lineage order selects the latest verified completion,
never the best score. Results, Conclusions and Usage expose the whole experiment
with the original combination numbers and original detail links.

Usage journals from older selective retries can contain phantom ordinals such as
22–24 outside their actual selection, 29–64. The cumulative usage reader filters
only those invalid journal entries against the frozen selection; it never removes
real calls or their costs. Thus a phantom blocked ordinal cannot hide an earlier
completed combination's Usage tile. Original journal files remain unchanged.

The observed `test-hiv-1` incident had 28 + 21 + 15 = 64 stored results. The old
report assembler looked only in the last attempt folder, saw its 15 reports and
incorrectly marked 1–49 missing. This global failure had no replicate ID, causing
the misleading `Retry unavailable: the failed replicate is not identified.` label.

## Recover the current report without rerunning 64 analyses

After deployment, use **Rebuild report** for the ended experiment. This path
assembles verified saved Explanation outputs without question generation, training
or LLM calls. It retains the actual old process exit code and original failure
record, and publishes a checksum-backed recovery receipt. The UI shows Completed
only when the explicit recovery receipt validates. A failed rebuild does not
pretend that missing outputs exist.

The equivalent command for the inspected execution is:

```sh
docker compose exec -T control python /app/deployment/exec_service.py python -m memstara.rebuild_report --run-tag board_20261105T144711_459900
```

This command repairs report artifacts and their registry mirror. It does not clear
history, recompute scientific results, change seeds or add model usage. Original
report/status text is retained in `report-before-rebuild.json`; the new validated
receipt is `report_rebuild.json`. An interrupted publication can be explicitly
retried using the same verified source outputs.

## Verification limits

Offline tests exercise 64 combinations in three attempts, provenance/tamper
checks, report-only recovery, partial publication, both clear choices, backup
failure, database rollback, settings preservation, cache revision barriers and
active-driver/ML leases. Browser fixtures verify 64 tiles in all three views,
cross-tab clearing, zero costs, confirmation, responsive dialogs and recovery
without an experiment-start request. No development test resets the installation.
The live Docker build, backup/restore rehearsal and deployment remain operator
actions after the current experiment ends.
