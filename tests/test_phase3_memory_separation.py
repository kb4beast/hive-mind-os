from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.authority import decide_foundation_write
from hive_mind_os.foundation.brain import (
    PACK_DIRECTORY,
    ProjectionError,
    project_memory_pack,
    project_released_memory_pack,
)
from hive_mind_os.foundation.brain import run as run_brain
from hive_mind_os.foundation.public_memory import (
    MAX_ENVELOPE_BYTES,
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    PublicMemoryReleaseStore,
    PublicMemorySeparationError,
    materialize_public_memory,
    read_public_memory_release_snapshot,
)
from hive_mind_os.foundation.public_memory_contracts import (
    PUBLIC_MEMORY_SCHEMA_NAMES,
    validate_public_memory_catalog,
)
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import cli_inventory
from scripts.phase3_memory_separation_inventory import (
    build_phase3_item2_inventory,
)
from tests.test_phase3_open_brain import (
    REPOSITORY_ID,
    TENANT_ID,
    _authority,
    _identity,
    _memory_payload,
)


def _release_authority(
    *,
    tenant_id: str = TENANT_ID,
    repository_id: str = REPOSITORY_ID,
):
    decision = decide_foundation_write(
        role=Role.BUILDER,
        action=PUBLIC_MEMORY_RELEASE_ACTION,
        policy_decision=PolicyDecision(True, "item-2 fixture"),
        lease_actions={PUBLIC_MEMORY_RELEASE_ACTION},
        adapter_actions={PUBLIC_MEMORY_RELEASE_ACTION},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=tenant_id,
        repository_id=repository_id,
        actor_id=PUBLIC_MEMORY_RELEASER,
        decision_id="decision:item2:release",
        lease_id="lease:item2:release",
    )
    if not decision.allowed:
        raise AssertionError(decision)
    return decision


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class PublicPrivateMemorySeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.private_root = self.root / "private"
        self.private_root.mkdir()
        self.store_path = self.private_root / "foundation.sqlite3"
        self.public_root = self.root / "public"
        self.public_root.mkdir()
        self.public_store_path = self.public_root / "safe-public.sqlite3"
        self.protected_release = self.root / "protected-release"
        self.protected_projection = self.root / "protected-projection"
        self.store = FoundationStore(self.store_path)
        self.store.register_repository(
            _identity(),
            authority=_authority("foundation.repository.register"),
        )

    def tearDown(self) -> None:
        try:
            self.store.close()
        except sqlite3.Error:
            pass
        self.temporary.cleanup()

    def _append(
        self,
        memory_id: str,
        *,
        sensitivity: str,
        status: str = "active",
        protected_content_ref: str | None = None,
    ) -> dict:
        payload = _memory_payload(
            memory_id,
            sensitivity=sensitivity,
            status=status,
        )
        payload["protected_content_ref"] = protected_content_ref
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
            idempotency_key=f"item2:{memory_id}",
            observed_at=payload["observed_at"],
            sensitivity=sensitivity,
        )

    def _materialize(self, **kwargs):
        protected_state_root = kwargs.pop(
            "protected_state_root",
            self.protected_release,
        )
        self.store.close()
        try:
            return materialize_public_memory(
                self.store_path,
                self.public_store_path,
                self.repository,
                protected_state_root,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                authority=_release_authority(),
                **kwargs,
            )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_release_store_is_physically_separate_public_only_and_idempotent(
        self,
    ) -> None:
        public = self._append("memory:public", sensitivity="safe-public")
        self._append("memory:private-secret-marker", sensitivity="private")
        self._append(
            "memory:quarantined-secret-marker",
            sensitivity="safe-public",
            status="quarantined",
        )
        source_before = [
            (
                item["record_id"],
                item["semantic_digest"],
                item["sensitivity"],
            )
            for item in self.store.records(
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
            )
        ]

        first = self._materialize()
        second = self._materialize()

        self.assertEqual(first.status, "materialized")
        self.assertEqual(first.released_record_count, 1)
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(second.existing_record_count, 1)
        self.assertFalse((self.repository / ".hive-mind-projection-state").exists())
        connection = sqlite3.connect(self.public_store_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            envelope = json.loads(
                connection.execute(
                    "SELECT envelope_json FROM released_memory"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        self.assertEqual(
            tables,
            {"public_memory_metadata", "released_memory"},
        )
        self.assertEqual(envelope["record_id"], public["record_id"])
        encoded = json.dumps(envelope, sort_keys=True)
        for forbidden in (
            "memory:private-secret-marker",
            "memory:quarantined-secret-marker",
            "protected_content_ref",
            "retrieval_receipt",
            "authority_decision_id",
            "lease_id",
            "idempotency_key",
            "outbox",
        ):
            self.assertNotIn(forbidden, encoded)
        source_after = [
            (
                item["record_id"],
                item["semantic_digest"],
                item["sensitivity"],
            )
            for item in self.store.records(
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
            )
        ]
        self.assertEqual(source_after, source_before)

    def test_separated_projection_matches_item1_and_never_opens_private_store(
        self,
    ) -> None:
        self._append("memory:equivalent", sensitivity="safe-public")
        self._append("memory:private", sensitivity="private")
        self._materialize()

        direct_repository = self.root / "direct"
        direct_repository.mkdir()
        self.store.close()
        direct = project_memory_pack(
            self.store_path,
            direct_repository,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=_authority(
                "foundation.projection.write",
                actor_id="foundation-brain-projector-v1",
            ),
        )
        hidden_store = self.store_path.with_suffix(".unavailable")
        self.store_path.rename(hidden_store)
        separated = project_released_memory_pack(
            self.public_store_path,
            self.repository,
            self.protected_projection,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=_authority(
                "foundation.projection.write",
                actor_id="foundation-brain-projector-v1",
            ),
        )
        self.store_path = hidden_store
        self.store = FoundationStore(self.store_path)

        self.assertEqual(direct.tree_digest, separated.tree_digest)
        self.assertEqual(
            _tree(direct_repository / PACK_DIRECTORY),
            _tree(self.repository / PACK_DIRECTORY),
        )
        self.assertTrue(separated.receipt_path.startswith("protected-state:"))
        self.assertFalse(
            (self.repository / ".hive-mind-projection-state").exists()
        )

    def test_non_null_protected_reference_fails_before_public_store_creation(
        self,
    ) -> None:
        self._append(
            "memory:protected",
            sensitivity="safe-public",
            protected_content_ref="protected://private/object",
        )
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "protected content references",
        ):
            self._materialize()
        self.assertFalse(self.public_store_path.exists())
        self.assertFalse(self.protected_release.exists())

    def test_private_store_and_protected_state_must_be_outside_repository(
        self,
    ) -> None:
        nested_store = self.repository / "private.sqlite3"
        nested = FoundationStore(nested_store)
        nested.register_repository(
            _identity(),
            authority=_authority("foundation.repository.register"),
        )
        nested.close()
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "outside the repository",
        ):
            materialize_public_memory(
                nested_store,
                self.public_store_path,
                self.repository,
                self.protected_release,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                authority=_release_authority(),
            )
        self._append("memory:public", sensitivity="safe-public")
        self.store.close()
        try:
            with self.assertRaisesRegex(
                PublicMemorySeparationError,
                "must be disjoint",
            ):
                materialize_public_memory(
                    self.store_path,
                    self.public_store_path,
                    self.repository,
                    self.repository / "ignored-private-state",
                    tenant_id=TENANT_ID,
                    repository_id=REPOSITORY_ID,
                    authority=_release_authority(),
                )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_public_store_cannot_share_private_root(self) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self.store.close()
        try:
            with self.assertRaisesRegex(
                PublicMemorySeparationError,
                "must not share",
            ):
                materialize_public_memory(
                    self.store_path,
                    self.private_root / "public.sqlite3",
                    self.repository,
                    self.protected_release,
                    tenant_id=TENANT_ID,
                    repository_id=REPOSITORY_ID,
                    authority=_release_authority(),
                )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_hardlinked_protected_lock_cannot_modify_external_bytes(self) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self.protected_release.mkdir()
        external = self.root / "external-lock"
        external.write_bytes(b"external")
        os.link(
            external,
            self.protected_release / "public-memory-release.lock",
        )
        before = external.read_bytes()
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "lock is unsafe",
        ):
            self._materialize()
        self.assertEqual(external.read_bytes(), before)
        self.assertFalse(self.public_store_path.exists())

    def test_wrong_authority_scope_and_wrong_public_store_scope_fail_closed(
        self,
    ) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self.store.close()
        try:
            with self.assertRaisesRegex(
                PublicMemorySeparationError,
                "does not allow this scope",
            ):
                materialize_public_memory(
                    self.store_path,
                    self.public_store_path,
                    self.repository,
                    self.protected_release,
                    tenant_id=TENANT_ID,
                    repository_id=REPOSITORY_ID,
                    authority=_release_authority(repository_id="repository:other"),
                )
        finally:
            self.store = FoundationStore(self.store_path)
        self.assertFalse(self.protected_release.exists())
        self.assertFalse(self.public_store_path.exists())
        self._materialize()
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "repository_id mismatch",
        ):
            read_public_memory_release_snapshot(
                self.public_store_path,
                tenant_id=TENANT_ID,
                repository_id="repository:other",
            )

    def test_interruption_after_public_commit_is_idempotently_recovered(self) -> None:
        self._append("memory:restart", sensitivity="safe-public")
        with self.assertRaisesRegex(InterruptedError, "post-public-commit"):
            self._materialize(fail_after_public_commit=True)
        pending = list((self.protected_release / "transactions").glob("*.json"))
        self.assertEqual(len(pending), 1)
        recovered = self._materialize()
        self.assertEqual(recovered.status, "unchanged")
        self.assertEqual(recovered.existing_record_count, 1)
        self.assertFalse((self.protected_release / "transactions").exists())
        self.assertEqual(
            len(list((self.protected_release / "receipts").glob("*.json"))),
            1,
        )

    def test_changed_source_after_public_commit_recovers_prior_receipt_first(
        self,
    ) -> None:
        self._append("memory:first", sensitivity="safe-public")
        with self.assertRaisesRegex(InterruptedError, "post-public-commit"):
            self._materialize(fail_after_public_commit=True)
        first_transaction = next(
            (self.protected_release / "transactions").glob("*.json")
        )
        first_journal = json.loads(first_transaction.read_bytes())

        self._append("memory:second", sensitivity="safe-public")
        result = self._materialize()

        self.assertEqual(result.status, "materialized")
        self.assertEqual(result.released_record_count, 1)
        self.assertEqual(result.existing_record_count, 1)
        self.assertFalse((self.protected_release / "transactions").exists())
        receipts = [
            json.loads(path.read_bytes())
            for path in sorted((self.protected_release / "receipts").glob("*.json"))
        ]
        self.assertEqual(len(receipts), 2)
        prior = next(
            receipt
            for receipt in receipts
            if receipt["batch_id"] == first_journal["batch_id"]
        )
        self.assertEqual(prior["source_cursor"], first_journal["source_cursor"])
        self.assertEqual(len(prior["release_ids"]), 1)

    def test_public_store_is_append_only_self_identifying_and_tamper_evident(
        self,
    ) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self._materialize()
        connection = sqlite3.connect(self.public_store_path)
        try:
            with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                connection.execute(
                    "UPDATE released_memory SET source_digest='sha256:"
                    + ("0" * 64)
                    + "'"
                )
        finally:
            connection.close()
        snapshot = read_public_memory_release_snapshot(
            self.public_store_path,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
        )
        self.assertEqual(len(snapshot.records), 1)

    def test_oversized_tampered_public_envelope_is_rejected_before_json_read(
        self,
    ) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self._materialize()
        connection = sqlite3.connect(self.public_store_path)
        try:
            connection.execute(
                "INSERT INTO released_memory VALUES(?,?,?,?,?,?,?,?)",
                (
                    "release:oversized",
                    "memory-record:oversized",
                    "sha256:" + ("1" * 64),
                    "sha256:" + ("2" * 64),
                    "{" + (" " * MAX_ENVELOPE_BYTES) + "}",
                    "decision:item2:oversized",
                    PUBLIC_MEMORY_RELEASER,
                    "2025-01-01T00:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "envelope exceeds size bound",
        ):
            read_public_memory_release_snapshot(
                self.public_store_path,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
            )
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "envelope exceeds size bound",
        ):
            self._materialize()

    def test_newer_public_store_version_fails_read_only_admission(self) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self._materialize()
        connection = sqlite3.connect(self.public_store_path)
        try:
            connection.execute("PRAGMA user_version=2")
        finally:
            connection.close()
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "schema 2 is not supported",
        ):
            read_public_memory_release_snapshot(
                self.public_store_path,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
            )

    def test_public_append_requires_verified_materialization_seal(self) -> None:
        self._append("memory:public", sensitivity="safe-public")
        self._materialize()
        connection = sqlite3.connect(self.public_store_path)
        try:
            envelope = json.loads(
                connection.execute(
                    "SELECT envelope_json FROM released_memory"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        snapshot = read_public_memory_release_snapshot(
            self.public_store_path,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
        )
        release_store = PublicMemoryReleaseStore(
            self.public_store_path,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            repository_identity_digest=snapshot.repository_identity_digest,
            source_foundation_schema_version=snapshot.schema_version,
            source_foundation_schema_digest=snapshot.schema_digest,
        )
        try:
            self.assertFalse(hasattr(release_store, "append_envelopes"))
            with self.assertRaisesRegex(
                PublicMemorySeparationError,
                "materialization seal",
            ):
                release_store._append_verified_envelopes(
                    [envelope],
                    authority=_release_authority(),
                    materialization_seal=object(),
                    expected_logical_digest=release_store.logical_digest(),
                )
        finally:
            release_store.close()

    def test_public_and_protected_persistence_roots_are_disjoint(self) -> None:
        self._append("memory:public", sensitivity="safe-public")
        with self.assertRaisesRegex(
            PublicMemorySeparationError,
            "must not share",
        ):
            self._materialize(
                protected_state_root=self.public_root / "private-state"
            )
        self.assertFalse((self.public_root / "private-state").exists())
        self._materialize()
        with self.assertRaisesRegex(
            ProjectionError,
            "source persistence must be disjoint",
        ):
            project_released_memory_pack(
                self.public_store_path,
                self.repository,
                self.public_root,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                authority=_authority(
                    "foundation.projection.write",
                    actor_id="foundation-brain-projector-v1",
                ),
            )
        self.assertFalse((self.public_root / "projection.lock").exists())

    def test_dedicated_release_and_separated_projection_commands_round_trip(
        self,
    ) -> None:
        self._append("memory:cli", sensitivity="safe-public")
        self.store.close()
        commands = (
            (
                [
                    "release",
                    "--store",
                    str(self.store_path),
                    "--public-store",
                    str(self.public_store_path),
                    "--repo",
                    str(self.repository),
                    "--protected-state",
                    str(self.protected_release),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ],
                "hive-public-memory-materialization-result/v1",
            ),
            (
                [
                    "project-separated",
                    "--public-store",
                    str(self.public_store_path),
                    "--repo",
                    str(self.repository),
                    "--protected-state",
                    str(self.protected_projection),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ],
                "hive-brain-projection-result/v1",
            ),
            (
                [
                    "check-separated",
                    "--public-store",
                    str(self.public_store_path),
                    "--repo",
                    str(self.repository),
                    "--protected-state",
                    str(self.protected_projection),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ],
                "hive-brain-projection-result/v1",
            ),
        )
        try:
            for arguments, schema_version in commands:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = run_brain(arguments)
                self.assertEqual(exit_code, 0)
                self.assertEqual(
                    json.loads(output.getvalue())["schema_version"],
                    schema_version,
                )
        finally:
            self.store = FoundationStore(self.store_path)

    def test_item2_contracts_are_additive_and_frozen_surfaces_remain_exact(
        self,
    ) -> None:
        self.assertEqual(len(PUBLIC_MEMORY_SCHEMA_NAMES), 3)
        self.assertTrue(validate_public_memory_catalog().valid)
        self.assertEqual(
            (len(hive_mind_os.__all__), len(package_system.__all__)),
            (131, 33),
        )
        self.assertEqual(cli_inventory()["parser_count"], 13)
        self.assertEqual(PublicMemoryReleaseStore.__module__.split(".")[-1], "public_memory")
        repository = Path(__file__).parents[1]
        committed = json.loads(
            (
                repository
                / "evidence"
                / "phase3"
                / "phase3_memory_separation_inventory.json"
            ).read_bytes()
        )
        self.assertEqual(build_phase3_item2_inventory(repository), committed)
        self.assertEqual(
            (
                committed["generation_zero"]["root_api_count"],
                committed["generation_zero"]["package_api_count"],
                committed["generation_zero"]["cli_parser_count"],
                committed["generation_zero"]["definition_count"],
            ),
            (131, 33, 13, 304),
        )
        self.assertEqual(committed["phase2_input"]["foundation_schema_count"], 17)
        self.assertEqual(
            committed["phase3_item1_input"]["projection_schema_count"],
            7,
        )
        self.assertTrue(committed["deterministic_fixture"]["trees_equal"])


if __name__ == "__main__":
    unittest.main()
