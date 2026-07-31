from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, cast

from .canonical import digest
from .integrator_playbook_contracts import (
    ACCEPTED_BASE_COMMIT,
    ACTIVATION,
    AFFECTED_BOUNDARIES,
    AGENT_ID,
    BASE_DEFINITION_ID,
    CHECK_IDS,
    DEFINITION_ID,
    ENVELOPE_SCHEMA,
    OUTPUT_FIELDS,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    REQUIRED_DEBT_IDS,
    TENANT_ID,
    validate_integrator,
    validate_integrator_request,
)


_CHECK_BOUNDARY = {
    "exact-contract-versions": "contracts",
    "undeclared-dependency-detection": "dependencies",
    "provenance-continuity": "evidence",
    "data-lineage-continuity": "data-lineage",
    "adapter-replaceability": "adapters",
    "migration-order": "migration",
    "rollback-invertibility": "rollback",
    "inherited-debt-closure": "evidence",
    "temporary-workflow-removal": "temporary-workflows",
}


def example_integrator_request() -> dict[str, Any]:
    debt = [
        {
            "debt_id": "P5D-DEBT-01",
            "status": "open",
            "source_refs": [
                "run:30660783595",
                "run:30661841213",
                "file:src/hive_mind_os/foundation/curator_playbook.py",
                "file:tests/test_phase5d_curator_playbook.py",
            ],
            "blocked_effects": ["static-validation", "green-build"],
            "resolution_exit": (
                "Commit the demonstrated Ruff repairs and retain an exact-head hosted Ruff receipt."
            ),
        },
        {
            "debt_id": "P5D-DEBT-02",
            "status": "open",
            "source_refs": [
                "run:30661841213",
                "file:src/hive_mind_os/foundation/curator_playbook.py",
            ],
            "blocked_effects": ["type-validation", "cleanup-publication"],
            "resolution_exit": (
                "Correct the Mapping/dict typing without weakening exact-container validation and "
                "retain successful Pyright and focused-test receipts."
            ),
        },
        {
            "debt_id": "P5D-DEBT-03",
            "status": "open",
            "source_refs": [
                "run:30660783595",
                (
                    "test:tests/test_workers.py::WorkerTests::"
                    "test_seeded_process_kill_sweep_reclaims_without_duplicate_effects"
                ),
            ],
            "blocked_effects": ["python-3.11-determinism", "full-suite"],
            "resolution_exit": (
                "Pass exact-head Python 3.11, 3.12, and 3.14 suites without weakening the worker test."
            ),
        },
        {
            "debt_id": "P5D-DEBT-04",
            "status": "open",
            "source_refs": [
                "file:.github/workflows/phase5d-materialize.yml",
                "file:.github/workflows/phase5d-publication-remand.yml",
                "file:.github/workflows/phase5d-final-cleanup.yml",
            ],
            "blocked_effects": ["workflow-governance", "integration-surface"],
            "resolution_exit": (
                "Remove all temporary workflows in a normal commit and pass governance checks."
            ),
        },
        {
            "debt_id": "P5D-DEBT-05",
            "status": "open",
            "source_refs": ["run:30661841169", "run:30661841213"],
            "blocked_effects": ["release-readiness", "production-readiness"],
            "resolution_exit": (
                "Pass the full exact-head Constitutional CI matrix and installed-wheel evidence jobs."
            ),
        },
    ]
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5e:integrator:intake:001",
        "tenant_id": TENANT_ID,
        "repository_id": REPOSITORY_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "curator_envelope_digest": (
            "sha256:2222222222222222222222222222222222222222222222222222222222222222"
        ),
        "inherited_debt": debt,
        "requested_next_role": "steward",
        "authority": "none",
        "activation": "inert",
    }


def _required_evidence_refs(request: dict[str, Any]) -> list[str]:
    debt = cast(list[dict[str, Any]], request["inherited_debt"])
    return sorted(
        {
            reference
            for item in debt
            for reference in cast(list[str], item["source_refs"])
        }
    )


def _compile_checks(request: dict[str, Any]) -> list[dict[str, Any]]:
    required_refs = _required_evidence_refs(request)
    checks: list[dict[str, Any]] = []
    for check_id in CHECK_IDS:
        evidence_refs = required_refs if check_id in {
            "inherited-debt-closure",
            "temporary-workflow-removal",
        } else [
            f"request:{request['request_id']}",
            f"curator-envelope:{request['curator_envelope_digest']}",
        ]
        checks.append(
            {
                "check_id": check_id,
                "boundary": _CHECK_BOUNDARY[check_id],
                "status": "not-run",
                "required_evidence_refs": evidence_refs,
            }
        )
    return checks


def compile_integrator_intake(request: Mapping[str, Any]) -> dict[str, Any]:
    validate_integrator_request(request)
    request_snapshot = cast(dict[str, Any], deepcopy(dict(request)))
    outputs: dict[str, Any] = {
        "integration_scope": {
            "schema_version": "phase5e-integration-scope/v1",
            "repository_id": request_snapshot["repository_id"],
            "tenant_id": request_snapshot["tenant_id"],
            "request_id": request_snapshot["request_id"],
            "accepted_base_commit": request_snapshot["subject_commit"],
            "subject_tree": request_snapshot["subject_tree"],
            "curator_envelope_digest": request_snapshot["curator_envelope_digest"],
            "affected_boundaries": list(AFFECTED_BOUNDARIES),
            "release_recommendation": "defer",
            "authority": "none",
            "activation": "inert",
        },
        "compatibility_plan": {
            "schema_version": "phase5e-compatibility-plan/v1",
            "request_id": request_snapshot["request_id"],
            "checks": _compile_checks(request_snapshot),
            "execution_status": "not-run",
            "implementation_authorized": False,
            "release_authorized": False,
        },
        "debt_register": {
            "schema_version": "phase5e-debt-register/v1",
            "items": deepcopy(request_snapshot["inherited_debt"]),
            "unresolved_count": len(REQUIRED_DEBT_IDS),
            "release_blocked": True,
        },
        "steward_handoff": {
            "schema_version": "phase5e-steward-handoff/v1",
            "request_id": request_snapshot["request_id"],
            "next_role": "steward",
            "status": "blocked",
            "required_debt_ids": list(REQUIRED_DEBT_IDS),
            "required_evidence_refs": _required_evidence_refs(request_snapshot),
            "implementation_authorized": False,
            "release_authorized": False,
            "activation_authorized": False,
            "authority": "none",
        },
    }
    output_digests = {field: digest(outputs[field]) for field in OUTPUT_FIELDS}
    body: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "agent_id": AGENT_ID,
        "definition_id": DEFINITION_ID,
        "base_definition_id": BASE_DEFINITION_ID,
        "authority": "none",
        "activation": "inert",
        "request_snapshot": request_snapshot,
        "request_digest": digest(request_snapshot),
        "outputs": outputs,
        "output_digests": output_digests,
    }
    envelope = {**body, "envelope_digest": digest(body)}
    validate_integrator(envelope)
    return cast(dict[str, Any], deepcopy(envelope))
