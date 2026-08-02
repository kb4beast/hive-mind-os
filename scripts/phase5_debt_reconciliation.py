from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict

OUTPUT_PATH = Path("evidence/phase5l/phase5_debt_reconciliation.json")
RELEASE_SUBJECT_COMMIT = "0ff332249e7830464724ca9b5a0ebcc6fc43c741"
RELEASE_RUNS = ("30772648692", "30772650299")

ALL_DEBT_IDS = tuple(
    f"P5{phase}-DEBT-{index:02d}"
    for phase in "DEFGHIJ"
    for index in range(1, 6)
)

class Resolution(TypedDict):
    reason: str
    evidence: tuple[str, ...]


RESOLUTIONS: dict[str, Resolution] = {
    "P5D-DEBT-01": {
        "reason": "committed Ruff repairs pass on the stabilized and integrated trees",
        "evidence": (
            "commit:af9ac00a5959b96260fb3bcdfb0958ce0640ae04",
            "run:30771264748",
            "run:30771265827",
        ),
    },
    "P5D-DEBT-02": {
        "reason": "concrete-dict normalization preserves validation and passes Pyright 1.1.411",
        "evidence": (
            "commit:af9ac00a5959b96260fb3bcdfb0958ce0640ae04",
            "run:30771264748",
            "run:30771265827",
        ),
    },
    "P5D-DEBT-04": {
        "reason": "all three temporary write-capable Phase 5D workflows are absent",
        "evidence": (
            "commit:af9ac00a5959b96260fb3bcdfb0958ce0640ae04",
            "run:30771264748",
            "run:30771265827",
        ),
    },
    "P5D-DEBT-05": {
        "reason": "the integrated release head passes every Constitutional CI job",
        "evidence": (
            f"commit:{RELEASE_SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in RELEASE_RUNS),
        ),
    },
    "P5E-DEBT-04": {
        "reason": "the integrated exact release head supplies the required fully green receipt",
        "evidence": (
            f"commit:{RELEASE_SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in RELEASE_RUNS),
        ),
    },
    "P5F-DEBT-04": {
        "reason": "global Pyright and all integrated hosted gates pass on the exact release head",
        "evidence": (
            f"commit:{RELEASE_SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in RELEASE_RUNS),
        ),
    },
    "P5G-DEBT-04": {
        "reason": "the corrected Optimizer source now has fully green integrated exact-head evidence",
        "evidence": (
            f"commit:{RELEASE_SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in RELEASE_RUNS),
        ),
    },
    "P5I-DEBT-04": {
        "reason": "worker, Ruff, Pyright, and all Python matrices pass on the exact release head",
        "evidence": (
            f"commit:{RELEASE_SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in RELEASE_RUNS),
        ),
    },
    "P5J-DEBT-04": {
        "reason": "the packet is included in a fully green integrated exact-head receipt",
        "evidence": (
            f"commit:{RELEASE_SUBJECT_COMMIT}",
            *(f"run:{run_id}" for run_id in RELEASE_RUNS),
        ),
    },
}

CURRENT_ACTIVE_DEBT_IDS = tuple(
    debt_id for debt_id in ALL_DEBT_IDS if debt_id not in RESOLUTIONS
)

EXTERNAL_INPUT_DEBT_IDS = (
    "P5E-DEBT-05",
    "P5F-DEBT-05",
    "P5G-DEBT-05",
    "P5H-DEBT-03",
    "P5H-DEBT-04",
    "P5I-DEBT-01",
    "P5I-DEBT-03",
    "P5I-DEBT-05",
    "P5J-DEBT-01",
    "P5J-DEBT-03",
    "P5J-DEBT-05",
)

NEXT_INTERNAL_DEBT_IDS = (
    "P5E-DEBT-01",
    "P5E-DEBT-02",
    "P5E-DEBT-03",
    "P5F-DEBT-01",
    "P5F-DEBT-02",
    "P5F-DEBT-03",
    "P5G-DEBT-01",
    "P5G-DEBT-02",
    "P5G-DEBT-03",
    "P5H-DEBT-01",
    "P5H-DEBT-02",
    "P5I-DEBT-02",
    "P5J-DEBT-02",
)


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def build_reconciliation(repository: Path) -> dict[str, Any]:
    canonical_plan = (
        repository / "docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md"
    ).read_text(encoding="utf-8")
    phase5j_plan = (
        repository / "docs/plan/PHASE5J_CARRIED_FORWARD_DEBT.md"
    ).read_text(encoding="utf-8")
    source_text = canonical_plan + phase5j_plan
    missing_ids = [debt_id for debt_id in ALL_DEBT_IDS if debt_id not in source_text]
    if missing_ids:
        raise RuntimeError(f"source debt register is incomplete: {missing_ids}")

    obsolete_workflows = (
        ".github/workflows/phase5d-materialize.yml",
        ".github/workflows/phase5d-publication-remand.yml",
        ".github/workflows/phase5d-final-cleanup.yml",
    )
    retained_workflows = [
        relative for relative in obsolete_workflows if (repository / relative).exists()
    ]
    if retained_workflows:
        raise RuntimeError(f"obsolete workflows remain: {retained_workflows}")

    worker_test = (repository / "tests/test_workers.py").read_text(encoding="utf-8")
    for required in (
        "_read_claim_marker",
        "_wait_for_observed_lease_expiry",
        "self.assertNotEqual(claimed_id, \"none\")",
        "recovery_queue = Scheduler(self.root, lease_seconds=5.0)",
        "heartbeat_interval=0.25",
    ):
        if required not in worker_test:
            raise RuntimeError(f"worker recovery repair is missing: {required!r}")

    if set(RESOLUTIONS) & set(CURRENT_ACTIVE_DEBT_IDS):
        raise RuntimeError("resolved and active debt sets overlap")
    if set(RESOLUTIONS) | set(CURRENT_ACTIVE_DEBT_IDS) != set(ALL_DEBT_IDS):
        raise RuntimeError("resolved and active debt sets do not partition the source register")
    if not set(EXTERNAL_INPUT_DEBT_IDS).issubset(CURRENT_ACTIVE_DEBT_IDS):
        raise RuntimeError("an external-input debt was resolved without external evidence")
    if not set(NEXT_INTERNAL_DEBT_IDS).issubset(CURRENT_ACTIVE_DEBT_IDS):
        raise RuntimeError("an internally actionable debt is absent from the active register")

    body: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "phase5-debt-reconciliation",
        "release_subject_commit": RELEASE_SUBJECT_COMMIT,
        "release_run_ids": list(RELEASE_RUNS),
        "source_registers": [
            "docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md",
            "docs/plan/PHASE5J_CARRIED_FORWARD_DEBT.md",
        ],
        "prior_active_debt_ids": list(ALL_DEBT_IDS),
        "resolved": [
            {
                "debt_id": debt_id,
                "reason": RESOLUTIONS[debt_id]["reason"],
                "evidence": list(RESOLUTIONS[debt_id]["evidence"]),
            }
            for debt_id in ALL_DEBT_IDS
            if debt_id in RESOLUTIONS
        ],
        "current_active_debt_ids": list(CURRENT_ACTIVE_DEBT_IDS),
        "external_input_debt_ids": list(EXTERNAL_INPUT_DEBT_IDS),
        "next_internal_debt_ids": list(NEXT_INTERNAL_DEBT_IDS),
        "counts": {
            "prior_active": len(ALL_DEBT_IDS),
            "resolved": len(RESOLUTIONS),
            "current_active": len(CURRENT_ACTIVE_DEBT_IDS),
        },
        "local_release_validation": {
            "platform": "windows-cpython-3.14",
            "tests_run": 946,
            "duration_seconds": 863.292,
            "result": "failed-known-blocker",
            "blocker_ids": ["B-OPS-08"],
            "new_phase5_failures": 0,
        },
        "claims": {
            "adr_015_adopted": False,
            "p14_eligible": False,
            "p20_eligible": False,
            "authenticated_independence": False,
            "release_ready": False,
            "production_ready": False,
            "deployment_authorized": False,
            "promotion_authorized": False,
            "superiority_established": False,
        },
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
