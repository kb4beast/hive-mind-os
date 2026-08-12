from __future__ import annotations

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from statistics import pstdev

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.evaluation_runtime import (
    ChallengerDescriptor,
    EvaluationContract,
    EvaluationError,
    EvaluationIdentities,
    EvaluationRuntime,
    EvaluationVerdict,
    GuardrailSpec,
    HoldoutSeal,
    HoldoutViolation,
    SealedHoldout,
    SurfaceKind,
    SurfaceResult,
)

HOLDOUT_CASES = {
    "case-beta": {"expected": "restore-evidence", "weight": 2},
    "case-alpha": {"expected": "repair-regression", "weight": 1},
}


def _make_artifact(root: Path, name: str, content: str = "surface log\n") -> str:
    """Write a small file and return a valid ``path#sha256:<digest>`` reference."""

    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    digest = sha256(path.read_bytes()).hexdigest()
    return f"{path.as_posix()}#sha256:{digest}"


class _EvaluationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.evidence_root = self.root / "evidence"
        self.runtime = EvaluationRuntime()
        self.descriptor = ChallengerDescriptor(
            "challenger:prompt-v7",
            "champion:prompt-v6",
            "refs/heads/autopilot/challenger-v7",
            canonical_digest({"proposal": "prompt-v7"}),
        )
        self.identities = EvaluationIdentities(
            "optimizer:proposer",
            "builder:isolated",
            "curator:independent-evaluator",
        )
        self.holdout = SealedHoldout("holdout:round-5", HOLDOUT_CASES)
        self.seal = self.holdout.seal_prediction(
            self.identities.evaluator_id,
            {"expected_keep": False},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _surface(
        self,
        kind: SurfaceKind,
        baseline: tuple[float, ...],
        candidate: tuple[float, ...],
        *,
        refs: tuple[str, ...] | None = None,
        name: str | None = None,
    ) -> SurfaceResult:
        label = name if name is not None else f"{kind.value}-surface"
        if refs is None:
            refs = (
                _make_artifact(
                    self.artifacts,
                    f"{kind.value}.log",
                    f"surface={kind.value}\n",
                ),
            )
        return SurfaceResult(kind, label, baseline, candidate, refs)

    def _surfaces(
        self,
        *,
        held_out: tuple[tuple[float, ...], tuple[float, ...]] = (
            (0.50, 0.52, 0.48),
            (0.80, 0.82, 0.78),
        ),
        adversarial: tuple[tuple[float, ...], tuple[float, ...]] = (
            (0.90, 0.90, 0.90),
            (0.90, 0.90, 0.90),
        ),
        comparator: tuple[tuple[float, ...], tuple[float, ...]] = (
            (0.70, 0.70, 0.70),
            (0.72, 0.72, 0.72),
        ),
        pit: tuple[tuple[float, ...], tuple[float, ...]] | None = (
            (0.60, 0.60, 0.60),
            (0.65, 0.65, 0.65),
        ),
    ) -> list[SurfaceResult]:
        surfaces = [
            self._surface(SurfaceKind.HELD_OUT, *held_out),
            self._surface(SurfaceKind.ADVERSARIAL, *adversarial),
            self._surface(SurfaceKind.COMPARATOR, *comparator),
        ]
        if pit is not None:
            surfaces.append(self._surface(SurfaceKind.PIT, *pit))
        return surfaces

    def _evaluate(self, surfaces, *, holdout=None, runtime=None):
        return (runtime or self.runtime).evaluate(
            self.descriptor,
            self.identities,
            surfaces,
            holdout or self.holdout,
            evidence_root=self.evidence_root,
        )


class HeldOutEvaluationTests(_EvaluationCase):
    def test_keep_when_effect_beats_noise_floor(self) -> None:
        record = self._evaluate(self._surfaces())
        self.assertEqual(EvaluationVerdict.KEEP, record.verdict)
        self.assertAlmostEqual(0.30, record.primary_effect, places=12)
        self.assertGreater(record.primary_effect, record.required_effect)
        self.assertEqual(
            max(pstdev((0.50, 0.52, 0.48)), pstdev((0.80, 0.82, 0.78))),
            record.noise_floor,
        )
        self.assertTrue(record.record_path.is_file())
        self.assertEqual(
            "keep",
            json.loads(record.record_path.read_text(encoding="utf-8"))["verdict"],
        )

    def test_discard_when_candidate_materially_underperforms(self) -> None:
        record = self._evaluate(
            self._surfaces(held_out=((0.80, 0.82, 0.78), (0.50, 0.52, 0.48)))
        )
        self.assertEqual(EvaluationVerdict.DISCARD, record.verdict)
        self.assertLess(record.primary_effect, -record.required_effect)
        self.assertIn("materially underperformed", " ".join(record.reasons))
        self.assertTrue(record.record_path.is_file())

    def test_retest_when_a_surface_kind_is_missing(self) -> None:
        record = self._evaluate(self._surfaces(pit=None))
        self.assertEqual(EvaluationVerdict.RETEST, record.verdict)
        self.assertIn("missing surfaces: pit", record.reasons)
        self.assertIsNone(record.primary_effect)

    def test_evaluator_must_differ_from_proposer_and_builder(self) -> None:
        with self.assertRaises(EvaluationError):
            EvaluationIdentities("agent:a", "builder:b", "agent:a")
        with self.assertRaises(EvaluationError):
            EvaluationIdentities("agent:a", "builder:b", "builder:b")
        with self.assertRaises(EvaluationError):
            EvaluationIdentities("agent:a", "agent:a", "curator:c")
        with self.assertRaises(EvaluationError):
            EvaluationIdentities("", "builder:b", "curator:c")
        with self.assertRaises(EvaluationError):
            EvaluationIdentities("agent:a ", "builder:b", "curator:c")
        independent = EvaluationIdentities("agent:a", "builder:b", "curator:c")
        self.assertEqual("curator:c", independent.evaluator_id)
        with self.assertRaises(EvaluationError):
            ChallengerDescriptor("same:id", "same:id", "refs/heads/x", "sha256:abc")

    def test_record_is_retained_append_only(self) -> None:
        surfaces = self._surfaces()
        first = self._evaluate(surfaces)
        second = self._evaluate(surfaces)
        self.assertEqual(first.evaluation_id, second.evaluation_id)
        self.assertEqual(first.record_digest, second.record_digest)
        self.assertEqual(first.record_path, second.record_path)
        document = json.loads(first.record_path.read_text(encoding="utf-8"))
        self.assertEqual(canonical_digest(document), first.record_digest)
        first.record_path.write_bytes(b'{"verdict":"keep"}\n')
        with self.assertRaises(EvaluationError):
            self._evaluate(surfaces)


class PITLeakageTests(_EvaluationCase):
    def test_reveal_before_seal_raises_and_quarantines(self) -> None:
        unsealed = SealedHoldout("holdout:unsealed", HOLDOUT_CASES)
        with self.assertRaises(HoldoutViolation):
            unsealed.reveal()
        forged = HoldoutSeal(
            "holdout:unsealed",
            self.identities.evaluator_id,
            canonical_digest({"expected_keep": True}),
            1,
        )
        with self.assertRaises(HoldoutViolation):
            unsealed.reveal(forged)
        self.assertEqual(("reveal_without_seal", "reveal_without_seal"), unsealed.violations)
        self.assertFalse(unsealed.ordering["valid"])
        record = self._evaluate(self._surfaces(), holdout=unsealed)
        self.assertEqual(EvaluationVerdict.QUARANTINE, record.verdict)
        self.assertIn("holdout boundary violated", " ".join(record.reasons))

    def test_foreign_seal_digest_is_rejected(self) -> None:
        other = SealedHoldout("holdout:other-round", HOLDOUT_CASES)
        foreign = other.seal_prediction(
            self.identities.evaluator_id, {"expected_keep": True}
        )
        with self.assertRaises(HoldoutViolation):
            self.holdout.reveal(foreign)
        self.assertEqual(("prediction_digest_mismatch",), self.holdout.violations)
        self.assertFalse(self.holdout.ordering["valid"])
        tampered = HoldoutSeal(
            self.seal.holdout_id,
            self.seal.evaluator_id,
            canonical_digest({"expected_keep": True}),
            self.seal.sequence,
        )
        with self.assertRaises(HoldoutViolation):
            self.holdout.reveal(tampered)
        record = self._evaluate(self._surfaces())
        self.assertEqual(EvaluationVerdict.QUARANTINE, record.verdict)
        self.assertIn("prediction_digest_mismatch", " ".join(record.reasons))

    def test_second_seal_is_refused(self) -> None:
        with self.assertRaises(HoldoutViolation):
            self.holdout.seal_prediction(
                self.identities.evaluator_id, {"expected_keep": True}
            )
        self.assertEqual((), self.holdout.violations)
        self.assertEqual(self.seal.sequence, self.holdout.ordering["seal_sequence"])
        self.assertEqual(HOLDOUT_CASES, self.holdout.reveal(self.seal))
        self.assertTrue(self.holdout.ordering["valid"])

    def test_case_payloads_are_invisible_until_reveal(self) -> None:
        sealed = SealedHoldout("holdout:hidden", HOLDOUT_CASES)
        self.assertEqual(("case-alpha", "case-beta"), sealed.case_ids)
        self.assertEqual(
            {"case_ids", "ordering", "reveal", "seal_prediction", "violations"},
            {name for name in dir(sealed) if not name.startswith("_")},
        )
        self.assertFalse(hasattr(sealed, "__dict__"))
        with self.assertRaises(HoldoutViolation):
            sealed.reveal()
        self.assertEqual(("reveal_without_seal",), sealed.violations)
        own = sealed.seal_prediction(
            self.identities.evaluator_id, {"expected_keep": False}
        )
        twin = SealedHoldout("holdout:hidden", HOLDOUT_CASES)
        foreign = twin.seal_prediction(
            self.identities.evaluator_id, {"expected_keep": True}
        )
        with self.assertRaises(HoldoutViolation):
            sealed.reveal(foreign)
        revealed = sealed.reveal(own)
        self.assertEqual(HOLDOUT_CASES, revealed)
        self.assertGreater(sealed.ordering["reveal_sequence"], own.sequence)


class NoiseFloorTests(_EvaluationCase):
    def test_retest_when_improvement_is_within_noise(self) -> None:
        baseline = (0.20, 0.80, 0.50)
        candidate = (0.25, 0.85, 0.55)
        record = self._evaluate(self._surfaces(held_out=(baseline, candidate)))
        self.assertEqual(EvaluationVerdict.RETEST, record.verdict)
        self.assertEqual(max(pstdev(baseline), pstdev(candidate)), record.noise_floor)
        self.assertEqual(2.0 * record.noise_floor, record.required_effect)
        self.assertGreater(record.required_effect, 0.0)
        self.assertLess(abs(record.primary_effect), record.required_effect)
        self.assertIn("noise floor", " ".join(record.reasons))

    def test_minimum_effect_dominates_when_noise_is_zero(self) -> None:
        runtime = EvaluationRuntime(EvaluationContract(minimum_effect=0.25))
        within = self._evaluate(
            self._surfaces(held_out=((0.50, 0.50, 0.50), (0.60, 0.60, 0.60))),
            runtime=runtime,
        )
        self.assertEqual(0.0, within.noise_floor)
        self.assertEqual(0.25, within.required_effect)
        self.assertEqual(EvaluationVerdict.RETEST, within.verdict)
        beyond = self._evaluate(
            self._surfaces(held_out=((0.50, 0.50, 0.50), (0.90, 0.90, 0.90))),
            runtime=runtime,
        )
        self.assertEqual(0.25, beyond.required_effect)
        self.assertEqual(EvaluationVerdict.KEEP, beyond.verdict)

    def test_hard_guardrail_regression_discards_and_retains_losing_evidence(self) -> None:
        record = self._evaluate(
            self._surfaces(adversarial=((0.90, 0.90, 0.90), (0.70, 0.70, 0.70)))
        )
        self.assertEqual(EvaluationVerdict.DISCARD, record.verdict)
        self.assertIn("hard guardrail regressed: adversarial-surface", record.reasons)
        document = json.loads(record.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record.reasons, tuple(document["reasons"]))
        retained = {entry["name"]: entry for entry in document["surfaces"]}
        self.assertEqual([0.90, 0.90, 0.90], retained["adversarial-surface"]["baseline_samples"])
        self.assertEqual([0.70, 0.70, 0.70], retained["adversarial-surface"]["candidate_samples"])
        self.assertEqual([0.80, 0.82, 0.78], retained["held-out-surface"]["candidate_samples"])
        self.assertEqual(canonical_digest(document), record.record_digest)
        tolerant = EvaluationRuntime(
            EvaluationContract(
                guardrails=(
                    GuardrailSpec(SurfaceKind.ADVERSARIAL, 0.25),
                    GuardrailSpec(SurfaceKind.COMPARATOR),
                )
            )
        )
        allowed = self._evaluate(
            self._surfaces(adversarial=((0.90, 0.90, 0.90), (0.70, 0.70, 0.70))),
            runtime=tolerant,
        )
        self.assertEqual(EvaluationVerdict.KEEP, allowed.verdict)

    def test_insufficient_repetitions_retest(self) -> None:
        record = self._evaluate(
            self._surfaces(held_out=((0.50, 0.52), (0.80, 0.82)))
        )
        self.assertEqual(EvaluationVerdict.RETEST, record.verdict)
        self.assertIn(
            "insufficient repeated measurements: held-out-surface", record.reasons
        )
        self.assertIsNone(record.primary_effect)
        relaxed = EvaluationRuntime(EvaluationContract(minimum_repetitions=2))
        self.assertEqual(
            EvaluationVerdict.KEEP,
            self._evaluate(
                self._surfaces(held_out=((0.50, 0.52), (0.80, 0.82))), runtime=relaxed
            ).verdict,
        )
        with self.assertRaises(EvaluationError):
            EvaluationContract(minimum_repetitions=1)
        with self.assertRaises(EvaluationError):
            SurfaceResult(
                SurfaceKind.HELD_OUT,
                "non-finite",
                (0.5, float("nan")),
                (0.6, 0.6),
                (),
            )
        with self.assertRaises(EvaluationError):
            SurfaceResult(SurfaceKind.HELD_OUT, "empty", (), (0.6,), ())


class MissingArtifactQuarantineTests(_EvaluationCase):
    def test_missing_artifact_file_quarantines_not_retests(self) -> None:
        surfaces = self._surfaces(
            held_out=((0.50, 0.52), (0.80, 0.82)),
            pit=None,
        )
        reference = surfaces[0].artifact_refs[0]
        Path(reference.rpartition("#")[0]).unlink()
        record = self._evaluate(surfaces)
        self.assertEqual(EvaluationVerdict.QUARANTINE, record.verdict)
        self.assertNotEqual(EvaluationVerdict.RETEST, record.verdict)
        self.assertIn("missing or mutated artifact", " ".join(record.reasons))
        self.assertIn("artifact does not resolve", " ".join(record.reasons))
        self.assertNotIn("missing surfaces", " ".join(record.reasons))
        self.assertIsNone(record.primary_effect)

    def test_digest_mismatch_quarantines(self) -> None:
        surfaces = self._surfaces()
        reference = surfaces[1].artifact_refs[0]
        Path(reference.rpartition("#")[0]).write_text("tampered\n", encoding="utf-8")
        record = self._evaluate(surfaces)
        self.assertEqual(EvaluationVerdict.QUARANTINE, record.verdict)
        self.assertIn("artifact digest mismatch", " ".join(record.reasons))

    def test_empty_artifact_refs_quarantine(self) -> None:
        surfaces = self._surfaces()
        surfaces[0] = SurfaceResult(
            SurfaceKind.HELD_OUT,
            "held-out-surface",
            (0.50, 0.52, 0.48),
            (0.80, 0.82, 0.78),
            (),
        )
        record = self._evaluate(surfaces)
        self.assertEqual(EvaluationVerdict.QUARANTINE, record.verdict)
        self.assertIn(
            "surface has no retained artifacts: held-out-surface", record.reasons
        )
        duplicated = self._surfaces()
        duplicated.append(
            self._surface(
                SurfaceKind.COMPARATOR,
                (0.70, 0.70, 0.70),
                (0.72, 0.72, 0.72),
            )
        )
        duplicate_record = self._evaluate(duplicated)
        self.assertEqual(EvaluationVerdict.QUARANTINE, duplicate_record.verdict)
        self.assertIn(
            "duplicate surface: comparator-surface", duplicate_record.reasons
        )

    def test_quarantine_record_is_still_retained(self) -> None:
        surfaces = self._surfaces()
        Path(surfaces[0].artifact_refs[0].rpartition("#")[0]).unlink()
        record = self._evaluate(surfaces)
        self.assertEqual(EvaluationVerdict.QUARANTINE, record.verdict)
        self.assertTrue(record.record_path.is_file())
        document = json.loads(record.record_path.read_text(encoding="utf-8"))
        self.assertEqual("quarantine", document["verdict"])
        self.assertEqual(record.reasons, tuple(document["reasons"]))
        self.assertEqual(record.evaluation_id, document["evaluation_id"])
        self.assertEqual(canonical_digest(document), record.record_digest)
        self.assertEqual(4, len(document["surfaces"]))
        self.assertIsNone(document["primary_effect"])
        self.assertEqual(
            self.identities.evaluator_id, document["identities"]["evaluator_id"]
        )


if __name__ == "__main__":
    unittest.main()
