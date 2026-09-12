from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.evaluation_admission import (
    EvaluationAdmissionError,
    load_evaluation_record,
    recheck_resolved_evidence,
    resolve_keep_evidence,
)
from hive_mind_os.brain_kernel.evaluation_runtime import (
    ChallengerDescriptor,
    EvaluationContract,
    EvaluationError,
    EvaluationIdentities,
    EvaluationRecordReference,
    EvaluationRuntime,
    EvaluationVerdict,
    GuardrailSpec,
    PromptEvaluationSubject,
    SealedHoldout,
    SurfaceKind,
    SurfaceResult,
)


class EvaluationAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifact = self.root / "measurements.log"
        self.artifact.write_bytes(b"retained surface measurements\n")
        self.ref = str(self.artifact) + "#sha256:" + sha256(self.artifact.read_bytes()).hexdigest()
        self.descriptor = ChallengerDescriptor("candidate-1", "opaque-parent-label", "refs/proposal", "proposal:opaque")
        self.identities = EvaluationIdentities("proposer", "builder", "evaluator")
        self.contract = EvaluationContract(minimum_effect=0.25)
        self.subject = PromptEvaluationSubject(
            self.descriptor, "candidate-1", "builder", "experiment-1",
            "sha256:" + sha256(b"candidate prompt").hexdigest(), None,
            "proposer", "builder", (self.ref,), self.contract.fingerprint,
        )
        self.surfaces = tuple(
            SurfaceResult(kind, kind.value, (0.5,) * 3,
                          ((0.8,) * 3 if kind is SurfaceKind.HELD_OUT else (0.55,) * 3),
                          (self.ref,))
            for kind in SurfaceKind
        )

    def _evaluate(self, *, subject=True, surfaces=None, unsealed=False, contract=None):
        selected_contract = contract or self.contract
        selected_subject = replace(self.subject, contract_fingerprint=selected_contract.fingerprint)
        holdout = SealedHoldout("holdout", {"case": {"expected": "receipt"}})
        if not unsealed:
            holdout.seal_prediction("evaluator", {"prediction": "sealed"})
        return EvaluationRuntime(selected_contract).evaluate(
            self.descriptor, self.identities, self.surfaces if surfaces is None else surfaces,
            holdout, evidence_root=self.root / "evidence",
            promotion_subject=selected_subject if subject else None,
        )

    def _resolve(self, record=None, subject=None):
        return resolve_keep_evidence(
            subject or self.subject, (record or self._evaluate()).reference(), evaluator_id="evaluator"
        )

    def _rewrite(self, reference, mutate, *, update_id=True):
        document = json.loads(Path(reference.record_path).read_bytes())
        mutate(document)
        if update_id:
            preimage = {key: value for key, value in document.items() if key != "evaluation_id"}
            document["evaluation_id"] = "EVAL-" + canonical_digest(preimage)[7:23]
        path = self.root / "evidence" / (document["evaluation_id"] + "-modified.json")
        path.write_bytes(canonical_bytes(document) + b"\n")
        return EvaluationRecordReference(document["evaluation_id"], str(path), canonical_digest(document))

    def _assert_code(self, expected, function, *args, **kwargs):
        with self.assertRaises(EvaluationAdmissionError) as raised:
            function(*args, **kwargs)
        self.assertEqual(expected, raised.exception.code)

    def test_explicit_subject_reference_round_trip_and_read_only_keep(self):
        self.assertNotEqual(self.subject.artifact_digest, self.descriptor.proposal_digest)
        self.assertIsNone(self.subject.parent_champion_digest)
        self.assertEqual(self.subject, PromptEvaluationSubject.from_document(self.subject.document()))
        record = self._evaluate()
        self.assertEqual(record.reference(), EvaluationRecordReference.from_document(record.reference().document()))
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        resolved = self._resolve(record)
        self.assertEqual(EvaluationVerdict.KEEP, resolved.record.verdict)
        self.assertEqual(4, resolved.record.schema_version)
        self.assertEqual(self.subject, resolved.subject)
        self.assertEqual(self.contract, resolved.contract)
        self.assertEqual(3, len(resolved.snapshots))  # shared surface file only once
        self.assertNotEqual(resolved.record.record_digest, resolved.snapshots[0].raw_digest)
        recheck_resolved_evidence(resolved)
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        with self.assertRaises(FrozenInstanceError):
            resolved.record.descriptor.challenger_id = "mutated"
        detached = resolved.record.document()
        detached["identities"]["evaluator_id"] = "mutated"
        self.assertEqual("evaluator", resolved.record.identities.evaluator_id)

    def test_subject_field_changes_are_versioned_or_rejected(self):
        baseline = self.subject.subject_digest
        alternate_ref = self.ref + "x"
        mutations = {
            "role": "curator", "experiment_id": "experiment-2",
            "artifact_digest": "sha256:" + "a" * 64,
            "parent_champion_digest": "sha256:" + "b" * 64,
            "proposer_id": "proposer-2", "builder_id": "builder-2",
            "evidence_refs": (alternate_ref,), "contract_fingerprint": "sha256:" + "c" * 64,
            "descriptor": replace(self.descriptor, proposal_digest="another opaque proposal"),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                self.assertNotEqual(baseline, replace(self.subject, **{field: value}).subject_digest)
        with self.assertRaises(EvaluationError):
            replace(self.subject, candidate_id="unrelated")
        two = replace(self.subject, evidence_refs=(self.ref, alternate_ref))
        self.assertNotEqual(two.subject_digest, replace(two, evidence_refs=two.evidence_refs[::-1]).subject_digest)
        for mutation in ({"evidence_refs": (self.ref, self.ref)}, {"artifact_digest": "sha256:bad"},
                         {"parent_champion_digest": self.subject.artifact_digest}):
            with self.assertRaises(EvaluationError):
                replace(self.subject, **mutation)
        for kind in ("subject", "reference"):
            value = self.subject if kind == "subject" else self._evaluate().reference()
            document = value.document()
            document["schema_version"] = True
            with self.assertRaises(EvaluationError):
                type(value).from_document(document)

    def test_producer_rejects_unbound_subject_before_persisting(self):
        holdout = SealedHoldout("holdout", {"case": 1})
        holdout.seal_prediction("evaluator", {})
        with self.assertRaises(EvaluationError):
            EvaluationRuntime(self.contract).evaluate(
                self.descriptor, self.identities, self.surfaces, holdout,
                evidence_root=self.root / "never-written",
                promotion_subject=replace(self.subject, proposer_id="different"),
            )
        self.assertFalse((self.root / "never-written").exists())

    def test_legacy_readability_and_unbound_receipt_bytes_unchanged(self):
        legacy = self._evaluate(subject=False)
        original = legacy.record_path.read_bytes()
        self.assertEqual(original, self._evaluate(subject=False).record_path.read_bytes())
        self.assertEqual(2, load_evaluation_record(legacy.reference()).schema_version)
        v1 = self._rewrite(legacy.reference(), lambda doc: (
            doc.update(schema_version=1), doc["holdout"].pop("evaluator_id")))
        self.assertEqual(1, load_evaluation_record(v1).schema_version)
        v3 = self._evaluate(subject=False, contract=EvaluationContract(primary_held_out_name="held-out"))
        self.assertEqual(3, load_evaluation_record(v3.reference()).schema_version)
        shutil.rmtree(self.root / "evidence" / "contracts")
        for reference in (v1, legacy.reference(), v3.reference()):
            load_evaluation_record(reference)  # no current-contract read for inspection
            self._assert_code("evaluation-schema-not-admissible", resolve_keep_evidence,
                              self.subject, reference, evaluator_id="evaluator")
        self.assertEqual(original, legacy.record_path.read_bytes())

    def test_all_verdicts_and_unsealed_quarantine_are_readable(self):
        cases = (
            (self.surfaces, False, EvaluationVerdict.KEEP),
            (self.surfaces[:-1], False, EvaluationVerdict.RETEST),
            (tuple(replace(s, candidate_samples=(0.0,) * 3) if s.kind is SurfaceKind.ADVERSARIAL else s
                   for s in self.surfaces), False, EvaluationVerdict.DISCARD),
            (tuple(replace(s, artifact_refs=()) for s in self.surfaces), True, EvaluationVerdict.QUARANTINE),
        )
        for surfaces, unsealed, verdict in cases:
            with self.subTest(verdict=verdict):
                record = self._evaluate(surfaces=surfaces, unsealed=unsealed)
                parsed = load_evaluation_record(record.reference())
                self.assertEqual(verdict, parsed.verdict)
                if unsealed:
                    self.assertIsNone(parsed.holdout.prediction_digest)
                    self.assertIsNone(parsed.holdout.evaluator_id)
                    self.assertIsNone(parsed.holdout.seal_sequence)
                if verdict is not EvaluationVerdict.KEEP:
                    self._assert_code("evaluation-not-keep", self._resolve, record)

    def test_rehashed_semantic_forgeries_do_not_bypass_recomputation(self):
        original = self._evaluate().reference()
        cases = (
            ("thin", "evaluation-insufficient", lambda doc: doc["surfaces"][0].update(baseline_samples=[0.5])),
            ("missing-kind", "evaluation-insufficient", lambda doc: doc["surfaces"].pop()),
            ("guardrail", "evaluation-not-keep", lambda doc: doc["surfaces"][0].update(candidate_samples=[0.0] * 3)),
            ("duplicate", "evaluation-not-keep", lambda doc: doc["surfaces"].insert(0, doc["surfaces"][0].copy())),
            ("derived-score", "evaluation-derived-fields-mismatch", lambda doc: doc.update(primary_effect=0.99)),
            ("reason", "evaluation-derived-fields-mismatch", lambda doc: doc.update(reasons=["fabricated success"])),
            ("descriptor", "subject-mismatch", lambda doc: doc["descriptor"].update(change_ref="other proposal")),
            ("identity", "identity-mismatch", lambda doc: doc["identities"].update(evaluator_id="other evaluator")),
            ("false-order", "evaluation-not-keep", lambda doc: doc["holdout"]["ordering"].update(valid=False)),
            ("backward-reveal", "evaluation-not-keep", lambda doc: doc["holdout"]["ordering"].update(reveal_sequence=1)),
        )
        for name, code, mutate in cases:
            with self.subTest(case=name):
                reference = self._rewrite(original, mutate)
                self._assert_code(code, resolve_keep_evidence, self.subject, reference, evaluator_id="evaluator")

    def test_false_keep_at_exact_threshold_and_ambiguous_primary(self):
        threshold = tuple(replace(s, candidate_samples=(0.75,) * 3) if s.kind is SurfaceKind.HELD_OUT else s
                          for s in self.surfaces)
        record = self._evaluate(surfaces=threshold)
        self.assertEqual(EvaluationVerdict.RETEST, record.verdict)
        reference = self._rewrite(record.reference(), lambda doc: doc.update(verdict="keep"))
        self._assert_code("evaluation-not-keep", resolve_keep_evidence, self.subject, reference, evaluator_id="evaluator")
        extra = replace(self.surfaces[0], name="second-held-out")
        ambiguous = self._evaluate(surfaces=(*self.surfaces, extra))
        forged = self._rewrite(ambiguous.reference(), lambda doc: doc.update(verdict="keep"))
        with patch("hive_mind_os.brain_kernel.evaluation_runtime.fmean", side_effect=AssertionError("scored quarantine")):
            self._assert_code("evaluation-not-keep", resolve_keep_evidence, self.subject, forged, evaluator_id="evaluator")

    def test_exact_json_types_ids_and_raw_canonicality(self):
        original = self._evaluate().reference()
        cases = (
            lambda doc: doc.update(schema_version=True),
            lambda doc: doc.update(primary_scored=1),
            lambda doc: doc.update(primary_effect=True),
            lambda doc: doc["holdout"]["ordering"].update(seal_sequence=True),
            lambda doc: doc["surfaces"][0].update(candidate_samples=[True] * 3),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                reference = self._rewrite(original, mutate)
                self._assert_code("evaluation-malformed", load_evaluation_record, reference)
        unsupported = self._rewrite(original, lambda doc: doc.update(schema_version=99))
        self._assert_code("evaluation-schema-unsupported", load_evaluation_record, unsupported)
        stale_id = self._rewrite(original, lambda doc: doc.update(primary_effect=0.9), update_id=False)
        self._assert_code("evaluation-id-mismatch", load_evaluation_record, stale_id)
        self._assert_code("evaluation-digest-mismatch", load_evaluation_record,
                          replace(original, record_digest="sha256:" + "f" * 64))
        path = Path(original.record_path)
        original_bytes = path.read_bytes()
        for malformed in (original_bytes + b"\n", b'{"schema_version":4,"schema_version":4}\n', b'{"a":NaN}\n'):
            path.write_bytes(malformed)
            self._assert_code("evaluation-malformed", load_evaluation_record, original)
        path.write_bytes(original_bytes)

    def test_custom_guardrail_contract_and_mutated_contract_rejected(self):
        custom = EvaluationContract(
            minimum_repetitions=2, minimum_effect=0.1,
            guardrails=(GuardrailSpec(SurfaceKind.COMPARATOR, 0.3),),
            primary_held_out_name="held-out",
        )
        subject = replace(self.subject, contract_fingerprint=custom.fingerprint)
        record = self._evaluate(contract=custom)
        self.assertEqual(custom, self._resolve(record, subject).contract)
        path = record.record_path.parent / "contracts" / (custom.fingerprint[7:] + ".json")
        document = custom.document()
        document["noise_multiplier"] = True
        path.write_bytes(canonical_bytes(document) + b"\n")
        self._assert_code("contract-malformed", self._resolve, record, subject)
        document = custom.document()
        document["minimum_effect"] = 0.2
        path.write_bytes(canonical_bytes(document) + b"\n")
        self._assert_code("contract-mismatch", self._resolve, record, subject)

    def test_recheck_detects_mutation_of_each_located_resource(self):
        for resource, code in (("evaluation", "evaluation-digest-mismatch"),
                               ("contract", "contract-mismatch"), ("artifact", "artifact-mismatch")):
            with self.subTest(resource=resource):
                resolved = self._resolve()
                snapshot = next(item for item in resolved.snapshots if item.resource == resource)
                path = Path(snapshot.path)
                path.write_bytes(snapshot.raw_bytes + b"changed")
                self._assert_code(code, recheck_resolved_evidence, resolved)
                path.write_bytes(snapshot.raw_bytes)

    def test_relocation_preserves_content_digest_not_reference_path(self):
        record = self._evaluate()
        relocated = self.root / "relocated"
        shutil.copytree(record.record_path.parent, relocated)
        reference = replace(record.reference(), record_path=str(relocated / record.record_path.name))
        moved = resolve_keep_evidence(self.subject, reference, evaluator_id="evaluator")
        self.assertEqual(record.record_digest, moved.record.record_digest)
        self.assertNotEqual(record.reference().record_path, moved.reference.record_path)

    def test_relative_surface_refs_are_readable_but_not_resolvable(self):
        original = self._evaluate().reference()
        relative = "measurements.log#" + self.ref.rpartition("#")[2]
        subject = replace(self.subject, evidence_refs=(relative,))
        def mutate(document):
            document["promotion_subject"] = subject.document()
            document["promotion_subject_digest"] = subject.subject_digest
            for surface in document["surfaces"]:
                surface["artifact_refs"] = [relative]
        reference = self._rewrite(original, mutate)
        self.assertEqual(relative, load_evaluation_record(reference).surfaces[0].artifact_refs[0])
        self._assert_code("path-unsupported", resolve_keep_evidence, subject, reference, evaluator_id="evaluator")

    def test_unresolved_surface_file_remains_inspectable(self):
        record = self._evaluate()
        original = self.artifact.read_bytes()
        self.artifact.unlink()
        self.assertEqual(EvaluationVerdict.KEEP, load_evaluation_record(record.reference()).verdict)
        self._assert_code("artifact-unreadable", self._resolve, record)
        self.artifact.write_bytes(original + b"tampered")
        self._assert_code("artifact-mismatch", self._resolve, record)

    def test_module_import_orders_in_fresh_processes(self):
        for first, second in (
            ("hive_mind_os.prompt_registry", "hive_mind_os.brain_kernel.evaluation_admission"),
            ("hive_mind_os.brain_kernel.evaluation_admission", "hive_mind_os.prompt_registry"),
        ):
            with self.subTest(first=first):
                result = subprocess.run(
                    [sys.executable, "-c", f"import {first}; import {second}"],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
