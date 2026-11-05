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
from urllib.parse import parse_qs, urlsplit

from economic_news_scripts import economic_news


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def gdelt_article(number, **overrides):
    article = {
        "url": f"https://Example.com/economy/{number}",
        "url_mobile": f"https://m.example.com/economy/{number}",
        "title": f"Economic story {number}",
        "seendate": "20261015T103000Z",
        "socialimage": f"https://example.com/images/{number}.jpg",
        "domain": "Example.com",
        "language": "English",
        "sourcecountry": "United States",
    }
    article.update(overrides)
    return article


def saved_article(number, **overrides):
    url = f"https://example.com/economy/{number}"
    article = {
        "id": economic_news._article_id(url),
        "provider": "GDELT",
        "item_type": "article",
        "title": f"Economic story {number}",
        "description": None,
        "keywords": economic_news.DEFAULT_QUERY,
        "snippet": None,
        "url": url,
        "mobile_url": f"https://m.example.com/economy/{number}",
        "image_url": f"https://example.com/images/{number}.jpg",
        "language": "English",
        "published_at": "2026-10-15T10:30:00+00:00",
        "gdelt_seen_at": "2026-10-15T10:30:00+00:00",
        "gdelt_seen_date": "20261015T103000Z",
        "source": "example.com",
        "source_country": "United States",
        "feed": "gdelt_doc",
        "feed_rank": number,
        "query": economic_news.DEFAULT_QUERY,
        "category": "economic",
        "categories": ["economic"],
    }
    article.update(overrides)
    return article


class FetchEconomicNewsTests(unittest.TestCase):
    @patch("economic_news_scripts.economic_news.urlopen")
    def test_builds_token_free_request_and_maps_gdelt_fields(
        self, mocked_urlopen
    ):
        mocked_urlopen.return_value = FakeResponse(
            {"articles": [gdelt_article(1, title="Inflation &amp; growth")]}
        )

        result = economic_news.fetch_economic_news(
            limit=1,
            timeout=12,
            query="inflation OR GDP",
            timespan="1week",
        )

        request = mocked_urlopen.call_args.args[0]
        parameters = parse_qs(urlsplit(request.full_url).query)
        effective_query = "inflation OR GDP sourcelang:english"
        self.assertEqual(mocked_urlopen.call_args.kwargs["timeout"], 12)
        self.assertEqual(parameters["query"], [effective_query])
        self.assertEqual(parameters["mode"], ["artlist"])
        self.assertEqual(parameters["format"], ["json"])
        self.assertEqual(parameters["maxrecords"], ["1"])
        self.assertEqual(parameters["sort"], ["datedesc"])
        self.assertEqual(parameters["timespan"], ["1week"])
        self.assertNotIn("key", request.full_url.casefold())
        self.assertNotIn("token", request.full_url.casefold())

        item = result["items"][0]
        self.assertEqual(item["title"], "Inflation & growth")
        self.assertEqual(item["url"], "https://example.com/economy/1")
        self.assertEqual(item["source"], "example.com")
        self.assertEqual(item["source_country"], "United States")
        self.assertEqual(item["published_at"], "2026-10-15T10:30:00+00:00")
        self.assertEqual(item["gdelt_seen_date"], "20261015T103000Z")
        self.assertEqual(item["feed_rank"], 1)
        self.assertEqual(item["id"], economic_news._article_id(item["url"]))
        self.assertEqual(result["query"], effective_query)
        self.assertEqual(item["query"], effective_query)
        self.assertEqual(item["keywords"], effective_query)

    @patch("economic_news_scripts.economic_news.urlopen")
    def test_default_query_fetches_english_articles(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {"articles": [gdelt_article(1)]}
        )

        result = economic_news.fetch_economic_news(limit=1)

        request = mocked_urlopen.call_args.args[0]
        parameters = parse_qs(urlsplit(request.full_url).query)
        effective_query = (
            f"{economic_news.DEFAULT_QUERY} "
            f"{economic_news.ENGLISH_SOURCE_FILTER}"
        )
        self.assertEqual(parameters["query"], [effective_query])
        self.assertEqual(result["query"], effective_query)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["query"], effective_query)

    @patch("economic_news_scripts.economic_news.urlopen")
    def test_skips_non_english_and_missing_language_rows(
        self, mocked_urlopen
    ):
        missing_language = gdelt_article(4)
        del missing_language["language"]
        mocked_urlopen.return_value = FakeResponse(
            {
                "articles": [
                    gdelt_article(1),
                    gdelt_article(2, language="Spanish"),
                    gdelt_article(3, language=None),
                    missing_language,
                ]
            }
        )

        result = economic_news.fetch_economic_news(limit=10)

        self.assertEqual(result["available"], 4)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["skipped"], 3)
        self.assertEqual(result["items"][0]["language"], "English")
        self.assertEqual(result["items"][0]["feed_rank"], 1)

    @patch("economic_news_scripts.economic_news.urlopen")
    def test_skips_invalid_rows_and_duplicate_urls(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {
                "articles": [
                    gdelt_article(1),
                    gdelt_article(2, url="https://example.com/economy/1#section"),
                    gdelt_article(3, title=" "),
                    gdelt_article(4, url="ftp://example.com/4"),
                    "not an object",
                    gdelt_article(5),
                ]
            }
        )

        result = economic_news.fetch_economic_news(limit=10)

        self.assertEqual(result["available"], 6)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["skipped"], 4)
        self.assertEqual([item["feed_rank"] for item in result["items"]], [1, 6])

    @patch("economic_news_scripts.economic_news.urlopen")
    def test_accepts_an_empty_article_list(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse({"articles": []})

        result = economic_news.fetch_economic_news(limit=1)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["available"], 0)
        self.assertEqual(result["skipped"], 0)

    @patch("economic_news_scripts.economic_news.urlopen")
    def test_rejects_unexpected_api_shapes(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse([])
        with self.assertRaises(economic_news.EconomicNewsError):
            economic_news.fetch_economic_news(limit=1)

        mocked_urlopen.return_value = FakeResponse({"results": []})
        with self.assertRaises(economic_news.EconomicNewsError):
            economic_news.fetch_economic_news(limit=1)

    @patch("economic_news_scripts.economic_news.time.sleep")
    @patch("economic_news_scripts.economic_news.urlopen")
    def test_retries_gdelt_rate_limit_then_succeeds(
        self, mocked_urlopen, mocked_sleep
    ):
        mocked_urlopen.side_effect = [
            HTTPError(
                url=economic_news.GDELT_DOC_API_URL,
                code=429,
                msg="Too Many Requests",
                hdrs=None,
                fp=None,
            ),
            FakeResponse({"articles": [gdelt_article(1)]}),
        ]

        result = economic_news.fetch_economic_news(limit=1)

        self.assertEqual(result["count"], 1)
        self.assertEqual(mocked_urlopen.call_count, 2)
        mocked_sleep.assert_called_once_with(5)

    @patch("economic_news_scripts.economic_news.time.sleep")
    @patch("economic_news_scripts.economic_news.urlopen")
    def test_reports_gdelt_rate_limit_after_bounded_retries(
        self, mocked_urlopen, mocked_sleep
    ):
        mocked_urlopen.side_effect = HTTPError(
            url=economic_news.GDELT_DOC_API_URL,
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(economic_news.GdeltRateLimitError) as context:
            economic_news.fetch_economic_news(limit=1)

        self.assertIn("rate limit was reached", str(context.exception))
        self.assertEqual(mocked_urlopen.call_count, 4)
        self.assertEqual(
            [call.args[0] for call in mocked_sleep.call_args_list],
            [5, 10, 20],
        )

    @patch("economic_news_scripts.economic_news.time.sleep")
    @patch("economic_news_scripts.economic_news.urlopen")
    def test_does_not_retry_non_rate_limit_http_errors(
        self, mocked_urlopen, mocked_sleep
    ):
        mocked_urlopen.side_effect = HTTPError(
            url=economic_news.GDELT_DOC_API_URL,
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(economic_news.EconomicNewsError) as context:
            economic_news.fetch_economic_news(limit=1)

        self.assertIn("HTTP 500", str(context.exception))
        mocked_urlopen.assert_called_once()
        mocked_sleep.assert_not_called()

    def test_rejects_invalid_arguments(self):
        with self.assertRaises(ValueError):
            economic_news.fetch_economic_news(limit=0)
        with self.assertRaises(ValueError):
            economic_news.fetch_economic_news(limit=251)
        with self.assertRaises(ValueError):
            economic_news.fetch_economic_news(timeout=0)
        with self.assertRaises(ValueError):
            economic_news.fetch_economic_news(query=" ")
        with self.assertRaises(ValueError):
            economic_news.fetch_economic_news(timespan="yesterday")


class SaveEconomicNewsTests(unittest.TestCase):
    def test_inserts_then_updates_and_preserves_first_seen(self):
        first_fetch = {
            "query": economic_news.DEFAULT_QUERY,
            "fetched_at": "2026-10-15T10:00:00+00:00",
            "items": [saved_article(1, title="Original title")],
        }
        second_fetch = {
            **first_fetch,
            "fetched_at": "2026-10-15T11:00:00+00:00",
            "items": [
                saved_article(
                    1,
                    title="Updated title",
                    source_country="Canada",
                    feed_rank=7,
                )
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nested" / "economic_news.db"
            first_result = economic_news.save_economic_news(database, first_fetch)
            second_result = economic_news.save_economic_news(database, second_fetch)

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT
                        title,
                        source_country,
                        feed_rank,
                        categories_json,
                        first_seen_at,
                        last_seen_at
                    FROM economic_articles
                    """
                ).fetchone()
                staged = connection.execute(
                    "SELECT COUNT(*) FROM stg_economic_articles"
                ).fetchone()[0]

        self.assertEqual(
            first_result,
            {"inserted": 1, "updated": 0, "total": 1, "staged": 1},
        )
        self.assertEqual(
            second_result,
            {"inserted": 0, "updated": 1, "total": 1, "staged": 1},
        )
        self.assertEqual(staged, 1)
        self.assertEqual(
            row,
            (
                "Updated title",
                "Canada",
                7,
                '["economic"]',
                "2026-10-15T10:00:00+00:00",
                "2026-10-15T11:00:00+00:00",
            ),
        )

    def test_retains_articles_across_200_record_daily_batches(self):
        first_batch = {
            "query": economic_news.DEFAULT_QUERY,
            "fetched_at": "2026-10-15T10:00:00+00:00",
            "items": [saved_article(number) for number in range(1, 201)],
        }
        second_batch = {
            "query": economic_news.DEFAULT_QUERY,
            "fetched_at": "2026-10-16T10:00:00+00:00",
            "items": [saved_article(number) for number in range(201, 401)],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "economic_articles" / "economic_news.db"
            first_result = economic_news.save_economic_news(database, first_batch)
            second_result = economic_news.save_economic_news(database, second_batch)
            with closing(sqlite3.connect(database)) as connection:
                raw_count = connection.execute(
                    "SELECT COUNT(*) FROM economic_articles"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_economic_articles"
                ).fetchone()[0]

        self.assertEqual(first_result["total"], 200)
        self.assertEqual(second_result["inserted"], 200)
        self.assertEqual(second_result["total"], 200)
        self.assertEqual(second_result["staged"], 400)
        self.assertEqual(raw_count, 400)
        self.assertEqual(staged_count, 400)


class EconomicNewsCliTests(unittest.TestCase):
    def test_default_contract(self):
        args = economic_news.build_parser().parse_args([])

        self.assertEqual(args.limit, 200)
        self.assertEqual(args.database, Path("economic_articles/economic_news.db"))
        self.assertEqual(args.query, economic_news.DEFAULT_QUERY)
        self.assertEqual(args.timespan, "1d")
        self.assertFalse(args.allow_stale_on_rate_limit)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            economic_news.build_parser().parse_args(["--watch", "4"])

    @patch("economic_news_scripts.economic_news._write_json")
    @patch("economic_news_scripts.economic_news.save_economic_news")
    @patch("economic_news_scripts.economic_news.fetch_economic_news")
    def test_cli_runs_without_an_api_token(
        self, mocked_fetch, mocked_save, mocked_write
    ):
        mocked_fetch.return_value = {
            "count": 1,
            "available": 1,
            "skipped": 0,
            "items": [saved_article(1)],
        }
        mocked_save.return_value = {
            "inserted": 1,
            "updated": 0,
            "total": 1,
            "staged": 1,
        }
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "economic-news.db"
            with patch.dict(os.environ, {}, clear=True), redirect_stderr(stderr):
                result = economic_news.main(["--database", str(database)])

        self.assertEqual(result, 0)
        mocked_fetch.assert_called_once_with(
            limit=200,
            timeout=economic_news.DEFAULT_TIMEOUT,
            query=economic_news.DEFAULT_QUERY,
            timespan="1d",
        )
        self.assertEqual(
            mocked_save.call_args.args[0],
            database,
        )
        mocked_write.assert_called_once()
        self.assertNotIn("token", stderr.getvalue().casefold())

    @patch("economic_news_scripts.economic_news.fetch_economic_news")
    def test_scheduled_cli_retains_cached_data_after_rate_limit(
        self, mocked_fetch
    ):
        mocked_fetch.side_effect = economic_news.GdeltRateLimitError(
            "The GDELT API rate limit was reached after 4 attempts"
        )
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "economic-news.db"
            output = Path(directory) / "economic-news.json"
            economic_news.save_economic_news(
                database,
                {
                    "query": economic_news.DEFAULT_QUERY,
                    "fetched_at": "2026-10-15T10:00:00+00:00",
                    "items": [saved_article(1)],
                },
            )

            with redirect_stderr(stderr):
                result = economic_news.main(
                    [
                        "--database",
                        str(database),
                        "--output",
                        str(output),
                        "--allow-stale-on-rate-limit",
                    ]
                )

            fallback_output = json.loads(output.read_text(encoding="utf-8"))

            with closing(sqlite3.connect(database)) as connection:
                audit_row = connection.execute(
                    """
                    SELECT status, error_type, total_rows
                    FROM ingestion_audit
                    ORDER BY rowid DESC
                    LIMIT 1
                    """
                ).fetchone()
                article_count = connection.execute(
                    "SELECT COUNT(*) FROM economic_articles"
                ).fetchone()[0]

        self.assertEqual(result, 0)
        self.assertEqual(article_count, 1)
        self.assertEqual(audit_row, ("failed", "GdeltRateLimitError", 1))
        self.assertTrue(fallback_output["stale"])
        self.assertEqual(fallback_output["count"], 1)
        self.assertEqual(fallback_output["items"][0]["id"], saved_article(1)["id"])
        self.assertIn("rate limit", fallback_output["fallback_error"])
        self.assertIn("retaining cached economic articles", stderr.getvalue())

    @patch("economic_news_scripts.economic_news.fetch_economic_news")
    def test_scheduled_cli_fails_without_cached_data(self, mocked_fetch):
        mocked_fetch.side_effect = economic_news.GdeltRateLimitError(
            "The GDELT API rate limit was reached after 4 attempts"
        )
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "economic-news.db"
            output = Path(directory) / "economic-news.json"
            with redirect_stderr(stderr):
                result = economic_news.main(
                    [
                        "--database",
                        str(database),
                        "--output",
                        str(output),
                        "--allow-stale-on-rate-limit",
                    ]
                )

            with closing(sqlite3.connect(database)) as connection:
                audit_status = connection.execute(
                    "SELECT status FROM ingestion_audit"
                ).fetchone()[0]

        self.assertEqual(result, 1)
        self.assertEqual(audit_status, "failed")
        self.assertFalse(output.exists())
        self.assertIn("error: The GDELT API rate limit", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
