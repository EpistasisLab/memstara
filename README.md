# Memstara

A research workspace for generating hypotheses, training predictive models and exploring recorded results.

## Get started

**Requirements:** Git, a running Docker Desktop (or Docker Engine with Compose v2),
and credentials for a supported LLM deployment. Docker installs the application
and its dependencies, including **Motoro 0.10.0**; no separate Python, Node or database setup is needed.

### 1. Download

```bash
git clone --branch feature/question-universe-ui https://github.com/HyunjunA/memstara.git
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

Enter your provider API key and one common model for all agents. For Azure Foundry:

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
When overriding `PROVIDER` with a different service, also set that agent's `MODEL`,
its `API_BASE` if required (Azure Foundry/local), and the matching provider API key.
Common endpoints and generation settings are not inherited across providers.
The template lists provider-specific requirements. Local servers accept HTTP/HTTPS
and an optional `MEMSTARA_LOCAL_API_KEY`. Bedrock requires `AWS_REGION` and either
`AWS_BEARER_TOKEN_BEDROCK` or AWS access credentials (plus a session token for temporary
credentials). Docker receives these from `.env`; host AWS profiles are not mounted.
Restart after editing `.env`; saved executions retain their recorded model profiles.
Keep the remaining defaults for a first installation.
Database credentials are generated automatically. Keep `.env` private; do not
replace an existing installation's `.env` with another checkout's settings.

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
| **Prepare research inputs** | Your CSV, OKF corpus, prediction target and label mapping |
| **Add pipeline → All Combinations** | Research input, agent skills, ML evaluation options, Loop limit and pipeline name |

For the included example:

1. Open **Experiments → Add pipeline → All Combinations**.
2. In **Research inputs**, select **Heart failure complete-case software demonstration** and review its target.
3. In **Agent skills**, choose one skill for each stage. Set optional ML evaluation/advanced model settings in the Machine learning step.
4. In **Review & create**, set a name and a maximum of **1 Loop** for a first run, review the plan and confirm it. **Random Start** is off by default: execution starts at combination 1 and continues in order.
5. Select **Create pipeline**, then **Run** on that pipeline's card. Creating a pipeline does not start it.

Complete skill and evaluation settings in the creation wizard. Pipeline cards have
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

For developer verification including mandatory paid model calls, run
`uv run --frozen --extra dev --extra runtime python -m scripts.verify_pipeline`.
App startup and offline tests alone do not verify a real pipeline execution.
