from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.external_adoption_evidence import (
    compile_external_adoption_evidence_intake,
    example_evidence_intake_request,
)
from hive_mind_os.foundation.external_adoption_evidence_contracts import (
    OUTPUT_FIELDS as EXTERNAL_EVIDENCE_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.external_adoption_evidence_contracts import (
    validate_evidence_intake_request,
    validate_external_adoption_evidence_intake,
)
from hive_mind_os.foundation.independent_adoption_review import (
    compile_independent_adoption_review_packet,
    example_review_packet_request,
)
from hive_mind_os.foundation.independent_adoption_review_contracts import (
    OUTPUT_FIELDS as REVIEW_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.independent_adoption_review_contracts import (
    validate_independent_adoption_review_packet,
    validate_review_packet_request,
)
from hive_mind_os.foundation.integrator_playbook import (
    compile_integrator_intake,
    example_integrator_request,
)
from hive_mind_os.foundation.integrator_playbook_contracts import (
    OUTPUT_FIELDS as INTEGRATOR_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.integrator_playbook_contracts import (
    validate_integrator,
    validate_integrator_request,
)
from hive_mind_os.foundation.optimizer_playbook import (
    compile_optimizer_intake,
    example_optimizer_request,
)
from hive_mind_os.foundation.optimizer_playbook_contracts import (
    OUTPUT_FIELDS as OPTIMIZER_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.optimizer_playbook_contracts import (
    validate_optimizer,
    validate_optimizer_request,
)
from hive_mind_os.foundation.post_p13_adoption import (
    compile_post_p13_adoption_docket,
    example_adoption_request,
)
from hive_mind_os.foundation.post_p13_adoption_contracts import (
    OUTPUT_FIELDS as ADOPTION_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.post_p13_adoption_contracts import (
    validate_adoption_request,
    validate_post_p13_adoption_docket,
)
from hive_mind_os.foundation.role_deepening_court import (
    compile_role_deepening_court,
    example_consolidation_request,
)
from hive_mind_os.foundation.role_deepening_court_contracts import (
    OUTPUT_FIELDS as COURT_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.role_deepening_court_contracts import (
    validate_consolidation_request,
    validate_role_deepening_court,
)
from hive_mind_os.foundation.steward_playbook import (
    compile_steward_intake,
    example_steward_request,
)
from hive_mind_os.foundation.steward_playbook_contracts import (
    OUTPUT_FIELDS as STEWARD_OUTPUT_FIELDS,
)
from hive_mind_os.foundation.steward_playbook_contracts import (
    validate_steward,
    validate_steward_request,
)

BASE_HEAD = "8ca34497051a9b50927f3615df49506f79d0046e"
PHASE5D_INVENTORY_PATH = Path("evidence/phase5d/phase5d_curator_inventory.json")


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def _lookup(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            raise RuntimeError(f"missing boundary path {path}")
        current = current[component]
    return current


def _validate_inventory_digest(record: dict[str, Any], path: Path) -> str:
    claimed = record.get("inventory_digest")
    if not isinstance(claimed, str):
        raise RuntimeError(f"{path} has no inventory_digest")
    body = {key: value for key, value in record.items() if key != "inventory_digest"}
    observed = _digest_json(body)
    if observed != claimed:
        raise RuntimeError(f"{path} digest mismatch: {claimed} != {observed}")
    return claimed


@dataclass(frozen=True)
class PhaseSpec:
    item: str
    component: str
    output_path: Path
    module_path: str
    contracts_path: str
    test_path: str
    document_paths: tuple[str, ...]
    output_fields: tuple[str, ...]
    example: Callable[[], dict[str, Any]]
    compile: Callable[[dict[str, Any]], dict[str, Any]]
    validate_request: Callable[[dict[str, Any]], None]
    validate_envelope: Callable[[dict[str, Any]], None]
    boundaries: tuple[tuple[str, Any], ...]


def phase_specs() -> tuple[PhaseSpec, ...]:
    return (
        PhaseSpec(
            "E",
            "integrator-intake",
            Path("evidence/phase5e/phase5e_integrator_inventory.json"),
            "src/hive_mind_os/foundation/integrator_playbook.py",
            "src/hive_mind_os/foundation/integrator_playbook_contracts.py",
            "tests/test_phase5e_integrator_playbook.py",
            ("docs/architecture/PHASE5E_INTEGRATOR_CONTRACT.md",),
            tuple(INTEGRATOR_OUTPUT_FIELDS),
            example_integrator_request,
            compile_integrator_intake,
            validate_integrator_request,
            validate_integrator,
            (
                ("authority", "none"),
                ("activation", "inert"),
                ("outputs.integration_scope.release_recommendation", "defer"),
                ("outputs.compatibility_plan.execution_status", "not-run"),
                ("outputs.compatibility_plan.implementation_authorized", False),
                ("outputs.compatibility_plan.release_authorized", False),
                ("outputs.steward_handoff.status", "blocked"),
                ("outputs.steward_handoff.activation_authorized", False),
            ),
        ),
        PhaseSpec(
            "F",
            "steward-intake",
            Path("evidence/phase5f/phase5f_steward_inventory.json"),
            "src/hive_mind_os/foundation/steward_playbook.py",
            "src/hive_mind_os/foundation/steward_playbook_contracts.py",
            "tests/test_phase5f_steward_playbook.py",
            ("docs/architecture/PHASE5F_STEWARD_CONTRACT.md",),
            tuple(STEWARD_OUTPUT_FIELDS),
            example_steward_request,
            compile_steward_intake,
            validate_steward_request,
            validate_steward,
            (
                ("outputs.health_snapshot.health_status", "degraded"),
                ("outputs.health_snapshot.release_recommendation", "defer"),
                ("outputs.maintenance_plan.execution_status", "not-run"),
                ("outputs.maintenance_plan.maintenance_authorized", False),
                ("outputs.recovery_plan.execution_status", "not-run"),
                ("outputs.recovery_plan.recovery_authorized", False),
                ("outputs.optimizer_handoff.eligible", False),
                ("outputs.optimizer_handoff.status", "blocked"),
            ),
        ),
        PhaseSpec(
            "G",
            "optimizer-intake",
            Path("evidence/phase5g/phase5g_optimizer_inventory.json"),
            "src/hive_mind_os/foundation/optimizer_playbook.py",
            "src/hive_mind_os/foundation/optimizer_playbook_contracts.py",
            "tests/test_phase5g_optimizer_playbook.py",
            ("docs/architecture/PHASE5G_OPTIMIZER_CONTRACT.md",),
            tuple(OPTIMIZER_OUTPUT_FIELDS),
            example_optimizer_request,
            compile_optimizer_intake,
            validate_optimizer_request,
            validate_optimizer,
            (
                ("authority", "none"),
                ("activation", "inert"),
                ("outputs.challenger_plan.execution_status", "not-run"),
                ("outputs.evaluation_plan.holdout_exposure_status", "sealed-not-accessed"),
                ("outputs.evaluation_plan.execution_status", "not-run"),
                ("outputs.promotion_handoff.eligible", False),
                ("outputs.promotion_handoff.promotion_authorized", False),
                ("outputs.promotion_handoff.release_authorized", False),
            ),
        ),
        PhaseSpec(
            "H",
            "role-deepening-court",
            Path("evidence/phase5h/phase5h_role_deepening_inventory.json"),
            "src/hive_mind_os/foundation/role_deepening_court.py",
            "src/hive_mind_os/foundation/role_deepening_court_contracts.py",
            "tests/test_phase5h_role_deepening_court.py",
            ("docs/architecture/PHASE5H_ROLE_DEEPENING_CONSOLIDATION_COURT.md",),
            tuple(COURT_OUTPUT_FIELDS),
            example_consolidation_request,
            compile_role_deepening_court,
            validate_consolidation_request,
            validate_role_deepening_court,
            (
                ("outputs.role_inventory.release_eligible", False),
                ("outputs.evidence_coverage.overall_status", "incomplete"),
                ("outputs.court_disposition.disposition", "defer-non-release"),
                ("outputs.court_disposition.p20_eligible", False),
                ("outputs.court_disposition.release_ready", False),
                ("outputs.court_disposition.production_ready", False),
                ("outputs.court_disposition.authority", "none"),
            ),
        ),
        PhaseSpec(
            "I",
            "post-p13-adoption-docket",
            Path("evidence/phase5i/phase5i_post_p13_adoption_inventory.json"),
            "src/hive_mind_os/foundation/post_p13_adoption.py",
            "src/hive_mind_os/foundation/post_p13_adoption_contracts.py",
            "tests/test_phase5i_post_p13_adoption.py",
            ("docs/architecture/PHASE5I_POST_P13_ADOPTION_DOCKET.md",),
            tuple(ADOPTION_OUTPUT_FIELDS),
            example_adoption_request,
            compile_post_p13_adoption_docket,
            validate_adoption_request,
            validate_post_p13_adoption_docket,
            (
                ("outputs.adoption_disposition.disposition", "awaiting-independent-adoption"),
                ("outputs.adoption_disposition.p14_eligible", False),
                ("outputs.adoption_disposition.p20_eligible", False),
                ("outputs.adoption_disposition.release_ready", False),
                ("outputs.adoption_disposition.production_ready", False),
                ("outputs.adoption_disposition.deployment_authorized", False),
                ("outputs.adoption_disposition.authority", "none"),
            ),
        ),
        PhaseSpec(
            "J",
            "independent-adoption-review-packet",
            Path("evidence/phase5j/phase5j_review_packet_inventory.json"),
            "src/hive_mind_os/foundation/independent_adoption_review.py",
            "src/hive_mind_os/foundation/independent_adoption_review_contracts.py",
            "tests/test_phase5j_independent_adoption_review.py",
            ("docs/architecture/PHASE5J_INDEPENDENT_ADOPTION_REVIEW_PACKET.md",),
            tuple(REVIEW_OUTPUT_FIELDS),
            example_review_packet_request,
            compile_independent_adoption_review_packet,
            validate_review_packet_request,
            validate_independent_adoption_review_packet,
            (
                ("outputs.review_packet_manifest.review_status", "not-run"),
                ("outputs.decision_templates.selected_decision", "none"),
                ("outputs.decision_templates.signed_decision_present", False),
                ("outputs.external_handoff.handoff_status", "external-action-required"),
                ("outputs.external_handoff.p14_eligible", False),
                ("outputs.external_handoff.release_ready", False),
                ("outputs.external_handoff.deployment_authorized", False),
                ("outputs.external_handoff.authority", "none"),
            ),
        ),
        PhaseSpec(
            "K",
            "external-adoption-evidence-intake",
            Path("evidence/phase5k/phase5k_external_evidence_inventory.json"),
            "src/hive_mind_os/foundation/external_adoption_evidence.py",
            "src/hive_mind_os/foundation/external_adoption_evidence_contracts.py",
            "tests/test_phase5k_external_adoption_evidence.py",
            ("docs/architecture/PHASE5K_EXTERNAL_ADOPTION_EVIDENCE_INTAKE.md",),
            tuple(EXTERNAL_EVIDENCE_OUTPUT_FIELDS),
            example_evidence_intake_request,
            compile_external_adoption_evidence_intake,
            validate_evidence_intake_request,
            validate_external_adoption_evidence_intake,
            (
                ("outputs.evidence_requirements.trust_anchor_status", "missing"),
                ("outputs.evidence_requirements.external_retention_status", "missing"),
                ("outputs.verification_policy.policy_status", "defined-not-executed"),
                ("outputs.evidence_register.signed_decision_present", False),
                ("outputs.intake_disposition.disposition", "awaiting-external-evidence"),
                ("outputs.intake_disposition.p14_eligible", False),
                ("outputs.intake_disposition.release_ready", False),
                ("outputs.intake_disposition.deployment_authorized", False),
                ("outputs.intake_disposition.authority", "none"),
            ),
        ),
    )


def build_inventory(
    repository: Path,
    spec: PhaseSpec,
    predecessor_path: Path,
    predecessor_digest: str,
) -> dict[str, Any]:
    request = spec.example()
    spec.validate_request(request)
    envelope = spec.compile(request)
    spec.validate_envelope(envelope)
    if tuple(envelope["outputs"]) != spec.output_fields:
        raise RuntimeError(f"Phase 5{spec.item} output order drifted")
    expected_digests = {
        field: digest(envelope["outputs"][field]) for field in spec.output_fields
    }
    if envelope["output_digests"] != expected_digests:
        raise RuntimeError(f"Phase 5{spec.item} output digests drifted")
    boundary_values = {path: _lookup(envelope, path) for path, _ in spec.boundaries}
    for path, expected in spec.boundaries:
        if boundary_values[path] != expected:
            raise RuntimeError(
                f"Phase 5{spec.item} boundary {path} drifted: "
                f"{boundary_values[path]!r} != {expected!r}"
            )
    implementation_paths = (
        ".github/workflows/ci.yml",
        spec.module_path,
        spec.contracts_path,
        spec.test_path,
        *spec.document_paths,
        "scripts/phase5e_to_k_inventory.py",
        "scripts/verify_phase5e_to_k_installed_wheel.py",
        "tests/test_phase5m_evidence_inventory.py",
    )
    missing = [path for path in implementation_paths if not (repository / path).is_file()]
    if missing:
        raise RuntimeError(f"Phase 5{spec.item} inventory paths are missing: {missing}")
    body = {
        "schema_version": 1,
        "phase": 5,
        "phase_item": spec.item,
        "component": spec.component,
        "base_head": BASE_HEAD,
        "predecessor": {
            "path": predecessor_path.as_posix(),
            "inventory_digest": predecessor_digest,
        },
        "contract_reproduction": {
            "request_digest": digest(request),
            "envelope_digest": envelope["envelope_digest"],
            "request_valid": True,
            "envelope_valid": True,
            "output_fields": list(spec.output_fields),
            "output_digests": expected_digests,
        },
        "boundary_assertions": boundary_values,
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "external_dependencies_added": 0,
        "runtime_binding_added": False,
        "authority_added": False,
        "authenticated_independence_claimed": False,
        "commands_executed_by_inventory": False,
        "tests_executed_by_inventory": False,
        "release_ready": False,
        "production_ready": False,
        "deployment_authorized": False,
        "promotion_authorized": False,
        "superiority_claimed": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def build_inventory_chain(repository: Path) -> tuple[dict[str, Any], ...]:
    predecessor_absolute = repository / PHASE5D_INVENTORY_PATH
    predecessor = json.loads(predecessor_absolute.read_text(encoding="utf-8"))
    predecessor_digest = _validate_inventory_digest(predecessor, PHASE5D_INVENTORY_PATH)
    predecessor_path = PHASE5D_INVENTORY_PATH
    records: list[dict[str, Any]] = []
    for spec in phase_specs():
        record = build_inventory(
            repository, spec, predecessor_path, predecessor_digest
        )
        records.append(record)
        predecessor_path = spec.output_path
        predecessor_digest = record["inventory_digest"]
    return tuple(records)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    records = build_inventory_chain(repository)
    for spec, record in zip(phase_specs(), records, strict=True):
        destination = repository / spec.output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"{destination} {record['inventory_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
