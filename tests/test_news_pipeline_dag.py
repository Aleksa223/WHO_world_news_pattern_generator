import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = PROJECT_ROOT / "dags"
sys.path.insert(0, str(DAGS_DIR))


@unittest.skipIf(os.name == "nt", "Airflow runtime imports require Linux")
class NewsPipelineDagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from airflow.models import DagBag

        cls.dag_bag = DagBag(dag_folder=str(DAGS_DIR), include_examples=False)
        cls.dags = {
            dag_id: cls.dag_bag.get_dag(dag_id)
            for dag_id in (
                "who_news_pipeline",
                "tech_news_pipeline",
                "economic_news_pipeline",
                "news_warehouse_pipeline",
            )
        }

    def test_all_dags_import_without_errors(self):
        self.assertEqual(self.dag_bag.import_errors, {})
        self.assertTrue(all(self.dags.values()))
        self.assertEqual(set(self.dag_bag.dags), set(self.dags))

    def test_source_dags_are_independent_daily_runs(self):
        expected_fetch_tasks = {
            "who_news_pipeline": {
                "fetch_news",
                "fetch_campaigns",
                "fetch_commentaries",
                "fetch_events",
                "fetch_speeches",
                "fetch_statements",
                "fetch_stories",
            },
            "tech_news_pipeline": {"fetch_tech_news"},
            "economic_news_pipeline": {"fetch_economic_news"},
        }

        for dag_id, fetch_task_ids in expected_fetch_tasks.items():
            with self.subTest(dag_id=dag_id):
                source_dag = self.dags[dag_id]
                self.assertEqual(source_dag.schedule, "0 6 * * *")
                self.assertFalse(source_dag.catchup)
                self.assertEqual(source_dag.max_active_runs, 1)
                self.assertEqual(
                    set(source_dag.task_ids),
                    fetch_task_ids | {"cleanup_old_articles", "complete_ingestion"},
                )

                cleanup_task = source_dag.get_task("cleanup_old_articles")
                self.assertEqual(cleanup_task.upstream_task_ids, fetch_task_ids)
                self.assertEqual(
                    cleanup_task.downstream_task_ids,
                    {"complete_ingestion"},
                )
                self.assertEqual(cleanup_task.trigger_rule.value, "all_done")

                completion_task = source_dag.get_task("complete_ingestion")
                self.assertEqual(
                    completion_task.upstream_task_ids,
                    fetch_task_ids | {"cleanup_old_articles"},
                )
                self.assertEqual(completion_task.downstream_task_ids, set())
                self.assertEqual(
                    completion_task.trigger_rule.value,
                    "all_success",
                )
                self.assertEqual(
                    [task.task_id for task in source_dag.leaves],
                    ["complete_ingestion"],
                )

                for task_id in fetch_task_ids:
                    task = source_dag.get_task(task_id)
                    self.assertEqual(task.upstream_task_ids, set())
                    self.assertEqual(
                        task.downstream_task_ids,
                        {"cleanup_old_articles", "complete_ingestion"},
                    )
                    self.assertEqual(task.retries, 2)
                    self.assertEqual(
                        task.retry_delay,
                        timedelta(minutes=5),
                    )

    def test_warehouse_build_is_separate_and_serialized(self):
        warehouse_dag = self.dags["news_warehouse_pipeline"]

        self.assertEqual(warehouse_dag.schedule, "0 8 * * *")
        self.assertFalse(warehouse_dag.catchup)
        self.assertEqual(warehouse_dag.max_active_runs, 1)
        self.assertEqual(warehouse_dag.task_ids, ["build_dbt_models"])
        build_task = warehouse_dag.get_task("build_dbt_models")
        self.assertEqual(build_task.upstream_task_ids, set())
        self.assertEqual(build_task.downstream_task_ids, set())

    def test_factory_rejects_unsafe_retention_scope(self):
        from news_pipeline_config import TECH_FETCH_JOBS
        from news_pipeline_factory import create_ingestion_dag

        base_arguments = {
            "dag_id": "invalid_test_pipeline",
            "description": "not registered",
            "jobs": TECH_FETCH_JOBS,
            "tags": ["test"],
        }
        with self.assertRaisesRegex(ValueError, "must own a retention target"):
            create_ingestion_dag(
                **base_arguments,
                retention_targets=(),
            )
        with self.assertRaisesRegex(ValueError, "not owned by this DAG"):
            create_ingestion_dag(
                **base_arguments,
                retention_targets=("economic_news",),
            )


if __name__ == "__main__":
    unittest.main()
