# Memstara

A research workspace for generating hypotheses, training predictive models and exploring recorded results.

**First MVP release: [v0.1.0](https://github.com/HyunjunA/memstara/releases/tag/v0.1.0).**
See [release notes](CHANGELOG.md) for the included features.

## Get started

**Requirements:** Git, a running Docker Desktop (or Docker Engine with Compose v2),
and credentials for an Azure Foundry deployment. Docker installs the application
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
2. Provider is fixed to **Azure Foundry**. Select the model type and enter your
   **Deployment name**, **Endpoint URL** and **API key**. If available, you can
   reuse the configured server credentials.
3. Select **Check & use model** to verify and save the connection. This makes a
   small test request that your provider may charge for.

The checked GUI configuration applies to **all agents in that experiment**.
It does not overwrite `.env` or require a server restart. To use the server's
per-agent defaults instead, select **Use current model**. Installation settings,
such as the web port, remain in `.env`.

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
| **Add pipeline → Register or revise research inputs** | Your CSV, OKF corpus, prediction target and label mapping |
| **Add pipeline** | Research input, agent skills, replicates per pipeline and experiment name |

For the included example:

1. Open **Experiments → Add pipeline**.
2. In **Research inputs**, select **Heart failure complete-case software demonstration** and review its target.
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
- **Results:** read the recorded interpretation; expand **Model performance and technical details** for AUC, charts and settings. **Compare recorded analyses** opens the comparison tools. A **New** badge marks unread results.
- **Conclusions:** select a pipeline, read its saved Explanation agent output and download Markdown.
- **Usage:** inspect execution usage and Motoro-provided cost estimates. These are estimates, not actual billed charges; unavailable prices remain unknown.

These four views appear in this order in Control. A selected execution that completes
while you watch Experiments opens Results automatically (Conclusions for proposal-only
runs). Opening saved history does not redirect you. Descriptive headings quote saved
AI hypotheses; your pipeline names and records are retained.

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

### Pipelines and replicates

A **Pipeline** is one combination of agent skills. A **Replicate** repeats that Pipeline’s complete research process, from question generation to Explanation. Selecting several skills creates an experiment containing multiple Pipelines. A Replicate repeats the configuration, not necessarily the same question or hypothesis; the actual generated content, data splits and model settings are recorded for each attempt.

For example, **48 pipelines × 10 replicates per pipeline = 480 total replicates**. The default is **1 replicate per pipeline**. With **All pipelines first**, all Pipelines complete their first scheduled replicate before the next cycle. **One pipeline all replicates first** finishes one Pipeline's replicates before proceeding to the next. Resuming preserves the recorded schedule.

### Release versions

Development continues on `mvp`; install a published `vX.Y.Z` tag for a repeatable
release. Released tags are immutable. During the MVP phase, use patch releases
for compatible fixes and minor releases for new features; describe any breaking
changes explicitly. Version `1.0.0` will mark a stable compatibility contract.
Python packages derive their version from Git. `deployment/VERSION` records the
same release number for Docker builds, which do not include Git metadata.

Progress identifies both units, for example **Pipeline 3 / 48 · Replicate 2 / 10**. Failed or skipped attempts remain recorded separately from completed work. Historical **Split evaluations** repeat model evaluation inside a Replicate; they do not multiply the number of Pipeline replicates. New designs use one split evaluation and do not expose advanced ML controls. Existing capped schedules retain their recorded counts. Raw agent outputs and technical execution IDs are preserved as saved.
