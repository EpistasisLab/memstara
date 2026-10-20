# Deployment configuration contract

Run `./start.sh` after configuring `.env` to start and check the complete app.
The script uses the supported full-stack entry point, root `compose.yml`. Native developer
commands remain available through `python -m memstara.local_setup`. The old
`viewer/docker-compose.yml` supports the native development viewer. Use root
`compose.yml` for the complete application.

## Ownership and precedence

| Category | Authoritative source | Consumers |
|---|---|---|
| Models, credentials and per-agent overrides | Project `.env` | Configuration validation, control, execution workers |
| Database and Redis identities | Generated private `.memstara/installation.json` (legacy explicit `.env` values retained) | Bootstrap, DB entrypoints, control; only read-only DSNs reach API |
| Public port and project identity | `.env` web port; generated private project identity and `compose.override.yaml` | Compose, control origin checks |
| Host directories | `.env` output/cache/input fields | Compose mounts and derived application paths |
| CSV/OKF/target and skills | App research/pipeline selections | Saved profiles and frozen executions |
| Execution cost estimates | Motoro pricing service | Memstara records returned estimates; missing prices stay unknown |
| Advanced rate overrides, meter mappings and specialist sources | Inline JSON in `.env` | Owning backend subsystem; no config directory |
| Per-research selections | Saved research/pipeline record | Execution preparation |
| Per-execution settings | Immutable redacted run snapshot | Execution, audit, historical resume |
| Release readiness metadata | `deployment/release-readiness.json` | Development/release checks only |

`operational.resolve()` validates project configuration. Normal native execution
never fills missing managed values from shell or sibling projects. Explicit
`environment` mode is reserved for validated subprocess/deployment settings.
`COMPOSE_PROJECT_NAME` is canonical; the old native `MEMSTARA_COMPOSE_PROJECT` is
accepted for compatibility, but conflicting assignments are rejected.

Docker bootstrap reads `.env` literally (not through `source`). Compose host binding
settings are compared with that file; a shell override cannot silently change them.
The DB host/port portions of local URLs are transformed to private `board`,
`runtime` and `redis` service addresses. External managed databases are not supported
by this local provisioning stack; native configurations may use other destinations.

The `user-inputs/...` path prefix resolves under `MEMSTARA_INPUTS_DIR` for native
execution and under `/app/user-inputs` in Docker. Output and cache paths similarly
map to stable container locations. CSV, OKF and skill file contents are never copied
into `.env`. The default bundled examples require no private files.

Generated installation files are not user configuration. `./start.sh` prepares them
with Docker before Compose runs. New installations receive unique project names and
random owner passwords; existing explicit identities and external-volume names are
retained. The files are ignored by Git and excluded from the Docker build context.
Back them up securely; do not copy them when creating an independent installation.
Read-only credentials continue to be provisioned in private settings volumes.
Ordinary users never need to enter owner/viewer DSNs or set `COMPOSE_FILE`.
Custom overrides require explicit migration review, and conflicting saved identities
are rejected before application services restart.

## Startup and credential boundaries

1. `configure` validates settings and writes separate, permission-restricted service
   files to named volumes. It makes no model calls.
2. The two PostgreSQL entrypoints source their generated, shell-quoted identity
   files. Database contents live in separate persistent volumes.
3. `initialize` runs supported migrations and schema creation, creates missing
   viewer roles and grants SELECT access. Existing credentials are not rotated.
   It probes owner connections, read-only permissions and Redis.
4. Control and API start after successful initialization; web waits for health.
   Control binds the private container interface; only the web port is published
   on host loopback. Host/Origin checks remain active.

The API receives only read-only DB credentials and artifact/cache locations. Web
receives neither database nor provider credentials. Project `.env`, local inputs,
outputs and Git history are excluded from application image build contexts. Docker
administrators can inspect containers and volumes; this is not a multi-tenant
secret-management boundary. Generated credential volumes must be protected like
`.env` and must not be published with support bundles.

## Maintenance and diagnostics

Use `docker compose logs --tail=80 configure initialize` for bootstrap failures.
No default command deletes data or resets credentials. After editing `.env`, stop
active work deliberately and use `docker compose up -d --build --force-recreate`
to refresh running consumers. Ordinary restarts with unchanged settings use
`docker compose up -d`. Back up databases and outputs before upgrades.

For an optional CLI input inspection after the stack is healthy:

```bash
docker compose run --rm --no-deps control python -m memstara.research_inputs inspect examples/research-inputs/research.json
```

This command uses the service entrypoint's validated settings. Do not assume that
`docker compose exec ... python` inherits settings loaded dynamically by another
process; use the configured `run` entrypoint for standalone commands.

The image uses the locked Motoro commit and runtime dependencies. CPU PyTorch is
selected by the existing uv Linux source policy; downstream XGBoost dependencies
may still increase image download size. Neither container startup nor application
health authorizes or proves a successful model call. Real LLM acceptance is a
separate, explicitly recorded validation step.

## Validation scope

Unit tests cover URL transformation, percent-encoded credentials, native/container
path equivalence, conflicting project names, invalid input rejection and credential
separation. Integration acceptance uses a separate Compose project, dummy provider
credentials and synthetic data: bootstrap, read-only access, browser/API/control,
input registration, pipeline persistence and repeated startup. Never use a private
research DB for destructive test setup, and do not infer real model-call success
from these checks.

## Optional inline settings

Legacy `MEMSTARA_PRICING_JSON` and `MEMSTARA_PRICING_PATH` do not override
execution costs. Motoro exclusively calculates request estimates.

**Settings and more → How cost estimates work** explains this policy. Local manual
rate editing is retired; its POST endpoint returns HTTP 410. Historical receipts
and offline catalog tools remain available, but do not price new requests.

The following settings are for offline audits and advanced source bindings only.
No `config/` folder is required. Keep optional JSON on one single-quoted line in
`.env`. These are advanced settings; leave them unset for the standard workflow.
The following examples are schemas, not verified prices or working database bindings.
Never replace a missing price with zero. Inline rates and a catalog path are mutually
exclusive, as are inline source bindings and the legacy source-file path.

```dotenv
# Example structure only: replace every placeholder with verified values.
# MEMSTARA_PRICING_JSON='{"profiles":[{"provider":"openai","model":"deployment-name","api_base":"https://endpoint.example/v1","billing":"tokens","currency":"USD","source":"verified-rate-source","retrieved_at":"ISO-8601-timestamp","valid_from":"ISO-8601-timestamp","valid_until":"ISO-8601-timestamp","usd_per_million_tokens":{"input":1,"output":1,"cache_read":1}}]}'
# MEMSTARA_AZURE_PRICING_METERS_JSON='{"profiles":[{"provider":"openai","model":"deployment-name","api_base":"https://endpoint.example/v1","region":"region-name","meters":{"input":"verified-meter-uuid","output":"verified-meter-uuid"}}]}'
# MEMSTARA_EXPLANATION_SOURCES_JSON='{"hiv":{"expert":"hiv","database_id":"authorized-knowledge","kind":"postgres","dsn_env":"MEMSTARA_HIV_KNOWLEDGE_DSN","table":"documents","id_column":"id","text_column":"text","scope_column":"domain","scope_value":"hiv"}}'
# MEMSTARA_HIV_KNOWLEDGE_DSN=postgresql://reader:password@authorized-host/database
```

Specialist bindings must contain each selected expert (`hiv` and/or `addiction`).
Use a separate authorized read-only database identity. Refer to a DSN variable name
instead of embedding credentials in binding JSON. CSV, OKF documents and database
contents remain research inputs; they are not encoded into `.env`.

For retail-rate refresh, leave inline rates unset, set the meter mapping above and
`MEMSTARA_PRICING_PATH=outputs/pricing/catalog.json`, then run
`python -m memstara.azure_costs refresh`. The catalog is generated output, not a
second manual settings source. Create it before bootstrapping a service configured
to read it. This optional command queries public retail rates, not actual Azure
billing, and does not make an inference request.

Model assignments are configured directly in `.env`. Release
review metadata in `deployment/release-readiness.json` does not configure the app.

Docker automatically generates missing viewer credentials and retains them in its
restricted control-settings volume. Restarting reuses the credentials; it never
rotates an existing database role silently. Explicit `.env` DSNs override this
derivation. Preserve the settings volumes together with the databases. A changed
owner identity with persisted viewer settings requires explicit credentials.

### Docker builder connection failures

The launcher builds one service at a time before recreating application services.
Recognized BuildKit transport failures (`failed to dial gRPC`, h2c upgrade errors,
or an unavailable RPC connection) retry up to three times per image, with short
backoff. Build output is printed after each attempt. Compilation, dependency and
configuration failures stop immediately. Persistent transport failures also stop;
inspect Docker Desktop diagnostics before trying again. The launcher never restarts
Docker Desktop or deletes caches, inputs, experiment results or database volumes.
