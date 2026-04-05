# Backend container (FastAPI) - suitable for Cloud Run
# Build from repo root with:
#   docker build -t ai-notes-backend -f backend/Dockerfile .

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (minimal). Some Python packages (e.g., sentence-transformers/torch)
# can require extra libs; keep this lean and add only if your build fails.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend app code
COPY backend /app

# Cloud Run provides $PORT (usually 8080)
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
