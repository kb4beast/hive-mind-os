from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.package_system as package_system
import tests.test_phase3_cognitive_notes as cognitive_notes_tests
from hive_mind_os.foundation import cognitive_views
from hive_mind_os.foundation.brain_contracts import PROJECTION_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive_contracts import COGNITIVE_SCHEMA_NAMES
from hive_mind_os.foundation.cognitive_view_contracts import (
    COGNITIVE_VIEW_SCHEMA_NAMES,
    validate_cognitive_view,
    validate_cognitive_view_catalog,
)
from hive_mind_os.foundation.contracts import PHASE2_SCHEMA_NAMES
from hive_mind_os.foundation.public_memory_contracts import PUBLIC_MEMORY_SCHEMA_NAMES
from scripts.phase1_surface_inventory import cli_inventory
from scripts.phase3_cognitive_views_inventory import build_phase3_item4_inventory

REPOSITORY_ID = cognitive_notes_tests.REPOSITORY_ID
TENANT_ID = cognitive_notes_tests.TENANT_ID


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class CognitiveViewProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = cognitive_notes_tests.StableIdCognitiveNoteTests(
            "test_all_memory_kinds_map_once_and_home_reconciles"
        )
        self.fixture.setUp()
        self.fixture._append("memory:view:idea", "opportunity")
        self.fixture._append("memory:view:agent", "social")
        self.fixture._append("memory:view:telemetry", "resource")
        self.fixture._release()
        self.fixture._project()
        self.repository = self.fixture.repository
        self.cognitive_state = self.fixture.cognitive_state
        self.view_state = self.fixture.root / "protected-views"
        self.authority = cognitive_notes_tests._authority(
            "foundation.projection.write",
            actor_id=cognitive_views.VIEW_ACTOR,
        )

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _project(self, **kwargs):
        return cognitive_views.project_cognitive_views(
            self.repository,
            self.cognitive_state,
            self.view_state,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=self.authority,
            clock=lambda: "2026-07-29T20:00:00+00:00",
            **kwargs,
        )

    def test_exact_artifacts_truthful_canvas_and_strict_bases(self) -> None:
        item1 = self.repository / "hive-mind" / "generated"
        item1.mkdir(parents=True)
        (item1 / "sentinel.json").write_bytes(b'{"owned":"item1"}\n')
        item1_before = _tree(item1)
        source_before = _tree(self.repository / cognitive_views.SOURCE_NAMESPACE)
        result = self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        files = _tree(root)
        self.assertEqual(result.status, "projected")
        self.assertEqual(
            sorted(files),
            [
                "bases/agent-records.base",
                "bases/ideas.base",
                "bases/released-war-room.base",
                "bases/telemetry-metadata.base",
                "canvases/war-room.canvas",
                "manifest.json",
            ],
        )
        manifest = json.loads(files["manifest.json"])
        self.assertTrue(
            validate_cognitive_view("cognitive-view-manifest-v1", manifest).valid
        )
        self.assertEqual(manifest["base_count"], 4)
        self.assertEqual(manifest["canvas_count"], 1)
        self.assertNotIn("source_receipt_digest", manifest)
        for path in (name for name in files if name.endswith(".base")):
            content = files[path]
            filter_block = content.split(b"properties:", 1)[0]
            self.assertEqual(filter_block.count(b"    - "), 8)
            self.assertIn(b'    - file.inFolder("', content)
            self.assertIn(b"is_generated == true", content)
            self.assertIn(b"is_authoritative == false", content)
            self.assertNotIn(b'    - "file.inFolder', content)
            self.assertNotIn(b'displayName: "', content)
            self.assertNotIn(b'    name: "', content)
            for forbidden in (
                b"formula",
                b"summary",
                b"now(",
                b"today(",
                b"this.",
                b"http:",
                b"https:",
            ):
                self.assertNotIn(forbidden, content)
        canvas = json.loads(files["canvases/war-room.canvas"])
        self.assertTrue(
            validate_cognitive_view("cognitive-view-canvas-v1", canvas).valid
        )
        self.assertEqual(canvas["edges"], [])
        self.assertEqual(len(canvas["nodes"]), 9)
        self.assertEqual(len({node["id"] for node in canvas["nodes"]}), 9)
        text = "\n".join(node.get("text", "") for node in canvas["nodes"])
        for required in (
            "not live",
            "scores and health are unavailable",
            "Unknown does not imply zero",
            "Loop state is unavailable",
            "Quarantine inventory is unavailable",
            "No all-clear is implied",
        ):
            self.assertIn(required, text)
        self.assertEqual(
            _tree(self.repository / cognitive_views.SOURCE_NAMESPACE),
            source_before,
        )
        self.assertEqual(_tree(item1), item1_before)

    def test_view_projection_never_opens_private_or_public_sqlite(self) -> None:
        with patch("sqlite3.connect", side_effect=AssertionError("SQLite opened")):
            self.assertEqual(self._project().status, "projected")

    def test_base_scalars_are_obsidian_stable_and_yaml_safe(self) -> None:
        self.assertEqual(
            cognitive_views._yaml_scalar('file.inFolder("generated")'),
            'file.inFolder("generated")',
        )
        self.assertEqual(
            cognitive_views._yaml_scalar("Released idea metadata"),
            "Released idea metadata",
        )
        self.assertEqual(cognitive_views._yaml_scalar("true"), '"true"')
        self.assertEqual(cognitive_views._yaml_scalar("unsafe: value"), '"unsafe: value"')

    def test_repeat_and_check_are_unchanged(self) -> None:
        first = self._project()
        tree = _tree(self.repository / cognitive_views.MANAGED_NAMESPACE)
        second = self._project()
        checked = cognitive_views.project_cognitive_views(
            self.repository,
            self.cognitive_state,
            self.view_state,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            check=True,
        )
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(checked.status, "unchanged")
        self.assertEqual(first.manifest_digest, second.manifest_digest)
        self.assertEqual(
            _tree(self.repository / cognitive_views.MANAGED_NAMESPACE), tree
        )

    def test_check_missing_view_state_creates_nothing(self) -> None:
        missing = self.fixture.root / "missing-view-state"
        result = cognitive_views.project_cognitive_views(
            self.repository,
            self.cognitive_state,
            missing,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            check=True,
        )
        self.assertEqual(result.status, "drift")
        self.assertFalse(missing.exists())
        self.assertFalse((self.repository / cognitive_views.MANAGED_NAMESPACE).exists())

    def test_cursor_change_preserves_base_canvas_bytes_and_node_ids(self) -> None:
        first = self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        stable = {
            path: content
            for path, content in _tree(root).items()
            if path != "manifest.json"
        }
        first_canvas = json.loads(stable["canvases/war-room.canvas"])
        self.fixture._append("memory:view:later", "decision")
        self.fixture._release()
        self.fixture._project()
        second = self._project()
        after = _tree(root)
        self.assertNotEqual(first.source_cursor, second.source_cursor)
        self.assertNotEqual(first.manifest_digest, second.manifest_digest)
        self.assertEqual(
            {
                path: content
                for path, content in after.items()
                if path != "manifest.json"
            },
            stable,
        )
        self.assertEqual(
            [
                node["id"]
                for node in json.loads(after["canvases/war-room.canvas"])["nodes"]
            ],
            [node["id"] for node in first_canvas["nodes"]],
        )

    def test_source_tamper_and_pending_transaction_fail_before_view_writes(
        self,
    ) -> None:
        source_root = self.repository / cognitive_views.SOURCE_NAMESPACE
        note = next(
            path for path in source_root.rglob("*.md") if path.name != "HOME.md"
        )
        original = note.read_bytes()
        note.write_bytes(original + b"\n")
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project()
        self.assertFalse(self.view_state.exists())
        note.write_bytes(original)
        transactions = self.cognitive_state / "transactions"
        transactions.mkdir(exist_ok=True)
        (transactions / ("0" * 64)).mkdir()
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "pending transactions"
        ):
            self._project()
        self.assertFalse(self.view_state.exists())

    def test_source_transaction_root_must_be_safe_directory(self) -> None:
        transactions = self.cognitive_state / "transactions"
        self.assertFalse(any(transactions.iterdir()))
        transactions.rmdir()
        transactions.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "transaction root is unsafe"
        ):
            cognitive_views.project_cognitive_views(
                self.repository,
                self.cognitive_state,
                self.view_state,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            )
        self.assertFalse(self.view_state.exists())

    def test_unmanaged_and_manual_edits_are_typed_conflicts(self) -> None:
        self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        target = root / "bases" / "ideas.base"
        target.write_bytes(target.read_bytes() + b"# human edit\n")
        (root / "human.md").write_text("keep", encoding="utf-8")
        before = _tree(root)
        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertEqual(set(result.conflict_paths), {"bases/ideas.base", "human.md"})
        self.assertEqual(_tree(root), before)
        self.assertIsNotNone(result.receipt_path)

    def test_missing_managed_file_is_preserved_as_conflict(self) -> None:
        self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        missing = root / "bases" / "ideas.base"
        missing.unlink()
        before = _tree(root)
        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertIn("bases/ideas.base", result.conflict_paths)
        self.assertEqual(_tree(root), before)
        self.assertFalse(missing.exists())

    def test_nested_source_directory_and_unmanaged_protected_state_fail(self) -> None:
        nested = (
            self.repository
            / cognitive_views.SOURCE_NAMESPACE
            / "ideas"
            / "unmanaged-empty"
        )
        nested.mkdir()
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "directories are not exact"
        ):
            self._project()
        nested.rmdir()
        self.view_state.mkdir()
        (self.view_state / "unmanaged").mkdir()
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "unmanaged paths"
        ):
            self._project()

    def test_interrupted_publication_recovers(self) -> None:
        with self.assertRaisesRegex(cognitive_views.CognitiveViewError, "injected"):
            self._project(fail_after_replacements=2)
        result = self._project()
        self.assertEqual(result.status, "projected")
        self.assertEqual(result.recovery_status, "recovered")
        self.assertEqual(
            cognitive_views.project_cognitive_views(
                self.repository,
                self.cognitive_state,
                self.view_state,
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            ).status,
            "unchanged",
        )

    def test_crash_after_hardlink_install_recovers_two_link_window(self) -> None:
        real_link = cognitive_views.os.link
        crashed = False

        def crash_after_link(source, destination):
            nonlocal crashed
            real_link(source, destination)
            if not crashed:
                crashed = True
                raise cognitive_views.CognitiveViewError("crash after hardlink")

        with (
            patch.object(cognitive_views.os, "link", side_effect=crash_after_link),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError, "crash after hardlink"
            ),
        ):
            self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        reserved = next(root.rglob("*.cognitive-view-next-*"))
        destination_name = reserved.name.split(".cognitive-view-next-", 1)[
            0
        ].removeprefix(".")
        destination = reserved.with_name(destination_name)
        self.assertTrue(cognitive_views.os.path.samefile(reserved, destination))
        self.assertEqual(reserved.stat().st_nlink, 2)
        result = self._project()
        self.assertEqual(result.recovery_status, "recovered")
        self.assertFalse(reserved.exists())
        self.assertEqual(destination.stat().st_nlink, 1)

    def test_interrupted_empty_preparation_is_preserved_then_retried(self) -> None:
        with (
            patch.object(
                cognitive_views,
                "_write_exclusive",
                side_effect=cognitive_views.CognitiveViewError(
                    "crash before preparation journal"
                ),
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash before preparation journal",
            ),
        ):
            self._project()
        result = self._project()
        self.assertEqual(result.status, "projected")
        self.assertTrue(any((self.view_state / "abandoned").iterdir()))

    def test_interrupted_partial_staging_is_preserved_then_retried(self) -> None:
        real_write = cognitive_views._write_exclusive
        calls = 0

        def crash_during_staging(path, content):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise cognitive_views.CognitiveViewError(
                    "crash during preparation staging"
                )
            return real_write(path, content)

        with (
            patch.object(
                cognitive_views,
                "_write_exclusive",
                side_effect=crash_during_staging,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash during preparation staging",
            ),
        ):
            self._project()
        result = self._project()
        self.assertEqual(result.status, "projected")
        abandoned = next(
            path
            for path in (self.view_state / "abandoned").iterdir()
            if path.is_dir()
        )
        self.assertTrue((abandoned / "transaction.json").is_file())
        receipt = self.view_state / "abandoned" / f"{abandoned.name}.json"
        self.assertEqual(
            json.loads(receipt.read_text(encoding="utf-8"))["transaction_id"],
            json.loads(
                abandoned.joinpath("transaction.json").read_text(encoding="utf-8")
            )["transaction_id"],
        )
        forged = json.loads(receipt.read_text(encoding="utf-8"))
        forged["transaction_id"] = "0" * 64
        forged_bytes = (
            json.dumps(
                forged,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        forged_identity = sha256(forged_bytes.encode()).hexdigest()
        forged_receipt = receipt.with_name(f"{forged_identity}.json")
        receipt.rename(forged_receipt)
        forged_receipt.write_bytes(forged_bytes.encode())
        abandoned.rename(abandoned.with_name(forged_identity))
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError,
            "abandoned view preparation journal scope is inconsistent",
        ):
            self._project()

    def test_partial_atomic_abandonment_receipt_recovers(self) -> None:
        real_write = cognitive_views._write_exclusive
        calls = 0

        def crash_during_staging(path, content):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise cognitive_views.CognitiveViewError("crash during staging")
            return real_write(path, content)

        with (
            patch.object(
                cognitive_views,
                "_write_exclusive",
                side_effect=crash_during_staging,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash during staging",
            ),
        ):
            self._project()

        def partial_atomic_write(path, content):
            if path.name.startswith(".cognitive-view-write-"):
                path.write_bytes(b"{")
                raise cognitive_views.CognitiveViewError(
                    "crash inside atomic evidence write"
                )
            return real_write(path, content)

        with (
            patch.object(
                cognitive_views,
                "_write_exclusive",
                side_effect=partial_atomic_write,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash inside atomic evidence write",
            ),
        ):
            self._project()
        pending = list(self.view_state.rglob(".cognitive-view-write-*"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].read_bytes(), b"{")
        result = self._project()
        self.assertEqual(result.status, "projected")
        self.assertFalse(list(self.view_state.rglob(".cognitive-view-write-*")))
        abandoned = self.view_state / "abandoned"
        self.assertTrue(any(path.is_dir() for path in abandoned.iterdir()))

    def test_partial_atomic_completion_receipt_recovers(self) -> None:
        real_write = cognitive_views._write_exclusive

        def partial_atomic_write(path, content):
            if (
                path.parent.name == "receipts"
                and path.name.startswith(".cognitive-view-write-")
            ):
                path.write_bytes(b"{")
                raise cognitive_views.CognitiveViewError(
                    "crash inside completion receipt"
                )
            return real_write(path, content)

        with (
            patch.object(
                cognitive_views,
                "_write_exclusive",
                side_effect=partial_atomic_write,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash inside completion receipt",
            ),
        ):
            self._project()
        result = self._project()
        self.assertEqual(result.recovery_status, "recovered")
        self.assertFalse(list(self.view_state.rglob(".cognitive-view-write-*")))

    def test_complete_atomic_completion_receipt_reports_recovery(self) -> None:
        real_rename = cognitive_views._rename_no_replace

        def crash_after_fsync(source, destination):
            if (
                source.name.startswith(".cognitive-view-write-")
                and destination.parent.name == "receipts"
            ):
                raise cognitive_views.CognitiveViewError(
                    "crash after complete evidence fsync"
                )
            return real_rename(source, destination)

        with (
            patch.object(
                cognitive_views,
                "_rename_no_replace",
                side_effect=crash_after_fsync,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash after complete evidence fsync",
            ),
        ):
            self._project()
        pending = list(self.view_state.rglob(".cognitive-view-write-*"))
        self.assertEqual(len(pending), 1)
        json.loads(pending[0].read_bytes())
        result = self._project()
        self.assertEqual(result.status, "projected")
        self.assertEqual(result.recovery_status, "recovered")
        self.assertFalse(list(self.view_state.rglob(".cognitive-view-write-*")))

    def test_partial_atomic_conflict_receipt_recovers(self) -> None:
        self._project()
        target = (
            self.repository
            / cognitive_views.MANAGED_NAMESPACE
            / "bases"
            / "ideas.base"
        )
        target.write_bytes(b"human edit\n")
        real_write = cognitive_views._write_exclusive

        def partial_atomic_write(path, content):
            if (
                path.parent.name == "conflicts"
                and path.name.startswith(".cognitive-view-write-")
            ):
                path.write_bytes(b"{")
                raise cognitive_views.CognitiveViewError(
                    "crash inside conflict receipt"
                )
            return real_write(path, content)

        with (
            patch.object(
                cognitive_views,
                "_write_exclusive",
                side_effect=partial_atomic_write,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "crash inside conflict receipt",
            ),
        ):
            self._project()
        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertEqual(target.read_bytes(), b"human edit\n")
        self.assertFalse(list(self.view_state.rglob(".cognitive-view-write-*")))

    def test_directory_seal_and_windows_path_budget_fail_closed(self) -> None:
        real_rename = cognitive_views._rename_no_replace
        injected: Path | None = None

        def late_directory(source, destination):
            nonlocal injected
            if destination.parent.name == "transactions" and injected is None:
                destination.mkdir()
                late_writer = destination / "late-writer"
                late_writer.write_bytes(b"preserve")
                injected = late_writer
            return real_rename(source, destination)

        with (
            patch.object(
                cognitive_views,
                "_rename_no_replace",
                side_effect=late_directory,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "sealed view transaction already exists",
            ),
        ):
            self._project()
        assert injected is not None
        self.assertEqual(injected.read_bytes(), b"preserve")
        self.assertTrue(any((self.view_state / "preparations").iterdir()))

        with patch.object(cognitive_views.os, "name", "nt"):
            cognitive_views._validate_windows_protected_root(
                Path("C:\\" + ("a" * 107))
            )
            with self.assertRaisesRegex(
                cognitive_views.CognitiveViewError,
                "Windows path budget",
            ):
                cognitive_views._validate_windows_protected_root(
                    Path("C:\\" + ("a" * 108))
                )

    def test_invalid_preparation_shape_fails_before_abandonment(self) -> None:
        preparation = self.view_state / "preparations" / ("0" * 64)
        evil = preparation / "evil" / "payload"
        evil.parent.mkdir(parents=True)
        evil.write_bytes(b"unowned")
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError,
            "view preparation evidence (path|directory) is invalid",
        ):
            self._project()
        self.assertTrue(evil.is_file())
        self.assertFalse((self.view_state / "abandoned").exists())

    def test_sealed_transaction_accepts_fresh_authentic_recovery_authority(
        self,
    ) -> None:
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project(fail_after_replacements=2)
        fresh = cognitive_notes_tests._authority(
            "foundation.projection.write",
            actor_id="foundation-cognitive-view-recovery-v2",
        )
        result = cognitive_views.project_cognitive_views(
            self.repository,
            self.cognitive_state,
            self.view_state,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
            authority=fresh,
            clock=lambda: "2026-07-29T20:00:01+00:00",
        )
        self.assertEqual(result.recovery_status, "recovered")

    def test_sealed_older_source_recovers_before_current_source(self) -> None:
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project(fail_after_replacements=2)
        self.fixture._append("memory:view:newer-source", "semantic")
        self.fixture._release()
        self.fixture._project()
        result = self._project()
        self.assertEqual(result.status, "projected")
        self.assertEqual(result.recovery_status, "recovered")
        self.assertEqual(len(list((self.view_state / "receipts").glob("*.json"))), 2)
        manifest = json.loads(
            (
                self.repository / cognitive_views.MANAGED_NAMESPACE / "manifest.json"
            ).read_bytes()
        )
        self.assertEqual(manifest["source_cursor"], result.source_cursor)

    def test_tampered_staging_and_forged_prior_plan_fail_closed(self) -> None:
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project(fail_after_replacements=1)
        transaction = next((self.view_state / "transactions").iterdir())
        manifest_stage = (
            transaction / "files" / cognitive_views.sha256(b"manifest.json").hexdigest()
        )
        manifest_stage.write_bytes(manifest_stage.read_bytes() + b"\n")
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "staged view manifest"
        ):
            self._project()

    def test_unverified_reserved_sibling_is_preserved_as_conflict(self) -> None:
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project(fail_after_replacements=1)
        transaction = next((self.view_state / "transactions").iterdir())
        destination = (
            self.repository
            / cognitive_views.MANAGED_NAMESPACE
            / "bases"
            / "agent-records.base"
        )
        reserved = destination.with_name(
            f".{destination.name}.cognitive-view-prior-{transaction.name}"
        )
        reserved.write_bytes(b"HUMAN RESERVED NAME")
        before = _tree(self.repository / cognitive_views.MANAGED_NAMESPACE)
        receipts_before = set((self.view_state / "receipts").glob("*.json"))
        result = self._project()
        self.assertEqual(result.status, "conflict")
        self.assertEqual(reserved.read_bytes(), b"HUMAN RESERVED NAME")
        self.assertEqual(
            _tree(self.repository / cognitive_views.MANAGED_NAMESPACE), before
        )
        self.assertEqual(
            set((self.view_state / "receipts").glob("*.json")), receipts_before
        )

    def test_forged_pending_path_cannot_write_or_receive_receipt(self) -> None:
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project(fail_after_replacements=1)
        transaction = next((self.view_state / "transactions").iterdir())
        journal_path = transaction / "transaction.json"
        journal = json.loads(journal_path.read_bytes())
        forged = journal["operations"][1]
        old_stage = (
            transaction
            / "files"
            / cognitive_views.sha256(forged["path"].encode()).hexdigest()
        )
        forged["path"] = "evil.txt"
        new_stage = (
            transaction / "files" / cognitive_views.sha256(b"evil.txt").hexdigest()
        )
        old_stage.rename(new_stage)
        journal_path.write_bytes(cognitive_views._json_bytes(journal))
        tree_before = _tree(self.repository / cognitive_views.MANAGED_NAMESPACE)
        receipts_before = set((self.view_state / "receipts").glob("*.json"))
        with self.assertRaisesRegex(cognitive_views.CognitiveViewError, "desired plan"):
            self._project()
        self.assertFalse(
            (self.repository / cognitive_views.MANAGED_NAMESPACE / "evil.txt").exists()
        )
        self.assertEqual(
            _tree(self.repository / cognitive_views.MANAGED_NAMESPACE),
            tree_before,
        )
        self.assertEqual(
            set((self.view_state / "receipts").glob("*.json")), receipts_before
        )

    def test_source_change_before_manifest_commit_leaves_no_receipt(self) -> None:
        original = cognitive_views.read_verified_cognitive_projection
        calls = 0

        def changing_source(*args, **kwargs):
            nonlocal calls
            calls += 1
            source = original(*args, **kwargs)
            if calls >= 2:
                return replace(source, manifest_digest=f"sha256:{'0' * 64}")
            return source

        with (
            patch.object(
                cognitive_views,
                "read_verified_cognitive_projection",
                side_effect=changing_source,
            ),
            self.assertRaisesRegex(
                cognitive_views.CognitiveViewError, "source changed"
            ),
        ):
            self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        self.assertFalse((root / "manifest.json").exists())
        self.assertFalse((self.view_state / "receipts").exists())

    def test_view_receipt_source_provenance_is_bound(self) -> None:
        result = self._project()
        receipt = (
            self.view_state
            / "receipts"
            / f"{result.manifest_digest.removeprefix('sha256:')}.json"
        )
        document = json.loads(receipt.read_bytes())
        document["source_receipt_digest"] = f"sha256:{'0' * 64}"
        receipt.write_bytes(cognitive_views._json_bytes(document))
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "source receipt"
        ):
            self._project()

    def test_malformed_existing_conflict_evidence_fails_closed(self) -> None:
        self._project()
        root = self.repository / cognitive_views.MANAGED_NAMESPACE
        target = root / "bases" / "ideas.base"
        target.write_bytes(target.read_bytes() + b"# edit\n")
        first = self._project()
        conflict = self.view_state / str(first.receipt_path).split("/")[-1]
        conflict = self.view_state / "conflicts" / conflict.name
        conflict.write_bytes(b"{malformed")
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "view conflict"
        ):
            self._project()

    def test_unrelated_corrupt_protected_evidence_fails_closed(self) -> None:
        self._project()
        forged_conflict = self.view_state / "conflicts" / f"{'0' * 64}.json"
        forged_conflict.parent.mkdir(exist_ok=True)
        forged_conflict.write_bytes(b"{malformed")
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "protected view conflict"
        ):
            self._project()
        forged_conflict.unlink()
        forged_receipt = self.view_state / "receipts" / f"{'0' * 64}.json"
        forged_receipt.write_bytes(b"{malformed")
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "protected view receipt"
        ):
            self._project()

    def test_schema_valid_unreachable_receipt_fails_closed(self) -> None:
        result = self._project()
        head = (
            self.view_state
            / "receipts"
            / f"{result.manifest_digest.removeprefix('sha256:')}.json"
        )
        forged = json.loads(head.read_bytes())
        zero_digest = f"sha256:{'0' * 64}"
        forged["transaction_id"] = "0" * 64
        forged["desired_manifest_digest"] = zero_digest
        forged["verified_manifest_digest"] = zero_digest
        forged["operations"][-1]["desired_digest"] = zero_digest
        path = self.view_state / "receipts" / f"{'0' * 64}.json"
        path.write_bytes(cognitive_views._json_bytes(forged))
        self.assertTrue(
            validate_cognitive_view("cognitive-view-receipt-v1", forged).valid
        )
        with self.assertRaisesRegex(
            cognitive_views.CognitiveViewError, "not reachable"
        ):
            self._project()

    def test_corrupt_source_receipt_fails_closed(self) -> None:
        source_manifest = (
            self.repository / cognitive_views.SOURCE_NAMESPACE / "manifest.json"
        )
        digest = cognitive_views._digest_bytes(source_manifest.read_bytes())
        receipt = (
            self.cognitive_state / "receipts" / f"{digest.removeprefix('sha256:')}.json"
        )
        document = json.loads(receipt.read_bytes())
        document["verified_manifest_digest"] = f"sha256:{'0' * 64}"
        receipt.write_bytes(cognitive_views._json_bytes(document))
        with self.assertRaises(cognitive_views.CognitiveViewError):
            self._project()
        self.assertFalse(self.view_state.exists())

    def test_catalogs_package_resources_and_frozen_surfaces(self) -> None:
        self.assertTrue(validate_cognitive_view_catalog().valid)
        self.assertEqual(len(COGNITIVE_VIEW_SCHEMA_NAMES), 8)
        self.assertEqual(len(PHASE2_SCHEMA_NAMES), 17)
        self.assertEqual(len(PROJECTION_SCHEMA_NAMES), 7)
        self.assertEqual(len(PUBLIC_MEMORY_SCHEMA_NAMES), 3)
        self.assertEqual(len(COGNITIVE_SCHEMA_NAMES), 8)
        package_root = Path(hive_mind_os.__file__).parent
        resources = {
            path.name
            for path in (package_root / "foundation" / "generated").glob("*.json")
            if path.name.startswith("cognitive-view-")
        }
        self.assertEqual(
            resources,
            {f"{name}.schema.json" for name in COGNITIVE_VIEW_SCHEMA_NAMES},
        )
        inventory = cli_inventory()
        self.assertEqual(len(hive_mind_os.__all__), 131)
        self.assertEqual(len(package_system.__all__), 33)
        self.assertEqual(inventory["parser_count"], 13)
        repository = Path(__file__).parents[1]
        committed = json.loads(
            (
                repository
                / "evidence"
                / "phase3"
                / "phase3_cognitive_views_inventory.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(build_phase3_item4_inventory(repository), committed)

    def test_owned_contracts_reject_unsafe_base_and_canvas_semantics(self) -> None:
        source = cognitive_views.read_verified_cognitive_projection(
            self.repository,
            self.cognitive_state,
            tenant_id=TENANT_ID,
            repository_id=REPOSITORY_ID,
        )
        bundle = cognitive_views.compile_cognitive_views(source)
        canvas = json.loads(bundle.files["canvases/war-room.canvas"])
        canvas["nodes"][1]["id"] = canvas["nodes"][0]["id"]
        self.assertFalse(
            validate_cognitive_view("cognitive-view-canvas-v1", canvas).valid
        )
        base = cognitive_views._base_document(
            "ideas",
            source.repository_identity_digest,
            "Released idea metadata",
            (("note_id", "Generated note ID"),),
        )
        base["filters"]["and"][0] = 'file.inFolder("private")'
        self.assertFalse(validate_cognitive_view("cognitive-view-base-v1", base).valid)

    def test_cli_check_and_projection_contract(self) -> None:
        args = [
            "--repo",
            str(self.repository),
            "--cognitive-protected-state",
            str(self.cognitive_state),
            "--protected-state",
            str(self.view_state),
            "--tenant",
            TENANT_ID,
            "--repository-id",
            REPOSITORY_ID,
        ]
        with redirect_stdout(StringIO()):
            self.assertEqual(cognitive_views.run(["check", *args]), 2)
            self.assertEqual(cognitive_views.run(["project", *args]), 0)
            self.assertEqual(cognitive_views.run(["check", *args]), 0)

    def test_overlapping_protected_state_is_rejected(self) -> None:
        with self.assertRaisesRegex(cognitive_views.CognitiveViewError, "disjoint"):
            cognitive_views.project_cognitive_views(
                self.repository,
                self.cognitive_state,
                self.repository / "inside",
                tenant_id=TENANT_ID,
                repository_id=REPOSITORY_ID,
                check=True,
            )


if __name__ == "__main__":
    unittest.main()
