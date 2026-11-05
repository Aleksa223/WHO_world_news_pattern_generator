"""Airflow DAG for the shared dbt warehouse and snapshot build."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task

from news_pipeline_config import DBT_NEWS_SELECTION
from news_pipeline_factory import PROJECT_ROOT


@dag(
    dag_id="news_warehouse_pipeline",
    description="Build and test the shared news warehouse after source ingestion.",
    schedule="0 8 * * *",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["who", "tech", "economic", "news", "dbt", "warehouse"],
)
def build_news_warehouse():
    @task(execution_timeout=timedelta(minutes=30))
    def build_dbt_models() -> None:
        """Build and test every dbt layer in one serialized process."""
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

    build_dbt_models()


news_warehouse_pipeline = build_news_warehouse()
