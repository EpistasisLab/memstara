# Same Python as the local venv (3.12). A container that differs from the machine the
# code was written on is a source of bugs that only appear after deploy.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/

# Read-only credentials by default. The account holds SELECT and nothing else, so even
# a bug here cannot change the board.
ENV MEMSTARA_VIEWER_DSN="postgresql://memstara_viewer:viewer@host.docker.internal:5463/memstara" \
    CORE_VIEWER_DSN="postgresql://memstara_viewer:viewer@host.docker.internal:5453/motoro" \
    VIEWER_CORS=""

EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000"]
