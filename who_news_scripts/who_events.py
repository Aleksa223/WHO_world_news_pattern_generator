"""Fetch WHO event titles and store them in a dedicated SQLite database.

WHO publishes events on a paginated events index rather than in the newsroom
JSON feed used by ``who_news.py`` and ``who_statements.py``. This module reads
that official index, extracts event cards, and stores their titles, displayed
dates, and URLs without requiring an API key or third-party packages.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maintenance_scripts.ingestion_audit import (  # noqa: E402
    AuditTarget,
    IngestionAuditError,
    begin_ingestion_audit,
)

if __package__:
    from .incremental import (
        IncrementalBatch,
        IncrementalStateError,
        load_existing_ids,
    )
else:  # Support ``python who_news_scripts/who_events.py``.
    from incremental import (
        IncrementalBatch,
        IncrementalStateError,
        load_existing_ids,
    )


WHO_BASE_URL = "https://www.who.int"
WHO_EVENTS_URL = f"{WHO_BASE_URL}/news-room/events"
EVENT_TYPE = "Events"
DEFAULT_TIMEOUT = 30
MAX_EVENTS = 1000
MAX_EVENT_PAGES = 50
DEFAULT_DATABASE = Path("articles/who_event_news.db")
AUDIT_TARGET = AuditTarget("who_events", "events", None)


class WhoEventsError(RuntimeError):
    """Raised when WHO events cannot be downloaded, parsed, or saved."""


def _who_path(href: str | None) -> str | None:
    if not href:
        return None

    parsed = urlparse(urljoin(WHO_BASE_URL, href.strip()))
    if parsed.netloc.casefold() not in {"who.int", "www.who.int"}:
        return None
    return parsed.path.rstrip("/")


def _event_path(href: str | None) -> str | None:
    path = _who_path(href)
    if not path or not path.casefold().startswith("/news-room/events/detail/"):
        return None
    return path


class _EventCardParser(HTMLParser):
    """Extract event cards and pagination links from a WHO events page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[dict[str, str]] = []
        self.page_numbers: set[int] = set()
        self._path: str | None = None
        self._aria_title: str | None = None
        self._title_parts: list[str] = []
        self._date_parts: list[str] = []
        self._in_title = False
        self._in_date = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())

        if tag == "a":
            href = attributes.get("href")
            path = _who_path(href)
            if path:
                page_match = re.fullmatch(r"/news-room/events/(\d+)", path)
                if page_match:
                    self.page_numbers.add(int(page_match.group(1)))

            event_path = _event_path(href)
            if event_path and "event-table" in classes:
                self._path = event_path
                self._aria_title = attributes.get("aria-label")
                self._title_parts = []
                self._date_parts = []

        if self._path is not None:
            if tag == "p" and "heading" in classes:
                self._in_title = True
            elif tag == "span" and "timestamp" in classes:
                self._in_date = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_date:
            self._date_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p":
            self._in_title = False
        elif tag == "span":
            self._in_date = False
        elif tag == "a" and self._path is not None:
            title = self._aria_title or "".join(self._title_parts)
            title = " ".join(title.split())
            date_text = " ".join("".join(self._date_parts).split())
            if title:
                self.events.append(
                    {
                        "id": self._path.removeprefix(
                            "/news-room/events/detail/"
                        ),
                        "title": title,
                        "event_type": EVENT_TYPE,
                        "date_text": date_text,
                        "url": urljoin(WHO_BASE_URL, self._path),
                    }
                )
            self._path = None
            self._aria_title = None
            self._title_parts = []
            self._date_parts = []
            self._in_title = False
            self._in_date = False


def _parse_events(page: str) -> tuple[list[dict[str, str]], set[int]]:
    parser = _EventCardParser()
    parser.feed(page)
    parser.close()
    return parser.events, parser.page_numbers


def _fetch_page(page_number: int, timeout: int) -> str:
    url = WHO_EVENTS_URL if page_number == 1 else f"{WHO_EVENTS_URL}/{page_number}"
    request = Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": "who-events/1.0 (+personal news data project)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise WhoEventsError(f"WHO returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WhoEventsError(f"Could not connect to WHO: {exc.reason}") from exc
    except TimeoutError as exc:
        raise WhoEventsError("WHO request timed out") from exc
    except UnicodeDecodeError as exc:
        raise WhoEventsError("WHO returned an invalid text response") from exc


def fetch_events(
    limit: int = 10,
    timeout: int = DEFAULT_TIMEOUT,
    existing_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Fetch unseen WHO events, following listing pagination as needed."""
    if not 1 <= limit <= MAX_EVENTS:
        raise ValueError(f"limit must be between 1 and {MAX_EVENTS}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    batch = IncrementalBatch[dict[str, str]](limit, existing_ids)
    page_number = 1
    last_page = 1
    pages_scanned = 0

    while page_number <= last_page and page_number <= MAX_EVENT_PAGES:
        page = _fetch_page(page_number, timeout)
        pages_scanned += 1
        events, page_numbers = _parse_events(page)
        if page_number == 1 and not events:
            raise WhoEventsError("WHO events page contained no event cards")
        if page_numbers:
            last_page = min(max(page_numbers), MAX_EVENT_PAGES)

        for event in events:
            batch.consider(event, event["id"])
            if not batch.needs_unseen:
                break

        if not batch.needs_unseen:
            break
        page_number += 1

    return {
        "source": WHO_EVENTS_URL,
        "event_type": EVENT_TYPE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **batch.metadata(),
        "scanned": batch.encountered_count,
        "pages_scanned": pages_scanned,
        "items": batch.items,
    }


def _is_event(item: dict[str, Any]) -> bool:
    event_type = item.get("event_type")
    return (
        isinstance(event_type, str)
        and event_type.strip().casefold() == EVENT_TYPE.casefold()
    )


def save_events(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update events using their stable WHO detail path."""
    database.parent.mkdir(parents=True, exist_ok=True)
    items = [
        item
        for item in data.get("items", [])
        if (
            isinstance(item, dict)
            and item.get("id")
            and item.get("title")
            and _is_event(item)
        )
    ]
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    date_text TEXT,
                    url TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE VIEW IF NOT EXISTS stg_events AS
                SELECT
                    id,
                    title,
                    event_type,
                    date_text,
                    url,
                    first_seen_at,
                    last_seen_at
                FROM events
                WHERE LOWER(TRIM(event_type)) = 'events'
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_title
                ON events (title)
                """
            )

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM events WHERE id IN ({placeholders})", ids
                )
                existing_ids = {row[0] for row in rows}

            connection.executemany(
                """
                INSERT INTO events (
                    id, title, event_type, date_text, url,
                    first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    event_type = excluded.event_type,
                    date_text = excluded.date_text,
                    url = excluded.url,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (
                        str(item["id"]),
                        str(item["title"]),
                        str(item["event_type"]),
                        item.get("date_text"),
                        str(item["url"]),
                        fetched_at,
                        fetched_at,
                    )
                    for item in items
                ],
            )
            staged = connection.execute(
                "SELECT COUNT(*) FROM stg_events"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise WhoEventsError(f"Could not save Events to {database}: {exc}") from exc

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
    print(f"Saved {data['count']} WHO Events to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download WHO event titles into SQLite.")
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help=f"number of Events to fetch, up to {MAX_EVENTS} (default: 10)",
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
    if args.limit > MAX_EVENTS:
        print(f"error: --limit cannot exceed {MAX_EVENTS}", file=sys.stderr)
        return 2

    try:
        while True:
            with begin_ingestion_audit(
                args.database,
                AUDIT_TARGET,
                requested_limit=args.limit,
            ) as audit:
                existing_ids = load_existing_ids(args.database, "events")
                data = fetch_events(
                    limit=args.limit,
                    timeout=args.timeout,
                    existing_ids=existing_ids,
                )
                saved = save_events(args.database, data)
                audit.set_changes(
                    new_rows=saved["inserted"],
                    refreshed_rows=saved["updated"],
                    selected_rows=saved["total"],
                )
                print(
                    f"Database {args.database}: {saved['inserted']} inserted, "
                    f"{saved['updated']} updated, {saved['staged']} staged "
                    f"({data['pages_scanned']} event pages scanned)",
                    file=sys.stderr,
                )
                _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except (WhoEventsError, IncrementalStateError, IngestionAuditError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
