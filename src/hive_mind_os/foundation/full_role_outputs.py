from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Callable

from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.full_role_output_contracts import (
    CLAIM_FIELDS,
    OUTPUT_FIELDS_BY_ROLE,
    STATUS_BY_ROLE_FIELD,
    validate_full_role_envelope,
)
from hive_mind_os.foundation.integrator_playbook import (
    compile_integrator_intake,
    example_integrator_request,
)
from hive_mind_os.foundation.integrator_playbook_contracts import validate_integrator
from hive_mind_os.foundation.optimizer_playbook import (
    compile_optimizer_intake,
    example_optimizer_request,
)
from hive_mind_os.foundation.optimizer_playbook_contracts import validate_optimizer
from hive_mind_os.foundation.steward_playbook import (
    compile_steward_intake,
    example_steward_request,
)
from hive_mind_os.foundation.steward_playbook_contracts import validate_steward

AUTHORITY = {
    "authority": "none",
    "execution_authorized": False,
    "release_authorized": False,
}

PAYLOADS: dict[str, dict[str, dict[str, Any]]] = {
    "integrator": {
        "contract_inventory": {
            "contract_families": [
                "model",
                "tool",
                "storage",
                "scheduler",
                "git",
                "research",
                "courtroom",
                "ui",
            ],
            "unknown_contracts": [],
        },
        "dependency_graph": {
            "nodes": ["curator", "integrator", "steward"],
            "edges": [["curator", "integrator"], ["integrator", "steward"]],
            "cycles": [],
        },
        "data_lineage": {
            "inputs": ["curator-envelope", "source-register", "debt-register"],
            "outputs": ["integration-envelope"],
            "external_flows": [],
        },
        "adapter_replacement_analysis": {
            "adapters": [
                "model",
                "provider",
                "tool",
                "storage",
                "scheduler",
                "git",
                "research",
                "courtroom",
                "benchmark",
                "ui",
                "sandbox",
            ],
            "checks_executed": False,
        },
        "migration_ordering": {
            "steps": [
                "freeze-old",
                "add-v1",
                "reproduce",
                "independent-verify",
                "migrate-consumers",
            ],
            "executed_steps": [],
        },
        "rollback_mapping": {
            "strategy": "revert-additive-version",
            "evidence_preserved": True,
            "rollback_executed": False,
        },
        "integration_receipt": {
            "compatibility_checks": [],
            "side_effect_receipts": [],
            "release_recommendation": "defer",
        },
    },
    "steward": {
        "reliability_assessment": {
            "health": "degraded",
            "unknowns": ["external-runtime", "windows-hard-isolation"],
        },
        "observability_inventory": {
            "signals": ["scheduler-ledger", "sandbox-receipts", "ci-runs"],
            "external_signals": [],
        },
        "dependency_health": {
            "checks": [],
            "critical_unknowns": ["provider", "deployment"],
        },
        "operational_runbook": {
            "path": "docs/operations/PHASE5F_STEWARD_RUNBOOK.md",
            "executed": False,
        },
        "interruption_recovery": {
            "exercise": "phase5f-recovery-exercise-template-v1",
            "executed": False,
            "known_blockers": ["B-OPS-08"],
        },
        "evidence_integrity": {
            "append_only": True,
            "failed_receipts_preserved": True,
            "external_retention": "missing",
        },
        "maintenance_schedule": {
            "windows": [],
            "dependency_mutation_authorized": False,
        },
    },
    "optimizer": {
        "outcome_metrics": {
            "metrics": [
                "verified-customer-value",
                "safety-regression",
                "resource-cost",
            ],
            "observations": [],
        },
        "experiment_design": {
            "challenger_versioned": True,
            "holdout": "sealed-not-accessed",
            "executed": False,
        },
        "resource_budget": {
            "authorized": False,
            "token": None,
            "money": None,
            "time": None,
        },
        "comparator_results": {"comparators": [], "results": []},
        "regression_results": {"budgets": [], "results": []},
        "experiment_receipts": {"successful": [], "losing": [], "failed": []},
        "improvement_proposals": {"proposals": [], "learning_claimed": False},
        "rollback_exercise": {
            "executed": False,
            "champion_mutated": False,
            "rollback_verified": False,
        },
    },
}


def _clone(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _compile(
    role: str, intake: Mapping[str, Any], validator: Callable[[Mapping[str, Any]], None]
) -> dict[str, Any]:
    source = _clone(intake)
    validator(source)
    request = source.get("request_snapshot", source.get("request"))
    if type(request) is not dict:
        raise ValueError("source intake has no exact request scope")
    scope_digest = digest(request)
    outputs: dict[str, Any] = {}
    for field in OUTPUT_FIELDS_BY_ROLE[role]:
        outputs[field] = {
            "schema_version": f"phase5p-{role}-{field.replace('_', '-')}/v1",
            "output_id": f"phase5p:{role}:{field}:{scope_digest}",
            "scope_digest": scope_digest,
            "status": STATUS_BY_ROLE_FIELD[role][field],
            "evidence_requirements": [
                "exact-subject",
                "independent-reproduction",
                "authority-receipt",
            ],
            "payload": _clone(PAYLOADS[role][field]),
            "authority": dict(AUTHORITY),
        }
    body = {
        "schema_version": f"phase5p-{role}-full-output-envelope/v1",
        "role": role,
        "source_intake": source,
        "source_intake_digest": digest(source),
        "scope_digest": scope_digest,
        "outputs": outputs,
        "output_digests": {
            field: digest(outputs[field]) for field in OUTPUT_FIELDS_BY_ROLE[role]
        },
        "claims": {field: False for field in CLAIM_FIELDS},
    }
    envelope = {**body, "envelope_digest": digest(body)}
    validate_full_role_envelope(envelope)
    return envelope


def compile_integrator_full_outputs(
    intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = (
        intake
        if intake is not None
        else compile_integrator_intake(example_integrator_request())
    )
    return _compile("integrator", source, validate_integrator)


def compile_steward_full_outputs(
    intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = (
        intake
        if intake is not None
        else compile_steward_intake(example_steward_request())
    )
    return _compile("steward", source, validate_steward)


def compile_optimizer_full_outputs(
    intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = (
        intake
        if intake is not None
        else compile_optimizer_intake(example_optimizer_request())
    )
    return _compile("optimizer", source, validate_optimizer)
