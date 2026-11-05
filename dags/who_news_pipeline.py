"""Airflow DAG for the seven WHO news sources."""

from news_pipeline_config import WHO_FETCH_JOBS
from news_pipeline_factory import create_ingestion_dag

who_news_pipeline = create_ingestion_dag(
    dag_id="who_news_pipeline",
    description="Fetch and retain the seven WHO news sources independently.",
    jobs=WHO_FETCH_JOBS,
    retention_targets=("who_news",),
    tags=["who", "news", "ingestion"],
)
