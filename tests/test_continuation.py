from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hive_mind_os import cli
from hive_mind_os.continuation import (
    ContinuationPacketError,
    export_packet,
    validate_packet,
    write_packet,
)


class ContinuationPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init")
        self.git("config", "user.email", "continuation@example.invalid")
        self.git("config", "user.name", "Continuation Test")
        (self.repository / "evidence").mkdir()
        (self.repository / "evidence" / "receipt.txt").write_text(
            "verified local result\n", encoding="utf-8"
        )
        self.git("add", ".")
        self.git("commit", "-m", "fixture evidence")

    def git(self, *arguments: str) -> None:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *arguments),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def source(self, **overrides: object) -> dict[str, object]:
        source: dict[str, object] = {
            "schema_version": 1,
            "packet_id": "CP-test-001",
            "created_at": "2026-08-05T12:00:00Z",
            "objective": "Preserve the verified local change.",
            "scope": "Local repository continuation only.",
            "granted_authority": ["read_repository", "run_local_tests"],
            "forbidden_authority": [
                "network", "remote_git", "credentials", "secrets", "external_message",
                "deploy", "payment", "policy_mutation",
            ],
            "artifact_paths": ["evidence/receipt.txt"],
            "decision": "approved",
            "independent_verification": [
                {"verifier_id": "curator-local-001", "decision": "approved"}
            ],
            "blockers": [],
            "next_action": {
                "action": "Run the focused receipt test.",
                "success_condition": "The receipt remains verified.",
                "stopping_condition": "Stop if the repository state changes.",
            },
            "resume_instruction": "Validate this packet before any local action.",
        }
        source.update(overrides)
        return source

    def packet(self) -> dict[str, object]:
        return export_packet(self.source(), self.repository)

    def test_export_validate_and_cli_round_trip(self) -> None:
        packet = self.packet()
        self.assertTrue(validate_packet(packet, self.repository).valid)
        output = self.root / "continuation.json"
        self.assertEqual(write_packet(packet, output, self.repository), output)
        source_path = self.root / "source.json"
        source_path.write_text(json.dumps(self.source()), encoding="utf-8")
        cli_output = self.root / "cli-continuation.json"
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli.main(("continuation", "export", "--repository", str(self.repository), "--input", str(source_path), "--output", str(cli_output)))
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "exported")
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli.main(("continuation", "validate", "--repository", str(self.repository), "--packet", str(output)))
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "valid")

    def test_write_packet_returns_the_requested_path_when_windows_resolution_uses_an_alias(self) -> None:
        packet = self.packet()
        requested = self.root / "requested-continuation.json"
        resolved = self.root / "resolved-continuation.json"
        original_resolve = Path.resolve

        def aliasing_resolve(path: Path, *args: object, **kwargs: object) -> Path:
            if path == requested:
                return resolved
            return original_resolve(path, *args, **kwargs)

        with patch(
            "hive_mind_os.continuation.Path.resolve",
            autospec=True,
            side_effect=aliasing_resolve,
        ):
            self.assertEqual(write_packet(packet, requested, self.repository), requested)
        self.assertTrue(resolved.is_file())

    def test_packet_tampering_unknown_fields_and_unsafe_paths_are_rejected(self) -> None:
        tampered = self.packet()
        tampered["scope"] = "A different local scope."
        result = validate_packet(tampered, self.repository)
        self.assertFalse(result.valid)
        self.assertIn("packet canonical digest mismatch", result.issues)
        unknown = self.packet()
        unknown["invented_authority"] = True
        self.assertFalse(validate_packet(unknown, self.repository).valid)
        with self.assertRaisesRegex(ContinuationPacketError, "artifact path is unsafe"):
            export_packet(self.source(artifact_paths=["../outside.txt"]), self.repository)

    def test_approved_has_no_reason_but_nonapproval_reason_is_short_and_safe(self) -> None:
        approved = self.packet()
        self.assertNotIn("reason", approved)
        rejected = export_packet(
            self.source(
                decision="not-approved",
                reason="Evidence digest did not match.",
                independent_verification=[
                    {"verifier_id": "curator-local-001", "decision": "not-approved"}
                ],
            ),
            self.repository,
        )
        self.assertTrue(validate_packet(rejected, self.repository).valid)
        with self.assertRaisesRegex(ContinuationPacketError, "approval or no-decision"):
            export_packet(self.source(reason="An approval should not carry a reason."), self.repository)
        with self.assertRaisesRegex(ContinuationPacketError, "plain-English|secret-like"):
            export_packet(self.source(decision="blocked", reason="api_key=not-allowed"), self.repository)
        with self.assertRaisesRegex(ContinuationPacketError, "longer than 240"):
            export_packet(self.source(decision="blocked", reason="x" * 241), self.repository)

    def test_unclean_and_stale_worktree_are_rejected(self) -> None:
        packet = self.packet()
        (self.repository / "untracked.txt").write_text("drift\n", encoding="utf-8")
        unclean = validate_packet(packet, self.repository)
        self.assertFalse(unclean.valid)
        self.assertIn("repository worktree is not clean", unclean.issues)
        (self.repository / "untracked.txt").unlink()
        (self.repository / "after.txt").write_text("next\n", encoding="utf-8")
        self.git("add", "after.txt")
        self.git("commit", "-m", "advance head")
        stale = validate_packet(packet, self.repository)
        self.assertFalse(stale.valid)
        self.assertIn("repository HEAD is stale relative to the packet", stale.issues)

    def test_remote_authority_cannot_be_granted(self) -> None:
        with self.assertRaisesRegex(ContinuationPacketError, "packet is unsafe"):
            export_packet(self.source(granted_authority=["read_repository", "remote_git"]), self.repository)

    def test_subdirectory_cannot_bypass_output_guard_or_store_unsafe_identifiers(self) -> None:
        subdirectory = self.repository / "component"
        subdirectory.mkdir()
        packet = export_packet(self.source(), subdirectory)
        self.assertEqual(packet["repository"]["path"], self.repository.resolve().as_posix())
        with self.assertRaisesRegex(ContinuationPacketError, "outside"):
            write_packet(packet, self.repository / "packet.json", subdirectory)
        with self.assertRaisesRegex(ContinuationPacketError, "safe identifier"):
            export_packet(self.source(packet_id="CP-id\napi_key=retained"), self.repository)
        with self.assertRaisesRegex(ContinuationPacketError, "safe identifier"):
            export_packet(
                self.source(independent_verification=[
                    {"verifier_id": "curator-001\napi_key=retained", "decision": "approved"}
                ]),
                self.repository,
            )

    def test_nonfinite_packet_is_rejected_without_cli_crash(self) -> None:
        packet = self.packet()
        packet["objective"] = float("nan")
        self.assertFalse(validate_packet(packet, self.repository).valid)
        packet_path = self.root / "nonfinite.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli.main(("continuation", "validate", "--repository", str(self.repository), "--packet", str(packet_path)))
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "rejected")

    def test_output_cannot_dirty_the_bound_repository(self) -> None:
        with self.assertRaisesRegex(ContinuationPacketError, "outside"):
            write_packet(self.packet(), self.repository / "packet.json", self.repository)


if __name__ == "__main__":
    unittest.main()
