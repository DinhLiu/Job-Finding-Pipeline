-- Create isolated schemas for pipeline layers
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Raw storage table at Ingestion layer
CREATE TABLE IF NOT EXISTS staging.raw_jobs (
    job_id VARCHAR(100) NOT NULL,         -- Unique job identifier parsed from crawler
    source_platform VARCHAR(50) NOT NULL, -- 'itviec' or 'topcv'
    url TEXT,                             -- Direct reference link to the job posting
    file_name VARCHAR(255),               -- Traceability: target filename inside MinIO
    raw_payload JSONB NOT NULL,           -- Pure unstructured JSON-LD metadata payload
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite primary key enforces structural idempotency across multiple runs
    PRIMARY KEY (job_id, source_platform)
);

-- Composite index optimized for incremental dbt runs 
-- Helps dbt scan for new job records within a specific platform and timeframe efficiently
CREATE INDEX IF NOT EXISTS idx_raw_jobs_incremental 
ON staging.raw_jobs (source_platform, extracted_at DESC);