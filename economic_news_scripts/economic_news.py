"""Fetch recent economic news from the GDELT DOC 2.0 API.

GDELT is a free, open news index and does not require an API key. Article
metadata is normalized and upserted into SQLite using a stable hash of each
canonical article URL.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from maintenance_scripts.ingestion_audit import (  # noqa: E402
    AuditTarget,
    IngestionAuditError,
    begin_ingestion_audit,
)


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_PROVIDER = "GDELT"
ECONOMIC_CATEGORY = "economic"
DEFAULT_QUERY = (
    '(economy OR inflation OR GDP OR unemployment OR recession OR '
    '"interest rates" OR "central bank" OR "fiscal policy")'
)
ENGLISH_SOURCE_FILTER = "sourcelang:english"
DEFAULT_TIMESPAN = "1d"
DEFAULT_TIMEOUT = 30
DEFAULT_LIMIT = 200
MAX_ARTICLES = 250
DEFAULT_DATABASE = Path("economic_articles/economic_news.db")
AUDIT_TARGET = AuditTarget(
    source_name="economic_news",
    table="economic_articles",
    date_column="published_at",
)
_TIMESPAN_PATTERN = re.compile(
    r"^[1-9][0-9]*(?:min|h|hours?|d|days?|w|weeks?|m|months?)$",
    re.IGNORECASE,
)
_SOURCE_LANGUAGE_OPERATOR_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9_])(-?sourcelang(?:not)?):([a-z0-9_-]+)"
)
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


class EconomicNewsError(RuntimeError):
    """Raised when economic news cannot be downloaded, parsed, or saved."""


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(html.unescape(value).split())
    return cleaned or None


def _is_english_language(value: Any) -> bool:
    """Return whether a GDELT language label identifies English."""
    cleaned = _clean_text(value)
    if cleaned is None:
        return False
    normalized = cleaned.casefold().replace("_", "-")
    return (
        normalized == "en"
        or normalized.startswith("en-")
        or normalized == "english"
        or normalized.startswith("english ")
    )


def _english_only_query(query: str) -> str:
    """Add GDELT's English source filter and reject conflicting filters."""
    operators = _SOURCE_LANGUAGE_OPERATOR_PATTERN.findall(query)
    if not operators:
        return f"{query} {ENGLISH_SOURCE_FILTER}"

    for operator, language in operators:
        if (
            operator.casefold() != "sourcelang"
            or language.casefold() not in {"english", "eng"}
        ):
            raise ValueError(
                "query cannot override the required English source-language filter"
            )
    return query


def _canonical_url(value: Any) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    try:
        parsed = urlsplit(cleaned)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
        return None

    host = hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (
        parsed.scheme.casefold() == "http" and port == 80
    ) or (
        parsed.scheme.casefold() == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    query_pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path or "/",
            urlencode(query_pairs, doseq=True),
            "",
        )
    )


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _gdelt_datetime(value: Any) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    for date_format in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            parsed = datetime.strptime(cleaned, date_format)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc).isoformat()

    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _valid_timespan(value: str) -> str:
    cleaned = value.strip()
    if not _TIMESPAN_PATTERN.fullmatch(cleaned):
        raise argparse.ArgumentTypeError(
            "must look like 15min, 12h, 1d, 1week, or 3months"
        )
    return cleaned


def _build_request_url(
    query: str,
    limit: int,
    timespan: str,
) -> str:
    parameters = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": limit,
        "sort": "datedesc",
        "timespan": timespan,
    }
    return f"{GDELT_DOC_API_URL}?{urlencode(parameters)}"


def _request_json(url: str, timeout: int) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "who-world-news/1.0 (+economic news pipeline)",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            raise EconomicNewsError(
                "The GDELT API rate limit was reached; wait at least "
                "five seconds before retrying"
            ) from exc
        raise EconomicNewsError(
            f"GDELT API returned HTTP {exc.code} for {url}"
        ) from exc
    except URLError as exc:
        raise EconomicNewsError(
            f"Could not connect to the GDELT API: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise EconomicNewsError("The GDELT API request timed out") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EconomicNewsError("The GDELT API returned invalid JSON") from exc


def _normalize_article(
    article: dict[str, Any],
    query: str,
) -> dict[str, Any] | None:
    if not _is_english_language(article.get("language")):
        return None
    url = _canonical_url(article.get("url"))
    title = _clean_text(article.get("title"))
    if url is None or title is None:
        return None

    source = _clean_text(article.get("domain"))
    if source is None:
        source = urlsplit(url).hostname
    if source:
        source = source.casefold().removeprefix("www.")

    raw_seen_date = _clean_text(article.get("seendate"))
    seen_at = _gdelt_datetime(raw_seen_date)
    return {
        "id": _article_id(url),
        "provider": GDELT_PROVIDER,
        "item_type": "article",
        "title": title,
        "description": None,
        "keywords": query,
        "snippet": None,
        "url": url,
        "mobile_url": _canonical_url(article.get("url_mobile")),
        "image_url": _canonical_url(article.get("socialimage")),
        "language": _clean_text(article.get("language")),
        # GDELT's seen date is the best available article-time proxy, but is
        # not guaranteed to be the publisher's original publication time.
        "published_at": seen_at,
        "gdelt_seen_at": seen_at,
        "gdelt_seen_date": raw_seen_date,
        "source": source,
        "source_country": _clean_text(article.get("sourcecountry")),
        "feed": "gdelt_doc",
        "query": query,
        "category": ECONOMIC_CATEGORY,
        "categories": [ECONOMIC_CATEGORY],
    }


def fetch_economic_news(
    limit: int = DEFAULT_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
    query: str = DEFAULT_QUERY,
    timespan: str = DEFAULT_TIMESPAN,
) -> dict[str, Any]:
    """Fetch and normalize recent economic-news article metadata."""
    if not 1 <= limit <= MAX_ARTICLES:
        raise ValueError(f"limit must be between 1 and {MAX_ARTICLES}")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    cleaned_query = _clean_text(query)
    if cleaned_query is None:
        raise ValueError("query must not be empty")
    effective_query = _english_only_query(cleaned_query)
    if not _TIMESPAN_PATTERN.fullmatch(timespan.strip()):
        raise ValueError("timespan has an unsupported format")

    request_url = _build_request_url(effective_query, limit, timespan.strip())
    payload = _request_json(request_url, timeout)
    if not isinstance(payload, dict):
        raise EconomicNewsError("The GDELT response was not an object")
    raw_articles = payload.get("articles")
    if not isinstance(raw_articles, list):
        raise EconomicNewsError(
            "The GDELT response did not contain an articles list"
        )

    articles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for feed_rank, raw_article in enumerate(raw_articles, start=1):
        if not isinstance(raw_article, dict):
            continue
        normalized = _normalize_article(raw_article, effective_query)
        if normalized is None or normalized["id"] in seen_ids:
            continue
        normalized["feed_rank"] = feed_rank
        seen_ids.add(normalized["id"])
        articles.append(normalized)

    return {
        "source": request_url,
        "provider": GDELT_PROVIDER,
        "feed": "gdelt_doc",
        "query": effective_query,
        "timespan": timespan.strip(),
        "category": ECONOMIC_CATEGORY,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "available": len(raw_articles),
        "skipped": len(raw_articles) - len(articles),
        "items": articles,
    }


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS economic_articles (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            item_type TEXT NOT NULL,
            title TEXT NOT NULL,
            title_original TEXT NOT NULL,
            title_english TEXT,
            translation_source_language TEXT,
            translation_status TEXT NOT NULL DEFAULT 'pending',
            translation_provider TEXT,
            translated_at TEXT,
            description TEXT,
            keywords TEXT,
            snippet TEXT,
            url TEXT NOT NULL,
            mobile_url TEXT,
            image_url TEXT,
            language TEXT,
            published_at TEXT,
            gdelt_seen_at TEXT,
            gdelt_seen_date TEXT,
            source TEXT,
            source_country TEXT,
            feed TEXT NOT NULL,
            feed_rank INTEGER,
            query TEXT NOT NULL,
            category TEXT NOT NULL,
            categories_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """
    )
    existing_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(economic_articles)")
    }
    added_columns = {
        "gdelt_seen_at": "TEXT",
        "gdelt_seen_date": "TEXT",
        "title_original": "TEXT",
        "title_english": "TEXT",
        "translation_source_language": "TEXT",
        "translation_status": "TEXT NOT NULL DEFAULT 'pending'",
        "translation_provider": "TEXT",
        "translated_at": "TEXT",
    }
    for name, definition in added_columns.items():
        if name not in existing_columns:
            connection.execute(
                f"ALTER TABLE economic_articles ADD COLUMN {name} {definition}"
            )
    connection.execute(
        """
        UPDATE economic_articles
        SET title_original = title
        WHERE title_original IS NULL OR TRIM(title_original) = ''
        """
    )
    connection.execute(
        """
        UPDATE economic_articles
        SET
            title = title_original,
            title_english = title_original,
            translation_source_language = 'en',
            translation_status = 'original_english',
            translation_provider = 'source',
            translated_at = NULL
        WHERE (
            LOWER(REPLACE(TRIM(COALESCE(language, '')), '_', '-')) = 'en'
            OR LOWER(REPLACE(TRIM(COALESCE(language, '')), '_', '-')) LIKE 'en-%'
            OR LOWER(TRIM(COALESCE(language, ''))) LIKE 'english%'
        )
        AND (title_english IS NULL OR TRIM(title_english) = '')
        AND COALESCE(translation_status, 'pending') IN ('pending', 'failed')
        """
    )
    connection.execute(
        """
        UPDATE economic_articles
        SET translation_status = CASE
                WHEN title_english IS NULL OR TRIM(title_english) = ''
                    THEN 'pending'
                ELSE 'translated'
            END
        WHERE translation_status IS NULL OR TRIM(translation_status) = ''
        """
    )
    connection.execute(
        """
        UPDATE economic_articles
        SET title = title_english
        WHERE translation_status IN ('translated', 'original_english')
          AND title_english IS NOT NULL
          AND TRIM(title_english) <> ''
        """
    )
    connection.execute("DROP VIEW IF EXISTS stg_economic_articles")
    connection.execute(
        """
        CREATE VIEW stg_economic_articles AS
        SELECT
            id,
            provider,
            item_type,
            title,
            title_original,
            title_english,
            translation_source_language,
            translation_status,
            translation_provider,
            translated_at,
            description,
            keywords,
            snippet,
            url,
            mobile_url,
            image_url,
            language,
            published_at,
            gdelt_seen_at,
            gdelt_seen_date,
            source,
            source_country,
            feed,
            feed_rank,
            query,
            category,
            categories_json,
            first_seen_at,
            last_seen_at
        FROM economic_articles
        WHERE LOWER(TRIM(category)) = 'economic'
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_economic_articles_published_at
        ON economic_articles (published_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_economic_articles_source
        ON economic_articles (source)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_economic_articles_source_country
        ON economic_articles (source_country)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_economic_articles_translation_status
        ON economic_articles (translation_status)
        """
    )


def save_economic_news(database: Path, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update economic articles using their stable URL hashes."""
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EconomicNewsError(
            f"Could not create database directory for {database}: {exc}"
        ) from exc

    unique_items: dict[str, dict[str, Any]] = {}
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        url = _canonical_url(item.get("url"))
        if title is None or url is None:
            continue
        article_id = _article_id(url)
        unique_items[article_id] = {
            **item,
            "id": article_id,
            "title": title,
            "url": url,
        }

    items = list(unique_items.values())
    fetched_at = str(data.get("fetched_at") or datetime.now(timezone.utc).isoformat())
    default_query = _clean_text(data.get("query")) or DEFAULT_QUERY

    try:
        with closing(sqlite3.connect(database)) as connection, connection:
            _ensure_schema(connection)
            ids = [str(item["id"]) for item in items]
            existing_ids: set[str] = set()
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id FROM economic_articles WHERE id IN ({placeholders})",
                    ids,
                )
                existing_ids = {str(row[0]) for row in rows}

            connection.executemany(
                """
                INSERT INTO economic_articles (
                    id,
                    provider,
                    item_type,
                    title,
                    title_original,
                    title_english,
                    translation_source_language,
                    translation_status,
                    translation_provider,
                    translated_at,
                    description,
                    keywords,
                    snippet,
                    url,
                    mobile_url,
                    image_url,
                    language,
                    published_at,
                    gdelt_seen_at,
                    gdelt_seen_date,
                    source,
                    source_country,
                    feed,
                    feed_rank,
                    query,
                    category,
                    categories_json,
                    first_seen_at,
                    last_seen_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    item_type = excluded.item_type,
                    title = CASE
                        WHEN economic_articles.title_original IS excluded.title_original
                            THEN COALESCE(
                                economic_articles.title_english,
                                economic_articles.title_original,
                                economic_articles.title
                            )
                        ELSE excluded.title
                    END,
                    title_original = excluded.title_original,
                    title_english = CASE
                        WHEN economic_articles.title_original IS excluded.title_original
                            THEN economic_articles.title_english
                        ELSE excluded.title_english
                    END,
                    translation_source_language = CASE
                        WHEN economic_articles.title_original IS excluded.title_original
                            THEN economic_articles.translation_source_language
                        ELSE excluded.translation_source_language
                    END,
                    translation_status = CASE
                        WHEN economic_articles.title_original IS excluded.title_original
                            THEN COALESCE(
                                economic_articles.translation_status,
                                excluded.translation_status
                            )
                        ELSE excluded.translation_status
                    END,
                    translation_provider = CASE
                        WHEN economic_articles.title_original IS excluded.title_original
                            THEN economic_articles.translation_provider
                        ELSE excluded.translation_provider
                    END,
                    translated_at = CASE
                        WHEN economic_articles.title_original IS excluded.title_original
                            THEN economic_articles.translated_at
                        ELSE excluded.translated_at
                    END,
                    description = excluded.description,
                    keywords = excluded.keywords,
                    snippet = excluded.snippet,
                    url = excluded.url,
                    mobile_url = excluded.mobile_url,
                    image_url = excluded.image_url,
                    language = excluded.language,
                    published_at = excluded.published_at,
                    gdelt_seen_at = excluded.gdelt_seen_at,
                    gdelt_seen_date = excluded.gdelt_seen_date,
                    source = excluded.source,
                    source_country = excluded.source_country,
                    feed = excluded.feed,
                    feed_rank = excluded.feed_rank,
                    query = excluded.query,
                    category = excluded.category,
                    categories_json = excluded.categories_json,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (
                        str(item["id"]),
                        _clean_text(item.get("provider")) or GDELT_PROVIDER,
                        _clean_text(item.get("item_type")) or "article",
                        str(item["title"]),
                        str(item["title"]),
                        (
                            str(item["title"])
                            if _is_english_language(item.get("language"))
                            else None
                        ),
                        (
                            "en"
                            if _is_english_language(item.get("language"))
                            else None
                        ),
                        (
                            "original_english"
                            if _is_english_language(item.get("language"))
                            else "pending"
                        ),
                        (
                            "source"
                            if _is_english_language(item.get("language"))
                            else None
                        ),
                        None,
                        _clean_text(item.get("description")),
                        _clean_text(item.get("keywords")) or default_query,
                        _clean_text(item.get("snippet")),
                        str(item["url"]),
                        _canonical_url(item.get("mobile_url")),
                        _canonical_url(item.get("image_url")),
                        _clean_text(item.get("language")),
                        _clean_text(item.get("published_at")),
                        _clean_text(item.get("gdelt_seen_at")),
                        _clean_text(item.get("gdelt_seen_date")),
                        _clean_text(item.get("source")),
                        _clean_text(item.get("source_country")),
                        _clean_text(item.get("feed")) or "gdelt_doc",
                        _nonnegative_int(item.get("feed_rank")),
                        _clean_text(item.get("query")) or default_query,
                        ECONOMIC_CATEGORY,
                        json.dumps([ECONOMIC_CATEGORY], ensure_ascii=False),
                        fetched_at,
                        fetched_at,
                    )
                    for item in items
                ],
            )
            staged = connection.execute(
                "SELECT COUNT(*) FROM stg_economic_articles"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        raise EconomicNewsError(
            f"Could not save economic news to {database}: {exc}"
        ) from exc

    inserted = len(set(ids) - existing_ids)
    return {
        "inserted": inserted,
        "updated": len(items) - inserted,
        "total": len(items),
        "staged": staged,
    }


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _write_json(data: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        try:
            print(rendered, end="")
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or "ascii"
            safe_rendered = rendered.encode(
                encoding, errors="backslashreplace"
            ).decode(encoding)
            print(safe_rendered, end="")
        return
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise EconomicNewsError(
            f"Could not write JSON output to {output}: {exc}"
        ) from exc
    print(f"Saved {data['count']} economic-news articles to {output}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _watch_interval(value: str) -> int:
    parsed = _positive_int(value)
    if parsed < 5:
        raise argparse.ArgumentTypeError(
            "must be at least 5 seconds for the GDELT rate limit"
        )
    return parsed


def _translate_saved_titles(database: Path, timeout: int) -> dict[str, int]:
    try:
        from economic_news_scripts.azure_translate import (
            AzureTranslationError,
            translate_database_from_environment,
        )
    except ModuleNotFoundError:  # Support direct execution from the script folder.
        from azure_translate import (
            AzureTranslationError,
            translate_database_from_environment,
        )

    try:
        return translate_database_from_environment(database, timeout=timeout)
    except AzureTranslationError as exc:
        raise EconomicNewsError(f"title translation failed: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download recent English-language economic news from GDELT "
            "into SQLite."
        )
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_LIMIT,
        help=(
            f"number of articles to fetch, up to {MAX_ARTICLES} "
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
        "--query",
        default=DEFAULT_QUERY,
        help=(
            "GDELT search expression used to identify economic news; an "
            "English source-language filter is always enforced"
        ),
    )
    parser.add_argument(
        "--timespan",
        type=_valid_timespan,
        default=DEFAULT_TIMESPAN,
        help=f"lookback window such as 1d or 1week (default: {DEFAULT_TIMESPAN})",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_TIMEOUT,
        help=f"request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--watch",
        type=_watch_interval,
        metavar="SECONDS",
        help="keep refreshing at this interval until Ctrl+C is pressed",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help=(
            "translate pending titles to English with Azure Translator after "
            "each fetch"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit > MAX_ARTICLES:
        print(f"error: --limit cannot exceed {MAX_ARTICLES}", file=sys.stderr)
        return 2
    if _clean_text(args.query) is None:
        print("error: --query cannot be empty", file=sys.stderr)
        return 2

    try:
        while True:
            with begin_ingestion_audit(
                args.database,
                AUDIT_TARGET,
                requested_limit=args.limit,
            ) as audit:
                data = fetch_economic_news(
                    limit=args.limit,
                    timeout=args.timeout,
                    query=args.query,
                    timespan=args.timespan,
                )
                saved = save_economic_news(args.database, data)
                audit.set_changes(
                    new_rows=saved["inserted"],
                    refreshed_rows=saved["updated"],
                    selected_rows=saved["total"],
                )
                print(
                    f"Database {args.database}: {saved['inserted']} inserted, "
                    f"{saved['updated']} updated, {saved['staged']} staged "
                    f"({data['available']} results returned, "
                    f"{data['skipped']} skipped)",
                    file=sys.stderr,
                )
                if args.translate:
                    translated = _translate_saved_titles(
                        args.database,
                        args.timeout,
                    )
                    print(
                        f"Azure Translator: {translated['translated']} titles "
                        f"translated, {translated['stale']} stale updates skipped "
                        f"({translated['selected']} pending titles selected)",
                        file=sys.stderr,
                    )
                _write_json(data, args.output)
            if args.watch is None:
                return 0
            time.sleep(args.watch)
    except (EconomicNewsError, IngestionAuditError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
