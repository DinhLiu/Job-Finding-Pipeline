/* code_comment_style: English, explanation_style: Vietnamese */
/* Upgraded Intermediate model to handle flexible, negotiable, and multi-currency salary structures safely */

{{ config(materialized='table') }}

WITH staging_data AS (
    SELECT * FROM {{ ref('stg_raw_jobs') }}
),

parsed_salary AS (
    SELECT
        job_id,
        source_platform,
        url,
        job_title,
        company_name,
        location,
        extracted_at,
        raw_salary_object->>'currency' AS salary_currency,

        -- Safe parsing for Min Salary: Check if it's a valid numeric string before casting
        CASE 
            WHEN raw_salary_object->>'minValue' ~ '^[0-9.]+$' 
            THEN CAST(raw_salary_object->>'minValue' AS NUMERIC)
            ELSE NULL 
        END AS salary_min,

        -- Safe parsing for Max Salary: Check if it's a valid numeric string before casting
        CASE 
            WHEN raw_salary_object->>'maxValue' ~ '^[0-9.]+$' 
            THEN CAST(raw_salary_object->>'maxValue' AS NUMERIC)
            ELSE NULL 
        END AS salary_max

    FROM staging_data
),

calculated_metrics AS (
    SELECT
        *,
        -- If both min and max exist, calculate the statistical average salary
        CASE 
            WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL 
            THEN (salary_min + salary_max) / 2
            ELSE COALESCE(salary_min, salary_max) -- Fallback if only one boundary is provided
        END AS salary_avg,

        -- Set a boolean flag to easily filter or group "Thỏa thuận" jobs in dashboards later
        CASE 
            WHEN salary_min IS NULL AND salary_max IS NULL THEN TRUE
            ELSE FALSE
        END AS is_negotiable

    FROM parsed_salary
)

-- Final transformation: Normalize currencies to VND (Assuming 1 USD = 25,000 VND for estimation in 2026)
SELECT
    job_id,
    source_platform,
    url,
    job_title,
    company_name,
    extracted_at,
    is_negotiable,
    salary_currency,
    salary_min,
    salary_max,
    salary_avg,

    -- Normalized average salary in VND for unified charting
    CASE 
        WHEN is_negotiable = TRUE THEN NULL
        WHEN salary_currency = 'USD' THEN salary_avg * 25000
        ELSE salary_avg
    END AS normalized_salary_vnd,

    CASE 
        WHEN location IS NULL OR location = '' THEN 'Remote/Flexible'
        ELSE location
    END AS clean_location

FROM calculated_metrics