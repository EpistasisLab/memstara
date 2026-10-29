# Memstara

A research workspace for generating hypotheses, training predictive models and exploring recorded results.

**First release: [v0.1.0](https://github.com/HyunjunA/memstara/releases/tag/v0.1.0).**
See [release notes](CHANGELOG.md) for the included features.

## Get started

**Requirements:** Git and a running Docker Desktop (or Docker Engine with Compose v2).
Download Git from [git-scm.com](https://git-scm.com/downloads) and Docker from
[docker.com](https://www.docker.com/products/docker-desktop/).
Azure Foundry credentials are needed when configuring a model to run an experiment.
Docker installs the application and its dependencies, including **Motoro 0.13.0**;
no separate Python, Node or database setup is needed.

### 1. Download

```bash
git clone --branch v0.1.0 --depth 1 https://github.com/HyunjunA/memstara.git
cd memstara
cp .env.example .env
```

The included HeartFailure demonstration pairs a dataset from the UCI Machine
Learning Repository with an associated OKF corpus created from 100 recent
research papers in PubMed/PMC. **Do not move or download these files separately:**

| Input | Location |
|---|---|
| CSV | `examples/heart-failure/dataset.csv` |
| OKF corpus | `examples/heart-failure/okf/` |

Startup prepares and registers the demonstration automatically, including the
`chronic_heart_failure` target (positive `1`, negative `0`). It uses a derived
complete-case dataset and preserves the supplied files. 

### 2. Configure a model

Choose one of two options:

1. **Use the GUI (recommended).** Leave the API key, deployment name and endpoint
   blank in `.env`. After starting Memstara, open **Add experiment → AI model →
   Set up a model**, enter those details and select **Check & use model**.
2. **Edit `.env`.** Set server-wide Azure Foundry defaults before starting Memstara:

```dotenv
MEMSTARA_AZURE_FOUNDRY_API_KEY=YOUR_API_KEY
MEMSTARA_LLM_PROVIDER=azure_foundry
MEMSTARA_LLM_MODEL=YOUR_DEPLOYMENT_NAME
MEMSTARA_LLM_API_BASE=https://YOUR_RESOURCE.services.ai.azure.com
```

Only **Azure Foundry** is currently supported. Restart after editing `.env`, leave
agent overrides blank to inherit these defaults and keep `.env` private. A GUI
connection check makes a small request that your provider may charge for.

### 3. Start

```bash
./start.sh
```

Open **http://127.0.0.1:5173/**, or the URL printed by the script if you changed
`MEMSTARA_WEB_PORT` in `.env`. The first build may take several minutes.
After the ready message, you can close the terminal.

## Configure and run a pipeline

| Configure in | Settings |
|---|---|
| `.env` | LLM provider, credentials, common model, optional per-agent model overrides and web port |
| **Add experiment → AI model** | Use server defaults or check an Azure Foundry model connection for all agents in this experiment |
| **Add experiment → Upload a new CSV** | Your CSV, binary prediction target, missing-value consent and knowledge source; label mapping is automatic |
| **Add experiment → Use saved data** | Included Heart Failure demonstration or previously registered data |
| **Add experiment → Choose skills → Review & create** | Agent skills, data split settings, replicates, execution order and experiment name |

For the included example:

1. Open **Experiments → Add experiment**. Review the **AI model** settings, or set up and check an Azure Foundry connection if needed.
2. In **Research inputs → Use saved data**, select **Heart failure complete-case software demonstration** and review its target.
3. In **Agent skills**, each stage starts with one compatible skill selected. Keep these defaults and select **Next**, or change the selections. The HeartFailure example defaults to hypotheses across all knowledge categories, Training-heavy data, Logistic Regression, SHAP Interpretation and cardiovascular Explanation. Clearing all hypothesis selections uses the compatible default shown in review. If you deselect all ML skills, the server runs scikit-learn default Logistic Regression without LLM parameter tuning.
4. In **Review & create**, set a name and **1 replicate per pipeline** for a first experiment, review the execution order and confirm it. Execution starts at Pipeline 1.
5. Select **Create pipeline**, then **Run** on that pipeline's card. Creating a pipeline does not start it.

Review skill selections in the creation wizard. Pipeline cards have
execution controls and a delete button; there is no post-creation **Settings** or
**Details** menu. To change a saved combination design, create a new pipeline.
Running or interrupted pipelines show the applicable Pause/Resume controls.

Starting the app does not start an experiment. Selecting Run makes model requests
and may incur charges. Successful startup does not verify model credentials or
complete a research run. The bundled study is a software demonstration, not a
validated clinical prediction tool.

## Read activity and results

- **Experiments:** create and run pipelines, follow agents and open the live log.
- **Results:** open a Pipeline/Replicate tile to read its saved Interpretation agent output. The text is rendered from the recorded output without rewriting it; tile metadata includes recorded target, predictors, model and Test AUROC when available.
- **Conclusions:** open a Pipeline/Replicate tile to read its saved Explanation agent output and download Markdown.
- **Usage:** open a Pipeline/Replicate tile for recorded usage and Motoro-provided cost estimates. These are estimates, not actual billed charges; unavailable prices remain unknown.

These views show completed outputs/replicates. A **New** badge marks unread
output in Results, Conclusions and Usage.

These four views appear in this order in Control. A selected execution that completes
while you watch Experiments opens Results automatically (Conclusions for proposal-only
runs). Opening saved history does not redirect you. Output navigation identifies
the pipeline and replicate; your experiment names and saved records are retained.

Results and reports appear as they are recorded. An empty view before an execution
has produced output is expected. Both open in the main workspace; choose **Experiments**
in Control to return to execution monitoring. The header's **Estimated total** stays
visible across views; click it for the latest-execution cost breakdown by pipeline.

## Stop, restart or troubleshoot

```bash
docker compose stop
./start.sh
docker compose logs --tail=80 configure initialize control api web
```

These commands stop the app, restart/apply settings, and inspect logs respectively.
Finish active experiments before rerunning `./start.sh`; it restarts services.
Saved records are retained. Use an unused web port for a second installation.

## Input and setup help

- [Your own CSV, OKF and target](examples/research-inputs/README.md)
- [Environment settings and examples](.env.example)
- [HeartFailure data and preparation](examples/heart-failure/README.md)

To verify one real Haiku 5.5 pipeline in a running Docker installation, run
`./test-live.sh`. This makes paid model calls using the generated application settings,
connects to databases inside Docker, and retains evidence in `outputs/verification/`.
It does not restart existing experiments or require publishing database ports.
App startup and offline tests alone do not verify a real pipeline execution.
