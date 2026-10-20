FROM python:3.12-slim AS configure
WORKDIR /app
RUN pip install --no-cache-dir python-dotenv==1.2.1
COPY src/memstara/__init__.py src/memstara/paths.py src/memstara/operational.py src/memstara/stage_models.py src/memstara/container_config.py /app/src/memstara/
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
RUN apt-get update && apt-get install -y --no-install-recommends procps && rm -rf /var/lib/apt/lists/*
COPY README.md THIRD_PARTY_NOTICES.md ./
COPY licenses/ licenses/
COPY src/ src/
COPY examples/ examples/
COPY deployment/ deployment/
RUN SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+container uv sync --frozen --extra runtime --no-dev
RUN .venv/bin/python -c "from importlib.metadata import version; assert version('motoro') == '0.10.0'"
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 MEMSTARA_CONFIG_MODE=environment
ENTRYPOINT ["python", "/app/deployment/exec_service.py"]
CMD ["python", "-m", "memstara.control"]
