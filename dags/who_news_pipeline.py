"""Airflow DAG for fetching and transforming WHO news data."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import dag, task


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("WHO_NEWS_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)
).resolve()
DATABASE_PATH = PROJECT_ROOT / "articles" / "who_news.db"
JSON_OUTPUT_PATH = PROJECT_ROOT / "articles" / "latest_who_news.json"


@dag(
    dag_id="who_news_pipeline",
    description="Fetch WHO news and build the dbt staging, intermediate, and mart layers.",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["who", "news", "dbt"],
)
def who_news_pipeline():
    @task
    def fetch_who_news() -> str:
        """Fetch the latest WHO records into the raw SQLite table."""
        subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "who_news.py"),
                "--limit",
                "200",
                "--database",
                str(DATABASE_PATH),
                "--output",
                str(JSON_OUTPUT_PATH),
            ],
            cwd=PROJECT_ROOT,
            check=True,
        )
        return str(DATABASE_PATH)

    @task
    def build_dbt_models(_: str) -> None:
        """Build and test every dbt layer after a successful fetch."""
        from dbt.cli.main import dbtRunner

        # SQLite paths in profiles.yml are relative to the project directory.
        os.chdir(PROJECT_ROOT)
        result = dbtRunner().invoke(
            [
                "build",
                "--project-dir",
                str(PROJECT_ROOT),
                "--profiles-dir",
                str(PROJECT_ROOT),
                "--no-use-colors",
            ]
        )
        if not result.success:
            raise RuntimeError("dbt build failed") from result.exception

    build_dbt_models(fetch_who_news())


who_news_pipeline()
