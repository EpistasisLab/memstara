# Start from a fresh checkout

This path uses repository examples and the pinned Motoro package; it does not
require the authors' datasets, sibling source checkouts or saved executions.
The synthetic example is provisional release material. A complete live acceptance
of the final release candidate and redistribution approvals are still required;
see [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## 1. Install and configure the runtime

For the normal Docker installation, follow [README steps 1–3](README.md#get-started).
Git and Docker with Compose are sufficient; `./start.sh` installs the application,
provisions its databases/Redis and registers the Heart Failure demonstration.
You may leave LLM credentials blank and configure Azure Foundry later in
**Add experiment → AI model → Set up a model**. A usable model is required before
continuing with an experiment. Other providers are not available for new web executions.

The Python commands below are an **optional native tutorial**, not additional
Docker installation steps. For that path, install uv and Python 3.12 or 3.13:

```sh
uv sync --frozen --extra dev --extra runtime
source .venv/bin/activate
```

Copy `.env.example` to `.env` only in a new checkout. For native execution, configure
model defaults using `MEMSTARA_LLM_*` and optional per-agent overrides, plus two
separate PostgreSQL databases and Redis. Motoro requires pgvector. Native viewer
setup also needs read-only database credentials; see the
[viewer guide](viewer/README.md) and [model configuration guide](DEVELOPER_GUIDE.md#model-profiles-and-their-limits).
Do not reuse the historical two-group profile keys for new setup. Keep secrets out of Git.

Run all following commands from the checkout root with the environment activated.
Relative research paths are resolved against the process working directory, not
against the JSON file's directory. Use absolute paths for your own files.

## 2. Inspect the included example without model calls

| Resource | Repository path | Meaning |
|---|---|---|
| CSV | `examples/research-inputs/dataset.csv` | 120 generated rows, four baseline predictors, identifier and binary outcome |
| Knowledge root | `examples/research-inputs/okf/` | Invented educational Markdown, not clinical evidence |
| Corpus entry | `examples/research-inputs/okf/index.md` | Corpus entry point |
| Knowledge document | `examples/research-inputs/okf/observations/simulated-risk.md` | Predictor meanings and simulation scope |
| Research contract | `examples/research-inputs/research.json` | Paths, target, positive/negative labels, prediction timing and excluded ID |
| Tutorial skills | `examples/research-inputs/skills/` | Custom Hypothesis instructions and historical Explanation reference |

```sh
python -m memstara.research_inputs inspect examples/research-inputs/research.json
python scripts/prepare_research_tutorial.py examples/research-inputs/research.json
```

Inspection should return `input_checks_passed: true`. The preparation script saves
a research version and one custom Hypothesis skill, selects a supplied Explanation
skill, validates that selection, and prints the
one-replicate `next_command`. It never executes that command. `execution_ready: false`
means runtime services, embeddings and model availability were not validated by
this offline step. It is not a failed experiment.

Choose a Hypothesis skill compatible with the selected research corpus. The
tutorial uses training-heavy Data, LR ML, the unchanged supplied SHAP skill and a
supplied Explanation skill. It does not register custom Interpretation/Explanation
instructions. Review the printed specialist choice for your question; its use is
not an endorsement of a synthetic outcome.

## 3. Start one execution and inspect its evidence

With the runtime ready, review and execute the printed `next_command`. Model and
embedding operations may incur costs or download model files. A selected research
profile prepares a separate analysis copy and matcher; do not build a cache for an
unrelated legacy cohort. The initial preparation may be slower than subsequent runs.

For a native browser workflow, follow [the viewer setup](viewer/README.md).
Keep that installation's control service running, then open its configured web port.
In **Add experiment → Use saved data**, choose the registered research version,
then the returned custom skill IDs, training-heavy Data, LR ML, SHAP Interpretation
and one replicate. Start only once; do not also execute the CLI command for the
same intended test. Native and Docker installations have separate registries unless
explicitly configured to share them. Docker users can register the synthetic example
with the [container command in the input guide](examples/research-inputs/README.md#register-the-supplied-synthetic-example).

Look for terminal `completed` status and saved results from every required stage,
including the final Explanation. Inspect the run under `outputs/runs/` for
configuration, traces, results, model usage and provenance. An input-inspection
success or visible pipeline tile alone is not end-to-end success. For a failure,
retain its execution ID and trace; see [developer diagnostics](DEVELOPER_GUIDE.md).
Token-price estimates are not actual Azure charges; billing attribution may be
unavailable even when model usage is recorded.

## 4. Replace the example with your own study

Copy `research.json` to an ignored local location such as `outputs/my-study.json`.
Keep the original examples unchanged. For CLI/JSON registration, use these fields:

| Field | What to supply |
|---|---|
| `name` | Required study name |
| `dataset_path` | Absolute path to an analysis-ready CSV |
| `knowledge_path` | Accessible OKF folder containing `index.md`; omitted for `llm_only` |
| `target.column` | Exact binary outcome column name |
| `target.description` | Optional in dataset mode; generated from the mapping when omitted. Required for proposal mode |
| `target.positive_label`, `target.negative_label` | Required exact values in dataset JSON; the upload UI instead assigns sorted labels automatically |
| `target.prediction_time`, `target.horizon` | Optional timing details; unspecified timing is not inferred |
| `excluded_columns` | Identifiers, post-outcome measurements and other prohibited predictors |
| `missing_policy` | `reject` (default), or explicit consent with `impute_train_v1` |
| `predictor_types` | Optional map of predictor names to `continuous` or `categorical`; use it for text categories and ambiguous numeric codes |

Provide at least four eligible predictors. Current support is one CSV and a binary
target: **5 MiB for browser uploads, 100 MiB for local-file inspection/registration**.
Multiclass is not supported here. With imputation consent, the ML pipeline fits
continuous means and categorical/binary modes on training data only, separately
inside each training CV fold when applicable. Upload/registration does not fill gaps.
Missing targets and entirely empty predictors are rejected. See the
[input guide](examples/research-inputs/README.md#source-preservation-and-dataset-requirements)
for automatic type-detection limits and categorical encoding.

The browser has no exclusion/type editor: prepare an upload copy without unwanted
columns, or register JSON with explicit exclusions/types. Prevent leakage by
excluding information unavailable at prediction time. The tool cannot infer the
clinical timing of every column for you.

For a new corpus, use the included OKF layout as a structural example: a root
`index.md`, domain directories and Markdown documents. Replace invented content
with material you are entitled to use; record source identifiers and distinguish
source evidence from your interpretation. A directory of PDFs is not automatically
an OKF corpus. No external graph database is required for this Markdown input.

Inspect and register your new JSON with the same preparation command. Review the
tutorial skills for your domain before starting; create a separate custom skill
through the UI if changes are needed. Never edit contributed originals to adapt
a study. Select the new research version explicitly: existing pipelines are not
silently switched. Re-register when the files or target semantics change.

## 5. Explicitly choose missing-source behavior

| Inputs supplied | Modes | Output |
|---|---|---|
| CSV and OKF | `dataset`, `okf` | Fitted models and source-grounded analysis |
| CSV only | `dataset`, `llm_only` | Fitted models, no external knowledge grounding |
| OKF only | `proposal`, `okf` | Research plan; no measured model performance |
| Neither | `proposal`, `llm_only` | Research plan based on unverified model knowledge |

Use `data_mode` and `knowledge_mode` in the JSON. A target description is required
for proposal mode and optional for dataset mode. The new-CSV form has no proposal-mode switch.
A missing file is an input error, not consent to change modes. See the
[detailed input walkthrough](examples/research-inputs/README.md#choose-the-input-mode).

## Repository-local research materials

Local deployments may keep supplied research data under
`resources/datasets/` and `resources/knowledge/`. These input directories are
currently ignored by Git and are not included in a clone or release artifact.
A separate tracked HeartFailure copy is included in `examples/heart-failure/`; use it for the portable demonstration. See [the resource layout](resources/README.md).

| Study | Local dataset | Local knowledge root |
|---|---|---|
| HIV | `resources/datasets/hiv/dataset.csv` | `resources/knowledge/hiv/` |
| Heart failure | `resources/datasets/heart-failure/dataset.csv` | `resources/knowledge/heart-failure/` |
| Alternate HIV suppression corpus | No implied dataset binding | `resources/knowledge/hiv-suppression/` |

`resources/manifests/sources.local.json` inventories these paths; it is not a completed research
contract. `resources/manifests/materials.local.json` records source-to-copy hashes. If a deployment
previously used a distinct analysis CSV, `resources/datasets/active/dataset.csv` preserves those exact
bytes instead of silently substituting the donor dataset. Existing saved research
versions and run snapshots retain their original provenance; register a new version
with the internal paths to use them for a new study.

Specialist skills default to `src/memstara/resources/contributed/specialists/` and ML
reference documents to `src/memstara/resources/contributed/machine-learning/`. No sibling skill
folder is automatically selected. Explicit environment overrides remain supported.
Changing `.env` affects newly started processes; an already running control service
or worker retains its loaded settings. Restart it between executions to adopt new
paths. Historical runs and checkpoints are not rewritten.

## HeartFailure installation acceptance

The clone includes the supplied CSV and complete OKF in `examples/heart-failure/`.
Docker startup prepares and registers the complete-case example automatically.
The following separate preparation is for the optional native tutorial:

```sh
python scripts/prepare_heart_failure_demo.py \
  --source examples/heart-failure/dataset.csv \
  --corpus examples/heart-failure/okf \
  --destination outputs/heart-failure-demo
python scripts/prepare_research_tutorial.py outputs/heart-failure-demo/research.json
```

The preparation selects eight fixed age, sex and history predictors and retains
complete cases on those predictors. It does not impute, alter the donor file or
select features using outcome associations. `preparation.json` records source and
derived hashes, exact features and retained/excluded row counts. Existing output
directories are rejected to preserve evidence. This restricted dataset is for
installation acceptance, not a clinically validated risk model. Complete-case
selection can bias the sample, and the supplied endpoint's prediction horizon and
ascertainment timing require review. Do not claim prospective performance.

In an independent checkout, configure its own `.env`. Adjacent Motoro files and
exported operational settings are not fallback sources. Docker startup provisions
database settings automatically; native execution requires explicit database/Redis
settings. Use separate instances/volumes and output/cache directories for acceptance.
Follow [README steps 2–3](README.md#2-configure-env) for Docker setup; native
`memstara.local_setup` commands use the ports from the selected project settings.
