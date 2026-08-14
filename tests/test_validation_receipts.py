from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.validation_receipts import (
    CandidateApplicability,
    CandidateStatus,
    DiscoveryRecord,
    ReceiptStore,
    RecoveryCase,
    RecoveryState,
    TerminalKind,
    TerminalOutcome,
    ValidationReceiptCapture,
)


COMMIT = "a" * 40
TREE = "b" * 40
CONTRACT = "sha256:" + "c" * 64


class ValidationReceiptCaptureTests(unittest.TestCase):
    """Independent executable contract for native validation receipt capture."""

    def capture(self) -> ValidationReceiptCapture:
        return ValidationReceiptCapture(
            session_id="018f8d4a-0000-7000-8000-000000000001",
            label_vocabulary={
                "pass": TerminalKind.PASS,
                "class-skip": TerminalKind.SKIP_CLASS,
                "policy-blocked": TerminalKind.NOT_RUN_POLICY_BLOCKED,
            },
            source_commit=COMMIT,
            source_tree=TREE,
            runner_contract_digest=CONTRACT,
        )

    @staticmethod
    def records() -> tuple[DiscoveryRecord, ...]:
        return (
            DiscoveryRecord(0, "tests.alpha.test_one", "selected"),
            DiscoveryRecord(1, "tests.beta.test_two", "selected"),
            DiscoveryRecord(2, "tests.gamma.test_three", "excluded_by_declared_selector"),
        )

    def test_seals_complete_ordered_vector_and_requires_one_terminal_outcome_per_id(self) -> None:
        capture = self.capture()
        capture.seal_discovery(self.records())
        capture.record_outcome(
            TerminalOutcome(0, "tests.alpha.test_one", TerminalKind.PASS, "pass", 0)
        )
        capture.record_outcome(
            TerminalOutcome(1, "tests.beta.test_two", TerminalKind.PASS, "pass", 1)
        )
        capture.record_outcome(
            TerminalOutcome(
                2,
                "tests.gamma.test_three",
                TerminalKind.NOT_RUN_POLICY_BLOCKED,
                "policy-blocked",
                2,
                reason_code="declared-selector",
            )
        )

        receipt = capture.finalize()

        self.assertEqual(receipt.discovery_vector, self.records())
        self.assertEqual([item.discovery_id for item in receipt.terminal_ledger], [0, 1, 2])
        self.assertTrue(receipt.discovery_vector_digest.startswith("sha256:"))
        self.assertTrue(receipt.verify())

        duplicate = self.capture()
        duplicate.seal_discovery(self.records())
        duplicate.record_outcome(
            TerminalOutcome(0, "tests.alpha.test_one", TerminalKind.PASS, "pass", 0)
        )
        with self.assertRaises(ValueError):
            duplicate.record_outcome(
                TerminalOutcome(0, "tests.alpha.test_one", TerminalKind.PASS, "pass", 1)
            )

        missing = self.capture()
        missing.seal_discovery(self.records())
        with self.assertRaises(ValueError):
            missing.finalize()

    def test_class_skip_expands_to_each_affected_discovery_id(self) -> None:
        capture = self.capture()
        capture.seal_discovery(self.records()[:2])
        capture.record_class_skip(
            discovery_ids=(0, 1),
            terminal_label="class-skip",
            event_ordinal=0,
            reason_code="missing-required-api",
        )

        receipt = capture.finalize()

        self.assertEqual(
            [(item.discovery_id, item.terminal_kind) for item in receipt.terminal_ledger],
            [(0, TerminalKind.SKIP_CLASS), (1, TerminalKind.SKIP_CLASS)],
        )
        self.assertTrue(all(item.reason_code == "missing-required-api" for item in receipt.terminal_ledger))

    def test_unknown_label_or_foreign_or_out_of_order_outcome_is_rejected(self) -> None:
        capture = self.capture()
        capture.seal_discovery(self.records()[:2])

        with self.assertRaises(ValueError):
            capture.record_outcome(
                TerminalOutcome(0, "tests.alpha.test_one", TerminalKind.PASS, "invented", 0)
            )
        with self.assertRaises(ValueError):
            capture.record_outcome(
                TerminalOutcome(99, "tests.not.discovered", TerminalKind.PASS, "pass", 0)
            )

        capture.record_outcome(
            TerminalOutcome(0, "tests.alpha.test_one", TerminalKind.PASS, "pass", 2)
        )
        with self.assertRaises(ValueError):
            capture.record_outcome(
                TerminalOutcome(1, "tests.beta.test_two", TerminalKind.PASS, "pass", 1)
            )

    def test_redacts_diagnostics_before_any_receipt_document_is_retained(self) -> None:
        secret = "private-api-token-should-never-persist"
        capture = self.capture()
        capture.seal_discovery(self.records()[:1])
        capture.record_diagnostic(f"runner response included {secret}")
        capture.record_outcome(
            TerminalOutcome(0, "tests.alpha.test_one", TerminalKind.PASS, "pass", 0)
        )

        document = capture.finalize().to_document()
        serialized = json.dumps(document, sort_keys=True)

        self.assertNotIn(secret, serialized)
        self.assertIn("<REDACTED:SECRET>", serialized)
        self.assertGreater(document["privacy"]["redaction_count"], 0)


class ReceiptStoreTests(unittest.TestCase):
    def test_only_a_complete_atomically_committed_receipt_verifies(self) -> None:
        capture = ValidationReceiptCapture(
            session_id="018f8d4a-0000-7000-8000-000000000002",
            label_vocabulary={"pass": TerminalKind.PASS},
            source_commit=COMMIT,
            source_tree=TREE,
            runner_contract_digest=CONTRACT,
        )
        capture.seal_discovery((DiscoveryRecord(0, "tests.atomic.test_receipt", "selected"),))
        capture.record_outcome(
            TerminalOutcome(0, "tests.atomic.test_receipt", TerminalKind.PASS, "pass", 0)
        )
        receipt = capture.finalize()

        with tempfile.TemporaryDirectory() as temporary:
            store = ReceiptStore(Path(temporary))
            reference = store.commit(receipt)
            self.assertTrue(store.verify(reference))
            self.assertTrue((Path(temporary) / reference.path).is_dir())

            receipt_file = Path(temporary) / reference.path / "receipt.json"
            receipt_file.write_text("{}", encoding="utf-8")
            self.assertFalse(store.verify(reference))


class RecoveryCaseTests(unittest.TestCase):
    def test_recovery_is_bounded_append_only_and_escalates_repeated_blockers(self) -> None:
        recovery = RecoveryCase(
            case_id="RECOVERY-001",
            predecessor_receipt_digest="sha256:" + "d" * 64,
            max_automatic_attempts=2,
            max_diagnosis_rounds_per_signature=1,
            max_remediation_rounds_per_signature=1,
        )
        self.assertEqual(recovery.state, RecoveryState.BLOCKED)

        recovery.diagnose("parser:unknown-label")
        recovery.remediate("parser:unknown-label", remediation_id="redaction-policy-v2")
        successor = recovery.revalidate(new_session_id="018f8d4a-0000-7000-8000-000000000003")

        self.assertEqual(recovery.state, RecoveryState.REVALIDATE)
        self.assertEqual(successor.predecessor_receipt_digest, recovery.predecessor_receipt_digest)
        self.assertNotEqual(successor.session_id, recovery.session_id)
        self.assertEqual(recovery.history[0].state, RecoveryState.BLOCKED)

        recovery.block("parser:unknown-label")
        self.assertEqual(recovery.state, RecoveryState.ESCALATED)
        self.assertEqual(recovery.escalation_reason, "repeated-blocker-signature")
        with self.assertRaises(ValueError):
            recovery.diagnose("parser:unknown-label")


class CandidateApplicabilityTests(unittest.TestCase):
    def test_candidate_requires_exact_binding_and_rejected_status_can_never_apply(self) -> None:
        candidate = CandidateApplicability(
            candidate_id="fixture-v2",
            candidate_commit="e" * 40,
            candidate_tree="f" * 40,
            parent_commit=COMMIT,
            component_kind="fixture",
            changed_path_manifest_digest="sha256:" + "1" * 64,
            source_target_commit=COMMIT,
            source_target_tree=TREE,
            required_composition="standalone",
            authority_status="authorized",
            status=CandidateStatus.ELIGIBLE,
            required_validation_contract_digest=CONTRACT,
            rollback_reference="rollback:fixture-v2",
        )

        self.assertTrue(candidate.applies_to(
            candidate_commit="e" * 40,
            candidate_tree="f" * 40,
            target_commit=COMMIT,
            target_tree=TREE,
            composition="standalone",
            validation_contract_digest=CONTRACT,
        ))
        self.assertFalse(candidate.applies_to(
            candidate_commit="e" * 40,
            candidate_tree="0" * 40,
            target_commit=COMMIT,
            target_tree=TREE,
            composition="standalone",
            validation_contract_digest=CONTRACT,
        ))

        rejected = CandidateApplicability(
            candidate_id="historical-rejected-fixture",
            candidate_commit="e" * 40,
            candidate_tree="f" * 40,
            parent_commit=COMMIT,
            component_kind="fixture",
            changed_path_manifest_digest="sha256:" + "1" * 64,
            source_target_commit=COMMIT,
            source_target_tree=TREE,
            required_composition="standalone",
            authority_status="authorized",
            status=CandidateStatus.REJECTED,
            required_validation_contract_digest=CONTRACT,
            rollback_reference="rollback:fixture-v2",
        )
        self.assertFalse(rejected.applies_to(
            candidate_commit="e" * 40,
            candidate_tree="f" * 40,
            target_commit=COMMIT,
            target_tree=TREE,
            composition="standalone",
            validation_contract_digest=CONTRACT,
        ))


if __name__ == "__main__":
    unittest.main()
