from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .canonical import digest
from .optimizer_playbook_contracts import (
    ACCEPTED_BASE_COMMIT,
    AGENT_ID,
    BASE_DEFINITION_ID,
    CHALLENGER_ID,
    CHAMPION_ID,
    COMPARATOR_IDS,
    DEFINITION_ID,
    ENVELOPE_SCHEMA,
    EVALUATION_DIMENSIONS,
    OPEN_DEBT_IDS,
    OUTPUT_FIELDS,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    RESOLVED_DEBT_IDS,
    TENANT_ID,
    validate_optimizer,
    validate_optimizer_request,
)


def example_optimizer_request() -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5g-optimizer-intake-001",
        "tenant_id": TENANT_ID,
        "repository_id": REPOSITORY_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "steward_envelope_digest": "sha256:" + ("3" * 64),
        "open_debt_ids": list(OPEN_DEBT_IDS),
        "resolved_debt_ids": list(RESOLVED_DEBT_IDS),
        "champion_id": CHAMPION_ID,
        "challenger_id": CHALLENGER_ID,
        "holdout_manifest_digest": "sha256:" + ("4" * 64),
        "requested_next_stage": "promotion-court",
        "authority": "none",
        "activation": "inert",
    }


def _baseline_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5g-baseline-snapshot/v1",
        "request_id": request["request_id"],
        "repository_id": request["repository_id"],
        "tenant_id": request["tenant_id"],
        "accepted_base_commit": request["subject_commit"],
        "subject_tree": request["subject_tree"],
        "steward_envelope_digest": request["steward_envelope_digest"],
        "champion_id": request["champion_id"],
        "health_status": "degraded",
        "evidence_status": "incomplete",
        "open_debt_ids": list(request["open_debt_ids"]),
        "resolved_debt_ids": list(request["resolved_debt_ids"]),
        "release_recommendation": "defer",
        "authority": "none",
        "activation": "inert",
    }


def _challenger_plan(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5g-challenger-plan/v1",
        "request_id": request["request_id"],
        "champion_id": request["champion_id"],
        "challenger_id": request["challenger_id"],
        "status": "proposed",
        "execution_status": "not-run",
        "champion_mutation_authorized": False,
        "skill_change_authorized": False,
        "rollback_ref": "rollback:champion-unchanged",
        "evidence_preservation_required": True,
    }


def _evaluation_plan(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5g-evaluation-plan/v1",
        "request_id": request["request_id"],
        "challenger_id": request["challenger_id"],
        "comparator_ids": list(COMPARATOR_IDS),
        "dimensions": list(EVALUATION_DIMENSIONS),
        "holdout_manifest_digest": request["holdout_manifest_digest"],
        "holdout_exposure_status": "sealed-not-accessed",
        "execution_status": "not-run",
        "outcome_evidence_status": "not-evaluated",
        "regression_budget_status": "not-evaluated",
        "superiority_claim": "prohibited",
        "losing_results_preserved": True,
    }


def _promotion_handoff(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5g-promotion-handoff/v1",
        "request_id": request["request_id"],
        "challenger_id": request["challenger_id"],
        "requested_stage": "promotion-court",
        "status": "blocked",
        "eligible": False,
        "blockers": list(request["open_debt_ids"]),
        "independent_court_required": True,
        "promotion_authorized": False,
        "self_promotion_authorized": False,
        "release_authorized": False,
        "recommendation": "defer",
        "losing_results_preserved": True,
    }


def compile_optimizer_intake(request: Mapping[str, Any]) -> dict[str, Any]:
    validate_optimizer_request(request)
    request_copy = deepcopy(dict(request))
    outputs = {
        "baseline_snapshot": _baseline_snapshot(request_copy),
        "challenger_plan": _challenger_plan(request_copy),
        "evaluation_plan": _evaluation_plan(request_copy),
        "promotion_handoff": _promotion_handoff(request_copy),
    }
    output_digests = {field: digest(outputs[field]) for field in OUTPUT_FIELDS}
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "agent_id": AGENT_ID,
        "definition_id": DEFINITION_ID,
        "base_definition_id": BASE_DEFINITION_ID,
        "request": request_copy,
        "outputs": outputs,
        "output_digests": output_digests,
        "authority": "none",
        "activation": "inert",
    }
    envelope["envelope_digest"] = digest(envelope)
    validate_optimizer(envelope)
    return deepcopy(envelope)
