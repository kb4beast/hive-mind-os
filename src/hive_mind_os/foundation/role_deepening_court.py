from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .canonical import digest
from .role_deepening_court_contracts import (
    ACCEPTED_BASE_COMMIT,
    ACTIVE_DEBT_IDS,
    CONFLICT_IDS,
    COURT_ID,
    ENVELOPE_SCHEMA,
    EVIDENCE_CATEGORIES,
    OUTPUT_FIELDS,
    REOPENED_DEBT_IDS,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    ROLE_SEQUENCE,
    TENANT_ID,
    validate_consolidation_request,
    validate_role_deepening_court,
)

_ROLE_EVIDENCE = {
    "explorer": ["phase:4", "role:explorer", "evidence:phase4"],
    "orchestrator": ["phase:5a", "role:orchestrator", "pr:49"],
    "architect": ["phase:5b", "role:architect", "evidence:phase5b"],
    "builder": ["phase:5c", "role:builder", "pr:53"],
    "curator": ["phase:5d", "role:curator", "pr:54"],
    "integrator": ["phase:5e", "role:integrator", "pr:55"],
    "steward": ["phase:5f", "role:steward", "pr:56"],
    "optimizer": ["phase:5g", "role:optimizer", "pr:57"],
}

_EVIDENCE_STATUS = {
    "role-contracts": "partial",
    "focused-tests": "partial",
    "cross-version-tests": "partial",
    "static-validation": "blocked",
    "type-validation": "blocked",
    "installed-wheel-verification": "partial",
    "external-retention": "missing",
    "authenticated-independence": "missing",
    "operational-recovery": "missing",
    "held-out-evaluation": "missing",
}

_EVIDENCE_REFS = {
    "role-contracts": ["docs:phase4-phase5g", "plan:phase5-carried-forward-debt"],
    "focused-tests": ["run:30661841213", "run:30674699706"],
    "cross-version-tests": ["run:30674773848", "run:30680063488"],
    "static-validation": ["run:30680063488", "debt:P5D-DEBT-01"],
    "type-validation": ["run:30661841213", "debt:P5D-DEBT-02"],
    "installed-wheel-verification": ["run:30680063488", "through:phase5d"],
    "external-retention": ["debt:P5G-DEBT-03", "blocker:B-GOV-04"],
    "authenticated-independence": ["debt:P5G-DEBT-05", "blocker:B-GOV-02"],
    "operational-recovery": ["debt:P5F-DEBT-03", "status:not-executed"],
    "held-out-evaluation": ["debt:P5G-DEBT-01", "status:sealed-not-accessed"],
}

_CONFLICT_EXIT = {
    "active-debt": "Satisfy each exact debt exit condition with retained receipts.",
    "static-type-gate": "Pass Ruff and global Pyright on one exact combined head.",
    "temporary-workflows": "Remove the three Phase 5D temporary workflows and pass governance checks.",
    "worker-determinism": "Find the worker-sweep root cause and repeat cross-version hosted passes.",
    "inventory-packaging-gap": "Chain Phase 5E through Phase 5H inventory and installed-wheel receipts.",
    "external-evidence-gap": "Retain and recover evidence through an external append-only boundary.",
    "independence-gap": "Obtain authenticated distinct reviewer and judge identities.",
    "p20-prerequisites": "Complete and adopt P14-P20 prerequisites, including P18 and P19.",
}


def _debt_evidence(debt_id: str) -> list[str]:
    references = [f"plan:{debt_id}", "plan:PHASE5_CARRIED_FORWARD_DEBT"]
    if debt_id == "P5D-DEBT-03":
        references.extend(["run:30679862330", "run:30680063488"])
    elif debt_id.startswith("P5D"):
        references.append("run:30661841213")
    elif debt_id.startswith("P5E"):
        references.append("pr:55")
    elif debt_id.startswith("P5F"):
        references.append("pr:56")
    else:
        references.append("pr:57")
    return references


def example_consolidation_request() -> dict[str, Any]:
    roles = [
        {
            "phase_id": phase_id,
            "role_id": role_id,
            "status": "bounded-candidate",
            "authority": "none",
            "activation": "inert",
            "release_eligible": False,
            "evidence_refs": list(_ROLE_EVIDENCE[role_id]),
        }
        for phase_id, role_id in ROLE_SEQUENCE
    ]
    debts = [
        {
            "debt_id": debt_id,
            "status": "reopened" if debt_id in REOPENED_DEBT_IDS else "open",
            "evidence_refs": _debt_evidence(debt_id),
            "exit_condition": f"Satisfy the recorded exit condition for {debt_id} with exact receipts.",
        }
        for debt_id in ACTIVE_DEBT_IDS
    ]
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5h-role-deepening-court-001",
        "court_id": COURT_ID,
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "role_entries": roles,
        "debt_items": debts,
        "source_index_digest": "sha256:" + ("2" * 64),
        "authority": "none",
        "activation": "inert",
    }


def _role_inventory(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5h-role-inventory/v1",
        "request_id": request["request_id"],
        "subject_commit": request["subject_commit"],
        "roles": deepcopy(request["role_entries"]),
        "complete_role_sequence": True,
        "release_eligible": False,
        "authority": "none",
        "activation": "inert",
    }


def _evidence_coverage(request: dict[str, Any]) -> dict[str, Any]:
    categories = [
        {
            "category_id": category_id,
            "status": _EVIDENCE_STATUS[category_id],
            "evidence_refs": list(_EVIDENCE_REFS[category_id]),
        }
        for category_id in EVIDENCE_CATEGORIES
    ]
    return {
        "schema_version": "phase5h-evidence-coverage/v1",
        "request_id": request["request_id"],
        "source_index_digest": request["source_index_digest"],
        "categories": categories,
        "overall_status": "incomplete",
        "independently_verified": False,
    }


def _conflict_register(request: dict[str, Any]) -> dict[str, Any]:
    conflicts = [
        {
            "conflict_id": conflict_id,
            "status": "unresolved",
            "evidence_refs": [f"conflict:{conflict_id}", "plan:PHASE5_CARRIED_FORWARD_DEBT"],
            "exit_condition": _CONFLICT_EXIT[conflict_id],
        }
        for conflict_id in CONFLICT_IDS
    ]
    return {
        "schema_version": "phase5h-conflict-register/v1",
        "request_id": request["request_id"],
        "debt_items": deepcopy(request["debt_items"]),
        "conflicts": conflicts,
        "all_resolved": False,
    }


def _court_disposition(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5h-court-disposition/v1",
        "request_id": request["request_id"],
        "disposition": "defer-non-release",
        "p20_eligible": False,
        "release_ready": False,
        "production_ready": False,
        "promotion_eligible": False,
        "authenticated_independence": False,
        "superiority_established": False,
        "authority": "none",
        "activation": "inert",
        "required_successor": "explicit-remediation-or-p14-p20-adoption",
    }


def compile_role_deepening_court(request: Mapping[str, Any]) -> dict[str, Any]:
    validate_consolidation_request(request)
    admitted = deepcopy(dict(request))
    outputs = {
        "role_inventory": _role_inventory(admitted),
        "evidence_coverage": _evidence_coverage(admitted),
        "conflict_register": _conflict_register(admitted),
        "court_disposition": _court_disposition(admitted),
    }
    if tuple(outputs) != OUTPUT_FIELDS:
        raise RuntimeError("internal Phase 5H output order drifted")
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "court_id": COURT_ID,
        "request": admitted,
        "outputs": outputs,
        "output_digests": {field: digest(outputs[field]) for field in OUTPUT_FIELDS},
    }
    envelope["envelope_digest"] = digest(envelope)
    validate_role_deepening_court(envelope)
    return deepcopy(envelope)
