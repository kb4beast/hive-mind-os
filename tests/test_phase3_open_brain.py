from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os import cli
from hive_mind_os.foundation import brain
from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.brain import (
    MANIFEST_PATH,
    PACK_DIRECTORY,
    ProjectionError,
    project_memory_pack,
    run,
)
from hive_mind_os.foundation.brain_contracts import (
    PROJECTION_SCHEMA_NAMES,
    validate_projection,
    validate_projection_catalog,
)
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import cli_inventory
from scripts.phase3_projection_inventory import build_phase3_inventory

TENANT_ID = "tenant:test"
REPOSITORY_ID = "repository:test"


def _authority(
    action: str,
    *,
    actor_id: str = "builder",
    public_payload: dict | None = None,
):
    decision = decide_foundation_write(
        role=Role.BUILDER,
        action=action,
        policy_decision=PolicyDecision(True, "phase3 fixture"),
        lease_actions={action},
        adapter_actions={action},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        actor_id=actor_id,
        decision_id=f"decision:{action}:{actor_id}",
        lease_id=f"lease:{action}:{actor_id}",
        public_release_decision_id=(
            "release:curator-approved" if public_payload is not None else None
        ),
        public_release_decided_by=(
            "curator-independent" if public_payload is not None else None
        ),
        public_release_subject_digest=(
            digest(public_payload) if public_payload is not None else None
        ),
    )
    if not decision.allowed:
        raise AssertionError(decision)
    return decision


def _identity() -> dict:
    return {
        "record_type": "repository-identity",
        "schema_version": 1,
        "tenant_id": TENANT_ID,
        "repository_id": REPOSITORY_ID,
        "project_lineage_id": "lineage:test",
        "instance_id": "instance:test",
        "remote_evidence_digest": digest("remote"),
        "controller_build_digest": digest("controller"),
        "self_host_depth": 0,
        "parent_run_id": None,
        "subject_commit": "a" * 40,
        "target_cutoff": "a" * 40,
    }


def _memory_payload(
    memory_id: str,
    *,
    sensitivity: str,
    status: str = "active",
) -> dict:
    content_digest = digest({"memory_id": memory_id})
    return {
        "record_type": "memory-record",
        "schema_version": 1,
        "memory_id": memory_id,
        "memory_kind": "semantic",
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "mission_id": "mission:test",
        "run_id": "run:test",
        "step_id": "step:test",
        "actor_id": "builder",
        "payload_digest": content_digest,
        "previous_record_id": None,
        "supersedes_record_id": None,
        "observed_at": "2026-07-29T00:00:00+00:00",
        "recorded_at": "2026-07-29T00:00:01+00:00",
        "causation_id": None,
        "correlation_id": "correlation:test",
        "source_refs": ["source:test"],
        "claim_refs": ["claim:test"],
        "evidence_refs": ["evidence:test"],
        "court_refs": ["court:test"],
        "code_receipt_refs": ["receipt:test"],
        "generation_refs": [],
        "status": status,
        "confidence_ppm": 900_000,
        "freshness_expires_at": None,
        "contradiction_refs": [],
        "relation_refs": [],
        "owner_id": "builder",
        "sensitivity": sensitivity,
        "access_purpose": "public-review",
        "retention": "governed",
        "deletion_policy": "tombstone",
        "quarantine_state": "none",
        "appeal_state": "available",
        "content_digest": content_digest,
        "protected_content_ref": None,
        "retrieval_receipt": None,
    }


def _create_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise OSError(completed.stderr or completed.stdout)


def _remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
    else:
        link.rmdir()


class PortableOpenBrainProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository with spaces"
        self.repository.mkdir()
        self.store_path = self.root / "private-state" / "foundation.sqlite3"
        self.store_path.parent.mkdir()
        self.store = FoundationStore(self.store_path)
        self.store.register_repository(
            _identity(),
            authority=_authority("foundation.repository.register"),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _append(
        self,
        memory_id: str,
        *,
        sensitivity: str,
        status: str = "active",
    ) -> dict:
        payload = _memory_payload(
            memory_id,
            sensitivity=sensitivity,
            status=status,
        )
        return self.store.append_record(
            authority=_authority(
                "foundation.memory.write",
                public_payload=payload if sensitivity == "safe-public" else None,
            ),
            foundation_action="foundation.memory.write",
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            record_type="memory-record",
            schema_name="memory-record-v1",
            stream_id=f"memory:{memory_id}",
            payload=payload,
            actor_id="builder",
            idempotency_key=f"append:{memory_id}",
            observed_at=payload["observed_at"],
            sensitivity=sensitivity,
        )

    def _project(self, **kwargs):
        self.store.close()
        try:
            if not kwargs.get("check", False):
                kwargs["authority"] = _authority(
                    "foundation.projection.write",
                    actor_id="foundation-brain-projector-v1",
                )
            return project_memory_pack(
                self.store_path,
                self.repository,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                **kwargs,
            )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_projection_is_deterministic_portable_and_safe_public_only(self) -> None:
        public = self._append("memory:public:with:windows:unsafe:id", sensitivity="safe-public")
        self._append("memory:private", sensitivity="private")
        human_note = self.repository / PACK_DIRECTORY / "human" / "notes.md"
        human_note.parent.mkdir(parents=True)
        human_note.write_text("human authority remains separate\n", encoding="utf-8")

        first = self._project()
        pack = self.repository / PACK_DIRECTORY
        manifest_bytes = (pack / MANIFEST_PATH).read_bytes()
        manifest = json.loads(manifest_bytes)
        projected = [
            entry
            for entry in manifest["files"]
            if entry["record_id"] == public["record_id"]
        ]
        self.assertEqual(first.status, "projected")
        self.assertEqual(first.projected_record_count, 1)
        self.assertEqual(first.omitted_sensitive_count, 1)
        self.assertEqual(len(projected), 1)
        note_path = pack / projected[0]["path"]
        self.assertTrue(note_path.is_file())
        self.assertNotIn(":", note_path.name)
        note = note_path.read_text(encoding="utf-8")
        self.assertIn("is_generated: true", note)
        self.assertIn("is_authoritative: false", note)
        self.assertIn("memory:public:with:windows:unsafe:id", note)
        self.assertNotIn("memory:private", note)
        self.assertEqual(
            human_note.read_text(encoding="utf-8"),
            "human authority remains separate\n",
        )

        second = self._project()
        checked = self._project(check=True)
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(checked.status, "unchanged")
        self.assertEqual((pack / MANIFEST_PATH).read_bytes(), manifest_bytes)
        self.assertNotIn(b"omitted_sensitive", manifest_bytes)
        self.assertNotIn(b"memory:private", manifest_bytes)

        self._append("memory:later-private", sensitivity="private")
        after_private = self._project()
        self.assertEqual(after_private.status, "unchanged")
        self.assertEqual((pack / MANIFEST_PATH).read_bytes(), manifest_bytes)
        self.assertEqual(after_private.omitted_sensitive_count, 2)

        second_repository = self.root / "second clean root"
        second_repository.mkdir()
        self.store.close()
        try:
            rebuilt = project_memory_pack(
                self.store_path,
                second_repository,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                authority=_authority(
                    "foundation.projection.write",
                    actor_id="foundation-brain-projector-v1",
                ),
            )
        finally:
            self.store = FoundationStore(self.store_path)
        self.assertEqual(rebuilt.tree_digest, first.tree_digest)
        first_tree = {
            path.relative_to(pack).as_posix(): path.read_bytes()
            for path in (pack / "generated").rglob("*")
            if path.is_file()
        }
        second_pack = second_repository / PACK_DIRECTORY
        second_tree = {
            path.relative_to(second_pack).as_posix(): path.read_bytes()
            for path in (second_pack / "generated").rglob("*")
            if path.is_file()
        }
        self.assertEqual(second_tree, first_tree)

    def test_human_edit_conflicts_and_is_never_overwritten(self) -> None:
        public = self._append("memory:conflict", sensitivity="safe-public")
        self._project()
        manifest = json.loads(
            (self.repository / PACK_DIRECTORY / MANIFEST_PATH).read_bytes()
        )
        relative = next(
            entry["path"]
            for entry in manifest["files"]
            if entry["record_id"] == public["record_id"]
        )
        note_path = self.repository / PACK_DIRECTORY / relative
        edited = note_path.read_bytes() + b"\nHuman correction that must survive.\n"
        note_path.write_bytes(edited)

        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict_paths, (relative,))
        self.assertEqual(note_path.read_bytes(), edited)

    def test_interrupted_projection_resumes_from_transaction_receipt(self) -> None:
        self._append("memory:one", sensitivity="safe-public")
        self._append("memory:two", sensitivity="safe-public")
        with self.assertRaisesRegex(InterruptedError, "injected"):
            self._project(fail_after_replacements=1)
        recovered = self._project()
        self.assertEqual(recovered.status, "projected")
        self.assertIsNotNone(recovered.receipt_path)
        self.assertTrue((self.repository / str(recovered.receipt_path)).is_file())
        self.assertEqual(self._project(check=True).status, "unchanged")

    def test_tombstone_is_projected_and_unmanaged_generated_files_fail_closed(self) -> None:
        tombstone = self._append(
            "memory:tombstone",
            sensitivity="safe-public",
            status="tombstoned",
        )
        self._project()
        manifest = json.loads(
            (self.repository / PACK_DIRECTORY / MANIFEST_PATH).read_bytes()
        )
        relative = next(
            entry["path"]
            for entry in manifest["files"]
            if entry["record_id"] == tombstone["record_id"]
        )
        note = (self.repository / PACK_DIRECTORY / relative).read_text(
            encoding="utf-8"
        )
        self.assertIn('status: "tombstoned"', note)
        unmanaged = (
            self.repository / PACK_DIRECTORY / "generated" / "manual-edit.md"
        )
        unmanaged.write_text("not managed\n", encoding="utf-8")
        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertIn("generated/manual-edit.md", result.conflict_paths)
        self.assertEqual(unmanaged.read_text(encoding="utf-8"), "not managed\n")

    def test_unmanaged_file_created_at_lock_entry_is_a_preserved_conflict(self) -> None:
        self._append("memory:editor-race", sensitivity="safe-public")
        original_lock = brain._projection_lock

        @contextmanager
        def injecting_lock(state_root):
            with original_lock(state_root):
                unmanaged = (
                    self.repository
                    / PACK_DIRECTORY
                    / "generated"
                    / "editor-race.md"
                )
                unmanaged.parent.mkdir(parents=True, exist_ok=True)
                unmanaged.write_text("human race\n", encoding="utf-8")
                yield

        with patch.object(brain, "_projection_lock", injecting_lock):
            result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict_paths, ("generated/editor-race.md",))
        self.assertFalse(
            (self.repository / PACK_DIRECTORY / MANIFEST_PATH).exists()
        )

    def test_manifest_edits_conflict_with_and_without_private_state(self) -> None:
        self._append("memory:manifest-conflict", sensitivity="safe-public")
        self._project()
        manifest_path = self.repository / PACK_DIRECTORY / MANIFEST_PATH
        manifest = json.loads(manifest_path.read_bytes())
        manifest["source_cursor"] = f"memory-set:{'0' * 64}"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with_state = self._project()
        self.assertEqual(with_state.status, "conflict")
        self.assertIn(MANIFEST_PATH, with_state.conflict_paths)

        shutil.rmtree(self.repository / ".hive-mind-projection-state")
        without_state = self._project()
        self.assertEqual(without_state.status, "conflict")
        self.assertIn(MANIFEST_PATH, without_state.conflict_paths)
        self.assertEqual(
            json.loads(manifest_path.read_bytes())["source_cursor"],
            f"memory-set:{'0' * 64}",
        )

    def test_completed_receipt_cleans_stale_transaction_state(self) -> None:
        self._append("memory:receipt-cleanup", sensitivity="safe-public")
        first = self._project()
        self.assertIsNotNone(first.receipt_path)
        receipt = json.loads(
            (self.repository / str(first.receipt_path)).read_bytes()
        )
        transaction_id = receipt["transaction_id"]
        transaction_root = (
            self.repository
            / ".hive-mind-projection-state"
            / "transactions"
            / transaction_id
        )
        transaction_root.mkdir(parents=True)
        (transaction_root / "transaction.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        recovered = self._project()
        self.assertEqual(recovered.recovery_status, "already-committed")
        self.assertFalse(transaction_root.exists())
        self.assertEqual(self._project().status, "unchanged")

    def test_hardlinked_store_inside_pack_is_rejected(self) -> None:
        linked = self.repository / PACK_DIRECTORY / "human" / "foundation.sqlite3"
        linked.parent.mkdir(parents=True)
        self.store.close()
        try:
            try:
                os.link(self.store_path, linked)
            except OSError as error:
                self.skipTest(f"hard links unavailable: {error}")
            self.assertTrue(linked.samefile(self.store_path))
            with self.assertRaisesRegex(ProjectionError, "overlap"):
                project_memory_pack(
                    self.store_path,
                    self.repository,
                    tenant_id=TENANT_ID,
                    repository_id=REPOSITORY_ID,
                    check=True,
                )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_linked_state_subtree_cannot_redirect_staging(self) -> None:
        self._append("memory:linked-state", sensitivity="safe-public")
        state_root = self.repository / ".hive-mind-projection-state"
        outside = self.root / "outside-state"
        state_root.mkdir()
        outside.mkdir()
        try:
            _create_directory_link(state_root / "transactions", outside)
        except OSError as error:
            self.skipTest(f"directory links unavailable: {error}")
        try:
            with self.assertRaisesRegex(ProjectionError, "linked or reparse"):
                self._project()
            self.assertEqual(list(outside.rglob("*")), [])
        finally:
            _remove_directory_link(state_root / "transactions")

    def test_pack_link_swap_at_lock_entry_cannot_escape_repository(self) -> None:
        self._append("memory:pack-link-race", sensitivity="safe-public")
        outside = self.root / "outside-pack"
        outside.mkdir()
        pack_root = self.repository / PACK_DIRECTORY
        original_lock = brain._projection_lock

        @contextmanager
        def injecting_lock(state_root):
            with original_lock(state_root):
                _create_directory_link(pack_root, outside)
                yield

        try:
            with (
                patch.object(brain, "_projection_lock", injecting_lock),
                self.assertRaisesRegex(ProjectionError, "memory pack path"),
            ):
                self._project()
            self.assertEqual(list(outside.rglob("*")), [])
        finally:
            if pack_root.exists():
                _remove_directory_link(pack_root)

    def test_missing_or_renamed_managed_note_is_a_conflict(self) -> None:
        public = self._append("memory:rename", sensitivity="safe-public")
        self._project()
        manifest = json.loads(
            (self.repository / PACK_DIRECTORY / MANIFEST_PATH).read_bytes()
        )
        relative = next(
            entry["path"]
            for entry in manifest["files"]
            if entry["record_id"] == public["record_id"]
        )
        original = self.repository / PACK_DIRECTORY / relative
        renamed = original.with_name("human-renamed.md")
        original.rename(renamed)
        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertIn(relative, result.conflict_paths)
        self.assertIn(
            renamed.relative_to(self.repository / PACK_DIRECTORY).as_posix(),
            result.conflict_paths,
        )
        self.assertTrue(renamed.is_file())

    def test_scope_paths_and_check_mode_fail_closed_without_writes(self) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self.store.close()
        try:
            with self.assertRaisesRegex(ProjectionError, "not registered"):
                project_memory_pack(
                    self.store_path,
                    self.repository,
                    tenant_id=TENANT_ID,
                    repository_id="repository:unknown",
                )
            result = project_memory_pack(
                self.store_path,
                self.repository,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            )
            self.assertEqual(result.status, "drift")
            self.assertFalse((self.repository / PACK_DIRECTORY).exists())
            with self.assertRaisesRegex(ProjectionError, "existing regular file"):
                project_memory_pack(
                    self.root / "missing.sqlite3",
                    self.repository,
                    tenant_id=TENANT_ID,
                    repository_id=REPOSITORY_ID,
                )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_read_snapshot_does_not_change_canonical_database_bytes(self) -> None:
        self._append("memory:readonly", sensitivity="safe-public")
        self.store.close()
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.store_path.parent.glob(f"{self.store_path.name}*")
            if path.is_file()
        }
        try:
            result = project_memory_pack(
                self.store_path,
                self.repository,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            )
            self.assertEqual(result.status, "drift")
            after = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.store_path.parent.glob(f"{self.store_path.name}*")
                if path.is_file()
            }
            self.assertEqual(after[self.store_path.name], before[self.store_path.name])
            wal = Path(f"{self.store_path}-wal")
            self.assertFalse(wal.exists() and wal.stat().st_size)
        finally:
            self.store = FoundationStore(self.store_path)

    def test_read_snapshot_sees_a_consistent_live_wal_commit(self) -> None:
        public = self._append("memory:live-wal", sensitivity="safe-public")
        result = project_memory_pack(
            self.store_path,
            self.repository,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            check=True,
        )
        self.assertEqual(result.status, "drift")
        self.assertEqual(result.projected_record_count, 1)
        snapshot = FoundationStore.read_public_memory_snapshot(
            self.store_path,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
        )
        self.assertEqual(snapshot.records[0]["record_id"], public["record_id"])

    def test_write_requires_authentic_scope_bound_authority(self) -> None:
        self._append("memory:authority", sensitivity="safe-public")
        self.store.close()
        try:
            with self.assertRaisesRegex(ProjectionError, "not authentic"):
                project_memory_pack(
                    self.store_path,
                    self.repository,
                    tenant_id=TENANT_ID,
                    repository_id=REPOSITORY_ID,
                )
            self.assertFalse((self.repository / PACK_DIRECTORY).exists())
            self.assertFalse(
                (self.repository / ".hive-mind-projection-state").exists()
            )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_metadata_renderer_bounds_hostile_values_and_quarantine(self) -> None:
        hostile = self._append(
            "memory:---\n![[embed]]\n<script>alert(1)</script>",
            sensitivity="safe-public",
        )
        quarantined = self._append(
            "memory:quarantined",
            sensitivity="safe-public",
            status="quarantined",
        )
        result = self._project()
        self.assertEqual(result.projected_record_count, 1)
        self.assertEqual(result.omitted_quarantined_count, 1)
        manifest = json.loads(
            (self.repository / PACK_DIRECTORY / MANIFEST_PATH).read_bytes()
        )
        self.assertNotIn(
            quarantined["record_id"],
            json.dumps(manifest, sort_keys=True),
        )
        relative = next(
            entry["path"]
            for entry in manifest["files"]
            if entry["record_id"] == hostile["record_id"]
        )
        note = (self.repository / PACK_DIRECTORY / relative).read_text(
            encoding="utf-8"
        )
        self.assertEqual(note.splitlines().count("---"), 2)
        self.assertIn(r"![[embed]]\n<script>alert(1)</script>", note)
        self.assertNotIn("protected_content_ref", note)
        self.assertNotIn("retrieval_receipt", note)

    def test_store_inside_public_pack_is_rejected(self) -> None:
        nested_repository = self.root / "nested"
        nested_store = nested_repository / PACK_DIRECTORY / "foundation.sqlite3"
        nested_store.parent.mkdir(parents=True)
        nested = FoundationStore(nested_store)
        try:
            nested.register_repository(
                _identity(),
                authority=_authority("foundation.repository.register"),
            )
        finally:
            nested.close()
        with self.assertRaisesRegex(ProjectionError, "overlap"):
            project_memory_pack(
                nested_store,
                nested_repository,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            )

    def test_failure_exit_is_typed_by_a_strict_contract(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = run(
                [
                    "check",
                    "--store",
                    str(self.root / "missing.sqlite3"),
                    "--repo",
                    str(self.repository),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ]
            )
        self.assertEqual(exit_code, 2)
        failure = json.loads(stderr.getvalue())
        self.assertTrue(validate_projection("brain-failure-v1", failure).valid)

    def test_dedicated_module_cli_preserves_frozen_facades_and_parsers(self) -> None:
        self._append("memory:cli", sensitivity="safe-public")
        self.store.close()
        try:
            exit_code = run(
                [
                    "project",
                    "--store",
                    str(self.store_path),
                    "--repo",
                    str(self.repository),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ]
            )
        finally:
            self.store = FoundationStore(self.store_path)
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            (len(hive_mind_os.__all__), len(package_system.__all__)),
            (131, 33),
        )
        self.assertEqual(cli_inventory()["parser_count"], 13)
        self.assertFalse(hasattr(cli, "build_brain_parser"))

    def test_phase3_contract_catalog_and_inventory_are_separate_and_strict(self) -> None:
        self.assertEqual(len(PROJECTION_SCHEMA_NAMES), 7)
        self.assertTrue(validate_projection_catalog().valid)
        malformed = {
            "schema_version": "hive-brain-pack/v1",
            "self_granted_authority": True,
        }
        validation = validate_projection("brain-manifest-v1", malformed)
        self.assertFalse(validation.valid)
        self.assertTrue(
            any("unknown properties" in issue for issue in validation.issues)
        )
        inventory = build_phase3_inventory(Path(__file__).parents[1])
        committed_inventory = json.loads(
            (
                Path(__file__).parents[1]
                / "evidence"
                / "phase3"
                / "phase3_projection_inventory.json"
            ).read_bytes()
        )
        self.assertEqual(inventory, committed_inventory)
        frozen = inventory["generation_zero"]
        self.assertEqual(
            (
                frozen["root_api_count"],
                frozen["package_api_count"],
                frozen["cli_parser_count"],
                frozen["definition_count"],
            ),
            (131, 33, 13, 304),
        )
        self.assertEqual(inventory["projection_contracts"]["count"], 7)
        self.assertTrue(inventory["projection_contracts"]["catalog_valid"])
        self.assertEqual(
            inventory["deterministic_fixture"]["projected_record_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
