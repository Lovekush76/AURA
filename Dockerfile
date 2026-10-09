# ==============================================================================
# Aura Assistant - Multi-Stage Sovereign Container Build
# ==============================================================================

# STAGE 1: Frontend Build
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# STAGE 2: Python Backend & Unified Production Runtime
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies (curl, build tools, audio/ffmpeg if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install .

# Copy application sources
COPY src/ /app/src/
COPY configs/ /app/configs/
COPY daemons/ /app/daemons/
COPY scripts/ /app/scripts/

# Copy built frontend assets into static web root
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose API and WebSocket IPC port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default launch command
CMD ["uvicorn", "aura_assistant.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
