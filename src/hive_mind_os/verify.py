"""Immutable, isolated, receipt-backed verification for committed Git candidates."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping, Sequence, TypedDict
from uuid import uuid4

from .acceptance import AcceptanceSpecification
from .autonomy import AutonomyBudget
from .contracts import tool_intent_digest
from .curator import _is_test_path, _python_test_metrics
from .ledger import EvidenceLedger
from .models import RiskTier, Role
from .receipts import (
    FileReceiptValidator,
    ReceiptReference,
    path_traverses_link_or_reparse_point,
    portable_path_parts,
    sha256_digest,
)
from .sandbox import SandboxError, SandboxRunner, SandboxSpec, SandboxTimeout

_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CHECK_TIMEOUT_SECONDS = 30.0
_CHECK_MAX_OUTPUT_BYTES = 1_000_000
_POLICY_VERSION = "verify-immutable-v1"
_LFS_HEADER = b"version https://git-lfs.github.com/spec/v1\n"
_INTERPRETER_INLINE_FLAGS = frozenset({"-c", "-m", "-e", "--eval", "--print"})


class VerificationError(RuntimeError):
    """The requested verification could not be assembled safely."""


class _TestAnalysis(TypedDict):
    files: list[dict[str, object]]
    weakened: list[str]
    not_evaluated: list[str]


@dataclass(frozen=True, slots=True)
class VerificationReport:
    run_id: str
    verdict: str
    report_path: Path
    seal_sequence: int
    repository_read_sequence: int
    changed_paths: tuple[str, ...]
    undeclared_paths: tuple[str, ...]
    weakened_tests: tuple[str, ...]
    checks: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _GitChange:
    status: str
    paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"status": self.status, "paths": list(self.paths)}


def verify_repository(
    repository: str | Path,
    specification_path: str | Path,
    output: str | Path,
    candidate: str,
) -> VerificationReport:
    """Verify one full-SHA candidate without executing the caller's worktree.

    Input validation and acceptance sealing deliberately precede every candidate-object
    read.  Git object reads, checkouts, and command execution use separate fresh
    workspaces.  The only published success artifact is a self-verifying bundle that
    is renamed into place after all digests have been checked.
    """

    root = _validate_repository(repository)
    bundle = _validate_output(root, output)
    specification = _load_specification(specification_path)
    _validate_command(specification)
    if not specification.declared_paths:
        raise VerificationError("acceptance specification must declare changed paths")
    candidate_reference = _validate_candidate_reference(candidate)

    run_id = f"VERIFY-{uuid4()}"
    staging = Path(tempfile.mkdtemp(dir=bundle.parent, prefix=".hive-mind-verify-"))
    ledger: EvidenceLedger | None = None
    resolved: dict[str, object] | None = None
    try:
        ledger = EvidenceLedger(staging / "ledger.sqlite3")
        contract = _sealed_contract(specification, candidate_reference)
        seal_sequence = ledger.append_event(
            run_id,
            "verify.acceptance.sealed",
            "curator",
            {"contract": contract, "contract_digest": _digest_json(contract)},
        )

        _reject_unsupported_source_features(root)
        resolved = _resolve_objects(root, candidate_reference)
        repository_read_sequence = ledger.append_event(
            run_id,
            "verify.repository.objects.resolved",
            "curator",
            resolved,
        )
        _reject_unsupported_tree_features(root, str(resolved["base_commit"]))
        _reject_unsupported_tree_features(root, str(resolved["candidate_commit"]))

        workspace_root = staging / "private-workspaces"
        base_workspace = _materialize_workspace(
            root,
            str(resolved["base_commit"]),
            workspace_root / "base",
        )
        candidate_workspace = _materialize_workspace(
            root,
            str(resolved["candidate_commit"]),
            workspace_root / "candidate",
        )
        _verify_materialization(base_workspace, str(resolved["base_commit"]), str(resolved["base_tree"]))
        _verify_materialization(
            candidate_workspace,
            str(resolved["candidate_commit"]),
            str(resolved["candidate_tree"]),
        )
        # From this point forward all Git object reads come from the private
        # candidate clone; no later operation reads the caller's worktree.
        changes = _changes_from_objects(
            candidate_workspace,
            str(resolved["base_commit"]),
            str(resolved["candidate_commit"]),
        )
        changed_paths = tuple(sorted({path for change in changes for path in change.paths}))
        if not changed_paths:
            raise VerificationError("candidate commit contains no change from its parent")
        undeclared_paths = tuple(
            sorted(set(changed_paths) - set(specification.declared_paths))
        )
        test_analysis = _analyze_tests(
            candidate_workspace,
            str(resolved["base_commit"]),
            str(resolved["candidate_commit"]),
            changes,
        )
        weakened_tests = tuple(test_analysis["weakened"])
        checks = (
            _run_check(
                candidate_workspace,
                staging,
                run_id,
                specification,
                ledger,
                resolved,
            ),
        )
        _remove_workspace_root(workspace_root)

        accepted = (
            all(item["matched"] is True for item in checks)
            and not undeclared_paths
            and not weakened_tests
            and not test_analysis["not_evaluated"]
        )
        verdict = "adopt" if accepted else "reject"
        ledger.append_event(
            run_id,
            "verify.completed",
            "curator",
            {
                "verdict": verdict,
                "undeclared_paths": list(undeclared_paths),
                "weakened_tests": list(weakened_tests),
                "not_evaluated_tests": list(test_analysis["not_evaluated"]),
            },
        )
        document = {
            "schema_version": 2,
            "run_id": run_id,
            "verdict": verdict,
            "policy_version": _POLICY_VERSION,
            "seal_sequence": seal_sequence,
            "repository_read_sequence": repository_read_sequence,
            "contract": contract,
            "candidate": {
                "reference": candidate_reference,
                "commit": resolved["candidate_commit"],
                "tree": resolved["candidate_tree"],
            },
            "base": {
                "commit": resolved["base_commit"],
                "tree": resolved["base_tree"],
            },
            "repository": resolved["repository"],
            "materialization": {
                "base": {
                    "commit": resolved["base_commit"],
                    "tree": resolved["base_tree"],
                    "detached": True,
                },
                "candidate": {
                    "commit": resolved["candidate_commit"],
                    "tree": resolved["candidate_tree"],
                    "detached": True,
                },
                "source_worktree_used_for_execution": False,
            },
            "changed_paths": list(changed_paths),
            "changes": [change.to_dict() for change in changes],
            "undeclared_paths": list(undeclared_paths),
            "weakened_tests": list(weakened_tests),
            "test_analysis": test_analysis,
            "checks": list(checks),
            "ledger_events": ledger.events(run_id),
        }
        _atomic_write_json(staging / "acceptance.json", specification.to_dict())
        _atomic_write_json(staging / "objects.json", resolved)
        _atomic_write_json(
            staging / "changed-paths.json",
            {
                "changed_paths": list(changed_paths),
                "changes": [change.to_dict() for change in changes],
            },
        )
        _atomic_write_json(staging / "environment.json", contract["environment"])
        _atomic_write_json(staging / "tool-versions.json", contract["tool"])
        _atomic_write_json(staging / "verification.json", document)
        ledger.close()
        ledger = None
        _write_integrity_manifest(staging)
        _self_verify_bundle(staging)
        _publish_bundle(staging, bundle)
        report_path = bundle / "verification.json"
        return VerificationReport(
            run_id=run_id,
            verdict=verdict,
            report_path=report_path,
            seal_sequence=seal_sequence,
            repository_read_sequence=repository_read_sequence,
            changed_paths=changed_paths,
            undeclared_paths=undeclared_paths,
            weakened_tests=weakened_tests,
            checks=checks,
        )
    except BaseException as error:
        if ledger is not None:
            ledger.close()
        _publish_failure_evidence(staging, bundle, run_id, error, resolved)
        raise


def verify_bundle(bundle: str | Path) -> None:
    """Raise ``VerificationError`` unless an evidence bundle is internally coherent."""

    root = Path(bundle)
    if not root.is_dir() or root.is_symlink() or path_traverses_link_or_reparse_point(root):
        raise VerificationError("verification bundle must be a regular directory")
    manifest_path = root / "integrity.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"integrity manifest is unreadable: {error}") from None
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise VerificationError("integrity manifest schema is unsupported")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise VerificationError("integrity manifest has no file digests")
    observed = _bundle_file_digests(root, include_integrity=False)
    if files != observed:
        raise VerificationError("integrity manifest does not match bundle bytes")
    required = {
        "acceptance.json",
        "changed-paths.json",
        "environment.json",
        "ledger.sqlite3",
        "objects.json",
        "tool-versions.json",
        "verification.json",
    }
    if not required.issubset(files):
        raise VerificationError("integrity manifest is missing required evidence")
    document = _read_json_object(root / "verification.json", "verification report")
    objects = _read_json_object(root / "objects.json", "object manifest")
    acceptance = _read_json_object(root / "acceptance.json", "acceptance specification")
    try:
        specification = AcceptanceSpecification.from_dict(acceptance)
    except ValueError as error:
        raise VerificationError(f"bundled acceptance specification is invalid: {error}") from None
    candidate = document.get("candidate")
    base = document.get("base")
    contract = document.get("contract")
    if not isinstance(candidate, Mapping) or not isinstance(base, Mapping) or not isinstance(contract, Mapping):
        raise VerificationError("verification report lacks candidate, base, or contract binding")
    if candidate.get("commit") != objects.get("candidate_commit") or candidate.get("tree") != objects.get("candidate_tree"):
        raise VerificationError("candidate object binding is inconsistent")
    if base.get("commit") != objects.get("base_commit") or base.get("tree") != objects.get("base_tree"):
        raise VerificationError("base object binding is inconsistent")
    if contract.get("specification_digest") != specification.digest:
        raise VerificationError("sealed contract does not bind the acceptance specification")
    run_id = document.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise VerificationError("verification report has no run identifier")
    ledger = EvidenceLedger(root / "ledger.sqlite3")
    try:
        events = ledger.events(run_id)
    finally:
        ledger.close()
    if document.get("ledger_events") != events:
        raise VerificationError("verification report ledger events do not match the ledger")
    for label, binding in (("candidate", candidate), ("base", base)):
        for field in ("commit", "tree"):
            value = binding.get(field)
            if not isinstance(value, str) or _FULL_SHA.fullmatch(value) is None:
                raise VerificationError(f"{label} {field} is not a full immutable SHA")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise VerificationError("verification report contains no checks")
    trusted_receipts = root / "receipts"
    for check in checks:
        if not isinstance(check, Mapping):
            raise VerificationError("verification report contains an invalid check")
        if check.get("candidate_commit") != candidate.get("commit") or check.get("candidate_tree") != candidate.get("tree"):
            raise VerificationError("check is not bound to the candidate objects")
        receipt = check.get("receipt")
        binding = check.get("receipt_binding")
        if receipt is None:
            continue
        if not isinstance(receipt, Mapping) or not isinstance(binding, Mapping):
            raise VerificationError("check receipt binding is malformed")
        try:
            reference_path = receipt["path"]
            reference_digest = receipt["digest"]
            reference = ReceiptReference(str(reference_path), str(reference_digest))
            validator = FileReceiptValidator(trusted_receipts)
            validation = validator.validate(
                reference,
                mission_id=str(binding["mission_id"]),
                state_ref=str(binding["state_ref"]),
                actor_id=str(binding["actor_id"]),
                action_id=str(binding["action_id"]),
                action_kind="command",
                action_digest=str(binding["action_digest"]),
            )
        except (KeyError, ValueError, OSError) as error:
            raise VerificationError(f"check receipt cannot be validated: {error}") from None
        if not validation.valid:
            raise VerificationError(
                "check receipt is invalid: " + "; ".join(validation.issues)
            )
        receipt_document = _read_json_object(
            trusted_receipts / Path(*portable_path_parts(reference.path)),
            "check receipt",
        )
        execution = receipt_document.get("execution")
        acceptance_binding = (
            execution.get("acceptance_specification")
            if isinstance(execution, Mapping)
            else None
        )
        if not isinstance(acceptance_binding, Mapping) or (
            acceptance_binding.get("candidate_commit") != candidate.get("commit")
            or acceptance_binding.get("candidate_tree") != candidate.get("tree")
        ):
            raise VerificationError("check receipt is not bound to the candidate objects")


def _validate_repository(repository: str | Path) -> Path:
    supplied = Path(os.path.abspath(repository))
    if path_traverses_link_or_reparse_point(supplied):
        raise VerificationError("repository path must not traverse a symlink or junction")
    if not supplied.is_dir() or not (supplied / ".git").is_dir():
        raise VerificationError("repository must be an existing standalone Git worktree")
    return supplied.resolve()


def _validate_output(root: Path, output: str | Path) -> Path:
    bundle = Path(os.path.abspath(output))
    parent = bundle.parent
    if not parent.is_dir():
        raise VerificationError("output bundle parent must already exist")
    if path_traverses_link_or_reparse_point(parent):
        raise VerificationError("output bundle parent must not traverse a symlink or junction")
    if bundle.exists() or bundle.is_symlink():
        raise VerificationError("output bundle directory must not already exist")
    try:
        bundle.relative_to(root)
    except ValueError:
        return bundle
    raise VerificationError("output bundle directory must be outside the repository")


def _load_specification(path: str | Path) -> AcceptanceSpecification:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"acceptance specification is unreadable: {error}") from None
    if not isinstance(document, dict):
        raise VerificationError("acceptance specification must be a JSON object")
    try:
        return AcceptanceSpecification.from_dict(document)
    except ValueError as error:
        raise VerificationError(f"acceptance specification is invalid: {error}") from None


def _validate_command(specification: AcceptanceSpecification) -> None:
    executable = Path(specification.argv[0]).name.casefold().removesuffix(".exe")
    if executable in {"python", "python3", "pypy", "pypy3", "node", "ruby", "perl", "sh", "bash"} and any(
        argument in _INTERPRETER_INLINE_FLAGS for argument in specification.argv[1:]
    ):
        raise VerificationError("acceptance command must not use inline interpreter execution")


def _validate_candidate_reference(candidate: str) -> str:
    if not isinstance(candidate, str) or _FULL_SHA.fullmatch(candidate) is None:
        raise VerificationError("candidate must be a full 40-hex immutable commit SHA")
    return candidate.lower()


def _sealed_contract(
    specification: AcceptanceSpecification,
    candidate_reference: str,
) -> dict[str, object]:
    try:
        package_version = version("hive-mind-os")
    except PackageNotFoundError:
        package_version = "uninstalled-source"
    return {
        "schema_version": 1,
        "specification_digest": specification.digest,
        "candidate_reference": candidate_reference,
        "environment": {
            "inherited_allowlist": [],
            "fixed": dict(_verification_fixed_environment()),
            "credential_inheritance": "disabled",
        },
        "sandbox": {
            "profile": "process-sandbox-v1",
            "filesystem": "none",
            "network": "none",
            "timeout_s": _CHECK_TIMEOUT_SECONDS,
            "max_output_bytes": _CHECK_MAX_OUTPUT_BYTES,
        },
        "tool": {
            "hive_mind_os": package_version,
            "python": sys.version,
            "git": _git_version(),
        },
        "policy_version": _POLICY_VERSION,
    }


def _git_version() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise VerificationError("Git executable is unavailable")
    completed = subprocess.run(
        (str(Path(executable).resolve()), "--version"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise VerificationError("Git executable could not report its version")
    return completed.stdout.decode("utf-8", "strict").strip()


def _git_environment() -> dict[str, str]:
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "PATH": os.environ.get("PATH", ""),
    }
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC"):
            if name in os.environ:
                environment[name] = os.environ[name]
    return environment


def _verification_fixed_environment() -> tuple[tuple[str, str], ...]:
    """Minimal non-secret environment needed to start allowlisted tools on Windows."""

    values = [("PYTHONDONTWRITEBYTECODE", "1")]
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC"):
            value = os.environ.get(name)
            if value:
                values.append((name, value))
    return tuple(values)


def _git(root: Path, *arguments: str, allow_failure: bool = False) -> bytes:
    executable = shutil.which("git")
    if executable is None:
        raise VerificationError("Git executable is unavailable")
    completed = subprocess.run(
        (
            str(Path(executable).resolve()),
            "-C",
            str(root),
            "-c",
            "core.hooksPath=/dev/null" if os.name != "nt" else "core.hooksPath=NUL",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.eol=lf",
            *arguments,
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
        check=False,
        timeout=30,
    )
    if completed.returncode != 0 and not allow_failure:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise VerificationError(f"Git inspection failed: {detail}")
    return completed.stdout


def _git_text(root: Path, *arguments: str, allow_failure: bool = False) -> str:
    return _git(root, *arguments, allow_failure=allow_failure).decode("utf-8", "strict").strip()


def _reject_unsupported_source_features(root: Path) -> None:
    filters = _git_text(root, "config", "--local", "--get-regexp", r"^filter\.", allow_failure=True)
    if filters:
        raise VerificationError("repository-local clean, smudge, or process filters are unsupported")
    if _git_text(root, "config", "--local", "--get", "core.hooksPath", allow_failure=True):
        raise VerificationError("repository-local hooks configuration is unsupported")
    if _git_text(root, "config", "--local", "--bool", "core.sparseCheckout", allow_failure=True).casefold() == "true":
        raise VerificationError("sparse-checkout repositories are unsupported")
    hooks = root / ".git" / "hooks"
    if hooks.is_dir():
        active = [entry.name for entry in hooks.iterdir() if not entry.name.endswith(".sample")]
        if active:
            raise VerificationError("repository-local Git hooks are unsupported")


def _resolve_objects(root: Path, candidate_reference: str) -> dict[str, object]:
    _git(root, "cat-file", "-e", f"{candidate_reference}^{{commit}}")
    candidate_commit = _git_text(root, "rev-parse", f"{candidate_reference}^{{commit}}")
    candidate_tree = _git_text(root, "rev-parse", f"{candidate_commit}^{{tree}}")
    parent_line = _git_text(root, "rev-list", "--parents", "-n", "1", candidate_commit)
    parts = parent_line.split()
    if len(parts) < 2:
        raise VerificationError("candidate commit must have a declared parent commit")
    base_commit = parts[1]
    base_tree = _git_text(root, "rev-parse", f"{base_commit}^{{tree}}")
    remote = _git_text(root, "config", "--local", "--get", "remote.origin.url", allow_failure=True)
    return {
        "candidate_reference": candidate_reference,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "base_commit": base_commit,
        "base_tree": base_tree,
        "repository": {
            "source_git_dir": str((root / ".git").resolve()),
            "origin": remote or None,
        },
    }


def _reject_unsupported_tree_features(root: Path, commit: str) -> None:
    entries = _tree_entries(root, commit)
    for mode, object_type, object_sha, relative in entries:
        if mode == "160000" or object_type == "commit":
            raise VerificationError("active Git submodules are unsupported")
        if mode == "120000":
            raise VerificationError(f"candidate contains unsupported symlink: {relative}")
        if relative == ".gitattributes":
            attributes = _git(root, "cat-file", "blob", object_sha)
            if b"filter=" in attributes:
                raise VerificationError("candidate attributes require an unsupported filter")
        if object_type == "blob":
            size = _git_text(root, "cat-file", "-s", object_sha)
            if int(size) <= 1024 and _git(root, "cat-file", "blob", object_sha).startswith(_LFS_HEADER):
                raise VerificationError(f"candidate contains Git LFS pointer content: {relative}")


def _tree_entries(root: Path, commit: str) -> list[tuple[str, str, str, str]]:
    raw = _git(root, "ls-tree", "-r", "-z", commit)
    entries: list[tuple[str, str, str, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            metadata, raw_path = item.split(b"\t", 1)
            mode, object_type, object_sha = metadata.decode("ascii").split(" ")
            relative = raw_path.decode("utf-8", "strict")
            portable_path_parts(relative)
        except (UnicodeDecodeError, ValueError) as error:
            raise VerificationError(f"Git tree contains an unsafe path: {error}") from None
        entries.append((mode, object_type, object_sha, relative))
    return entries


def _changes_from_objects(root: Path, base: str, candidate: str) -> tuple[_GitChange, ...]:
    raw = _git(root, "diff", "--name-status", "-z", "--find-renames", base, candidate)
    fields = [field for field in raw.split(b"\0") if field]
    changes: list[_GitChange] = []
    index = 0
    while index < len(fields):
        try:
            status = fields[index].decode("ascii")
        except UnicodeDecodeError as error:
            raise VerificationError(f"Git change status is invalid: {error}") from None
        index += 1
        path_count = 2 if status[:1] in {"R", "C"} else 1
        if index + path_count > len(fields):
            raise VerificationError("Git diff returned an incomplete changed-path record")
        paths: list[str] = []
        for raw_path in fields[index : index + path_count]:
            try:
                path = raw_path.decode("utf-8", "strict")
                portable_path_parts(path)
            except (UnicodeDecodeError, ValueError) as error:
                raise VerificationError(f"Git returned an unsafe changed path: {error}") from None
            paths.append(path)
        index += path_count
        changes.append(_GitChange(status=status, paths=tuple(paths)))
    return tuple(changes)


def _analyze_tests(
    root: Path,
    base: str,
    candidate: str,
    changes: Sequence[_GitChange],
) -> _TestAnalysis:
    weakened: list[str] = []
    not_evaluated: list[str] = []
    files: list[dict[str, object]] = []
    for change in changes:
        relevant_paths = change.paths
        if not any(_is_test_path(path) or _is_test_configuration(path) for path in relevant_paths):
            continue
        if any(_is_test_configuration(path) for path in relevant_paths):
            not_evaluated.extend(relevant_paths)
            files.append({"paths": list(relevant_paths), "finding": "not-evaluated", "reason": "test configuration changed"})
            continue
        before_path = relevant_paths[0]
        after_path = relevant_paths[-1]
        test_path = before_path if _is_test_path(before_path) else after_path
        if change.status.startswith("D") or (change.status.startswith("R") and _is_test_path(before_path)):
            weakened.append(before_path)
            files.append({"paths": list(relevant_paths), "finding": "fail", "reason": "test deleted or renamed"})
            continue
        if not test_path.endswith(".py"):
            not_evaluated.append(test_path)
            files.append({"paths": list(relevant_paths), "finding": "not-evaluated", "reason": "non-Python test analysis unsupported"})
            continue
        before = _git_optional_blob(root, base, before_path)
        after = _git_optional_blob(root, candidate, after_path)
        before_metrics = _python_test_metrics(before)
        after_metrics = _python_test_metrics(after)
        before_controls = _python_test_controls(before)
        after_controls = _python_test_controls(after)
        retained = len(before_metrics["assertion_signatures"] & after_metrics["assertion_signatures"])
        is_weakened = (
            retained < len(before_metrics["assertion_signatures"])
            or after_metrics["test_functions"] < before_metrics["test_functions"]
            or not before_controls["skips"].issuperset(after_controls["skips"])
        )
        if is_weakened:
            weakened.append(test_path)
        files.append(
            {
                "paths": list(relevant_paths),
                "finding": "fail" if is_weakened else "pass",
                "assertion_count_before": before_metrics["assertions"],
                "assertion_count_after": after_metrics["assertions"],
                "test_functions_before": before_metrics["test_functions"],
                "test_functions_after": after_metrics["test_functions"],
                "skip_decorators_before": sorted(before_controls["skips"]),
                "skip_decorators_after": sorted(after_controls["skips"]),
                "imports_before": sorted(before_controls["imports"]),
                "imports_after": sorted(after_controls["imports"]),
                "fixtures_before": sorted(before_controls["fixtures"]),
                "fixtures_after": sorted(after_controls["fixtures"]),
            }
        )
    return {
        "files": files,
        "weakened": sorted(set(weakened)),
        "not_evaluated": sorted(set(not_evaluated)),
    }


def _is_test_configuration(path: str) -> bool:
    return path in {"pytest.ini", "tox.ini", "noxfile.py", "conftest.py", "pyproject.toml"}


def _python_test_controls(content: bytes) -> dict[str, set[str]]:
    try:
        tree = ast.parse(content.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return {"skips": set(), "imports": set(), "fixtures": set()}
    skips: set[str] = set()
    imports: set[str] = set()
    fixtures: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                rendered = ast.unparse(decorator)
                lowered = rendered.casefold()
                if "skip" in lowered or "xfail" in lowered:
                    skips.add(rendered)
                if "fixture" in lowered:
                    fixtures.add(node.name)
    return {"skips": skips, "imports": imports, "fixtures": fixtures}


def _git_optional_blob(root: Path, commit: str, relative: str) -> bytes:
    return _git(root, "show", f"{commit}:{relative}", allow_failure=True)


def _materialize_workspace(source: Path, commit: str, destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise VerificationError("isolated workspace destination already exists")
    source_url = (source / ".git").resolve().as_uri()
    hooks_root = destination.parent / f"disabled-hooks-{uuid4()}"
    hooks_root.mkdir(parents=True)
    executable = shutil.which("git")
    if executable is None:
        raise VerificationError("Git executable is unavailable")
    completed = subprocess.run(
        (
            str(Path(executable).resolve()),
            "clone",
            "--no-local",
            "--no-hardlinks",
            "--no-checkout",
            "--config",
            f"core.hooksPath={hooks_root}",
            "--config",
            "core.autocrlf=false",
            "--config",
            "core.eol=lf",
            source_url,
            str(destination),
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise VerificationError(f"isolated Git clone failed: {detail}")
    _git(destination, "checkout", "--detach", "--force", commit)
    return destination


def _verify_materialization(workspace: Path, commit: str, tree: str) -> None:
    observed_commit = _git_text(workspace, "rev-parse", "HEAD")
    observed_tree = _git_text(workspace, "rev-parse", "HEAD^{tree}")
    symbolic = _git_text(workspace, "symbolic-ref", "-q", "HEAD", allow_failure=True)
    status = _git_text(workspace, "status", "--porcelain", "--untracked-files=all")
    if observed_commit != commit or observed_tree != tree or symbolic or status:
        raise VerificationError("isolated Git checkout does not exactly match the sealed object")


def _run_check(
    candidate_workspace: Path,
    staging: Path,
    run_id: str,
    specification: AcceptanceSpecification,
    ledger: EvidenceLedger,
    resolved: Mapping[str, object],
) -> dict[str, object]:
    executable_name = Path(specification.argv[0]).name
    state_ref = f"VERIFY_STATE:{resolved['candidate_commit']}:{resolved['candidate_tree']}"
    intent: dict[str, Any] = {
        "schema_version": 1,
        "action_id": f"ACT-{run_id}-0",
        "mission_id": run_id,
        "state_ref": state_ref,
        "actor_id": "verify-cli",
        "kind": "command",
        "description": (
            f"run sealed acceptance {specification.identifier} against immutable candidate "
            f"{resolved['candidate_commit']} tree {resolved['candidate_tree']}"
        ),
        "policy_decision_ref": f"POLICY-{_POLICY_VERSION}",
        "lease_id": f"LEASE-{run_id}-0",
        "idempotency_key": f"VERIFY-{resolved['candidate_commit']}-{specification.digest}",
        "rollback_ref": None,
        "status": "proposed",
        "command": {"argv": list(specification.argv), "path_args": []},
        "acceptance_specification": {
            "id": specification.identifier,
            "digest": specification.digest,
            "candidate_commit": resolved["candidate_commit"],
            "candidate_tree": resolved["candidate_tree"],
        },
    }
    intent["action_digest"] = tool_intent_digest(intent)
    runner = SandboxRunner(
        SandboxSpec(
            root=candidate_workspace,
            argv_allowlist=(executable_name,),
            fixed_environment=_verification_fixed_environment(),
            timeout_s=_CHECK_TIMEOUT_SECONDS,
            max_output_bytes=_CHECK_MAX_OUTPUT_BYTES,
        ),
        staging / "receipts",
        AutonomyBudget(
            max_episodes=1,
            max_tool_calls=1,
            max_compute_units=1.0,
            max_tool_calls_per_episode=1,
            max_compute_units_per_episode=1.0,
        ).issue_allowance(),
        role=Role.CURATOR,
        risk=RiskTier.MODERATE,
        runner_identity="verify-sandbox",
        ledger=ledger,
    )
    receipt: dict[str, object] | None = None
    error: str | None = None
    try:
        receipt = runner.run(intent)
    except SandboxTimeout as timeout:
        receipt = timeout.receipt
    except SandboxError as failure:
        error = str(failure)
    workspace_matches = _workspace_still_matches(
        candidate_workspace,
        str(resolved["candidate_commit"]),
        str(resolved["candidate_tree"]),
    )
    execution = receipt.get("execution", {}) if isinstance(receipt, Mapping) else {}
    outcome = execution.get("outcome") if isinstance(execution, Mapping) else None
    truncated = bool(
        isinstance(execution, Mapping)
        and (
            bool(execution.get("stdout", {}).get("truncated"))
            or bool(execution.get("stderr", {}).get("truncated"))
        )
    )
    matched = (
        receipt is not None
        and receipt.get("result") == specification.expected
        and workspace_matches
    )
    reference = runner.last_reference
    return {
        "id": specification.identifier,
        "expected": specification.expected,
        "matched": matched,
        "error": error,
        "outcome": outcome,
        "output_truncated": truncated,
        "candidate_commit": resolved["candidate_commit"],
        "candidate_tree": resolved["candidate_tree"],
        "workspace_unchanged": workspace_matches,
        "receipt": None if reference is None else {"path": reference.path, "digest": reference.digest},
        "receipt_binding": None
        if receipt is None
        else {
            "mission_id": receipt["mission_id"],
            "state_ref": receipt["state_ref"],
            "actor_id": receipt["actor_id"],
            "action_id": receipt["action_id"],
            "action_digest": receipt["action_digest"],
        },
    }


def _workspace_still_matches(workspace: Path, commit: str, tree: str) -> bool:
    try:
        return (
            _git_text(workspace, "rev-parse", "HEAD") == commit
            and _git_text(workspace, "rev-parse", "HEAD^{tree}") == tree
            and not _git_text(
                workspace,
                "status",
                "--porcelain",
                "--untracked-files=all",
            )
        )
    except VerificationError:
        return False


def _remove_workspace_root(workspace_root: Path) -> None:
    if workspace_root.exists():
        _rmtree(workspace_root)


def _rmtree(path: Path) -> None:
    """Remove verifier-private files, including read-only Git pack files on Windows."""

    def make_writable(function: object, name: str, _error: object) -> None:
        try:
            os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
            function(name)  # type: ignore[operator]
        except OSError:
            raise

    for attempt in range(3):
        try:
            # ``onexc`` was added in Python 3.12.  The public package supports
            # Python 3.11 too, where the equivalent callback is ``onerror``.
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=make_writable)
            else:
                shutil.rmtree(path, onerror=make_writable)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)


def _atomic_write_json(destination: Path, document: object) -> None:
    _atomic_write(destination, json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=destination.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_integrity_manifest(staging: Path) -> None:
    _atomic_write_json(
        staging / "integrity.json",
        {"schema_version": 1, "files": _bundle_file_digests(staging, include_integrity=False)},
    )


def _bundle_file_digests(root: Path, *, include_integrity: bool) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise VerificationError("evidence bundle contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not include_integrity and relative == "integrity.json":
            continue
        try:
            portable_path_parts(relative)
        except ValueError as error:
            raise VerificationError(f"evidence bundle path is unsafe: {error}") from None
        files[relative] = sha256_digest(path.read_bytes())
    return files


def _self_verify_bundle(staging: Path) -> None:
    verify_bundle(staging)


def _publish_bundle(staging: Path, bundle: Path) -> None:
    if bundle.exists() or bundle.is_symlink():
        raise VerificationError("output bundle directory appeared before atomic publication")
    os.replace(staging, bundle)


def _publish_failure_evidence(
    staging: Path,
    bundle: Path,
    run_id: str,
    error: BaseException,
    resolved: Mapping[str, object] | None,
) -> None:
    try:
        failure_root = bundle.parent / f"{bundle.name}.failed-{run_id}"
        if failure_root.exists() or failure_root.is_symlink():
            return
        failed_stage = Path(tempfile.mkdtemp(dir=bundle.parent, prefix=".hive-mind-verify-failure-"))
        _atomic_write_json(
            failed_stage / "failure.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "resolved_objects": dict(resolved) if resolved is not None else None,
            },
        )
        for name in ("ledger.sqlite3", "receipts"):
            source = staging / name
            if source.is_file():
                shutil.copy2(source, failed_stage / name)
            elif source.is_dir():
                shutil.copytree(source, failed_stage / name)
        os.replace(failed_stage, failure_root)
    finally:
        if staging.exists():
            _rmtree(staging)


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{label} is unreadable: {error}") from None
    if not isinstance(document, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return document


def _digest_json(document: Mapping[str, object]) -> str:
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return f"sha256:{sha256(raw).hexdigest()}"
