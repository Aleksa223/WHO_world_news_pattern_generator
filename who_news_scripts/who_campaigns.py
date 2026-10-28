"""Fetch WHO campaign titles and store them in a dedicated SQLite database.

WHO publishes campaigns on its campaigns index rather than in the newsroom
JSON feed used by ``who_news.py`` and ``who_statements.py``. This module reads
the official campaigns page, extracts campaign cards, and stores their titles
and URLs without requiring an API key or third-party packages.
"""

from __future__ import annotations

import argparse
import json
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

if __package__:
    from .incremental import (
        IncrementalBatch,
        IncrementalStateError,
        load_existing_ids,
    )
else:  # Support ``python who_news_scripts/who_campaigns.py``.
    from incremental import (
        IncrementalBatch,
        IncrementalStateError,
        load_existing_ids,
    )


WHO_BASE_URL = "https://www.who.int"
WHO_CAMPAIGNS_URL = f"{WHO_BASE_URL}/campaigns"
CAMPAIGN_TYPE = "Campaigns"
DEFAULT_TIMEOUT = 30
MAX_CAMPAIGNS = 1000
DEFAULT_DATABASE = Path("articles/who_campaign_news.db")


class WhoCampaignsError(RuntimeError):
    """Raised when WHO campaigns cannot be downloaded, parsed, or saved."""


def _campaign_path(href: str | None) -> str | None:
    """Return a normalized WHO campaign path for a campaign-card link."""
    if not href:
        return None

    parsed = urlparse(urljoin(WHO_BASE_URL, href.strip()))
    if parsed.netloc.casefold() not in {"who.int", "www.who.int"}:
        return None

    path = parsed.path.rstrip("/")
    if not path.casefold().startswith("/campaigns/"):
        return None
    if path.casefold() == "/campaigns/terms-of-use":
        return None
    return path


class _CampaignCardParser(HTMLParser):
    """Extract campaign links and titles from WHO campaign cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.campaigns: list[dict[str, str]] = []
        self._div_depth = 0
        self._card_depth: int | None = None
        self._title_depth: int | None = None
        self._path: str | None = None
        self._title_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)

        if tag == "div":
            self._div_depth += 1
            if (
                self._card_depth is None
                and attributes.get("role", "").casefold() == "article"
            ):
                self._card_depth = self._div_depth
                self._path = None
                self._title_parts = []

            classes = set((attributes.get("class") or "").split())
            if self._card_depth is not None and "item--title" in classes:
                self._title_depth = self._div_depth

        if tag == "a" and self._card_depth is not None and self._path is None:
            self._path = _campaign_path(attributes.get("href"))

    def handle_data(self, data: str) -> None:
        if self._title_depth is not None:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return

        if self._title_depth == self._div_depth:
            self._title_depth = None

        if self._card_depth == self._div_depth:
            title = " ".join("".join(self._title_parts).split())
            if self._path and title:
                self.campaigns.append(
                    {
                        "id": self._path.removeprefix("/campaigns/"),
                        "title": title,
                        "campaign_type": CAMPAIGN_TYPE,
                        "url": urljoin(WHO_BASE_URL, self._path),
                    }
                )
            self._card_depth = None
            self._title_depth = None
            self._path = None
            self._title_parts = []

        self._div_depth -= 1


def _parse_campaigns(page: str) -> list[dict[str, str]]:
    parser = _CampaignCardParser()
    parser.feed(page)
    parser.close()

    # Preserve page order while guarding against duplicated responsive cards.
    unique: dict[str, dict[str, str]] = {}
    for campaign in parser.campaigns:
        unique.setdefault(campaign["id"], campaign)
    return list(unique.values())


def fetch_campaigns(
    limit: int = 10,
    timeout: int = DEFAULT_TIMEOUT,
    existing_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Fetch unseen campaigns from WHO's official campaigns index."""
    if not 1 <= limit <= MAX_CAMPAIGNS:
        raise ValueError(f"limit must be between 1 and {MAX_CAMPAIGNS}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    request = Request(
        WHO_CAMPAIGNS_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": "who-campaigns/1.0 (+personal news data project)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            page = response.read().decode("utf-8")
    except HTTPError as exc:
        raise WhoCampaignsError(f"WHO returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WhoCampaignsError(f"Could not connect to WHO: {exc.reason}") from exc
    except TimeoutError as exc:
        raise WhoCampaignsError("WHO request timed out") from exc
    except UnicodeDecodeError as exc:
        raise WhoCampaignsError("WHO returned an invalid text response") from exc

    campaigns = _parse_campaigns(page)
    if not campaigns:
        raise WhoCampaignsError("WHO campaigns page contained no campaign cards")

    batch = IncrementalBatch[dict[str, str]](limit, existing_ids)
    for campaign in campaigns:
        batch.consider(campaign, campaign["id"])
        if not batch.needs_unseen:
            break

    return {
        "source": WHO_CAMPAIGNS_URL,
        "campaign_type": CAMPAIGN_TYPE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **batch.metadata(),
        "available": len(campaigns),
        "items": batch.items,
    }


def _is_campaign(item: dict[str, Any]) -> bool:
    campaign_type = item.get("campaign_type")
    return (
        isinstance(campaign_type, str)
        and campaign_type.strip().casefold() == CAMPAIGN_TYPE.casefold()
    )


def save_campaigns(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update campaigns using their stable WHO URL slug."""
    database.parent.mkdir(parents=True, exist_ok=True)
    items = [
        item
        for item in data.get("items", [])
        if (
            isinstance(item, dict)
            and item.get("id")
            and item.get("title")
            and _is_campaign(item)
        )
    ]
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    campaign_type TEXT NOT NULL,
                    url TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE VIEW IF NOT EXISTS stg_campaigns AS
                SELECT
                    id,
                    title,
                    campaign_type,
                    url,
                    first_seen_at,
                    last_seen_at
                FROM campaigns
                WHERE LOWER(TRIM(campaign_type)) = 'campaigns'
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_campaigns_title
                ON campaigns (title)
                """
            )

            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM campaigns WHERE id IN ({placeholders})", ids
                )
                existing_ids = {row[0] for row in rows}

            connection.executemany(
                """
                INSERT INTO campaigns (
                    id, title, campaign_type, url, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    campaign_type = excluded.campaign_type,
                    url = excluded.url,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (
                        str(item["id"]),
                        str(item["title"]),
                        str(item["campaign_type"]),
                        str(item["url"]),
                        fetched_at,
                        fetched_at,
                    )
                    for item in items
                ],
            )
            staged = connection.execute(
                "SELECT COUNT(*) FROM stg_campaigns"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise WhoCampaignsError(
            f"Could not save Campaigns to {database}: {exc}"
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
    print(f"Saved {data['count']} WHO Campaigns to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download WHO campaign titles into SQLite."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help=f"number of Campaigns to fetch, up to {MAX_CAMPAIGNS} (default: 10)",
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
    if args.limit > MAX_CAMPAIGNS:
        print(f"error: --limit cannot exceed {MAX_CAMPAIGNS}", file=sys.stderr)
        return 2

    try:
        while True:
            existing_ids = load_existing_ids(args.database, "campaigns")
            data = fetch_campaigns(
                limit=args.limit,
                timeout=args.timeout,
                existing_ids=existing_ids,
            )
            saved = save_campaigns(args.database, data)
            print(
                f"Database {args.database}: {saved['inserted']} inserted, "
                f"{saved['updated']} updated, {saved['staged']} staged "
                f"({data['available']} campaign cards available)",
                file=sys.stderr,
            )
            _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except (WhoCampaignsError, IncrementalStateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
