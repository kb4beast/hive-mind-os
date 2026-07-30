from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from hive_mind_os.roles import DEFAULT_LIFECYCLE

from .canonical import canonical_bytes, digest
from .contracts import validate_foundation
from .explorer_contracts import load_explorer_schema
from .explorer_shadow import (
    ACTOR_ID,
    CATEGORIES,
    CRITICAL_CLASSES,
    GENERATED_ORIGINS,
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_RECORDS,
    MAX_FINDINGS,
    MAX_TEXT,
    POLICY_VERSION,
    ExplorerShadowRunner,
    compile_shadow_skills,
)
from .explorer_successor_contracts import validate_explorer_successor
from .generation import (
    GENERATOR_VERSION,
    compile_generation_zero_candidates,
    digest_bytes,
)
from .opportunities import NORMALIZATION_VERSION

BASE_DEFINITION_ID = "hive-agent-definition:explorer:v2-candidate"
BASE_CONTENT_DIGEST = (
    "sha256:cc7a2f06e2e18ef77c6c2146e6037a9942a94c00682aeb2f174c62be32a3a793"
)
BASE_PROJECTION_DIGEST = (
    "sha256:a9c3758f4a64d486c72e389871e4ea06521ea74b46b64969f881d0b05880308a"
)
BASE_PROMPT_DIGEST = (
    "sha256:74415c43cb1e5950e98ef6f046f9db44900abdeeedfe9bd5647da48b070f6aca"
)
EXPECTED_SUCCESSOR_DIGEST = (
    "sha256:0494c32237fbbe83b90444c9b0496646e8f0b27e7c20379320a6bd7241697463"
)

_LENSES = (
    "customer-end-user",
    "workflow-operator",
    "product-strategy",
    "software-engineering",
    "architecture-integration",
    "quality-adversarial-testing",
    "security-privacy-safety",
    "reliability-maintenance-support",
    "accessibility-inclusive-design",
    "research-standards-ecosystem",
    "market-economics-cost",
    "legal-licensing-governance",
    "contrarian-attacker-premortem",
)
_DISCOVERY_MODES = (
    "obvious-defects",
    "repository-history-signals",
    "external-primary-sources",
    "inversion-boundary-counterfactual",
    "second-order-effects",
    "analogy-transfer",
    "testable-concept-combination",
    "serendipity",
    "negative-evidence",
    "customer-value-ranking",
)
_IDEA_LIFECYCLE = (
    "observe",
    "question",
    "investigate",
    "synthesize",
    "search-prior-ideas",
    "classify-relationship",
    "cross-examine",
    "propose",
    "define-falsifiable-test",
    "stop-defer-handoff",
)
_CROSS_DOMAIN_FIELDS = (
    "concepts",
    "causal-mechanism",
    "assumptions",
    "break-point",
    "counterexample",
    "falsifiable-experiment",
    "expected-value",
    "cost-if-wrong",
)
_STOP_CONDITIONS = (
    "research-budget",
    "lens-coverage",
    "source-saturation",
    "duplicate-saturation",
    "diminishing-expected-value",
    "policy-boundary",
    "critical-evidence-unavailable",
    "uncertainty-threshold",
)
_PROHIBITED_ACTIONS = (
    "self-approval",
    "self-promotion",
    "authority-expansion",
    "production-mutation",
    "policy-mutation",
    "package-installation",
    "novelty-as-authorization",
)


def _playbook() -> dict[str, list[str]]:
    return {
        "lenses": list(_LENSES),
        "discovery_modes": list(_DISCOVERY_MODES),
        "idea_lifecycle": list(_IDEA_LIFECYCLE),
        "cross_domain_fields": list(_CROSS_DOMAIN_FIELDS),
        "stop_conditions": list(_STOP_CONDITIONS),
        "prohibited_actions": list(_PROHIBITED_ACTIONS),
    }


def _layer(
    position: int,
    layer_id: str,
    kind: str,
    version: str,
    source_digests: list[str],
) -> dict[str, Any]:
    body = {
        "position": position,
        "layer_id": layer_id,
        "kind": kind,
        "version": version,
        "source_digests": source_digests,
    }
    return {**body, "digest": digest(body)}


def _compile_unpinned() -> dict[str, Any]:
    generated = compile_generation_zero_candidates()
    if set(generated) != {
        "agents/architect.json",
        "agents/builder.json",
        "agents/curator.json",
        "agents/explorer.json",
        "agents/integrator.json",
        "agents/optimizer.json",
        "agents/orchestrator.json",
        "agents/steward.json",
        "manifest.json",
    }:
        raise ValueError("Phase 2 generated candidate set drifted")
    explorer_bytes = generated["agents/explorer.json"]
    explorer = json.loads(explorer_bytes)
    if not validate_foundation("agent-definition-v2", explorer).valid:
        raise ValueError("Phase 2 Explorer projection is contract-invalid")
    if (
        explorer["definition_id"] != BASE_DEFINITION_ID
        or explorer["content_digest"] != BASE_CONTENT_DIGEST
        or explorer["generator_version"] != GENERATOR_VERSION
        or digest_bytes(explorer_bytes) != BASE_PROJECTION_DIGEST
    ):
        raise ValueError("Phase 2 Explorer identity or projection drifted")
    prompt_layers = explorer["prompt_layers"]
    if (
        len(prompt_layers) != 1
        or prompt_layers[0]["layer_id"] != "generation-zero:explorer"
        or prompt_layers[0]["version"] != "1"
        or prompt_layers[0]["digest"] != BASE_PROMPT_DIGEST
    ):
        raise ValueError("Generation Zero Explorer prompt binding drifted")

    playbook = _playbook()
    skills = compile_shadow_skills()
    context_schema_digest = digest(
        load_explorer_schema("explorer-context-selection-v1")
    )
    output_schema_digest = digest(load_explorer_schema("explorer-shadow-run-v1"))
    context_manifest = {
        "contract": "explorer-context-selection-v1",
        "policy_version": POLICY_VERSION,
        "critical_classes": list(CRITICAL_CLASSES),
        "generated_origins": sorted(GENERATED_ORIGINS),
        "whole_records": True,
        "scope": "one-tenant-one-repository",
        "sealed_sequence_cutoff": True,
        "max_context_records": MAX_CONTEXT_RECORDS,
        "max_context_bytes": MAX_CONTEXT_BYTES,
    }
    output_manifest = {
        "contract": "explorer-shadow-run-v1",
        "finding_fields": sorted(ExplorerShadowRunner._FINDING_FIELDS),
        "categories": sorted(CATEGORIES),
        "dispositions": sorted(
            "none" if item is None else item for item in explorer_dispositions()
        ),
        "selected_evidence_only": True,
        "max_findings": MAX_FINDINGS,
        "max_nested_values": 64,
        "max_text": MAX_TEXT,
    }
    admission_manifest = {
        "actor_id": ACTOR_ID,
        "ledger": "OpportunityLedger",
        "normalization_version": NORMALIZATION_VERSION,
        "required_external_action": "foundation.opportunity.write",
        "structured_key_derived_by_runner": True,
        "semantic_auto_merge": False,
        "effective_capabilities": [],
        "tool_interfaces": [],
    }
    lifecycle = [role.value for role in DEFAULT_LIFECYCLE]
    lifecycle_manifest = {
        "workflow_ref": "generation-zero:lifecycle",
        "stages": lifecycle,
    }
    layers = [
        _layer(
            1,
            BASE_DEFINITION_ID,
            "base",
            "2-candidate",
            [BASE_CONTENT_DIGEST, BASE_PROJECTION_DIGEST],
        ),
        _layer(
            2,
            "generation-zero:explorer",
            "prompt",
            "1",
            [BASE_PROMPT_DIGEST],
        ),
        _layer(3, "explorer:playbook", "playbook", "1", [digest(playbook)]),
        _layer(
            4,
            "explorer:skill-bundle",
            "skills",
            "1",
            [
                str(skills["bundle_digest"]),
                *[str(item["digest"]) for item in skills["outputs"]],
            ],
        ),
        _layer(
            5,
            "explorer:context-selection",
            "context",
            "2",
            [context_schema_digest, digest(context_manifest)],
        ),
        _layer(
            6,
            "explorer:shadow-output",
            "output",
            "1",
            [output_schema_digest, digest(output_manifest)],
        ),
        _layer(
            7,
            "explorer:opportunity-admission",
            "admission",
            "1",
            [digest(admission_manifest)],
        ),
        _layer(
            8,
            "generation-zero:lifecycle",
            "lifecycle",
            "1",
            [digest(lifecycle_manifest)],
        ),
    ]
    requested = list(explorer["requested_capabilities"])
    body = {
        "record_type": "explorer-agent-successor",
        "schema_version": 1,
        "agent_id": "hive-agent:explorer:v2-shadow-1",
        "definition_id": "hive-agent-definition:explorer:v2-shadow-1",
        "role_id": "explorer",
        "version": "2-shadow-1",
        "status": "candidate",
        "lineage_relation": "extends-inert",
        "base_definition_ref": BASE_DEFINITION_ID,
        "rollback_ref": BASE_DEFINITION_ID,
        "layers": layers,
        "requested_capabilities": requested,
        "effective_capabilities": [],
        "unsupported_capabilities": requested,
        "tool_refs": [],
        "input_contract_refs": ["explorer-context-selection-v1"],
        "output_contract_refs": ["explorer-shadow-run-v1"],
        "workflow_refs": ["generation-zero:lifecycle"],
        "budgets": {
            "max_context_records": MAX_CONTEXT_RECORDS,
            "max_context_bytes": MAX_CONTEXT_BYTES,
            "max_findings": MAX_FINDINGS,
            "max_nested_values": 64,
            "max_engine_calls": 1,
        },
        "playbook": playbook,
        "governance": {
            "source_refs": [
                "phase1-canonical-contracts",
                "phase4a-explorer-shadow",
                "phase4b-explorer-successor-source-register",
            ],
            "court_refs": ["P2-FOUNDATION-001", "P4A-EXPLORER-SHADOW", "P4B-001"],
            "dissent_ref": "evidence/phase4b/PHASE4B_DISSENT.md",
            "activation_prerequisites": [
                "held-out-behavioral-evaluation",
                "independent-curator",
                "independent-judge",
            ],
        },
        "activation": "inert",
        "authority": "none",
        "public": False,
    }
    candidate = {**body, "content_digest": digest(body)}
    validation = validate_explorer_successor(candidate)
    if not validation.valid:
        raise ValueError(
            "Explorer successor failed its contract: "
            + "; ".join(validation.issues)
        )
    return candidate


def explorer_dispositions() -> frozenset[str | None]:
    from .explorer_shadow import DISPOSITIONS

    return DISPOSITIONS


def compile_explorer_successor() -> dict[str, Any]:
    candidate = _compile_unpinned()
    if candidate["content_digest"] != EXPECTED_SUCCESSOR_DIGEST:
        raise ValueError("Explorer successor differs from its reviewed digest")
    return deepcopy(candidate)


def explorer_successor_bytes() -> bytes:
    return canonical_bytes(compile_explorer_successor())
