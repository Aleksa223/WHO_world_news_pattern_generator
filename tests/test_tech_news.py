import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from tech_news_scripts import tech_news


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def hn_item(item_id, title=None, **overrides):
    item = {
        "id": item_id,
        "type": "story",
        "by": f"author-{item_id}",
        "time": 1_700_000_000 + item_id,
        "title": title or f"Story {item_id}",
        "url": f"https://example.com/{item_id}",
        "score": item_id,
        "descendants": item_id + 10,
        "kids": [999],
    }
    item.update(overrides)
    return item


def saved_item(item_id, title=None, **overrides):
    item = {
        "id": str(item_id),
        "provider": "Hacker News",
        "item_type": "story",
        "title": title or f"Story {item_id}",
        "description": None,
        "keywords": None,
        "snippet": None,
        "url": f"https://example.com/{item_id}",
        "discussion_url": (
            f"https://news.ycombinator.com/item?id={item_id}"
        ),
        "image_url": None,
        "language": None,
        "published_at": "2026-10-09T10:00:00+00:00",
        "source": "example.com",
        "author": f"author-{item_id}",
        "score": 10,
        "comment_count": 3,
        "feed": "newstories",
        "feed_rank": int(item_id),
        "categories": ["tech"],
    }
    item.update(overrides)
    return item


class FetchTechNewsTests(unittest.TestCase):
    @patch("tech_news_scripts.tech_news.urlopen")
    def test_fetches_200_stories_and_scans_past_skipped_items(
        self, mocked_urlopen
    ):
        story_ids = list(range(1, 203))
        items = {
            item_id: hn_item(item_id)
            for item_id in story_ids
        }
        items[1] = hn_item(1, dead=True)
        items[2] = hn_item(2, type="job")

        def response_for(request, timeout):
            self.assertEqual(timeout, tech_news.DEFAULT_TIMEOUT)
            if request.full_url == tech_news.HACKER_NEWS_FEED_URL:
                return FakeResponse(story_ids)
            item_id = int(request.full_url.rsplit("/", 1)[1].split(".", 1)[0])
            return FakeResponse(items[item_id])

        mocked_urlopen.side_effect = response_for
        result = tech_news.fetch_tech_news(limit=200, workers=4)

        self.assertEqual(result["count"], 200)
        self.assertEqual(result["scanned"], 202)
        self.assertEqual(result["available"], 202)
        self.assertFalse(result["exhausted"])
        self.assertEqual(result["items"][0]["id"], "3")
        self.assertEqual(result["items"][-1]["id"], "202")
        self.assertEqual(result["items"][0]["feed_rank"], 3)
        self.assertEqual(mocked_urlopen.call_count, 203)

        for call in mocked_urlopen.call_args_list:
            request = call.args[0]
            self.assertNotIn("token", request.full_url.casefold())
            self.assertNotIn(
                "authorization",
                {name.casefold() for name, _ in request.header_items()},
            )

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_maps_hacker_news_fields_and_self_post_url(
        self, mocked_urlopen
    ):
        mocked_urlopen.side_effect = [
            FakeResponse([42]),
            FakeResponse(
                hn_item(
                    42,
                    title="Ask HN: Better databases?",
                    url=None,
                    text="<p>Hello &amp; welcome</p>",
                    by="alice",
                    time=1_700_000_000,
                    score=99,
                    descendants=17,
                    kids=[1, 2],
                )
            ),
        ]

        result = tech_news.fetch_tech_news(limit=1, workers=1)
        item = result["items"][0]

        self.assertEqual(item["author"], "alice")
        self.assertEqual(item["published_at"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(item["score"], 99)
        self.assertEqual(item["comment_count"], 17)
        self.assertEqual(item["description"], "Hello & welcome")
        self.assertEqual(
            item["url"], "https://news.ycombinator.com/item?id=42"
        )
        self.assertEqual(item["url"], item["discussion_url"])
        self.assertEqual(item["source"], "news.ycombinator.com")

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_skips_null_deleted_dead_non_story_and_missing_title(
        self, mocked_urlopen
    ):
        responses = {
            1: None,
            2: hn_item(2, deleted=True),
            3: hn_item(3, dead=True),
            4: hn_item(4, type="comment"),
            5: hn_item(5, title=" "),
            6: hn_item(6),
        }

        def response_for(request, timeout):
            if request.full_url == tech_news.HACKER_NEWS_FEED_URL:
                return FakeResponse([True, 0, -1, "6", 1, 2, 3, 4, 5, 6, 6])
            item_id = int(request.full_url.rsplit("/", 1)[1].split(".", 1)[0])
            return FakeResponse(responses[item_id])

        mocked_urlopen.side_effect = response_for
        result = tech_news.fetch_tech_news(limit=2, workers=1)

        self.assertEqual(result["available"], 6)
        self.assertEqual(result["scanned"], 6)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["exhausted"])
        self.assertEqual(result["items"][0]["id"], "6")

    def test_rejects_invalid_arguments(self):
        with self.assertRaises(ValueError):
            tech_news.fetch_tech_news(limit=0)
        with self.assertRaises(ValueError):
            tech_news.fetch_tech_news(limit=501)
        with self.assertRaises(ValueError):
            tech_news.fetch_tech_news(timeout=0)
        with self.assertRaises(ValueError):
            tech_news.fetch_tech_news(workers=33)

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_rejects_unexpected_api_shapes(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse({"items": []})
        with self.assertRaises(tech_news.TechNewsError):
            tech_news.fetch_tech_news(limit=1, workers=1)

        mocked_urlopen.side_effect = [
            FakeResponse([1]),
            FakeResponse(["not", "an", "object"]),
        ]
        with self.assertRaises(tech_news.TechNewsError):
            tech_news.fetch_tech_news(limit=1, workers=1)

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_accepts_an_empty_feed(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse([])

        result = tech_news.fetch_tech_news(limit=1, workers=1)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["available"], 0)
        self.assertEqual(result["scanned"], 0)
        self.assertTrue(result["exhausted"])

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_fetches_unseen_and_bounded_existing_stories(
        self, mocked_urlopen
    ):
        story_ids = [1, 2, 3, 4, 5]

        def response_for(request, timeout):
            if request.full_url == tech_news.HACKER_NEWS_FEED_URL:
                return FakeResponse(story_ids)
            item_id = int(request.full_url.rsplit("/", 1)[1].split(".", 1)[0])
            return FakeResponse(hn_item(item_id))

        mocked_urlopen.side_effect = response_for
        result = tech_news.fetch_tech_news(
            limit=2,
            workers=1,
            existing_ids={"1", "2", "5"},
        )

        self.assertEqual(
            [item["id"] for item in result["items"]],
            ["1", "2", "3", "4"],
        )
        self.assertEqual(
            [item["feed_rank"] for item in result["items"]], [1, 2, 3, 4]
        )
        self.assertEqual(result["available"], 5)
        self.assertEqual(result["unseen_available"], 2)
        self.assertEqual(result["existing_available"], 3)
        self.assertEqual(result["new_count"], 2)
        self.assertEqual(result["refreshed_count"], 2)
        self.assertEqual(result["refresh_selected"], 2)
        self.assertEqual(result["refresh_skipped"], 1)
        self.assertEqual(result["unseen_scanned"], 2)
        self.assertEqual(result["refresh_scanned"], 2)
        self.assertEqual(result["scanned"], 4)
        self.assertFalse(result["exhausted"])
        requested_urls = [
            call.args[0].full_url for call in mocked_urlopen.call_args_list
        ]
        self.assertIn(
            tech_news.HACKER_NEWS_ITEM_URL.format(item_id=1), requested_urls
        )
        self.assertIn(
            tech_news.HACKER_NEWS_ITEM_URL.format(item_id=2), requested_urls
        )
        self.assertNotIn(
            tech_news.HACKER_NEWS_ITEM_URL.format(item_id=5), requested_urls
        )

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_reports_hacker_news_http_error(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            url=tech_news.HACKER_NEWS_FEED_URL,
            code=503,
            msg="Unavailable",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(tech_news.TechNewsError) as context:
            tech_news.fetch_tech_news(limit=1, workers=1)

        self.assertIn("Hacker News API returned HTTP 503", str(context.exception))


class SaveTechNewsTests(unittest.TestCase):
    @patch("tech_news_scripts.tech_news.urlopen")
    def test_repeated_fetches_accumulate_unseen_stories(self, mocked_urlopen):
        story_ids = [1, 2, 3, 4, 5]

        def response_for(request, timeout):
            if request.full_url == tech_news.HACKER_NEWS_FEED_URL:
                return FakeResponse(story_ids)
            item_id = int(
                request.full_url.rsplit("/", 1)[1].split(".", 1)[0]
            )
            return FakeResponse(hn_item(item_id))

        mocked_urlopen.side_effect = response_for

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tech_news.db"
            batch_sizes = []
            for _ in range(3):
                data = tech_news.fetch_tech_news(
                    limit=2,
                    workers=1,
                    existing_ids=tech_news.load_existing_ids(database),
                )
                result = tech_news.save_tech_news(database, data)
                batch_sizes.append(result["inserted"])

            with closing(sqlite3.connect(database)) as connection:
                stored_ids = [
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT id
                        FROM tech_articles
                        ORDER BY CAST(id AS INTEGER)
                        """
                    )
                ]

        self.assertEqual(batch_sizes, [2, 2, 1])
        self.assertEqual(stored_ids, ["1", "2", "3", "4", "5"])

    @patch("tech_news_scripts.tech_news.urlopen")
    def test_refreshes_scores_while_accumulating_new_stories(
        self, mocked_urlopen
    ):
        story_ids = [1, 2, 3]

        def response_for(request, timeout):
            if request.full_url == tech_news.HACKER_NEWS_FEED_URL:
                return FakeResponse(story_ids)
            item_id = int(request.full_url.rsplit("/", 1)[1].split(".", 1)[0])
            if item_id == 1:
                return FakeResponse(
                    hn_item(1, score=99, descendants=42, title="Updated")
                )
            return FakeResponse(hn_item(item_id))

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tech_news.db"
            tech_news.save_tech_news(
                database,
                {
                    "fetched_at": "2026-10-09T10:00:00+00:00",
                    "items": [
                        saved_item(1, score=1, comment_count=2, title="Old")
                    ],
                },
            )
            mocked_urlopen.side_effect = response_for
            data = tech_news.fetch_tech_news(
                limit=2,
                workers=1,
                existing_ids=tech_news.load_existing_ids(database),
            )
            result = tech_news.save_tech_news(database, data)

            with closing(sqlite3.connect(database)) as connection:
                refreshed = connection.execute(
                    """
                    SELECT title, score, comment_count, feed_rank
                    FROM tech_articles
                    WHERE id = '1'
                    """
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM tech_articles"
                ).fetchone()[0]

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(count, 3)
        self.assertEqual(refreshed, ("Updated", 99, 42, 1))
        self.assertEqual(data["new_count"], 2)
        self.assertEqual(data["refreshed_count"], 1)

    def test_inserts_then_updates_hacker_news_fields(self):
        first_fetch = {
            "fetched_at": "2026-10-09T10:00:00+00:00",
            "items": [
                saved_item(
                    42,
                    title="Original title",
                    author="alice",
                    score=10,
                    comment_count=3,
                )
            ],
        }
        second_fetch = {
            **first_fetch,
            "fetched_at": "2026-10-09T11:00:00+00:00",
            "items": [
                saved_item(
                    42,
                    title="Updated title",
                    author="bob",
                    score=20,
                    comment_count=8,
                )
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nested" / "tech_news.db"
            first_result = tech_news.save_tech_news(database, first_fetch)
            second_result = tech_news.save_tech_news(database, second_fetch)

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT
                        title,
                        author,
                        score,
                        comment_count,
                        discussion_url,
                        categories_json,
                        first_seen_at,
                        last_seen_at
                    FROM tech_articles
                    WHERE id = ?
                    """,
                    ("42",),
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM tech_articles"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_tech_articles"
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
                "bob",
                20,
                8,
                "https://news.ycombinator.com/item?id=42",
                '["tech"]',
                "2026-10-09T10:00:00+00:00",
                "2026-10-09T11:00:00+00:00",
            ),
        )

    def test_retains_articles_across_200_record_daily_batches(self):
        first_batch = {
            "fetched_at": "2026-10-09T10:00:00+00:00",
            "items": [saved_item(item_id) for item_id in range(1, 201)],
        }
        second_batch = {
            "fetched_at": "2026-10-10T10:00:00+00:00",
            "items": [saved_item(item_id) for item_id in range(201, 401)],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tech_articles" / "tech_news.db"
            first_result = tech_news.save_tech_news(database, first_batch)
            second_result = tech_news.save_tech_news(database, second_batch)
            with closing(sqlite3.connect(database)) as connection:
                raw_count = connection.execute(
                    "SELECT COUNT(*) FROM tech_articles"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_tech_articles"
                ).fetchone()[0]

        self.assertEqual(first_result["total"], 200)
        self.assertEqual(second_result["inserted"], 200)
        self.assertEqual(second_result["total"], 200)
        self.assertEqual(second_result["staged"], 400)
        self.assertEqual(raw_count, 400)
        self.assertEqual(staged_count, 400)

    def test_migrates_the_legacy_table_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tech_news.db"
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    """
                    CREATE TABLE tech_articles (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        keywords TEXT,
                        snippet TEXT,
                        url TEXT NOT NULL,
                        image_url TEXT,
                        language TEXT,
                        published_at TEXT,
                        source TEXT,
                        category TEXT NOT NULL,
                        categories_json TEXT NOT NULL,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE VIEW stg_tech_articles AS
                    SELECT * FROM tech_articles
                    """
                )

            result = tech_news.save_tech_news(
                database,
                {
                    "fetched_at": "2026-10-09T10:00:00+00:00",
                    "items": [saved_item(7)],
                },
            )
            with closing(sqlite3.connect(database)) as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(tech_articles)"
                    )
                }
                row = connection.execute(
                    """
                    SELECT provider, author, score, comment_count
                    FROM stg_tech_articles
                    WHERE id = '7'
                    """
                ).fetchone()

        self.assertEqual(result["inserted"], 1)
        self.assertTrue(
            {
                "provider",
                "item_type",
                "discussion_url",
                "author",
                "score",
                "comment_count",
                "feed",
                "feed_rank",
            }.issubset(columns)
        )
        self.assertEqual(row, ("Hacker News", "author-7", 10, 3))


class TechNewsCliTests(unittest.TestCase):
    def test_default_contract(self):
        args = tech_news.build_parser().parse_args([])

        self.assertEqual(tech_news.DEFAULT_LIMIT, 200)
        self.assertEqual(args.limit, 200)
        self.assertEqual(
            args.database, Path("tech_articles/tech_news.db")
        )

    @patch("tech_news_scripts.tech_news._write_json")
    @patch("tech_news_scripts.tech_news.save_tech_news")
    @patch("tech_news_scripts.tech_news.fetch_tech_news")
    @patch("tech_news_scripts.tech_news.load_existing_ids")
    def test_cli_runs_without_an_api_token(
        self, mocked_load_ids, mocked_fetch, mocked_save, mocked_write
    ):
        mocked_load_ids.return_value = {"already-stored"}
        mocked_fetch.return_value = {
            "count": 1,
            "scanned": 1,
            "available": 1,
            "exhausted": False,
            "items": [saved_item(1)],
        }
        mocked_save.return_value = {
            "inserted": 1,
            "updated": 0,
            "total": 1,
            "staged": 1,
        }
        stderr = io.StringIO()

        with patch.dict(os.environ, {}, clear=True), redirect_stderr(stderr):
            result = tech_news.main([])

        self.assertEqual(result, 0)
        mocked_fetch.assert_called_once_with(
            limit=200,
            timeout=tech_news.DEFAULT_TIMEOUT,
            workers=tech_news.DEFAULT_WORKERS,
            existing_ids={"already-stored"},
        )
        mocked_save.assert_called_once()
        self.assertEqual(
            mocked_save.call_args.args[0],
            Path("tech_articles/tech_news.db"),
        )
        mocked_write.assert_called_once()
        self.assertNotIn("token", stderr.getvalue().casefold())


if __name__ == "__main__":
    unittest.main()
