import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from maintenance_scripts.ingestion_audit import (
    AUDIT_TABLE,
    AuditTarget,
    IngestionAuditError,
    apply_retention_audit,
    begin_ingestion_audit,
    snapshot_all_sources,
)


AS_OF = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
ARTICLE_TARGET = AuditTarget("who_news", "articles", "published_at")


def create_articles(database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE TABLE articles (id TEXT PRIMARY KEY, published_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO articles (id, published_at) VALUES (?, ?)",
            [
                ("old", "2026-01-01T00:00:00Z"),
                ("today", "2026-10-28T08:00:00Z"),
                ("invalid", "not-a-date"),
            ],
        )


def read_audit(database: Path, audit_id: str) -> sqlite3.Row:
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            f"SELECT * FROM {AUDIT_TABLE} WHERE audit_id = ?",
            (audit_id,),
        ).fetchone()
    if row is None:
        raise AssertionError(f"audit row {audit_id!r} does not exist")
    return row


class IngestionAuditTests(unittest.TestCase):
    def test_successful_run_records_changes_and_source_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "articles.db"
            create_articles(database)
            audit = begin_ingestion_audit(
                database,
                ARTICLE_TARGET,
                requested_limit=200,
                pipeline_run_id="scheduled__2026-10-28",
                attempt_number=2,
                now=AS_OF,
            )
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "INSERT INTO articles (id, published_at) VALUES (?, ?)",
                    ("new", "2026-10-28T09:00:00Z"),
                )
            audit.set_changes(new_rows=1, refreshed_rows=1, selected_rows=2)
            audit.succeed(now=AS_OF + timedelta(minutes=1))

            row = read_audit(database, audit.audit_id)

        self.assertEqual(row["status"], "succeeded")
        self.assertEqual(row["pipeline_run_id"], "scheduled__2026-10-28")
        self.assertEqual(row["attempt_number"], 2)
        self.assertEqual(row["requested_limit"], 200)
        self.assertEqual(row["selected_rows"], 2)
        self.assertEqual(row["new_rows"], 1)
        self.assertEqual(row["refreshed_rows"], 1)
        self.assertEqual(row["deleted_rows"], 0)
        self.assertEqual(row["total_rows"], 4)
        self.assertEqual(row["oldest_published_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(row["newest_published_at"], "2026-10-28T09:00:00Z")
        self.assertEqual(row["published_today_rows"], 2)
        self.assertEqual(row["metric_date_utc"], "2026-10-28")
        self.assertIsNone(row["error_type"])
        self.assertIsNotNone(row["completed_at"])

    def test_context_records_failure_and_preserves_the_source_exception(self):
        class FetchFailure(RuntimeError):
            pass

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "articles.db"
            create_articles(database)
            audit = begin_ingestion_audit(
                database,
                ARTICLE_TARGET,
                pipeline_run_id="failed-run",
                now=AS_OF,
            )
            with self.assertRaises(FetchFailure):
                with audit:
                    raise FetchFailure("upstream\n unavailable")

            row = read_audit(database, audit.audit_id)

        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error_type"], "FetchFailure")
        self.assertEqual(row["error_message"], "upstream unavailable")
        self.assertIsNotNone(row["completed_at"])

    def test_source_without_publication_date_keeps_date_metrics_null(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "campaigns.db"
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("CREATE TABLE campaigns (id TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO campaigns (id) VALUES ('one')")
            audit = begin_ingestion_audit(
                database,
                AuditTarget("who_campaigns", "campaigns", None),
                pipeline_run_id="campaign-run",
                now=AS_OF,
            )
            audit.set_changes(new_rows=1, refreshed_rows=0, selected_rows=1)
            audit.succeed(now=AS_OF)

            row = read_audit(database, audit.audit_id)

        self.assertEqual(row["total_rows"], 1)
        self.assertIsNone(row["oldest_published_at"])
        self.assertIsNone(row["newest_published_at"])
        self.assertIsNone(row["published_today_rows"])

    def test_retention_metrics_update_the_matching_run_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "articles.db"
            create_articles(database)
            audit = begin_ingestion_audit(
                database,
                ARTICLE_TARGET,
                pipeline_run_id="retention-run",
                now=AS_OF,
            )
            audit.set_changes(new_rows=0, refreshed_rows=3, selected_rows=3)
            audit.succeed(now=AS_OF)

            with closing(sqlite3.connect(database)) as connection, connection:
                deleted = connection.execute(
                    "DELETE FROM articles WHERE id = 'old'"
                ).rowcount
                apply_retention_audit(
                    connection,
                    pipeline_run_id="retention-run",
                    target=ARTICLE_TARGET,
                    deleted_rows=deleted,
                    retention_days=365,
                    cutoff_utc="2025-10-28T12:00:00Z",
                    as_of=AS_OF,
                )

            row = read_audit(database, audit.audit_id)

        self.assertEqual(row["deleted_rows"], 1)
        self.assertEqual(row["total_rows"], 2)
        self.assertEqual(row["oldest_published_at"], "2026-10-28T08:00:00Z")
        self.assertEqual(row["retention_days"], 365)
        self.assertEqual(row["retention_cutoff_utc"], "2025-10-28T12:00:00Z")

    def test_snapshot_bootstraps_configured_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            database = project_root / "raw" / "articles.db"
            create_articles(database)
            jobs = (
                SimpleNamespace(
                    database="raw/articles.db",
                    source_name="who_news",
                    table="articles",
                    date_column="published_at",
                ),
            )
            with patch(
                "maintenance_scripts.ingestion_audit._configured_jobs",
                return_value=jobs,
            ):
                report = snapshot_all_sources(
                    project_root,
                    pipeline_run_id="bootstrap",
                    now=AS_OF,
                )

            row = report["sources"][0]

        self.assertEqual(report["pipeline_run_id"], "bootstrap")
        self.assertEqual(row["status"], "snapshot")
        self.assertEqual(row["source_name"], "who_news")
        self.assertEqual(row["total_rows"], 3)
        self.assertEqual(row["published_today_rows"], 1)

    def test_rejects_unsafe_identifiers_and_missing_audit_links(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "articles.db"
            create_articles(database)
            with self.assertRaises(IngestionAuditError):
                begin_ingestion_audit(
                    database,
                    AuditTarget("broken", "articles; DROP TABLE articles"),
                    now=AS_OF,
                )
            with closing(sqlite3.connect(database)) as connection, connection:
                with self.assertRaises(IngestionAuditError):
                    apply_retention_audit(
                        connection,
                        pipeline_run_id="missing",
                        target=ARTICLE_TARGET,
                        deleted_rows=0,
                        retention_days=365,
                        cutoff_utc="2025-10-28T12:00:00Z",
                        as_of=AS_OF,
                    )


if __name__ == "__main__":
    unittest.main()
