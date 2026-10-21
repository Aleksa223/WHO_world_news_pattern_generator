"""Airflow DAG for fetching and transforming WHO, Tech, and Economic news."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import TriggerRule, dag, task, task_group

from news_pipeline_config import (
    DBT_NEWS_SELECTION,
    ECONOMIC_FETCH_JOBS,
    TECH_FETCH_JOBS,
    WHO_FETCH_JOBS,
    FetchJob,
    build_fetch_command,
)


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("WHO_NEWS_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)
).resolve()


@dag(
    dag_id="who_news_pipeline",
    description=(
        "Fetch WHO, Tech, and Economic news and build all dbt warehouse layers."
    ),
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["who", "tech", "economic", "news", "dbt"],
)
def who_news_pipeline():
    @task(execution_timeout=timedelta(minutes=15))
    def fetch_source(
        script: str,
        database: str,
        output: str,
        limit: int,
        extra_args: list[str],
    ) -> str:
        """Fetch one source into its raw SQLite database."""
        job = FetchJob(
            name="runtime",
            script=script,
            database=database,
            output=output,
            fetch_limit=limit,
            extra_args=tuple(extra_args),
        )
        subprocess.run(
            build_fetch_command(job, PROJECT_ROOT, sys.executable),
            cwd=PROJECT_ROOT,
            check=True,
        )
        return str(PROJECT_ROOT / database)

    @task(
        execution_timeout=timedelta(minutes=5),
        trigger_rule=TriggerRule.ALL_DONE,
    )
    def cleanup_old_articles() -> dict[str, object]:
        """Remove raw articles published more than 90 days ago."""
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    PROJECT_ROOT
                    / "maintenance_scripts"
                    / "cleanup_old_articles.py"
                ),
                "--project-root",
                str(PROJECT_ROOT),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        completed.check_returncode()
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Retention script returned invalid JSON") from exc

    @task(execution_timeout=timedelta(minutes=30))
    def build_dbt_models(_: dict[str, object]) -> None:
        """Build and test every dbt layer after all sources are fetched."""
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
                "--select",
                *DBT_NEWS_SELECTION,
                "--no-use-colors",
            ]
        )
        if not result.success:
            raise RuntimeError("dbt build failed") from result.exception

    def create_fetch_tasks(jobs: tuple[FetchJob, ...]):
        return [
            fetch_source.override(task_id=f"fetch_{job.name}")(
                script=job.script,
                database=job.database,
                output=job.output,
                limit=job.fetch_limit,
                extra_args=list(job.extra_args),
            )
            for job in jobs
        ]

    # Keep prefixes out of task IDs so the seven existing WHO task histories
    # remain attached while the Airflow UI still groups tasks by domain.
    @task_group(group_id="who", prefix_group_id=False)
    def fetch_who_sources():
        return create_fetch_tasks(WHO_FETCH_JOBS)

    @task_group(group_id="tech", prefix_group_id=False)
    def fetch_tech_sources():
        return create_fetch_tasks(TECH_FETCH_JOBS)

    @task_group(group_id="economic", prefix_group_id=False)
    def fetch_economic_sources():
        return create_fetch_tasks(ECONOMIC_FETCH_JOBS)

    fetched_databases = [
        *fetch_who_sources(),
        *fetch_tech_sources(),
        *fetch_economic_sources(),
    ]
    retention_report = cleanup_old_articles()
    dbt_build = build_dbt_models(retention_report)
    for fetched_database in fetched_databases:
        # Cleanup runs daily after every fetch attempt. dbt still requires both
        # successful fetches and a successful cleanup, so it cannot build a
        # partial refresh when one source fails.
        fetched_database >> retention_report
        fetched_database >> dbt_build


who_news_pipeline()
