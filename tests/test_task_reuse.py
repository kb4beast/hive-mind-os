from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.task_reuse import (
    ReuseDisposition,
    TaskFingerprint,
    TaskReceipt,
    TaskRecordState,
    TaskReuseError,
    TaskReuseIndex,
    classify_reuse,
)
from hive_mind_os.wave_manifest import CandidateIdentity


def digest(character: str) -> str:
    return "sha256:" + character * 64


SUBJECT = digest("1")
CANDIDATE = CandidateIdentity("a" * 40, "b" * 40, SUBJECT)
TARGET = CandidateIdentity("c" * 40, "d" * 40, SUBJECT)


def fingerprint(**overrides) -> TaskFingerprint:
    values = {
        "plan_digest": digest("2"),
        "node_id": "node-1",
        "subject_id": SUBJECT,
        "subject_snapshot_digest": digest("3"),
        "relevant_surface_digest": digest("4"),
        "direct_dependency_receipt_digests": (digest("5"), digest("6")),
        "authority_digest": digest("7"),
        "compiler_digest": digest("8"),
        "policy_digest": digest("9"),
        "environment_digest": digest("a"),
        "task_contract_digest": digest("b"),
    }
    values.update(overrides)
    return TaskFingerprint(**values)


def receipt(
    state: TaskRecordState,
    *,
    receipt_id: str = "receipt-1",
    fp: TaskFingerprint | None = None,
    candidate: CandidateIdentity | None = None,
    sequence: int = 1,
    previous: str | None = None,
) -> TaskReceipt:
    return TaskReceipt(
        receipt_id=receipt_id,
        fingerprint=fp or fingerprint(),
        state=state,
        sequence=sequence,
        candidate=(
            candidate
            if candidate is not None
            else CANDIDATE
            if state in {
                TaskRecordState.CANDIDATE_SEALED,
                TaskRecordState.VERIFIED,
                TaskRecordState.INTEGRATED,
            }
            else None
        ),
        validation_receipt_digest=(
            digest("c")
            if state in {TaskRecordState.VERIFIED, TaskRecordState.INTEGRATED}
            else None
        ),
        integrated_target=TARGET if state is TaskRecordState.INTEGRATED else None,
        blocker_digest=(
            digest("d")
            if state in {TaskRecordState.BLOCKED, TaskRecordState.FAILED}
            else None
        ),
        previous_receipt_digest=previous,
    )


class TaskReuseTests(unittest.TestCase):
    def test_boolean_reuse_schema_versions_are_rejected(self) -> None:
        fingerprint_document = fingerprint().to_document()
        fingerprint_document["schema_version"] = True
        with self.assertRaisesRegex(TaskReuseError, "unknown shape"):
            TaskFingerprint.from_document(fingerprint_document)

        receipt_document = receipt(TaskRecordState.ACTIVE).to_document()
        receipt_document["schema_version"] = True
        with self.assertRaisesRegex(TaskReuseError, "unknown shape"):
            TaskReceipt.from_document(receipt_document)

    def test_only_validated_integrated_exact_receipt_completes_task(self) -> None:
        fp = fingerprint()
        decision = classify_reuse(fp, [receipt(TaskRecordState.INTEGRATED)])
        self.assertEqual(decision.disposition, ReuseDisposition.EXACT_REUSE)
        self.assertTrue(decision.complete)
        sealed = classify_reuse(fp, [receipt(TaskRecordState.CANDIDATE_SEALED)])
        self.assertEqual(sealed.disposition, ReuseDisposition.VERIFY_EXISTING)
        self.assertFalse(sealed.complete)

    def test_active_checkpoint_failed_and_empty_have_distinct_dispositions(self) -> None:
        fp = fingerprint()
        self.assertEqual(
            classify_reuse(fp, [receipt(TaskRecordState.ACTIVE)]).disposition,
            ReuseDisposition.RESUME_ACTIVE,
        )
        self.assertEqual(
            classify_reuse(fp, [receipt(TaskRecordState.CHECKPOINTED)]).disposition,
            ReuseDisposition.REPAIR_EXISTING,
        )
        self.assertEqual(
            classify_reuse(fp, [receipt(TaskRecordState.FAILED)]).disposition,
            ReuseDisposition.REPAIR_EXISTING,
        )
        self.assertEqual(
            classify_reuse(fp, []).disposition,
            ReuseDisposition.EXECUTE_NEW,
        )
        self.assertEqual(
            classify_reuse(fp, [receipt(TaskRecordState.BLOCKED)]).disposition,
            ReuseDisposition.BLOCKED,
        )

    def test_every_fingerprint_input_invalidates_reuse(self) -> None:
        original = fingerprint()
        changes = {
            "subject_snapshot_digest": digest("e"),
            "relevant_surface_digest": digest("f"),
            "direct_dependency_receipt_digests": (digest("5"), digest("0")),
            "authority_digest": digest("e"),
            "compiler_digest": digest("f"),
            "policy_digest": digest("e"),
            "environment_digest": digest("f"),
            "task_contract_digest": digest("e"),
            "subject_id": digest("f"),
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                current = replace(original, **{field: value})
                decision = classify_reuse(
                    current,
                    [receipt(TaskRecordState.INTEGRATED, fp=original)],
                )
                self.assertEqual(decision.disposition, ReuseDisposition.STALE)

    def test_competing_attempts_and_candidates_conflict(self) -> None:
        fp = fingerprint()
        active = [
            receipt(TaskRecordState.ACTIVE, receipt_id="one"),
            receipt(TaskRecordState.ACTIVE, receipt_id="two"),
        ]
        self.assertEqual(
            classify_reuse(fp, active).disposition,
            ReuseDisposition.CONFLICT,
        )
        other = CandidateIdentity("e" * 40, "f" * 40, SUBJECT)
        integrated = [
            receipt(TaskRecordState.INTEGRATED, receipt_id="one"),
            receipt(
                TaskRecordState.INTEGRATED,
                receipt_id="two",
                candidate=other,
            ),
        ]
        self.assertEqual(
            classify_reuse(fp, integrated).disposition,
            ReuseDisposition.CONFLICT,
        )

    def test_append_only_index_survives_restart_and_rejects_key_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reuse.sqlite3"
            index = TaskReuseIndex(path)
            record = receipt(TaskRecordState.INTEGRATED)
            index.append(record, idempotency_key="publish-1")
            self.assertEqual(index.append(record, idempotency_key="publish-1"), record)
            index.close()
            resumed = TaskReuseIndex(path)
            self.assertEqual(
                resumed.decide(fingerprint()).disposition,
                ReuseDisposition.EXACT_REUSE,
            )
            with self.assertRaises(TaskReuseError):
                resumed.append(
                    receipt(TaskRecordState.ACTIVE, receipt_id="other"),
                    idempotency_key="publish-1",
                )
            resumed.close()

    def test_receipt_chain_must_extend_exact_prior_digest(self) -> None:
        index = TaskReuseIndex()
        self.addCleanup(index.close)
        first = receipt(TaskRecordState.ACTIVE)
        index.append(first, idempotency_key="one")
        bad = receipt(
            TaskRecordState.CHECKPOINTED,
            sequence=2,
            previous=digest("0"),
        )
        with self.assertRaisesRegex(TaskReuseError, "exact prior"):
            index.append(bad, idempotency_key="two")


if __name__ == "__main__":
    unittest.main()
