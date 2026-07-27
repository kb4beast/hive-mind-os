from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.receipts import FileReceiptValidator, ReceiptReference, sha256_digest


class FileReceiptValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.artifact = self.root / "artifact.txt"
        self.artifact.write_text("observed state", encoding="utf-8")
        self.validator = FileReceiptValidator(self.root)
        self.bindings = {
            "mission_id": "mission-1",
            "state_ref": "MISSION_STATE:mission-1:2",
            "actor_id": "builder-pass-1",
            "action_id": "ACT-1",
            "action_kind": "git",
            "action_digest": f"sha256:{'a' * 64}",
        }

    def tearDown(self) -> None:
        self.directory.cleanup()

    def document(self, **overrides) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": 1,
            "receipt_id": "REC-1",
            "provider": "test-enforcement-point",
            "execution_id": "EXEC-1",
            **self.bindings,
            "policy_decision_ref": "POLICY-1",
            "lease_id": "LEASE-1",
            "executed": True,
            "result": "succeeded",
            "observed_at": "2026-07-27T12:00:00Z",
            "verified_by": "curator-pass-1",
            "artifacts": [
                {
                    "path": self.artifact.name,
                    "digest": sha256_digest(self.artifact.read_bytes()),
                }
            ],
        }
        document.update(overrides)
        return document

    def reference(self, document: object, name: str = "receipt.json") -> ReceiptReference:
        path = self.root / name
        path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        return ReceiptReference(path.name, sha256_digest(path.read_bytes()))

    def validate(self, reference: ReceiptReference):
        return self.validator.validate(reference, **self.bindings)

    def test_correctly_bound_success_receipt_passes(self) -> None:
        validation = self.validate(self.reference(self.document()))
        self.assertTrue(validation.valid, validation.issues)
        self.assertTrue(validation.succeeded)
        self.assertEqual(validation.receipt_id, "REC-1")

    def test_failed_result_is_valid_evidence_but_not_success(self) -> None:
        validation = self.validate(self.reference(self.document(result="failed")))
        self.assertTrue(validation.valid, validation.issues)
        self.assertFalse(validation.succeeded)

    def test_mutated_receipt_fails_digest_validation(self) -> None:
        reference = self.reference(self.document())
        (self.root / reference.path).write_text("{}", encoding="utf-8")
        validation = self.validate(reference)
        self.assertFalse(validation.valid)
        self.assertIn("receipt digest mismatch", validation.issues)

    def test_missing_directory_and_escape_paths_fail_closed(self) -> None:
        missing = ReceiptReference("missing.json", f"sha256:{'0' * 64}")
        self.assertFalse(self.validate(missing).valid)

    def test_symlink_escape_fails_closed_when_supported(self) -> None:
        outside_directory = tempfile.TemporaryDirectory()
        self.addCleanup(outside_directory.cleanup)
        outside = Path(outside_directory.name) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = self.root / "link.json"
        try:
            os.symlink(outside, link)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        reference = ReceiptReference(link.name, sha256_digest(outside.read_bytes()))
        validation = self.validate(reference)
        self.assertFalse(validation.valid)
        self.assertIn("receipt path escapes the trusted root", validation.issues)

    def test_malformed_json_and_unknown_schema_fail(self) -> None:
        malformed_path = self.root / "malformed.json"
        malformed_path.write_text("{", encoding="utf-8")
        malformed = ReceiptReference(
            malformed_path.name,
            sha256_digest(malformed_path.read_bytes()),
        )
        self.assertFalse(self.validate(malformed).valid)
        validation = self.validate(self.reference(self.document(schema_version=2)))
        self.assertFalse(validation.valid)
        self.assertIn("unsupported receipt schema version", validation.issues)
        for invalid_version in (True, 1.0):
            with self.subTest(schema_version=invalid_version):
                validation = self.validate(
                    self.reference(
                        self.document(schema_version=invalid_version),
                        f"schema-{invalid_version}.json",
                    )
                )
                self.assertFalse(validation.valid)

    def test_foreign_or_incomplete_binding_fails(self) -> None:
        mutations = {
            "mission_id": "other-mission",
            "state_ref": "MISSION_STATE:other:1",
            "actor_id": "other-actor",
            "action_id": "ACT-2",
            "action_kind": "deploy",
            "action_digest": f"sha256:{'b' * 64}",
            "executed": False,
            "result": "pending",
            "policy_decision_ref": "",
            "lease_id": "",
            "verified_by": "builder-pass-1",
            "observed_at": "2026-07-27T12:00:00",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                validation = self.validate(
                    self.reference(self.document(**{field: value}), f"{field}.json")
                )
                self.assertFalse(validation.valid)

        invalid_offset = self.validate(
            self.reference(
                self.document(observed_at="2026-07-27T12:00:00+00:00:30"),
                "invalid-offset.json",
            )
        )
        self.assertFalse(invalid_offset.valid)
        self.assertIn("receipt observed_at must be RFC 3339", invalid_offset.issues)

    def test_artifact_substitution_fails(self) -> None:
        reference = self.reference(self.document())
        self.artifact.write_text("substituted", encoding="utf-8")
        validation = self.validate(reference)
        self.assertFalse(validation.valid)
        self.assertIn("artifact 0 digest mismatch", validation.issues)

    def test_receipt_reference_rejects_blank_path_and_malformed_digest(self) -> None:
        with self.assertRaises(ValueError):
            ReceiptReference(" ", f"sha256:{'0' * 64}")
        with self.assertRaises(ValueError):
            ReceiptReference("receipt.json", "abc123")
        for path in (
            "/absolute/receipt.json",
            r"C:\receipts\receipt.json",
            r"nested\receipt.json",
            "nested/../receipt.json",
            "nested//receipt.json",
            "carrier.txt:receipt.json",
            "CON",
            "con.txt",
            "file?.json",
            "trailing.",
            "trailing ",
            "nul\u0000byte.json",
        ):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    ReceiptReference(path, f"sha256:{'0' * 64}")


if __name__ == "__main__":
    unittest.main()
