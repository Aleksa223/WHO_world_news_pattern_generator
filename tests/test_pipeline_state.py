import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from maintenance_scripts.pipeline_state import (
    MANIFEST_FILENAME,
    RAW_DATABASES,
    RAW_DATABASE_PATHS,
    PipelineStateError,
    create_snapshot,
    restore_snapshot,
)


class PipelineStateTests(unittest.TestCase):
    def _create_project_databases(self, root: Path, marker: str) -> None:
        for relative_path, table_name in RAW_DATABASES:
            database = root / relative_path
            database.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    f'CREATE TABLE "{table_name}" (id TEXT PRIMARY KEY, marker TEXT)'
                )
                connection.execute(
                    f'INSERT INTO "{table_name}" (id, marker) VALUES (?, ?)',
                    (relative_path.as_posix(), marker),
                )
                connection.commit()

    def _markers(self, root: Path) -> dict[str, str]:
        markers = {}
        for relative_path, table_name in RAW_DATABASES:
            with closing(sqlite3.connect(root / relative_path)) as connection:
                marker = connection.execute(
                    f'SELECT marker FROM "{table_name}"'
                ).fetchone()[0]
            markers[relative_path.as_posix()] = marker
        return markers

    def test_raw_state_paths_follow_every_configured_fetch_job(self):
        self.assertEqual(len(RAW_DATABASE_PATHS), 9)
        self.assertNotIn(Path("warehouse/analytics.db"), RAW_DATABASE_PATHS)
        self.assertFalse(any("before_" in path.name for path in RAW_DATABASE_PATHS))
        self.assertFalse(any("migration" in path.name for path in RAW_DATABASE_PATHS))

    def test_create_and_restore_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")

            manifest = create_snapshot(
                project,
                snapshot,
                source_commit="abc123",
                workflow_run_id="42",
            )
            self.assertEqual(manifest["format_version"], 1)
            self.assertEqual(manifest["source_commit"], "abc123")
            self.assertEqual(manifest["workflow_run_id"], "42")
            self.assertEqual(
                {entry["path"] for entry in manifest["databases"]},
                {path.as_posix() for path in RAW_DATABASE_PATHS},
            )
            self.assertTrue((snapshot / MANIFEST_FILENAME).is_file())

            for relative_path, table_name in RAW_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    connection.execute(f'DELETE FROM "{table_name}"')
                    connection.execute(
                        f'INSERT INTO "{table_name}" (id, marker) VALUES (?, ?)',
                        (relative_path.as_posix(), "changed"),
                    )
                    connection.commit()

            report = restore_snapshot(project, snapshot)
            self.assertEqual(report["source_commit"], "abc123")
            self.assertEqual(
                set(report["restored"]),
                {path.as_posix() for path in RAW_DATABASE_PATHS},
            )
            self.assertEqual(set(self._markers(project).values()), {"original"})

    def test_corrupt_snapshot_fails_before_any_database_is_replaced(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            create_snapshot(project, snapshot)

            for relative_path, table_name in RAW_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    connection.execute(f'DELETE FROM "{table_name}"')
                    connection.execute(
                        f'INSERT INTO "{table_name}" (id, marker) VALUES (?, ?)',
                        (relative_path.as_posix(), "current"),
                    )
                    connection.commit()

            corrupt_path = snapshot / RAW_DATABASE_PATHS[0]
            corrupt_path.write_bytes(b"not a sqlite database")
            with self.assertRaises(PipelineStateError):
                restore_snapshot(project, snapshot)

            self.assertEqual(set(self._markers(project).values()), {"current"})

    def test_manifest_cannot_omit_a_configured_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            create_snapshot(project, snapshot)

            manifest_path = snapshot / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["databases"].pop()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(PipelineStateError):
                restore_snapshot(project, snapshot)


if __name__ == "__main__":
    unittest.main()
