"""Airflow DAG for Hacker News technology stories."""

from news_pipeline_config import TECH_FETCH_JOBS
from news_pipeline_factory import create_ingestion_dag

tech_news_pipeline = create_ingestion_dag(
    dag_id="tech_news_pipeline",
    description="Fetch and retain Hacker News technology stories independently.",
    jobs=TECH_FETCH_JOBS,
    retention_targets=("tech_news",),
    tags=["tech", "news", "ingestion"],
)
