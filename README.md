# Job Finding Pipeline

An ELT data pipeline for crawling job postings from ITViec and TopCV, storing raw JSON-LD payloads in MinIO, loading them into PostgreSQL, transforming them with dbt, and sending a cleaned job report to Discord.

## Current Architecture

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

- Python 3.11
- Playwright, BeautifulSoup
- MinIO
- PostgreSQL 15
- Apache Airflow 2.10.0
- dbt Core / dbt-postgres 1.8.0
- Discord bot and Discord webhook
- Docker Compose

## Repository Structure

```text
.
|-- airflow/
|   `-- dags/
|       `-- auto_data_pipeline.py
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
|   |-- crawler.py
|   |-- load_to_minio.py
|   |-- load_to_postgres.py
|   |-- report_to_discord.py
|   `-- crawlers/
|       |-- it_viec.py
|       `-- topcv.py
|-- docker-compose.yml
|-- dockerfile
|-- init.sql
|-- requirements.txt
`-- README.md
```

## Main Components

### Crawlers

The crawler entrypoint is:

```bash
python scripts/crawler.py --headless -k "Data Engineer" --pages 3
```

It crawls the first `N` listing pages for each keyword. For example, `--pages 3` crawls pages `1`, `2`, and `3`, not only page `3`.

The crawler currently supports:

- `scripts/crawlers/it_viec.py`
- `scripts/crawlers/topcv.py`

Each crawler extracts job URLs from listing pages, opens each job detail page, extracts `JobPosting` JSON-LD, and uploads records to MinIO.

### MinIO Raw Storage

Raw records are uploaded to the `raw-job-payloads` bucket with date-partitioned keys:

```text
itviec/YYYY/MM/DD/itviec_output.json
topcv/YYYY/MM/DD/topcv_output.json
```

### PostgreSQL Ingestion

`scripts/load_to_postgres.py` reads the newest JSON object per source from MinIO and upserts rows into:

```text
staging.raw_jobs
```

The table is created by `init.sql` and uses this primary key:

```sql
PRIMARY KEY (job_id, source_platform)
```

### dbt Models

The dbt project is in:

```text
dbt_jobs/dbt_job_analytics
```

Models:

- `stg_raw_jobs.sql`: reads `staging.raw_jobs` and extracts base JSON fields.
- `int_job_postings.sql`: parses salary fields, negotiable flags, normalized salary metrics, and location.
- `dim_job_postings.sql`: creates the final analytics table with job level classification.

Final reporting table:

```text
analytics.dim_job_postings
```

### Discord Bot

The Discord bot is in:

```text
discord_bot/discord_bot.py
```

Command syntax:

```text
!search -k "Data Engineer" -p 3
```

Options:

- `-k`, `--keyword`: search keyword.
- `-p`, `--pages`: number of listing pages to crawl from each source. Defaults to `1`.

The bot triggers Airflow through:

```text
http://airflow-webserver:8080/api/v1/dags/auto_data_pipeline/dagRuns
```

Payload example:

```json
{
  "conf": {
    "keyword": "Data Engineer",
    "pages": 3
  }
}
```

### Discord Report

`scripts/report_to_discord.py` queries:

```text
analytics.dim_job_postings
```

It sends a Discord embed containing:

- total cleaned jobs extracted today
- top jobs ordered by `salary_max DESC NULLS LAST`
- job title, company, URL, and salary range

## Airflow DAG

The main DAG is:

```text
airflow/dags/auto_data_pipeline.py
```

DAG ID:

```text
auto_data_pipeline
```

Schedule:

```text
0 0 * * *
```

Task order:

```text
crawl_to_minio
  -> load_minio_to_postgres
  -> dbt_transformation_run
  -> dbt_quality_test
  -> send_clean_data_report
```

The DAG accepts runtime config:

```json
{
  "keyword": "Data Engineer",
  "pages": 3
}
```

If no config is passed, the DAG defaults to:

```text
keyword = Data Engineer
pages = 1
```

## Environment Variables

The Docker Compose file already defines most infrastructure variables for Airflow services.

Expected variables:

```env
MINIO_ENDPOINT_URL=http://minio:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=securepassword123
MINIO_BUCKET_NAME=raw-job-payloads

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=job_analytics
POSTGRES_USER=warehouse_user
POSTGRES_PASSWORD=warehouse_password

DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

For local scripts outside Docker, use:

```env
MINIO_ENDPOINT_URL=http://localhost:9000
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
```

## Running With Docker Compose

Start the stack:

```bash
docker compose up -d --build
```

Initialize Airflow if needed:

```bash
docker compose up airflow-init
```

Open services:

- Airflow: http://localhost:8080
- MinIO Console: http://localhost:9001
- PostgreSQL: localhost:5433

Default Airflow credentials from `docker-compose.yml`:

```text
username: admin
password: admin
```

Default MinIO credentials from `docker-compose.yml`:

```text
username: admin
password: securepassword123
```

## Manual Commands

Run crawler locally:

```bash
python scripts/crawler.py --headless -k "Data Engineer" --pages 3
```

Load latest MinIO objects into PostgreSQL:

```bash
python scripts/load_to_postgres.py
```

Run dbt locally:

```bash
cd dbt_jobs/dbt_job_analytics
dbt run --profiles-dir .. --target dev
dbt test --profiles-dir .. --target dev
```

Send Discord report:

```bash
python scripts/report_to_discord.py
```

## Data Flow Details

1. `scripts/crawler.py` crawls ITViec and TopCV.
2. `scripts/load_to_minio.py` uploads raw JSON arrays to MinIO.
3. `scripts/load_to_postgres.py` reads latest MinIO objects and upserts into `staging.raw_jobs`.
4. dbt builds staging, intermediate, and dimension models in PostgreSQL.
5. `scripts/report_to_discord.py` sends a summary report to Discord.

## Notes

- `--pages N` means crawl pages `1..N` for each source.
- The pipeline upserts by `(job_id, source_platform)`, so repeated runs update existing jobs instead of inserting duplicates.
- `analytics.dim_job_postings` is materialized as a dbt table.
- The Discord bot starts the pipeline; the final report is sent by webhook after dbt tests pass.
