from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hive_mind_os.current_state_audit import (
    COMMAND_TIMEOUT_SECONDS,
    CommandObservation,
    _broken_references,
    _parse_test_result,
    collect_current_state_audit,
    create_audit_artifact,
    execute_command,
    verify_audit_artifact,
    write_audit_artifact,
)


class CurrentStateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[1]

    def valid_audit(self, **overrides) -> dict[str, object]:
        head = "a" * 40
        audit: dict[str, object] = {
            "schema_version": 2,
            "artifact_type": "CurrentStateAudit",
            "repository": {
                "root": str(self.repository),
                "head": head,
                "working_tree_clean": True,
                "working_tree_entries": [],
                "post_test_head": head,
                "post_test_working_tree_clean": True,
                "post_test_working_tree_entries": [],
                "tracked_tree_digest": f"sha256:{'b' * 64}",
            },
            "docket": {
                "source_count": 1,
                "claim_count": 1,
                "broken_references": [],
                "receipts_valid": True,
                "reference_receipts": [
                    {
                        "claim_id": "CLM-1",
                        "kind": "test",
                        "reference": "tests/test_example.py",
                        "path_valid": True,
                        "digest": f"sha256:{'c' * 64}",
                        "execution": {"status": "passed"},
                        "valid": True,
                        "issues": [],
                    }
                ],
            },
            "tests": {"status": "passed", "passed": 1, "failed": 0, "errors": 0},
            "commands": [
                {
                    "command": ["python", "-m", "pytest", "-q"],
                    "cwd": str(self.repository),
                    "return_code": 0,
                    "stdout": "1 passed",
                    "stderr": "",
                    "timed_out": False,
                    "output_truncated": False,
                }
            ],
            "failures": [],
            "complete": True,
        }
        audit.update(overrides)
        return audit

    def test_collects_repository_docket_without_broken_receipts_or_running_tests(self) -> None:
        audit = collect_current_state_audit(
            self.repository,
            run_tests=False,
            generated_at=datetime(2026, 7, 27, tzinfo=UTC),
            invocation=("hive-mind", "audit", "--skip-tests"),
        )

        self.assertEqual(audit["artifact_type"], "CurrentStateAudit")
        self.assertGreaterEqual(audit["repository"]["full_ref_commit_count"], 79)
        self.assertEqual(audit["docket"]["source_count"], 22)
        self.assertEqual(audit["docket"]["claim_count"], 80)
        self.assertTrue(audit["docket"]["inventory_complete"])
        self.assertFalse(audit["docket"]["release_ready"])
        self.assertEqual(
            audit["docket"]["source_blockers"],
            ["SRC-005", "SRC-006", "SRC-016", "SRC-017", "SRC-018", "SRC-019", "SRC-020"],
        )
        self.assertEqual(audit["docket"]["broken_references"], [])
        self.assertFalse(audit["docket"]["receipts_valid"])
        policy_receipts = [
            item
            for item in audit["docket"]["reference_receipts"]
            if item["reference"] == "tests/test_policy_invariants.py"
        ]
        self.assertTrue(policy_receipts)
        self.assertTrue(all(item["path_valid"] and item["digest"] for item in policy_receipts))
        self.assertTrue(
            all(item["execution"]["status"] == "not_run" for item in policy_receipts)
        )
        self.assertEqual(audit["tests"]["status"], "not_run")
        self.assertFalse(audit["complete"])

    def test_broken_reference_detector_rejects_missing_and_escaping_paths(self) -> None:
        claim = SimpleNamespace(
            id="CLM-TEST",
            architecture_refs=(),
            code_refs=("missing.py", "../outside.py"),
            test_refs=(),
            benchmark_refs=(),
        )
        docket = SimpleNamespace(claims=(claim,))
        broken = _broken_references(docket, self.repository)
        reasons = {item["reason"] for item in broken}
        self.assertIn("referenced file does not exist", reasons)
        self.assertIn("referenced path escapes the repository", reasons)

    def test_free_form_success_text_is_not_a_test_receipt(self) -> None:
        command = ("python", "-c", "print('999 passed')")
        observation = CommandObservation(
            command=command,
            cwd=str(self.repository),
            return_code=0,
            stdout="999 passed\n",
            stderr="",
        )
        result = _parse_test_result(observation)
        self.assertEqual(result["status"], "unverified")

    def test_test_time_worktree_mutation_is_reported(self) -> None:
        status_calls = 0

        def executor(command, cwd):
            nonlocal status_calls
            command_tuple = tuple(command)
            if command_tuple[:4] == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
                status_calls += 1
                return CommandObservation(
                    command_tuple,
                    str(cwd),
                    0,
                    "" if status_calls == 1 else " M README.md\0",
                    "",
                )
            if len(command_tuple) >= 4 and command_tuple[1:4] == ("-m", "pytest", "-q"):
                return CommandObservation(command_tuple, str(cwd), 0, "1 passed\n", "")
            return execute_command(command_tuple, cwd)

        audit = collect_current_state_audit(
            self.repository,
            run_tests=True,
            generated_at=datetime(2026, 7, 27, tzinfo=UTC),
            executor=executor,
        )
        self.assertFalse(audit["complete"])
        self.assertFalse(audit["repository"]["post_test_working_tree_clean"])
        self.assertIn(
            "worktree_changed_during_audit",
            {failure.get("kind") for failure in audit["failures"]},
        )

    def test_command_timeout_is_a_visible_failed_observation(self) -> None:
        timeout = subprocess.TimeoutExpired(("test",), COMMAND_TIMEOUT_SECONDS)
        with patch("hive_mind_os.current_state_audit.subprocess.run", side_effect=timeout):
            observation = execute_command(("test",), self.repository)
        self.assertFalse(observation.succeeded)
        self.assertTrue(observation.timed_out)
        self.assertEqual(observation.return_code, 124)
        self.assertIn("timed out", observation.stderr)

    def test_digest_detects_mutation(self) -> None:
        artifact = create_audit_artifact(self.valid_audit(value="original"))
        valid, issues = verify_audit_artifact(artifact)
        self.assertTrue(valid, issues)

        mutated = copy.deepcopy(artifact)
        mutated["audit"]["value"] = "substituted"
        valid, issues = verify_audit_artifact(mutated)
        self.assertFalse(valid)
        self.assertIn("audit digest mismatch", issues)

    def test_optional_signature_requires_matching_key(self) -> None:
        artifact = create_audit_artifact(
            self.valid_audit(),
            signing_key=b"test-only-key",
            signing_key_id="test-key-1",
        )
        valid, issues = verify_audit_artifact(artifact, signing_key=b"test-only-key")
        self.assertTrue(valid, issues)

        valid, issues = verify_audit_artifact(artifact, signing_key=b"wrong-key")
        self.assertFalse(valid)
        self.assertIn("audit signature mismatch", issues)

    def test_unknown_schema_is_not_verified(self) -> None:
        artifact = create_audit_artifact(self.valid_audit(schema_version=3))
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

    def test_minimal_self_digested_payload_is_not_a_verified_audit(self) -> None:
        artifact = create_audit_artifact({"schema_version": 2})
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertIn("artifact type must be CurrentStateAudit", issues)

        underspecified = {
            "schema_version": 2,
            "artifact_type": "CurrentStateAudit",
            "repository": {},
            "docket": {},
            "tests": {},
            "commands": [],
            "failures": [],
            "complete": True,
        }
        valid, issues = verify_audit_artifact(create_audit_artifact(underspecified))
        self.assertFalse(valid)
        self.assertIn("audit repository head is invalid", issues)
        self.assertIn("audit contains no command observations", issues)
        self.assertIn("complete audit requires passing tests", issues)

    def test_boolean_schema_and_contradictory_complete_audit_are_rejected(self) -> None:
        boolean_schema = create_audit_artifact(self.valid_audit(schema_version=True))
        valid, issues = verify_audit_artifact(boolean_schema)
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

        contradictory = self.valid_audit()
        contradictory["repository"]["working_tree_clean"] = False
        contradictory["repository"]["working_tree_entries"] = [" M file.py"]
        contradictory["tests"]["status"] = "failed"
        contradictory["docket"]["receipts_valid"] = False
        contradictory["failures"] = [{"kind": "test_failure"}]
        valid, issues = verify_audit_artifact(create_audit_artifact(contradictory))
        self.assertFalse(valid)
        self.assertIn("complete audit requires a clean repository", issues)
        self.assertIn("complete audit requires passing tests", issues)
        self.assertIn("complete audit requires valid reference receipts", issues)
        self.assertIn("complete audit cannot contain failures", issues)

    def test_written_artifact_is_newline_terminated(self) -> None:
        artifact = create_audit_artifact(self.valid_audit())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            write_audit_artifact(artifact, output)
            self.assertTrue(output.read_bytes().endswith(b"\n"))
            with self.assertRaises(FileExistsError):
                write_audit_artifact(artifact, output)

    def test_interrupted_atomic_publish_leaves_destination_retryable(self) -> None:
        artifact = create_audit_artifact(self.valid_audit())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            with patch(
                "hive_mind_os.current_state_audit.os.link",
                side_effect=OSError("simulated publish interruption"),
            ):
                with self.assertRaises(OSError):
                    write_audit_artifact(artifact, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
            write_audit_artifact(artifact, output)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
