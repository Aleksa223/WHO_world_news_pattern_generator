"""Shared helpers for cumulative WHO SQLite ingestion."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Generic, Iterable, TypeVar


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
Item = TypeVar("Item")


class IncrementalStateError(RuntimeError):
    """Raised when an existing WHO ingestion database cannot be inspected."""


def normalize_ids(values: Iterable[object] | None) -> set[str]:
    """Return non-empty IDs as strings for stable API/database comparison."""
    if values is None:
        return set()
    return {str(value) for value in values if value is not None and str(value)}


class IncrementalBatch(Generic[Item]):
    """Select bounded unseen and refresh records while de-duplicating IDs."""

    def __init__(
        self,
        limit: int,
        existing_ids: Iterable[object] | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        self.limit = limit
        self.items: list[Item] = []
        self._existing_ids = normalize_ids(existing_ids)
        self._encountered_ids: set[str] = set()
        self.unseen_count = 0
        self.refreshed_count = 0
        self.existing_encountered = 0

    @property
    def needs_unseen(self) -> bool:
        """Whether the requested unseen-item quota has not been filled."""
        return self.unseen_count < self.limit

    @property
    def encountered_count(self) -> int:
        """Number of distinct valid source IDs considered by this batch."""
        return len(self._encountered_ids)

    def consider(self, item: Item, item_id: object) -> bool:
        """Consider one source item and return whether it was selected."""
        normalized_id = str(item_id) if item_id is not None else ""
        if not normalized_id or normalized_id in self._encountered_ids:
            return False
        self._encountered_ids.add(normalized_id)

        if normalized_id in self._existing_ids:
            self.existing_encountered += 1
            if self.refreshed_count >= self.limit:
                return False
            self.refreshed_count += 1
        else:
            if self.unseen_count >= self.limit:
                return False
            self.unseen_count += 1

        self.items.append(item)
        return True

    def metadata(self) -> dict[str, int]:
        """Return explicit counts for the selected incremental batch."""
        return {
            "count": len(self.items),
            "unseen_count": self.unseen_count,
            "refreshed_count": self.refreshed_count,
            "existing_encountered": self.existing_encountered,
            "skipped_existing": (
                self.existing_encountered - self.refreshed_count
            ),
        }


def load_existing_ids(database: Path, table: str) -> set[str]:
    """Read IDs from an existing SQLite table without creating a database.

    A missing database or table represents a first ingestion and therefore has
    no known IDs. Other SQLite failures are surfaced so a damaged database is
    never silently treated as empty and overwritten.
    """
    if not _IDENTIFIER_PATTERN.fullmatch(table):
        raise ValueError(f"Unsafe SQLite table name: {table!r}")
    if not database.is_file():
        return set()

    try:
        with closing(
            sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        ) as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if table_exists is None:
                return set()
            return normalize_ids(
                row[0] for row in connection.execute(f'SELECT id FROM "{table}"')
            )
    except sqlite3.Error as exc:
        raise IncrementalStateError(
            f"Could not read existing IDs from {database}:{table}: {exc}"
        ) from exc
