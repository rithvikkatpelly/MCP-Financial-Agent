# syntax=docker/dockerfile:1
#
# Econ Data API image.
#
# IMPORTANT: the build context is the REPO ROOT, not backend/ — the API
# imports the shared tool logic from src/. Build it with:
#
#   docker build -f backend/Dockerfile -t econ-data-api .
#
# Run it (offline synthetic fixture; add -e FRED_API_KEY=... for live data):
#
#   docker run -p 8080:8080 -e CORS_ALLOWED_ORIGINS=http://localhost:5173 econ-data-api

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Container FS may be read-only / non-root; keep the audit log in /tmp.
    AUDIT_LOG_PATH=/tmp/audit.log

WORKDIR /app

# Dependencies first so this layer is cached across code-only changes.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Shared tool logic (src/) + the HTTP layer (backend/). src/server.py rides
# along but is never started here.
COPY src ./src
COPY backend ./backend

RUN useradd --create-home --uid 10001 appuser
USER appuser

WORKDIR /app/backend

# Cloud Run / Fly / Render inject $PORT; default to 8080 otherwise.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
