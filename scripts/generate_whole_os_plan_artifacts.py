"""Regenerate the inert whole-OS N01 portable-plan artifacts.

This script performs no activation, signing, host attestation, or external effect.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hive_mind_os.dag_standard import compile_plan
from hive_mind_os.plan_generation import PinnedArtifact, PlanGenerationRequest
from hive_mind_os.portable_plan import RepositorySubject, SubjectBinding
from hive_mind_os.runtime_contracts import AuthorityEnvelope, EvidenceReference, raw_sha256
from hive_mind_os.tournament_plan_factory import WholeOSPlanFactory


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs/plan/whole-os-tournament-2026-09-13"
OUTPUT = ROOT / "docs/plan/whole-os-implementation"
BASE_COMMIT = "7dff0a807936b5be33099bdaa5c242674c624776"
BASE_TREE = "682619e74077e9d0bbc4486dd7e219a8d282d347"
TARGET = "codex/whole-os-tournament-implementation"


LOCKS = {
    "N00": ("successor-source-manifest",),
    "N01": ("plan-schema", "architecture-decision-index"),
    "N02": ("benchmark-rubric", "holdout-manifest"),
    "N03": ("repository-profile", "adapter-registry"),
    "N04": ("mission-contract", "acceptance-contract"),
    "N05": ("context-assembly",),
    "N06": ("validation-cache-contract", "task-reuse-admission"),
    "N07": ("provider-route-binding", "local-worker-command"),
    "N08": ("canonical-runtime-binding",),
    "N09": ("outcome-graph-contract", "tournament-dispatch-contract"),
    "N10": ("scheduler-lifecycle", "campaign-controller"),
    "N11": ("campaign-backlog-selection", "idea-ledger:campaign"),
    "N12": ("role-applicability-policy", "mission-closeout-contract"),
    "N13": ("builder-session", "local-tournament-worker"),
    "N14": ("candidate-qualification", "verification-adapter-contract"),
    "N15": (
        "remote-delivery",
        "repository-run-branch:repository:run-branch",
        "campaign-controller",
    ),
    "N16": ("pr-feedback-cursor", "campaign-controller", "repair:pr-head"),
    "N17": (
        "self-upgrade",
        "host-runtime-version-pointer",
        "campaign-controller",
    ),
    "N18": ("isolation-backend:host", "verification-adapter-contract"),
    "N19": ("memory:tenant:repository",),
    "N20": ("draft:subject:external-mission-id:claim-id",),
    "N21": (
        "lesson-delivery:destination:draft-id",
        "upstream-branch:destination:draft-id",
    ),
    "N22": ("source:repository-family:endpoint-pair",),
    "N23": ("episode:id:seal", "evaluator-custody:episode"),
    "N24": ("evaluation:seal:rubric",),
    "N25": ("champion:subject:surface",),
    "N26": ("tool-cache:tool-digest", "adapter-registry"),
    "N27": (
        "roblox-test-environment:id",
        "account-capability:id",
    ),
    "N28": ("release-composition", "public-cli"),
    "N29": ("adversarial-harness", "qualification-evidence"),
    "N30": ("frozen-benchmark", "candidate-promotion"),
    "N31": ("self-campaign", "supervisor-release-pointer"),
    "N32": ("pilot:tenant",),
    "N33": ("release-closeout",),
}


WRITE_PATHS = {
    "N00": (
        "docs/plan/whole-os-implementation/SOURCE_RECONCILIATION.md",
        "docs/plan/whole-os-implementation/source-inventory.json",
        "docs/plan/whole-os-implementation/successor-node-map.json",
        "docs/plan/whole-os-implementation/symbol-classification.json",
        "docs/plan/whole-os-implementation/n00-validation.json",
        "docs/plan/whole-os-implementation/verify_n00.ps1",
    ),
    "N01": (
        "docs/architecture/ADR-079-WHOLE-OS-CAMPAIGN-TOPOLOGY.md",
        "docs/architecture/ADR-080-WHOLE-OS-DURABLE-COMPOSITION.md",
        "docs/architecture/ADR-081-WHOLE-OS-TENANT-LEARNING-BOUNDARIES.md",
        "docs/architecture/ADR-082-WHOLE-OS-ENDPOINT-RECONSTRUCTION.md",
        "docs/architecture/ADR-083-WHOLE-OS-RISK-BASED-QUALIFICATION.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/plan/whole-os-implementation/PLAN.md",
        "docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json",
        "docs/plan/whole-os-implementation/whole-os-plan-v2.json",
        "docs/plan/whole-os-implementation/generation-manifest.json",
        "docs/plan/whole-os-implementation/DISPATCHER.json",
        "docs/plan/whole-os-implementation/NODE_PROMPT.md",
        "scripts/generate_whole_os_plan_artifacts.py",
        "src/hive_mind_os/portable_plan.py",
        "src/hive_mind_os/dag_standard.py",
        "src/hive_mind_os/tournament_plan_factory.py",
        "tests/test_whole_os_plan_contract.py",
    ),
    "N02": (
        "src/hive_mind_os/campaign_metrics.py",
        "tests/test_campaign_metrics.py",
        "docs/benchmarks/whole-os-protocol.md",
    ),
    "N03": (
        "src/hive_mind_os/repository_profile.py",
        "src/hive_mind_os/schemas/repository-profile.schema.json",
        "src/hive_mind_os/adapter_registry.py",
        "tests/test_repository_profile.py",
    ),
    "N04": (
        "src/hive_mind_os/campaign_contracts.py",
        "src/hive_mind_os/schemas/campaign-mission.schema.json",
        "src/hive_mind_os/schemas/work-package.schema.json",
        "tests/test_campaign_contracts.py",
    ),
    "N05": (
        "src/hive_mind_os/campaign_context.py",
        "src/hive_mind_os/local_dag_runtime.py",
        "src/hive_mind_os/workers.py",
        "tests/test_campaign_context.py",
    ),
    "N06": (
        "src/hive_mind_os/validation_policy.py",
        "src/hive_mind_os/task_reuse.py",
        "src/hive_mind_os/test_result_cache.py",
        "src/hive_mind_os/verification_adapters.py",
        "tests/test_validation_policy.py",
    ),
    "N07": (
        "src/hive_mind_os/campaign_routing.py",
        "src/hive_mind_os/local_codex_worker.py",
        "tests/test_campaign_routing.py",
    ),
    "N08": (
        "src/hive_mind_os/workers.py",
        "src/hive_mind_os/cortex/repository/mission_bindings.py",
        "tests/test_hive_cortex_cli_migration.py",
        "tests/test_configured_mission_bindings.py",
    ),
    "N09": (
        "src/hive_mind_os/tournament_plan_factory.py",
        "src/hive_mind_os/local_dag_runtime.py",
        "src/hive_mind_os/brain_kernel/mission_runtime.py",
        "src/hive_mind_os/outcome_graph.py",
        "tests/test_tournament_plan_factory.py",
        "tests/test_hive_cortex_mission_runtime.py",
        "tests/test_outcome_graph.py",
    ),
    "N10": (
        "src/hive_mind_os/workers.py",
        "src/hive_mind_os/scheduler.py",
        "src/hive_mind_os/campaign_service.py",
        "tests/test_scheduler.py",
        "tests/test_workers.py",
        "tests/test_campaign_service.py",
    ),
    "N11": (
        "src/hive_mind_os/discovery_backlog.py",
        "src/hive_mind_os/campaign_service.py",
        "tests/test_discovery_backlog.py",
    ),
    "N12": (
        "src/hive_mind_os/brain_kernel/role_applicability.py",
        "src/hive_mind_os/brain_kernel/role_runtime.py",
        "src/hive_mind_os/brain_kernel/mission_runtime.py",
        "src/hive_mind_os/role_coverage.py",
        "tests/test_hive_cortex_role_applicability.py",
        "tests/test_role_coverage.py",
    ),
    "N13": (
        "src/hive_mind_os/local_codex_worker.py",
        "src/hive_mind_os/local_dag_runtime.py",
        "src/hive_mind_os/builder_session.py",
        "tests/test_local_codex_worker.py",
        "tests/test_local_dag_runtime.py",
        "tests/test_builder_session.py",
    ),
    "N14": (
        "src/hive_mind_os/local_evidence_packet.py",
        "src/hive_mind_os/verification_adapters.py",
        "src/hive_mind_os/candidate_qualification.py",
        "tests/test_verification_adapters.py",
        "tests/test_candidate_qualification.py",
    ),
    "N15": (
        "src/hive_mind_os/delivery_broker.py",
        "src/hive_mind_os/campaign_service.py",
        "tests/test_delivery_broker.py",
        "tests/test_hive_cortex_delivery.py",
    ),
    "N16": (
        "src/hive_mind_os/pr_feedback.py",
        "src/hive_mind_os/campaign_service.py",
        "src/hive_mind_os/cortex/github/rest_gateway.py",
        "tests/test_pr_feedback.py",
        "tests/test_delivery_broker.py",
    ),
    "N17": (
        "src/hive_mind_os/self_upgrade.py",
        "src/hive_mind_os/campaign_service.py",
        "tests/test_self_upgrade.py",
    ),
    "N18": (
        "src/hive_mind_os/isolated_execution.py",
        "src/hive_mind_os/schemas/isolation-attestation.schema.json",
        "src/hive_mind_os/verification_adapters.py",
        "tests/test_isolated_execution.py",
        "docs/architecture/ADR-WOS-N18-isolation.md",
    ),
    "N19": (
        "src/hive_mind_os/tenant_memory.py",
        "src/hive_mind_os/campaign_context.py",
        "src/hive_mind_os/schemas/subject-memory-boundary.schema.json",
        "tests/test_tenant_memory.py",
        "docs/architecture/ADR-WOS-N19-memory-boundaries.md",
    ),
    "N20": (
        "src/hive_mind_os/lesson_drafts.py",
        "src/hive_mind_os/schemas/lesson-draft.schema.json",
        "tests/test_lesson_drafts.py",
        "docs/architecture/ADR-WOS-N20-draft-learning.md",
    ),
    "N21": (
        "src/hive_mind_os/lesson_delivery.py",
        "src/hive_mind_os/delivery_broker.py",
        "src/hive_mind_os/schemas/lesson-delivery-obligation.schema.json",
        "tests/test_lesson_delivery.py",
        "docs/architecture/ADR-WOS-N21-lesson-contribution.md",
        ".hivemind/lessons/drafts/<mission-id>.md",
        "docs/lessons/drafts/<draft-id>.md",
    ),
    "N22": (
        "src/hive_mind_os/endpoint_curriculum.py",
        "src/hive_mind_os/schemas/endpoint-episode.schema.json",
        "tests/test_endpoint_curriculum.py",
        "docs/architecture/ADR-WOS-N22-endpoint-curriculum.md",
    ),
    "N23": (
        "src/hive_mind_os/endpoint_oracle.py",
        "src/hive_mind_os/schemas/endpoint-seal.schema.json",
        "tests/test_endpoint_oracle.py",
        "tests/test_pit_oracle.py",
        "docs/architecture/ADR-WOS-N23-evaluator-custody.md",
    ),
    "N24": (
        "src/hive_mind_os/functional_evaluation.py",
        "src/hive_mind_os/candidate_qualification.py",
        "src/hive_mind_os/schemas/functional-evaluation.schema.json",
        "tests/test_functional_evaluation.py",
        "docs/architecture/ADR-WOS-N24-functional-evaluation.md",
    ),
    "N25": (
        "src/hive_mind_os/scoped_learning.py",
        "src/hive_mind_os/brain_kernel/challengers.py",
        "src/hive_mind_os/brain_kernel/promotion.py",
        "src/hive_mind_os/schemas/learning-route.schema.json",
        "tests/test_scoped_learning.py",
        "docs/architecture/ADR-WOS-N25-scoped-promotion.md",
    ),
    "N26": (
        "src/hive_mind_os/roblox_profile.py",
        "src/hive_mind_os/adapter_registry.py",
        "src/hive_mind_os/verification_adapters.py",
        "src/hive_mind_os/schemas/roblox-profile.schema.json",
        "tests/test_roblox_profile.py",
        "tests/fixtures/roblox_profile/README.md",
        "docs/architecture/ADR-WOS-N26-roblox-profile.md",
    ),
    "N27": (
        "src/hive_mind_os/roblox_runtime.py",
        "src/hive_mind_os/schemas/roblox-runtime-evidence.schema.json",
        "tests/test_roblox_runtime.py",
        "tests/fixtures/roblox_profile",
        "docs/architecture/ADR-WOS-N27-roblox-runtime-evidence.md",
    ),
    "N28": (
        "src/hive_mind_os/cli.py",
        "src/hive_mind_os/workers.py",
        "src/hive_mind_os/verification_adapters.py",
        "tests/test_whole_os_integration.py",
        "tests/fixtures/whole_os",
        "docs/execution/WHOLE_OS_SERVICE.md",
    ),
    "N29": (
        "tests/test_whole_os_adversarial.py",
        "docs/execution/WHOLE_OS_FAILURE_MATRIX.md",
    ),
    "N30": (
        "src/hive_mind_os/whole_os_benchmark.py",
        "src/hive_mind_os/benchmark_adapters.py",
        "tests/test_whole_os_benchmark.py",
        "tests/test_benchmark_adapters.py",
        "docs/benchmarks/whole-os-results-<run-id>.md",
    ),
    "N31": ("docs/execution/SELF_PILOT_RECEIPT.md",),
    "N32": ("docs/execution/EXTERNAL_PILOT_RECEIPT.md",),
    "N33": (
        "docs/execution/WHOLE_OS_ACCEPTANCE.md",
        "USER_GUIDE/08_AUTONOMOUS_REPOSITORY_SERVICE.md",
        "docs/execution/WHOLE_OS_RECOVERY.md",
    ),
}


PUBLICATION = {
    "N15": "code-pr",
    "N21": "lesson-draft",
    "N31": "pilot",
    "N32": "pilot",
    "N33": "release-handoff",
}

ROLE_STAGE = {
    "Orchestrator": "integrate",
    "Explorer": "discover",
    "Architect": "design",
    "Builder": "build",
    "Curator": "validate",
    "Integrator": "integrate",
    "Steward": "maintain",
    "Optimizer": "grow",
}


def _sections(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## (N\d{2}) — .+$", text, re.MULTILINE))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1)] = text[match.start():end].rstrip() + "\n"
    return result


def _acceptance(section: str) -> str:
    match = re.search(r"^\*\*Acceptance(?:[.:])\*\*\s*(.+)$", section, re.MULTILINE)
    if match is None:
        raise ValueError("node contract lacks acceptance")
    return match.group(1).strip()


def _node_contracts() -> dict[str, object]:
    dag = json.loads((HANDOFF / "dag-index.json").read_text(encoding="utf-8"))
    sections: dict[str, tuple[str, str]] = {}
    for filename in (
        "NODES-FOUNDATION.md",
        "NODES-EXECUTION.md",
        "NODES-LEARNING.md",
        "NODES-QUALIFICATION.md",
    ):
        for node_id, body in _sections(HANDOFF / filename).items():
            sections[node_id] = (filename, body)
    nodes = []
    for node in dag["nodes"]:
        node_id = node["id"]
        filename, section = sections[node_id]
        ex_sources = sorted(set(re.findall(r"\bEX\d{2}\b", section)))
        sources = [
            "OWNER-IMPLEMENTATION-01",
            "HANDOFF-01",
            "GOV-AGENTS-01",
            "GOV-DAG-01",
            *ex_sources,
        ]
        if node_id == "N00":
            sources.extend(("OWNER-ORIGINAL-01", "LOCAL-01"))
        if node_id == "N01":
            sources.extend(f"GOV-ADR-{value:03d}" for value in range(74, 79))
        requirement_ids = list(node["requirement_ids"])
        if node_id == "N01":
            requirement_ids.append("R16")
        nodes.append(
            {
                "id": node_id,
                "objective": node["objective"],
                "dependencies": node["dependencies"],
                "owner_role": node["owner_role"],
                "roles": [node["owner_role"].lower()],
                "lifecycle_stages": [ROLE_STAGE[node["owner_role"]]],
                "minimum_route": node["minimum_route_hypothesis"],
                "contract_path": f"docs/plan/whole-os-tournament-2026-09-13/{filename}",
                "contract_section": node_id,
                "contract_digest": raw_sha256(section.encode("utf-8")),
                "requirement_ids": requirement_ids,
                "source_ids": list(dict.fromkeys(sources)),
                "semantic_locks": list(LOCKS[node_id]),
                "write_paths": list(WRITE_PATHS[node_id]),
                "acceptance_criteria": [_acceptance(section)],
                "rollback": [line for line in section.splitlines() if line.strip()][-1],
                "output_contracts": ["node-receipt", *WRITE_PATHS[node_id]],
                "publication_stage": PUBLICATION.get(node_id, "none"),
                "independent_review_required": node["independent_review_required"],
                "completion_rule": node["completion_rule"],
            }
        )
    return {
        "schema": "whole-os-node-contracts/v1",
        "source_inventory": {
            "inventory_id": "WOS-N00-20260914-01",
            "sha256": raw_sha256(
                (OUTPUT / "source-inventory.json").read_bytes()
            ),
        },
        "nodes": nodes,
    }


def main() -> None:
    if len(LOCKS) != 34 or len(WRITE_PATHS) != 34:
        raise ValueError("lock/write-path mappings must cover N00 through N33")
    contracts = _node_contracts()
    contract_bytes = (
        json.dumps(contracts, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    contract_path = OUTPUT / "whole-os-node-contracts-v1.json"
    contract_path.write_bytes(contract_bytes)

    repository_id = raw_sha256(b"https://github.com/kb4beast/hive-mind-os.git")
    subject = SubjectBinding.for_repository(
        RepositorySubject(repository_id, BASE_COMMIT, BASE_TREE, TARGET)
    )
    prompt_bytes = (
        ROOT / "docs/plan/whole-os-tournament-2026-09-13-IMPLEMENTATION_PROMPT.md"
    ).read_bytes()
    request = PlanGenerationRequest(
        raw_sha256(prompt_bytes),
        raw_sha256(b"Implement the accepted N00 through N33 whole-OS successor campaign."),
        subject.subject_id,
        "repository",
        repository_id,
        TARGET,
        BASE_COMMIT,
        BASE_TREE,
        None,
    )
    authority = AuthorityEnvelope(
        "whole-os-inert-local-profile",
        "repository-owner",
        raw_sha256(b"inert local planning profile; not a host grant"),
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
        "2099-01-01T00:00:00Z",
        False,
    )
    evidence = (
        EvidenceReference(
            "whole-os-handoff",
            raw_sha256((HANDOFF / "MANIFEST.json").read_bytes()),
            "docs/plan/whole-os-tournament-2026-09-13/MANIFEST.json",
            tuple(f"R{index:02d}" for index in range(1, 19)),
            "2026-09-14T02:13:05Z",
        ),
        EvidenceReference(
            "accepted-n00-inventory",
            raw_sha256((OUTPUT / "source-inventory.json").read_bytes()),
            "docs/plan/whole-os-implementation/source-inventory.json",
            ("N00-ACCEPTED",),
            "2026-09-14T02:49:00Z",
        ),
    )
    standard = PinnedArtifact.pin(
        "dag-standard-v2", (ROOT / "docs/execution/DAG_AUTHORING_STANDARD_V2.md").read_bytes()
    )
    factory = WholeOSPlanFactory()
    plan = factory.build(
        request,
        standard=standard,
        authority=authority,
        evidence=evidence,
        node_contracts=contracts,
    )
    receipt = compile_plan(
        plan.canonical_bytes(),
        expected_plan_digest=plan.digest(),
        standard_bytes=standard.content,
        expected_request_id=request.request_id,
        expected_subject_id=request.subject_id,
    )
    if receipt.metrics.node_count != 34:
        raise ValueError("compiled successor does not contain all 34 nodes")
    plan_path = OUTPUT / "whole-os-plan-v2.json"
    plan_path.write_bytes(plan.canonical_bytes())

    compiler_bytes = b"\n".join(
        (ROOT / path).read_bytes()
        for path in (
            "src/hive_mind_os/portable_plan.py",
            "src/hive_mind_os/dag_standard.py",
            "src/hive_mind_os/tournament_plan_factory.py",
        )
    )
    source_artifacts = tuple(
        PinnedArtifact.pin(name, (ROOT / path).read_bytes())
        for name, path in (
            ("implementation-prompt", "docs/plan/whole-os-tournament-2026-09-13-IMPLEMENTATION_PROMPT.md"),
            ("handoff-manifest", "docs/plan/whole-os-tournament-2026-09-13/MANIFEST.json"),
            ("n00-inventory", "docs/plan/whole-os-implementation/source-inventory.json"),
            ("node-prompt", "docs/plan/whole-os-implementation/NODE_PROMPT.md"),
        )
    )
    generated, _ = factory.generate(
        request,
        standard=standard,
        authority=authority,
        evidence=evidence,
        node_contracts=contracts,
        node_mappings=PinnedArtifact.pin("whole-os-node-contracts", contract_bytes),
        sources=source_artifacts,
        compiler=PinnedArtifact.pin("whole-os-compiler", compiler_bytes),
    )
    manifest_path = OUTPUT / "generation-manifest.json"
    manifest_path.write_bytes(generated.activation_material.external_manifest_bytes)

    prompt_path = OUTPUT / "NODE_PROMPT.md"
    dispatcher = {
        "schema": "whole-os-dispatcher-entry/v1",
        "status": "INACTIVE",
        "authority_granted": False,
        "host_attestation_required": True,
        "plan_path": "docs/plan/whole-os-implementation/whole-os-plan-v2.json",
        "plan_digest": raw_sha256(plan_path.read_bytes()),
        "generation_manifest_path": "docs/plan/whole-os-implementation/generation-manifest.json",
        "generation_manifest_digest": raw_sha256(manifest_path.read_bytes()),
        "node_contracts_path": "docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json",
        "node_contracts_digest": raw_sha256(contract_path.read_bytes()),
        "node_prompt_path": "docs/plan/whole-os-implementation/NODE_PROMPT.md",
        "node_prompt_digest": raw_sha256(prompt_path.read_bytes()),
        "dispatch_policy": {
            "dependency_ready_only": True,
            "semantic_and_write_locks_required": True,
            "planning_group_is_lock": False,
            "full_handoff_retransmission_forbidden": True,
        },
    }
    (OUTPUT / "DISPATCHER.json").write_text(
        json.dumps(dispatcher, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
