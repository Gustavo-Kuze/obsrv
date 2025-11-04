# Multi-stage Dockerfile for Obsrv API

# Base stage with common dependencies
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 obsrv && chown -R obsrv:obsrv /app

# Copy requirements
COPY --chown=obsrv:obsrv pyproject.toml ./

# Development stage
FROM base as development

# Copy application code
COPY --chown=obsrv:obsrv backend/ ./backend/
COPY --chown=obsrv:obsrv tests/ ./tests/

# Install development dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Switch to non-root user
USER obsrv

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run development server with auto-reload
CMD ["uvicorn", "backend.src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base as production

# Set working directory to /app
WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Copy application code
COPY --chown=obsrv:obsrv backend/ ./backend/

# Install production dependencies only
RUN pip install --no-cache-dir .

# Switch to non-root user
USER obsrv

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run production server with multiple workers
CMD ["sh", "-c", "PYTHONPATH=/app uvicorn backend.src.api.main:app --host 0.0.0.0 --port 8000 --workers 4"]
