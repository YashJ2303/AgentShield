FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY sdk /app/sdk
COPY server /app/server
COPY README.md /app/README.md

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e /app/sdk && \
    pip install --no-cache-dir \
    fastapi \
    uvicorn \
    sqlalchemy \
    alembic \
    psycopg2-binary \
    pydantic \
    pydantic-settings \
    pyyaml \
    httpx \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp-proto-http \
    sqlglot \
    python-multipart

EXPOSE 8000

CMD ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
