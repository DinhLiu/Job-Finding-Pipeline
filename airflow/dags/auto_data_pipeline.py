# code_comment_style: English, explanation_style: Vietnamese
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

# Define centralized runtime workspace paths mapped directly from your real structure
PROJECT_ROOT = "/opt/airflow/project_root"
SCRIPTS_DIR = f"{PROJECT_ROOT}/scripts"          # Target folder holding your python extraction routines
DBT_DIR = f"{PROJECT_ROOT}/dbt_jobs/dbt_job_analytics" # Exact path to your dbt project infrastructure

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    "auto_data_pipeline",
    default_args=default_args,
    description="Automated midnight sweep data pipeline for tech jobs market analysis",
    schedule_interval="0 0 * * *",  # Runs at 00:00 UTC every midnight
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    # Task 1: Execute Python ingestion script targeting the correct /scripts subdirectory location
    task_extract_load = BashOperator(
        task_id="extract_and_load_raw",
        bash_command=f"python {SCRIPTS_DIR}/load_to_postgres.py",
    )

    # Task 2: Trigger dbt transformation models inside the targeted nested dbt structure
    task_dbt_run = BashOperator(
        task_id="dbt_transformation_run",
        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir .. --target prod",
    )

    # Task 3: Trigger dbt structural data quality assertions targeting the internal prod network topology
    task_dbt_test = BashOperator(
        task_id="dbt_quality_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir .. --target prod",
    )

    # Enforce automated pipeline execution lineage sequence
    task_extract_load >> task_dbt_run >> task_dbt_test