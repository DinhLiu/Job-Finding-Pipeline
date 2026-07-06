# Job Finding Pipeline

An ELT data pipeline for crawling job postings from ITViec and TopCV, storing raw JSON-LD payloads in MinIO, loading them into PostgreSQL, transforming them with dbt, and sending a cleaned job report to Discord.

## Quick Start

```bash
cp .env.example .env
# Set DISCORD_BOT_TOKEN and DISCORD_WEBHOOK_URL in .env

bash scripts/setup.sh
docker compose up -d discord-bot   # optional
```

Open Airflow at http://localhost:8080 (`admin` / `admin`), then trigger the pipeline from the UI or Discord:

```text
!search -k "Data Engineer" -p 1
```

## Architecture

```text
Discord command
  -> Discord bot
  -> Airflow DAG trigger
  -> Playwright crawlers
  -> MinIO raw JSON storage
  -> PostgreSQL staging.raw_jobs
  -> dbt analytics models
  -> Discord webhook report
```

## Tech Stack

- Python 3.11+
- Playwright, BeautifulSoup
- MinIO
- PostgreSQL 15
- Apache Airflow 2.10.0
- dbt Core / dbt-postgres 1.8.0
- Discord bot and Discord webhook
- Docker Compose

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ (only if running scripts or the Discord bot locally)
- Discord bot token and webhook URL

## Repository Structure

```text
.
|-- airflow/
|   |-- dags/
|   |   `-- auto_data_pipeline.py
|   `-- logs/                         # created by setup; owned by Airflow user
|-- dbt_jobs/
|   |-- profiles.yml
|   `-- dbt_job_analytics/
|       |-- dbt_project.yml
|       `-- models/
|           |-- sources.yml
|           |-- schema.yml
|           |-- stg_raw_jobs.sql
|           |-- int_job_postings.sql
|           `-- dim_job_postings.sql
|-- discord_bot/
|   |-- discord_bot.py
|   `-- dockerfile
|-- scripts/
|   |-- setup.sh                    # recommended first-time setup
|   |-- docker-airflow-init.sh      # permissions + Airflow DB init
|   |-- crawler.py
|   |-- load_to_minio.py
|   |-- load_to_postgres.py
|   |-- report_to_discord.py
|   `-- crawlers/
|       |-- it_viec.py
|       `-- topcv.py
|-- .env.example
|-- docker-compose.yml
|-- dockerfile
|-- init.sql
|-- requirements.txt
`-- README.md
```

## Setup

### Recommended: one-command setup

```bash
cp .env.example .env
bash scripts/setup.sh
```

`scripts/setup.sh` runs these steps in order:

1. Create `.env` from `.env.example` if missing.
2. Start Postgres and MinIO.
3. Run `airflow-init` to fix log directory permissions, migrate the Airflow DB, and verify the DAG bind mount.
4. Recreate `airflow-webserver` and `airflow-scheduler`.
5. Wait for Airflow health and confirm `auto_data_pipeline` is loaded.

Start the Discord bot after setup:

```bash
docker compose up -d discord-bot
```

### Manual setup

```bash
cp .env.example .env
mkdir -p airflow/logs

docker compose up -d --build postgres minio
docker compose run --rm airflow-init
docker compose up -d --force-recreate airflow-webserver airflow-scheduler
docker compose up -d discord-bot
```

### Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Airflow | http://localhost:8080 | `admin` / `admin` |
| MinIO Console | http://localhost:9001 | `admin` / `securepassword123` |
| PostgreSQL | `localhost:5433` | `warehouse_user` / `warehouse_password` |

## Environment Variables

Copy `.env.example` to `.env` and fill in the required secrets:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

Docker Compose sets infrastructure variables for Airflow services. For local scripts outside Docker, `.env.example` already points to host endpoints:

```env
MINIO_ENDPOINT_URL=http://localhost:9000
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
```

Discord bot Airflow settings:

| Run mode | `AIRFLOW_API_URL` |
|----------|-------------------|
| Local: `python -m discord_bot.discord_bot` | `http://localhost:8080/api/v1/dags/auto_data_pipeline/dagRuns` |
| Docker: `docker compose up -d discord-bot` | `http://airflow-webserver:8080/api/v1/dags/auto_data_pipeline/dagRuns` (set automatically in `docker-compose.yml`) |

## Discord Bot

Entry point:

```text
discord_bot/discord_bot.py
```

Command syntax:

```text
!search -k "Data Engineer" -p 3
```

Options:

- `-k`, `--keyword`: search keyword
- `-p`, `--pages`: number of listing pages per source (default `1`)

`--pages 3` crawls pages `1`, `2`, and `3` for each source.

Run modes:

```bash
# Inside Docker (recommended for production-like setup)
docker compose up -d discord-bot

# On host (requires Airflow running at localhost:8080)
python -m discord_bot.discord_bot
```

Trigger payload sent to Airflow:

```json
{
  "conf": {
    "keyword": "Data Engineer",
    "pages": 3
  }
}
```

## Airflow DAG

DAG file:

```text
airflow/dags/auto_data_pipeline.py
```

DAG ID: `auto_data_pipeline`

Schedule: `0 0 * * *`

Task order:

```text
crawl_to_minio
  -> load_minio_to_postgres
  -> dbt_transformation_run
  -> dbt_quality_test
  -> send_clean_data_report
```

Runtime config:

```json
{
  "keyword": "Data Engineer",
  "pages": 3
}
```

Defaults when no config is passed:

```text
keyword = Data Engineer
pages = 1
```

dbt tasks write build artifacts to `/tmp/dbt_logs` and `/tmp/dbt_target` inside the Airflow container so bind-mounted repo folders do not need write permission from the Airflow user.

## Pipeline Components

### Crawlers

```bash
python scripts/crawler.py --headless -k "Data Engineer" --pages 3
```

Supported sources:

- `scripts/crawlers/it_viec.py`
- `scripts/crawlers/topcv.py`

Each crawler extracts job URLs from listing pages, opens job detail pages, extracts `JobPosting` JSON-LD, and uploads records to MinIO.

### MinIO Raw Storage

Bucket: `raw-job-payloads`

Object keys:

```text
itviec/YYYY/MM/DD/itviec_output.json
topcv/YYYY/MM/DD/topcv_output.json
```

### PostgreSQL Ingestion

`scripts/load_to_postgres.py` reads the newest JSON object per source from MinIO and upserts into `staging.raw_jobs`.

Primary key:

```sql
PRIMARY KEY (job_id, source_platform)
```

### dbt Models

Project path:

```text
dbt_jobs/dbt_job_analytics
```

Models:

- `stg_raw_jobs.sql`: reads `staging.raw_jobs` and extracts base JSON fields
- `int_job_postings.sql`: parses salary, negotiable flags, normalized salary metrics, and location
- `dim_job_postings.sql`: final analytics table with job level classification

Final reporting table:

```text
analytics.dim_job_postings
```

Run locally:

```bash
cd dbt_jobs/dbt_job_analytics
dbt run --profiles-dir .. --target dev
dbt test --profiles-dir .. --target dev
```

### Discord Report

`scripts/report_to_discord.py` queries `analytics.dim_job_postings` and sends a Discord embed with:

- total new jobs seen in the current session
- top jobs ordered by `salary_max DESC NULLS LAST`
- job title, company, URL, and salary range

## Manual Commands

Run crawler locally:

```bash
python scripts/crawler.py --headless -k "Data Engineer" --pages 3
```

Load latest MinIO objects into PostgreSQL:

```bash
python scripts/load_to_postgres.py
```

Send Discord report:

```bash
python scripts/report_to_discord.py
```

Install Python dependencies for local use:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Data Flow

1. `scripts/crawler.py` crawls ITViec and TopCV.
2. `scripts/load_to_minio.py` uploads raw JSON arrays to MinIO.
3. `scripts/load_to_postgres.py` reads latest MinIO objects and upserts into `staging.raw_jobs`.
4. dbt builds staging, intermediate, and dimension models in PostgreSQL.
5. `scripts/report_to_discord.py` sends a summary report to Discord.

## Troubleshooting

### Airflow UI not loading or log permission errors

```bash
docker compose run --rm airflow-init
docker compose restart airflow-webserver airflow-scheduler
```

### DAG missing or Discord bot gets HTTP 404

Usually a stale bind mount. Recreate Airflow containers:

```bash
docker compose up -d --force-recreate airflow-webserver airflow-scheduler
```

Verify:

```bash
curl -s -u admin:admin http://localhost:8080/api/v1/dags
docker exec de_project_airflow_webserver ls -la /opt/airflow/dags/
```

### `dbt_transformation_run` fails with exit code 2 and no output

This was caused by Airflow lacking write permission on bind-mounted `dbt_jobs/`. The DAG now writes dbt artifacts to `/tmp`. If it still fails, rerun setup:

```bash
bash scripts/setup.sh
```

### Discord bot cannot connect to Airflow

| Symptom | Fix |
|---------|-----|
| `Cannot connect to host airflow-webserver` | Bot is running on the host but URL points to Docker DNS. Use `localhost:8080` or set `AIRFLOW_API_URL` in `.env`. |
| `404 NOT FOUND` on trigger | DAG is not active. Recreate Airflow containers and confirm the DAG appears in the UI. |

### Full reset

```bash
docker compose down
bash scripts/setup.sh
```

## Notes

- `--pages N` means crawl pages `1..N` for each source.
- The pipeline upserts by `(job_id, source_platform)`, so repeated runs update existing jobs instead of inserting duplicates.
- `analytics.dim_job_postings` is materialized as a dbt table.
- The Discord bot starts the pipeline; the final report is sent by webhook after dbt tests pass.
- Always run `airflow-init` before starting Airflow services on a fresh machine.
- Prefer `bash scripts/setup.sh` over `docker compose up -d` alone to avoid permission and bind-mount issues.
