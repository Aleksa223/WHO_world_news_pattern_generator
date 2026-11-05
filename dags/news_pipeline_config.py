"""Configuration for the daily WHO, Tech, and Economic news fetches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# This is the API batch size for each daily task, not a database retention cap.
# Fetchers upsert into cumulative tables; the DAG applies retention separately.
DAILY_FETCH_LIMIT = 200


@dataclass(frozen=True)
class FetchJob:
    """One command-line fetch job executed by the Airflow DAG."""

    name: str
    source_name: str
    script: str
    database: str
    output: str
    table: str
    date_column: str | None = "published_at"
    fetch_limit: int = DAILY_FETCH_LIMIT
    extra_args: tuple[str, ...] = ()


WHO_FETCH_JOBS = (
    FetchJob(
        name="news",
        source_name="who_news",
        script="who_news_scripts/who_news.py",
        database="articles/who_news.db",
        output="articles/who_latest_news.json",
        table="articles",
    ),
    FetchJob(
        name="campaigns",
        source_name="who_campaigns",
        script="who_news_scripts/who_campaigns.py",
        database="articles/who_campaign_news.db",
        output="articles/who_latest_campaigns.json",
        table="campaigns",
        date_column=None,
    ),
    FetchJob(
        name="commentaries",
        source_name="who_commentaries",
        script="who_news_scripts/who_commentaries.py",
        database="articles/who_commentary_news.db",
        output="articles/who_latest_commentaries.json",
        table="commentaries",
    ),
    FetchJob(
        name="events",
        source_name="who_events",
        script="who_news_scripts/who_events.py",
        database="articles/who_event_news.db",
        output="articles/who_latest_events.json",
        table="events",
        date_column=None,
    ),
    FetchJob(
        name="speeches",
        source_name="who_speeches",
        script="who_news_scripts/who_speeches.py",
        database="articles/who_speech_news.db",
        output="articles/who_latest_speeches.json",
        table="speeches",
    ),
    FetchJob(
        name="statements",
        source_name="who_statements",
        script="who_news_scripts/who_statements.py",
        database="articles/who_statement_news.db",
        output="articles/who_latest_statements.json",
        table="statements",
    ),
    FetchJob(
        name="stories",
        source_name="who_stories",
        script="who_news_scripts/who_feature_stories.py",
        database="articles/who_stories_news.db",
        output="articles/who_latest_feature_stories.json",
        table="feature_stories",
    ),
)

TECH_FETCH_JOBS = (
    FetchJob(
        name="tech_news",
        source_name="tech_news",
        script="tech_news_scripts/tech_news.py",
        database="tech_articles/tech_news.db",
        output="tech_articles/tech_news.json",
        table="tech_articles",
        extra_args=("--timeout", "30", "--workers", "16"),
    ),
)

ECONOMIC_FETCH_JOBS = (
    FetchJob(
        name="economic_news",
        source_name="economic_news",
        script="economic_news_scripts/economic_news.py",
        database="economic_articles/economic_news.db",
        output="economic_articles/economic_news.json",
        table="economic_articles",
        extra_args=("--timespan", "1d", "--timeout", "30"),
    ),
)

ALL_FETCH_JOBS = WHO_FETCH_JOBS + TECH_FETCH_JOBS + ECONOMIC_FETCH_JOBS

# Select every domain's staging models before building shared downstream layers.
DBT_NEWS_SELECTION = (
    "path:staging",
    "path:intermediate",
    "path:marts",
    "path:seeds",
    "path:snapshots",
)


def build_fetch_command(
    job: FetchJob,
    project_root: Path,
    python_executable: str,
) -> list[str]:
    """Build a shell-free command for one configured fetch job."""
    project_root = project_root.resolve()
    return [
        python_executable,
        str(project_root / job.script),
        "--limit",
        str(job.fetch_limit),
        "--database",
        str(project_root / job.database),
        "--output",
        str(project_root / job.output),
        *job.extra_args,
    ]
