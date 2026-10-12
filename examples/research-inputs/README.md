# User research inputs walkthrough

These files are newly generated, synthetic educational examples. They contain no
patient data or real research evidence. The example CSV and OKF documents are
dedicated to the public domain under CC0-1.0. No clinical claim is made.

From the repository root, after installing Memstara:

```sh
python -m memstara.research_inputs inspect examples/research-inputs/research.json
python -m memstara.research_inputs register examples/research-inputs/research.json
```

The second command returns an immutable record ID. No model calls are made.
Alternatively, open **Floor plan → Prepare research inputs**, enter the paths and
target description from `research.json`, inspect, and save. Paths refer to the
machine running the control service; relative paths use its working directory.
Absolute paths are recommended for user datasets.

In **Add pipeline**, choose the saved research version in the first step. Review
the `hypothesis_research` skill, Data, ML, Interpretation and Explanation settings.
Use one Loop initially. Creating a pipeline saves settings; Start executes it
and can incur model charges. All Combinations uses the same research selector.
Existing pipelines can switch versions in **Data & target** when not running.

A direct CLI execution, after configuring the normal model/database prerequisites,
uses the returned ID:

```sh
python -m memstara.pipeline.board --research-input-id RECORD_ID \
  --playbook-hypothesis hypothesis_research --trials 1 --waves 1
```

## Choose the input mode

`research.json` defaults to `knowledge_mode: "okf"` and `data_mode: "dataset"`.
Copy it to a new configuration file to select another mode; preserve the supplied
example and register each configuration as its own version.

| Available inputs | `knowledge_mode` | `data_mode` | Expected result |
|---|---|---|---|
| OKF and CSV | `okf` | `dataset` | Source-grounded hypotheses, fitted models and measured evaluation results |
| CSV only | `llm_only` | `dataset` | Hypotheses without external OKF grounding, fitted models and measured evaluation results |
| OKF only | `okf` | `proposal` | Source-grounded research proposal and future data/analysis plan |
| Neither | `llm_only` | `proposal` | Research proposal based on unverified model knowledge, with that limitation disclosed |

These are explicit modes: a missing file in a selected input is an error, not an
automatic switch to another mode. `llm_only` clears `knowledge_path`; `proposal`
clears `dataset_path` and `excluded_columns`. Unselected inputs are not inspected.
For dataset mode, provide the CSV target column, its description, positive/negative
labels and predictor timing. For proposal mode, `target.description` is required
as the research objective; a CSV column and observed label values are not required.

For example, this complete configuration needs no CSV or corpus:

```json
{
  "name": "Synthetic event research proposal",
  "knowledge_mode": "llm_only",
  "data_mode": "proposal",
  "target": {
    "description": "Plan a study of a generated toy event using predictors available at simulated baseline. This is not a clinical endpoint."
  }
}
```

Save it as `proposal.json`, then inspect and register it using the same CLI:

```sh
python -m memstara.research_inputs inspect proposal.json
python -m memstara.research_inputs register proposal.json
```

Use that new record ID with the execution command above. Inspection and
registration make no model calls; starting an execution still requires the normal
runtime/model setup and can incur charges even when no sources are supplied.

In proposal mode, Question and Hypothesis define the proposed study. Data specifies
what must be collected. ML proposes LR/XGBoost settings and evaluation methods but
does not train. Interpretation plans future SHAP/LIME analysis, and Explanation
summarizes conditional meaning, limitations and next steps. There are no measured
AUROC/F1 scores, confusion matrices, fitted models or computed SHAP/LIME values.
An OKF source can support a proposal, but it is not a substitute for observations.

## Source preservation and dataset requirements

For selected inputs, the pipeline revalidates source fingerprints, copies the selected corpus, removes
only explicitly excluded columns from an analysis copy, and maps the supplied
positive/negative labels to 1/0. Original files are never modified. Missing values
are rejected; no implicit imputation, row deletion or label inference occurs.
Evaluation preflight can reject inadequate class counts or unsupported data types.

Derived inputs and matcher artifacts live under the local, ignored
`outputs/research_inputs/prepared/<fingerprint>/`. The matcher builds embeddings
once per configuration before inference; first preparation can take longer than
subsequent runs and requires the configured embedding model. Each execution keeps
its research profile, source/artifact hashes and target semantics in `config.json`
under `outputs/runs/`. Question generation reads its own run-scoped question bank.

To revise a study, load its saved record, edit and save a new version, then select
that version in the pipeline. Changed sources cannot silently reuse an old
registration. Resume verifies and uses the original analysis copy and corpus,
even if the source files have subsequently changed. Do not edit generated copies.

Dataset mode supports one analysis-ready CSV and a binary target, at least
four eligible predictors and a 100 MiB CSV limit. OKF mode requires a bundle with
`index.md` and parseable Markdown documents. Target column names currently use letters,
digits and underscores, up to 64 characters. It is not an arbitrary-document
ingestion, automatic cleaning or multiclass workflow.

Legacy corpus-specific Hypothesis defaults and unbound Addiction/HIV specialist
Explanation skills are rejected for these generic profiles. Use the generic
defaults or a custom skill you have reviewed for the selected dataset and corpus.
Selecting different research inputs resets source filters and fixed baselines;
review the entire skill selection, especially a saved combination schedule.
