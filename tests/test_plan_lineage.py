from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.plan_lineage import (
    ActivationMaterial,
    GenerationLineage,
    GenerationRecord,
    QualifiedNodeReceipt,
    TraceabilityDisposition,
    carry_forward_receipts,
    validate_traceability,
    verify_historical_bytes,
)
from hive_mind_os.runtime_contracts import (
    ContractViolation,
    canonical_json_bytes,
    raw_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


def record(
    *,
    parent: GenerationRecord | None = None,
    subject_id: str = D1,
    standard_version: int = 2,
    plan_digest: str = D2,
) -> GenerationRecord:
    return GenerationRecord.create(
        request_id=D1,
        objective_digest=D2,
        repository_id=D3,
        subject_id=subject_id,
        subject_kind="repository",
        target="candidate/main",
        parent_generation_id=None if parent is None else parent.generation_id,
        parent_commit="a" * 40,
        parent_tree="b" * 40,
        node_mappings_digest=D3,
        source_inventory_digest=D4,
        standard_version=standard_version,
        standard_digest=D1,
        compiler_digest=D2,
        plan_digest=plan_digest,
    )


class PlanLineageTests(unittest.TestCase):
    def test_boolean_schema_versions_are_rejected(self) -> None:
        generation = record()
        document = generation.to_document()
        document["schema_version"] = True
        with self.assertRaisesRegex(ContractViolation, "schema version"):
            GenerationRecord.from_document(document)

        plan_bytes = b"sealed-plan"
        plan_digest = raw_sha256(plan_bytes)
        manifest_bytes = canonical_json_bytes(
            {
                "schema_version": True,
                "kind": "external-plan-activation-manifest",
                "generation": {"generation_id": generation.generation_id},
                "plan_digest": plan_digest,
                "authentication": {
                    "host_signature_required": True,
                    "distinct_key_required": True,
                    "repository_signature_forbidden": True,
                },
            }
        )
        with self.assertRaisesRegex(ContractViolation, "unsupported external"):
            ActivationMaterial(
                generation.generation_id,
                plan_bytes,
                manifest_bytes,
                plan_digest,
                raw_sha256(manifest_bytes),
            )

    def test_generation_id_authenticates_every_nested_binding(self) -> None:
        original = record()
        self.assertEqual(
            original, GenerationRecord.from_document(original.to_document())
        )
        for field, value in (
            ("request_id", D4),
            ("objective_digest", D4),
            ("repository_id", D4),
            ("subject_id", D4),
            ("target", "other"),
            ("parent_tree", "c" * 40),
            ("node_mappings_digest", D4),
            ("source_inventory_digest", D3),
            ("standard_digest", D4),
            ("compiler_digest", D4),
            ("plan_digest", D4),
        ):
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ContractViolation, "generation_id"),
            ):
                replace(original, **{field: value})

    def test_lineage_exact_repeat_is_idempotent_but_substitution_fails(self) -> None:
        parent = record(standard_version=2)
        lineage = GenerationLineage()
        self.assertTrue(lineage.register(parent)[1])
        self.assertFalse(lineage.register(parent)[1])
        cross_subject = record(parent=parent, subject_id=D4, plan_digest=D3)
        with self.assertRaisesRegex(ContractViolation, "cross-subject"):
            lineage.register(cross_subject)
        downgrade = record(parent=parent, standard_version=1, plan_digest=D3)
        with self.assertRaisesRegex(ContractViolation, "downgrade"):
            lineage.register(downgrade)
        seed = record(plan_digest=D3)
        orphan = GenerationRecord.create(
            request_id=seed.request_id,
            objective_digest=seed.objective_digest,
            repository_id=seed.repository_id,
            subject_id=seed.subject_id,
            subject_kind=seed.subject_kind,
            target=seed.target,
            parent_generation_id=D4,
            parent_commit=seed.parent_commit,
            parent_tree=seed.parent_tree,
            node_mappings_digest=seed.node_mappings_digest,
            source_inventory_digest=seed.source_inventory_digest,
            standard_version=seed.standard_version,
            standard_digest=seed.standard_digest,
            compiler_digest=seed.compiler_digest,
            plan_digest=seed.plan_digest,
        )
        with self.assertRaisesRegex(ContractViolation, "parent is missing"):
            lineage.register(orphan)

    def test_current_request_and_tree_are_checked_without_legacy_fallback(self) -> None:
        item = record()
        lineage = GenerationLineage((item,))
        self.assertIs(
            item,
            lineage.require_expected(
                item.generation_id,
                request_id=D1,
                objective_digest=D2,
                subject_id=D1,
                repository_id=D3,
                target="candidate/main",
                parent_commit="a" * 40,
                parent_tree="b" * 40,
            ),
        )
        with self.assertRaisesRegex(ContractViolation, "does not match"):
            lineage.require_expected(
                item.generation_id,
                request_id=D1,
                objective_digest=D2,
                subject_id=D1,
                repository_id=D3,
                target="candidate/main",
                parent_commit="a" * 40,
                parent_tree="c" * 40,
            )

    def test_receipts_carry_only_for_unchanged_contract_and_same_subject(self) -> None:
        keep = QualifiedNodeReceipt.create("keep", D1, D3, b"qualified keep")
        changed = QualifiedNodeReceipt.create("changed", D2, D3, b"qualified changed")
        removed = QualifiedNodeReceipt.create("removed", D1, D3, b"qualified removed")
        result = carry_forward_receipts(
            previous_contracts={"keep": D1, "changed": D2, "removed": D1},
            next_contracts={"keep": D1, "changed": D4, "new": D1},
            receipts=(keep, changed, removed),
            subject_id=D3,
        )
        self.assertEqual((keep,), result.carried)
        self.assertIs(keep.receipt_bytes, result.carried[0].receipt_bytes)
        self.assertEqual(("changed",), result.requalify)
        self.assertEqual((removed,), result.historical)
        self.assertEqual(("new",), result.new_nodes)
        with self.assertRaisesRegex(ContractViolation, "cross-subject"):
            carry_forward_receipts(
                previous_contracts={"keep": D1},
                next_contracts={"keep": D1},
                receipts=(keep,),
                subject_id=D4,
            )

    def test_v1_plan_rows_have_retained_plan_trace_dispositions(self) -> None:
        source = json.loads(
            (OVERLAY / "source-intake.json").read_text(encoding="utf-8")
        )
        trace = json.loads((OVERLAY / "traceability.json").read_text(encoding="utf-8"))[
            "rows"
        ]
        expected = {
            row["row_id"]
            for row in source["v1_traceability"]["rows"]
            if "PLAN-CORE-100" in row["target_node_ids"]
        }
        rows = tuple(
            TraceabilityDisposition(
                row_id,
                trace[row_id]["disposition"],
                tuple(trace[row_id]["target_acceptance_ids"]),
            )
            for row_id in expected
        )
        self.assertEqual(
            len(expected),
            len(
                validate_traceability(
                    rows,
                    expected_row_ids=expected,
                    required_acceptance_id="AC-PLAN-TRACE",
                )
            ),
        )
        with self.assertRaisesRegex(ContractViolation, "coverage"):
            validate_traceability(
                rows[:-1],
                expected_row_ids=expected,
                required_acceptance_id="AC-PLAN-TRACE",
            )

    def test_historical_plan_is_checked_as_bytes_not_reinterpreted(self) -> None:
        raw = (ROOT / ".autopilot" / "plan.json").read_bytes()
        verify_historical_bytes(raw, raw_sha256(raw))
        with self.assertRaisesRegex(ContractViolation, "changed"):
            verify_historical_bytes(raw + b"\n", raw_sha256(raw))


if __name__ == "__main__":
    unittest.main()
