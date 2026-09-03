from __future__ import annotations

import unittest
from dataclasses import replace

from hive_mind_os.dag_standard import (
    COMPILER_PACKAGE_DIGEST,
    COMPILER_PACKAGE_ID,
    compile_plan,
    git_blob_id,
)
from hive_mind_os.portable_plan import (
    PortableNode,
    RepositorySubject,
    StandardBinding,
    SubjectBinding,
)
from hive_mind_os.runtime_contracts import ContractViolation, raw_sha256
from tests.test_portable_plan import make_plan

STANDARD = b"portable standard v2\n"
ACTIVATION_REQUEST = (
    "Approve an executable successor to `generic-hive-mind-product-v3`, bind it "
    "to `main` and this exact request, and issue a signed one-run activation bundle "
    "with independent review and frozen-host evidence."
)
ROLES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)
STAGES = ("discover", "design", "build", "validate", "grow", "maintain", "integrate")


def compiler_plan():
    original = make_plan()
    subject = SubjectBinding.for_repository(
        RepositorySubject(
            "sha256:" + "5" * 64,
            "0" * 40,
            "1" * 40,
            "main",
        )
    )
    standard = StandardBinding(
        2,
        "docs/execution/DAG_AUTHORING_STANDARD_V2.md",
        raw_sha256(STANDARD),
        len(STANDARD),
        git_blob_id(STANDARD),
        COMPILER_PACKAGE_ID,
        COMPILER_PACKAGE_DIGEST,
    )
    nodes = []
    for index, role in enumerate(ROLES):
        dependencies = () if index < 2 else (ROLES[index - 2],)
        nodes.append(
            PortableNode(
                role,
                f"exercise {role}",
                dependencies,
                ("cpu",),
                ("inspect",),
                ("subject-adapter",),
                "local-auth",
                "small",
                ("source-1",),
                (f"{role} receipt exists",),
                "discard disposable output",
                (role,),
                (STAGES[index % len(STAGES)],),
            )
        )
    budget = replace(original.budgets[0].policy, concurrent_workers=4)
    allocation = replace(original.budgets[0], policy=budget)
    resource = replace(original.resources[0], quantity=4)
    return replace(
        original,
        request_id=raw_sha256(ACTIVATION_REQUEST.encode("utf-8")),
        subject=subject,
        standard=standard,
        resources=(resource,),
        budgets=(allocation,),
        nodes=tuple(nodes),
    )


class PackagedDagCompilerTests(unittest.TestCase):
    def test_canonical_compiler_emits_repeatable_conflict_free_rounds(self) -> None:
        plan = compiler_plan()
        first = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD,
            maximum_workers=4,
        )
        second = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD,
            maximum_workers=4,
        )
        self.assertEqual(first, second)
        self.assertEqual(8, first.metrics.node_count)
        self.assertEqual(4, first.metrics.dependency_level_count)
        self.assertEqual(2, len(first.rounds[0].node_ids))
        self.assertEqual((), first.lint_errors)
        self.assertEqual((), first.lint_warnings)

    def test_resource_capacity_splits_a_dependency_level(self) -> None:
        plan = compiler_plan()
        constrained = replace(plan.resources[0], quantity=1)
        plan = replace(plan, resources=(constrained,))
        receipt = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD,
        )
        self.assertEqual(8, len(receipt.rounds))
        self.assertTrue(all(len(item.node_ids) == 1 for item in receipt.rounds))

    def test_digest_standard_package_and_canonical_substitution_fail_closed(self) -> None:
        plan = compiler_plan()
        arguments = {
            "expected_plan_digest": plan.digest(),
            "standard_bytes": STANDARD,
        }
        with self.assertRaisesRegex(ContractViolation, "caller expectation"):
            compile_plan(
                plan.canonical_bytes(),
                **{**arguments, "expected_plan_digest": "sha256:" + "0" * 64},
            )
        with self.assertRaisesRegex(ContractViolation, "raw digest"):
            compile_plan(plan.canonical_bytes(), **{**arguments, "standard_bytes": b"swap"})
        changed = replace(
            plan,
            standard=replace(plan.standard, package_digest="sha256:" + "0" * 64),
        )
        with self.assertRaisesRegex(ContractViolation, "package identity"):
            compile_plan(
                changed.canonical_bytes(),
                expected_plan_digest=changed.digest(),
                standard_bytes=STANDARD,
            )
        noncanonical = plan.canonical_bytes().replace(b"{", b"{ ", 1)
        with self.assertRaisesRegex(ContractViolation, "canonical form"):
            compile_plan(noncanonical, **arguments)

    def test_missing_role_evidence_or_lifecycle_fails_closed(self) -> None:
        plan = compiler_plan()
        plan = replace(plan, nodes=plan.nodes[:-1])
        with self.assertRaisesRegex(ContractViolation, "omits required specialist"):
            compile_plan(
                plan.canonical_bytes(),
                expected_plan_digest=plan.digest(),
                standard_bytes=STANDARD,
            )
        complete = compiler_plan()
        first = replace(complete.nodes[0], evidence_ids=())
        complete = replace(complete, nodes=(first, *complete.nodes[1:]))
        with self.assertRaisesRegex(ContractViolation, "no evidence"):
            compile_plan(
                complete.canonical_bytes(),
                expected_plan_digest=complete.digest(),
                standard_bytes=STANDARD,
            )

    def test_product_compiler_has_no_execute_surface(self) -> None:
        plan = compiler_plan()
        receipt = compile_plan(
            plan.canonical_bytes(),
            expected_plan_digest=plan.digest(),
            standard_bytes=STANDARD,
        )
        self.assertFalse(hasattr(receipt, "execute"))


if __name__ == "__main__":
    unittest.main()
