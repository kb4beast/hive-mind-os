from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.phase5_debt_reconciliation import ALL_DEBT_IDS, _digest_json
from scripts.phase5n_debt_reconciliation import EXTERNAL_INPUT_DEBT_IDS

OUTPUT_PATH = Path("evidence/phase5o/phase5_debt_reconciliation.json")
PREDECESSOR_PATH = Path("evidence/phase5n/phase5_debt_reconciliation.json")
PREDECESSOR_DIGEST = "sha256:dc6ee7ca0986d0cefe9df98a61bdcd8eea8a7985b3b725b27e0b7c564bfb04e4"
SUBJECT_COMMIT = "a576603b056c30156b88ea5dfa99d893afdf3cfc"
SUBJECT_RUNS = ("30776259417", "30776260598")
GOVERNANCE_DIGEST = "sha256:13499ff4a27a3e4f20a78c6e9695bb7ed83354ca4da7d3cd25b0e3699c2a83a6"
NEW_RESOLUTIONS = ("P5E-DEBT-03", "P5F-DEBT-03", "P5G-DEBT-03")
NEXT_INTERNAL_DEBT_IDS = ("P5E-DEBT-01", "P5F-DEBT-01", "P5G-DEBT-01")


def build_reconciliation(repository: Path) -> dict[str, Any]:
    predecessor = json.loads((repository / PREDECESSOR_PATH).read_text(encoding="utf-8"))
    predecessor_body = {
        key: value for key, value in predecessor.items() if key != "reconciliation_digest"
    }
    if predecessor.get("reconciliation_digest") != PREDECESSOR_DIGEST:
        raise RuntimeError("Phase 5N predecessor claim drifted")
    if _digest_json(predecessor_body) != PREDECESSOR_DIGEST:
        raise RuntimeError("Phase 5N predecessor digest is invalid")
    governance = json.loads(
        (repository / "evidence/phase5o/phase5_governance_records.json").read_text(
            encoding="utf-8"
        )
    )
    if governance.get("record_digest") != GOVERNANCE_DIGEST:
        raise RuntimeError("Phase 5O governance record drifted")

    prior_active = tuple(predecessor["current_active_debt_ids"])
    if not set(NEW_RESOLUTIONS).issubset(prior_active):
        raise RuntimeError("a Phase 5O resolution is not active in the predecessor")
    current_active = tuple(item for item in prior_active if item not in NEW_RESOLUTIONS)
    reasons = {
        "P5E-DEBT-03": "Integrator court, dissent, ADR, sources, migration/rollback, and procedural review are present and sealed",
        "P5F-DEBT-03": "Steward court, dissent, ADR, sources, runbook, recovery template, rollback, and procedural review are present and sealed",
        "P5G-DEBT-03": "Optimizer court, dissent, ADR, sources, custody, comparator, losing-result, evaluator, and defer-promotion records are present and sealed",
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
                    "artifact:evidence/phase5o/phase5_governance_records.json",
                ],
            }
        )
    resolved.sort(key=lambda item: ALL_DEBT_IDS.index(item["debt_id"]))
    if set(EXTERNAL_INPUT_DEBT_IDS) - set(current_active):
        raise RuntimeError("Phase 5O resolved an external-input debt")
    if not set(NEXT_INTERNAL_DEBT_IDS).issubset(current_active):
        raise RuntimeError("Phase 5O internal output debt is not active")
    if {item["debt_id"] for item in resolved} | set(current_active) != set(ALL_DEBT_IDS):
        raise RuntimeError("Phase 5O debt sets do not partition the register")
    body: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "phase5-debt-reconciliation",
        "phase_item": "O",
        "predecessor": {
            "path": PREDECESSOR_PATH.as_posix(),
            "reconciliation_digest": PREDECESSOR_DIGEST,
        },
        "subject_commit": SUBJECT_COMMIT,
        "subject_run_ids": list(SUBJECT_RUNS),
        "governance_record_digest": GOVERNANCE_DIGEST,
        "resolved_in_phase5o": list(NEW_RESOLUTIONS),
        "resolved": resolved,
        "current_active_debt_ids": list(current_active),
        "external_input_debt_ids": list(EXTERNAL_INPUT_DEBT_IDS),
        "next_internal_debt_ids": list(NEXT_INTERNAL_DEBT_IDS),
        "counts": {
            "total": 35,
            "prior_resolved": 18,
            "resolved_in_phase5o": 3,
            "resolved": 21,
            "current_active": 14,
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
