FROM python:3.12-slim

# Unbuffered stdout so `docker compose logs` shows startup/migration output live.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# build-essential is needed by a few wheels (bcrypt/cryptography) on slim images.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# Single worker on purpose: run_migrations() fires from the FastAPI lifespan hook
# (main.py -> app/db/database.py), and multiple workers would race on
# `alembic upgrade head` at startup.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
