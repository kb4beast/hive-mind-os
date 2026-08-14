from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))


def _load_autopilot():
    spec = importlib.util.spec_from_file_location(
        "runtime_migration_cli_autopilot", BIN / "autopilot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


autopilot = _load_autopilot()


class RuntimeMigrationCliTests(unittest.TestCase):
    def test_operation_evidence_paths_are_bounded_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            coordination = Path(temp).resolve() / ("x" * 120)
            operation_id = "sha256:" + "1" * 64

            operation_path = autopilot._runtime_migration_operation_path(
                coordination, operation_id
            )
            abort_path = autopilot._runtime_migration_abort_path(
                coordination, operation_id
            )
            completion_path = autopilot._runtime_migration_completion_path(
                coordination, operation_id
            )

            self.assertEqual(operation_path.parent.name, "mo")
            self.assertEqual(operation_path.name, "1" * 20 + ".op.json")
            self.assertEqual(abort_path.name, "1" * 20 + ".abort.json")
            self.assertEqual(completion_path.name, "1" * 20 + ".complete.json")
            self.assertLess(len(str(operation_path)), len(str(coordination)) + 40)

    def test_completion_replay_is_exact_and_plan_bound(self) -> None:
        operation = {
            "operation_id": "sha256:" + "1" * 64,
            "record_id": "sha256:" + "2" * 64,
        }
        semantic_id = "sha256:" + "3" * 64
        bootstrap_id = "sha256:" + "4" * 64
        ready_id = "sha256:" + "5" * 64
        material = {
            "schema_version": 1,
            "kind": autopilot.RUNTIME_MIGRATION_COMPLETE_KIND,
            "status": "COMPLETE",
            "operation_id": operation["operation_id"],
            "operation_record_id": operation["record_id"],
            "semantic_reconciliation_id": semantic_id,
            "bootstrap_migration_id": bootstrap_id,
            "ready_record_id": ready_id,
            "actor": "migration-test",
            "completed_at": "2026-08-14T12:00:00Z",
        }
        completion = {**material, "record_id": autopilot.digest_json(material)}

        self.assertEqual(
            autopilot._validated_runtime_migration_completion(
                completion,
                operation=operation,
                semantic_reconciliation_id=semantic_id,
                bootstrap_migration_id=bootstrap_id,
                ready_record_id=ready_id,
            ),
            completion,
        )
        with self.assertRaisesRegex(
            autopilot.AutopilotError, "completion is invalid"
        ):
            autopilot._validated_runtime_migration_completion(
                {**completion, "unexpected": True},
                operation=operation,
                semantic_reconciliation_id=semantic_id,
                bootstrap_migration_id=bootstrap_id,
                ready_record_id=ready_id,
            )
        with self.assertRaisesRegex(
            autopilot.AutopilotError, "completion is invalid"
        ):
            autopilot._validated_runtime_migration_completion(
                completion,
                operation=operation,
                semantic_reconciliation_id="sha256:" + "9" * 64,
                bootstrap_migration_id=bootstrap_id,
                ready_record_id=ready_id,
            )

    def test_dry_run_is_read_only_and_bypasses_control_plane(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            coordination = root / "coordination"
            plan = {
                "schema_version": 1,
                "kind": "hive-mind-runtime-migration-plan-v1",
                "operation_id": "sha256:" + "1" * 64,
                "plan_id": "sha256:" + "2" * 64,
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "resolve_repository_state_dir",
                    return_value=coordination,
                ),
                mock.patch.object(
                    autopilot,
                    "_active_runtime_migration_operation",
                    return_value=None,
                ),
                mock.patch.object(
                    autopilot, "_runtime_migration_plan", return_value=plan
                ) as build,
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                mock.patch.object(
                    autopilot, "exclusive_write_json_or_identical"
                ) as write,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "--state-dir",
                        str(coordination),
                        "runtime-authority-migrate",
                        "--mode",
                        "dry-run",
                        "--actor",
                        "migration-test",
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            write.assert_not_called()
            build.assert_called_once()
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "DRY_RUN")
            self.assertEqual(result["plan"], plan)

    def test_dry_run_replays_ready_chain_without_replanning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            coordination = root / "coordination"
            coordination.mkdir()
            (coordination / autopilot.RUNTIME_READY_MANIFEST).write_text(
                "sealed by the mocked strict verifier", encoding="utf-8"
            )
            verification = {
                "schema_version": 1,
                "kind": "hive-mind-runtime-migration-verification-v1",
                "status": "READY",
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "resolve_repository_state_dir",
                    return_value=coordination,
                ),
                mock.patch.object(
                    autopilot,
                    "_verify_runtime_migration",
                    return_value=verification,
                ) as verify,
                mock.patch.object(
                    autopilot, "_runtime_migration_plan"
                ) as build,
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "--state-dir",
                        str(coordination),
                        "runtime-authority-migrate",
                        "--mode",
                        "dry-run",
                        "--actor",
                        "migration-test",
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            build.assert_not_called()
            verify.assert_called_once_with(root, coordination)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "ALREADY_READY")
            self.assertIsNone(result["plan"])
            self.assertEqual(result["verification"], verification)

    def test_verify_uses_the_read_only_chain_without_a_plane(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            coordination = root / "coordination"
            receipt = {
                "schema_version": 1,
                "kind": "hive-mind-runtime-migration-verification-v1",
                "status": "READY",
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "resolve_repository_state_dir",
                    return_value=coordination,
                ),
                mock.patch.object(
                    autopilot, "_verify_runtime_migration", return_value=receipt
                ) as verify,
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "--state-dir",
                        str(coordination),
                        "runtime-authority-migrate",
                        "--mode",
                        "verify",
                        "--actor",
                        "migration-test",
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            verify.assert_called_once_with(root, coordination)
            self.assertEqual(json.loads(output.getvalue()), receipt)

    def test_pre_ready_verify_uses_each_sealed_historical_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            coordination = root / "coordination"
            semantic_path = (
                coordination / autopilot.LEGACY_SEMANTIC_RECONCILIATION_MANIFEST
            )
            bootstrap_path = coordination / autopilot.RUNTIME_BOOTSTRAP_MANIFEST
            semantic_path.parent.mkdir(parents=True, exist_ok=True)
            bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
            semantic_path.write_bytes(b"placeholder")
            bootstrap_path.write_bytes(b"placeholder")
            repository_identity = {
                "repository": "example/repository",
                "transport_digest": "sha256:" + "1" * 64,
            }
            semantic_inventory = [str(root / "historical-semantic")]
            bootstrap_inventory = [str(root / "historical-bootstrap")]
            semantic = {
                "status": "COMPLETE",
                "worktree_inventory": semantic_inventory,
            }
            bootstrap = {
                "status": "COMPLETE",
                "worktree_inventory": bootstrap_inventory,
            }

            def read_document(path, **_kwargs):
                candidate = Path(path)
                if candidate == semantic_path:
                    return semantic
                if candidate == bootstrap_path:
                    return bootstrap
                raise AssertionError(f"unexpected authority read: {candidate}")

            with (
                mock.patch.object(
                    autopilot,
                    "runtime_repository_identity",
                    return_value=repository_identity,
                ),
                mock.patch.object(
                    autopilot,
                    "_linked_worktree_roots",
                    return_value=[root / "new-current-worktree"],
                ),
                mock.patch.object(
                    autopilot,
                    "read_strict_canonical_json",
                    side_effect=read_document,
                ),
                mock.patch.object(
                    autopilot, "_validate_legacy_semantic_manifest"
                ) as validate_semantic,
                mock.patch.object(
                    autopilot, "_validate_migration_manifest"
                ) as validate_bootstrap,
            ):
                result = autopilot._verify_runtime_migration(root, coordination)

            validate_semantic.assert_called_once_with(
                semantic,
                repository_identity=repository_identity,
                inventory=semantic_inventory,
                coordination_dir=coordination,
            )
            validate_bootstrap.assert_called_once_with(
                bootstrap,
                repository_identity=repository_identity,
                inventory=bootstrap_inventory,
                coordination_dir=coordination,
            )
            self.assertEqual(
                result["current_worktree_inventory"],
                [str(root / "new-current-worktree")],
            )

    def test_rollback_before_ready_is_abort_only_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            coordination = root / "coordination"
            host_runtime = root / "host-runtime"
            operation = {
                "operation_id": "sha256:" + "1" * 64,
                "record_id": "sha256:" + "2" * 64,
                "plan": {},
            }
            abort = {
                "schema_version": 1,
                "kind": autopilot.RUNTIME_MIGRATION_ABORT_KIND,
                "status": "ABORTED_FENCED",
                "record_id": "sha256:" + "4" * 64,
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "resolve_repository_state_dir",
                    return_value=coordination,
                ),
                mock.patch.object(
                    autopilot,
                    "resolve_host_runtime_dir",
                    return_value=host_runtime,
                ),
                mock.patch.object(
                    autopilot,
                    "_active_runtime_migration_operation",
                    return_value=operation,
                ),
                mock.patch.object(
                    autopilot, "runtime_file_lock", side_effect=lambda *a, **k: nullcontext()
                ),
                mock.patch.object(
                    autopilot, "read_current_host_runtime_identity", return_value={}
                ),
                mock.patch.object(
                    autopilot,
                    "_runtime_migration_abort",
                    return_value=abort,
                ) as read_abort,
                mock.patch.object(
                    autopilot, "exclusive_write_json_or_identical"
                ) as write,
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "--state-dir",
                        str(coordination),
                        "--host-runtime-dir",
                        str(host_runtime),
                        "runtime-authority-migrate",
                        "--mode",
                        "rollback-before-ready",
                        "--actor",
                        "migration-test",
                        "--reason",
                        "stop before READY and preserve evidence",
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            write.assert_not_called()
            read_abort.assert_called_once_with(coordination, operation)
            self.assertEqual(json.loads(output.getvalue()), abort)


if __name__ == "__main__":
    unittest.main()
