# Demo Agent Dockerfile
# Multi-stage build for minimal image size
# Build: docker build -t demo-agent .

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user for security (before COPY --chown)
RUN useradd -m -u 1000 demouser && \
    mkdir -p /app/logs /app/credentials

# Copy application code with correct ownership
COPY --chown=demouser:demouser app /app/app
COPY --chown=demouser:demouser __main__.py /app/
COPY --chown=demouser:demouser prompts /app/prompts

# Set Python path
ENV PYTHONPATH=/app

# Set permissions and ownership
RUN chown -R demouser:demouser /app
USER demouser

# Default port (overridable via environment)
ARG PORT=9090
ENV DEMO_AGENT_PORT=${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:${DEMO_AGENT_PORT}/health || exit 1

# Expose port
EXPOSE ${PORT}

# Run application
CMD ["python", "-m", "__main__"]
