from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from hive_mind_os.current_state_audit import (
    CommandObservation,
    _broken_references,
    _parse_test_result,
    collect_current_state_audit,
    create_audit_artifact,
    verify_audit_artifact,
    write_audit_artifact,
)


class CurrentStateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[1]

    def valid_audit(self, **overrides) -> dict[str, object]:
        audit: dict[str, object] = {
            "schema_version": 1,
            "artifact_type": "CurrentStateAudit",
            "repository": {"head": "abc123"},
            "docket": {},
            "tests": {"status": "passed"},
            "commands": [],
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
        artifact = create_audit_artifact(self.valid_audit(schema_version=2))
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

    def test_minimal_self_digested_payload_is_not_a_verified_audit(self) -> None:
        artifact = create_audit_artifact({"schema_version": 1})
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertIn("artifact type must be CurrentStateAudit", issues)

    def test_written_artifact_is_newline_terminated(self) -> None:
        artifact = create_audit_artifact(self.valid_audit())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            write_audit_artifact(artifact, output)
            self.assertTrue(output.read_bytes().endswith(b"\n"))
            with self.assertRaises(FileExistsError):
                write_audit_artifact(artifact, output)


if __name__ == "__main__":
    unittest.main()
