import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = PROJECT_ROOT / "dags"
sys.path.insert(0, str(DAGS_DIR))

from news_pipeline_config import (  # noqa: E402
    ALL_FETCH_JOBS,
    DAILY_FETCH_LIMIT,
    DBT_NEWS_SELECTION,
    ECONOMIC_FETCH_JOBS,
    TECH_FETCH_JOBS,
    WHO_FETCH_JOBS,
    build_fetch_command,
)


class NewsPipelineConfigTests(unittest.TestCase):
    def test_all_daily_fetch_jobs_are_configured(self):
        self.assertEqual(len(WHO_FETCH_JOBS), 7)
        self.assertEqual(len(TECH_FETCH_JOBS), 1)
        self.assertEqual(len(ECONOMIC_FETCH_JOBS), 1)
        self.assertEqual(
            {job.name for job in ALL_FETCH_JOBS},
            {
                "news",
                "campaigns",
                "commentaries",
                "events",
                "speeches",
                "statements",
                "stories",
                "tech_news",
                "economic_news",
            },
        )
        self.assertEqual(DAILY_FETCH_LIMIT, 200)
        self.assertTrue(
            all(job.fetch_limit == DAILY_FETCH_LIMIT for job in ALL_FETCH_JOBS)
        )

    def test_fetch_jobs_have_unique_outputs_and_existing_scripts(self):
        databases = [job.database for job in ALL_FETCH_JOBS]
        outputs = [job.output for job in ALL_FETCH_JOBS]
        source_names = [job.source_name for job in ALL_FETCH_JOBS]

        self.assertEqual(len(databases), len(set(databases)))
        self.assertEqual(len(outputs), len(set(outputs)))
        self.assertEqual(len(source_names), len(set(source_names)))
        for job in ALL_FETCH_JOBS:
            self.assertTrue((PROJECT_ROOT / job.script).is_file(), job.script)

    def test_fetch_jobs_define_their_audit_source_contracts(self):
        self.assertEqual(
            {
                job.name: (job.source_name, job.table, job.date_column)
                for job in ALL_FETCH_JOBS
            },
            {
                "news": ("who_news", "articles", "published_at"),
                "campaigns": ("who_campaigns", "campaigns", None),
                "commentaries": (
                    "who_commentaries",
                    "commentaries",
                    "published_at",
                ),
                "events": ("who_events", "events", None),
                "speeches": ("who_speeches", "speeches", "published_at"),
                "statements": (
                    "who_statements",
                    "statements",
                    "published_at",
                ),
                "stories": ("who_stories", "feature_stories", "published_at"),
                "tech_news": ("tech_news", "tech_articles", "published_at"),
                "economic_news": (
                    "economic_news",
                    "economic_articles",
                    "published_at",
                ),
            },
        )

    def test_fetch_commands_use_absolute_project_paths(self):
        for job in ALL_FETCH_JOBS:
            command = build_fetch_command(job, PROJECT_ROOT, "python-for-test")

            self.assertEqual(command[0], "python-for-test")
            self.assertEqual(command[1], str(PROJECT_ROOT / job.script))
            self.assertEqual(command[2:4], ["--limit", "200"])
            self.assertEqual(
                command[command.index("--database") + 1],
                str(PROJECT_ROOT / job.database),
            )
            self.assertEqual(
                command[command.index("--output") + 1],
                str(PROJECT_ROOT / job.output),
            )
            self.assertNotIn("--watch", command)

    def test_tech_and_economic_fetches_are_safe_one_shot_commands(self):
        tech_command = build_fetch_command(
            TECH_FETCH_JOBS[0], PROJECT_ROOT, "python-for-test"
        )
        economic_command = build_fetch_command(
            ECONOMIC_FETCH_JOBS[0], PROJECT_ROOT, "python-for-test"
        )

        self.assertEqual(tech_command[-4:], ["--timeout", "30", "--workers", "16"])
        self.assertEqual(
            economic_command[-4:], ["--timespan", "1d", "--timeout", "30"]
        )
        self.assertNotIn("--translate", economic_command)
        self.assertNotIn("--watch", economic_command)

    def test_dbt_selection_refreshes_every_domain(self):
        self.assertEqual(
            DBT_NEWS_SELECTION,
            (
                "path:staging",
                "path:intermediate",
                "path:marts",
                "path:seeds",
                "path:snapshots",
            ),
        )


if __name__ == "__main__":
    unittest.main()
