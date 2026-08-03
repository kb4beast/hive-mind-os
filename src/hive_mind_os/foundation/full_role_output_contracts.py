from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hive_mind_os.foundation.canonical import digest

OUTPUT_FIELDS_BY_ROLE = {
    "integrator": (
        "contract_inventory",
        "dependency_graph",
        "data_lineage",
        "adapter_replacement_analysis",
        "migration_ordering",
        "rollback_mapping",
        "integration_receipt",
    ),
    "steward": (
        "reliability_assessment",
        "observability_inventory",
        "dependency_health",
        "operational_runbook",
        "interruption_recovery",
        "evidence_integrity",
        "maintenance_schedule",
    ),
    "optimizer": (
        "outcome_metrics",
        "experiment_design",
        "resource_budget",
        "comparator_results",
        "regression_results",
        "experiment_receipts",
        "improvement_proposals",
        "rollback_exercise",
    ),
}

STATUS_BY_ROLE_FIELD = {
    "integrator": {
        "contract_inventory": "structural-complete",
        "dependency_graph": "structural-complete",
        "data_lineage": "structural-complete",
        "adapter_replacement_analysis": "not-run",
        "migration_ordering": "proposed",
        "rollback_mapping": "proposed",
        "integration_receipt": "not-run",
    },
    "steward": {
        "reliability_assessment": "degraded-unknowns",
        "observability_inventory": "structural-complete",
        "dependency_health": "not-run",
        "operational_runbook": "defined-not-executed",
        "interruption_recovery": "not-run",
        "evidence_integrity": "structural-complete",
        "maintenance_schedule": "proposed",
    },
    "optimizer": {
        "outcome_metrics": "defined-no-observations",
        "experiment_design": "proposed",
        "resource_budget": "not-authorized",
        "comparator_results": "not-run",
        "regression_results": "not-run",
        "experiment_receipts": "empty-no-experiments",
        "improvement_proposals": "none-without-results",
        "rollback_exercise": "not-run",
    },
}

CLAIM_FIELDS = (
    "execution_performed",
    "authenticated_independence",
    "release_ready",
    "production_ready",
    "deployment_authorized",
    "learning_established",
    "promotion_authorized",
    "superiority_established",
)


def _exact_dict(value: object, fields: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{where} must be an exact dict")
    result: dict[str, Any] = value
    if set(result) != fields:
        raise ValueError(f"{where} fields drifted")
    return result


def validate_full_role_envelope(value: Mapping[str, Any]) -> None:
    envelope = _exact_dict(
        value,
        {
            "schema_version",
            "role",
            "source_intake",
            "source_intake_digest",
            "scope_digest",
            "outputs",
            "output_digests",
            "claims",
            "envelope_digest",
        },
        "envelope",
    )
    role = envelope["role"]
    if role not in OUTPUT_FIELDS_BY_ROLE:
        raise ValueError("unknown full-output role")
    if envelope["schema_version"] != f"phase5p-{role}-full-output-envelope/v1":
        raise ValueError("envelope schema version drifted")
    source_value = envelope["source_intake"]
    if type(source_value) is not dict:
        raise ValueError("source_intake must be an exact dict")
    source: dict[str, Any] = source_value
    if envelope["source_intake_digest"] != digest(source):
        raise ValueError("source intake digest drifted")
    request = source.get("request_snapshot", source.get("request"))
    if type(request) is not dict:
        raise ValueError("source intake has no exact request scope")
    if envelope["scope_digest"] != digest(request):
        raise ValueError("scope digest drifted")
    outputs = _exact_dict(
        envelope["outputs"], set(OUTPUT_FIELDS_BY_ROLE[role]), "outputs"
    )
    output_digests = _exact_dict(
        envelope["output_digests"], set(OUTPUT_FIELDS_BY_ROLE[role]), "output_digests"
    )
    for field in OUTPUT_FIELDS_BY_ROLE[role]:
        output = _exact_dict(
            outputs[field],
            {
                "schema_version",
                "output_id",
                "scope_digest",
                "status",
                "evidence_requirements",
                "payload",
                "authority",
            },
            f"outputs.{field}",
        )
        if output["schema_version"] != f"phase5p-{role}-{field.replace('_', '-')}/v1":
            raise ValueError(f"{field} schema version drifted")
        if output["output_id"] != f"phase5p:{role}:{field}:{envelope['scope_digest']}":
            raise ValueError(f"{field} output id drifted")
        if output["scope_digest"] != envelope["scope_digest"]:
            raise ValueError(f"{field} scope drifted")
        if output["status"] != STATUS_BY_ROLE_FIELD[role][field]:
            raise ValueError(f"{field} status escalated")
        requirements = output["evidence_requirements"]
        if type(requirements) is not list or not requirements:
            raise ValueError(f"{field} evidence requirements are incomplete")
        if any(type(item) is not str or not item for item in requirements):
            raise ValueError(f"{field} evidence requirement is invalid")
        if type(output["payload"]) is not dict or not output["payload"]:
            raise ValueError(f"{field} payload is incomplete")
        authority = _exact_dict(
            output["authority"],
            {"authority", "execution_authorized", "release_authorized"},
            f"outputs.{field}.authority",
        )
        if authority != {
            "authority": "none",
            "execution_authorized": False,
            "release_authorized": False,
        }:
            raise ValueError(f"{field} authority escalated")
        if output_digests[field] != digest(output):
            raise ValueError(f"{field} digest drifted")
    claims = _exact_dict(envelope["claims"], set(CLAIM_FIELDS), "claims")
    if any(claims[field] is not False for field in CLAIM_FIELDS):
        raise ValueError("full-output claim escalated")
    body = {key: item for key, item in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != digest(body):
        raise ValueError("full-output envelope digest drifted")
