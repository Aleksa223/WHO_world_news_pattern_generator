"""Create and restore validated SQLite state for ephemeral pipeline runners."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIRECTORY = DEFAULT_PROJECT_ROOT / "dags"
if str(DAGS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(DAGS_DIRECTORY))

from news_pipeline_config import ALL_FETCH_JOBS  # noqa: E402


MANIFEST_FILENAME = "manifest.json"
SNAPSHOT_FORMAT_VERSION = 1
EXPECTED_TABLE_BY_JOB = {
    "news": "articles",
    "campaigns": "campaigns",
    "commentaries": "commentaries",
    "events": "events",
    "speeches": "speeches",
    "statements": "statements",
    "stories": "feature_stories",
    "tech_news": "tech_articles",
    "economic_news": "economic_articles",
}


class PipelineStateError(RuntimeError):
    """Raised when a pipeline-state snapshot is missing, unsafe, or corrupt."""


def _configured_databases() -> tuple[tuple[Path, str], ...]:
    unknown_jobs = {
        job.name for job in ALL_FETCH_JOBS if job.name not in EXPECTED_TABLE_BY_JOB
    }
    if unknown_jobs:
        raise PipelineStateError(
            "No expected SQLite table configured for jobs: "
            + ", ".join(sorted(unknown_jobs))
        )

    databases = tuple(
        (Path(job.database), EXPECTED_TABLE_BY_JOB[job.name])
        for job in ALL_FETCH_JOBS
    )
    paths = [path.as_posix() for path, _ in databases]
    if len(paths) != len(set(paths)):
        raise PipelineStateError("Pipeline fetch jobs contain duplicate database paths")
    return databases


RAW_DATABASES = _configured_databases()
RAW_DATABASE_PATHS = tuple(path for path, _ in RAW_DATABASES)


def _resolved_child(root: Path, relative_path: Path) -> Path:
    root = root.resolve()
    candidate = root / relative_path
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(root)
    except ValueError as exc:
        raise PipelineStateError(
            f"State path escapes its expected root: {relative_path}"
        ) from exc
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_database(path: Path, expected_table: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise PipelineStateError(f"SQLite state file is missing or unsafe: {path}")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            check_rows = connection.execute("PRAGMA quick_check").fetchall()
            if not check_rows or any(row[0] != "ok" for row in check_rows):
                raise PipelineStateError(
                    f"SQLite integrity check failed for {path}: {check_rows}"
                )
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = ? LIMIT 1",
                (expected_table,),
            ).fetchone()
            if table_exists is None:
                raise PipelineStateError(
                    f"Expected table {expected_table!r} is missing from {path}"
                )
    except sqlite3.Error as exc:
        raise PipelineStateError(f"Could not validate SQLite database {path}: {exc}") from exc


def _backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    try:
        with closing(
            sqlite3.connect(source_uri, uri=True, timeout=30)
        ) as source_connection, closing(
            sqlite3.connect(destination, timeout=30)
        ) as destination_connection:
            source_connection.backup(destination_connection)
    except sqlite3.Error as exc:
        raise PipelineStateError(
            f"Could not snapshot SQLite database {source}: {exc}"
        ) from exc


def create_snapshot(
    project_root: Path,
    snapshot_directory: Path,
    *,
    source_commit: str = "unknown",
    workflow_run_id: str = "local",
) -> dict[str, Any]:
    """Copy all raw databases into a validated, self-contained snapshot."""
    project_root = project_root.resolve()
    snapshot_directory = snapshot_directory.resolve()
    if snapshot_directory.exists():
        if not snapshot_directory.is_dir():
            raise PipelineStateError(
                f"Snapshot path is not a directory: {snapshot_directory}"
            )
        if any(snapshot_directory.iterdir()):
            raise PipelineStateError(
                f"Snapshot directory must be empty: {snapshot_directory}"
            )
    snapshot_directory.mkdir(parents=True, exist_ok=True)

    source_files: list[tuple[Path, Path, str]] = []
    for relative_path, expected_table in RAW_DATABASES:
        source = _resolved_child(project_root, relative_path)
        if source.is_symlink() or not source.is_file():
            raise PipelineStateError(f"Required raw database is missing: {relative_path}")
        source_files.append((relative_path, source, expected_table))

    database_entries: list[dict[str, Any]] = []
    for relative_path, source, expected_table in source_files:
        destination = _resolved_child(snapshot_directory, relative_path)
        _backup_database(source, destination)
        _validate_database(destination, expected_table)
        database_entries.append(
            {
                "path": relative_path.as_posix(),
                "expected_table": expected_table,
                "size_bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
            }
        )

    manifest = {
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "workflow_run_id": workflow_run_id,
        "databases": database_entries,
    }
    manifest_path = snapshot_directory / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _load_and_validate_manifest(snapshot_directory: Path) -> dict[str, Any]:
    manifest_path = snapshot_directory / MANIFEST_FILENAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PipelineStateError(f"Snapshot manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineStateError(f"Snapshot manifest is invalid: {exc}") from exc

    if manifest.get("format_version") != SNAPSHOT_FORMAT_VERSION:
        raise PipelineStateError("Unsupported pipeline-state snapshot format")
    entries = manifest.get("databases")
    if not isinstance(entries, list):
        raise PipelineStateError("Snapshot manifest has no database list")
    if any(
        not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
        for entry in entries
    ):
        raise PipelineStateError("Snapshot manifest contains an invalid database entry")

    expected_paths = {path.as_posix() for path in RAW_DATABASE_PATHS}
    actual_paths = {entry["path"] for entry in entries}
    if len(entries) != len(actual_paths) or actual_paths != expected_paths:
        raise PipelineStateError(
            "Snapshot database paths do not exactly match the configured fetch jobs"
        )
    return manifest


def restore_snapshot(
    project_root: Path,
    snapshot_directory: Path,
) -> dict[str, Any]:
    """Validate a snapshot completely, then atomically restore each raw database."""
    project_root = project_root.resolve()
    snapshot_directory = snapshot_directory.resolve()
    manifest = _load_and_validate_manifest(snapshot_directory)
    entries_by_path = {entry["path"]: entry for entry in manifest["databases"]}

    validated_sources: list[tuple[Path, Path]] = []
    for relative_path, expected_table in RAW_DATABASES:
        relative_text = relative_path.as_posix()
        entry = entries_by_path[relative_text]
        if entry.get("expected_table") != expected_table:
            raise PipelineStateError(
                f"Snapshot table contract does not match for {relative_text}"
            )
        source = _resolved_child(snapshot_directory, relative_path)
        _validate_database(source, expected_table)
        if source.stat().st_size != entry.get("size_bytes"):
            raise PipelineStateError(f"Snapshot size mismatch for {relative_text}")
        if _sha256(source) != entry.get("sha256"):
            raise PipelineStateError(f"Snapshot checksum mismatch for {relative_text}")
        validated_sources.append((relative_path, source))

    restored: list[str] = []
    for relative_path, source in validated_sources:
        destination = _resolved_child(project_root, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            shutil.copy2(source, temporary_path)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
        restored.append(relative_path.as_posix())

    return {
        "restored": restored,
        "source_commit": manifest.get("source_commit"),
        "workflow_run_id": manifest.get("workflow_run_id"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or restore validated raw SQLite pipeline state."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("create", "restore"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument(
            "--project-root",
            type=Path,
            default=DEFAULT_PROJECT_ROOT,
        )
        command_parser.add_argument(
            "--snapshot-directory",
            type=Path,
            required=True,
        )

    create_parser = subparsers.choices["create"]
    create_parser.add_argument("--source-commit", default="unknown")
    create_parser.add_argument("--workflow-run-id", default="local")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            report = create_snapshot(
                args.project_root,
                args.snapshot_directory,
                source_commit=args.source_commit,
                workflow_run_id=args.workflow_run_id,
            )
        else:
            report = restore_snapshot(args.project_root, args.snapshot_directory)
    except PipelineStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
