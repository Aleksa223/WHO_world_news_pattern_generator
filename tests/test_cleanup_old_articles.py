import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from maintenance_scripts.cleanup_old_articles import (
    DEFAULT_RETENTION_DAYS,
    RETENTION_TARGETS,
    WHO_NEWS_RETENTION_DAYS,
    RetentionError,
    RetentionTarget,
    calculate_cutoff,
    cleanup_old_articles,
    main,
)
from maintenance_scripts.ingestion_audit import (
    AUDIT_TABLE,
    AuditTarget,
    begin_ingestion_audit,
)

AS_OF = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


def create_target_database(
    project_root: Path,
    target: RetentionTarget,
    rows: list[tuple[str, str | None]],
) -> Path:
    database = project_root / target.database
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            f"CREATE TABLE {target.table} "
            f"(id TEXT PRIMARY KEY, {target.date_column} TEXT)"
        )
        connection.executemany(
            f"INSERT INTO {target.table} (id, {target.date_column}) VALUES (?, ?)",
            rows,
        )
    return database


class CleanupOldArticlesTests(unittest.TestCase):
    def test_targets_only_the_three_requested_article_databases(self):
        self.assertEqual(
            {target.database for target in RETENTION_TARGETS},
            {
                "articles/who_news.db",
                "tech_articles/tech_news.db",
                "economic_articles/economic_news.db",
            },
        )
        self.assertTrue(
            all(target.date_column == "published_at" for target in RETENTION_TARGETS)
        )
        self.assertEqual(
            {target.name: target.retention_days for target in RETENTION_TARGETS},
            {
                "who_news": 365,
                "tech_news": 90,
                "economic_news": 90,
            },
        )

    def test_applies_who_one_year_and_other_sources_ninety_days(self):
        rows = [
            ("older-than-year", "2025-10-16T11:59:59Z"),
            ("year-boundary", "2025-10-16T12:00:00+00:00"),
            ("between-90-and-365", "2026-01-01T00:00:00Z"),
            ("older-than-90-offset", "2026-07-18T13:59:59+02:00"),
            ("ninety-day-boundary", "2026-07-18T12:00:00Z"),
            ("new", "2026-07-18T12:00:01Z"),
            ("missing", None),
            ("invalid", "not-a-date"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            for target in RETENTION_TARGETS:
                create_target_database(project_root, target, rows)

            report = cleanup_old_articles(project_root, as_of=AS_OF)

            retained_by_database = {}
            for target in RETENTION_TARGETS:
                with closing(
                    sqlite3.connect(project_root / target.database)
                ) as connection:
                    retained_by_database[target.name] = {
                        row[0]
                        for row in connection.execute(f"SELECT id FROM {target.table}")
                    }

        self.assertIsNone(report["retention_days_override"])
        self.assertEqual(report["eligible_total"], 9)
        self.assertEqual(report["deleted_total"], 9)

        results = {result["name"]: result for result in report["databases"]}
        self.assertEqual(results["who_news"]["retention_days"], 365)
        self.assertEqual(
            results["who_news"]["cutoff_utc"],
            "2025-10-16T12:00:00Z",
        )
        self.assertEqual(results["who_news"]["eligible"], 1)
        self.assertEqual(results["who_news"]["deleted"], 1)
        self.assertEqual(results["who_news"]["remaining"], 7)

        for name in ("tech_news", "economic_news"):
            self.assertEqual(results[name]["retention_days"], 90)
            self.assertEqual(
                results[name]["cutoff_utc"],
                "2026-07-18T12:00:00Z",
            )
            self.assertEqual(results[name]["eligible"], 4)
            self.assertEqual(results[name]["deleted"], 4)
            self.assertEqual(results[name]["remaining"], 4)

        for result in report["databases"]:
            self.assertEqual(result["invalid_or_missing_dates"], 2)

        self.assertEqual(
            retained_by_database["who_news"],
            {
                "year-boundary",
                "between-90-and-365",
                "older-than-90-offset",
                "ninety-day-boundary",
                "new",
                "missing",
                "invalid",
            },
        )
        for name in ("tech_news", "economic_news"):
            self.assertEqual(
                retained_by_database[name],
                {"ninety-day-boundary", "new", "missing", "invalid"},
            )

    def test_explicit_retention_override_applies_to_every_target(self):
        rows = [
            ("old", "2026-09-15T23:59:59Z"),
            ("boundary", "2026-09-16T12:00:00Z"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            for target in RETENTION_TARGETS:
                create_target_database(project_root, target, rows)

            report = cleanup_old_articles(
                project_root,
                as_of=AS_OF,
                retention_days=30,
            )

        self.assertEqual(report["retention_days_override"], 30)
        self.assertEqual(report["eligible_total"], 3)
        for result in report["databases"]:
            self.assertEqual(result["retention_days"], 30)
            self.assertEqual(result["cutoff_utc"], "2026-09-16T12:00:00Z")

    def test_dry_run_reports_candidates_without_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            for target in RETENTION_TARGETS:
                create_target_database(
                    project_root,
                    target,
                    [("old", "2020-01-01T00:00:00Z")],
                )

            report = cleanup_old_articles(
                project_root,
                as_of=AS_OF,
                dry_run=True,
                pipeline_run_id="dry-run-without-audit",
            )

            counts = []
            for target in RETENTION_TARGETS:
                with closing(
                    sqlite3.connect(project_root / target.database)
                ) as connection:
                    counts.append(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {target.table}"
                        ).fetchone()[0]
                    )

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["pipeline_run_id"], "dry-run-without-audit")
        self.assertEqual(report["eligible_total"], 3)
        self.assertEqual(report["deleted_total"], 0)
        self.assertEqual(counts, [1, 1, 1])

    def test_cli_target_limits_cleanup_to_one_source(self):
        tech_target = next(
            target for target in RETENTION_TARGETS if target.name == "tech_news"
        )
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            create_target_database(
                project_root,
                tech_target,
                [("old", "2020-01-01T00:00:00Z")],
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--project-root",
                        str(project_root),
                        "--target",
                        "tech_news",
                        "--as-of",
                        "2026-10-16T12:00:00Z",
                        "--dry-run",
                    ]
                )

            report = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            [database["name"] for database in report["databases"]],
            ["tech_news"],
        )
        self.assertEqual(report["eligible_total"], 1)

    def test_retention_updates_the_matching_ingestion_audit(self):
        target = RetentionTarget(
            name="who_news",
            database="articles/who_news.db",
            table="articles",
            retention_days=365,
        )
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            database = create_target_database(
                project_root,
                target,
                [
                    ("old", "2020-01-01T00:00:00Z"),
                    ("current", "2026-10-28T08:00:00Z"),
                ],
            )
            audit = begin_ingestion_audit(
                database,
                AuditTarget("who_news", "articles", "published_at"),
                pipeline_run_id="airflow-run",
                now=AS_OF,
            )
            audit.set_changes(new_rows=1, refreshed_rows=1, selected_rows=2)
            audit.succeed(now=AS_OF)

            report = cleanup_old_articles(
                project_root,
                as_of=AS_OF,
                pipeline_run_id="airflow-run",
                targets=(target,),
            )
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    f"SELECT deleted_rows, total_rows, retention_days, "
                    f"retention_cutoff_utc FROM {AUDIT_TABLE} "
                    "WHERE audit_id = ?",
                    (audit.audit_id,),
                ).fetchone()

        self.assertEqual(report["pipeline_run_id"], "airflow-run")
        self.assertEqual(report["deleted_total"], 1)
        self.assertEqual(
            row,
            (1, 1, 365, "2025-10-16T12:00:00Z"),
        )

    def test_missing_audit_link_rolls_back_retention_deletion(self):
        target = RetentionTarget(
            name="who_news",
            database="articles/who_news.db",
            table="articles",
            retention_days=365,
        )
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            database = create_target_database(
                project_root,
                target,
                [("old", "2020-01-01T00:00:00Z")],
            )

            with self.assertRaises(RetentionError):
                cleanup_old_articles(
                    project_root,
                    as_of=AS_OF,
                    pipeline_run_id="missing-run",
                    targets=(target,),
                )
            with closing(sqlite3.connect(database)) as connection:
                remaining = connection.execute(
                    "SELECT COUNT(*) FROM articles"
                ).fetchone()[0]

        self.assertEqual(remaining, 1)

    def test_preflight_failure_does_not_delete_or_create_databases(self):
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            who_target, tech_target, economic_target = RETENTION_TARGETS
            who_database = create_target_database(
                project_root,
                who_target,
                [("old", "2020-01-01T00:00:00Z")],
            )
            create_target_database(project_root, tech_target, [])
            missing_database = project_root / economic_target.database

            with self.assertRaises(RetentionError):
                cleanup_old_articles(project_root, as_of=AS_OF)

            with closing(sqlite3.connect(who_database)) as connection:
                who_count = connection.execute(
                    f"SELECT COUNT(*) FROM {who_target.table}"
                ).fetchone()[0]

        self.assertEqual(who_count, 1)
        self.assertFalse(missing_database.exists())

    def test_preflight_rejects_a_missing_date_column(self):
        target = RetentionTarget(
            name="broken",
            database="raw/broken.db",
            table="articles",
        )
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            database = project_root / target.database
            database.parent.mkdir(parents=True)
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("CREATE TABLE articles (id TEXT PRIMARY KEY)")

            with self.assertRaises(RetentionError):
                cleanup_old_articles(
                    project_root,
                    as_of=AS_OF,
                    targets=(target,),
                )

    def test_rejects_non_positive_retention_periods(self):
        self.assertEqual(DEFAULT_RETENTION_DAYS, 90)
        self.assertEqual(WHO_NEWS_RETENTION_DAYS, 365)
        self.assertEqual(
            calculate_cutoff(as_of=AS_OF),
            datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValueError):
            calculate_cutoff(as_of=AS_OF, retention_days=0)


if __name__ == "__main__":
    unittest.main()
