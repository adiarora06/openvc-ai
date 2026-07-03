FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first to leverage Docker layer caching.
COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --upgrade pip && pip install -e .

# Copy the remainder of the project (tests, etc.).
COPY . /app

EXPOSE 8080

# Container-level health check hits the lightweight liveness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "openvc_ai.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
