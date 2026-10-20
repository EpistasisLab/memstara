# Same Python as the local venv (3.12). A container that differs from the machine the
# code was written on is a source of bugs that only appear after deploy.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt requirements-semantic.txt ./
ARG ENABLE_UNIVERSE_SEMANTICS=0
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$ENABLE_UNIVERSE_SEMANTICS" = "1" ]; then pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements-semantic.txt; fi

COPY api/ ./api/

# Read-only credentials by default. The account holds SELECT and nothing else, so even
# a bug here cannot change the board.
ENV VIEWER_CORS=""

EXPOSE 8000
# Snapshot assembly performs several independent database reads. Keep one slow read
# from monopolising the only event loop and making every browser request time out.
CMD ["uvicorn", "main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
