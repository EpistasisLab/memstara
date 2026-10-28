# User research inputs walkthrough

These files are newly generated, synthetic educational examples. They contain no
patient data or real research evidence. The example CSV and OKF documents are
dedicated to the public domain under CC0-1.0. No clinical claim is made.

## Upload your own CSV in the browser

Start the app using [the installation steps](../../README.md#get-started).
You can leave LLM credentials blank at startup and configure an Azure Foundry
connection in **Add experiment → AI model → Set up a model** before continuing.

1. Open **Experiments → Add experiment → Upload a new CSV**.
2. Upload one UTF-8 CSV, at most **5 MiB**. Upload checks the file; it does not
   fill missing values or start model training.
3. If missing values are found, choose **I’ll fix the CSV** and upload a corrected
   copy, or consent with **Fill missing values for me**. With the first option,
   the outcome and knowledge-source steps stay hidden until a corrected upload.
4. Under **What do you want to predict?**, choose a column with exactly two
   distinct non-missing values. The UI assigns the two labels automatically;
   there is no positive/negative-class input. Study name comes from the filename,
   and an omitted outcome description is generated from the target and mapping.
   Predictor timing and prediction horizon are not required or inferred.
5. Choose **Heart Failure example**, **My research folder**, or **LLM only**.
   For your own OKF, enter the full folder path containing `index.md`.
6. Select **Check & use this data**. Successful validation saves and selects the
   data and asks you to choose **Choose skills**. Otherwise, it lists the issues
   to correct. Passing input checks does not verify model connectivity or train a model.

The automatic binary mapping uses sorted CSV label strings: the first becomes
negative/0 and the second positive/1. This is an encoding rule, not an inference
of clinical meaning. For `0` and `1`, the mapping is unchanged. For `event` and
`no_event`, it makes `no_event` positive. If a specific positive class matters,
register a JSON configuration with explicit labels as shown below, or prepare a
separate CSV with your intended outcome encoded as 1 and the other as 0.

Remove identifier and unsuitable predictor columns from an upload copy before
uploading. The current upload form has no column-exclusion editor. JSON
registration supports `excluded_columns` without changing the original CSV.

### Folder paths in Docker and native installations

The path must be accessible to the **control service**, not just your browser.

| Research folder | Docker path to enter |
|---|---|
| Included Heart Failure library | Select **Heart Failure example**, or use `/app/examples/heart-failure/okf` |
| Included synthetic library | `/app/examples/research-inputs/okf` |
| `user-inputs/my-study/okf` in the checkout | `/app/user-inputs/my-study/okf` |

`MEMSTARA_INPUTS_DIR` chooses the host folder mounted read-only at
`/app/user-inputs`. A folder on your computer is not automatically available inside Docker. For a native control service, use its accessible absolute
filesystem path. **LLM only** needs no OKF folder.

## Register the supplied synthetic example

The supplied `dataset.csv` contains `record_id`. Its JSON configuration excludes
that column and explicitly makes `event` positive and `no_event` negative.
Uploading this CSV unchanged through the current form fails identifier validation;
use JSON registration to preserve the example's intended settings.

For a running Docker installation, from the checkout root:

```sh
docker compose exec -T -w /app control python -m memstara.research_inputs register examples/research-inputs/research.json
```

Then open **Add experiment → Use saved data** and select
**Synthetic baseline prediction tutorial**. A registration made in an unrelated
native installation will not appear in Docker's registry.

For native development, with the project's Python environment installed and
activated, run from the repository root:

```sh
python -m memstara.research_inputs inspect examples/research-inputs/research.json
python -m memstara.research_inputs register examples/research-inputs/research.json
```

The second command returns an immutable record ID. Neither command makes model
calls. CLI paths in this example are relative to the working directory.

For the optional native tutorial, register the example with a tutorial Hypothesis
skill and a supplied Explanation skill:

```sh
python scripts/prepare_research_tutorial.py examples/research-inputs/research.json
```

This prints an input record ID, the selected Hypothesis/Explanation IDs and a
one-replicate execution command. It registers one custom Hypothesis skill and
uses a supplied Explanation skill; it does not register custom Interpretation or
Explanation instructions. The existing `skills/explanation.md` example is retained
as reference material and is not used by this command.

In **Add experiment**, select that research version and the printed skills, with
training-heavy Data, LR ML and SHAP Interpretation. All four supplied Explanation
skills are selectable. Review their suitability for your question; selection does
not make a synthetic example clinically valid. Preparation does not start a run
or check provider/database availability. The original skill files are unchanged.

The printed command makes real model calls only when you execute it. Configure the
runtime first. This is a software demonstration, not evidence of clinical validity
or a successful live execution of the current revision. See the
[release gates](../../RELEASE_CHECKLIST.md) for outstanding acceptance.

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
For JSON registration in dataset mode, provide the CSV target column and explicit
positive/negative labels. Description, predictor timing and horizon are optional;
an omitted description is generated, but timing and horizon remain unspecified.
The browser supplies the label mapping automatically as described above. For
proposal mode, `target.description` is required as the research objective; a CSV
column and observed label values are not required. The new-CSV form does not
offer a switch to proposal mode; register that mode using JSON.

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
positive/negative labels to 1/0. Original files are never modified. Upload,
registration and preparation do not fill missing cells or delete rows.

`missing_policy: "reject"` blocks missing predictors. With explicit
`missing_policy: "impute_train_v1"` consent, the ML pipeline fills predictor gaps
after splitting: continuous measurements/counts use the training mean; categorical
and binary predictors use the training mode. If training CV is used, each fold
fits its own replacement values. Test/validation rows do not determine them.
Missing target values, entirely empty predictors and non-finite values still block
validation; consent does not repair them.

The upload UI detects types automatically. Text and binary columns are treated as
categories, with name/range rules for fields such as `age_years`, `_count` and
`_stage`. Other numeric columns default to continuous. Numeric category codes
cannot always be identified correctly from the CSV alone. JSON users can supply
`predictor_types`, for example `{"age_years": "continuous", "region_code": "categorical"}`.
This typed path supports training-fitted categorical encoding. Without
`predictor_types`, the legacy JSON path rejects nonnumeric predictors; use explicit
types or prepare an appropriate analysis copy. The upload UI has no manual type editor.
CSV inspection rejects malformed quoting and fields exceeding the Python CSV parser's
field-size limit. Fix the source explicitly and register a new version; inspection
does not repair quoting or truncate cells. Evaluation preflight can reject inadequate
class counts or unsupported data types.

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

Dataset mode supports one CSV and a binary target, with at least four eligible
predictors. **Browser uploads are limited to 5 MiB; local-file inspection/JSON
registration supports up to 100 MiB.** Both target classes need observations;
execution may impose stricter counts for the selected split/CV. OKF mode requires
`index.md` and parseable Markdown documents. Target names must start with a letter
or underscore, then use letters, digits or underscores, up to 64 characters.
Multiclass targets, arbitrary-document ingestion and automatic row cleaning are
not supported by this workflow.

Choose a compatible Hypothesis skill for the selected corpus. Interpretation uses
supplied SHAP/LIME instructions, and Explanation uses one of the four supplied
specialist instructions. Custom Interpretation/Explanation registration is disabled.
Selecting different research inputs resets source filters and fixed baselines;
review the entire skill selection, especially a saved combination schedule.
