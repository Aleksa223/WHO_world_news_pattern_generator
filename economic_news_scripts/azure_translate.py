"""Translate pending economic-news titles to English with Azure Translator.

Credentials are read from environment variables by the CLI. The subscription
key is used only in the HTTPS request header and is never stored in SQLite.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:
    from economic_news_scripts.economic_news import (
        DEFAULT_DATABASE,
        _clean_text,
        _ensure_schema,
    )
except ModuleNotFoundError:  # Support direct execution from the script folder.
    from economic_news import DEFAULT_DATABASE, _clean_text, _ensure_schema


AZURE_TRANSLATOR_PROVIDER = "Azure Translator"
DEFAULT_ENDPOINT = "https://api.cognitive.microsofttranslator.com"
DEFAULT_TIMEOUT = 30
DEFAULT_BATCH_SIZE = 100
DEFAULT_BATCH_CHARACTER_LIMIT = 40_000
MAX_BATCH_SIZE = 1_000
MAX_BATCH_CHARACTERS = 50_000
DEFAULT_RETRIES = 3
_RETRYABLE_HTTP_STATUSES = {408, 429, 500, 503}


class AzureTranslationError(RuntimeError):
    """Raised when Azure configuration, translation, or persistence fails."""


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _batch_size(value: str) -> int:
    parsed = _positive_int(value)
    if parsed > MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(
            f"must not exceed Azure's {MAX_BATCH_SIZE}-item request limit"
        )
    return parsed


def _translation_url(endpoint: str) -> str:
    cleaned = endpoint.strip().rstrip("/")
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise AzureTranslationError("Azure Translator endpoint is invalid") from exc
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise AzureTranslationError(
            "Azure Translator endpoint must be a valid HTTPS URL"
        )
    if parsed.username or parsed.password or parsed.fragment:
        raise AzureTranslationError("Azure Translator endpoint is invalid")

    path = parsed.path.rstrip("/")
    if not path:
        if parsed.hostname.casefold().endswith(".cognitiveservices.azure.com"):
            path = "/translator/text/v3.0/translate"
        else:
            path = "/translate"
    elif not path.casefold().endswith("/translate"):
        path = f"{path}/translate"

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"api-version": "3.0", "to": "en"})
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query), ""))


def _azure_error_code(error: HTTPError) -> str | None:
    try:
        raw_body = error.read()
        payload = json.loads(raw_body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None
    code = payload["error"].get("code")
    return str(code) if code is not None else None


def _retry_delay(attempt: int, error: HTTPError | None = None) -> float:
    if error is not None and error.headers is not None:
        retry_after = error.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except ValueError:
                pass
    return min(2 ** attempt + random.uniform(0.0, 0.25), 8.0)


def _request_translations(
    texts: Sequence[str],
    *,
    key: str,
    region: str | None,
    endpoint: str,
    timeout: int,
    retries: int = DEFAULT_RETRIES,
) -> list[dict[str, str | None]]:
    if not texts:
        return []
    if len(texts) > MAX_BATCH_SIZE:
        raise AzureTranslationError(
            f"An Azure translation batch cannot exceed {MAX_BATCH_SIZE} titles"
        )
    character_count = sum(len(text) for text in texts)
    if character_count > MAX_BATCH_CHARACTERS:
        raise AzureTranslationError(
            "An Azure translation batch cannot exceed "
            f"{MAX_BATCH_CHARACTERS:,} input characters"
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "Ocp-Apim-Subscription-Key": key,
        "X-ClientTraceId": str(uuid.uuid4()),
    }
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region
    body = json.dumps(
        [{"Text": text} for text in texts], ensure_ascii=False
    ).encode("utf-8")
    request = Request(
        _translation_url(endpoint),
        data=body,
        headers=headers,
        method="POST",
    )

    payload: Any = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            break
        except HTTPError as exc:
            service_code = _azure_error_code(exc)
            if exc.code in _RETRYABLE_HTTP_STATUSES and attempt < retries:
                time.sleep(_retry_delay(attempt, exc))
                continue
            suffix = f" (service code {service_code})" if service_code else ""
            raise AzureTranslationError(
                f"Azure Translator returned HTTP {exc.code}{suffix}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            if attempt < retries:
                time.sleep(_retry_delay(attempt))
                continue
            raise AzureTranslationError(
                "Could not connect to Azure Translator after retries"
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AzureTranslationError(
                "Azure Translator returned invalid JSON"
            ) from exc

    if not isinstance(payload, list) or len(payload) != len(texts):
        raise AzureTranslationError(
            "Azure Translator returned an unexpected number of results"
        )

    results: list[dict[str, str | None]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise AzureTranslationError(
                "Azure Translator returned an invalid translation result"
            )
        translations = item.get("translations")
        if not isinstance(translations, list):
            raise AzureTranslationError(
                "Azure Translator returned an invalid translation result"
            )
        english = next(
            (
                translation
                for translation in translations
                if isinstance(translation, dict)
                and str(translation.get("to", "")).casefold() == "en"
            ),
            None,
        )
        translated_text = (
            _clean_text(english.get("text")) if isinstance(english, dict) else None
        )
        if translated_text is None:
            raise AzureTranslationError(
                "Azure Translator returned an empty English title"
            )
        detected = item.get("detectedLanguage")
        source_language = (
            _clean_text(detected.get("language"))
            if isinstance(detected, dict)
            else None
        )
        results.append(
            {"text": translated_text, "source_language": source_language}
        )
    return results


def _title_batches(
    rows: Iterable[tuple[str, str]],
    batch_size: int,
) -> Iterable[list[tuple[str, str]]]:
    batch: list[tuple[str, str]] = []
    characters = 0
    for article_id, title in rows:
        title_characters = len(title)
        if title_characters > MAX_BATCH_CHARACTERS:
            raise AzureTranslationError(
                f"Article {article_id} has a title longer than Azure's input limit"
            )
        if batch and (
            len(batch) >= batch_size
            or characters + title_characters > DEFAULT_BATCH_CHARACTER_LIMIT
        ):
            yield batch
            batch = []
            characters = 0
        batch.append((article_id, title))
        characters += title_characters
    if batch:
        yield batch


def translate_database(
    database: Path,
    *,
    key: str,
    region: str | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, int]:
    """Translate titles that do not yet have an English value in SQLite."""
    clean_key = key.strip()
    if not clean_key:
        raise AzureTranslationError(
            "AZURE_TRANSLATOR_KEY is not set; configure it in your environment"
        )
    clean_region = _clean_text(region)
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if retries < 0:
        raise ValueError("retries cannot be negative")
    if not database.is_file():
        raise AzureTranslationError(
            f"Database {database} does not exist; fetch economic news first"
        )

    try:
        with closing(sqlite3.connect(database)) as connection:
            with connection:
                _ensure_schema(connection)
            query = """
                SELECT id, title_original
                FROM economic_articles
                WHERE (title_english IS NULL OR TRIM(title_english) = '')
                  AND COALESCE(translation_status, 'pending') IN ('pending', 'failed')
                  AND title_original IS NOT NULL
                  AND TRIM(title_original) <> ''
                ORDER BY COALESCE(published_at, last_seen_at) DESC, id
            """
            parameters: tuple[int, ...] = ()
            if limit is not None:
                query += " LIMIT ?"
                parameters = (limit,)
            pending_rows = [
                (str(row[0]), str(row[1]))
                for row in connection.execute(query, parameters)
            ]

            translated = 0
            stale = 0
            for batch in _title_batches(pending_rows, batch_size):
                try:
                    results = _request_translations(
                        [title for _, title in batch],
                        key=clean_key,
                        region=clean_region,
                        endpoint=endpoint,
                        timeout=timeout,
                        retries=retries,
                    )
                except AzureTranslationError:
                    with connection:
                        for article_id, original_title in batch:
                            connection.execute(
                                """
                                UPDATE economic_articles
                                SET translation_status = 'failed'
                                WHERE id = ?
                                  AND title_original IS ?
                                  AND (title_english IS NULL OR TRIM(title_english) = '')
                                """,
                                (article_id, original_title),
                            )
                    raise
                translated_at = datetime.now(timezone.utc).isoformat()
                with connection:
                    for (article_id, original_title), result in zip(batch, results):
                        cursor = connection.execute(
                            """
                            UPDATE economic_articles
                            SET
                                title = ?,
                                title_english = ?,
                                translation_source_language = ?,
                                translation_status = 'translated',
                                translation_provider = ?,
                                translated_at = ?
                            WHERE id = ? AND title_original IS ?
                            """,
                            (
                                result["text"],
                                result["text"],
                                result["source_language"],
                                AZURE_TRANSLATOR_PROVIDER,
                                translated_at,
                                article_id,
                                original_title,
                            ),
                        )
                        if cursor.rowcount == 1:
                            translated += 1
                        else:
                            stale += 1
    except sqlite3.Error as exc:
        raise AzureTranslationError(
            f"Could not translate titles in {database}: {exc}"
        ) from exc

    return {
        "selected": len(pending_rows),
        "translated": translated,
        "stale": stale,
    }


def translate_database_from_environment(
    database: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, int]:
    """Translate a database using Azure settings from environment variables."""
    return translate_database(
        database,
        key=os.environ.get("AZURE_TRANSLATOR_KEY", ""),
        region=os.environ.get("AZURE_TRANSLATOR_REGION"),
        endpoint=os.environ.get("AZURE_TRANSLATOR_ENDPOINT", DEFAULT_ENDPOINT),
        batch_size=batch_size,
        limit=limit,
        timeout=timeout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Translate pending economic-news titles to English with Azure "
            "Translator. Credentials are read from AZURE_TRANSLATOR_KEY and "
            "AZURE_TRANSLATOR_REGION."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"SQLite database path (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=DEFAULT_BATCH_SIZE,
        help=f"titles per Azure request (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        help="translate at most this many pending titles",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_TIMEOUT,
        help=f"request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = translate_database_from_environment(
            args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            timeout=args.timeout,
        )
    except (AzureTranslationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Database {args.database}: {result['translated']} titles translated, "
        f"{result['stale']} stale updates skipped "
        f"({result['selected']} pending titles selected)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
