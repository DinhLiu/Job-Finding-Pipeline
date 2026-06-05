# code_comment_style: English, explanation_style: Vietnamese
from datetime import datetime, timedelta
import requests
from airflow import DAG
from airflow.operators.bash import BashOperator
from dotenv import load_dotenv
import os

load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

def send_discord_alert(context):
    """
    Automated callback function to structure and send failure telemetry to Discord via Webhook
    """
    ti = context.get("task_instance")
    dag_id = ti.dag_id
    task_id = ti.task_id
    execution_date = context.get("execution_date").strftime("%Y-%m-%d %H:%M:%S")
    log_url = ti.log_url

    # Structure a clean Embed message for Discord
    payload = {
        "username": "Airflow Monitor",
        "avatar_url": "https://airflow.apache.org/images/feature-image.png",
        "embeds": [{
            "title": "🚨 DATA PIPELINE TASK FAILED",
            "color": 15158332, # Vibrant Red color code
            "fields": [
                {"name": "DAG ID", "value": f"`{dag_id}`", "inline": True},
                {"name": "Task ID", "value": f"`{task_id}`", "inline": True},
                {"name": "Execution Time (UTC)", "value": f"{execution_date}", "inline": False},
                {"name": "Local Log Link", "value": f"[Click here to view log]({log_url})", "inline": False}
            ],
            "footer": {
                "text": "DE Project Automated Alert System"
            },
            "timestamp": datetime.utcnow().isoformat()
        }]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send alert to Discord: {e}")

# Define centralized runtime workspace paths inside the Linux container
PROJECT_ROOT = "/opt/airflow/project_root"
SCRIPTS_DIR = f"{PROJECT_ROOT}/scripts"
DBT_DIR = f"{PROJECT_ROOT}/dbt_jobs/dbt_job_analytics"

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    # HOOK: This binds the alert function to ALL tasks inside this DAG
    "on_failure_callback": send_discord_alert,
}

with DAG(
    "auto_data_pipeline",
    default_args=default_args,
    description="Automated midnight sweep data pipeline for tech jobs market analysis",
    schedule_interval="0 0 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    task_crawl_to_minio = BashOperator(
        task_id="crawl_to_minio",
        bash_command=f"python {SCRIPTS_DIR}/crawler.py --headless",
    )

    task_load_to_postgres = BashOperator(
        task_id="load_minio_to_postgres",
        bash_command=f"python {SCRIPTS_DIR}/load_to_postgres.py",
    )

    task_dbt_run = BashOperator(
        task_id="dbt_transformation_run",
        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir .. --target prod",
    )
    task_dbt_test = BashOperator(
        task_id="dbt_quality_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir .. --target prod",
    )

    task_discord_report = BashOperator(
        task_id="send_clean_data_report",
        bash_command=f"python {SCRIPTS_DIR}/report_to_discord.py",
    )

    task_crawl_to_minio >> task_load_to_postgres >> task_dbt_run >> task_dbt_test >> task_discord_report
