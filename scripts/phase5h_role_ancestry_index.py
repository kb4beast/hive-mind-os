from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OUTPUT_PATH = Path("evidence/phase5n/phase5_role_ancestry_index.json")
SUBJECT_COMMIT = "ebe5884e30f62834ca649b72495e0178280ec3b3"
RETRIEVED_AT = "2026-08-03T00:34:00Z"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: object) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def _git(repository: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ("git", *args),
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {error}")
    if binary:
        return completed.stdout
    return completed.stdout.decode().strip()


@dataclass(frozen=True)
class RoleSpec:
    item: str
    role: str
    source_path: str
    contracts_path: str
    inventory_path: str
    audit_path: str
    court_path: str | None
    introduction_commit: str
    pr_number: int
    pr_merge_commit: str
    pr_url: str


def role_specs() -> tuple[RoleSpec, ...]:
    values = (
        ("A", "Orchestrator", "orchestrator_playbook", "3abfb58f465c2d3581010d7c313ea12c57a34fe3", 49, "cf4d4beb461d1c201b6eab9ced60db86389f3257"),
        ("B", "Architect", "architect_playbook", "db1430ffa2db152c019eeaa2cfdb3af7f7b431c5", 52, "43db53de7a41d9bc02e987776edc260594def4c8"),
        ("C", "Builder", "builder_playbook", "b313fc7d06749feb36c52297d729f14a9a601638", 53, "92a7f6ed96186a2a1c8fd1fd55147663f25588d9"),
        ("D", "Curator", "curator_playbook", "3b92d853cd2e63a2da2be40459cc995dd1366ed7", 54, "38ecbd176f3ae5b63b116c6a182a2889cd5d16a6"),
        ("E", "Integrator", "integrator_playbook", "c05a77d7d3368ae5dc5d8acca6c450eb2144b1c4", 55, "eccc8fce1bab5fb289279985198cb8753b3f171c"),
        ("F", "Steward", "steward_playbook", "58a8b36d5c040775b1acafb6a3ec87854a36bc18", 56, "eebda921352271c7d534009fe5ac8ba2306a2410"),
        ("G", "Optimizer", "optimizer_playbook", "af3bd37bc0df7092ca064bf61ef4d6852c9bcc83", 57, "e65be29ae1380743dfb6804e12c83af43abd291d"),
        ("H", "Consolidation Court", "role_deepening_court", "ff7b8c2334cfbd2048dec3f79f98c4a2bc3ea63e", 58, "522d04fe76b53574a4f93256466df69de42f747a"),
    )
    specs: list[RoleSpec] = []
    for item, role, stem, introduction, pr_number, merge in values:
        inventory_names = {
            "A": "phase5a_orchestrator_inventory.json",
            "B": "phase5b_architect_inventory.json",
            "C": "phase5c_builder_inventory.json",
            "D": "phase5d_curator_inventory.json",
            "E": "phase5e_integrator_inventory.json",
            "F": "phase5f_steward_inventory.json",
            "G": "phase5g_optimizer_inventory.json",
            "H": "phase5h_role_deepening_inventory.json",
        }
        court_names = {
            "A": "phase5a-orchestrator-playbook-court.md",
            "B": "phase5b-architect-playbook-court.md",
            "C": "phase5c-builder-playbook-court.md",
            "D": "phase5d-curator-playbook-court.md",
        }
        specs.append(
            RoleSpec(
                item=item,
                role=role,
                source_path=f"src/hive_mind_os/foundation/{stem}.py",
                contracts_path=f"src/hive_mind_os/foundation/{stem}_contracts.py",
                inventory_path=f"evidence/phase5{item.lower()}/{inventory_names[item]}",
                audit_path=f"evidence/phase5{item.lower()}/PHASE5{item}_AUDIT_LEDGER.md",
                court_path=(
                    f"evidence/courts/{court_names[item]}" if item in court_names else None
                ),
                introduction_commit=introduction,
                pr_number=pr_number,
                pr_merge_commit=merge,
                pr_url=f"https://github.com/kb4beast/hive-mind-os/pull/{pr_number}",
            )
        )
    return tuple(specs)


def _file_receipt(repository: Path, path: str) -> dict[str, str]:
    subject_bytes = _git(repository, "show", f"{SUBJECT_COMMIT}:{path}", binary=True)
    if not isinstance(subject_bytes, bytes):
        raise RuntimeError("binary Git read returned text")
    blob = _git(repository, "rev-parse", f"{SUBJECT_COMMIT}:{path}")
    if not isinstance(blob, str):
        raise RuntimeError("Git blob lookup returned bytes")
    return {"path": path, "git_blob": blob, "sha256": _digest_bytes(subject_bytes)}


def build_index(repository: Path) -> dict[str, Any]:
    subject_tree = _git(repository, "rev-parse", f"{SUBJECT_COMMIT}^{{tree}}")
    if not isinstance(subject_tree, str):
        raise RuntimeError("Git tree lookup returned bytes")
    roles: list[dict[str, Any]] = []
    for spec in role_specs():
        introduction = _git(
            repository,
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--reverse",
            "--",
            spec.source_path,
        )
        if not isinstance(introduction, str) or introduction.splitlines()[0] != spec.introduction_commit:
            raise RuntimeError(f"Phase 5{spec.item} introduction commit drifted")
        _git(repository, "merge-base", "--is-ancestor", spec.introduction_commit, SUBJECT_COMMIT)
        _git(repository, "merge-base", "--is-ancestor", spec.pr_merge_commit, SUBJECT_COMMIT)
        merge_tree = _git(repository, "rev-parse", f"{spec.pr_merge_commit}^{{tree}}")
        if not isinstance(merge_tree, str):
            raise RuntimeError("Git merge tree lookup returned bytes")

        inventory = _file_receipt(repository, spec.inventory_path)
        inventory_bytes = _git(
            repository, "show", f"{SUBJECT_COMMIT}:{spec.inventory_path}", binary=True
        )
        if not isinstance(inventory_bytes, bytes):
            raise RuntimeError("binary Git inventory read returned text")
        inventory_body = json.loads(inventory_bytes)
        inventory_digest = inventory_body.get("inventory_digest")
        if not isinstance(inventory_digest, str):
            raise RuntimeError(f"Phase 5{spec.item} inventory has no digest")
        sealed_body = {
            key: value for key, value in inventory_body.items() if key != "inventory_digest"
        }
        if _digest_json(sealed_body) != inventory_digest:
            raise RuntimeError(f"Phase 5{spec.item} inventory digest is invalid")
        inventory["inventory_digest"] = inventory_digest

        evidence_receipts = [_file_receipt(repository, spec.audit_path)]
        missing_evidence: list[str] = []
        if spec.court_path is None:
            missing_evidence.append("dedicated-procedural-court-record")
        else:
            evidence_receipts.append(_file_receipt(repository, spec.court_path))
        roles.append(
            {
                "phase_item": spec.item,
                "role": spec.role,
                "introduction_commit": spec.introduction_commit,
                "pull_request": {
                    "number": spec.pr_number,
                    "url": spec.pr_url,
                    "merge_commit": spec.pr_merge_commit,
                    "merge_tree": merge_tree,
                    "retrieved_at": RETRIEVED_AT,
                },
                "implementation": _file_receipt(repository, spec.source_path),
                "contract": _file_receipt(repository, spec.contracts_path),
                "inventory": inventory,
                "evidence_receipts": evidence_receipts,
                "missing_evidence": missing_evidence,
                "package_paths": [
                    spec.source_path.removeprefix("src/"),
                    spec.contracts_path.removeprefix("src/"),
                ],
                "merge_ancestry_verified": True,
                "current_tree_verified": True,
                "package_verification_required": True,
            }
        )
    body = {
        "schema_version": 1,
        "record_type": "phase5-role-ancestry-index",
        "subject_commit": SUBJECT_COMMIT,
        "subject_tree": subject_tree,
        "repository": "https://github.com/kb4beast/hive-mind-os",
        "license": "MIT",
        "retrieved_at": RETRIEVED_AT,
        "roles": roles,
        "role_count": len(roles),
        "authenticated_independence_claimed": False,
        "release_ready": False,
        "production_ready": False,
        "promotion_authorized": False,
        "superiority_claimed": False,
    }
    return {**body, "index_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    index = build_index(repository)
    destination = repository / OUTPUT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(destination)
    print(index["index_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
