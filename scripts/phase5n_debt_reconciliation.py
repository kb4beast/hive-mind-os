from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.phase5_debt_reconciliation import ALL_DEBT_IDS, _digest_json
from scripts.phase5m_debt_reconciliation import EXTERNAL_INPUT_DEBT_IDS

OUTPUT_PATH = Path("evidence/phase5n/phase5_debt_reconciliation.json")
PREDECESSOR_PATH = Path("evidence/phase5m/phase5_debt_reconciliation.json")
PREDECESSOR_DIGEST = "sha256:abc6a0ebcb0b676d13529ccf71330cf683a75464d1b017cef6fc7c75a6ecb701"
SUBJECT_COMMIT = "a78fcdd3418565565aa82ae127957632e5ac08d8"
SUBJECT_RUNS = ("30775103987", "30775114316")
INDEX_DIGEST = "sha256:2b029c1f7c39b3b248b5b9e3e6a6a91ca46b93be01583e6a4c3760f427df2f9f"
RESOLVED_DEBT_ID = "P5H-DEBT-01"
NEXT_INTERNAL_DEBT_IDS = (
    "P5E-DEBT-01",
    "P5E-DEBT-03",
    "P5F-DEBT-01",
    "P5F-DEBT-03",
    "P5G-DEBT-01",
    "P5G-DEBT-03",
)


def _load_predecessor(repository: Path) -> dict[str, Any]:
    record = json.loads((repository / PREDECESSOR_PATH).read_text(encoding="utf-8"))
    body = {key: value for key, value in record.items() if key != "reconciliation_digest"}
    if record.get("reconciliation_digest") != PREDECESSOR_DIGEST:
        raise RuntimeError("Phase 5M predecessor claim drifted")
    if _digest_json(body) != PREDECESSOR_DIGEST:
        raise RuntimeError("Phase 5M predecessor digest is invalid")
    return record


def build_reconciliation(repository: Path) -> dict[str, Any]:
    predecessor = _load_predecessor(repository)
    prior_active = tuple(predecessor["current_active_debt_ids"])
    if RESOLVED_DEBT_ID not in prior_active:
        raise RuntimeError("P5H-DEBT-01 is not active in the predecessor")
    index = json.loads(
        (repository / "evidence/phase5n/phase5_role_ancestry_index.json").read_text(
            encoding="utf-8"
        )
    )
    if index.get("index_digest") != INDEX_DIGEST or index.get("role_count") != 8:
        raise RuntimeError("Phase 5N ancestry index does not match the hosted subject")
    workflow = (repository / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if "Verify installed Phase 5 role ancestry" not in workflow:
        raise RuntimeError("permanent role ancestry verification is absent")

    current_active = tuple(item for item in prior_active if item != RESOLVED_DEBT_ID)
    resolution = {
        "debt_id": RESOLVED_DEBT_ID,
        "reason": "all eight roles have exact Git ancestry, PR merge trees, contract/evidence indexes, and installed-wheel byte verification",
        "evidence": [
            f"commit:{SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in SUBJECT_RUNS),
            "artifact:evidence/phase5n/phase5_role_ancestry_index.json",
            "artifact:dist/phase5-role-ancestry-installed-wheel.json",
        ],
    }
    resolved = [dict(item) for item in predecessor["resolved"]] + [resolution]
    resolved.sort(key=lambda item: ALL_DEBT_IDS.index(item["debt_id"]))
    if set(EXTERNAL_INPUT_DEBT_IDS) - set(current_active):
        raise RuntimeError("Phase 5N resolved an external-input debt")
    if not set(NEXT_INTERNAL_DEBT_IDS).issubset(current_active):
        raise RuntimeError("Phase 5N next-internal debt is not active")
    if {item["debt_id"] for item in resolved} | set(current_active) != set(ALL_DEBT_IDS):
        raise RuntimeError("Phase 5N debt sets do not partition the register")

    body: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "phase5-debt-reconciliation",
        "phase_item": "N",
        "predecessor": {
            "path": PREDECESSOR_PATH.as_posix(),
            "reconciliation_digest": PREDECESSOR_DIGEST,
        },
        "subject_commit": SUBJECT_COMMIT,
        "subject_run_ids": list(SUBJECT_RUNS),
        "ancestry_index_digest": INDEX_DIGEST,
        "resolved_in_phase5n": [RESOLVED_DEBT_ID],
        "resolved": resolved,
        "current_active_debt_ids": list(current_active),
        "external_input_debt_ids": list(EXTERNAL_INPUT_DEBT_IDS),
        "next_internal_debt_ids": list(NEXT_INTERNAL_DEBT_IDS),
        "counts": {
            "total": 35,
            "prior_resolved": len(predecessor["resolved"]),
            "resolved_in_phase5n": 1,
            "resolved": len(resolved),
            "current_active": len(current_active),
        },
        "local_release_validation": dict(predecessor["local_release_validation"]),
        "claims": dict(predecessor["claims"]),
    }
    return {**body, "reconciliation_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    record = build_reconciliation(repository)
    destination = repository / OUTPUT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
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
