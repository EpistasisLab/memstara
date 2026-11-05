FROM postgres:16-bookworm AS history-postgres-clients

FROM python:3.12-slim AS configure
WORKDIR /app
RUN pip install --no-cache-dir python-dotenv==1.2.1
COPY src/memstara/__init__.py src/memstara/paths.py src/memstara/operational.py src/memstara/installation.py src/memstara/stage_models.py src/memstara/container_config.py /app/src/memstara/
COPY examples/ /app/examples/
COPY src/memstara/resources/ /app/src/memstara/resources/
COPY deployment/ /app/deployment/
ENV PYTHONPATH=/app/src
CMD ["python", "/app/deployment/configure.py"]

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.8.22
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra runtime --no-dev --no-install-project
# Process identity checks are required when saving/recovering pipeline ownership.
# The UI history-backup worker uses libpq clients directly, without a Docker socket.
RUN apt-get update && apt-get install -y --no-install-recommends procps postgresql-client && rm -rf /var/lib/apt/lists/*
# Match this stack's PostgreSQL 16 servers; the distro package supplies libraries.
COPY --from=history-postgres-clients /usr/lib/postgresql/16/bin/pg_dump /usr/lib/postgresql/16/bin/pg_restore /usr/local/bin/
RUN python -c "import subprocess; assert all(subprocess.check_output([name, '--version'], text=True).split()[2].startswith('16.') for name in ('pg_dump', 'pg_restore'))"
COPY README.md THIRD_PARTY_NOTICES.md ./
COPY licenses/ licenses/
COPY src/ src/
COPY examples/ examples/
COPY deployment/ deployment/
# Git metadata is excluded from the Docker context. Keep the release version
# with the source so direct Compose builds and downloaded archives agree.
RUN SETUPTOOLS_SCM_PRETEND_VERSION="$(cat deployment/VERSION)" uv sync --frozen --extra runtime --no-dev
RUN .venv/bin/python -c "from importlib.metadata import version; from pathlib import Path; import memstara; assert version('motoro') == '0.15.0'; assert version('memstara') == memstara.__version__ == Path('deployment/VERSION').read_text().strip()"
# Fail local image builds as well as CI on undefined/shadowed names and broken
# HTTP query handlers. The smoke test uses isolated synthetic records, no LLM.
RUN uvx --from ruff==0.16.8 ruff check --select F821,F823 src/ \
    && .venv/bin/python deployment/check_control_routes.py
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 MEMSTARA_CONFIG_MODE=environment
ENTRYPOINT ["python", "/app/deployment/exec_service.py"]
CMD ["python", "-m", "memstara.control"]

# Opt-in paid acceptance runner; never started by the application profile.
FROM runtime AS acceptance
RUN SETUPTOOLS_SCM_PRETEND_VERSION="$(cat deployment/VERSION)" uv sync --frozen --extra runtime --extra dev --no-dev
COPY tests/conftest.py /app/tests/conftest.py
COPY tests/live/test_haiku_pipeline.py tests/live/test_request_pause.py /app/tests/live/
COPY scripts/prepare_heart_failure_demo.py /app/scripts/prepare_heart_failure_demo.py
CMD ["python", "/app/deployment/live_acceptance.py"]
