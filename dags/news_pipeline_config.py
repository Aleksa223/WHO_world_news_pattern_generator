"""Configuration for the daily WHO, Tech, and Economic news fetches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# This is the API batch size for each daily task, not a database retention cap.
# Fetchers upsert these batches into cumulative SQLite tables.
DAILY_FETCH_LIMIT = 200


@dataclass(frozen=True)
class FetchJob:
    """One command-line fetch job executed by the Airflow DAG."""

    name: str
    script: str
    database: str
    output: str
    fetch_limit: int = DAILY_FETCH_LIMIT
    extra_args: tuple[str, ...] = ()


WHO_FETCH_JOBS = (
    FetchJob(
        name="news",
        script="who_news_scripts/who_news.py",
        database="articles/who_news.db",
        output="articles/who_latest_news.json",
    ),
    FetchJob(
        name="campaigns",
        script="who_news_scripts/who_campaigns.py",
        database="articles/who_campaign_news.db",
        output="articles/who_latest_campaigns.json",
    ),
    FetchJob(
        name="commentaries",
        script="who_news_scripts/who_commentaries.py",
        database="articles/who_commentary_news.db",
        output="articles/who_latest_commentaries.json",
    ),
    FetchJob(
        name="events",
        script="who_news_scripts/who_events.py",
        database="articles/who_event_news.db",
        output="articles/who_latest_events.json",
    ),
    FetchJob(
        name="speeches",
        script="who_news_scripts/who_speeches.py",
        database="articles/who_speech_news.db",
        output="articles/who_latest_speeches.json",
    ),
    FetchJob(
        name="statements",
        script="who_news_scripts/who_statements.py",
        database="articles/who_statement_news.db",
        output="articles/who_latest_statements.json",
    ),
    FetchJob(
        name="stories",
        script="who_news_scripts/who_feature_stories.py",
        database="articles/who_stories_news.db",
        output="articles/who_latest_feature_stories.json",
    ),
)

TECH_FETCH_JOBS = (
    FetchJob(
        name="tech_news",
        script="tech_news_scripts/tech_news.py",
        database="tech_articles/tech_news.db",
        output="tech_articles/tech_news.json",
        extra_args=("--timeout", "30", "--workers", "16"),
    ),
)

ECONOMIC_FETCH_JOBS = (
    FetchJob(
        name="economic_news",
        script="economic_news_scripts/economic_news.py",
        database="economic_articles/economic_news.db",
        output="economic_articles/economic_news.json",
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
