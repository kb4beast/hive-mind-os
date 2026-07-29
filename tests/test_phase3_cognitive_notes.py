from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation import cognitive
from hive_mind_os.foundation.brain_contracts import PROJECTION_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive import (
    MANAGED_NAMESPACE,
    MAX_PUBLIC_STORE_BYTES,
    CognitiveProjectionError,
    project_cognitive_notes,
)
from hive_mind_os.foundation.cognitive import run as run_cognitive
from hive_mind_os.foundation.cognitive_contracts import (
    COGNITIVE_SCHEMA_NAMES,
    validate_cognitive,
    validate_cognitive_catalog,
)
from hive_mind_os.foundation.contracts import PHASE2_SCHEMA_NAMES
from hive_mind_os.foundation.public_memory import (
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    materialize_public_memory,
)
from hive_mind_os.foundation.public_memory_contracts import PUBLIC_MEMORY_SCHEMA_NAMES
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import cli_inventory
from scripts.phase3_cognitive_notes_inventory import build_phase3_item3_inventory
from tests.test_phase3_open_brain import (
    REPOSITORY_ID,
    TENANT_ID,
    _authority,
    _create_directory_link,
    _identity,
    _memory_payload,
    _remove_directory_link,
)

KIND_FOLDER = {
    "opportunity": "ideas",
    "semantic": "evidence",
    "procedural": "evidence",
    "not-applicable": "evidence",
    "decision": "courts",
    "counterfactual": "courts",
    "governance": "courts",
    "working": "runs",
    "episodic": "runs",
    "prospective": "runs",
    "social": "agents",
    "evaluation": "telemetry",
    "resource": "telemetry",
}


def _release_authority():
    decision = __import__(
        "hive_mind_os.foundation.authority",
        fromlist=["decide_foundation_write"],
    ).decide_foundation_write(
        role=Role.BUILDER,
        action=PUBLIC_MEMORY_RELEASE_ACTION,
        policy_decision=PolicyDecision(True, "item-3 fixture"),
        lease_actions={PUBLIC_MEMORY_RELEASE_ACTION},
        adapter_actions={PUBLIC_MEMORY_RELEASE_ACTION},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=TENANT_ID,
        repository_id=REPOSITORY_ID,
        actor_id=PUBLIC_MEMORY_RELEASER,
        decision_id="decision:item3:release",
        lease_id="lease:item3:release",
    )
    if not decision.allowed:
        raise AssertionError(decision)
    return decision


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class StableIdCognitiveNoteTests(unittest.TestCase):
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
        self.public_store = self.public_root / "safe-public.sqlite3"
        self.release_state = self.root / "protected-release"
        self.cognitive_state = self.root / "protected-cognitive"
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
        memory_kind: str,
        *,
        sensitivity: str = "safe-public",
    ) -> dict:
        payload = _memory_payload(memory_id, sensitivity=sensitivity)
        payload["memory_kind"] = memory_kind
        payload["source_refs"] = [f"source:{memory_id}"]
        payload["claim_refs"] = [f"claim:{memory_id}"]
        payload["evidence_refs"] = [f"evidence:{memory_id}"]
        payload["court_refs"] = [f"court:{memory_id}"]
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
            stream_id=f"item3:{memory_id}",
            payload=payload,
            actor_id="builder",
            idempotency_key=f"item3:{memory_id}",
            observed_at=payload["observed_at"],
            sensitivity=sensitivity,
        )

    def _release(self) -> None:
        self.store.close()
        try:
            materialize_public_memory(
                self.store_path,
                self.public_store,
                self.repository,
                self.release_state,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                authority=_release_authority(),
            )
        finally:
            self.store = FoundationStore(self.store_path)

    def _project(self, *, check: bool = False, **kwargs):
        return project_cognitive_notes(
            self.public_store,
            self.repository,
            self.cognitive_state,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            check=check,
            authority=(
                None
                if check
                else _authority(
                    "foundation.projection.write",
                    actor_id="foundation-cognitive-projector-v1",
                )
            ),
            **kwargs,
        )

    def test_all_memory_kinds_map_once_and_home_reconciles(self) -> None:
        for index, memory_kind in enumerate(KIND_FOLDER):
            self._append(f"memory:{index}:{memory_kind}", memory_kind)
        self._append("memory:private-marker", "resource", sensitivity="private")
        self._release()
        self.store.close()
        hidden_private = self.store_path.with_suffix(".unavailable")
        self.store_path.rename(hidden_private)

        result = self._project()
        namespace = self.repository / MANAGED_NAMESPACE
        manifest = json.loads((namespace / "manifest.json").read_bytes())
        files = _tree(namespace)

        self.assertEqual(result.status, "projected")
        self.assertEqual(result.projected_record_count, len(KIND_FOLDER))
        self.assertEqual(manifest["note_counts"]["total"], len(KIND_FOLDER))
        self.assertEqual(
            sum(manifest["note_counts"][folder] for folder in set(KIND_FOLDER.values())),
            len(KIND_FOLDER),
        )
        self.assertIn("HOME.md", files)
        self.assertNotIn(b"memory:private-marker", b"".join(files.values()))
        for memory_kind, folder in KIND_FOLDER.items():
            self.assertEqual(
                manifest["note_counts"][folder],
                sum(value == folder for value in KIND_FOLDER.values()),
            )
            matching = [
                content
                for path, content in files.items()
                if path.startswith(f"{folder}/")
                and f'memory_kind: "{memory_kind}"'.encode() in content
            ]
            self.assertEqual(len(matching), 1)
        telemetry = b"".join(
            content
            for path, content in files.items()
            if path.startswith("telemetry/")
        )
        self.assertIn(b"Usage accounting is unavailable", telemetry)
        for forbidden in (b"input_tokens", b"output_tokens", b"provider_request_id"):
            self.assertNotIn(forbidden, telemetry)

        self.store_path = hidden_private
        self.store = FoundationStore(self.store_path)

    def test_repeat_check_and_unrelated_record_preserve_existing_ids(self) -> None:
        self._append("memory:first", "opportunity")
        self._release()
        first = self._project()
        namespace = self.repository / MANAGED_NAMESPACE
        first_manifest = json.loads((namespace / "manifest.json").read_bytes())
        first_note = next(
            entry
            for entry in first_manifest["files"]
            if entry["source_record_id"] is not None
        )

        self.assertEqual(self._project().status, "unchanged")
        self.assertEqual(self._project(check=True).status, "unchanged")
        self._append("memory:unrelated", "social")
        self._release()
        updated = self._project()
        updated_manifest = json.loads((namespace / "manifest.json").read_bytes())
        same_note = next(
            entry
            for entry in updated_manifest["files"]
            if entry["source_record_id"] == first_note["source_record_id"]
        )

        self.assertEqual(first.status, "projected")
        self.assertEqual(updated.status, "projected")
        self.assertEqual(same_note["note_id"], first_note["note_id"])
        self.assertEqual(same_note["path"], first_note["path"])
        self.assertTrue((namespace / same_note["path"]).is_file())

    def test_check_is_read_only_and_edit_conflicts_without_overwrite(self) -> None:
        self._append("memory:edit", "decision")
        self._release()
        checked = self._project(check=True)
        self.assertEqual(checked.status, "drift")
        self.assertFalse((self.repository / MANAGED_NAMESPACE).exists())
        self.assertFalse(self.cognitive_state.exists())

        self._project()
        namespace = self.repository / MANAGED_NAMESPACE
        manifest = json.loads((namespace / "manifest.json").read_bytes())
        path = namespace / next(
            entry["path"]
            for entry in manifest["files"]
            if entry["source_record_id"] is not None
        )
        edited = path.read_bytes() + b"\nHuman edit survives.\n"
        path.write_bytes(edited)
        conflict = self._project()
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(path.read_bytes(), edited)
        self.assertIsNotNone(conflict.receipt_path)
        self.assertEqual(
            len(list((self.cognitive_state / "conflicts").glob("*/conflict.json"))),
            1,
        )

    def test_interrupted_first_publish_recovers_exact_tree(self) -> None:
        self._append("memory:restart", "episodic")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=1)
        recovered = self._project()
        self.assertEqual(recovered.status, "projected")
        self.assertEqual(recovered.recovery_status, "recovered")
        self.assertEqual(self._project().status, "unchanged")

    def test_interruption_after_manifest_install_recovers_and_receipts(self) -> None:
        self._append("memory:manifest-last", "episodic")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=3)
        namespace = self.repository / MANAGED_NAMESPACE
        self.assertTrue((namespace / "manifest.json").is_file())
        self.assertFalse((self.cognitive_state / "receipts").exists())

        recovered = self._project()
        self.assertEqual(recovered.status, "projected")
        self.assertEqual(recovered.recovery_status, "recovered")
        self.assertEqual(len(list(namespace.rglob(".cognitive-*"))), 0)
        self.assertEqual(self._project().status, "unchanged")

    def test_restart_cleans_manifest_install_hardlink_crash_window(self) -> None:
        self._append("memory:manifest-link-window", "episodic")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=2)
        transaction = next((self.cognitive_state / "transactions").iterdir())
        staged_manifest = (
            transaction / "files" / sha256("manifest.json".encode()).hexdigest()
        )
        namespace = self.repository / MANAGED_NAMESPACE
        install = (
            namespace
            / f".manifest.json.cognitive-next-{transaction.name}"
        )
        install.write_bytes(staged_manifest.read_bytes())
        os.link(install, namespace / "manifest.json")

        recovered = self._project()
        self.assertEqual(recovered.status, "projected")
        self.assertEqual(recovered.recovery_status, "recovered")
        self.assertFalse(install.exists())
        self.assertEqual(
            (namespace / "manifest.json").stat().st_nlink,
            1,
        )
        self.assertEqual(self._project().status, "unchanged")

    def test_recovery_rejects_junction_without_external_write(self) -> None:
        self._append("memory:junction", "opportunity")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=1)
        namespace = self.repository / MANAGED_NAMESPACE
        ideas = namespace / "ideas"
        ideas.rmdir()
        external = self.root / "external"
        external.mkdir()
        try:
            _create_directory_link(ideas, external)
        except OSError as error:
            self.skipTest(f"directory links unavailable: {error}")
        try:
            result = self._project()
            self.assertEqual(result.status, "conflict")
            self.assertIsNotNone(result.receipt_path)
            self.assertEqual(list(external.iterdir()), [])
        finally:
            _remove_directory_link(ideas)

    def test_changed_snapshot_finishes_sealed_prior_then_current(self) -> None:
        self._append("memory:prior", "episodic")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=1)
        self._append("memory:current", "social")
        self._release()
        result = self._project()
        self.assertEqual(result.status, "projected")
        self.assertEqual(result.projected_record_count, 2)
        self.assertEqual(
            len(list((self.cognitive_state / "receipts").glob("*.json"))),
            2,
        )
        self.assertEqual(self._project().status, "unchanged")

    def test_tampered_staged_manifest_cannot_receive_completion_receipt(self) -> None:
        self._append("memory:tamper", "decision")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=1)
        transaction = next((self.cognitive_state / "transactions").iterdir())
        journal_path = transaction / "transaction.json"
        journal = json.loads(journal_path.read_bytes())
        staged_manifest = (
            transaction
            / "files"
            / sha256("manifest.json".encode()).hexdigest()
        )
        hostile = b'{"schema_version":"not-a-cognitive-manifest"}\n'
        staged_manifest.write_bytes(hostile)
        hostile_digest = "sha256:" + sha256(hostile).hexdigest()
        manifest_operation = next(
            item for item in journal["operations"] if item["path"] == "manifest.json"
        )
        manifest_operation["desired_digest"] = hostile_digest
        journal_path.write_text(
            json.dumps(journal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        with self.assertRaisesRegex(
            CognitiveProjectionError,
            "manifest operation is inconsistent",
        ):
            self._project()
        self.assertFalse((self.cognitive_state / "receipts").exists())
        self.assertTrue(transaction.exists())

    def test_corrupt_receipt_operation_fails_closed(self) -> None:
        self._append("memory:receipt-one", "semantic")
        self._release()
        self._project()
        receipt_path = next((self.cognitive_state / "receipts").glob("*.json"))
        receipt = json.loads(receipt_path.read_bytes())
        note_operation = next(
            operation
            for operation in receipt["operations"]
            if operation["path"].startswith("evidence/")
        )
        note_operation["desired_digest"] = "sha256:" + ("f" * 64)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(
            CognitiveProjectionError,
            "receipt file plan is inconsistent",
        ):
            self._project(check=True)

    def test_extra_historical_receipt_operation_fails_closed(self) -> None:
        self._append("memory:history-one", "opportunity")
        self._release()
        self._project()
        first_receipt = next((self.cognitive_state / "receipts").glob("*.json"))
        self._append("memory:history-two", "social")
        self._release()
        self._project()

        receipt = json.loads(first_receipt.read_bytes())
        receipt["operations"].append(
            {
                "path": f"ideas/{'a' * 64}.md",
                "expected_prior_digest": None,
                "desired_digest": "sha256:" + ("f" * 64),
            }
        )
        first_receipt.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(
            CognitiveProjectionError,
            "receipt prior plan is inconsistent",
        ):
            self._project(check=True)

    def test_receipt_no_op_operation_fails_closed(self) -> None:
        self._append("memory:no-op-receipt", "opportunity")
        self._release()
        self._project()
        receipt_path = next((self.cognitive_state / "receipts").glob("*.json"))
        receipt = json.loads(receipt_path.read_bytes())
        receipt["operations"].append(
            {
                "path": f"ideas/{'b' * 64}.md",
                "expected_prior_digest": None,
                "desired_digest": None,
            }
        )
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(
            CognitiveProjectionError,
            "operation cannot be a no-op",
        ):
            self._project(check=True)

    def test_receipt_history_above_python_recursion_limit_is_iterative(self) -> None:
        self._append("memory:long-history", "semantic")
        self._release()
        self._project()
        receipts = self.cognitive_state / "receipts"
        head_path = next(receipts.glob("*.json"))
        template = json.loads(head_path.read_bytes())
        digests = [
            template["desired_manifest_digest"],
            *[
                "sha256:" + sha256(f"history:{index}".encode()).hexdigest()
                for index in range(1_050)
            ],
        ]
        base_desired = {
            operation["path"]: operation["desired_digest"]
            for operation in template["operations"]
        }
        for index, digest in enumerate(digests):
            prior_digest = (
                digests[index + 1] if index + 1 < len(digests) else None
            )
            prior_desired = (
                {
                    **base_desired,
                    "manifest.json": prior_digest,
                }
                if prior_digest is not None
                else {}
            )
            receipt = {
                **template,
                "transaction_id": digest.removeprefix("sha256:"),
                "prior_manifest_digest": prior_digest,
                "desired_manifest_digest": digest,
                "verified_manifest_digest": digest,
                "operations": [
                    {
                        **operation,
                        "expected_prior_digest": prior_desired.get(
                            operation["path"]
                        ),
                        "desired_digest": (
                            digest
                            if operation["path"] == "manifest.json"
                            else operation["desired_digest"]
                        ),
                    }
                    for operation in template["operations"]
                ],
            }
            path = receipts / f"{digest.removeprefix('sha256:')}.json"
            path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        self.assertEqual(self._project(check=True).status, "unchanged")

    def test_forged_prior_plan_fails_closed(self) -> None:
        self._append("memory:prior-one", "semantic")
        self._release()
        self._project()
        self._append("memory:prior-two", "social")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=1)
        transaction = next((self.cognitive_state / "transactions").iterdir())
        journal_path = transaction / "transaction.json"
        journal = json.loads(journal_path.read_bytes())
        prior_operation = next(
            operation
            for operation in journal["operations"]
            if operation["expected_prior_digest"] is not None
        )
        prior_operation["expected_prior_digest"] = "sha256:" + ("e" * 64)
        journal_path.write_text(
            json.dumps(journal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(
            CognitiveProjectionError,
            "prior plan is inconsistent",
        ):
            self._project()

    def test_late_human_write_is_preserved_with_typed_conflict(self) -> None:
        self._append("memory:race-one", "opportunity")
        self._release()
        self._project()
        self._append("memory:race-two", "social")
        self._release()
        namespace = self.repository / MANAGED_NAMESPACE
        home = namespace / "HOME.md"
        human = b"# Human-owned HOME\n"
        real_link = os.link

        def racing_link(source, destination, *args, **kwargs):
            destination_path = Path(destination)
            if destination_path == home:
                destination_path.write_bytes(human)
            return real_link(source, destination, *args, **kwargs)

        with patch.object(cognitive.os, "link", side_effect=racing_link):
            result = self._project()

        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.recovery_status, "conflict-preserved")
        self.assertEqual(result.conflict_paths, ("HOME.md",))
        self.assertEqual(home.read_bytes(), human)
        self.assertIsNotNone(result.receipt_path)
        conflict_path = (
            self.cognitive_state
            / str(result.receipt_path).removeprefix("protected-state:")
        )
        self.assertTrue(conflict_path.is_file())

    def test_late_junction_swap_is_rolled_back_as_typed_conflict(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows no-delete junction regression")
        self._append("memory:late-junction", "opportunity")
        self._release()
        namespace = self.repository / MANAGED_NAMESPACE
        ideas = namespace / "ideas"
        external = self.root / "late-junction-external"
        external.mkdir()
        probe = self.root / "junction-probe"
        try:
            _create_directory_link(probe, external)
        except OSError as error:
            self.skipTest(f"directory links unavailable: {error}")
        else:
            _remove_directory_link(probe)
        real_link = os.link
        swapped = False

        def racing_link(source, destination, *args, **kwargs):
            nonlocal swapped
            source_path = Path(source)
            destination_path = Path(destination)
            if destination_path.parent == ideas and not swapped:
                swapped = True
                prepared = external / source_path.name
                source_path.replace(prepared)
                ideas.rmdir()
                _create_directory_link(ideas, external)
            return real_link(source, destination, *args, **kwargs)

        try:
            with patch.object(cognitive.os, "link", side_effect=racing_link):
                result = self._project()
            self.assertEqual(result.status, "conflict")
            self.assertEqual(result.recovery_status, "conflict-preserved")
            self.assertIsNotNone(result.receipt_path)
            self.assertEqual(list(external.iterdir()), [])
        finally:
            is_junction = getattr(ideas, "is_junction", lambda: False)
            if ideas.is_symlink() or is_junction():
                _remove_directory_link(ideas)

    def test_unjournaled_reserved_sibling_conflicts_before_recovery_mutation(
        self,
    ) -> None:
        self._append("memory:reserved-sibling", "opportunity")
        self._release()
        with self.assertRaisesRegex(InterruptedError, "interruption"):
            self._project(fail_after_replacements=1)
        namespace = self.repository / MANAGED_NAMESPACE
        unrelated = (
            namespace
            / f".HOME.md.cognitive-prior-{'f' * 64}"
        )
        human = b"human reserved-looking bytes"
        unrelated.write_bytes(human)

        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.recovery_status, "conflict-preserved")
        self.assertEqual(unrelated.read_bytes(), human)
        self.assertFalse((namespace / "manifest.json").exists())
        self.assertIsNotNone(result.receipt_path)

    def test_existing_malformed_conflict_receipt_fails_closed(self) -> None:
        self._append("memory:conflict-contract", "decision")
        self._release()
        self._project()
        namespace = self.repository / MANAGED_NAMESPACE
        manifest = json.loads((namespace / "manifest.json").read_bytes())
        note = namespace / next(
            entry["path"]
            for entry in manifest["files"]
            if entry["source_record_id"] is not None
        )
        note.write_bytes(note.read_bytes() + b"\nHuman edit.\n")
        first = self._project()
        self.assertEqual(first.status, "conflict")
        conflict_path = (
            self.cognitive_state
            / str(first.receipt_path).removeprefix("protected-state:")
        )
        document = json.loads(conflict_path.read_bytes())
        del document["attempted_at"]
        conflict_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        with self.assertRaisesRegex(
            CognitiveProjectionError,
            "conflict receipt contract failed",
        ):
            self._project()

    def test_abandoned_staging_and_completed_stale_transaction_are_recoverable(
        self,
    ) -> None:
        self._append("memory:abandoned", "semantic")
        self._release()
        abandoned = self.cognitive_state / "transactions" / ("a" * 64)
        (abandoned / "files").mkdir(parents=True)
        (abandoned / "files" / "partial").write_bytes(b"partial")
        first = self._project()
        self.assertEqual(first.status, "projected")
        self.assertFalse(abandoned.exists())

        receipt = next((self.cognitive_state / "receipts").glob("*.json"))
        stale = self.cognitive_state / "transactions" / receipt.stem
        stale.mkdir(parents=True)
        (stale / "transaction.json").write_bytes(b"{malformed")
        second = self._project()
        self.assertEqual(second.status, "unchanged")
        self.assertFalse(stale.exists())

    def test_catalog_cli_and_frozen_surfaces(self) -> None:
        self.assertEqual(len(COGNITIVE_SCHEMA_NAMES), 8)
        self.assertTrue(validate_cognitive_catalog().valid)
        self.assertEqual(
            (len(PHASE2_SCHEMA_NAMES), len(PROJECTION_SCHEMA_NAMES), len(PUBLIC_MEMORY_SCHEMA_NAMES)),
            (17, 7, 3),
        )
        self.assertEqual(
            (len(hive_mind_os.__all__), len(package_system.__all__), cli_inventory()["parser_count"]),
            (131, 33, 13),
        )
        malformed = {
            "schema_version": "hive-cognitive-manifest/v1",
            "self_granted_authority": True,
        }
        validation = validate_cognitive("cognitive-manifest-v1", malformed)
        self.assertFalse(validation.valid)
        self.assertTrue(any("unknown properties" in issue for issue in validation.issues))
        fabricated_result = {
            "schema_version": "hive-cognitive-result/v1",
            "status": "unchanged",
            "tenant_id": TENANT_ID,
            "repository_id": REPOSITORY_ID,
            "repository_identity_digest": "sha256:" + ("0" * 64),
            "namespace_path": str(self.repository / MANAGED_NAMESPACE),
            "manifest_digest": "sha256:" + ("1" * 64),
            "source_cursor": "memory-set:" + ("2" * 64),
            "tree_digest": "sha256:" + ("3" * 64),
            "source_record_count": 0,
            "projected_record_count": 0,
            "note_counts": {"input_tokens": 0, "cost_usd": 0},
            "recovery_status": "not-required",
            "conflict_paths": [],
            "receipt_path": None,
        }
        self.assertFalse(
            validate_cognitive("cognitive-result-v1", fabricated_result).valid
        )

        self._append("memory:cli", "resource")
        self._release()
        output = StringIO()
        with redirect_stdout(output):
            exit_code = run_cognitive(
                [
                    "project",
                    "--public-store",
                    str(self.public_store),
                    "--repo",
                    str(self.repository),
                    "--protected-state",
                    str(self.cognitive_state),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(output.getvalue())["schema_version"],
            "hive-cognitive-result/v1",
        )
        error = StringIO()
        with redirect_stderr(error):
            failed = run_cognitive(
                [
                    "check",
                    "--public-store",
                    str(self.root / "missing.sqlite3"),
                    "--repo",
                    str(self.repository),
                    "--protected-state",
                    str(self.cognitive_state),
                    "--tenant",
                    TENANT_ID,
                    "--repository-id",
                    REPOSITORY_ID,
                ]
            )
        self.assertEqual(failed, 2)
        self.assertEqual(
            json.loads(error.getvalue())["schema_version"],
            "hive-cognitive-failure/v1",
        )
        repository = Path(__file__).parents[1]
        committed = json.loads(
            (
                repository
                / "evidence"
                / "phase3"
                / "phase3_cognitive_notes_inventory.json"
            ).read_bytes()
        )
        self.assertEqual(build_phase3_item3_inventory(repository), committed)

    def test_wrong_scope_and_overlap_fail_closed(self) -> None:
        self._append("memory:scope", "semantic")
        self._release()
        with self.assertRaises(CognitiveProjectionError):
            project_cognitive_notes(
                self.public_store,
                self.repository,
                self.repository / "protected",
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                authority=_authority(
                    "foundation.projection.write",
                    actor_id="foundation-cognitive-projector-v1",
                ),
            )
        self.assertFalse((self.repository / MANAGED_NAMESPACE).exists())

    def test_public_store_total_size_and_hostile_text_fail_before_output(self) -> None:
        oversized = self.public_root / "oversized.sqlite3"
        with oversized.open("wb") as handle:
            handle.seek(MAX_PUBLIC_STORE_BYTES)
            handle.write(b"\0")
        with self.assertRaisesRegex(CognitiveProjectionError, "read bound"):
            project_cognitive_notes(
                oversized,
                self.repository,
                self.cognitive_state,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            )
        self.assertFalse((self.repository / MANAGED_NAMESPACE).exists())
        self.assertFalse(self.cognitive_state.exists())

        self._append("memory:\u202ehostile", "semantic")
        self._release()
        with self.assertRaisesRegex(CognitiveProjectionError, "control"):
            self._project(check=True)
        self.assertFalse((self.repository / MANAGED_NAMESPACE).exists())


if __name__ == "__main__":
    unittest.main()
