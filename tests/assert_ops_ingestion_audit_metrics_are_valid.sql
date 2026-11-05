select *
from {{ ref('ops_mart_ingestion_runs') }}
where
    (attempt_number is not null and attempt_number <= 0)
    or (requested_limit is not null and requested_limit <= 0)
    or (selected_rows is not null and selected_rows < 0)
    or new_rows < 0
    or refreshed_rows < 0
    or deleted_rows < 0
    or total_rows < 0
    or (published_today_rows is not null and published_today_rows < 0)
    or (retention_days is not null and retention_days <= 0)
    or (selected_rows is not null and selected_rows <> new_rows + refreshed_rows)
    or (published_today_rows is not null and published_today_rows > total_rows)
    or datetime(started_at) is null
    or datetime(updated_at) is null
    or date(metric_date_utc) is null
    or (status = 'running' and completed_at is not null)
    or (status <> 'running' and completed_at is null)
    or (completed_at is not null and datetime(completed_at) is null)
    or (
        completed_at is not null
        and julianday(completed_at) < julianday(started_at)
    )
    or julianday(updated_at) < julianday(started_at)
    or (
        oldest_published_at is not null
        and newest_published_at is not null
        and julianday(newest_published_at) < julianday(oldest_published_at)
    )
