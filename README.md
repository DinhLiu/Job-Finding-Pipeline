# Multi-Source Job Market Data Pipeline & Analytics (DataOps-Driven)

An end-to-end, DataOps-driven ELT data pipeline that automatically collects, cleans, orchestrates, and analyzes job postings from multiple tech recruitment platforms (ITViec, TopCV). The system features a dual-mode execution (Automated Daily Sweeps & Interactive Chatbox Requests) controlled via a Telegram Bot.

## 🏗️ System Architecture

The project shifts away from traditional ETL to a modern **ELT (Extract-Load-Transform)** architecture using the **Modern Data Stack**:

1. **Extract & Load (EL):** Containerized Python scripts driven by **Playwright** simulate browser behaviors to bypass anti-bot mechanisms, fetch job postings, and dump raw JSON payloads into **MinIO** (S3-compatible Object Storage).
2. **Ingestion:** Raw payloads are extracted minimally and appended into a PostgreSQL staging area without heavy upstream transformations.
3. **Transform (T):** **dbt (Data Build Tool)** acts as the core transformation engine inside **PostgreSQL**, converting raw, unstructured JSON structures into clean, analytical star-schema data models through a multi-layered SQL pipeline.
4. **Orchestration:** **Apache Airflow** acts as the central nervous system, managing dependencies, operational retries, and failure alerts.
5. **Analytics & Alerts:** **Metabase** provides visual intelligence on market trends, while real-time job matching criteria trigger outbound alerts back to the user via **Telegram**.

## 🛠️ Tech Stack

* **Orchestration:** Apache Airflow
* **Data Collection & Ingestion:** Python, Playwright, Scrapy, DuckDB
* **Raw Data Storage (Data Lake):** MinIO (S3-Compatible Object Storage)
* **Data Warehouse:** PostgreSQL
* **Data Transformation & Quality Assurance:** dbt (Data Build Tool)
* **Visualization / BI:** Metabase
* **Control Interface & Alerting:** Telegram Bot API
* **Infrastructure:** Docker, Docker Compose

## 📁 Project Structure

```text
├── airflow/                  # Apache Airflow core components
│   └── dags/
│       ├── auto_data_pipeline.py    # Scheduled Midnight Sweep DAG (auto_data mode)
│       └── manual_crawl_pipeline.py # On-demand Triggered DAG (crawl_data mode)
├── crawler/                  # Scraper service blueprints
│   ├── scraper.py            # Playwright browser automation engines
│   └── upload_to_minio.py    # Local raw data lake synchronization
├── telegram_bot/             # Chatbox listener running 24/7
│   └── bot_listener.py       # Intercepts commands and triggers Airflow REST API
└── dbt_job_analytics/        # dbt transformation models & tests
    ├── dbt_project.yml       # Core dbt configuration
    ├── packages.yml          # External dbt dependencies (dbt_utils)
    └── models/
        ├── staging/          # Staging Layer: Schema casting and source alignment
        │   ├── stg_itviec.sql
        │   ├── stg_topcv.sql
        │   └── schema.yml    # Data quality constraints (unique, not_null)
        ├── intermediate/     # Intermediate Layer: Complex Regex for salary & skills parsing
        │   └── int_clean_jobs.sql
        └── marts/            # Marts Layer: Dimension and Fact tables built for BI
            └── dim_jobs.sql

```

## ⚙️ Operational Modes

The pipeline explicitly decouples system routines from ad-hoc operational requests into two robust behaviors:

### 1. `auto_data` Mode (Automated Daily Sweeps)

* **Trigger:** Scheduled natively by Airflow at `00:00 UTC` every midnight.
* **Scope:** Traverses a static array of predefined data-centric keywords (`["Data Engineer", "Data Analyst", "Data Scientist"]`).
* **Behavior:** Scans only the first 2 chronological pages of each target platform to capture newly posted openings within the past 24 hours. Minimizes footprint to guarantee IP protection.

### 2. `crawl_data` Mode (Interactive Chatbox Requests)

* **Trigger:** On-demand execution initiated via user text prompt in Telegram.
* **Command Syntax:** `/crawl <keyword> <pages>` (e.g., `/crawl Golang 5`).
* **Behavior:** The Telegram bot securely checks user authorization (`chat_id`), parses inputs, and issues an authenticated HTTP POST payload to trigger the Airflow API parameters dynamically, extracting deep historical records.

## 💎 Key DE Engineering Implementations

### Idempotency & Database Deduping (UPSERT)

To prevent duplicate job records during daily scanning cycles, the transformation layer leverages native PostgreSQL constraints. The primary identity token is bound to the platform's proprietary job ID parsed from the URL.

```sql
/* Ensure data pipeline consistency via SQL Upsert operations */
INSERT INTO analytical.dim_jobs (job_id, title, company, salary_min, salary_max, updated_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (job_id) 
DO UPDATE SET 
    salary_min = EXCLUDED.salary_min,
    salary_max = EXCLUDED.salary_max,
    updated_at = EXCLUDED.updated_at;

```

### dbt Multi-Layered Transformation & Regex Parsing

Dirty salary string ranges (e.g., "$1500 - $2500 USD", "Thoả thuận", "Up to 40M") are structured natively in the database using robust SQL regular expressions inside dbt intermediate states to produce uniform numeric metrics (`salary_min`, `salary_max`, `currency`).

### Automated Data Quality Testing

Utilizes `dbt test` assertions natively built into the continuous cycle to ensure missing properties or structural degradation from unexpected website redesigns do not corrupt reporting layer components:

* `unique` assertions on `job_id`.
* `not_null` validation constraints on core targets (`title`, `company`).
* Custom testing thresholds ensuring `salary_max >= salary_min`.

## 🚀 Getting Started

### Prerequisites

* Docker & Docker Compose installed.
* A Telegram Bot token (generated via `@BotFather`).

### Step 1: Environment Configuration

Clone the repository and set up your environment configurations in a `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
AUTHORIZED_CHAT_ID=your_private_telegram_chat_id
AIRFLOW_IMAGE_NAME=apache/airflow:2.10.0
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password

```

### Step 2: Initialize Infrastructure

Spin up the decoupled infrastructure layers (Airflow, MinIO, PostgreSQL, Metabase, and Telegram Listener) seamlessly via Docker Compose:

```bash
docker compose up -d --build

```

### Step 3: Verify Services

Once execution stabilizes, the local endpoints become active:

* **Apache Airflow Webserver:** `http://localhost:8080`
* **MinIO Console:** `http://localhost:9001`
* **Metabase Analytics:** `http://localhost:3000`

## 📊 Analytics Dashboard Showcase

*(Once active, embed screenshots here displaying Metabase charts depicting hiring densities by programming language, salary brackets distributed across seniority tiers, and tech stack demand shifts over time)*