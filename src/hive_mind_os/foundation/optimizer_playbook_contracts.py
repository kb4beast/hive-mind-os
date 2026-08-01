from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

AGENT_ID = "hive-agent:optimizer:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:optimizer:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:optimizer:v2-candidate"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "eebda921352271c7d534009fe5ac8ba2306a2410"
CHAMPION_ID = "champion:phase5a-5f-integration"
CHALLENGER_ID = "challenger:phase5g-optimizer-shadow-1"

REQUEST_SCHEMA = "phase5g-optimizer-request/v1"
ENVELOPE_SCHEMA = "phase5g-optimizer-intake/v1"
OUTPUT_FIELDS = (
    "baseline_snapshot",
    "challenger_plan",
    "evaluation_plan",
    "promotion_handoff",
)
OPEN_DEBT_IDS = (
    "P5D-DEBT-01",
    "P5D-DEBT-02",
    "P5D-DEBT-04",
    "P5D-DEBT-05",
    "P5E-DEBT-01",
    "P5E-DEBT-02",
    "P5E-DEBT-03",
    "P5E-DEBT-04",
    "P5E-DEBT-05",
    "P5F-DEBT-01",
    "P5F-DEBT-02",
    "P5F-DEBT-03",
    "P5F-DEBT-04",
    "P5F-DEBT-05",
)
RESOLVED_DEBT_IDS = ("P5D-DEBT-03",)
COMPARATOR_IDS = (
    CHAMPION_ID,
    "baseline:deterministic-offline",
    "control:no-change",
)
EVALUATION_DIMENSIONS = (
    "customer-outcome",
    "safety",
    "regression",
    "cost",
    "latency",
    "authority",
    "rollback",
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class OptimizerContractError(ValueError):
    pass


def _require_exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise OptimizerContractError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _require_exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise OptimizerContractError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _require_fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise OptimizerContractError(
            f"{label} fields differ: missing={missing}, extra={extra}"
        )


def _require_text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise OptimizerContractError(f"{label} must be a string")
    text = cast(str, value)
    if not text or text != text.strip() or len(text) > maximum:
        raise OptimizerContractError(f"{label} must be non-empty, trimmed, and bounded")
    return text


def _require_identifier(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(text) is None:
        raise OptimizerContractError(f"{label} is not a valid identifier")
    return text


def _require_digest(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=71)
    if _SHA256.fullmatch(text) is None:
        raise OptimizerContractError(f"{label} is not a canonical SHA-256 digest")
    return text


def _require_git_object(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(text) is None:
        raise OptimizerContractError(f"{label} is not a full Git object ID")
    return text


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise OptimizerContractError(f"{label} must be a boolean")
    return cast(bool, value)


def _require_text_list(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = 128,
) -> list[str]:
    items = _require_exact_list(value, label)
    if len(items) < minimum or len(items) > maximum:
        raise OptimizerContractError(f"{label} has an invalid item count")
    result = [_require_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise OptimizerContractError(f"{label} contains duplicate values")
    return result


def validate_optimizer_request(value: Mapping[str, Any]) -> None:
    request = _require_exact_dict(value, "request")
    _require_fields(
        request,
        {
            "schema_version",
            "request_id",
            "tenant_id",
            "repository_id",
            "subject_commit",
            "subject_tree",
            "steward_envelope_digest",
            "open_debt_ids",
            "resolved_debt_ids",
            "champion_id",
            "challenger_id",
            "holdout_manifest_digest",
            "requested_next_stage",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise OptimizerContractError("unsupported Optimizer request schema")
    _require_identifier(request["request_id"], "request.request_id")
    if request["tenant_id"] != TENANT_ID:
        raise OptimizerContractError("request tenant is outside the fixed Phase 5G scope")
    if request["repository_id"] != REPOSITORY_ID:
        raise OptimizerContractError("request repository is outside the fixed Phase 5G scope")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise OptimizerContractError("request commit is not the accepted Phase 5A-5F merge")
    _require_git_object(request["subject_commit"], "request.subject_commit")
    _require_git_object(request["subject_tree"], "request.subject_tree")
    _require_digest(request["steward_envelope_digest"], "request.steward_envelope_digest")
    open_debt = _require_text_list(request["open_debt_ids"], "request.open_debt_ids")
    if tuple(open_debt) != OPEN_DEBT_IDS:
        raise OptimizerContractError("open debt IDs or order differ from the plan")
    resolved_debt = _require_text_list(
        request["resolved_debt_ids"], "request.resolved_debt_ids"
    )
    if tuple(resolved_debt) != RESOLVED_DEBT_IDS:
        raise OptimizerContractError("resolved debt IDs or order differ from the plan")
    if request["champion_id"] != CHAMPION_ID:
        raise OptimizerContractError("request champion differs from the fixed Phase 5G champion")
    if request["challenger_id"] != CHALLENGER_ID:
        raise OptimizerContractError("request challenger differs from the fixed Phase 5G challenger")
    if request["champion_id"] == request["challenger_id"]:
        raise OptimizerContractError("challenger must be distinct from champion")
    _require_digest(request["holdout_manifest_digest"], "request.holdout_manifest_digest")
    if request["requested_next_stage"] != "promotion-court":
        raise OptimizerContractError("the only admitted next stage is promotion court")
    if request["authority"] != "none" or request["activation"] != "inert":
        raise OptimizerContractError("Optimizer request cannot grant authority or activation")


def _validate_baseline_snapshot(output: Any, request: dict[str, Any]) -> None:
    snapshot = _require_exact_dict(output, "outputs.baseline_snapshot")
    _require_fields(
        snapshot,
        {
            "schema_version",
            "request_id",
            "repository_id",
            "tenant_id",
            "accepted_base_commit",
            "subject_tree",
            "steward_envelope_digest",
            "champion_id",
            "health_status",
            "evidence_status",
            "open_debt_ids",
            "resolved_debt_ids",
            "release_recommendation",
            "authority",
            "activation",
        },
        "outputs.baseline_snapshot",
    )
    if snapshot["schema_version"] != "phase5g-baseline-snapshot/v1":
        raise OptimizerContractError("invalid baseline-snapshot schema")
    expected = {
        "request_id": request["request_id"],
        "repository_id": request["repository_id"],
        "tenant_id": request["tenant_id"],
        "accepted_base_commit": request["subject_commit"],
        "subject_tree": request["subject_tree"],
        "steward_envelope_digest": request["steward_envelope_digest"],
        "champion_id": request["champion_id"],
        "health_status": "degraded",
        "evidence_status": "incomplete",
        "release_recommendation": "defer",
        "authority": "none",
        "activation": "inert",
    }
    for key, expected_value in expected.items():
        if snapshot[key] != expected_value:
            raise OptimizerContractError(f"baseline snapshot drifted at {key}")
    if tuple(_require_text_list(snapshot["open_debt_ids"], "baseline.open_debt_ids")) != OPEN_DEBT_IDS:
        raise OptimizerContractError("baseline open debt differs from the plan")
    if tuple(
        _require_text_list(snapshot["resolved_debt_ids"], "baseline.resolved_debt_ids")
    ) != RESOLVED_DEBT_IDS:
        raise OptimizerContractError("baseline resolved debt differs from the plan")


def _validate_challenger_plan(output: Any, request: dict[str, Any]) -> None:
    plan = _require_exact_dict(output, "outputs.challenger_plan")
    _require_fields(
        plan,
        {
            "schema_version",
            "request_id",
            "champion_id",
            "challenger_id",
            "status",
            "execution_status",
            "champion_mutation_authorized",
            "skill_change_authorized",
            "rollback_ref",
            "evidence_preservation_required",
        },
        "outputs.challenger_plan",
    )
    if plan["schema_version"] != "phase5g-challenger-plan/v1":
        raise OptimizerContractError("invalid challenger-plan schema")
    if plan["request_id"] != request["request_id"]:
        raise OptimizerContractError("challenger plan request binding drifted")
    if plan["champion_id"] != CHAMPION_ID or plan["challenger_id"] != CHALLENGER_ID:
        raise OptimizerContractError("champion or challenger identity drifted")
    if plan["status"] != "proposed" or plan["execution_status"] != "not-run":
        raise OptimizerContractError("challenger plan cannot claim execution")
    if _require_bool(
        plan["champion_mutation_authorized"], "challenger.champion_mutation_authorized"
    ):
        raise OptimizerContractError("champion mutation must remain prohibited")
    if _require_bool(plan["skill_change_authorized"], "challenger.skill_change_authorized"):
        raise OptimizerContractError("skill change must remain unauthorized")
    if plan["rollback_ref"] != "rollback:champion-unchanged":
        raise OptimizerContractError("challenger rollback reference drifted")
    if not _require_bool(
        plan["evidence_preservation_required"], "challenger.evidence_preservation_required"
    ):
        raise OptimizerContractError("challenger must preserve all evidence")


def _validate_evaluation_plan(output: Any, request: dict[str, Any]) -> None:
    plan = _require_exact_dict(output, "outputs.evaluation_plan")
    _require_fields(
        plan,
        {
            "schema_version",
            "request_id",
            "challenger_id",
            "comparator_ids",
            "dimensions",
            "holdout_manifest_digest",
            "holdout_exposure_status",
            "execution_status",
            "outcome_evidence_status",
            "regression_budget_status",
            "superiority_claim",
            "losing_results_preserved",
        },
        "outputs.evaluation_plan",
    )
    if plan["schema_version"] != "phase5g-evaluation-plan/v1":
        raise OptimizerContractError("invalid evaluation-plan schema")
    if plan["request_id"] != request["request_id"] or plan["challenger_id"] != CHALLENGER_ID:
        raise OptimizerContractError("evaluation plan identity drifted")
    if tuple(_require_text_list(plan["comparator_ids"], "evaluation.comparator_ids")) != COMPARATOR_IDS:
        raise OptimizerContractError("evaluation comparators differ from the contract")
    if tuple(_require_text_list(plan["dimensions"], "evaluation.dimensions")) != EVALUATION_DIMENSIONS:
        raise OptimizerContractError("evaluation dimensions differ from the contract")
    if plan["holdout_manifest_digest"] != request["holdout_manifest_digest"]:
        raise OptimizerContractError("holdout manifest binding drifted")
    if plan["holdout_exposure_status"] != "sealed-not-accessed":
        raise OptimizerContractError("protected holdout must remain sealed and unaccessed")
    if plan["execution_status"] != "not-run":
        raise OptimizerContractError("evaluation plan cannot claim execution")
    if plan["outcome_evidence_status"] != "not-evaluated":
        raise OptimizerContractError("outcome evidence cannot be claimed before evaluation")
    if plan["regression_budget_status"] != "not-evaluated":
        raise OptimizerContractError("regression budget cannot be claimed before evaluation")
    if plan["superiority_claim"] != "prohibited":
        raise OptimizerContractError("superiority claim must remain prohibited")
    if not _require_bool(
        plan["losing_results_preserved"], "evaluation.losing_results_preserved"
    ):
        raise OptimizerContractError("losing results must be preserved")


def _validate_promotion_handoff(output: Any, request: dict[str, Any]) -> None:
    handoff = _require_exact_dict(output, "outputs.promotion_handoff")
    _require_fields(
        handoff,
        {
            "schema_version",
            "request_id",
            "challenger_id",
            "requested_stage",
            "status",
            "eligible",
            "blockers",
            "independent_court_required",
            "promotion_authorized",
            "self_promotion_authorized",
            "release_authorized",
            "recommendation",
            "losing_results_preserved",
        },
        "outputs.promotion_handoff",
    )
    if handoff["schema_version"] != "phase5g-promotion-handoff/v1":
        raise OptimizerContractError("invalid promotion-handoff schema")
    if handoff["request_id"] != request["request_id"] or handoff["challenger_id"] != CHALLENGER_ID:
        raise OptimizerContractError("promotion handoff identity drifted")
    if handoff["requested_stage"] != "promotion-court" or handoff["status"] != "blocked":
        raise OptimizerContractError("promotion court handoff must remain blocked")
    if _require_bool(handoff["eligible"], "promotion.eligible"):
        raise OptimizerContractError("challenger cannot be eligible while debt remains open")
    if tuple(_require_text_list(handoff["blockers"], "promotion.blockers")) != OPEN_DEBT_IDS:
        raise OptimizerContractError("promotion blockers differ from the plan")
    if not _require_bool(
        handoff["independent_court_required"], "promotion.independent_court_required"
    ):
        raise OptimizerContractError("independent promotion court must remain required")
    for field in (
        "promotion_authorized",
        "self_promotion_authorized",
        "release_authorized",
    ):
        if _require_bool(handoff[field], f"promotion.{field}"):
            raise OptimizerContractError(f"{field} must remain false")
    if handoff["recommendation"] != "defer":
        raise OptimizerContractError("promotion recommendation must remain defer")
    if not _require_bool(
        handoff["losing_results_preserved"], "promotion.losing_results_preserved"
    ):
        raise OptimizerContractError("promotion court must preserve losing results")


def validate_optimizer(value: Mapping[str, Any]) -> None:
    envelope = _require_exact_dict(value, "envelope")
    _require_fields(
        envelope,
        {
            "schema_version",
            "agent_id",
            "definition_id",
            "base_definition_id",
            "request",
            "outputs",
            "output_digests",
            "authority",
            "activation",
            "envelope_digest",
        },
        "envelope",
    )
    reject_private_content(envelope)
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise OptimizerContractError("unsupported Optimizer envelope schema")
    if envelope["agent_id"] != AGENT_ID or envelope["definition_id"] != DEFINITION_ID:
        raise OptimizerContractError("Optimizer candidate identity drifted")
    if envelope["base_definition_id"] != BASE_DEFINITION_ID:
        raise OptimizerContractError("Optimizer base definition drifted")
    if envelope["authority"] != "none" or envelope["activation"] != "inert":
        raise OptimizerContractError("Optimizer envelope cannot grant authority or activation")

    request = _require_exact_dict(envelope["request"], "envelope.request")
    validate_optimizer_request(request)
    outputs = _require_exact_dict(envelope["outputs"], "envelope.outputs")
    _require_fields(outputs, set(OUTPUT_FIELDS), "envelope.outputs")
    output_digests = _require_exact_dict(
        envelope["output_digests"], "envelope.output_digests"
    )
    _require_fields(output_digests, set(OUTPUT_FIELDS), "envelope.output_digests")

    _validate_baseline_snapshot(outputs["baseline_snapshot"], request)
    _validate_challenger_plan(outputs["challenger_plan"], request)
    _validate_evaluation_plan(outputs["evaluation_plan"], request)
    _validate_promotion_handoff(outputs["promotion_handoff"], request)

    for field in OUTPUT_FIELDS:
        _require_digest(output_digests[field], f"output_digests.{field}")
        if output_digests[field] != digest(outputs[field]):
            raise OptimizerContractError(f"output digest mismatch for {field}")

    _require_digest(envelope["envelope_digest"], "envelope.envelope_digest")
    body = {key: item for key, item in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != digest(body):
        raise OptimizerContractError("Optimizer envelope digest mismatch")
