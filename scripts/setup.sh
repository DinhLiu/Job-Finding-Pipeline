#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Set DISCORD_BOT_TOKEN and DISCORD_WEBHOOK_URL before starting discord-bot."
fi

mkdir -p airflow/logs

echo "==> Starting infrastructure..."
docker compose up -d --build postgres minio

echo "==> Initializing Airflow (permissions + database)..."
docker compose run --rm airflow-init

echo "==> Starting Airflow services..."
docker compose up -d --force-recreate airflow-webserver airflow-scheduler

echo "==> Waiting for Airflow..."
for _ in $(seq 1 30); do
  if curl -sf -u admin:admin http://localhost:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -sf -u admin:admin http://localhost:8080/health >/dev/null 2>&1; then
  echo "ERROR: Airflow did not become healthy on http://localhost:8080"
  exit 1
fi

dag_count="$(curl -s -u admin:admin http://localhost:8080/api/v1/dags | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_entries', 0))")"
if [[ "${dag_count}" -lt 1 ]]; then
  echo "ERROR: No DAGs loaded in Airflow."
  echo "Try: docker compose up -d --force-recreate airflow-webserver airflow-scheduler"
  exit 1
fi

echo "==> Setup complete."
echo "Airflow UI: http://localhost:8080 (admin/admin)"
echo "Optional: docker compose up -d discord-bot"
