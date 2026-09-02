# outputs — what the scripts produce

Everything here is **generated**. Do not edit it by hand — the next run overwrites it.

## How an OKF bundle is named

```
okf_<source>_<what it holds>
```

- **Starts with `okf_`** — say what the format is first
- **Source** — which knowledge source it came from (`alzkb`, `synthetic`)
- **What it holds** — always present, because **several bundles** come out of the same
  knowledge source. The same graph under a different hypothesis holds different things

Left as the single word `okf`, a second bundle makes it impossible to tell what the first
one was.

## The bundles that exist now

| Folder | Source | What is in it | What makes it |
|---|---|---|---|
| `okf_synthetic_sample/` | synthetic | 29 concepts — fake knowledge describing clinical measurement variables. `variables:` points at columns of `dataset.csv` | `make_sample_data.py` |

## The bundles that are planned

| Folder | Source | What will go in it |
|---|---|---|
| `okf_alzkb_druggable_non_ad_targets/` | AlzKB v2.0.0 | 1,162 genes — 76 AD genes (the anchors) plus 1,086 druggable non-AD counterparts. 1,781 relationships |


yet** — the conversion script is not written until the three decisions in that document's
last section are settled.

Built from the same graph under a different hypothesis, it sits alongside as something
like `okf_alzkb_shared_pathways/`.

## Swapping one bundle for another

The OKF server reads **one bundle at a time**. Which one is decided by an environment
variable.

```bash
export AGENTIC_OKF_BUNDLE_DIR="$PWD/outputs/okf_synthetic_sample"
```

Point the path at a different bundle and the pipeline sees a different knowledge source.
**No code has to change.**

## The rest of the files

| | |
|---|---|
| `dataset.csv` | the synthetic dataset (41 columns). `make_sample_data.py` makes it |
| `sub_*.csv` | the subsets the data stage cut during a trial |
| `summary.json` · `todo_rows.json` | the trial's aggregated results |
| `logs/` | run logs (console + JSONL) |
