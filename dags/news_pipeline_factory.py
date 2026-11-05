"""Shared Airflow task factory for the independent news ingestion DAGs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import TriggerRule, dag, get_current_context, task

from news_pipeline_config import FetchJob, build_fetch_command

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(
    os.environ.get("WHO_NEWS_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)
).resolve()
PIPELINE_RUN_ID_ENV = "NEWS_PIPELINE_RUN_ID"
PIPELINE_ATTEMPT_ENV = "NEWS_PIPELINE_ATTEMPT"
SOURCE_DAG_SCHEDULE = "0 6 * * *"
RETENTION_TARGET_NAMES = frozenset({"who_news", "tech_news", "economic_news"})


def audit_subprocess_environment() -> dict[str, str]:
    """Pass the current Airflow run identity to a source subprocess."""
    context = get_current_context()
    environment = os.environ.copy()
    environment[PIPELINE_RUN_ID_ENV] = str(context["run_id"])
    task_instance = context.get("task_instance") or context.get("ti")
    try_number = getattr(task_instance, "try_number", None)
    if isinstance(try_number, int) and try_number > 0:
        environment[PIPELINE_ATTEMPT_ENV] = str(try_number)
    else:
        environment.pop(PIPELINE_ATTEMPT_ENV, None)
    return environment


def create_ingestion_dag(
    *,
    dag_id: str,
    description: str,
    jobs: tuple[FetchJob, ...],
    retention_targets: tuple[str, ...],
    tags: list[str],
):
    """Create one independently scheduled source-ingestion DAG."""
    if not retention_targets:
        raise ValueError("an ingestion DAG must own a retention target")
    invalid_targets = set(retention_targets) - RETENTION_TARGET_NAMES
    if invalid_targets:
        raise ValueError(
            "unknown retention target(s): " + ", ".join(sorted(invalid_targets))
        )
    source_names = {job.source_name for job in jobs}
    unrelated_targets = set(retention_targets) - source_names
    if unrelated_targets:
        raise ValueError(
            "retention target(s) are not owned by this DAG: "
            + ", ".join(sorted(unrelated_targets))
        )

    @dag(
        dag_id=dag_id,
        description=description,
        schedule=SOURCE_DAG_SCHEDULE,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        catchup=False,
        max_active_runs=1,
        default_args={
            "retries": 2,
            "retry_delay": timedelta(minutes=5),
        },
        tags=tags,
    )
    def ingestion_pipeline():
        @task(execution_timeout=timedelta(minutes=15))
        def fetch_source(
            source_name: str,
            script: str,
            database: str,
            output: str,
            table: str,
            date_column: str | None,
            limit: int,
            extra_args: list[str],
        ) -> str:
            """Fetch one source into its raw SQLite database."""
            job = FetchJob(
                name="runtime",
                source_name=source_name,
                script=script,
                database=database,
                output=output,
                table=table,
                date_column=date_column,
                fetch_limit=limit,
                extra_args=tuple(extra_args),
            )
            subprocess.run(
                build_fetch_command(job, PROJECT_ROOT, sys.executable),
                cwd=PROJECT_ROOT,
                check=True,
                env=audit_subprocess_environment(),
            )
            return str(PROJECT_ROOT / database)

        @task(
            execution_timeout=timedelta(minutes=5),
            trigger_rule=TriggerRule.ALL_DONE,
        )
        def cleanup_old_articles() -> dict[str, object]:
            """Apply retention only to the database owned by this DAG."""
            command = [
                sys.executable,
                str(PROJECT_ROOT / "maintenance_scripts" / "cleanup_old_articles.py"),
                "--project-root",
                str(PROJECT_ROOT),
            ]
            for target_name in retention_targets:
                command.extend(("--target", target_name))

            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                env=audit_subprocess_environment(),
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

        @task
        def complete_ingestion() -> None:
            """Keep any failed fetch or cleanup visible in the DAG result."""

        fetched_databases = [
            fetch_source.override(task_id=f"fetch_{job.name}")(
                source_name=job.source_name,
                script=job.script,
                database=job.database,
                output=job.output,
                table=job.table,
                date_column=job.date_column,
                limit=job.fetch_limit,
                extra_args=list(job.extra_args),
            )
            for job in jobs
        ]
        retention_report = cleanup_old_articles()
        completion = complete_ingestion()
        retention_report >> completion
        for fetched_database in fetched_databases:
            # Retention still runs after a failed fetch attempt so its audit row
            # can record cleanup metrics. No other domain is touched here.
            fetched_database >> retention_report
            fetched_database >> completion

    return ingestion_pipeline()
