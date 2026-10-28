# Included HeartFailure example

This directory is tracked by Git. Clone the branch containing this directory to
receive both the supplied CSV and the complete OKF; no external shared folder is
required. `dataset.csv` and all files under `okf/` preserve the supplied bytes.
`manifest.json` lists SHA-256 hashes; it contains no private source paths.

## Inputs and provenance

- CSV: the supplied `mi_HeartFailure.csv`, stored here as `dataset.csv` (1,700 rows,
  113 columns). This is the supplied processed cohort, not the invented synthetic
  example and not a separately downloaded replacement dataset.
- OKF: the supplied HeartFailure bundle; its index describes 100 PubMed/PMC papers
  across eight topics, built by okf-loremaster/0.4.1. Preserve document citations,
  metadata, the catalogue, indexes and supporting files together.
- Copies originate from the repository-local supplied HeartFailure material.
  Original inputs are retained locally; their content has not been rewritten.
- Inclusion is requested for repository installation. This is not a new license
  grant for the source dataset or cited publications. Dataset provenance/licensing
  and applicable source-material redistribution terms still need a public-release
  review. Do not apply the synthetic example's CC0 declaration to this directory.

## Target and analysis preparation

Target: `chronic_heart_failure`; positive `1`, negative `0`.
The clinical outcome window and predictor timing have not been independently
validated. This is a software demonstration, not validated prospective prediction.

For the Docker installation, `./start.sh` automatically prepares and registers the
complete-case demonstration. Open **Experiments → Add experiment → Use saved data**
and select **Heart failure complete-case software demonstration**. No manual
preparation commands are needed. Model credentials may be supplied later through
**AI model → Set up a model**; startup and data registration do not call the LLM.

For optional native development, from the repository root after configuring the
runtime described in [the developer guide](../../DEVELOPER_GUIDE.md):

```bash
python scripts/prepare_heart_failure_demo.py \
  --source examples/heart-failure/dataset.csv \
  --corpus examples/heart-failure/okf \
  --destination outputs/heart-failure-demo
python -m memstara.research_inputs inspect outputs/heart-failure-demo/research.json
python scripts/prepare_research_tutorial.py outputs/heart-failure-demo/research.json > outputs/launch.json
```

The preparation script uses eight fixed predictors: `age_years`, `sex`,
`previous_myocardial_infarctions_count`, `essential_hypertension_stage`,
`diabetes_mellitus_history`, `obesity_history`, `chronic_bronchitis_history`,
`bronchial_asthma_history`. Complete-case selection retains 1,671 rows and excludes
29; no imputation is performed. Selection can bias the demonstration population.

This is the bundled demo's explicit preparation policy. It is separate from
**Upload a new CSV → Fill missing values for me**, which preserves rows and fits
mean/mode imputation inside ML training after the split. Uploading the original
1,700-row CSV does not automatically select these eight predictors or apply the
demo's complete-case filtering. See [the CSV input guide](../research-inputs/README.md)
for upload validation and imputation limits.

It writes the derived `dataset.csv`, executable input contract `research.json`,
and provenance record `preparation.json` under the destination. The contract uses
absolute paths resolved on the installing machine. An existing destination is
rejected to preserve previous evidence; choose a new path for another preparation.

Docker startup uses `outputs/bundled-research/heart-failure-v1-<source-hash>/`
and reuses unchanged prepared data and registrations on subsequent starts.
Its `research.json` uses a relative `dataset.csv` path, resolved against the
manifest directory by the startup registrar. The optional native preparation
command above writes absolute paths instead. These local outputs persist across
container recreation; reinstalling containers alone does not clear them.

See [the root README](../../README.md#configure-and-run-a-pipeline) for starting a pipeline in
the browser. Preparation alone does not make model calls or establish
pipeline completion. The generated contract is not committed because its paths
belong to the user's installation. Keep private credentials out of this directory.
