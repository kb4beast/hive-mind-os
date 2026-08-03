from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, TypedDict

from scripts.phase5_debt_reconciliation import (
    ALL_DEBT_IDS,
    EXTERNAL_INPUT_DEBT_IDS,
    _digest_json,
)

OUTPUT_PATH = Path("evidence/phase5m/phase5_debt_reconciliation.json")
PREDECESSOR_PATH = Path("evidence/phase5l/phase5_debt_reconciliation.json")
PREDECESSOR_DIGEST = "sha256:981832a1a900b98883c4eea3e052c666df5c084a6719038d6657a7c8b0357dcc"
SUBJECT_COMMIT = "da90b4430f8cb99113b58657db7539600e753395"
SUBJECT_RUNS = ("30774229678", "30774230905")
INVENTORY_TAIL = "sha256:4efbbe2e70e2d000fedde4dbf425df8ed5e7a6986778c8d52f0d3faf254d5ef8"


class Resolution(TypedDict):
    reason: str
    evidence: tuple[str, ...]


def _receipts(*artifacts: str) -> tuple[str, ...]:
    return (
        f"commit:{SUBJECT_COMMIT}",
        *(f"run:{run_id}" for run_id in SUBJECT_RUNS),
        *(f"artifact:{artifact}" for artifact in artifacts),
    )


NEW_RESOLUTIONS: dict[str, Resolution] = {
    "P5E-DEBT-02": {
        "reason": "the Integrator has a chained deterministic inventory and permanent isolated-wheel verification",
        "evidence": _receipts(
            "evidence/phase5e/phase5e_integrator_inventory.json",
            "dist/phase5e-to-k-installed-wheel.json",
        ),
    },
    "P5F-DEBT-02": {
        "reason": "the Steward inventory chains through Phase 5E and its installed package contract is permanently verified",
        "evidence": _receipts(
            "evidence/phase5f/phase5f_steward_inventory.json",
            "dist/phase5e-to-k-installed-wheel.json",
        ),
    },
    "P5G-DEBT-02": {
        "reason": "the Optimizer inventory and package surface are chained, reproduced, retained, and exact-head validated",
        "evidence": _receipts(
            "evidence/phase5g/phase5g_optimizer_inventory.json",
            "dist/phase5e-to-k-installed-wheel.json",
        ),
    },
    "P5H-DEBT-02": {
        "reason": "the consolidation court is included in the chained inventories and permanent installed-wheel gate",
        "evidence": _receipts(
            "evidence/phase5h/phase5h_role_deepening_inventory.json",
            "dist/phase5e-to-k-installed-wheel.json",
        ),
    },
    "P5H-DEBT-05": {
        "reason": "the exact final head passes chained inventory, installed-wheel, Ruff, Pyright, security, and every Python matrix gate",
        "evidence": _receipts(
            "evidence/phase5h/phase5h_role_deepening_inventory.json",
            "evidence/phase5m/PHASE5M_AUDIT_LEDGER.md",
        ),
    },
    "P5I-DEBT-02": {
        "reason": "the adoption docket has a chained inventory, package reproduction, permanent CI step, and retained receipt",
        "evidence": _receipts(
            "evidence/phase5i/phase5i_post_p13_adoption_inventory.json",
            "dist/phase5e-to-k-installed-wheel.json",
        ),
    },
    "P5J-DEBT-02": {
        "reason": "the review packet completes the required Phase 5E-J chain and passes isolated installed-wheel verification",
        "evidence": _receipts(
            "evidence/phase5j/phase5j_review_packet_inventory.json",
            "dist/phase5e-to-k-installed-wheel.json",
        ),
    },
}

NEXT_INTERNAL_DEBT_IDS = (
    "P5E-DEBT-01",
    "P5E-DEBT-03",
    "P5F-DEBT-01",
    "P5F-DEBT-03",
    "P5G-DEBT-01",
    "P5G-DEBT-03",
    "P5H-DEBT-01",
)


def _load_predecessor(repository: Path) -> dict[str, Any]:
    predecessor = json.loads((repository / PREDECESSOR_PATH).read_text(encoding="utf-8"))
    claimed = predecessor.get("reconciliation_digest")
    body = {
        key: value for key, value in predecessor.items() if key != "reconciliation_digest"
    }
    observed = _digest_json(body)
    if claimed != PREDECESSOR_DIGEST or observed != PREDECESSOR_DIGEST:
        raise RuntimeError(
            f"Phase 5L predecessor mismatch: claimed={claimed!r}, observed={observed!r}"
        )
    return predecessor


def build_reconciliation(repository: Path) -> dict[str, Any]:
    predecessor = _load_predecessor(repository)
    prior_active = tuple(predecessor["current_active_debt_ids"])
    if not set(NEW_RESOLUTIONS).issubset(prior_active):
        raise RuntimeError("a Phase 5M resolution is not active in the Phase 5L predecessor")

    tail_result = subprocess.run(
        (
            "git",
            "show",
            f"{SUBJECT_COMMIT}:evidence/phase5k/phase5k_external_evidence_inventory.json",
        ),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if tail_result.returncode != 0:
        raise RuntimeError(
            f"cannot reconstruct Phase 5M inventory tail: {tail_result.stderr.strip()}"
        )
    tail = json.loads(tail_result.stdout)
    if tail.get("inventory_digest") != INVENTORY_TAIL:
        raise RuntimeError("the Phase 5K inventory tail does not match the hosted subject")
    workflow = (repository / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for required in (
        "Verify installed Phase 5E-K contracts",
        "scripts/verify_phase5e_to_k_installed_wheel.py",
        "dist/phase5e-to-k-installed-wheel.json",
    ):
        if required not in workflow:
            raise RuntimeError(f"permanent installed-wheel gate is incomplete: {required}")

    current_active = tuple(
        debt_id for debt_id in prior_active if debt_id not in NEW_RESOLUTIONS
    )
    prior_resolved = {
        item["debt_id"]: {
            "debt_id": item["debt_id"],
            "reason": item["reason"],
            "evidence": list(item["evidence"]),
        }
        for item in predecessor["resolved"]
    }
    cumulative_resolved = [
        prior_resolved[debt_id]
        if debt_id in prior_resolved
        else {
            "debt_id": debt_id,
            "reason": NEW_RESOLUTIONS[debt_id]["reason"],
            "evidence": list(NEW_RESOLUTIONS[debt_id]["evidence"]),
        }
        for debt_id in ALL_DEBT_IDS
        if debt_id not in current_active
    ]

    if set(EXTERNAL_INPUT_DEBT_IDS) - set(current_active):
        raise RuntimeError("Phase 5M resolved an external-input debt")
    if not set(NEXT_INTERNAL_DEBT_IDS).issubset(current_active):
        raise RuntimeError("Phase 5M next-internal register contains a resolved debt")
    if {item["debt_id"] for item in cumulative_resolved} & set(current_active):
        raise RuntimeError("resolved and active Phase 5M debt sets overlap")
    if {item["debt_id"] for item in cumulative_resolved} | set(current_active) != set(
        ALL_DEBT_IDS
    ):
        raise RuntimeError("Phase 5M debt sets do not partition the source register")

    body: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "phase5-debt-reconciliation",
        "phase_item": "M",
        "predecessor": {
            "path": PREDECESSOR_PATH.as_posix(),
            "reconciliation_digest": PREDECESSOR_DIGEST,
        },
        "subject_commit": SUBJECT_COMMIT,
        "subject_run_ids": list(SUBJECT_RUNS),
        "inventory_tail_digest": INVENTORY_TAIL,
        "prior_active_debt_ids": list(prior_active),
        "resolved_in_phase5m": [
            debt_id for debt_id in ALL_DEBT_IDS if debt_id in NEW_RESOLUTIONS
        ],
        "resolved": cumulative_resolved,
        "current_active_debt_ids": list(current_active),
        "external_input_debt_ids": list(EXTERNAL_INPUT_DEBT_IDS),
        "next_internal_debt_ids": list(NEXT_INTERNAL_DEBT_IDS),
        "counts": {
            "total": len(ALL_DEBT_IDS),
            "prior_resolved": len(predecessor["resolved"]),
            "resolved_in_phase5m": len(NEW_RESOLUTIONS),
            "resolved": len(cumulative_resolved),
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
