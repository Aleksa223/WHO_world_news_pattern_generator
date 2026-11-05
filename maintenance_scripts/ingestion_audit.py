"""Durable per-source ingestion audit records for the news pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


AUDIT_TABLE = "ingestion_audit"
PIPELINE_RUN_ID_ENV = "NEWS_PIPELINE_RUN_ID"
PIPELINE_ATTEMPT_ENV = "NEWS_PIPELINE_ATTEMPT"
SQLITE_BUSY_TIMEOUT_MS = 30_000
MAX_ERROR_MESSAGE_LENGTH = 2_000
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_AUDIT_STATUSES = {"running", "succeeded", "failed", "snapshot"}


class IngestionAuditError(RuntimeError):
    """Raised when ingestion audit state cannot be recorded safely."""


@dataclass(frozen=True)
class AuditTarget:
    """Raw table whose ingestion metrics should be audited."""

    source_name: str
    table: str
    date_column: str | None = "published_at"


@dataclass(frozen=True)
class SourceMetrics:
    """Point-in-time metrics calculated from one raw source table."""

    total_rows: int
    oldest_published_at: str | None
    newest_published_at: str | None
    published_today_rows: int | None


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise IngestionAuditError(f"Unsafe SQLite identifier: {identifier!r}")
    return f'"{identifier}"'


def _utc_datetime(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return _utc_datetime(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_error_message(error: BaseException) -> str:
    message = " ".join(str(error).split()) or error.__class__.__name__
    return message[:MAX_ERROR_MESSAGE_LENGTH]


def _pipeline_run_id(value: str | None, started_at: datetime) -> str:
    candidate = (value or os.environ.get(PIPELINE_RUN_ID_ENV) or "").strip()
    if candidate:
        return candidate[:500]
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    return f"manual:{timestamp}:{uuid.uuid4().hex[:12]}"


def _attempt_number(value: int | None) -> int | None:
    if value is not None:
        if value <= 0:
            raise ValueError("attempt_number must be greater than zero")
        return value
    raw_value = os.environ.get(PIPELINE_ATTEMPT_ENV)
    if not raw_value:
        return None
    try:
        parsed = int(raw_value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _connect(database: Path) -> sqlite3.Connection:
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            database,
            timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
        )
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        return connection
    except (OSError, sqlite3.Error) as exc:
        raise IngestionAuditError(
            f"Could not open ingestion audit database {database}: {exc}"
        ) from exc


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            audit_id TEXT PRIMARY KEY,
            pipeline_run_id TEXT NOT NULL,
            attempt_number INTEGER,
            source_name TEXT NOT NULL,
            source_table TEXT NOT NULL,
            date_column TEXT,
            status TEXT NOT NULL CHECK (
                status IN ('running', 'succeeded', 'failed', 'snapshot')
            ),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            metric_date_utc TEXT NOT NULL,
            requested_limit INTEGER,
            selected_rows INTEGER,
            new_rows INTEGER NOT NULL DEFAULT 0 CHECK (new_rows >= 0),
            refreshed_rows INTEGER NOT NULL DEFAULT 0 CHECK (refreshed_rows >= 0),
            deleted_rows INTEGER NOT NULL DEFAULT 0 CHECK (deleted_rows >= 0),
            total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
            oldest_published_at TEXT,
            newest_published_at TEXT,
            published_today_rows INTEGER CHECK (
                published_today_rows IS NULL OR published_today_rows >= 0
            ),
            retention_days INTEGER,
            retention_cutoff_utc TEXT,
            error_type TEXT,
            error_message TEXT
        )
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{AUDIT_TABLE}_pipeline_source
        ON {AUDIT_TABLE} (pipeline_run_id, source_name, started_at)
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{AUDIT_TABLE}_status_started
        ON {AUDIT_TABLE} (status, started_at)
        """
    )


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def calculate_source_metrics(
    connection: sqlite3.Connection,
    target: AuditTarget,
    *,
    as_of: datetime | None = None,
) -> SourceMetrics:
    """Calculate total, date range, and UTC-today counts for a raw table."""
    table = _quote_identifier(target.table)
    if not _table_exists(connection, target.table):
        return SourceMetrics(
            total_rows=0,
            oldest_published_at=None,
            newest_published_at=None,
            published_today_rows=None if target.date_column is None else 0,
        )

    total_rows = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    if target.date_column is None:
        return SourceMetrics(
            total_rows=total_rows,
            oldest_published_at=None,
            newest_published_at=None,
            published_today_rows=None,
        )

    columns = {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if target.date_column not in columns:
        raise IngestionAuditError(
            f"Date column {target.date_column!r} is missing from {target.table!r}"
        )
    date_column = _quote_identifier(target.date_column)
    oldest = connection.execute(
        f"SELECT {date_column} FROM {table} "
        f"WHERE julianday({date_column}) IS NOT NULL "
        f"ORDER BY julianday({date_column}) ASC LIMIT 1"
    ).fetchone()
    newest = connection.execute(
        f"SELECT {date_column} FROM {table} "
        f"WHERE julianday({date_column}) IS NOT NULL "
        f"ORDER BY julianday({date_column}) DESC LIMIT 1"
    ).fetchone()
    metric_date = _utc_datetime(as_of).date().isoformat()
    published_today_rows = int(
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE date({date_column}) = ?",
            (metric_date,),
        ).fetchone()[0]
    )
    return SourceMetrics(
        total_rows=total_rows,
        oldest_published_at=str(oldest[0]) if oldest else None,
        newest_published_at=str(newest[0]) if newest else None,
        published_today_rows=published_today_rows,
    )


class IngestionAuditRun:
    """Context manager for one fetch/save/output iteration."""

    def __init__(
        self,
        *,
        database: Path,
        target: AuditTarget,
        audit_id: str,
        pipeline_run_id: str,
    ) -> None:
        self.database = database
        self.target = target
        self.audit_id = audit_id
        self.pipeline_run_id = pipeline_run_id
        self.selected_rows: int | None = None
        self.new_rows = 0
        self.refreshed_rows = 0

    def __enter__(self) -> IngestionAuditRun:
        return self

    def set_changes(
        self,
        *,
        new_rows: int,
        refreshed_rows: int,
        selected_rows: int | None = None,
    ) -> None:
        """Attach authoritative save counts before the run is completed."""
        values = (new_rows, refreshed_rows)
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("new_rows and refreshed_rows must be non-negative integers")
        if selected_rows is None:
            selected_rows = new_rows + refreshed_rows
        if not isinstance(selected_rows, int) or selected_rows < 0:
            raise ValueError("selected_rows must be a non-negative integer")
        self.new_rows = new_rows
        self.refreshed_rows = refreshed_rows
        self.selected_rows = selected_rows

    def _finish(
        self,
        *,
        status: str,
        error: BaseException | None = None,
        now: datetime | None = None,
    ) -> None:
        if status not in _AUDIT_STATUSES - {"running"}:
            raise ValueError(f"Unsupported completed audit status: {status}")
        completed_at = _utc_datetime(now)
        connection = _connect(self.database)
        try:
            with connection:
                _ensure_schema(connection)
                metrics = calculate_source_metrics(
                    connection,
                    self.target,
                    as_of=completed_at,
                )
                cursor = connection.execute(
                    f"""
                    UPDATE {AUDIT_TABLE}
                    SET status = ?, completed_at = ?, updated_at = ?,
                        metric_date_utc = ?, selected_rows = ?, new_rows = ?,
                        refreshed_rows = ?, total_rows = ?,
                        oldest_published_at = ?, newest_published_at = ?,
                        published_today_rows = ?, error_type = ?, error_message = ?
                    WHERE audit_id = ?
                    """,
                    (
                        status,
                        _format_utc(completed_at),
                        _format_utc(completed_at),
                        completed_at.date().isoformat(),
                        self.selected_rows,
                        self.new_rows,
                        self.refreshed_rows,
                        metrics.total_rows,
                        metrics.oldest_published_at,
                        metrics.newest_published_at,
                        metrics.published_today_rows,
                        error.__class__.__name__ if error else None,
                        _safe_error_message(error) if error else None,
                        self.audit_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise IngestionAuditError(
                        f"Audit row {self.audit_id!r} no longer exists"
                    )
        except sqlite3.Error as exc:
            raise IngestionAuditError(
                f"Could not finish ingestion audit in {self.database}: {exc}"
            ) from exc
        finally:
            connection.close()

    def succeed(self, *, now: datetime | None = None) -> None:
        self._finish(status="succeeded", now=now)

    def fail(
        self,
        error: BaseException,
        *,
        now: datetime | None = None,
    ) -> None:
        self._finish(status="failed", error=error, now=now)

    def snapshot(self, *, now: datetime | None = None) -> None:
        self._finish(status="snapshot", now=now)

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is None:
            self.succeed()
        else:
            try:
                self.fail(exc)
            except Exception as audit_error:  # Preserve the source exception.
                warnings.warn(
                    f"Could not record failed ingestion audit: {audit_error}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return False


def begin_ingestion_audit(
    database: Path,
    target: AuditTarget,
    *,
    requested_limit: int | None = None,
    pipeline_run_id: str | None = None,
    attempt_number: int | None = None,
    now: datetime | None = None,
) -> IngestionAuditRun:
    """Insert a running audit row and return its completion context."""
    if requested_limit is not None and requested_limit <= 0:
        raise ValueError("requested_limit must be greater than zero")
    _quote_identifier(target.table)
    if target.date_column is not None:
        _quote_identifier(target.date_column)

    started_at = _utc_datetime(now)
    audit_id = uuid.uuid4().hex
    run_id = _pipeline_run_id(pipeline_run_id, started_at)
    attempt = _attempt_number(attempt_number)
    connection = _connect(database)
    try:
        with connection:
            _ensure_schema(connection)
            metrics = calculate_source_metrics(connection, target, as_of=started_at)
            connection.execute(
                f"""
                INSERT INTO {AUDIT_TABLE} (
                    audit_id, pipeline_run_id, attempt_number, source_name,
                    source_table, date_column, status, started_at, updated_at,
                    metric_date_utc, requested_limit, total_rows,
                    oldest_published_at, newest_published_at,
                    published_today_rows
                ) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    run_id,
                    attempt,
                    target.source_name,
                    target.table,
                    target.date_column,
                    _format_utc(started_at),
                    _format_utc(started_at),
                    started_at.date().isoformat(),
                    requested_limit,
                    metrics.total_rows,
                    metrics.oldest_published_at,
                    metrics.newest_published_at,
                    metrics.published_today_rows,
                ),
            )
    except sqlite3.Error as exc:
        raise IngestionAuditError(
            f"Could not begin ingestion audit in {database}: {exc}"
        ) from exc
    finally:
        connection.close()
    return IngestionAuditRun(
        database=database,
        target=target,
        audit_id=audit_id,
        pipeline_run_id=run_id,
    )


def apply_retention_audit(
    connection: sqlite3.Connection,
    *,
    pipeline_run_id: str,
    target: AuditTarget,
    deleted_rows: int,
    retention_days: int,
    cutoff_utc: str,
    as_of: datetime | None = None,
) -> None:
    """Update the latest matching audit row inside a retention transaction."""
    if deleted_rows < 0:
        raise ValueError("deleted_rows must be non-negative")
    completed_at = _utc_datetime(as_of)
    _ensure_schema(connection)
    audit_row = connection.execute(
        f"""
        SELECT audit_id
        FROM {AUDIT_TABLE}
        WHERE pipeline_run_id = ? AND source_name = ?
        ORDER BY started_at DESC, audit_id DESC
        LIMIT 1
        """,
        (pipeline_run_id, target.source_name),
    ).fetchone()
    if audit_row is None:
        raise IngestionAuditError(
            f"No audit row for {target.source_name!r} in run {pipeline_run_id!r}"
        )
    metrics = calculate_source_metrics(connection, target, as_of=completed_at)
    connection.execute(
        f"""
        UPDATE {AUDIT_TABLE}
        SET deleted_rows = deleted_rows + ?, total_rows = ?,
            oldest_published_at = ?, newest_published_at = ?,
            published_today_rows = ?, metric_date_utc = ?,
            retention_days = ?, retention_cutoff_utc = ?, updated_at = ?
        WHERE audit_id = ?
        """,
        (
            deleted_rows,
            metrics.total_rows,
            metrics.oldest_published_at,
            metrics.newest_published_at,
            metrics.published_today_rows,
            completed_at.date().isoformat(),
            retention_days,
            cutoff_utc,
            _format_utc(completed_at),
            str(audit_row[0]),
        ),
    )


def _configured_jobs():
    project_root = Path(__file__).resolve().parents[1]
    dags_directory = project_root / "dags"
    if str(dags_directory) not in sys.path:
        sys.path.insert(0, str(dags_directory))
    from news_pipeline_config import ALL_FETCH_JOBS

    return ALL_FETCH_JOBS


def snapshot_all_sources(
    project_root: Path,
    *,
    pipeline_run_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create baseline audit rows for all configured raw databases."""
    snapshot_at = _utc_datetime(now)
    run_id = _pipeline_run_id(pipeline_run_id, snapshot_at)
    rows: list[dict[str, Any]] = []
    for job in _configured_jobs():
        audit = begin_ingestion_audit(
            project_root / job.database,
            AuditTarget(job.source_name, job.table, job.date_column),
            pipeline_run_id=run_id,
            now=snapshot_at,
        )
        audit.snapshot(now=snapshot_at)
        connection = _connect(project_root / job.database)
        try:
            cursor = connection.execute(
                f"SELECT * FROM {AUDIT_TABLE} WHERE audit_id = ?",
                (audit.audit_id,),
            )
            row = cursor.fetchone()
            columns = [item[0] for item in cursor.description]
            if row is None:
                raise IngestionAuditError(
                    f"Snapshot audit row {audit.audit_id!r} no longer exists"
                )
            rows.append(dict(zip(columns, row, strict=True)))
        finally:
            connection.close()
    return {
        "pipeline_run_id": run_id,
        "status": "snapshot",
        "sources": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create baseline ingestion audit rows for configured sources."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--run-id", help="optional shared pipeline run identifier")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = snapshot_all_sources(
            args.project_root.resolve(),
            pipeline_run_id=args.run_id,
        )
    except (IngestionAuditError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
