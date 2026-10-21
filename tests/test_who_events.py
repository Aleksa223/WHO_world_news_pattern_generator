import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
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


if __name__ == "__main__":
    unittest.main()
