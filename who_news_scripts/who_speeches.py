"""Fetch WHO Speeches and store them in a dedicated SQLite database.

WHO publishes speeches through a public Sitefinity/OData endpoint. This module
pages through that endpoint, normalizes each speech, and stores its title,
publication date, tag, subtitle, URL, and thumbnail without requiring an API
key.
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
WHO_SPEECHES_API_URL = f"{WHO_BASE_URL}/api/hubs/speeches"
WHO_SPEECH_URL = f"{WHO_BASE_URL}/news-room/speeches/item/"
SPEECH_TYPE = "Speeches"
SITE_ID = "15210d59-ad60-47ff-a542-7ed76645f0c7"
DEFAULT_TIMEOUT = 30
PAGE_SIZE = 100
MAX_SPEECHES = 1000
DEFAULT_DATABASE = Path("articles/who_speech_news.db")


class WhoSpeechesError(RuntimeError):
    """Raised when WHO Speeches cannot be downloaded, parsed, or saved."""


def _speech_url(item_path: str | None) -> str | None:
    if not item_path:
        return None
    return WHO_SPEECH_URL + item_path.lstrip("/")


def _thumbnail_url(item_path: str | None) -> str | None:
    if not item_path:
        return None
    return urljoin(WHO_BASE_URL, item_path)


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert WHO field names into the local Speeches schema."""
    return {
        "id": item.get("Id"),
        "title": item.get("Title"),
        "speech_type": SPEECH_TYPE,
        "speech_tag": item.get("Tag"),
        "subtitle": item.get("Subtitle"),
        "published_at": item.get("PublicationDateAndTime"),
        "formatted_date": item.get("FormatedDate"),
        "url": _speech_url(item.get("ItemDefaultUrl")),
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
            "Id,Title,Subtitle,ItemDefaultUrl,FormatedDate,"
            "PublicationDateAndTime,Tag,ThumbnailUrl"
        ),
    }
    request = Request(
        f"{WHO_SPEECHES_API_URL}?{urlencode(params)}",
        headers={
            "Accept": "application/json",
            "User-Agent": "who-speeches/1.0 (+personal news data project)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise WhoSpeechesError(f"WHO API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WhoSpeechesError(f"Could not connect to WHO API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise WhoSpeechesError("WHO API request timed out") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WhoSpeechesError("WHO API returned an invalid JSON response") from exc

    raw_items = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        raise WhoSpeechesError("WHO API response did not contain a 'value' list")
    return [item for item in raw_items if isinstance(item, dict)]


def fetch_speeches(
    limit: int = 10, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fetch the newest WHO Speeches, following API pagination."""
    if not 1 <= limit <= MAX_SPEECHES:
        raise ValueError(f"limit must be between 1 and {MAX_SPEECHES}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    speeches: list[dict[str, Any]] = []
    scanned = 0

    while len(speeches) < limit:
        page_size = min(PAGE_SIZE, limit - len(speeches))
        page = _fetch_page(skip=scanned, top=page_size, timeout=timeout)
        scanned += len(page)

        for item in page:
            normalized = _normalize_item(item)
            if normalized["id"] and normalized["title"]:
                speeches.append(normalized)
                if len(speeches) == limit:
                    break

        if len(page) < page_size:
            break

    return {
        "source": WHO_SPEECHES_API_URL,
        "speech_type": SPEECH_TYPE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(speeches),
        "scanned": scanned,
        "items": speeches,
    }


def _is_speech(item: dict[str, Any]) -> bool:
    speech_type = item.get("speech_type")
    return (
        isinstance(speech_type, str)
        and speech_type.strip().casefold() == SPEECH_TYPE.casefold()
    )


def save_speeches(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update Speeches using the stable WHO item ID."""
    database.parent.mkdir(parents=True, exist_ok=True)
    items = [
        item
        for item in data.get("items", [])
        if (
            isinstance(item, dict)
            and item.get("id")
            and item.get("title")
            and _is_speech(item)
        )
    ]
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS speeches (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    speech_type TEXT NOT NULL,
                    speech_tag TEXT,
                    subtitle TEXT,
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
                CREATE VIEW IF NOT EXISTS stg_speeches AS
                SELECT
                    id,
                    title,
                    speech_type,
                    speech_tag,
                    subtitle,
                    published_at,
                    formatted_date,
                    url,
                    thumbnail_url,
                    first_seen_at,
                    last_seen_at
                FROM speeches
                WHERE LOWER(TRIM(speech_type)) = 'speeches'
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_speeches_published_at
                ON speeches (published_at DESC)
                """
            )

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM speeches WHERE id IN ({placeholders})", ids
                )
                existing_ids = {row[0] for row in rows}

            connection.executemany(
                """
                INSERT INTO speeches (
                    id, title, speech_type, speech_tag, subtitle, published_at,
                    formatted_date, url, thumbnail_url, first_seen_at,
                    last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    speech_type = excluded.speech_type,
                    speech_tag = excluded.speech_tag,
                    subtitle = excluded.subtitle,
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
                        str(item["speech_type"]),
                        item.get("speech_tag"),
                        item.get("subtitle"),
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
                "SELECT COUNT(*) FROM stg_speeches"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise WhoSpeechesError(f"Could not save Speeches to {database}: {exc}") from exc

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
    print(f"Saved {data['count']} WHO Speeches to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download the newest WHO Speeches into SQLite."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help=f"number of Speeches to fetch, up to {MAX_SPEECHES} (default: 10)",
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
    if args.limit > MAX_SPEECHES:
        print(f"error: --limit cannot exceed {MAX_SPEECHES}", file=sys.stderr)
        return 2

    try:
        while True:
            data = fetch_speeches(limit=args.limit, timeout=args.timeout)
            saved = save_speeches(args.database, data)
            print(
                f"Database {args.database}: {saved['inserted']} inserted, "
                f"{saved['updated']} updated, {saved['staged']} staged "
                f"({data['scanned']} Speeches scanned)",
                file=sys.stderr,
            )
            _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except WhoSpeechesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
