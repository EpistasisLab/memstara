# Memstara workspace

The browser workspace configures pipelines and displays questions, agent activity,
model results, and explanations. It has three services with distinct responsibilities:

| Service | Local address | Responsibility |
|---|---|---|
| Web | <http://localhost:5173> | React development workspace |
| Observation API | <http://localhost:8071> | Reads Memstara and Motoro records |
| Host control | <http://127.0.0.1:8072> | Saves configurations and starts, pauses, resumes, or ends executions |

The browser sends `/api/` requests to the observation API and `/control/` requests
to the host control service. Only the observation database connections are
read-only; the workspace as a whole includes explicit execution controls.

For model profiles, control API usage, restart behavior and artifact auditing, see
the [developer guide](../DEVELOPER_GUIDE.md).

## Requirements

Complete the [pipeline setup](../README.md#get-started) first. The viewer needs
both databases, read-only database accounts, Docker Compose for container mode,
and the `memstara` Python environment for the host control service. Local frontend
development uses Node.js 22 and the committed `web/package-lock.json`.

The frontend uses Tailwind CSS 4 through its official PostCSS plugin. Its CSS
requires Safari 16.4+, Chrome/Edge 111+, or Firefox 128+; older browsers are not
supported. These are engine requirements, not a claim that every browser/version
has been tested. Automated browser fixtures currently run in Chromium.
See the [Tailwind migration guide](https://tailwindcss.com/docs/upgrade-guide).
CI runs `npm audit --audit-level=moderate` over runtime and build dependencies;
moderate or higher registry advisories block the frontend job. A passing audit
is time-specific and does not replace source/security review.
The existing theme remains in `web/tailwind.config.js`, explicitly loaded by
`web/src/index.css`; source scanning is restricted to application TS/TSX and HTML.

### Read-only database access

The observation API reads `MEMSTARA_VIEWER_DSN` and `CORE_VIEWER_DSN`. Its local
defaults use the `memstara_viewer` role, password `viewer`, and databases
`memstara` on port 5463 and `motoro` on port 5453. These are development defaults,
not automatically provisioned accounts. Docker uses `host.docker.internal`
instead of `localhost`; see [docker-compose.yml](docker-compose.yml).

For each database, connect as its administrator to create a dedicated login if
one does not already exist, then set its password interactively:

```sql
CREATE ROLE memstara_viewer LOGIN;
\password memstara_viewer
```

On separate PostgreSQL servers, repeat role creation for each server. If both
databases share one server, create the role once. In each target database, grant
connection access (use that database's name) and read access to the schema:

```sql
-- In the Memstara database:
GRANT CONNECT ON DATABASE memstara TO memstara_viewer;
-- In the Motoro database, use this instead:
-- GRANT CONNECT ON DATABASE motoro TO memstara_viewer;
GRANT USAGE ON SCHEMA public TO memstara_viewer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO memstara_viewer;
```

Run the following as each role that creates the application tables, so future
tables also become readable:

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO memstara_viewer;
```

Use a dedicated non-owner, non-superuser account without write-role memberships.
These grants do not revoke previously granted write access. Set the connection
strings to match the actual credentials and schema. For containers, the DSNs
are configured under the API service in the Compose file; exporting a host
variable alone does not override those literal Compose values. Keep credential
customizations local and never commit real credentials.

## Start the workspace

Follow [README step 7](../README.md#7-open-the-browser-workspace-optional-after-cli-acceptance)
to install dependencies and create read-only database roles first. In three
terminals with the root Python environment activated, run:

```bash
python -m memstara.local_setup control
python -m memstara.local_setup api
python -m memstara.local_setup web
```

Run one command per terminal. The project `.env` configures all three ports and
Vite's API/control proxy targets. The web process receives ports only; the API
receives read-only connection strings, not provider keys or database-owner
credentials. The legacy Docker viewer is an independently configured deployment,
not the project `.env` installation walkthrough.

Open the configured web port (default <http://localhost:5173>). Creating a design
does not execute it. A design can be saved without model connectivity, while Run
validates deployment configuration. All Combinations schedules skill combinations.
The services bind to loopback. There is no production authentication layer.

## Views

| View | Purpose |
|---|---|
| Question universe | Generated questions and their hypotheses, evidence, and results |
| Clinician view | Findings in clinical language with evidence and limitations |
| Floor plan | Agents, resources, and live activity across pipelines |
| Run log | Execution messages and troubleshooting |
| Final report | Saved explanations and research summaries |
| Board | Waiting, active, completed, or failed tasks |
| Task life | One task's progress through its stages |
| Telemetry | Agent calls, tool activity, usage, and database records |
| Access map | Tool access to stores |
| Results | Recorded model evaluations and interpretation |

Control exposes Floor plan, Question universe, Results, Clinician view, Final report,
and Telemetry. Results and Final report open in the main workspace; Floor plan has
no separate Results or Final report windows. Logs, Board, and task/access detail are additional workspace
panels rather than all being top-level navigation entries. Pipeline status is shown
within the workspace; the retained internal Status view is not a primary navigation tab.

The five visible roles are Hypothesis, Data, ML, Interpretation, and Explanation.
The Explanation role retains the internal `report` stage for compatibility.
Historical `curator` names are still recognized when reading older run records;
they do not imply a sixth active role.

## Development

Run the API from the repository root in a separate viewer environment:

```bash
python3 -m venv viewer/.venv
viewer/.venv/bin/python -m pip install -r viewer/requirements.txt
viewer/.venv/bin/python -m uvicorn main:app --app-dir viewer/api --port 8071 --reload
```

In another terminal, from the repository root:

```bash
cd viewer/web
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to 8071 and `/control` to 8072;
the host control service still needs to run separately. Verify a production build
with `npm run build` from `viewer/web`.

## Data and verification

The API maintains independent database pools. A failed source is reported as
unavailable rather than interpreted as zero activity. Run records may contain
JSON nulls, single tool calls, batched calls, and legacy server names.
[api/queries.py](api/queries.py) normalizes those shapes for aggregation.
The workspace uses snapshot data plus detail and control routes; a planned skill
is not proof that a corresponding agent call ran.

Tool grants originate in `memstara.pipeline.core`. The observation API includes
fallback definitions when the pipeline package is unavailable. With the pipeline
Python environment active, check the fallback definitions from the repository root:

```bash
python viewer/check_definitions.py
```

The live verification script requires running local containers and populated
records. It compares selected API values with database queries and attempts
writes that the read-only role must reject:

```bash
python viewer/verify.py
```

This is an operational check, not an offline test or a guarantee that every screen
is correct. Its permission checks require a correctly restricted account. The
script's container names and ports must match the deployment.

## Everyday commands

From the repository root:

```bash
docker compose -f viewer/docker-compose.yml logs -f api
docker compose -f viewer/docker-compose.yml up -d --build web
docker compose -f viewer/docker-compose.yml down
```

Stopping the viewer does not stop its databases or necessarily end a pipeline
process. Use the pipeline controls to manage execution before maintenance.
