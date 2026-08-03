from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OUTPUT_PATH = Path("evidence/phase5o/phase5_governance_records.json")
SUBJECT_BASE = "60b76a3ea858f20d1cd126cc223573adb2857c5e"

DOCUMENTS = {
    "E": (
        "docs/architecture/ADR-037-INTEGRATOR-GOVERNANCE-BOUNDARY.md",
        "docs/architecture/PHASE5E_MIGRATION_AND_ROLLBACK.md",
        "evidence/courts/phase5e-integrator-governance-court.md",
        "evidence/phase5e/PHASE5E_DISSENT.md",
        "evidence/sources/PHASE5E_INTEGRATOR_SOURCE_REGISTER.md",
    ),
    "F": (
        "docs/architecture/ADR-038-STEWARD-OPERATIONS-BOUNDARY.md",
        "docs/architecture/PHASE5F_MIGRATION_AND_ROLLBACK.md",
        "docs/operations/PHASE5F_STEWARD_RUNBOOK.md",
        "evidence/courts/phase5f-steward-governance-court.md",
        "evidence/phase5f/PHASE5F_DISSENT.md",
        "evidence/sources/PHASE5F_STEWARD_SOURCE_REGISTER.md",
    ),
    "G": (
        "docs/architecture/ADR-039-OPTIMIZER-EVALUATION-CUSTODY.md",
        "evidence/courts/phase5g-optimizer-governance-court.md",
        "evidence/phase5g/PHASE5G_DISSENT.md",
        "evidence/sources/PHASE5G_OPTIMIZER_SOURCE_REGISTER.md",
    ),
}


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: object) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def _procedural_review(phase: str) -> dict[str, Any]:
    roles = ("clerk", "advocate", "cross-examiner", "expert-witness", "judge")
    return {
        "phase": f"5{phase}",
        "actors": [
            {"role": role, "actor_id": f"procedural:p5o-{phase.lower()}-{role}"}
            for role in roles
        ],
        "same_assistant_performed_procedural_passes": True,
        "authenticated_distinct_actors": False,
        "independence_claimed": False,
        "authority": "none",
        "release_authorized": False,
    }


def build_records(repository: Path) -> dict[str, Any]:
    document_receipts: dict[str, dict[str, str]] = {}
    for phase, paths in DOCUMENTS.items():
        document_receipts[phase] = {}
        for path in paths:
            absolute = repository / path
            if not absolute.is_file():
                raise RuntimeError(f"Phase 5{phase} governance document is missing: {path}")
            document_receipts[phase][path] = _digest_bytes(absolute.read_bytes())

    body: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "phase5-governance-records",
        "subject_base": SUBJECT_BASE,
        "documents": document_receipts,
        "phase5e": {
            "procedural_role_review": _procedural_review("E"),
            "migration_status": "defined-not-executed",
            "rollback_status": "defined-not-executed",
            "compatibility_execution_status": "not-run",
        },
        "phase5f": {
            "procedural_role_review": _procedural_review("F"),
            "runbook_status": "defined-not-executed",
            "recovery_exercise": {
                "exercise_id": "phase5f-recovery-exercise-template-v1",
                "status": "designed-not-executed",
                "authority_supplied": False,
                "commands_executed": False,
                "recovery_claimed": False,
                "evidence_deletion_authorized": False,
                "known_blockers": ["B-OPS-08"],
            },
        },
        "phase5g": {
            "procedural_role_review": _procedural_review("G"),
            "protected_holdout_custody": {
                "status": "sealed-not-accessed",
                "external_custodian_authenticated": False,
                "contents_present": False,
            },
            "comparator_manifest": {
                "status": "awaiting-pinned-comparators",
                "comparators": [],
            },
            "losing_result_archive": {"status": "empty-no-evaluations-run", "results": []},
            "independent_evaluator_record": {
                "status": "required-not-authenticated",
                "actor_id": None,
                "signature": None,
            },
            "promotion_court_disposition": {
                "disposition": "defer",
                "evaluation_status": "not-run",
                "promotion_authorized": False,
                "superiority_established": False,
            },
        },
        "claims": {
            "authenticated_independence": False,
            "recovery_executed": False,
            "evaluation_executed": False,
            "release_ready": False,
            "production_ready": False,
            "promotion_authorized": False,
            "superiority_established": False,
        },
    }
    return {**body, "record_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    record = build_records(repository)
    destination = repository / OUTPUT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(destination)
    print(record["record_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
