"""Apply source-specific publication-date retention to raw news databases."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


DEFAULT_RETENTION_DAYS = 90
WHO_NEWS_RETENTION_DAYS = 365
SQLITE_BUSY_TIMEOUT_MS = 30_000
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RetentionError(RuntimeError):
    """Raised when retention cannot be applied safely."""


@dataclass(frozen=True)
class RetentionTarget:
    """One explicitly allowed raw article table."""

    name: str
    database: str
    table: str
    date_column: str = "published_at"
    retention_days: int = DEFAULT_RETENTION_DAYS


@dataclass(frozen=True)
class RetentionResult:
    """Deletion counts for one raw article table."""

    name: str
    database: str
    table: str
    date_column: str
    retention_days: int
    cutoff_utc: str
    eligible: int
    deleted: int
    remaining: int
    invalid_or_missing_dates: int


# Use an explicit allowlist so backup SQLite files are never cleaned by a glob.
RETENTION_TARGETS = (
    RetentionTarget(
        name="who_news",
        database="articles/who_news.db",
        table="articles",
        retention_days=WHO_NEWS_RETENTION_DAYS,
    ),
    RetentionTarget(
        name="tech_news",
        database="tech_articles/tech_news.db",
        table="tech_articles",
    ),
    RetentionTarget(
        name="economic_news",
        database="economic_articles/economic_news.db",
        table="economic_articles",
    ),
)


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise RetentionError(f"Unsafe SQLite identifier: {identifier!r}")
    return f'"{identifier}"'


def _utc_datetime(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return _utc_datetime(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def calculate_cutoff(
    *,
    as_of: datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> datetime:
    """Return the strict UTC cutoff used by the retention policy."""
    if retention_days <= 0:
        raise ValueError("retention_days must be greater than zero")
    return _utc_datetime(as_of) - timedelta(days=retention_days)


def parse_utc_datetime(value: str) -> datetime:
    """Parse an ISO date or timestamp and normalize it to UTC."""
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("must be a non-empty ISO date or timestamp")
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be an ISO date or timestamp, for example 2026-10-16T06:00:00Z"
        ) from exc
    return _utc_datetime(parsed)


def _resolve_database(project_root: Path, target: RetentionTarget) -> Path:
    root = project_root.resolve()
    database = (root / target.database).resolve()
    try:
        database.relative_to(root)
    except ValueError as exc:
        raise RetentionError(
            f"Retention database is outside the project root: {database}"
        ) from exc
    return database


def _connect_existing(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise RetentionError(f"Retention database does not exist: {database}")
    try:
        connection = sqlite3.connect(
            f"{database.as_uri()}?mode=rw",
            uri=True,
            timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
        )
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        return connection
    except sqlite3.Error as exc:
        raise RetentionError(
            f"Could not open retention database {database}: {exc}"
        ) from exc


def _validate_schema(database: Path, target: RetentionTarget) -> None:
    table = _quote_identifier(target.table)
    with closing(_connect_existing(database)) as connection:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (target.table,),
        ).fetchone()
        if table_exists is None:
            raise RetentionError(
                f"Expected table {target.table!r} is missing from {database}"
            )
        columns = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if target.date_column not in columns:
            raise RetentionError(
                f"Expected date column {target.date_column!r} is missing from "
                f"{database}:{target.table}"
            )


def _clean_target(
    database: Path,
    target: RetentionTarget,
    cutoff: datetime,
    *,
    retention_days: int,
    dry_run: bool,
) -> RetentionResult:
    table = _quote_identifier(target.table)
    date_column = _quote_identifier(target.date_column)
    cutoff_text = _format_utc(cutoff)

    connection = _connect_existing(database)
    try:
        connection.execute("BEGIN" if dry_run else "BEGIN IMMEDIATE")
        eligible = int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE julianday({date_column}) < julianday(?)",
                (cutoff_text,),
            ).fetchone()[0]
        )
        invalid_or_missing_dates = int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE {date_column} IS NULL "
                f"OR TRIM({date_column}) = '' "
                f"OR julianday({date_column}) IS NULL"
            ).fetchone()[0]
        )

        deleted = 0
        if not dry_run:
            cursor = connection.execute(
                f"DELETE FROM {table} "
                f"WHERE julianday({date_column}) < julianday(?)",
                (cutoff_text,),
            )
            deleted = cursor.rowcount

        remaining = int(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise RetentionError(
            f"Could not apply retention to {database}:{target.table}: {exc}"
        ) from exc
    finally:
        connection.close()

    return RetentionResult(
        name=target.name,
        database=target.database,
        table=target.table,
        date_column=target.date_column,
        retention_days=retention_days,
        cutoff_utc=cutoff_text,
        eligible=eligible,
        deleted=deleted,
        remaining=remaining,
        invalid_or_missing_dates=invalid_or_missing_dates,
    )


def cleanup_old_articles(
    project_root: Path,
    *,
    retention_days: int | None = None,
    as_of: datetime | None = None,
    dry_run: bool = False,
    targets: Sequence[RetentionTarget] = RETENTION_TARGETS,
) -> dict[str, object]:
    """Apply each target's policy, or one explicit override, to all targets."""
    as_of_utc = _utc_datetime(as_of)
    if retention_days is not None and retention_days <= 0:
        raise ValueError("retention_days must be greater than zero")

    resolved_targets = []
    for target in targets:
        effective_retention_days = (
            retention_days
            if retention_days is not None
            else target.retention_days
        )
        cutoff = calculate_cutoff(
            as_of=as_of_utc,
            retention_days=effective_retention_days,
        )
        resolved_targets.append(
            (
                target,
                _resolve_database(project_root, target),
                effective_retention_days,
                cutoff,
            )
        )

    # Validate every target before deleting from any of them.
    for target, database, _, _ in resolved_targets:
        _validate_schema(database, target)

    results = [
        _clean_target(
            database,
            target,
            cutoff,
            retention_days=effective_retention_days,
            dry_run=dry_run,
        )
        for target, database, effective_retention_days, cutoff in resolved_targets
    ]
    return {
        "retention_days_override": retention_days,
        "as_of_utc": _format_utc(as_of_utc),
        "dry_run": dry_run,
        "eligible_total": sum(result.eligible for result in results),
        "deleted_total": sum(result.deleted for result in results),
        "databases": [asdict(result) for result in results],
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply configured publication-date retention to WHO, Tech, and "
            "Economic articles."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="project directory containing the raw SQLite databases",
    )
    parser.add_argument(
        "--retention-days",
        type=_positive_int,
        default=None,
        help=(
            "override the configured retention for every database "
            f"(default: WHO {WHO_NEWS_RETENTION_DAYS} days; Tech and Economic "
            f"{DEFAULT_RETENTION_DAYS} days)"
        ),
    )
    parser.add_argument(
        "--as-of",
        type=parse_utc_datetime,
        help="optional ISO UTC time used instead of the current time",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report eligible rows without deleting them",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = cleanup_old_articles(
            args.project_root,
            retention_days=args.retention_days,
            as_of=args.as_of,
            dry_run=args.dry_run,
        )
    except (RetentionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
