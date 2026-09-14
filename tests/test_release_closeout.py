import tempfile
import unittest
from pathlib import Path

from hive_mind_os.release_closeout import (
    CloseoutBuilder,
    load_release_manifest,
    write_release_manifest,
)
from hive_mind_os.whole_os_qualification import (
    LIFECYCLE_STAGE_IDS,
    NODE_IDS,
    REQUIREMENT_IDS,
    SPECIALIST_ROLE_IDS,
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    OperationalReceipt,
    QualificationError,
)

CANDIDATE = "sha256:" + "a" * 64
PREVIOUS = "sha256:" + "b" * 64


def evidence(subject_id: str, *, kind: EvidenceKind = EvidenceKind.ATTESTED_REAL):
    return EvidenceRef(
        f"ledger:{subject_id}",
        "sha256:" + "c" * 64,
        kind,
        subject_id,
        100,
    )


def operation(name: str) -> OperationalReceipt:
    return OperationalReceipt(
        ("hive-mind", name),
        CANDIDATE,
        0,
        evidence(CANDIDATE, kind=EvidenceKind.EXTERNAL_RECEIPT),
    )


def complete_builder() -> CloseoutBuilder:
    builder = CloseoutBuilder(
        release_id="release-1",
        candidate_digest=CANDIDATE,
        previous_release_digest=PREVIOUS,
        builder_id="builder-1",
    )
    for requirement_id in REQUIREMENT_IDS:
        builder.record_requirement(
            requirement_id, Disposition.ADOPT, (evidence(requirement_id),)
        )
    for node_id in NODE_IDS:
        builder.disposition_node(node_id, Disposition.ADOPT, (evidence(node_id),))
    for role_id in SPECIALIST_ROLE_IDS:
        builder.record_role(role_id, (evidence(role_id),))
    for stage_id in LIFECYCLE_STAGE_IDS:
        builder.record_lifecycle_stage(stage_id, (evidence(stage_id),))
    return builder


class ReleaseCloseoutTests(unittest.TestCase):
    def test_positive_requirement_cannot_be_recorded_without_evidence(self):
        builder = CloseoutBuilder(
            release_id="release-1",
            candidate_digest=CANDIDATE,
            previous_release_digest=PREVIOUS,
            builder_id="builder-1",
        )
        with self.assertRaisesRegex(QualificationError, "requires evidence"):
            builder.record_requirement("R01", Disposition.ADOPT)

    def test_blocked_assessment_requires_matching_explicit_obligation(self):
        builder = complete_builder()
        obligation = ExternalObligation(
            "runtime-access",
            Disposition.BLOCKED_CAPABILITY,
            "A real engine runtime has not been supplied.",
            ("R14",),
        )
        builder.add_obligation(obligation)
        builder.requirements.pop("R14")
        builder.record_requirement(
            "R14",
            Disposition.BLOCKED_CAPABILITY,
            obligation_ids=("runtime-access",),
            rationale="Runtime evidence is unavailable.",
        )
        manifest = builder.seal(
            startup_receipt=operation("start"),
            rollback_receipt=operation("rollback"),
            independent_judge_id="judge-1",
            final_disposition=Disposition.ADAPT,
            final_rationale="Scoped release with a declared unsupported environment.",
            sealed_at=101,
        )
        self.assertEqual(
            manifest.requirement_assessments["R14"].obligation_ids,
            ("runtime-access",),
        )

    def test_closeout_rejects_self_judgment_and_missing_pilot_completion(self):
        builder = complete_builder()
        with self.assertRaisesRegex(ValueError, "independent judge"):
            builder.seal(
                startup_receipt=operation("start"),
                rollback_receipt=operation("rollback"),
                independent_judge_id="builder-1",
                final_disposition=Disposition.ADOPT,
                final_rationale="All scoped evidence passed.",
                sealed_at=101,
            )

        builder.nodes.pop("N32")
        builder.disposition_node(
            "N32", Disposition.DEFER, rationale="The outcome window is incomplete."
        )
        with self.assertRaisesRegex(QualificationError, "pilot closeout"):
            builder.seal(
                startup_receipt=operation("start"),
                rollback_receipt=operation("rollback"),
                independent_judge_id="judge-1",
                final_disposition=Disposition.ADOPT,
                final_rationale="This must not be accepted.",
                sealed_at=101,
            )

    def test_operational_receipt_rejects_synthetic_or_failed_execution(self):
        with self.assertRaisesRegex(QualificationError, "attested real"):
            OperationalReceipt(
                ("false",),
                CANDIDATE,
                0,
                evidence(CANDIDATE, kind=EvidenceKind.SYNTHETIC),
            )
        with self.assertRaisesRegex(QualificationError, "successful exit"):
            OperationalReceipt(
                ("hive-mind", "start"),
                CANDIDATE,
                1,
                evidence(CANDIDATE),
            )

    def test_manifest_round_trip_is_digest_bound_and_immutable(self):
        manifest = complete_builder().seal(
            startup_receipt=operation("start"),
            rollback_receipt=operation("rollback"),
            independent_judge_id="judge-1",
            final_disposition=Disposition.ADOPT,
            final_rationale="All scoped evidence passed.",
            sealed_at=101,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release-1.json"
            digest = write_release_manifest(path, manifest)
            loaded, loaded_digest = load_release_manifest(path)
            self.assertEqual(loaded, manifest)
            self.assertEqual(loaded_digest, digest)
            self.assertEqual(write_release_manifest(path, manifest), digest)

            changed = path.read_text(encoding="utf-8").replace(
                "All scoped evidence passed.", "Changed after sealing."
            )
            path.write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable"):
                write_release_manifest(path, manifest)


if __name__ == "__main__":
    unittest.main()
