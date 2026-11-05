import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _dbt_executable() -> str | None:
    candidates = (
        PROJECT_ROOT / "venv" / "Scripts" / "dbt.exe",
        PROJECT_ROOT / "venv" / "bin" / "dbt",
        PROJECT_ROOT / ".venv" / "Scripts" / "dbt.exe",
        PROJECT_ROOT / ".venv" / "bin" / "dbt",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("dbt")


DBT_EXECUTABLE = _dbt_executable()


@unittest.skipIf(DBT_EXECUTABLE is None, "dbt executable is not installed")
class DbtSnapshotIntegrationTests(unittest.TestCase):
    def _create_sources(self, root: Path) -> tuple[Path, Path]:
        tech_database = root / "tech.db"
        economic_database = root / "economic.db"

        with closing(sqlite3.connect(tech_database)) as connection:
            connection.execute(
                """
                CREATE TABLE tech_articles (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    keywords TEXT,
                    snippet TEXT,
                    url TEXT,
                    discussion_url TEXT,
                    image_url TEXT,
                    language TEXT,
                    published_at TEXT,
                    source TEXT,
                    author TEXT,
                    score INTEGER,
                    comment_count INTEGER,
                    last_seen_at TEXT
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO tech_articles (
                    id, title, url, discussion_url, language, published_at,
                    source, author, score, comment_count, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        "tech|1",
                        "Initial technology title",
                        "https://example.com/tech/1",
                        "https://news.ycombinator.com/item?id=1",
                        "en",
                        "2026-11-04T08:00:00+00:00",
                        "example.com",
                        "alice",
                        10,
                        2,
                        "2026-11-04T09:00:00+00:00",
                    ),
                    (
                        "tech|2",
                        "Unchanged technology title",
                        "https://example.com/tech/2",
                        "https://news.ycombinator.com/item?id=2",
                        "en",
                        "2026-11-04T08:30:00+00:00",
                        "example.com",
                        "bob",
                        5,
                        1,
                        "2026-11-04T09:00:00+00:00",
                    ),
                ),
            )
            connection.commit()

        with closing(sqlite3.connect(economic_database)) as connection:
            connection.execute(
                """
                CREATE TABLE economic_articles (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    title_original TEXT,
                    title_english TEXT,
                    translation_source_language TEXT,
                    translation_status TEXT,
                    translation_provider TEXT,
                    translated_at TEXT,
                    description TEXT,
                    keywords TEXT,
                    snippet TEXT,
                    mobile_url TEXT,
                    image_url TEXT,
                    language TEXT,
                    published_at TEXT,
                    gdelt_seen_at TEXT,
                    gdelt_seen_date TEXT,
                    source TEXT,
                    source_country TEXT,
                    last_seen_at TEXT
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO economic_articles (
                    id, title, title_original, translation_status, language,
                    published_at, gdelt_seen_at, gdelt_seen_date, source,
                    source_country, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        "economic|1",
                        "Initial economic title",
                        "Initial economic title",
                        "pending",
                        "en",
                        "2026-11-04T07:00:00+00:00",
                        "2026-11-04T07:05:00+00:00",
                        "20261104T070500Z",
                        "example.org",
                        "US",
                        "2026-11-04T09:00:00+00:00",
                    ),
                    (
                        "economic|2",
                        "Unchanged economic title",
                        "Unchanged economic title",
                        "pending",
                        "en",
                        "2026-11-04T07:30:00+00:00",
                        "2026-11-04T07:35:00+00:00",
                        "20261104T073500Z",
                        "example.net",
                        "GB",
                        "2026-11-04T09:00:00+00:00",
                    ),
                ),
            )
            connection.commit()

        return tech_database, economic_database

    def _write_profile(
        self,
        root: Path,
        tech_database: Path,
        economic_database: Path,
    ) -> Path:
        profiles_directory = root / "profiles"
        profiles_directory.mkdir()
        warehouse = root / "warehouse"
        warehouse.mkdir()
        profile = f"""who_world_news:
  target: test
  outputs:
    test:
      type: sqlite
      threads: 1
      database: analytics
      schema: main
      schemas_and_paths:
        main: {warehouse.joinpath('analytics.db').as_posix()}
        tech_articles: {tech_database.as_posix()}
        economic_articles: {economic_database.as_posix()}
        main_snapshot_history: {warehouse.joinpath('snapshot_history.db').as_posix()}
      schema_directory: {warehouse.as_posix()}
"""
        (profiles_directory / "profiles.yml").write_text(
            profile,
            encoding="utf-8",
        )
        return profiles_directory

    def _run_snapshots(self, root: Path, profiles_directory: Path) -> None:
        environment = os.environ.copy()
        environment["DBT_LOG_PATH"] = str(root / "logs")
        environment["DBT_TARGET_PATH"] = str(root / "target")
        completed = subprocess.run(
            [
                str(DBT_EXECUTABLE),
                "build",
                "--project-dir",
                str(PROJECT_ROOT),
                "--profiles-dir",
                str(profiles_directory),
                "--select",
                "path:snapshots",
                "--no-use-colors",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + "\n" + completed.stderr,
        )

    def _history_counts(self, database: Path, table: str) -> tuple[int, int]:
        with closing(sqlite3.connect(database)) as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN dbt_valid_to IS NULL THEN 1 ELSE 0 END)
                FROM "{table}"
                """
            ).fetchone()
        return int(row[0]), int(row[1] or 0)

    def test_snapshots_ignore_observation_only_updates_and_track_real_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            tech_database, economic_database = self._create_sources(root)
            profiles_directory = self._write_profile(
                root,
                tech_database,
                economic_database,
            )
            history_database = root / "warehouse" / "snapshot_history.db"

            self._run_snapshots(root, profiles_directory)
            self.assertEqual(
                self._history_counts(history_database, "tech_article_history"),
                (2, 2),
            )
            self.assertEqual(
                self._history_counts(
                    history_database,
                    "economic_article_history",
                ),
                (2, 2),
            )

            with closing(sqlite3.connect(tech_database)) as connection:
                connection.execute(
                    "UPDATE tech_articles SET last_seen_at = ?",
                    ("2026-11-05T09:00:00+00:00",),
                )
                connection.commit()
            with closing(sqlite3.connect(economic_database)) as connection:
                connection.execute(
                    "UPDATE economic_articles SET last_seen_at = ?",
                    ("2026-11-05T09:00:00+00:00",),
                )
                connection.commit()

            time.sleep(1.1)
            self._run_snapshots(root, profiles_directory)
            self.assertEqual(
                self._history_counts(history_database, "tech_article_history"),
                (2, 2),
            )
            self.assertEqual(
                self._history_counts(
                    history_database,
                    "economic_article_history",
                ),
                (2, 2),
            )

            with closing(sqlite3.connect(tech_database)) as connection:
                connection.execute(
                    "UPDATE tech_articles "
                    "SET score = 25, comment_count = 4 WHERE id = 'tech|1'"
                )
                connection.commit()
            with closing(sqlite3.connect(economic_database)) as connection:
                connection.execute(
                    """
                    UPDATE economic_articles
                    SET title = 'Translated economic title',
                        title_english = 'Translated economic title',
                        translation_status = 'translated',
                        translation_provider = 'test',
                        translated_at = '2026-11-05T10:00:00+00:00'
                    WHERE id = 'economic|1'
                    """
                )
                connection.commit()

            time.sleep(1.1)
            self._run_snapshots(root, profiles_directory)
            self.assertEqual(
                self._history_counts(history_database, "tech_article_history"),
                (3, 2),
            )
            self.assertEqual(
                self._history_counts(
                    history_database,
                    "economic_article_history",
                ),
                (3, 2),
            )

            with closing(sqlite3.connect(history_database)) as connection:
                tech_versions = connection.execute(
                    """
                    SELECT score, comment_count, dbt_valid_to
                    FROM tech_article_history
                    WHERE id = 'tech|1'
                    ORDER BY dbt_valid_from
                    """
                ).fetchall()
                economic_versions = connection.execute(
                    """
                    SELECT title, translation_status, dbt_valid_to
                    FROM economic_article_history
                    WHERE id = 'economic|1'
                    ORDER BY dbt_valid_from
                    """
                ).fetchall()
            self.assertEqual(
                [(row[0], row[1]) for row in tech_versions],
                [(10, 2), (25, 4)],
            )
            self.assertIsNotNone(tech_versions[0][2])
            self.assertIsNone(tech_versions[1][2])
            self.assertEqual(
                [(row[0], row[1]) for row in economic_versions],
                [
                    ("Initial economic title", "pending"),
                    ("Translated economic title", "translated"),
                ],
            )
            self.assertIsNotNone(economic_versions[0][2])
            self.assertIsNone(economic_versions[1][2])

            with closing(sqlite3.connect(tech_database)) as connection:
                connection.execute("DELETE FROM tech_articles WHERE id = 'tech|1'")
                connection.commit()
            with closing(sqlite3.connect(economic_database)) as connection:
                connection.execute(
                    "DELETE FROM economic_articles WHERE id = 'economic|1'"
                )
                connection.commit()

            time.sleep(1.1)
            self._run_snapshots(root, profiles_directory)
            self.assertEqual(
                self._history_counts(history_database, "tech_article_history"),
                (3, 1),
            )
            self.assertEqual(
                self._history_counts(
                    history_database,
                    "economic_article_history",
                ),
                (3, 1),
            )
            with closing(sqlite3.connect(history_database)) as connection:
                tech_current_ids = connection.execute(
                    "SELECT id FROM tech_article_history "
                    "WHERE dbt_valid_to IS NULL ORDER BY id"
                ).fetchall()
                economic_current_ids = connection.execute(
                    "SELECT id FROM economic_article_history "
                    "WHERE dbt_valid_to IS NULL ORDER BY id"
                ).fetchall()
            self.assertEqual(tech_current_ids, [("tech|2",)])
            self.assertEqual(economic_current_ids, [("economic|2",)])


if __name__ == "__main__":
    unittest.main()
