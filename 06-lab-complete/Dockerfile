# ============================================================
# Production Dockerfile — Multi-stage, < 500 MB, non-root
# ============================================================

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Non-root user
RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

# Copy venv from builder (path is fixed, not user-dependent)
COPY --from=builder /opt/venv /opt/venv

# Copy application + NGAY09 agent modules
COPY app/ ./app/
COPY utils/ ./utils/
COPY common/ ./common/
COPY registry/ ./registry/
COPY law_agent/ ./law_agent/
COPY tax_agent/ ./tax_agent/
COPY compliance_agent/ ./compliance_agent/
COPY customer_agent/ ./customer_agent/

RUN chown -R agent:agent /app && chown -R agent:agent /opt/venv

USER agent

ENV PATH=/opt/venv/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Increased start-period: sub-agents need ~30s to boot + register
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Single worker — lifespan starts sub-agents as child processes; multi-worker would cause port conflicts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
