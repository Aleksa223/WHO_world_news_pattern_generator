{{ config(materialized='table') }}

{% set audit_sources = [
    'who_news',
    'campaign_news',
    'commentary_news',
    'event_news',
    'speech_news',
    'statement_news',
    'stories_news',
    'tech_news',
    'economic_news'
] %}

with audit_rows as (
    {% for audit_source in audit_sources %}
    select
        audit_id,
        pipeline_run_id,
        attempt_number,
        source_name,
        source_table,
        date_column,
        status,
        started_at,
        completed_at,
        updated_at,
        metric_date_utc,
        requested_limit,
        selected_rows,
        new_rows,
        refreshed_rows,
        deleted_rows,
        total_rows,
        oldest_published_at,
        newest_published_at,
        published_today_rows,
        retention_days,
        retention_cutoff_utc,
        error_type,
        error_message
    from {{ source(audit_source, 'ingestion_audit') }}
    {% if not loop.last %}
    union all
    {% endif %}
    {% endfor %}
)

select
    source_name || ':' || audit_id as audit_key,
    audit_id,
    pipeline_run_id,
    attempt_number,
    source_name,
    source_table,
    date_column,
    status,
    started_at,
    completed_at,
    updated_at,
    metric_date_utc,
    requested_limit,
    selected_rows,
    new_rows,
    refreshed_rows,
    deleted_rows,
    total_rows,
    oldest_published_at,
    newest_published_at,
    published_today_rows,
    retention_days,
    retention_cutoff_utc,
    error_type,
    error_message
from audit_rows
