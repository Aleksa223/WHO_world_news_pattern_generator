"""Fetch recent technology news from the official Hacker News API.

The public API does not require a token. Story metadata is normalized and
upserted into a local SQLite database using each Hacker News item ID.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from functools import partial
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


HACKER_NEWS_API_ROOT = "https://hacker-news.firebaseio.com/v0"
HACKER_NEWS_FEED_URL = f"{HACKER_NEWS_API_ROOT}/newstories.json"
HACKER_NEWS_ITEM_URL = f"{HACKER_NEWS_API_ROOT}/item/{{item_id}}.json"
HACKER_NEWS_DISCUSSION_URL = "https://news.ycombinator.com/item?id={item_id}"
HACKER_NEWS_PROVIDER = "Hacker News"
TECH_CATEGORY = "tech"
DEFAULT_TIMEOUT = 30
DEFAULT_LIMIT = 200
DEFAULT_WORKERS = 16
MAX_WORKERS = 32
MAX_ARTICLES = 500
DEFAULT_DATABASE = Path("tech_articles/tech_news.db")


class TechNewsError(RuntimeError):
    """Raised when technology news cannot be downloaded, parsed, or saved."""


class _TextExtractor(HTMLParser):
    """Collect visible text from the small HTML fragments used by HN."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _plain_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    parser = _TextExtractor()
    try:
        parser.feed(cleaned)
        parser.close()
    except (ValueError, TypeError):
        return html.unescape(cleaned)

    rendered = " ".join(" ".join(parser.parts).split())
    return html.unescape(rendered) or None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _published_at(value: Any) -> str | None:
    timestamp = _nonnegative_int(value)
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _request_json(url: str, timeout: int) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "who-world-news/1.0 (+technology news pipeline)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise TechNewsError(
            f"Hacker News API returned HTTP {exc.code} for {url}"
        ) from exc
    except URLError as exc:
        raise TechNewsError(
            f"Could not connect to the Hacker News API: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise TechNewsError("The Hacker News API request timed out") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TechNewsError(
            f"The Hacker News API returned invalid JSON for {url}"
        ) from exc


def _fetch_story_ids(timeout: int) -> list[int]:
    payload = _request_json(HACKER_NEWS_FEED_URL, timeout)
    if not isinstance(payload, list):
        raise TechNewsError(
            "The Hacker News new-stories response was not a list"
        )

    story_ids: list[int] = []
    seen: set[int] = set()
    for value in payload:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            continue
        if value not in seen:
            seen.add(value)
            story_ids.append(value)
    return story_ids[:MAX_ARTICLES]


def _fetch_item(item_id: int, timeout: int) -> dict[str, Any] | None:
    url = HACKER_NEWS_ITEM_URL.format(item_id=item_id)
    payload = _request_json(url, timeout)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise TechNewsError(
            f"The Hacker News item response for {item_id} was not an object"
        )
    return payload


def _normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one Hacker News story into the local technology-news schema."""
    if item.get("deleted") is True or item.get("dead") is True:
        return None
    if _clean_text(item.get("type")) != "story":
        return None

    item_id = _nonnegative_int(item.get("id"))
    title = _clean_text(item.get("title"))
    if item_id is None or item_id <= 0 or title is None:
        return None

    discussion_url = HACKER_NEWS_DISCUSSION_URL.format(item_id=item_id)
    external_url = _clean_text(item.get("url"))
    article_url = external_url or discussion_url
    hostname = urlparse(external_url).hostname if external_url else None
    source = hostname.removeprefix("www.") if hostname else "news.ycombinator.com"
    description = _plain_text(item.get("text"))
    score = _nonnegative_int(item.get("score"))
    comment_count = _nonnegative_int(item.get("descendants"))

    return {
        "id": str(item_id),
        "provider": HACKER_NEWS_PROVIDER,
        "item_type": "story",
        "title": title,
        "description": description,
        "keywords": None,
        "snippet": description[:500] if description else None,
        "url": article_url,
        "discussion_url": discussion_url,
        "image_url": None,
        "language": None,
        "published_at": _published_at(item.get("time")),
        "source": source,
        "author": _clean_text(item.get("by")),
        "score": score if score is not None else 0,
        "comment_count": comment_count if comment_count is not None else 0,
        "feed": "newstories",
        "categories": [TECH_CATEGORY],
    }


def fetch_tech_news(
    limit: int = DEFAULT_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    """Fetch recent Hacker News stories while preserving feed order."""
    if not 1 <= limit <= MAX_ARTICLES:
        raise ValueError(f"limit must be between 1 and {MAX_ARTICLES}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")

    story_ids = _fetch_story_ids(timeout)
    articles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    scanned = 0
    cursor = 0

    if story_ids:
        fetch_one = partial(_fetch_item, timeout=timeout)
        with ThreadPoolExecutor(max_workers=min(workers, len(story_ids))) as executor:
            while len(articles) < limit and cursor < len(story_ids):
                remaining = limit - len(articles)
                batch_ids = story_ids[cursor : cursor + remaining]
                batch_start = cursor
                cursor += len(batch_ids)
                raw_items = list(executor.map(fetch_one, batch_ids))
                scanned += len(raw_items)

                for offset, raw_item in enumerate(raw_items):
                    if raw_item is None:
                        continue
                    normalized = _normalize_item(raw_item)
                    if normalized is None or normalized["id"] in seen_ids:
                        continue
                    normalized["feed_rank"] = batch_start + offset + 1
                    seen_ids.add(normalized["id"])
                    articles.append(normalized)
                    if len(articles) == limit:
                        break

    return {
        "source": HACKER_NEWS_FEED_URL,
        "provider": HACKER_NEWS_PROVIDER,
        "feed": "newstories",
        "category": TECH_CATEGORY,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "available": len(story_ids),
        "scanned": scanned,
        "exhausted": len(articles) < limit and cursor >= len(story_ids),
        "items": articles,
    }


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tech_articles (
            id TEXT PRIMARY KEY,
            provider TEXT,
            item_type TEXT,
            title TEXT NOT NULL,
            description TEXT,
            keywords TEXT,
            snippet TEXT,
            url TEXT NOT NULL,
            discussion_url TEXT,
            image_url TEXT,
            language TEXT,
            published_at TEXT,
            source TEXT,
            author TEXT,
            score INTEGER,
            comment_count INTEGER,
            feed TEXT,
            feed_rank INTEGER,
            category TEXT NOT NULL,
            categories_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """
    )

    required_columns = {
        "provider": "TEXT",
        "item_type": "TEXT",
        "discussion_url": "TEXT",
        "author": "TEXT",
        "score": "INTEGER",
        "comment_count": "INTEGER",
        "feed": "TEXT",
        "feed_rank": "INTEGER",
    }
    existing_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(tech_articles)")
    }
    for name, declaration in required_columns.items():
        if name not in existing_columns:
            connection.execute(
                f"ALTER TABLE tech_articles ADD COLUMN {name} {declaration}"
            )

    connection.execute("DROP VIEW IF EXISTS stg_tech_articles")
    connection.execute(
        """
        CREATE VIEW stg_tech_articles AS
        SELECT
            id,
            provider,
            item_type,
            title,
            description,
            keywords,
            snippet,
            url,
            discussion_url,
            image_url,
            language,
            published_at,
            source,
            author,
            score,
            comment_count,
            feed,
            feed_rank,
            category,
            categories_json,
            first_seen_at,
            last_seen_at
        FROM tech_articles
        WHERE LOWER(TRIM(category)) = 'tech'
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tech_articles_published_at
        ON tech_articles (published_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tech_articles_score
        ON tech_articles (score DESC)
        """
    )


def save_tech_news(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update Hacker News stories using their item IDs."""
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise TechNewsError(
            f"Could not create database directory for {database}: {exc}"
        ) from exc

    unique_items: dict[str, dict[str, Any]] = {}
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        article_id = _clean_text(item.get("id"))
        title = _clean_text(item.get("title"))
        item_type = _clean_text(item.get("item_type"))
        if item_type is not None and item_type != "story":
            continue
        if not article_id or not title:
            continue

        discussion_url = _clean_text(item.get("discussion_url"))
        if discussion_url is None and article_id.isdigit():
            discussion_url = HACKER_NEWS_DISCUSSION_URL.format(
                item_id=article_id
            )
        url = _clean_text(item.get("url")) or discussion_url
        if url is None:
            continue
        unique_items[article_id] = {
            **item,
            "id": article_id,
            "title": title,
            "url": url,
            "discussion_url": discussion_url,
        }

    items = list(unique_items.values())
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            _ensure_schema(connection)

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM tech_articles WHERE id IN ({placeholders})",
                    ids,
                )
                existing_ids = {str(row[0]) for row in rows}

            connection.executemany(
                """
                INSERT INTO tech_articles (
                    id,
                    provider,
                    item_type,
                    title,
                    description,
                    keywords,
                    snippet,
                    url,
                    discussion_url,
                    image_url,
                    language,
                    published_at,
                    source,
                    author,
                    score,
                    comment_count,
                    feed,
                    feed_rank,
                    category,
                    categories_json,
                    first_seen_at,
                    last_seen_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    item_type = excluded.item_type,
                    title = excluded.title,
                    description = excluded.description,
                    keywords = excluded.keywords,
                    snippet = excluded.snippet,
                    url = excluded.url,
                    discussion_url = excluded.discussion_url,
                    image_url = excluded.image_url,
                    language = excluded.language,
                    published_at = excluded.published_at,
                    source = excluded.source,
                    author = excluded.author,
                    score = excluded.score,
                    comment_count = excluded.comment_count,
                    feed = excluded.feed,
                    feed_rank = excluded.feed_rank,
                    category = excluded.category,
                    categories_json = excluded.categories_json,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (
                        str(item["id"]),
                        _clean_text(item.get("provider"))
                        or HACKER_NEWS_PROVIDER,
                        _clean_text(item.get("item_type")) or "story",
                        str(item["title"]),
                        _clean_text(item.get("description")),
                        _clean_text(item.get("keywords")),
                        _clean_text(item.get("snippet")),
                        str(item["url"]),
                        _clean_text(item.get("discussion_url")),
                        _clean_text(item.get("image_url")),
                        _clean_text(item.get("language")),
                        _clean_text(item.get("published_at")),
                        _clean_text(item.get("source")),
                        _clean_text(item.get("author")),
                        _nonnegative_int(item.get("score")),
                        _nonnegative_int(item.get("comment_count")),
                        _clean_text(item.get("feed")) or "newstories",
                        _nonnegative_int(item.get("feed_rank")),
                        TECH_CATEGORY,
                        json.dumps([TECH_CATEGORY], ensure_ascii=False),
                        fetched_at,
                        fetched_at,
                    )
                    for item in items
                ],
            )
            staged = connection.execute(
                "SELECT COUNT(*) FROM stg_tech_articles"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise TechNewsError(
            f"Could not save technology news to {database}: {exc}"
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

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise TechNewsError(
            f"Could not write JSON output to {output}: {exc}"
        ) from exc
    print(f"Saved {data['count']} Hacker News stories to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download recent Hacker News stories into SQLite."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_LIMIT,
        help=(
            f"number of stories to fetch, up to {MAX_ARTICLES} "
            f"(default: {DEFAULT_LIMIT})"
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
        "--workers",
        type=_positive_int,
        default=DEFAULT_WORKERS,
        help=(
            f"concurrent item requests, up to {MAX_WORKERS} "
            f"(default: {DEFAULT_WORKERS})"
        ),
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
    if args.limit > MAX_ARTICLES:
        print(f"error: --limit cannot exceed {MAX_ARTICLES}", file=sys.stderr)
        return 2
    if args.workers > MAX_WORKERS:
        print(f"error: --workers cannot exceed {MAX_WORKERS}", file=sys.stderr)
        return 2

    try:
        while True:
            data = fetch_tech_news(
                limit=args.limit,
                timeout=args.timeout,
                workers=args.workers,
            )
            saved = save_tech_news(args.database, data)
            print(
                f"Database {args.database}: {saved['inserted']} inserted, "
                f"{saved['updated']} updated, {saved['staged']} staged "
                f"({data['scanned']} items scanned from "
                f"{data['available']} available)",
                file=sys.stderr,
            )
            if data["exhausted"]:
                print(
                    "warning: the Hacker News feed was exhausted before "
                    "the requested number of valid stories was found",
                    file=sys.stderr,
                )
            _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except TechNewsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
