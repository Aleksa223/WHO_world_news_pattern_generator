import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from who_news_scripts import who_campaigns


class FakeResponse:
    def __init__(self, page):
        self.body = io.BytesIO(page.encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def campaign_card(path, title):
    return f"""
    <div class="mdc-card mdc-card--outlined" role="article">
      <div class="mdc-card__primary-action">
        <a href="{path}" class="link">
          <div class="card-media--item">
            <div class="item--title"> {title} </div>
          </div>
        </a>
      </div>
    </div>
    """


class FetchCampaignsTests(unittest.TestCase):
    @patch("who_news_scripts.who_campaigns.urlopen")
    def test_extracts_only_campaign_cards_and_applies_limit(self, mocked_urlopen):
        page = f"""
        <html><body>
          <a href="/campaigns/not-a-card">Navigation link</a>
          {campaign_card('/campaigns/world-health-day', 'World Health Day')}
          {campaign_card('/campaigns/world-tb-day/', 'World TB Day')}
          {campaign_card('/campaigns/terms-of-use', 'Terms of use')}
        </body></html>
        """
        mocked_urlopen.return_value = FakeResponse(page)

        result = who_campaigns.fetch_campaigns(limit=2)

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["available"], 2)
        self.assertEqual(
            [item["title"] for item in result["items"]],
            ["World Health Day", "World TB Day"],
        )
        self.assertEqual(result["items"][0]["id"], "world-health-day")
        self.assertEqual(result["items"][0]["campaign_type"], "Campaigns")
        self.assertEqual(
            result["items"][0]["url"],
            "https://www.who.int/campaigns/world-health-day",
        )

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            who_campaigns.fetch_campaigns(limit=0)

    @patch("who_news_scripts.who_campaigns.urlopen")
    def test_rejects_page_without_campaign_cards(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse("<html><body>No cards</body></html>")

        with self.assertRaises(who_campaigns.WhoCampaignsError):
            who_campaigns.fetch_campaigns()


class SaveCampaignsTests(unittest.TestCase):
    def test_inserts_then_updates_without_duplicates(self):
        first_fetch = {
            "fetched_at": "2026-09-10T15:00:00+00:00",
            "items": [
                {
                    "id": "world-health-day",
                    "title": "World Health Day",
                    "campaign_type": "Campaigns",
                    "url": "https://www.who.int/campaigns/world-health-day",
                }
            ],
        }
        second_fetch = {
            **first_fetch,
            "fetched_at": "2026-09-10T16:00:00+00:00",
            "items": [{**first_fetch["items"][0], "title": "Updated title"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_campaign_news.db"
            first_result = who_campaigns.save_campaigns(database, first_fetch)
            second_result = who_campaigns.save_campaigns(database, second_fetch)

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT title, first_seen_at, last_seen_at
                    FROM campaigns WHERE id = ?
                    """,
                    ("world-health-day",),
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM campaigns"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_campaigns"
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
