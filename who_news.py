"""Fetch WHO newsroom items whose news type contains the word ``news``.

This module uses WHO's public, read-only Sitefinity/OData endpoint. It does
not require an API key and can be imported by another Python application or
run directly from the command line.
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
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WHO_API_URL = "https://www.who.int/api/news/newsitems"
WHO_NEWS_ITEM_URL = "https://www.who.int/news/item/"
DEFAULT_TIMEOUT = 30
PAGE_SIZE = 100
MAX_ITEMS = 1000
MAX_SCANNED_ITEMS = 20_000
DEFAULT_DATABASE = Path("data/who_news.db")


class WhoNewsError(RuntimeError):
    """Raised when WHO news cannot be downloaded or parsed."""


def _article_url(item_path: str | None) -> str | None:
    if not item_path:
        return None
    return WHO_NEWS_ITEM_URL + item_path.lstrip("/")


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert WHO's field names into a small, stable application schema."""
    return {
        "id": item.get("Id"),
        "title": item.get("Title"),
        "news_type": item.get("NewsType"),
        "published_at": item.get("PublicationDateAndTime"),
        "formatted_date": item.get("FormatedDate"),
        "url": _article_url(item.get("ItemDefaultUrl")),
    }


def _contains_news(news_type: Any) -> bool:
    return isinstance(news_type, str) and "news" in news_type.casefold()


def _fetch_page(skip: int, top: int, timeout: int) -> list[dict[str, Any]]:
    params = {
        "$top": top,
        "$skip": skip,
        "$orderby": "PublicationDateAndTime desc",
        "$select": (
            "Id,Title,NewsType,PublicationDateAndTime,FormatedDate,"
            "ItemDefaultUrl"
        ),
    }
    request = Request(
        f"{WHO_API_URL}?{urlencode(params)}",
        headers={
            "Accept": "application/json",
            "User-Agent": "who-world-news/1.0 (+personal news data project)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise WhoNewsError(f"WHO API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WhoNewsError(f"Could not connect to WHO API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise WhoNewsError("WHO API request timed out") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WhoNewsError("WHO API returned an invalid JSON response") from exc

    raw_items = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        raise WhoNewsError("WHO API response did not contain a 'value' list")

    return [item for item in raw_items if isinstance(item, dict)]


def fetch_news(limit: int = 10, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Fetch the newest WHO items with ``news`` in their news type.

    Args:
        limit: Number of articles to request (1 through 1000).
        timeout: HTTP timeout in seconds.

    Returns:
        A dictionary containing ``fetched_at``, ``count``, and ``items``.

    Raises:
        ValueError: If an argument is outside its accepted range.
        WhoNewsError: If WHO cannot be reached or returns invalid data.
    """
    if not 1 <= limit <= MAX_ITEMS:
        raise ValueError(f"limit must be between 1 and {MAX_ITEMS}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    items: list[dict[str, Any]] = []
    scanned = 0
    exhausted = False

    while len(items) < limit and scanned < MAX_SCANNED_ITEMS:
        page_size = min(PAGE_SIZE, MAX_SCANNED_ITEMS - scanned)
        page = _fetch_page(skip=scanned, top=page_size, timeout=timeout)
        scanned += len(page)

        for item in page:
            if _contains_news(item.get("NewsType")):
                items.append(_normalize_item(item))
                if len(items) == limit:
                    break

        if len(page) < page_size:
            exhausted = True
            break

    return {
        "source": WHO_API_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "scanned": scanned,
        "scan_limit_reached": (
            not exhausted and scanned >= MAX_SCANNED_ITEMS and len(items) < limit
        ),
        "items": items,
    }


def save_news(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update fetched articles in a SQLite database.

    WHO's article ID is the primary key, so fetching the same articles again
    updates their metadata instead of creating duplicate rows.
    """
    database.parent.mkdir(parents=True, exist_ok=True)
    items = [
        item
        for item in data.get("items", [])
        if (
            isinstance(item, dict)
            and item.get("id")
            and _contains_news(item.get("news_type"))
        )
    ]
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    news_type TEXT,
                    published_at TEXT,
                    formatted_date TEXT,
                    url TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE VIEW IF NOT EXISTS stg_articles AS
                SELECT
                    id,
                    title,
                    news_type,
                    published_at,
                    formatted_date,
                    url,
                    first_seen_at,
                    last_seen_at
                FROM articles
                WHERE LOWER(COALESCE(news_type, '')) LIKE '%news%'
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_articles_published_at
                ON articles (published_at DESC)
                """
            )
            connection.execute(
                """
                DELETE FROM articles
                WHERE LOWER(COALESCE(news_type, '')) NOT LIKE '%news%'
                """
            )

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM articles WHERE id IN ({placeholders})", ids
                )
                existing_ids = {row[0] for row in rows}

            connection.executemany(
                """
                INSERT INTO articles (
                    id, title, news_type, published_at, formatted_date, url,
                    first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    news_type = excluded.news_type,
                    published_at = excluded.published_at,
                    formatted_date = excluded.formatted_date,
                    url = excluded.url,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (
                        str(item["id"]),
                        item.get("title") or "Untitled",
                        item.get("news_type"),
                        item.get("published_at"),
                        item.get("formatted_date"),
                        item.get("url"),
                        fetched_at,
                        fetched_at,
                    )
                    for item in items
                ],
            )
            staged = connection.execute(
                "SELECT COUNT(*) FROM stg_articles"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise WhoNewsError(f"Could not save articles to {database}: {exc}") from exc

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
    print(f"Saved {data['count']} WHO news items to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download WHO items whose news type contains 'news' into SQLite."
        )
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help=(
            f"number of matching news items to fetch, up to {MAX_ITEMS} "
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
    if args.limit > MAX_ITEMS:
        print(f"error: --limit cannot exceed {MAX_ITEMS}", file=sys.stderr)
        return 2

    try:
        while True:
            data = fetch_news(limit=args.limit, timeout=args.timeout)
            saved = save_news(args.database, data)
            print(
                f"Database {args.database}: {saved['inserted']} inserted, "
                f"{saved['updated']} updated, {saved['staged']} staged "
                f"({data['scanned']} newsroom items scanned)",
                file=sys.stderr,
            )
            if data["scan_limit_reached"]:
                print(
                    "warning: scan limit reached before the requested number "
                    "of news items was found",
                    file=sys.stderr,
                )
            _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except WhoNewsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
