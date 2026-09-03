from __future__ import annotations

import json
import unittest
from dataclasses import replace

from hive_mind_os.portable_plan import (
    BudgetAllocation,
    NonRepositorySubject,
    PortableNode,
    PortablePlanBundle,
    RepositorySubject,
    StandardBinding,
    SubjectBinding,
    SubjectKind,
)
from hive_mind_os.runtime_contracts import (
    EFFECT_CLASSES_V1,
    AdapterRequirement,
    AuthorityEnvelope,
    BudgetPolicy,
    CapabilityRequirement,
    ContractViolation,
    EvidenceReference,
    IntegrationPolicy,
    RecoveryPolicy,
    ResourceRequirement,
    TokenPolicy,
    canonical_digest,
    requires_external_authority,
)

DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
COMMIT = "a" * 40
TREE = "b" * 40
TIME = "2030-01-01T00:00:00Z"


def make_plan(*, repository: bool = True) -> PortablePlanBundle:
    if repository:
        subject = SubjectBinding.for_repository(
            RepositorySubject(DIGEST, COMMIT, TREE, "candidate/main")
        )
    else:
        subject = SubjectBinding.for_non_repository(
            NonRepositorySubject("document", DIGEST, OTHER_DIGEST)
        )
    return PortablePlanBundle(
        1,
        "portable-plan",
        DIGEST,
        OTHER_DIGEST,
        subject,
        StandardBinding(
            2,
            "docs/execution/DAG_AUTHORING_STANDARD_V2.md",
            DIGEST,
            12312,
            "c" * 40,
            "hive-mind-standard-v2",
            OTHER_DIGEST,
        ),
        (ResourceRequirement("cpu", "compute", 1, "worker", ("bounded",)),),
        (
            CapabilityRequirement(
                "inspect", "read", "none", "local-auth", "subject-adapter"
            ),
        ),
        (AdapterRequirement("subject-adapter", "subject.inspect", "v1", DIGEST),),
        (
            AuthorityEnvelope(
                "local-auth",
                "principal-builder",
                OTHER_DIGEST,
                ("read",),
                ("write",),
                TIME,
                False,
            ),
        ),
        (BudgetAllocation("small", BudgetPolicy(60, 1, 100, 50, 0, 4, 1)),),
        RecoveryPolicy(2, True, True, ("authority-gap", "evidence-gap")),
        IntegrationPolicy("compare-and-swap", "candidate/main", DIGEST, True, True),
        TokenPolicy(100, 50, 10, "exact", "stop"),
        (
            EvidenceReference(
                "source-1", DIGEST, "fixture", ("CLAIM-1",), "2026-08-23T00:00:00Z"
            ),
        ),
        (
            PortableNode(
                "inspect",
                "inspect subject",
                (),
                ("cpu",),
                ("inspect",),
                ("subject-adapter",),
                "local-auth",
                "small",
                ("source-1",),
                ("inspection is evidenced",),
                "discard candidate",
                ("explorer",),
                ("discover",),
            ),
            PortableNode(
                "judge",
                "judge evidence",
                ("inspect",),
                (),
                (),
                (),
                "local-auth",
                "small",
                ("source-1",),
                ("judgment is recorded",),
                "retain dissent",
                ("curator",),
                ("validate",),
            ),
        ),
    )


class EffectClassTests(unittest.TestCase):
    def test_v1_effect_vocabulary_is_closed_and_external_class_is_explicit(
        self,
    ) -> None:
        expected = {
            "none": False,
            "local-reversible": False,
            "external-reversible": True,
        }
        self.assertEqual(set(expected), set(EFFECT_CLASSES_V1))
        base = make_plan().capabilities[0]
        for effect_class, external in expected.items():
            with self.subTest(effect_class=effect_class):
                capability = replace(base, effect_class=effect_class)
                self.assertEqual(
                    external,
                    requires_external_authority(capability.effect_class),
                )
        for value in (
            "external",
            "external-reversible-v2",
            "external_reversible",
            "local",
            "none ",
            "production",
            "protected",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ContractViolation, "closed V1"):
                    replace(base, effect_class=value)


class PortablePlanContractTests(unittest.TestCase):
    def test_repository_plan_round_trips_to_one_canonical_form(self) -> None:
        plan = make_plan()
        restored = PortablePlanBundle.from_bytes(plan.canonical_bytes())
        self.assertEqual(plan, restored)
        self.assertEqual(plan.canonical_bytes(), restored.canonical_bytes())
        self.assertEqual(plan.digest(), canonical_digest(plan.to_document()))
        self.assertEqual(SubjectKind.REPOSITORY, restored.subject.kind)

    def test_non_repository_subject_is_first_class_and_cross_identity_fails(
        self,
    ) -> None:
        plan = make_plan(repository=False)
        self.assertEqual(
            SubjectKind.NON_REPOSITORY,
            PortablePlanBundle.from_bytes(plan.canonical_bytes()).subject.kind,
        )
        document = plan.to_document()
        document["subject"]["subject_id"] = DIGEST
        with self.assertRaisesRegex(ContractViolation, "authenticate"):
            PortablePlanBundle.from_document(document)

    def test_closed_boundary_rejects_unknown_duplicate_nonfinite_deep_and_oversize(
        self,
    ) -> None:
        plan = make_plan()
        document = plan.to_document()
        document["ambient_authority"] = True
        with self.assertRaisesRegex(ContractViolation, "unsupported"):
            PortablePlanBundle.from_document(document)
        with self.assertRaisesRegex(ContractViolation, "duplicate"):
            PortablePlanBundle.from_bytes(b'{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ContractViolation, "non-finite"):
            PortablePlanBundle.from_bytes(b'{"value":NaN}')
        deep: object = {}
        for _ in range(70):
            deep = {"child": deep}
        with self.assertRaisesRegex(ContractViolation, "nesting-depth"):
            PortablePlanBundle.from_bytes(json.dumps(deep).encode())
        with self.assertRaisesRegex(ContractViolation, "byte limit"):
            PortablePlanBundle.from_bytes(b"{" + b" " * 1_048_576 + b"}")

    def test_boolean_schema_version_is_not_integer_version_one(self) -> None:
        document = make_plan().to_document()
        document["schema_version"] = True
        with self.assertRaisesRegex(ContractViolation, "schema version"):
            PortablePlanBundle.from_document(document)

    def test_graph_and_cross_references_fail_closed(self) -> None:
        document = make_plan().to_document()
        document["nodes"][0]["dependencies"] = ["judge"]
        with self.assertRaisesRegex(ContractViolation, "cycle"):
            PortablePlanBundle.from_document(document)
        document = make_plan().to_document()
        document["nodes"][0]["capability_ids"] = ["missing"]
        with self.assertRaisesRegex(ContractViolation, "unknown capability"):
            PortablePlanBundle.from_document(document)
        document = make_plan().to_document()
        document["capabilities"][0]["authority_id"] = "missing"
        with self.assertRaisesRegex(ContractViolation, "unknown adapter or authority"):
            PortablePlanBundle.from_document(document)

    def test_plan_is_immutable_data_and_contains_no_execution_method(self) -> None:
        plan = make_plan()
        self.assertFalse(hasattr(plan, "execute"))
        self.assertFalse(plan.authority[0].external_effects)
        with self.assertRaisesRegex((AttributeError, TypeError), ""):
            plan.plan_id = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
