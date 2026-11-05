import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from maintenance_scripts.pipeline_state import (
    DBT_SNAPSHOT_DATABASES,
    DBT_SNAPSHOT_DATABASE_PATHS,
    LEGACY_SNAPSHOT_FORMAT_VERSION,
    MANIFEST_FILENAME,
    RAW_DATABASES,
    RAW_DATABASE_PATHS,
    SNAPSHOT_FORMAT_VERSION,
    PipelineStateError,
    create_snapshot,
    restore_snapshot,
)


class PipelineStateTests(unittest.TestCase):
    def _create_snapshot_history_database(self, root: Path, marker: str) -> None:
        for relative_path, table_names in DBT_SNAPSHOT_DATABASES:
            database = root / relative_path
            database.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(database)) as connection:
                for table_name in table_names:
                    connection.execute(
                        f'CREATE TABLE "{table_name}" '
                        "(id TEXT PRIMARY KEY, marker TEXT)"
                    )
                    connection.execute(
                        f'INSERT INTO "{table_name}" (id, marker) VALUES (?, ?)',
                        (table_name, marker),
                    )
                connection.commit()

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
                connection.execute(
                    "CREATE TABLE ingestion_audit "
                    "(audit_id TEXT PRIMARY KEY, marker TEXT)"
                )
                connection.execute(
                    "INSERT INTO ingestion_audit (audit_id, marker) VALUES (?, ?)",
                    (relative_path.as_posix(), marker),
                )
                connection.commit()

        self._create_snapshot_history_database(root, marker)

    def _markers(self, root: Path) -> dict[str, str]:
        markers = {}
        for relative_path, table_name in RAW_DATABASES:
            with closing(sqlite3.connect(root / relative_path)) as connection:
                marker = connection.execute(
                    f'SELECT marker FROM "{table_name}"'
                ).fetchone()[0]
            markers[relative_path.as_posix()] = marker
        return markers

    def _audit_markers(self, root: Path) -> dict[str, str]:
        markers = {}
        for relative_path, _ in RAW_DATABASES:
            with closing(sqlite3.connect(root / relative_path)) as connection:
                marker = connection.execute(
                    "SELECT marker FROM ingestion_audit"
                ).fetchone()[0]
            markers[relative_path.as_posix()] = marker
        return markers

    def _snapshot_history_markers(self, root: Path) -> dict[str, str]:
        markers = {}
        for relative_path, table_names in DBT_SNAPSHOT_DATABASES:
            with closing(sqlite3.connect(root / relative_path)) as connection:
                for table_name in table_names:
                    marker = connection.execute(
                        f'SELECT marker FROM "{table_name}"'
                    ).fetchone()[0]
                    markers[table_name] = marker
        return markers

    def test_raw_state_paths_follow_every_configured_fetch_job(self):
        self.assertEqual(len(RAW_DATABASE_PATHS), 9)
        self.assertNotIn(Path("warehouse/analytics.db"), RAW_DATABASE_PATHS)
        self.assertFalse(any("before_" in path.name for path in RAW_DATABASE_PATHS))
        self.assertFalse(any("migration" in path.name for path in RAW_DATABASE_PATHS))
        self.assertEqual(
            DBT_SNAPSHOT_DATABASE_PATHS,
            (Path("warehouse/snapshot_history.db"),),
        )
        self.assertTrue(
            set(RAW_DATABASE_PATHS).isdisjoint(DBT_SNAPSHOT_DATABASE_PATHS)
        )

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
            self.assertEqual(manifest["format_version"], SNAPSHOT_FORMAT_VERSION)
            self.assertEqual(manifest["source_commit"], "abc123")
            self.assertEqual(manifest["workflow_run_id"], "42")
            self.assertEqual(
                {entry["path"] for entry in manifest["databases"]},
                {path.as_posix() for path in RAW_DATABASE_PATHS},
            )
            self.assertEqual(
                {
                    entry["path"]
                    for entry in manifest["dbt_snapshot_databases"]
                },
                {path.as_posix() for path in DBT_SNAPSHOT_DATABASE_PATHS},
            )
            self.assertTrue((snapshot / MANIFEST_FILENAME).is_file())

            for relative_path, table_name in RAW_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    connection.execute(f'DELETE FROM "{table_name}"')
                    connection.execute(
                        f'INSERT INTO "{table_name}" (id, marker) VALUES (?, ?)',
                        (relative_path.as_posix(), "changed"),
                    )
                    connection.execute("UPDATE ingestion_audit SET marker = 'changed'")
                    connection.commit()

            for relative_path, table_names in DBT_SNAPSHOT_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    for table_name in table_names:
                        connection.execute(
                            f'UPDATE "{table_name}" SET marker = ?',
                            ("changed",),
                        )
                    connection.commit()

            report = restore_snapshot(project, snapshot)
            self.assertEqual(report["source_commit"], "abc123")
            self.assertEqual(
                set(report["restored"]),
                {path.as_posix() for path in RAW_DATABASE_PATHS},
            )
            self.assertEqual(
                set(report["restored_dbt_snapshot_databases"]),
                {path.as_posix() for path in DBT_SNAPSHOT_DATABASE_PATHS},
            )
            self.assertEqual(set(self._markers(project).values()), {"original"})
            self.assertEqual(
                set(self._audit_markers(project).values()),
                {"original"},
            )
            self.assertEqual(
                set(self._snapshot_history_markers(project).values()),
                {"original"},
            )

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

    def test_corrupt_snapshot_history_fails_before_any_database_is_replaced(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            create_snapshot(project, snapshot)

            for relative_path, table_name in RAW_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    connection.execute(
                        f'UPDATE "{table_name}" SET marker = ?',
                        ("current",),
                    )
                    connection.commit()
            for relative_path, table_names in DBT_SNAPSHOT_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    for table_name in table_names:
                        connection.execute(
                            f'UPDATE "{table_name}" SET marker = ?',
                            ("current",),
                        )
                    connection.commit()

            corrupt_path = snapshot / DBT_SNAPSHOT_DATABASE_PATHS[0]
            corrupt_path.write_bytes(b"not a sqlite database")
            with self.assertRaises(PipelineStateError):
                restore_snapshot(project, snapshot)

            self.assertEqual(set(self._markers(project).values()), {"current"})
            self.assertEqual(
                set(self._snapshot_history_markers(project).values()),
                {"current"},
            )

    def test_valid_sqlite_checksum_tamper_fails_before_restore(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            create_snapshot(project, snapshot)

            for relative_path, table_name in RAW_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    connection.execute(
                        f'UPDATE "{table_name}" SET marker = ?',
                        ("current",),
                    )
                    connection.commit()

            tampered_path = snapshot / RAW_DATABASE_PATHS[0]
            tampered_table = RAW_DATABASES[0][1]
            with closing(sqlite3.connect(tampered_path)) as connection:
                connection.execute(
                    f'UPDATE "{tampered_table}" SET marker = ?',
                    ("tampered",),
                )
                connection.commit()

            with self.assertRaisesRegex(PipelineStateError, "checksum mismatch"):
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

    def test_manifest_cannot_omit_snapshot_history_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            create_snapshot(project, snapshot)

            manifest_path = snapshot / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dbt_snapshot_databases"].pop()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(PipelineStateError):
                restore_snapshot(project, snapshot)

    def test_legacy_manifest_restores_raw_state_without_overwriting_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            create_snapshot(project, snapshot)

            manifest_path = snapshot / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["format_version"] = LEGACY_SNAPSHOT_FORMAT_VERSION
            manifest.pop("dbt_snapshot_databases")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            for relative_path, table_name in RAW_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    connection.execute(
                        f'UPDATE "{table_name}" SET marker = ?',
                        ("current",),
                    )
                    connection.commit()
            for relative_path, table_names in DBT_SNAPSHOT_DATABASES:
                with closing(sqlite3.connect(project / relative_path)) as connection:
                    for table_name in table_names:
                        connection.execute(
                            f'UPDATE "{table_name}" SET marker = ?',
                            ("current",),
                        )
                    connection.commit()

            report = restore_snapshot(project, snapshot)

            self.assertEqual(set(self._markers(project).values()), {"original"})
            self.assertEqual(
                set(self._snapshot_history_markers(project).values()),
                {"current"},
            )
            self.assertEqual(report["restored_dbt_snapshot_databases"], [])

    def test_legacy_state_bootstraps_fresh_project_then_upgrades_to_v2(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_project = root / "source-project"
            legacy_snapshot = root / "legacy-snapshot"
            fresh_project = root / "fresh-project"
            upgraded_snapshot = root / "upgraded-snapshot"
            self._create_project_databases(source_project, "legacy")
            create_snapshot(source_project, legacy_snapshot)

            manifest_path = legacy_snapshot / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["format_version"] = LEGACY_SNAPSHOT_FORMAT_VERSION
            manifest.pop("dbt_snapshot_databases")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (legacy_snapshot / DBT_SNAPSHOT_DATABASE_PATHS[0]).unlink()

            report = restore_snapshot(fresh_project, legacy_snapshot)

            self.assertEqual(set(self._markers(fresh_project).values()), {"legacy"})
            self.assertEqual(report["restored_dbt_snapshot_databases"], [])
            self.assertFalse(
                (fresh_project / DBT_SNAPSHOT_DATABASE_PATHS[0]).exists()
            )

            # The first dbt snapshot run creates this database and both tables.
            self._create_snapshot_history_database(fresh_project, "first-dbt-run")
            upgraded_manifest = create_snapshot(
                fresh_project,
                upgraded_snapshot,
            )
            self.assertEqual(
                upgraded_manifest["format_version"],
                SNAPSHOT_FORMAT_VERSION,
            )
            self.assertEqual(
                len(upgraded_manifest["dbt_snapshot_databases"]),
                1,
            )

    def test_create_requires_snapshot_history_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            (project / DBT_SNAPSHOT_DATABASE_PATHS[0]).unlink()

            with self.assertRaises(PipelineStateError):
                create_snapshot(project, snapshot)

    def test_create_requires_every_snapshot_history_table(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            snapshot = root / "snapshot"
            self._create_project_databases(project, "original")
            history_path = project / DBT_SNAPSHOT_DATABASE_PATHS[0]
            missing_table = DBT_SNAPSHOT_DATABASES[0][1][-1]
            with closing(sqlite3.connect(history_path)) as connection:
                connection.execute(f'DROP TABLE "{missing_table}"')
                connection.commit()

            with self.assertRaisesRegex(PipelineStateError, "tables are missing"):
                create_snapshot(project, snapshot)


if __name__ == "__main__":
    unittest.main()
