#!/usr/bin/env python3
"""Materialize the canonical V4 portable plan; never execute it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hive_mind_os.dag_standard import (
    COMPILER_PACKAGE_DIGEST,
    COMPILER_PACKAGE_ID,
    compile_plan,
    git_blob_id,
)
from hive_mind_os.portable_plan import (
    BudgetAllocation,
    PortableNode,
    PortablePlanBundle,
    RepositorySubject,
    StandardBinding,
    SubjectBinding,
)
from hive_mind_os.runtime_contracts import (
    AdapterRequirement,
    AuthorityEnvelope,
    BudgetPolicy,
    CapabilityRequirement,
    EvidenceReference,
    IntegrationPolicy,
    RecoveryPolicy,
    ResourceRequirement,
    TokenPolicy,
    canonical_digest,
    raw_sha256,
)

ROOT = Path(__file__).resolve().parents[4]
V3_CONTRACTS = ROOT / "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json"
STANDARD = ROOT / "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
REQUEST_TEXT = (
    "Approve an executable successor to `generic-hive-mind-product-v3`, bind it "
    "to `main` and this exact request, and issue a signed one-run activation bundle "
    "with independent review and frozen-host evidence."
)
BASE_COMMIT = "59a5364501c5e49ceb28574aad7a4ac1512291b9"
BASE_TREE = "72696b27cdd2c9cd08085c05c98513ece733cc8d"
EXPECTED_METRICS = (20, 28, 17, 6)

ROLE_STAGE = {
    "BASELINE-000": (("orchestrator", "explorer"), ("discover",)),
    "DOCTOR-PREFLIGHT-005": (("curator", "steward"), ("validate", "maintain")),
    "FOUNDATION-010": (("architect", "steward"), ("design", "maintain")),
    "PLAN-CORE-100": (("orchestrator", "architect"), ("design",)),
    "RUNTIME-CONTRACTS-150": (("architect", "integrator"), ("design", "integrate")),
    "BUILD-SYSTEM-200": (("builder",), ("build",)),
    "ADAPTER-INDEX-210": (("integrator", "builder"), ("build", "integrate")),
    "WAVE-HOST-300": (("steward", "builder"), ("build", "maintain")),
    "TASK-REUSE-310": (("builder", "optimizer"), ("build", "grow")),
    "RUNTIME-TOKEN-320": (("optimizer", "builder"), ("grow", "build")),
    "GENERIC-EXECUTOR-400": (("builder", "orchestrator"), ("build", "integrate")),
    "CONTROL-TOKEN-410": (("optimizer", "builder"), ("grow", "build")),
    "PUBLIC-RUNTIME-500": (("integrator", "builder"), ("integrate", "build")),
    "GENERIC-FIXTURES-600": (("curator", "builder"), ("validate", "build")),
    "FAILURE-QUALIFICATION-610": (("curator", "steward"), ("validate", "maintain")),
    "TOKEN-BENCHMARK-620": (("optimizer", "curator"), ("grow", "validate")),
    "QUALIFICATION-PREP-625": (("orchestrator", "steward"), ("integrate", "maintain")),
    "CANDIDATE-CI-627": (("curator", "steward"), ("validate", "maintain")),
    "GENERIC-QUALIFICATION-630": (("curator",), ("validate",)),
    "HANDOFF-700": (("integrator", "orchestrator"), ("integrate",)),
}

IMPLEMENTATION_NODES = frozenset(
    {
        "BUILD-SYSTEM-200",
        "ADAPTER-INDEX-210",
        "WAVE-HOST-300",
        "TASK-REUSE-310",
        "RUNTIME-TOKEN-320",
        "GENERIC-EXECUTOR-400",
        "CONTROL-TOKEN-410",
        "PUBLIC-RUNTIME-500",
        "GENERIC-FIXTURES-600",
    }
)
EVIDENCE_NODES = frozenset(
    {
        "BASELINE-000",
        "DOCTOR-PREFLIGHT-005",
        "FAILURE-QUALIFICATION-610",
        "TOKEN-BENCHMARK-620",
        "QUALIFICATION-PREP-625",
        "CANDIDATE-CI-627",
        "GENERIC-QUALIFICATION-630",
        "HANDOFF-700",
    }
)


def build_plan() -> PortablePlanBundle:
    source = json.loads(V3_CONTRACTS.read_text(encoding="utf-8"))
    standard_bytes = STANDARD.read_bytes()
    subject = SubjectBinding.for_repository(
        RepositorySubject(
            raw_sha256(b"https://github.com/kb4beast/hive-mind-os.git"),
            BASE_COMMIT,
            BASE_TREE,
            "main",
        )
    )
    resources = (
        ResourceRequirement("worker-slots", "compute", 8, "worker", ("bounded",)),
        ResourceRequirement("candidate-tree", "exclusive", 1, "writer", ("local",)),
        ResourceRequirement("evidence-ledger", "exclusive", 1, "writer", ("append-only",)),
    )
    adapters = (
        AdapterRequirement(
            "subject-inspector", "subject.inspect", "v1", canonical_digest({"mode": "read-only"})
        ),
        AdapterRequirement(
            "candidate-workspace", "candidate.local", "v1", canonical_digest({"mode": "reversible"})
        ),
        AdapterRequirement(
            "test-runner", "test.local", "v1", canonical_digest({"mode": "bounded"})
        ),
        AdapterRequirement(
            "evidence-writer", "evidence.local", "v1", canonical_digest({"mode": "append-only"})
        ),
    )
    request_id = raw_sha256(REQUEST_TEXT.encode("utf-8"))
    authority = (
        AuthorityEnvelope(
            "owner-local-candidate",
            "repository-owner",
            request_id,
            ("inspect", "local-edit", "local-test", "prepare-evidence"),
            (
                "credential",
                "deployment",
                "merge",
                "payment",
                "production-mutation",
                "protected-merge",
                "push",
            ),
            "2026-12-31T23:59:59Z",
            False,
        ),
    )
    capabilities = (
        CapabilityRequirement(
            "inspect-subject", "inspect", "none", "owner-local-candidate", "subject-inspector"
        ),
        CapabilityRequirement(
            "edit-candidate", "local-edit", "local-reversible", "owner-local-candidate", "candidate-workspace"
        ),
        CapabilityRequirement(
            "run-local-tests", "local-test", "local-reversible", "owner-local-candidate", "test-runner"
        ),
        CapabilityRequirement(
            "write-evidence", "prepare-evidence", "local-reversible", "owner-local-candidate", "evidence-writer"
        ),
    )
    budgets = (
        BudgetAllocation("inspect-budget", BudgetPolicy(900, 4, 100_000, 20_000, 0, 16, 8)),
        BudgetAllocation("build-budget", BudgetPolicy(3_600, 16, 300_000, 80_000, 0, 64, 8)),
        BudgetAllocation("evidence-budget", BudgetPolicy(1_800, 8, 160_000, 40_000, 0, 32, 8)),
    )
    evidence = (
        EvidenceReference(
            "v3-node-contracts",
            raw_sha256(V3_CONTRACTS.read_bytes()),
            "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json",
            tuple(f"{node['id']}-OBJ" for node in source["nodes"]),
            "2026-08-23T00:00:00Z",
        ),
    )
    nodes = []
    for source_node in source["nodes"]:
        node_id = source_node["id"]
        roles, stages = ROLE_STAGE[node_id]
        resource_ids = ["worker-slots"]
        capability_ids = ["inspect-subject"]
        adapter_ids = ["subject-inspector"]
        budget_id = "inspect-budget"
        if node_id in IMPLEMENTATION_NODES:
            resource_ids.append("candidate-tree")
            capability_ids.extend(("edit-candidate", "run-local-tests"))
            adapter_ids.extend(("candidate-workspace", "test-runner"))
            budget_id = "build-budget"
        if node_id in EVIDENCE_NODES:
            resource_ids.append("evidence-ledger")
            capability_ids.append("write-evidence")
            adapter_ids.append("evidence-writer")
            budget_id = "evidence-budget"
        nodes.append(
            PortableNode(
                node_id,
                source_node["objective"],
                tuple(source_node["dependencies"]),
                tuple(resource_ids),
                tuple(capability_ids),
                tuple(adapter_ids),
                "owner-local-candidate",
                budget_id,
                ("v3-node-contracts",),
                tuple(source_node["acceptance_criteria"]),
                source_node["rollback"],
                roles,
                stages,
            )
        )
    return PortablePlanBundle(
        1,
        "generic-hive-mind-product-v4",
        request_id,
        raw_sha256(
            b"Implement and qualify a portable externally activated generic DAG runtime."
        ),
        subject,
        StandardBinding(
            2,
            "docs/execution/DAG_AUTHORING_STANDARD_V2.md",
            raw_sha256(standard_bytes),
            len(standard_bytes),
            git_blob_id(standard_bytes),
            COMPILER_PACKAGE_ID,
            COMPILER_PACKAGE_DIGEST,
        ),
        resources,
        capabilities,
        adapters,
        authority,
        budgets,
        RecoveryPolicy(
            3,
            True,
            True,
            (
                "ambiguous-host-effect",
                "authority-gap",
                "candidate-drift",
                "evidence-gap",
                "one-run-deadline",
            ),
        ),
        IntegrationPolicy(
            "compare-and-swap",
            "main",
            canonical_digest({"commit": BASE_COMMIT, "tree": BASE_TREE}),
            True,
            True,
        ),
        TokenPolicy(300_000, 80_000, 20_000, "measured-or-unavailable", "stop"),
        evidence,
        tuple(nodes),
    )


def main() -> None:
    plan = build_plan()
    standard_bytes = STANDARD.read_bytes()
    receipt = compile_plan(
        plan.canonical_bytes(),
        expected_plan_digest=plan.digest(),
        standard_bytes=standard_bytes,
        expected_request_id=plan.request_id,
        expected_subject_id=plan.subject.subject_id,
    )
    metrics = receipt.metrics
    actual = (
        metrics.node_count,
        metrics.raw_edge_count,
        metrics.dependency_level_count,
        metrics.transitive_direct_edge_count,
    )
    if actual != EXPECTED_METRICS:
        raise SystemExit(f"unexpected topology: {actual!r}")
    raw = plan.canonical_bytes()
    if len(sys.argv) == 1:
        sys.stdout.buffer.write(raw)
        return
    if len(sys.argv) != 3 or sys.argv[1] != "--output":
        raise SystemExit("usage: build_plan.py [--output ABSOLUTE_PATH]")
    output = Path(sys.argv[2])
    if not output.is_absolute() or not output.parent.is_dir() or output.is_symlink():
        raise SystemExit("output must be an absolute non-symlink path with an existing parent")
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_bytes(raw)
    temporary.replace(output)


if __name__ == "__main__":
    main()
