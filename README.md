# Memstara

A research workspace for generating hypotheses, training predictive models and exploring recorded results.

**First MVP release: [v0.1.0](https://github.com/HyunjunA/memstara/releases/tag/v0.1.0).**
See [release notes](CHANGELOG.md) for the included features.

## Get started

**Requirements:** Git and a running Docker Desktop (or Docker Engine with Compose v2).
Azure Foundry credentials are needed when configuring a model to run an experiment.
Docker installs the application
and its dependencies, including **Motoro 0.13.0**; no separate Python, Node or database setup is needed.

### 1. Download

```bash
git clone --branch v0.1.0 --depth 1 https://github.com/HyunjunA/memstara.git
cd memstara
cp .env.example .env
```

The HeartFailure demonstration is already included. **Do not move or download these files separately:**

| Input | Location |
|---|---|
| CSV | `examples/heart-failure/dataset.csv` |
| OKF corpus | `examples/heart-failure/okf/` |

Startup prepares and registers the demonstration automatically, including the
`chronic_heart_failure` target (positive `1`, negative `0`). It uses a derived
complete-case dataset and preserves the supplied files. Private HIV data is not included.

### 2. Configure `.env`

**You can configure the LLM model in the GUI as well as in `.env`.**
Use `.env` for installation settings and server-wide model defaults. After starting
Memstara, use **Add experiment → AI model → Set up a model** to configure the model
for an individual experiment.

You may leave the API key, deployment name and endpoint blank in `.env` and start
the app. Then configure and check the connection in **Add experiment → AI model**.
An experiment cannot run until its model configuration is complete.

To set server defaults in `.env`, enter your Azure Foundry API key, deployment
name and endpoint:

```dotenv
MEMSTARA_AZURE_FOUNDRY_API_KEY=YOUR_API_KEY
MEMSTARA_LLM_PROVIDER=azure_foundry
MEMSTARA_LLM_MODEL=YOUR_DEPLOYMENT_NAME
MEMSTARA_LLM_API_BASE=https://YOUR_RESOURCE.services.ai.azure.com
```

Leave agent overrides blank to inherit these defaults. To use a different model
for Explanation on the same service, set `MEMSTARA_EXPLANATION_MODEL`.
Overrides are available for `QUESTION`, `HYPOTHESIS`, `DATA`, `ML`,
`INTERPRETATION` and `EXPLANATION`, including generation settings.
This MVP supports **Azure Foundry only** in experiment model setup. Keep every
agent's provider set to `azure_foundry`; other providers are rejected for new web executions.
Restart after editing `.env`; saved executions retain their recorded model profiles.
Keep the remaining defaults for a first installation.
Database credentials are generated automatically. Keep `.env` private; do not
replace an existing installation's `.env` with another checkout's settings.

**Configure a model in the GUI:**

1. Open **Add experiment → AI model → Set up a model**.
2. Provider is fixed to **Azure Foundry**. Select the **Base model** and enter your
   **Azure deployment name**, **Endpoint URL** and **API key**. If available, you can
   reuse the configured server credentials.
3. Select **Check & use model** to verify and save the connection. This makes a
   small test request that your provider may charge for.

After **Check & use model** succeeds, **Use current model** is selected automatically.
That checked connection becomes the default for new experiments in this installation,
including after reopening the wizard, refreshing the page or restarting containers
with the same saved outputs. It applies to **all agents in each new experiment**.
Reusing it does not make another connection-check request.

Before a GUI connection is saved, **Use current model** uses the server's per-agent
`.env` defaults. Once saved, the GUI connection takes priority; **Set up a model**
lets you check a replacement. Failed checks leave the previous default intact.
This does not overwrite `.env`, require a restart or change existing experiments.
Installation settings, such as the web port, remain in `.env`.

### 3. Start

```bash
./start.sh
```

Open **http://127.0.0.1:5173/**, or the URL printed by the script if you changed
`MEMSTARA_WEB_PORT` in `.env`. If that port is occupied by another app, the script
chooses an available port and saves it in `.env`; use the printed URL.
The first build may take several minutes.
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

Random-feature hypothesis generation and Random Start are unavailable for new MVP designs. Existing experiment records remain available.

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
