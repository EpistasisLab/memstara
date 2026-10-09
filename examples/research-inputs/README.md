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

The pipeline revalidates source fingerprints, copies the selected corpus, removes
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

The initial contract supports one analysis-ready CSV and a binary target, at least
four eligible predictors, a 100 MiB CSV limit, and an OKF bundle with `index.md`
and parseable Markdown documents. Target column names currently use letters,
digits and underscores, up to 64 characters. It is not an arbitrary-document
ingestion, automatic cleaning or multiclass workflow.

Legacy corpus-specific Hypothesis defaults and unbound Addiction/HIV specialist
Explanation skills are rejected for these generic profiles. Use the generic
defaults or a custom skill you have reviewed for the selected dataset and corpus.
Selecting different research inputs resets source filters and fixed baselines;
review the entire skill selection, especially a saved combination schedule.
