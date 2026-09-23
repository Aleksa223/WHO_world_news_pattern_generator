"""Fetch WHO Statements and store them in a dedicated SQLite database.

WHO publishes Statements in the same public Sitefinity/OData feed as its
other newsroom content. The endpoint does not allow ``NewsType`` in an OData
``$filter``, so this module pages through the feed and keeps only records whose
news type is ``Statement``.
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
STATEMENT_NEWS_TYPE = "Statement"
DEFAULT_TIMEOUT = 30
PAGE_SIZE = 100
MAX_STATEMENTS = 1000
MAX_SCANNED_ITEMS = 20_000
DEFAULT_DATABASE = Path("articles/statement_news.db")


class WhoStatementsError(RuntimeError):
    """Raised when WHO Statements cannot be downloaded or saved."""


def _statement_url(item_path: str | None) -> str | None:
    if not item_path:
        return None
    return WHO_NEWS_ITEM_URL + item_path.lstrip("/")


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert WHO field names into the database schema."""
    return {
        "id": item.get("Id"),
        "title": item.get("Title"),
        "news_type": item.get("NewsType"),
        "published_at": item.get("PublicationDateAndTime"),
        "formatted_date": item.get("FormatedDate"),
        "url": _statement_url(item.get("ItemDefaultUrl")),
    }


def _is_statement(item: dict[str, Any]) -> bool:
    news_type = item.get("NewsType")
    return (
        isinstance(news_type, str)
        and news_type.strip().casefold() == STATEMENT_NEWS_TYPE.casefold()
    )


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
            "User-Agent": "who-statements/1.0 (+personal news data project)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise WhoStatementsError(f"WHO API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WhoStatementsError(f"Could not connect to WHO API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise WhoStatementsError("WHO API request timed out") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WhoStatementsError("WHO API returned an invalid JSON response") from exc

    raw_items = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        raise WhoStatementsError("WHO API response did not contain a 'value' list")

    return [item for item in raw_items if isinstance(item, dict)]


def fetch_statements(
    limit: int = 10, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fetch the newest WHO Statements from the mixed newsroom feed."""
    if not 1 <= limit <= MAX_STATEMENTS:
        raise ValueError(f"limit must be between 1 and {MAX_STATEMENTS}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    statements: list[dict[str, Any]] = []
    scanned = 0
    exhausted = False

    while len(statements) < limit and scanned < MAX_SCANNED_ITEMS:
        page_size = min(PAGE_SIZE, MAX_SCANNED_ITEMS - scanned)
        page = _fetch_page(skip=scanned, top=page_size, timeout=timeout)
        scanned += len(page)

        for item in page:
            if _is_statement(item):
                statements.append(_normalize_item(item))
                if len(statements) == limit:
                    break

        if len(page) < page_size:
            exhausted = True
            break

    return {
        "source": WHO_API_URL,
        "news_type": STATEMENT_NEWS_TYPE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(statements),
        "scanned": scanned,
        "scan_limit_reached": (
            not exhausted
            and scanned >= MAX_SCANNED_ITEMS
            and len(statements) < limit
        ),
        "items": statements,
    }


def save_statements(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update Statements using the stable WHO item ID."""
    database.parent.mkdir(parents=True, exist_ok=True)
    items = [
        item
        for item in data.get("items", [])
        if isinstance(item, dict) and item.get("id")
    ]
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS statements (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    news_type TEXT NOT NULL,
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
                CREATE VIEW IF NOT EXISTS stg_statements AS
                SELECT
                    id,
                    title,
                    news_type,
                    published_at,
                    formatted_date,
                    url,
                    first_seen_at,
                    last_seen_at
                FROM statements
                WHERE LOWER(TRIM(news_type)) = 'statement'
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_statements_published_at
                ON statements (published_at DESC)
                """
            )

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM statements WHERE id IN ({placeholders})", ids
                )
                existing_ids = {row[0] for row in rows}

            connection.executemany(
                """
                INSERT INTO statements (
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
                        item.get("news_type") or STATEMENT_NEWS_TYPE,
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
                "SELECT COUNT(*) FROM stg_statements"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise WhoStatementsError(
            f"Could not save Statements to {database}: {exc}"
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
    print(f"Saved {data['count']} WHO Statements to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download the newest WHO Statements into SQLite."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help=(
            f"number of Statements to fetch, up to {MAX_STATEMENTS} "
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
    if args.limit > MAX_STATEMENTS:
        print(f"error: --limit cannot exceed {MAX_STATEMENTS}", file=sys.stderr)
        return 2

    try:
        while True:
            data = fetch_statements(limit=args.limit, timeout=args.timeout)
            saved = save_statements(args.database, data)
            print(
                f"Database {args.database}: {saved['inserted']} inserted, "
                f"{saved['updated']} updated, {saved['staged']} staged "
                f"({data['scanned']} newsroom items scanned)",
                file=sys.stderr,
            )
            if data["scan_limit_reached"]:
                print(
                    "warning: scan limit reached before the requested number "
                    "of Statements was found",
                    file=sys.stderr,
                )
            _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except WhoStatementsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
