import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from maintenance_scripts.cleanup_old_articles import (
    DEFAULT_RETENTION_DAYS,
    RETENTION_TARGETS,
    RetentionError,
    RetentionTarget,
    calculate_cutoff,
    cleanup_old_articles,
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

    def test_deletes_only_rows_strictly_older_than_90_days(self):
        rows = [
            ("old", "2026-07-18T11:59:59Z"),
            ("old-offset", "2026-07-18T13:59:59+02:00"),
            ("boundary", "2026-07-18T12:00:00+00:00"),
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
                        for row in connection.execute(
                            f"SELECT id FROM {target.table}"
                        )
                    }

        self.assertEqual(report["retention_days"], 90)
        self.assertEqual(report["cutoff_utc"], "2026-07-18T12:00:00Z")
        self.assertEqual(report["eligible_total"], 6)
        self.assertEqual(report["deleted_total"], 6)
        for result in report["databases"]:
            self.assertEqual(result["eligible"], 2)
            self.assertEqual(result["deleted"], 2)
            self.assertEqual(result["remaining"], 4)
            self.assertEqual(result["invalid_or_missing_dates"], 2)
        for retained in retained_by_database.values():
            self.assertEqual(
                retained,
                {"boundary", "new", "missing", "invalid"},
            )

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
        self.assertEqual(report["eligible_total"], 3)
        self.assertEqual(report["deleted_total"], 0)
        self.assertEqual(counts, [1, 1, 1])

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
        self.assertEqual(
            calculate_cutoff(as_of=AS_OF),
            datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValueError):
            calculate_cutoff(as_of=AS_OF, retention_days=0)


if __name__ == "__main__":
    unittest.main()
