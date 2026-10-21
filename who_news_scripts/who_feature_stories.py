"""Fetch WHO Feature stories and store them in a dedicated SQLite database.

WHO publishes Feature stories through a public Sitefinity/OData endpoint. This
module pages through that endpoint, normalizes each story, and stores its title,
publication date, URL, and thumbnail without requiring an API key.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


WHO_BASE_URL = "https://www.who.int"
WHO_FEATURE_STORIES_API_URL = f"{WHO_BASE_URL}/api/hubs/featurestories"
WHO_FEATURE_STORY_URL = f"{WHO_BASE_URL}/news-room/feature-stories/detail/"
FEATURE_STORY_TYPE = "Feature stories"
SITE_ID = "15210d59-ad60-47ff-a542-7ed76645f0c7"
DEFAULT_TIMEOUT = 30
PAGE_SIZE = 100
MAX_FEATURE_STORIES = 1000
DEFAULT_DATABASE = Path("articles/who_stories_news.db")


class WhoFeatureStoriesError(RuntimeError):
    """Raised when WHO Feature stories cannot be downloaded, parsed, or saved."""


def _story_url(item_path: str | None) -> str | None:
    if not item_path:
        return None
    return WHO_FEATURE_STORY_URL + item_path.lstrip("/")


def _thumbnail_url(item_path: str | None) -> str | None:
    if not item_path:
        return None
    return urljoin(WHO_BASE_URL, item_path)


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert WHO field names into the local Feature stories schema."""
    return {
        "id": item.get("Id"),
        "title": item.get("Title"),
        "story_type": FEATURE_STORY_TYPE,
        "published_at": item.get("PublicationDateAndTime"),
        "formatted_date": item.get("FormatedDate"),
        "url": _story_url(item.get("ItemDefaultUrl")),
        "thumbnail_url": _thumbnail_url(item.get("ThumbnailUrl")),
    }


def _fetch_page(skip: int, top: int, timeout: int) -> list[dict[str, Any]]:
    params = {
        "sf_site": SITE_ID,
        "sf_provider": "OpenAccessProvider",
        "sf_culture": "en",
        "$top": top,
        "$skip": skip,
        "$orderby": "PublicationDateAndTime desc",
        "$select": (
            "Id,Title,ItemDefaultUrl,FormatedDate,PublicationDateAndTime,"
            "ThumbnailUrl"
        ),
    }
    request = Request(
        f"{WHO_FEATURE_STORIES_API_URL}?{urlencode(params)}",
        headers={
            "Accept": "application/json",
            "User-Agent": "who-feature-stories/1.0 (+personal news data project)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise WhoFeatureStoriesError(f"WHO API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WhoFeatureStoriesError(
            f"Could not connect to WHO API: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise WhoFeatureStoriesError("WHO API request timed out") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WhoFeatureStoriesError(
            "WHO API returned an invalid JSON response"
        ) from exc

    raw_items = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        raise WhoFeatureStoriesError(
            "WHO API response did not contain a 'value' list"
        )
    return [item for item in raw_items if isinstance(item, dict)]


def fetch_feature_stories(
    limit: int = 10, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fetch the newest WHO Feature stories, following API pagination."""
    if not 1 <= limit <= MAX_FEATURE_STORIES:
        raise ValueError(f"limit must be between 1 and {MAX_FEATURE_STORIES}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    stories: list[dict[str, Any]] = []
    scanned = 0

    while len(stories) < limit:
        page_size = min(PAGE_SIZE, limit - len(stories))
        page = _fetch_page(skip=scanned, top=page_size, timeout=timeout)
        scanned += len(page)

        for item in page:
            normalized = _normalize_item(item)
            if normalized["id"] and normalized["title"]:
                stories.append(normalized)
                if len(stories) == limit:
                    break

        if len(page) < page_size:
            break

    return {
        "source": WHO_FEATURE_STORIES_API_URL,
        "story_type": FEATURE_STORY_TYPE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(stories),
        "scanned": scanned,
        "items": stories,
    }


def _is_feature_story(item: dict[str, Any]) -> bool:
    story_type = item.get("story_type")
    return (
        isinstance(story_type, str)
        and story_type.strip().casefold() == FEATURE_STORY_TYPE.casefold()
    )


def save_feature_stories(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update Feature stories using the stable WHO item ID."""
    database.parent.mkdir(parents=True, exist_ok=True)
    items = [
        item
        for item in data.get("items", [])
        if (
            isinstance(item, dict)
            and item.get("id")
            and item.get("title")
            and _is_feature_story(item)
        )
    ]
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_stories (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    story_type TEXT NOT NULL,
                    published_at TEXT,
                    formatted_date TEXT,
                    url TEXT,
                    thumbnail_url TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE VIEW IF NOT EXISTS stg_feature_stories AS
                SELECT
                    id,
                    title,
                    story_type,
                    published_at,
                    formatted_date,
                    url,
                    thumbnail_url,
                    first_seen_at,
                    last_seen_at
                FROM feature_stories
                WHERE LOWER(TRIM(story_type)) = 'feature stories'
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feature_stories_published_at
                ON feature_stories (published_at DESC)
                """
            )

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM feature_stories WHERE id IN ({placeholders})",
                    ids,
                )
                existing_ids = {row[0] for row in rows}

            connection.executemany(
                """
                INSERT INTO feature_stories (
                    id, title, story_type, published_at, formatted_date, url,
                    thumbnail_url, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    story_type = excluded.story_type,
                    published_at = excluded.published_at,
                    formatted_date = excluded.formatted_date,
                    url = excluded.url,
                    thumbnail_url = excluded.thumbnail_url,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (
                        str(item["id"]),
                        str(item["title"]),
                        str(item["story_type"]),
                        item.get("published_at"),
                        item.get("formatted_date"),
                        item.get("url"),
                        item.get("thumbnail_url"),
                        fetched_at,
                        fetched_at,
                    )
                    for item in items
                ],
            )
            staged = connection.execute(
                "SELECT COUNT(*) FROM stg_feature_stories"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise WhoFeatureStoriesError(
            f"Could not save Feature stories to {database}: {exc}"
        ) from exc

    inserted = len(set(ids) - existing_ids)
    return {
        "inserted": inserted,
        "updated": len(items) - inserted,
        "total": len(items),
        "staged": staged,
    }


def _write_json(data: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        print(rendered, end="")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Saved {data['count']} WHO Feature stories to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download the newest WHO Feature stories into SQLite."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help=(
            f"number of Feature stories to fetch, up to {MAX_FEATURE_STORIES} "
            "(default: 10)"
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"SQLite database path (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON output file; otherwise print to the terminal",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_TIMEOUT,
        help=f"request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--watch",
        type=_positive_int,
        metavar="SECONDS",
        help="keep refreshing at this interval until Ctrl+C is pressed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit > MAX_FEATURE_STORIES:
        print(
            f"error: --limit cannot exceed {MAX_FEATURE_STORIES}",
            file=sys.stderr,
        )
        return 2

    try:
        while True:
            data = fetch_feature_stories(limit=args.limit, timeout=args.timeout)
            saved = save_feature_stories(args.database, data)
            print(
                f"Database {args.database}: {saved['inserted']} inserted, "
                f"{saved['updated']} updated, {saved['staged']} staged "
                f"({data['scanned']} Feature stories scanned)",
                file=sys.stderr,
            )
            _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except WhoFeatureStoriesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
