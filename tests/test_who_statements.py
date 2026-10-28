import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import who_news_scripts.who_statements as who_statements


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def api_item(item_id, title, news_type):
    return {
        "Id": item_id,
        "Title": title,
        "NewsType": news_type,
        "PublicationDateAndTime": "2026-08-28T15:55:12Z",
        "FormatedDate": "28 August 2026",
        "ItemDefaultUrl": f"/28-08-2026-{item_id}",
    }


class FetchStatementsTests(unittest.TestCase):
    @patch("who_news_scripts.who_statements.PAGE_SIZE", 2)
    @patch("who_news_scripts.who_statements.urlopen")
    def test_filters_statements_and_paginates_mixed_feed(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            FakeResponse(
                {
                    "value": [
                        api_item("news-1", "News", "News release"),
                        api_item("statement-1", "First", "Statement"),
                    ]
                }
            ),
            FakeResponse(
                {
                    "value": [
                        api_item("update-1", "Update", "Departmental update"),
                        api_item("statement-2", "Second", " statement "),
                    ]
                }
            ),
        ]

        result = who_statements.fetch_statements(limit=2)

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["scanned"], 4)
        self.assertEqual(
            [item["id"] for item in result["items"]],
            ["statement-1", "statement-2"],
        )
        self.assertEqual(
            result["items"][0]["url"],
            "https://www.who.int/news/item/28-08-2026-statement-1",
        )
        first_request = mocked_urlopen.call_args_list[0].args[0]
        second_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertIn("%24skip=0", first_request.full_url)
        self.assertIn("%24skip=2", second_request.full_url)
        self.assertNotIn("%24filter", first_request.full_url)

    @patch("who_news_scripts.who_statements.PAGE_SIZE", 2)
    @patch("who_news_scripts.who_statements.urlopen")
    def test_skips_stored_ids_and_pages_until_it_finds_new_statement(
        self, mocked_urlopen
    ):
        mocked_urlopen.side_effect = [
            FakeResponse(
                {
                    "value": [
                        api_item("known-1", "Known one", "Statement"),
                        api_item("known-2", "Known two", "Statement"),
                    ]
                }
            ),
            FakeResponse(
                {"value": [api_item("new-1", "New one", "Statement")]}
            ),
        ]

        result = who_statements.fetch_statements(
            limit=1,
            existing_ids={"known-1", "known-2"},
        )

        self.assertEqual(
            [item["id"] for item in result["items"]],
            ["known-1", "new-1"],
        )
        self.assertEqual(result["unseen_count"], 1)
        self.assertEqual(result["refreshed_count"], 1)
        self.assertEqual(result["existing_encountered"], 2)
        self.assertEqual(result["skipped_existing"], 1)
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            who_statements.fetch_statements(limit=0)

    @patch("who_news_scripts.who_statements.urlopen")
    def test_rejects_unexpected_api_shape(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse({"items": []})

        with self.assertRaises(who_statements.WhoStatementsError):
            who_statements.fetch_statements()


class SaveStatementsTests(unittest.TestCase):
    def test_inserts_then_updates_without_duplicates(self):
        first_fetch = {
            "fetched_at": "2026-09-10T15:00:00+00:00",
            "items": [
                {
                    "id": "statement-id",
                    "title": "Original title",
                    "news_type": "Statement",
                    "published_at": "2026-08-28T15:55:12Z",
                    "formatted_date": "28 August 2026",
                    "url": "https://www.who.int/news/item/example",
                }
            ],
        }
        second_fetch = {
            **first_fetch,
            "fetched_at": "2026-09-10T16:00:00+00:00",
            "items": [{**first_fetch["items"][0], "title": "Updated title"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_statement_news.db"
            first_result = who_statements.save_statements(database, first_fetch)
            second_result = who_statements.save_statements(database, second_fetch)

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT title, first_seen_at, last_seen_at
                    FROM statements WHERE id = ?
                    """,
                    ("statement-id",),
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM statements"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_statements"
                ).fetchone()[0]

        self.assertEqual(
            first_result,
            {"inserted": 1, "updated": 0, "total": 1, "staged": 1},
        )
        self.assertEqual(
            second_result,
            {"inserted": 0, "updated": 1, "total": 1, "staged": 1},
        )
        self.assertEqual(count, 1)
        self.assertEqual(staged_count, 1)
        self.assertEqual(
            row,
            (
                "Updated title",
                "2026-09-10T15:00:00+00:00",
                "2026-09-10T16:00:00+00:00",
            ),
        )


if __name__ == "__main__":
    unittest.main()
