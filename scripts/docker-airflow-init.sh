#!/usr/bin/env bash
set -euo pipefail

AIRFLOW_UID="${AIRFLOW_UID:-50000}"

echo "==> Preparing Airflow log directories..."
mkdir -p \
  /opt/airflow/logs/scheduler \
  /opt/airflow/logs/dag_processor_manager
chown -R "${AIRFLOW_UID}:0" /opt/airflow/logs

echo "==> Verifying DAG bind mount..."
if [[ ! -f /opt/airflow/dags/auto_data_pipeline.py ]]; then
  echo "ERROR: /opt/airflow/dags/auto_data_pipeline.py not found."
  echo "The DAG folder bind mount is empty or stale."
  echo "Try: docker compose down && docker compose up -d --force-recreate"
  exit 1
fi

echo "==> Running Airflow DB migration..."
runuser -u airflow -- airflow db migrate

echo "==> Creating Airflow admin user..."
runuser -u airflow -- airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com || true

echo "==> Airflow init complete."
