# ==============================================================================
# Sovereign Agent Runtime - Production Multi-Stage Distroless Container
# Hardened for Sovereign Cloud Deployment (Zero Shell, Non-Root UID 65532)
# ==============================================================================

# Stage 1: Build wheels and virtual environment via Astral UV
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install uv for fast, deterministic dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /bin/uv

# Copy project specification files
COPY pyproject.toml README.md /build/

# Create isolated virtual environment and install production dependencies
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache-dir --requirement pyproject.toml

# Copy application source tree and install current package
COPY src/ /build/src/
RUN . /opt/venv/bin/activate && \
    uv pip install --no-cache-dir --no-deps -e .

# ------------------------------------------------------------------------------
# Stage 2: Google Distroless Python3 Runtime (Minimal CVE Footprint)
# ------------------------------------------------------------------------------
FROM gcr.io/distroless/python3-debian12:nonroot AS runner

WORKDIR /app

# Copy prepared virtual environment and application code from builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/src /app/src
COPY --from=builder /build/pyproject.toml /app/pyproject.toml

# Set non-root execution environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src:/opt/venv/lib/python3.12/site-packages" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SOVEREIGN_ENVIRONMENT=production

# Non-root user provided by distroless (UID 65532)
USER 65532:65532

EXPOSE 8000

# High-concurrency Uvicorn server entrypoint
ENTRYPOINT ["/opt/venv/bin/python", "-m", "uvicorn", "runtime.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
