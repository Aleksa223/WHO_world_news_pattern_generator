import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import who_news_scripts.who_feature_stories as who_feature_stories


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def api_item(item_id, title):
    return {
        "Id": item_id,
        "Title": title,
        "PublicationDateAndTime": "2026-09-29T14:12:45Z",
        "FormatedDate": "29 September 2026",
        "ItemDefaultUrl": f"/{item_id}",
        "ThumbnailUrl": f"/images/{item_id}.jpg",
    }


class FetchFeatureStoriesTests(unittest.TestCase):
    @patch("who_news_scripts.who_feature_stories.PAGE_SIZE", 2)
    @patch("who_news_scripts.who_feature_stories.urlopen")
    def test_normalizes_stories_and_follows_pagination(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            FakeResponse(
                {"value": [api_item("story-1", "First"), api_item("story-2", "Second")]}
            ),
            FakeResponse({"value": [api_item("story-3", "Third")]}),
        ]

        result = who_feature_stories.fetch_feature_stories(limit=3)

        self.assertEqual(result["count"], 3)
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(
            [item["title"] for item in result["items"]],
            ["First", "Second", "Third"],
        )
        self.assertEqual(result["items"][0]["story_type"], "Feature stories")
        self.assertEqual(
            result["items"][0]["url"],
            "https://www.who.int/news-room/feature-stories/detail/story-1",
        )
        self.assertEqual(
            result["items"][0]["thumbnail_url"],
            "https://www.who.int/images/story-1.jpg",
        )
        first_request = mocked_urlopen.call_args_list[0].args[0]
        second_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertIn("%24skip=0", first_request.full_url)
        self.assertIn("%24skip=2", second_request.full_url)

    @patch("who_news_scripts.who_feature_stories.PAGE_SIZE", 2)
    @patch("who_news_scripts.who_feature_stories.urlopen")
    def test_skips_stored_ids_and_pages_until_it_finds_new_story(
        self, mocked_urlopen
    ):
        mocked_urlopen.side_effect = [
            FakeResponse(
                {
                    "value": [
                        api_item("known-1", "Known one"),
                        api_item("known-2", "Known two"),
                    ]
                }
            ),
            FakeResponse({"value": [api_item("new-1", "New one")]}),
        ]

        result = who_feature_stories.fetch_feature_stories(
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

    @patch("who_news_scripts.who_feature_stories.MAX_SCANNED_ITEMS", 4)
    @patch("who_news_scripts.who_feature_stories.PAGE_SIZE", 2)
    @patch("who_news_scripts.who_feature_stories.urlopen")
    def test_stops_at_scan_ceiling_when_full_pages_have_no_unseen_items(
        self, mocked_urlopen
    ):
        payload = {
            "value": [
                api_item("known-1", "Known one"),
                api_item("known-2", "Known two"),
            ]
        }
        mocked_urlopen.side_effect = [FakeResponse(payload), FakeResponse(payload)]

        result = who_feature_stories.fetch_feature_stories(
            limit=1,
            existing_ids={"known-1", "known-2"},
        )

        self.assertTrue(result["scan_limit_reached"])
        self.assertEqual(result["scanned"], 4)
        self.assertEqual(result["unseen_count"], 0)
        self.assertEqual(result["refreshed_count"], 1)
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            who_feature_stories.fetch_feature_stories(limit=0)

    @patch("who_news_scripts.who_feature_stories.urlopen")
    def test_rejects_unexpected_api_shape(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse({"items": []})

        with self.assertRaises(who_feature_stories.WhoFeatureStoriesError):
            who_feature_stories.fetch_feature_stories()


class SaveFeatureStoriesTests(unittest.TestCase):
    def test_inserts_then_updates_without_duplicates(self):
        first_fetch = {
            "fetched_at": "2026-09-10T15:00:00+00:00",
            "items": [
                {
                    "id": "story-id",
                    "title": "Original title",
                    "story_type": "Feature stories",
                    "published_at": "2026-09-29T14:12:45Z",
                    "formatted_date": "29 September 2026",
                    "url": (
                        "https://www.who.int/news-room/feature-stories/"
                        "detail/example"
                    ),
                    "thumbnail_url": "https://www.who.int/images/example.jpg",
                }
            ],
        }
        second_fetch = {
            **first_fetch,
            "fetched_at": "2026-09-10T16:00:00+00:00",
            "items": [{**first_fetch["items"][0], "title": "Updated title"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "who_stories_news.db"
            first_result = who_feature_stories.save_feature_stories(
                database, first_fetch
            )
            second_result = who_feature_stories.save_feature_stories(
                database, second_fetch
            )

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    """
                    SELECT title, first_seen_at, last_seen_at
                    FROM feature_stories WHERE id = ?
                    """,
                    ("story-id",),
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM feature_stories"
                ).fetchone()[0]
                staged_count = connection.execute(
                    "SELECT COUNT(*) FROM stg_feature_stories"
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
