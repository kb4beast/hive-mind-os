from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MANIFEST_PATH = Path("docs/releases/version_1.1-manifest.json")
EXPECTED_ACCEPTED_STACK = (28, 29, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42)
EXPECTED_ROLES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "cross-examiner",
    "curator",
    "integrator",
    "steward",
    "optimizer",
    "judge",
)
TEMPORARY_EXPORT_WORKFLOW = Path(".github/workflows/export-source-bundle.yml")


@dataclass(frozen=True, slots=True)
class AuditResult:
    valid: bool
    issues: tuple[str, ...]
    report: dict[str, Any]


class DuplicateJsonKey(ValueError):
    """Raised when a supposedly canonical JSON object repeats a member name."""


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def load_json_strict(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _run_git(repository: Path, arguments: Sequence[str], *, check: bool = True) -> str:
    process = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return process.stdout.strip()


def _is_ancestor(repository: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    process = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode == 0:
        return True
    if process.returncode == 1:
        return False
    detail = process.stderr.strip() or process.stdout.strip()
    raise RuntimeError(f"git merge-base failed for {ancestor}: {detail}")


def _expect(condition: bool, issue: str, issues: list[str]) -> None:
    if not condition:
        issues.append(issue)


def _mapping(value: Any, label: str, issues: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        issues.append(f"{label} must be an object")
        return {}
    return value


def _list(value: Any, label: str, issues: list[str]) -> list[Any]:
    if not isinstance(value, list):
        issues.append(f"{label} must be an array")
        return []
    return value


def _read_text(repository: Path, relative: str, issues: list[str]) -> str:
    path = repository / relative
    if not path.is_file():
        issues.append(f"missing required file: {relative}")
        return ""
    return path.read_text(encoding="utf-8")


def _critical_paths(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    evidence = manifest.get("evidence", {})
    handoffs = manifest.get("handoffs", {})
    superseded = manifest.get("superseded_historical_prs", [])
    paths = {
        MANIFEST_PATH.as_posix(),
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "tests/test_governance.py",
        "tests/test_release_integration.py",
        "scripts/release_integration_audit.py",
        "docs/releases/version_1.1-integration.md",
        "docs/architecture/ADR_INDEX.md",
        "docs/architecture/ADR-026-OBSIDIAN-VAULT-REFRESH-CONFORMANCE.md",
        "docs/architecture/ADR-021-PR30-QUARANTINED-V2-FOUNDATION-NAMESPACE.md",
        "docs/architecture/PR30_SUPERSESSION_AND_DISPOSITION.md",
    }
    if isinstance(evidence, Mapping):
        for key in (
            "integration_court",
            "procedural_role_review",
            "inventory_reconciliation",
        ):
            value = evidence.get(key)
            if isinstance(value, str):
                paths.add(value)
    if isinstance(handoffs, Mapping):
        for value in handoffs.values():
            if isinstance(value, str):
                paths.add(value)
    if isinstance(superseded, list):
        for item in superseded:
            if isinstance(item, Mapping):
                value = item.get("disposition_record")
                if isinstance(value, str):
                    paths.add(value)
    return tuple(sorted(paths))


def audit_repository(
    repository: Path,
    *,
    require_git_ancestry: bool,
    allow_pending_pr30_merge: bool = False,
    allow_bootstrap_workflow: bool = False,
) -> AuditResult:
    repository = repository.resolve()
    issues: list[str] = []
    manifest_file = repository / MANIFEST_PATH
    if not manifest_file.is_file():
        return AuditResult(False, (f"missing {MANIFEST_PATH.as_posix()}",), {})
    try:
        manifest_value = load_json_strict(manifest_file)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return AuditResult(False, (f"manifest is not strict JSON: {error}",), {})
    manifest = _mapping(manifest_value, "manifest", issues)

    _expect(manifest.get("schema_version") == 1, "manifest schema_version must be 1", issues)
    _expect(
        manifest.get("manifest_kind") == "hive-mind-os-integration-train",
        "manifest_kind is not the integration-train contract",
        issues,
    )
    _expect(manifest.get("integration_train") == "1.1", "integration_train must be 1.1", issues)
    _expect(
        manifest.get("integration_train_is_distribution_version") is False,
        "integration train must not be represented as the distribution version",
        issues,
    )

    distribution = _mapping(manifest.get("distribution"), "distribution", issues)
    project_file = repository / "pyproject.toml"
    try:
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        issues.append(f"pyproject.toml is unavailable or invalid: {error}")
        project = {}
    project_metadata = project.get("project", {}) if isinstance(project, Mapping) else {}
    build_system = project.get("build-system", {}) if isinstance(project, Mapping) else {}
    if not isinstance(project_metadata, Mapping):
        project_metadata = {}
    if not isinstance(build_system, Mapping):
        build_system = {}
    _expect(distribution.get("name") == project_metadata.get("name"), "manifest/project name mismatch", issues)
    _expect(
        distribution.get("version") == project_metadata.get("version"),
        "manifest/project distribution version mismatch",
        issues,
    )
    _expect(
        distribution.get("build_backend") == build_system.get("build-backend"),
        "manifest/project build backend mismatch",
        issues,
    )
    _expect(
        distribution.get("build_requirements") == build_system.get("requires"),
        "manifest/project exact build requirements mismatch",
        issues,
    )
    _expect(
        build_system.get("requires") == ["setuptools==83.0.0"],
        "selected build requirement must be exactly setuptools==83.0.0",
        issues,
    )

    accepted = _list(manifest.get("accepted_stacked_prs"), "accepted_stacked_prs", issues)
    accepted_numbers = tuple(
        item.get("number") for item in accepted if isinstance(item, Mapping)
    )
    _expect(
        accepted_numbers == EXPECTED_ACCEPTED_STACK,
        f"accepted stack must be exactly {EXPECTED_ACCEPTED_STACK}",
        issues,
    )
    _expect(30 not in accepted_numbers, "PR #30 cannot be misclassified as accepted stack input", issues)

    superseded = _list(
        manifest.get("superseded_historical_prs"),
        "superseded_historical_prs",
        issues,
    )
    pr30 = next(
        (
            item
            for item in superseded
            if isinstance(item, Mapping) and item.get("number") == 30
        ),
        None,
    )
    _expect(pr30 is not None, "PR #30 supersession record is missing", issues)
    if isinstance(pr30, Mapping):
        _expect(
            pr30.get("head") == "39e07c9e3c3ce439911481be2d38d901d05d4824",
            "PR #30 exact head is wrong",
            issues,
        )
        _expect(
            pr30.get("posture") == "superseded-but-preserved",
            "PR #30 posture must remain superseded-but-preserved",
            issues,
        )
        merge_commit = pr30.get("tree_neutral_merge_commit")
        if merge_commit is None and not allow_pending_pr30_merge:
            issues.append("PR #30 tree-neutral merge commit is not sealed")
        elif merge_commit is not None and not (
            isinstance(merge_commit, str) and len(merge_commit) == 40
        ):
            issues.append("PR #30 tree-neutral merge commit must be a full SHA")

    claims = _mapping(manifest.get("claims"), "claims", issues)
    for denied_claim in (
        "main_modified",
        "source_prs_closed_or_merged",
        "source_branches_deleted_or_rewritten",
        "runtime_activation_authorized",
        "production_ready",
        "release_ready",
        "explorer_comparison_complete",
        "value_claimed",
        "learning_authorized",
        "promotion_authorized",
        "superiority_claimed",
        "automatic_merge_authorized",
    ):
        _expect(claims.get(denied_claim) is False, f"claim {denied_claim} must be false", issues)

    for forbidden in _list(manifest.get("forbidden_active_paths"), "forbidden_active_paths", issues):
        if isinstance(forbidden, str):
            _expect(not (repository / forbidden).exists(), f"obsolete active path exists: {forbidden}", issues)

    handoffs = _mapping(manifest.get("handoffs"), "handoffs", issues)
    stale_path = handoffs.get("superseded")
    current_path = handoffs.get("current")
    stale_text = _read_text(repository, str(stale_path), issues) if isinstance(stale_path, str) else ""
    current_text = _read_text(repository, str(current_path), issues) if isinstance(current_path, str) else ""
    _expect(stale_text.startswith("> **SUPERSEDED — DO NOT EXECUTE.**"), "stale Phase 3 handoff is not fail-closed", issues)
    for required in (
        "conservative reconstruction",
        "0cbf581b77b77c1cdc15879a05164674fd5ae3ec",
        "B-OPS-09",
        "no Explorer v2 versus Generation Zero comparison",
        "P20",
        "procedural role labels",
    ):
        _expect(required in current_text, f"Phase 5A handoff missing boundary: {required}", issues)

    adr_index = _read_text(repository, "docs/architecture/ADR_INDEX.md", issues)
    for required in ("ADR-021-PR30", "ADR-021-PR31", "three historical numeric collisions"):
        _expect(required in adr_index, f"ADR index missing {required}", issues)
    _expect(
        "ADR-026" in adr_index and "adapted for bounded stacked draft delivery" in adr_index,
        "ADR-026 index posture is stale",
        issues,
    )

    release_ledger = _read_text(repository, "docs/releases/version_1.1-integration.md", issues)
    for required in (
        "accepted stack #28, #29, and #31 through #42",
        "PR #30",
        "integration train 1.1",
        "distribution remains `0.6.0`",
        "archive/release-version_1.1-pre-hardening-2026-07-30",
        "No merge is authorized",
    ):
        _expect(required in release_ledger, f"release ledger missing: {required}", issues)

    evidence_manifest = _mapping(manifest.get("evidence"), "evidence", issues)
    reconciliation_path_value = evidence_manifest.get("inventory_reconciliation")
    reconciliation_value: Any = {}
    if isinstance(reconciliation_path_value, str):
        try:
            reconciliation_value = load_json_strict(
                repository / reconciliation_path_value
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            issues.append(f"inventory reconciliation is unavailable or invalid: {error}")
    reconciliation = _mapping(
        reconciliation_value, "inventory reconciliation", issues
    )
    _expect(
        reconciliation.get("historical_evidence_rewritten") is False,
        "inventory reconciliation cannot claim historical evidence was rewritten",
        issues,
    )
    _expect(
        reconciliation.get("runtime_activation_changed") is False,
        "inventory reconciliation cannot activate runtime behavior",
        issues,
    )
    for entry in _list(reconciliation.get("entries"), "inventory entries", issues):
        if not isinstance(entry, Mapping):
            issues.append("inventory reconciliation entry must be an object")
            continue
        relative = entry.get("path")
        expected_digest = entry.get("integrated_tree_digest")
        historical_digest = entry.get("historical_digest")
        if not isinstance(relative, str):
            issues.append("inventory reconciliation path must be text")
            continue
        try:
            current_inventory = load_json_strict(repository / relative)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            issues.append(f"reconciled inventory is unavailable: {relative}: {error}")
            continue
        if not isinstance(current_inventory, Mapping):
            issues.append(f"reconciled inventory is not an object: {relative}")
            continue
        _expect(
            current_inventory.get("inventory_digest") == expected_digest,
            f"reconciled inventory digest mismatch: {relative}",
            issues,
        )
        _expect(
            historical_digest != expected_digest,
            f"reconciliation entry does not distinguish historical/current: {relative}",
            issues,
        )
    phase4a_digest = next(
        (
            item.get("integrated_tree_digest")
            for item in reconciliation.get("entries", [])
            if isinstance(item, Mapping) and item.get("phase") == "phase4A"
        ),
        None,
    )
    phase4b_digest = next(
        (
            item.get("integrated_tree_digest")
            for item in reconciliation.get("entries", [])
            if isinstance(item, Mapping) and item.get("phase") == "phase4B"
        ),
        None,
    )
    phase4c_digest = next(
        (
            item.get("integrated_tree_digest")
            for item in reconciliation.get("entries", [])
            if isinstance(item, Mapping) and item.get("phase") == "phase4C"
        ),
        None,
    )
    for script, constant in (
        ("scripts/phase4b_explorer_successor_inventory.py", phase4a_digest),
        ("scripts/phase4c_explorer_behavior_inventory.py", phase4b_digest),
        ("scripts/phase4d_explorer_idea_lifecycle_inventory.py", phase4c_digest),
    ):
        script_text = _read_text(repository, script, issues)
        _expect(
            isinstance(constant, str) and constant in script_text,
            f"downstream inventory input constant is stale: {script}",
            issues,
        )

    role_path_value = evidence_manifest.get("procedural_role_review")
    role_value: Any = {}
    if isinstance(role_path_value, str):
        role_path = repository / role_path_value
        try:
            role_value = load_json_strict(role_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            issues.append(f"procedural role review is unavailable or invalid: {error}")
    role_review = _mapping(role_value, "procedural role review", issues)
    independence = _mapping(role_review.get("independence"), "role independence", issues)
    _expect(
        independence.get("authenticated_distinct_actors") is False,
        "procedural review must not claim authenticated independent actors",
        issues,
    )
    roles = _list(role_review.get("roles"), "roles", issues)
    observed_roles = tuple(item.get("role") for item in roles if isinstance(item, Mapping))
    _expect(observed_roles == EXPECTED_ROLES, f"role review must be exactly {EXPECTED_ROLES}", issues)
    identities = [item.get("identity") for item in roles if isinstance(item, Mapping)]
    identity_labels = [value for value in identities if isinstance(value, str)]
    _expect(
        len(identity_labels) == len(identities),
        "procedural role identities must be text labels",
        issues,
    )
    _expect(
        len(identity_labels) == len(set(identity_labels)),
        "procedural role identities must be distinct labels",
        issues,
    )

    workflow_text = _read_text(repository, ".github/workflows/ci.yml", issues)
    if not allow_bootstrap_workflow:
        _expect(
            not (repository / TEMPORARY_EXPORT_WORKFLOW).exists(),
            "temporary source-export workflow remains in selected tree",
            issues,
        )
    for required in (
        "scripts/release_integration_audit.py",
        "dist/release-version-1.1-audit.json",
        "PACKAGE_VERSION",
        "Attest wheel, SBOM, and release audit provenance",
    ):
        _expect(required in workflow_text, f"CI missing release evidence binding: {required}", issues)
    _expect(
        "--source-version 0.6.0" not in workflow_text,
        "SBOM source version remains a duplicated hard-coded literal",
        issues,
    )

    head = None
    tree = None
    parents: list[str] = []
    ancestry: dict[str, bool] = {}
    merge_details: dict[str, Any] | None = None
    if require_git_ancestry:
        try:
            head = _run_git(repository, ["rev-parse", "HEAD"])
            tree = _run_git(repository, ["rev-parse", "HEAD^{tree}"])
            parent_line = _run_git(repository, ["rev-list", "--parents", "-n", "1", "HEAD"])
            parents = parent_line.split()[1:]
            required_ancestors = _list(
                manifest.get("required_ancestor_commits"),
                "required_ancestor_commits",
                issues,
            )
            for commit in required_ancestors:
                if not isinstance(commit, str):
                    issues.append("required ancestor is not a SHA string")
                    continue
                try:
                    present = _is_ancestor(repository, commit)
                except RuntimeError as error:
                    issues.append(str(error))
                    present = False
                ancestry[commit] = present
                _expect(present, f"required commit is not an ancestor of HEAD: {commit}", issues)
            if isinstance(pr30, Mapping):
                merge_commit = pr30.get("tree_neutral_merge_commit")
                if isinstance(merge_commit, str) and len(merge_commit) == 40:
                    merge_line = _run_git(
                        repository,
                        ["rev-list", "--parents", "-n", "1", merge_commit],
                    ).split()
                    merge_parents = merge_line[1:]
                    merge_tree = _run_git(repository, ["rev-parse", f"{merge_commit}^{{tree}}"])
                    first_parent_tree = (
                        _run_git(repository, ["rev-parse", f"{merge_parents[0]}^{{tree}}"])
                        if merge_parents
                        else None
                    )
                    merge_details = {
                        "commit": merge_commit,
                        "parents": merge_parents,
                        "tree": merge_tree,
                        "first_parent_tree": first_parent_tree,
                    }
                    _expect(len(merge_parents) >= 2, "PR #30 preservation commit is not a merge", issues)
                    _expect(
                        "39e07c9e3c3ce439911481be2d38d901d05d4824" in merge_parents,
                        "PR #30 exact head is not a parent of its preservation merge",
                        issues,
                    )
                    _expect(
                        merge_tree == first_parent_tree,
                        "PR #30 preservation merge changed the selected file tree",
                        issues,
                    )
                    _expect(
                        _is_ancestor(repository, merge_commit),
                        "PR #30 preservation merge is not an ancestor of HEAD",
                        issues,
                    )
            tracked_status = _run_git(repository, ["status", "--porcelain", "--untracked-files=no"])
            _expect(not tracked_status, "tracked working tree is not clean", issues)
        except RuntimeError as error:
            issues.append(str(error))

    critical_digests: dict[str, str] = {}
    for relative in _critical_paths(manifest):
        path = repository / relative
        if path.is_file():
            critical_digests[relative] = sha256_file(path)
        else:
            issues.append(f"critical evidence file missing: {relative}")

    report = {
        "schema_version": 1,
        "audit_kind": "hive-mind-os-release-integration",
        "valid": not issues,
        "issues": list(dict.fromkeys(issues)),
        "subject": {
            "commit_sha": head,
            "tree_sha": tree,
            "parents": parents,
            "integration_train": manifest.get("integration_train"),
            "distribution": dict(distribution),
        },
        "manifest_digest": sha256_bytes(canonical_json_bytes(manifest)),
        "required_ancestor_results": ancestry,
        "pr30_tree_neutral_merge": merge_details,
        "critical_file_digests": critical_digests,
        "claims": dict(claims),
    }
    return AuditResult(not issues, tuple(dict.fromkeys(issues)), report)


def _parse_args(arguments: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the exact Version 1.1 integration tree")
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-git-ancestry", action="store_true")
    parser.add_argument("--allow-pending-pr30-merge", action="store_true")
    parser.add_argument("--allow-bootstrap-workflow", action="store_true")
    return parser.parse_args(arguments)


def main(arguments: Iterable[str] | None = None) -> int:
    options = _parse_args(arguments)
    result = audit_repository(
        options.repository,
        require_git_ancestry=not options.no_git_ancestry,
        allow_pending_pr30_merge=options.allow_pending_pr30_merge,
        allow_bootstrap_workflow=options.allow_bootstrap_workflow,
    )
    rendered = json.dumps(result.report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if options.output is not None:
        output = options.output
        if not output.is_absolute():
            output = options.repository / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(rendered)
    if not result.valid:
        for issue in result.issues:
            print(f"release-integration-audit: {issue}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
