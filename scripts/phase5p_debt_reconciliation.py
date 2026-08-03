from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.phase5_debt_reconciliation import ALL_DEBT_IDS, _digest_json
from scripts.phase5n_debt_reconciliation import EXTERNAL_INPUT_DEBT_IDS

OUTPUT_PATH = Path("evidence/phase5p/phase5_debt_reconciliation.json")
PREDECESSOR_PATH = Path("evidence/phase5o/phase5_debt_reconciliation.json")
PREDECESSOR_DIGEST = (
    "sha256:18de87d236e26a855fd79c4cd210f1eed8f45ca0dfeced984a54ff65369b6676"
)
SUBJECT_COMMIT = "4a80698a9c5a22569e79f936dda85c1921397bcb"
SUBJECT_RUNS = ("30777962621", "30777987391")
FULL_OUTPUT_INVENTORY_DIGEST = (
    "sha256:afb7a7d54357c5b50d6db276b064b97f1a803b33e495fd15adca455b0e5bdd38"
)
NEW_RESOLUTIONS = ("P5E-DEBT-01", "P5F-DEBT-01", "P5G-DEBT-01")
NEXT_INTERNAL_DEBT_IDS: tuple[str, ...] = ()


def build_reconciliation(repository: Path) -> dict[str, Any]:
    predecessor = json.loads(
        (repository / PREDECESSOR_PATH).read_text(encoding="utf-8")
    )
    predecessor_body = {
        key: value
        for key, value in predecessor.items()
        if key != "reconciliation_digest"
    }
    if predecessor.get("reconciliation_digest") != PREDECESSOR_DIGEST:
        raise RuntimeError("Phase 5O predecessor claim drifted")
    if _digest_json(predecessor_body) != PREDECESSOR_DIGEST:
        raise RuntimeError("Phase 5O predecessor digest is invalid")

    inventory = json.loads(
        (
            repository / "evidence/phase5p/phase5_full_role_output_inventory.json"
        ).read_text(encoding="utf-8")
    )
    if inventory.get("inventory_digest") != FULL_OUTPUT_INVENTORY_DIGEST:
        raise RuntimeError("Phase 5P full-output inventory drifted")
    if inventory.get("output_count") != 22:
        raise RuntimeError("Phase 5P full-output inventory is incomplete")
    if any(
        inventory.get(field) is not False
        for field in (
            "authority_added",
            "execution_performed",
            "authenticated_independence_claimed",
            "release_ready",
            "production_ready",
            "deployment_authorized",
            "promotion_authorized",
            "superiority_claimed",
        )
    ):
        raise RuntimeError("Phase 5P inventory claim escalated")

    prior_active = tuple(predecessor["current_active_debt_ids"])
    if not set(NEW_RESOLUTIONS).issubset(prior_active):
        raise RuntimeError("a Phase 5P resolution is not active in the predecessor")
    current_active = tuple(item for item in prior_active if item not in NEW_RESOLUTIONS)
    if set(current_active) != set(EXTERNAL_INPUT_DEBT_IDS):
        raise RuntimeError("Phase 5P changed the external-input debt boundary")

    reasons = {
        "P5E-DEBT-01": "seven separately versioned Integrator outputs bind exact scope, evidence requirements, authority, payload digests, and installed-wheel reproduction",
        "P5F-DEBT-01": "seven separately versioned Steward outputs preserve degraded and not-run states, reversible recovery boundaries, evidence requirements, and installed-wheel reproduction",
        "P5G-DEBT-01": "eight separately versioned Optimizer outputs preserve sealed holdout and empty result states with adversarial tests and installed-wheel reproduction",
    }
    resolved = [dict(item) for item in predecessor["resolved"]]
    for debt_id in NEW_RESOLUTIONS:
        resolved.append(
            {
                "debt_id": debt_id,
                "reason": reasons[debt_id],
                "evidence": [
                    f"commit:{SUBJECT_COMMIT}",
                    *(f"run:{run_id}" for run_id in SUBJECT_RUNS),
                    "artifact:evidence/phase5p/phase5_full_role_output_inventory.json",
                    "artifact:dist/phase5e-to-k-installed-wheel.json",
                ],
            }
        )
    resolved.sort(key=lambda item: ALL_DEBT_IDS.index(item["debt_id"]))
    if {item["debt_id"] for item in resolved} | set(current_active) != set(
        ALL_DEBT_IDS
    ):
        raise RuntimeError("Phase 5P debt sets do not partition the register")

    body: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "phase5-debt-reconciliation",
        "phase_item": "P",
        "predecessor": {
            "path": PREDECESSOR_PATH.as_posix(),
            "reconciliation_digest": PREDECESSOR_DIGEST,
        },
        "subject_commit": SUBJECT_COMMIT,
        "subject_run_ids": list(SUBJECT_RUNS),
        "full_output_inventory_digest": FULL_OUTPUT_INVENTORY_DIGEST,
        "resolved_in_phase5p": list(NEW_RESOLUTIONS),
        "resolved": resolved,
        "current_active_debt_ids": list(current_active),
        "external_input_debt_ids": list(EXTERNAL_INPUT_DEBT_IDS),
        "next_internal_debt_ids": list(NEXT_INTERNAL_DEBT_IDS),
        "counts": {
            "total": 35,
            "prior_resolved": 21,
            "resolved_in_phase5p": 3,
            "resolved": 24,
            "current_active": 11,
        },
        "local_release_validation": dict(predecessor["local_release_validation"]),
        "claims": dict(predecessor["claims"]),
    }
    return {**body, "reconciliation_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    record = build_reconciliation(repository)
    destination = repository / OUTPUT_PATH
    destination.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(destination)
    print(record["reconciliation_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
