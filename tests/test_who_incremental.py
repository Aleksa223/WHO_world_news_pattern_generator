import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from who_news_scripts.incremental import IncrementalBatch, load_existing_ids


class IncrementalBatchTests(unittest.TestCase):
    def test_bounds_unseen_and_refresh_items_and_ignores_duplicate_ids(self):
        batch = IncrementalBatch[str](2, {"known-1", "known-2", "known-3"})

        for item_id in (
            "known-1",
            "known-1",
            "known-2",
            "known-3",
            "new-1",
            "new-1",
            "new-2",
        ):
            batch.consider(item_id, item_id)

        self.assertEqual(
            batch.items,
            ["known-1", "known-2", "new-1", "new-2"],
        )
        self.assertEqual(
            batch.metadata(),
            {
                "count": 4,
                "unseen_count": 2,
                "refreshed_count": 2,
                "existing_encountered": 3,
                "skipped_existing": 1,
            },
        )


class ExistingIdsTests(unittest.TestCase):
    def test_missing_database_is_treated_as_first_run_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.db"

            result = load_existing_ids(database, "articles")

            self.assertEqual(result, set())
            self.assertFalse(database.exists())

    def test_reads_existing_primary_keys_from_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_news.db"
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("CREATE TABLE articles (id TEXT PRIMARY KEY)")
                connection.executemany(
                    "INSERT INTO articles (id) VALUES (?)",
                    [("known-1",), ("known-2",)],
                )

            result = load_existing_ids(database, "articles")

        self.assertEqual(result, {"known-1", "known-2"})

    def test_rejects_unsafe_table_names(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_news.db"
            database.touch()

            with self.assertRaises(ValueError):
                load_existing_ids(database, 'articles"; DROP TABLE articles; --')


if __name__ == "__main__":
    unittest.main()
