from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from hive_mind_os.activation_bundle import AuthorizedOneRun
from hive_mind_os.host_adapter import (
    HOST_DEADLINE_CAPABILITY,
    HostAdapter,
    HostExecutionReceipt,
    HostIdentity,
    HostLease,
    HostObservation,
    HostReceiptState,
)
from hive_mind_os.plan_lineage import TraceabilityDisposition, validate_traceability
from hive_mind_os.runtime_contracts import (
    AlternativeScore,
    AppealState,
    AuthorityEnvelope,
    BudgetPolicy,
    ContractViolation,
    DecisionAlternative,
    DecisionMemoryDraft,
    DurabilityRole,
    EvidenceReference,
    NodeRuntimeContract,
    SelectionBlocker,
    SelectionBlockerCode,
    SharedSurfaceOwner,
    VisionPosture,
    WaveState,
    select_decision,
    validate_runtime_contracts,
)
from hive_mind_os.wave_manifest import (
    CandidateIdentity,
    WaveManifest,
    WaveNode,
    WaveNodeState,
)

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
TIME = "2026-08-23T00:00:00Z"
FUTURE = "2030-01-01T00:00:00Z"


def load_v3_contracts() -> tuple[
    list[NodeRuntimeContract],
    list[SharedSurfaceOwner],
    dict[str, tuple[DurabilityRole, tuple[str, ...]]],
    dict[str, str],
]:
    contracts = json.loads(
        (OVERLAY / "node-contracts.json").read_text(encoding="utf-8")
    )
    ownership = json.loads(
        (OVERLAY / "ownership-effects.json").read_text(encoding="utf-8")
    )
    nodes = [
        NodeRuntimeContract(
            item["id"],
            tuple(item["dependencies"]),
            DurabilityRole(item["durability_role"]),
            tuple(item.get("durability_providers", ())),
            tuple(item["write_scope"]),
        )
        for item in contracts["nodes"]
    ]
    surfaces = [
        SharedSurfaceOwner(name, item["owner"], tuple(item["paths"]))
        for name, item in ownership["single_writer_surfaces"].items()
    ]
    durability = {
        item["id"]: (
            DurabilityRole(item["durability_role"]),
            tuple(item.get("durability_providers", ())),
        )
        for item in contracts["nodes"]
    }
    owners = {
        name: item["owner"]
        for name, item in ownership["single_writer_surfaces"].items()
    }
    return nodes, surfaces, durability, owners


def blocker_code(value) -> SelectionBlockerCode:
    assert isinstance(value, SelectionBlocker)
    return value.code


def decision_draft() -> DecisionMemoryDraft:
    evidence = (
        EvidenceReference("ev-a", DIGEST, "fixture:a", ("CLAIM-A",), TIME),
        EvidenceReference("ev-b", OTHER_DIGEST, "fixture:b", ("CLAIM-B",), TIME),
    )
    authority = (
        AuthorityEnvelope("auth", "principal", DIGEST, ("select",), (), FUTURE, False),
    )
    alternatives = (
        DecisionAlternative(
            "safe-a",
            "bounded option",
            ("ev-a",),
            (),
            (("inside-scope", True),),
            ("auth",),
            True,
        ),
        DecisionAlternative(
            "safe-b",
            "other bounded option",
            ("ev-b",),
            (),
            (("inside-scope", True),),
            ("auth",),
            True,
        ),
    )
    return DecisionMemoryDraft(
        1,
        "memory-choice",
        "Which bounded option?",
        DIGEST,
        alternatives,
        evidence,
        (),
        ("inside-scope",),
        authority,
        BudgetPolicy(60, 1, 10, 10, 0, 1, 1),
        "weighted-evidence-v1",
        (AlternativeScore("safe-a", 2.0), AlternativeScore("safe-b", 1.0)),
        "low",
        "judge",
        TIME,
        FUTURE,
        (),
        None,
        AppealState.NONE,
    )


class RuntimeContractTests(unittest.TestCase):
    def test_boolean_schema_versions_are_rejected(self) -> None:
        draft = decision_draft()
        with self.assertRaisesRegex(ContractViolation, "schema version"):
            replace(draft, schema_version=True)  # type: ignore[arg-type]

        selected = select_decision(draft, observed_snapshot=DIGEST, now=TIME)
        self.assertNotIsInstance(selected, SelectionBlocker)
        assert not isinstance(selected, SelectionBlocker)
        document = selected.to_document()
        document["schema_version"] = True
        with self.assertRaisesRegex(ContractViolation, "schema version"):
            type(selected).from_document(document)

        with self.assertRaisesRegex(ContractViolation, "schema version"):
            VisionPosture(
                True,  # type: ignore[arg-type]
                "NOT_READY",
                "RESOLVED",
                (),
                "bounded",
            )

    def test_exact_v3_durability_and_single_writer_contracts(self) -> None:
        nodes, surfaces, expected, owners = load_v3_contracts()
        summary = validate_runtime_contracts(
            nodes,
            surfaces,
            expected_durability=expected,
            expected_shared_surface_owners=owners,
            expected_node_count=20,
            expected_write_path_count=85,
        )
        self.assertEqual(
            (20, 85, 7),
            (
                summary.node_count,
                summary.unique_write_path_count,
                summary.shared_surface_count,
            ),
        )
        self.assertTrue(summary.digest.startswith("sha256:"))

    def test_changed_durability_or_duplicate_writer_fails_closed(self) -> None:
        nodes, surfaces, expected, owners = load_v3_contracts()
        changed = list(nodes)
        changed[0] = replace(changed[0], durability_role=DurabilityRole.PROVIDER)
        with self.assertRaisesRegex(ContractViolation, "durability assignment changed"):
            validate_runtime_contracts(
                changed,
                surfaces,
                expected_durability=expected,
                expected_shared_surface_owners=owners,
                expected_node_count=20,
                expected_write_path_count=85,
            )
        duplicate = list(nodes)
        duplicate[1] = replace(duplicate[1], write_scope=(nodes[0].write_scope[0],))
        with self.assertRaisesRegex(ContractViolation, "multiple owners"):
            validate_runtime_contracts(
                duplicate,
                surfaces,
                expected_durability={
                    **expected,
                    duplicate[1].node_id: (
                        duplicate[1].durability_role,
                        duplicate[1].durability_providers,
                    ),
                },
                expected_shared_surface_owners=owners,
                expected_node_count=20,
                expected_write_path_count=85,
            )

    def test_decision_memory_retains_complete_tree_and_selects_unique_safe_winner(
        self,
    ) -> None:
        selected = select_decision(decision_draft(), observed_snapshot=DIGEST, now=TIME)
        self.assertNotIsInstance(selected, SelectionBlocker)
        assert not isinstance(selected, SelectionBlocker)
        self.assertEqual("safe-a", selected.winner)
        self.assertEqual(("safe-b",), selected.losers)
        document = selected.to_document()
        required = {
            "question",
            "snapshot",
            "alternatives",
            "evidence",
            "counterevidence",
            "constraints",
            "authority",
            "budget",
            "scoring_model",
            "scores",
            "winner",
            "losers",
            "uncertainty",
            "owner",
            "decided_at",
            "fresh_until",
            "corrections",
            "supersession",
            "appeal_state",
        }
        self.assertTrue(required <= set(document))
        self.assertEqual(selected.entry_digest, document["entry_digest"])
        self.assertEqual(selected, type(selected).from_document(document))

    def test_decision_selection_returns_typed_blockers(self) -> None:
        draft = decision_draft()
        missing = replace(
            draft,
            alternatives=(
                replace(draft.alternatives[0], evidence_ids=()),
                draft.alternatives[1],
            ),
        )
        self.assertEqual(
            SelectionBlockerCode.MISSING_EVIDENCE,
            blocker_code(select_decision(missing, observed_snapshot=DIGEST, now=TIME)),
        )
        ambiguous = replace(
            draft,
            alternatives=(
                replace(draft.alternatives[0], authority_ids=()),
                draft.alternatives[1],
            ),
        )
        self.assertEqual(
            SelectionBlockerCode.AUTHORITY_AMBIGUOUS,
            blocker_code(
                select_decision(ambiguous, observed_snapshot=DIGEST, now=TIME)
            ),
        )
        tied = replace(
            draft, scores=(AlternativeScore("safe-a", 2), AlternativeScore("safe-b", 2))
        )
        self.assertEqual(
            SelectionBlockerCode.UNRESOLVED_TIE,
            blocker_code(select_decision(tied, observed_snapshot=DIGEST, now=TIME)),
        )
        unsafe = replace(
            draft,
            alternatives=(
                replace(draft.alternatives[0], safe=False),
                draft.alternatives[1],
            ),
        )
        self.assertEqual(
            SelectionBlockerCode.UNSAFE_WINNER,
            blocker_code(select_decision(unsafe, observed_snapshot=DIGEST, now=TIME)),
        )
        self.assertEqual(
            SelectionBlockerCode.STALE_SNAPSHOT,
            blocker_code(
                select_decision(draft, observed_snapshot=OTHER_DIGEST, now=TIME)
            ),
        )

    def test_wave_manifest_seals_subject_and_enforces_state_machine(self) -> None:
        nodes = (WaveNode("node-a", WaveNodeState.CHECKPOINTED, 1, DIGEST, None),)
        checkpoint = WaveManifest(
            1,
            "wave-1",
            DIGEST,
            OTHER_DIGEST,
            DIGEST,
            None,
            WaveState.CHECKPOINTED,
            nodes,
            DIGEST,
            None,
            TIME,
        )
        candidate = CandidateIdentity("a" * 40, "b" * 40, DIGEST)
        sealed = checkpoint.transition(
            WaveState.CANDIDATE_SEALED, candidate=candidate, created_at=TIME
        )
        self.assertEqual(checkpoint.manifest_digest, sealed.parent_wave_digest)
        self.assertEqual(sealed, WaveManifest.from_bytes(sealed.canonical_bytes()))
        document = sealed.to_document()
        document["schema_version"] = True
        with self.assertRaisesRegex(ContractViolation, "schema version"):
            WaveManifest.from_document(document)
        with self.assertRaisesRegex(ContractViolation, "invalid wave transition"):
            sealed.transition(WaveState.INTEGRATED, created_at=TIME)
        with self.assertRaisesRegex(ContractViolation, "subject differs"):
            checkpoint.transition(
                WaveState.CANDIDATE_SEALED,
                candidate=CandidateIdentity("a" * 40, "b" * 40, OTHER_DIGEST),
                created_at=TIME,
            )

    def test_host_boundary_is_structural_and_requires_a_bound_lease(self) -> None:
        class FixtureHost:
            def observe(self, *, subject_id: str) -> HostObservation:
                identity = HostIdentity(
                    "host", "windows", "amd64", "3.14", DIGEST, OTHER_DIGEST
                )
                return HostObservation(
                    identity, subject_id, TIME, ("local",), DIGEST, True
                )

            def prepare(
                self,
                *,
                plan_digest: str,
                generation_id: str,
                authority_digest: str,
                adapter_inventory_digest: str,
                external_effects_required: bool,
                compilation_receipt: Mapping[str, Any],
                subject_id: str,
                node_ids: tuple[str, ...],
                nonce_digest: str,
                lease_deadline: str,
                authorization: AuthorizedOneRun,
                required_capabilities: tuple[str, ...],
            ) -> HostLease:
                return HostLease(
                    "lease",
                    "host",
                    subject_id,
                    generation_id,
                    authority_digest,
                    adapter_inventory_digest,
                    external_effects_required,
                    OTHER_DIGEST,
                    authorization.activation_digest,
                    authorization.proof_digest,
                    authorization.candidate_commit,
                    authorization.candidate_tree,
                    authorization.candidate_content_sha256,
                    authorization.candidate_parent_commit,
                    authorization.candidate_parent_tree,
                    authorization.manifest_sha256,
                    authorization.repository_id,
                    authorization.request_sha256,
                    authorization.target_branch,
                    authorization.execution_client_sha256,
                    authorization.issued_at.isoformat().replace("+00:00", "Z"),
                    authorization.protected_merge_authorized,
                    DIGEST,
                    OTHER_DIGEST,
                    required_capabilities,
                    TIME,
                    lease_deadline,
                    node_ids,
                    nonce_digest,
                )

            def execute(
                self, *, node_id: str, input_bytes: bytes, lease: HostLease
            ) -> HostExecutionReceipt:
                return HostExecutionReceipt(
                    "receipt",
                    lease.lease_id,
                    node_id,
                    HostReceiptState.SUCCEEDED,
                    DIGEST,
                    OTHER_DIGEST,
                    DIGEST,
                    TIME,
                )

            def cancel(self, *, lease: HostLease, reason: str) -> HostExecutionReceipt:
                return HostExecutionReceipt(
                    "cancel",
                    lease.lease_id,
                    lease.allowed_node_ids[0],
                    HostReceiptState.CANCELLED,
                    DIGEST,
                    None,
                    DIGEST,
                    TIME,
                )

        self.assertIsInstance(FixtureHost(), HostAdapter)
        with self.assertRaisesRegex(ContractViolation, "expire after"):
            HostLease(
                lease_id="lease",
                host_id="host",
                subject_id=DIGEST,
                generation_id=OTHER_DIGEST,
                authority_digest=DIGEST,
                adapter_inventory_digest=OTHER_DIGEST,
                external_effects_required=False,
                compilation_digest=DIGEST,
                activation_digest=DIGEST,
                activation_proof_digest=OTHER_DIGEST,
                candidate_commit="a" * 40,
                candidate_tree="b" * 40,
                candidate_content_sha256=DIGEST,
                candidate_parent_commit="c" * 40,
                candidate_parent_tree="d" * 40,
                manifest_sha256=DIGEST,
                repository_id=OTHER_DIGEST,
                request_sha256=DIGEST,
                target_branch="main",
                execution_client_sha256=OTHER_DIGEST,
                activation_issued_at=TIME,
                protected_merge_authorized=False,
                host_identity_digest=DIGEST,
                trust_evidence_digest=OTHER_DIGEST,
                required_capabilities=(HOST_DEADLINE_CAPABILITY,),
                issued_at=TIME,
                expires_at=TIME,
                allowed_node_ids=("node",),
                nonce_digest=DIGEST,
            )

    def test_runtime_traceability_schemas_and_vision_nonclaim_are_retained(
        self,
    ) -> None:
        source = json.loads(
            (OVERLAY / "source-intake.json").read_text(encoding="utf-8")
        )
        trace = json.loads((OVERLAY / "traceability.json").read_text(encoding="utf-8"))[
            "rows"
        ]
        expected = {
            row["row_id"]
            for row in source["v1_traceability"]["rows"]
            if "RUNTIME-CONTRACTS-150" in row["target_node_ids"]
        }
        rows = tuple(
            TraceabilityDisposition(
                key,
                trace[key]["disposition"],
                tuple(trace[key]["target_acceptance_ids"]),
            )
            for key in expected
        )
        self.assertEqual(
            len(expected),
            len(
                validate_traceability(
                    rows,
                    expected_row_ids=expected,
                    required_acceptance_id="AC-CONTRACTS-TRACE",
                )
            ),
        )
        plan = json.loads((OVERLAY / "plan.json").read_text(encoding="utf-8"))
        posture = plan["vision_posture"]
        contract = VisionPosture(
            1,
            posture["A5"],
            posture["active_gate_reference_only_conflict"],
            tuple(posture["forbidden_claims"]),
            posture["maximum_claim"],
        )
        self.assertEqual("NOT_READY", contract.a5)
        for name in ("portable-plan.schema.json", "runtime-contracts.schema.json"):
            schema = json.loads(
                (ROOT / "docs" / "execution" / name).read_text(encoding="utf-8")
            )
            self.assertIn("v1", schema["$id"])
        portable_schema = json.loads(
            (ROOT / "docs" / "execution" / "portable-plan.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(portable_schema["additionalProperties"])
        self.assertIn("standard", portable_schema["required"])
        self.assertTrue(
            {"acceptance_criteria", "rollback", "roles", "lifecycle_stages"}
            <= set(portable_schema["$defs"]["node"]["required"])
        )


if __name__ == "__main__":
    unittest.main()
