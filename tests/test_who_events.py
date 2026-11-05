import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from who_news_scripts import who_events


class FakeResponse:
    def __init__(self, page):
        self.body = io.BytesIO(page.encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def event_card(path, title, date_text):
    return f"""
    <div class="list-view--item vertical-list-item">
      <a href="{path}" class="link-container table event-table"
         aria-label="{title}" role="link">
        <div class="table-cell info">
          <p class="heading text-underline">{title}</p>
          <span class="timestamp"><i class="fa fa-calendar"></i>{date_text}</span>
        </div>
      </a>
    </div>
    """


class FetchEventsTests(unittest.TestCase):
    @patch("who_news_scripts.who_events.urlopen")
    def test_extracts_events_and_follows_pagination(self, mocked_urlopen):
        first_path = "/news-room/events/detail/2026/10/01/default-calendar/first"
        second_path = "/news-room/events/detail/2026/10/02/default-calendar/second"
        third_path = "/news-room/events/detail/2026/10/03/default-calendar/third"
        page_one = f"""
        <html><body>
          {event_card(first_path, 'First event', '1 October 2026')}
          {event_card(second_path, 'Second event', '2 October 2026')}
          <ul class="pagination">
            <li><a href="/news-room/events/1">1</a></li>
            <li><a href="/news-room/events/2">2</a></li>
          </ul>
        </body></html>
        """
        page_two = f"""
        <html><body>
          {event_card(second_path, 'Second event', '2 October 2026')}
          {event_card(third_path, 'Third event', '3 October 2026')}
        </body></html>
        """
        mocked_urlopen.side_effect = [FakeResponse(page_one), FakeResponse(page_two)]

        result = who_events.fetch_events(limit=3)

        self.assertEqual(result["count"], 3)
        self.assertEqual(result["pages_scanned"], 2)
        self.assertEqual(
            [item["title"] for item in result["items"]],
            ["First event", "Second event", "Third event"],
        )
        self.assertEqual(result["items"][0]["event_type"], "Events")
        self.assertEqual(result["items"][0]["date_text"], "1 October 2026")
        self.assertEqual(
            result["items"][0]["url"],
            f"https://www.who.int{first_path}",
        )
        second_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(
            second_request.full_url, "https://www.who.int/news-room/events/2"
        )

    @patch("who_news_scripts.who_events.urlopen")
    def test_skips_stored_events_and_follows_pages_for_the_next_batch(
        self, mocked_urlopen
    ):
        known_path = "/news-room/events/detail/2026/10/01/known"
        new_path = "/news-room/events/detail/2026/10/02/new"
        page_one = f"""
        <html><body>
          {event_card(known_path, 'Known event', '1 October 2026')}
          <a href="/news-room/events/1">1</a>
          <a href="/news-room/events/2">2</a>
        </body></html>
        """
        page_two = f"""
        <html><body>
          {event_card(new_path, 'New event', '2 October 2026')}
        </body></html>
        """
        mocked_urlopen.side_effect = [FakeResponse(page_one), FakeResponse(page_two)]

        result = who_events.fetch_events(
            limit=1,
            existing_ids={"2026/10/01/known"},
        )

        self.assertEqual(
            [item["id"] for item in result["items"]],
            ["2026/10/01/known", "2026/10/02/new"],
        )
        self.assertEqual(result["unseen_count"], 1)
        self.assertEqual(result["refreshed_count"], 1)
        self.assertEqual(result["existing_encountered"], 1)
        self.assertEqual(result["skipped_existing"], 0)
        self.assertEqual(result["pages_scanned"], 2)

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            who_events.fetch_events(limit=0)

    @patch("who_news_scripts.who_events.urlopen")
    def test_rejects_page_without_event_cards(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse("<html><body>No cards</body></html>")

        with self.assertRaises(who_events.WhoEventsError):
            who_events.fetch_events()


class SaveEventsTests(unittest.TestCase):
    def test_inserts_then_updates_without_duplicates(self):
        first_fetch = {
            "fetched_at": "2026-09-10T15:00:00+00:00",
            "items": [
                {
                    "id": "2026/10/01/default-calendar/example",
                    "title": "Original event",
                    "event_type": "Events",
                    "date_text": "1 October 2026",
                    "url": (
                        "https://www.who.int/news-room/events/detail/"
                        "2026/10/01/default-calendar/example"
                    ),
                }
            ],
        }
        second_fetch = {
            **first_fetch,
            "fetched_at": "2026-09-10T16:00:00+00:00",
            "items": [{**first_fetch["items"][0], "title": "Updated event"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_event_news.db"
            first_result = who_events.save_events(database, first_fetch)
            second_result = who_events.save_events(database, second_fetch)

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT title, first_seen_at, last_seen_at
                    FROM events WHERE id = ?
                    """,
                    ("2026/10/01/default-calendar/example",),
                ).fetchone()
                count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_events"
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
                "Updated event",
                "2026-09-10T15:00:00+00:00",
                "2026-09-10T16:00:00+00:00",
            ),
        )


class EventsCliTests(unittest.TestCase):
    def test_default_contract(self):
        args = who_events.build_parser().parse_args([])

        self.assertEqual(args.limit, 10)
        self.assertEqual(args.database, Path("articles/who_event_news.db"))
        self.assertFalse(args.allow_stale_on_fetch_error)

    @patch("who_news_scripts.who_events.fetch_events")
    def test_scheduled_cli_writes_cached_output_after_fetch_error(
        self, mocked_fetch
    ):
        mocked_fetch.side_effect = who_events.WhoEventsFetchError(
            "WHO returned HTTP 400 for the Events page"
        )
        stderr = io.StringIO()
        cached_item = {
            "id": "2026/10/01/default-calendar/example",
            "title": "Cached event",
            "event_type": "Events",
            "date_text": "1 October 2026",
            "url": (
                "https://www.who.int/news-room/events/detail/"
                "2026/10/01/default-calendar/example"
            ),
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who-event-news.db"
            output = Path(directory) / "who-latest-events.json"
            who_events.save_events(
                database,
                {
                    "fetched_at": "2026-10-15T10:00:00+00:00",
                    "items": [cached_item],
                },
            )

            with redirect_stderr(stderr):
                result = who_events.main(
                    [
                        "--database",
                        str(database),
                        "--output",
                        str(output),
                        "--allow-stale-on-fetch-error",
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
                event_count = connection.execute(
                    "SELECT COUNT(*) FROM events"
                ).fetchone()[0]

        self.assertEqual(result, 0)
        self.assertEqual(event_count, 1)
        self.assertEqual(audit_row, ("failed", "WhoEventsFetchError", 1))
        self.assertTrue(fallback_output["stale"])
        self.assertEqual(fallback_output["items"], [cached_item])
        self.assertIn("HTTP 400", fallback_output["fallback_error"])
        self.assertIn("retaining cached WHO events", stderr.getvalue())

    @patch("who_news_scripts.who_events.fetch_events")
    def test_scheduled_cli_fails_without_cached_events(self, mocked_fetch):
        mocked_fetch.side_effect = who_events.WhoEventsFetchError(
            "WHO returned HTTP 400 for the Events page"
        )
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who-event-news.db"
            output = Path(directory) / "who-latest-events.json"
            with redirect_stderr(stderr):
                result = who_events.main(
                    [
                        "--database",
                        str(database),
                        "--output",
                        str(output),
                        "--allow-stale-on-fetch-error",
                    ]
                )

            with closing(sqlite3.connect(database)) as connection:
                audit_status = connection.execute(
                    "SELECT status FROM ingestion_audit"
                ).fetchone()[0]

        self.assertEqual(result, 1)
        self.assertEqual(audit_status, "failed")
        self.assertFalse(output.exists())
        self.assertIn("error: WHO returned HTTP 400", stderr.getvalue())

    @patch("who_news_scripts.who_events.save_events")
    @patch("who_news_scripts.who_events.fetch_events")
    def test_scheduled_cli_does_not_hide_database_save_errors(
        self, mocked_fetch, mocked_save
    ):
        mocked_fetch.return_value = {
            "count": 0,
            "pages_scanned": 1,
            "items": [],
        }
        mocked_save.side_effect = who_events.WhoEventsError(
            "Could not save Events"
        )
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who-event-news.db"
            with redirect_stderr(stderr):
                result = who_events.main(
                    [
                        "--database",
                        str(database),
                        "--allow-stale-on-fetch-error",
                    ]
                )

        self.assertEqual(result, 1)
        self.assertIn("error: Could not save Events", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
