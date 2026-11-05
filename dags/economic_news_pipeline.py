"""Airflow DAG for GDELT economic news."""

from news_pipeline_config import ECONOMIC_FETCH_JOBS
from news_pipeline_factory import create_ingestion_dag

economic_news_pipeline = create_ingestion_dag(
    dag_id="economic_news_pipeline",
    description="Fetch and retain GDELT economic news independently.",
    jobs=ECONOMIC_FETCH_JOBS,
    retention_targets=("economic_news",),
    tags=["economic", "news", "ingestion"],
)
