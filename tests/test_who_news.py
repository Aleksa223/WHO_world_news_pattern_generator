import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import who_news_scripts.who_news as who_news


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FetchNewsTests(unittest.TestCase):
    @patch("who_news_scripts.who_news.urlopen")
    def test_fetch_news_normalizes_api_fields(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {
                "value": [
                    {
                        "Id": "article-id",
                        "Title": "Example headline",
                        "NewsType": "News release",
                        "PublicationDateAndTime": "2026-09-09T12:00:00Z",
                        "FormatedDate": "9 September 2026",
                        "ItemDefaultUrl": "/09-09-2026-example-headline",
                    }
                ]
            }
        )

        result = who_news.fetch_news(limit=1)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["title"], "Example headline")
        self.assertEqual(
            result["items"][0]["url"],
            "https://www.who.int/news/item/09-09-2026-example-headline",
        )
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("%24top=100", request.full_url)
        self.assertIn("PublicationDateAndTime+desc", request.full_url)

    @patch("who_news_scripts.who_news.PAGE_SIZE", 2)
    @patch("who_news_scripts.who_news.urlopen")
    def test_filters_news_types_and_paginates_mixed_feed(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            FakeResponse(
                {
                    "value": [
                        {
                            "Id": "statement",
                            "Title": "Statement",
                            "NewsType": "Statement",
                        },
                        {
                            "Id": "news-release",
                            "Title": "News release",
                            "NewsType": "News release",
                        },
                    ]
                }
            ),
            FakeResponse(
                {
                    "value": [
                        {
                            "Id": "update",
                            "Title": "Update",
                            "NewsType": "Departmental update",
                        },
                        {
                            "Id": "joint-news",
                            "Title": "Joint release",
                            "NewsType": "Joint NEWS Release",
                        },
                    ]
                }
            ),
        ]

        result = who_news.fetch_news(limit=2)

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["scanned"], 4)
        self.assertEqual(
            [item["id"] for item in result["items"]],
            ["news-release", "joint-news"],
        )
        first_request = mocked_urlopen.call_args_list[0].args[0]
        second_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertIn("%24skip=0", first_request.full_url)
        self.assertIn("%24skip=2", second_request.full_url)

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            who_news.fetch_news(limit=0)

    @patch("who_news_scripts.who_news.urlopen")
    def test_rejects_unexpected_api_shape(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse({"items": []})

        with self.assertRaises(who_news.WhoNewsError):
            who_news.fetch_news()


class SaveNewsTests(unittest.TestCase):
    def test_save_news_inserts_then_updates_without_duplicates(self):
        first_fetch = {
            "fetched_at": "2026-09-10T15:00:00+00:00",
            "items": [
                {
                    "id": "article-id",
                    "title": "Original title",
                    "news_type": "News release",
                    "published_at": "2026-09-09T12:00:00Z",
                    "formatted_date": "9 September 2026",
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
            database = Path(directory) / "who_news.db"
            first_result = who_news.save_news(database, first_fetch)
            second_result = who_news.save_news(database, second_fetch)

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT title, first_seen_at, last_seen_at
                    FROM articles WHERE id = ?
                    """,
                    ("article-id",),
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM articles"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_articles"
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

    def test_staging_view_keeps_only_news_types_containing_news(self):
        data = {
            "fetched_at": "2026-09-10T15:00:00+00:00",
            "items": [
                {"id": "1", "title": "A", "news_type": "News release"},
                {"id": "2", "title": "B", "news_type": "Joint NEWS Release"},
                {"id": "3", "title": "C", "news_type": "Departmental update"},
                {"id": "4", "title": "D", "news_type": None},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_news.db"
            result = who_news.save_news(database, data)
            with closing(sqlite3.connect(database)) as connection:
                staged = connection.execute(
                    "SELECT id, news_type FROM stg_articles ORDER BY id"
                ).fetchall()
                raw = connection.execute(
                    "SELECT id, news_type FROM articles ORDER BY id"
                ).fetchall()

        self.assertEqual(result["staged"], 2)
        self.assertEqual(
            staged,
            [("1", "News release"), ("2", "Joint NEWS Release")],
        )
        self.assertEqual(raw, staged)

    def test_retains_records_across_200_record_daily_batches(self):
        def batch(first_id, fetched_at):
            return {
                "fetched_at": fetched_at,
                "items": [
                    {
                        "id": str(article_id),
                        "title": f"WHO news {article_id}",
                        "news_type": "News release",
                        "url": f"https://www.who.int/news/item/{article_id}",
                    }
                    for article_id in range(first_id, first_id + 200)
                ],
            }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_news.db"
            first_result = who_news.save_news(
                database, batch(1, "2026-10-15T06:00:00+00:00")
            )
            second_result = who_news.save_news(
                database, batch(201, "2026-10-16T06:00:00+00:00")
            )
            with closing(sqlite3.connect(database)) as connection:
                raw_count = connection.execute(
                    "SELECT COUNT(*) FROM articles"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_articles"
                ).fetchone()[0]

        self.assertEqual(first_result["total"], 200)
        self.assertEqual(second_result["inserted"], 200)
        self.assertEqual(second_result["total"], 200)
        self.assertEqual(second_result["staged"], 400)
        self.assertEqual(raw_count, 400)
        self.assertEqual(staged_count, 400)


if __name__ == "__main__":
    unittest.main()
