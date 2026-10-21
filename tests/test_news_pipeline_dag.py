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
        cls.dag = cls.dag_bag.get_dag("who_news_pipeline")

    def test_dag_imports_without_errors(self):
        self.assertEqual(self.dag_bag.import_errors, {})
        self.assertIsNotNone(self.dag)

    def test_dag_keeps_daily_single_run_configuration(self):
        self.assertEqual(self.dag.schedule, "0 6 * * *")
        self.assertFalse(self.dag.catchup)
        self.assertEqual(self.dag.max_active_runs, 1)

    def test_all_fetches_must_finish_before_dbt(self):
        fetch_task_ids = {
            "fetch_news",
            "fetch_campaigns",
            "fetch_commentaries",
            "fetch_events",
            "fetch_speeches",
            "fetch_statements",
            "fetch_stories",
            "fetch_tech_news",
            "fetch_economic_news",
        }
        expected_task_ids = fetch_task_ids | {
            "cleanup_old_articles",
            "build_dbt_models",
        }

        self.assertEqual(set(self.dag.task_ids), expected_task_ids)
        cleanup_task = self.dag.get_task("cleanup_old_articles")
        build_task = self.dag.get_task("build_dbt_models")
        self.assertEqual(cleanup_task.upstream_task_ids, fetch_task_ids)
        self.assertEqual(cleanup_task.downstream_task_ids, {"build_dbt_models"})
        self.assertEqual(cleanup_task.trigger_rule.value, "all_done")
        self.assertEqual(
            build_task.upstream_task_ids,
            fetch_task_ids | {"cleanup_old_articles"},
        )
        for task_id in fetch_task_ids:
            task = self.dag.get_task(task_id)
            self.assertEqual(task.upstream_task_ids, set())
            self.assertEqual(
                task.downstream_task_ids,
                {"cleanup_old_articles", "build_dbt_models"},
            )
            self.assertEqual(task.retries, 2)
            self.assertEqual(task.retry_delay, timedelta(minutes=5))


if __name__ == "__main__":
    unittest.main()
