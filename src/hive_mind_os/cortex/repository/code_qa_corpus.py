"""Deterministic, authority-bound code-to-QA corpus.

The corpus is intentionally small and local.  It proves that a Builder action
can change source through the real authority/effect/adapter boundary and that
the deterministic local evaluator mechanically binds public and sealed checks
to the resulting candidate.  The evaluator is same-trust, not independent.
The included Builder is a scripted test double, not a model, provider, or
production qualification.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence, cast

from ...brain_kernel.authority import AuthorityRegistry
from ...brain_kernel.builder import (
    BuilderAction,
    BuilderActionKind,
    BuilderCoordinator,
)
from ...brain_kernel.canonical import canonical_bytes, canonical_digest
from ...brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from ...brain_kernel.effects import EffectGateway
from .builder_adapter import IsolatedBuilderAdapter

SCHEMA_VERSION = 2
EVALUATOR_ID = "code-qa-corpus-v2-deterministic-local-evaluator"
BUILDER_ID = "code-qa-corpus-v2-scripted-builder-test-double"
QUALIFICATION = "deterministic-test-double-only-not-provider-or-production-qualified"
TRUST_MODEL = "unsandboxed-same-os-authority-local-development"
# evaluator-digest-excluded-bundle-pin-begin
PINNED_CORPUS_BUNDLE_DIGEST = (
    "sha256:13f0d3f8a7e34ca4b16d05b774fd22cfd52f255d8a01b5e3df8e97ed380961e7"
)
# evaluator-digest-excluded-bundle-pin-end
NOW = "2030-01-01T00:00:00Z"
EXPIRES = "2030-01-02T00:00:00Z"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TASK_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_PROTECTED_PREFIXES = ("tests/", ".git/", ".code-qa/", "evaluator/", "harness/")
_WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class CorpusDefinitionError(RuntimeError):
    """A corpus fixture is unsealed, ambiguous, or unsuitable for evaluation."""


class CandidateRejected(RuntimeError):
    """A candidate violates the sealed task or evidence boundary."""


def _sha256(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _normal_bytes(value: bytes) -> bytes:
    """Make text fixture seals independent of host newline translation."""

    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return value
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _portable_path(value: str) -> str:
    from ...brain_kernel.contracts import normalize_portable_path

    return normalize_portable_path(value)


@dataclass(frozen=True, slots=True)
class _TreeScan:
    files: Mapping[str, bytes]
    directories: tuple[str, ...]


def _link_like(path: Path, observed: os.stat_result | None = None) -> bool:
    information = observed or os.lstat(path)
    is_junction = getattr(path, "is_junction", None)
    return (
        stat.S_ISLNK(information.st_mode)
        or bool(getattr(information, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT)
        or bool(callable(is_junction) and is_junction())
    )


def _windows_alias(value: str) -> str:
    parts = value.split("/")
    if any(part.rstrip(" .") != part or ":" in part for part in parts):
        raise CorpusDefinitionError("corpus path has an unsafe Windows alias")
    return "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)


def _assert_casefold_unique(paths: Sequence[str]) -> None:
    aliases: dict[str, str] = {}
    for path in paths:
        alias = _windows_alias(path)
        prior = aliases.setdefault(alias, path)
        if prior != path:
            raise CorpusDefinitionError(
                f"corpus inventory contains a casefold alias collision: {prior}, {path}"
            )


def _assert_no_link_like_components(
    path: Path, *, label: str, allow_missing: bool
) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    components = absolute.parts[1:] if absolute.anchor else absolute.parts
    for component in components:
        current /= component
        try:
            observed = os.lstat(current)
        except FileNotFoundError:
            if allow_missing:
                return
            raise CorpusDefinitionError(
                f"{label} has a missing path component"
            ) from None
        except OSError as error:
            raise CorpusDefinitionError(
                f"{label} path component cannot be inspected safely"
            ) from error
        if _link_like(current, observed):
            raise CorpusDefinitionError(
                f"{label} traverses a link, junction, or reparse point"
            )


def _scan_tree(root: str | Path) -> _TreeScan:
    base = Path(root).absolute()
    try:
        root_stat = os.lstat(base)
    except OSError as error:
        raise CorpusDefinitionError("repository fixture is unavailable") from error
    if not stat.S_ISDIR(root_stat.st_mode) or _link_like(base, root_stat):
        raise CorpusDefinitionError("corpus root is a link, junction, or reparse point")
    files: dict[str, bytes] = {}
    directories: list[str] = []

    def visit(directory: Path, prefix: tuple[str, ...]) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise CorpusDefinitionError(
                "corpus tree cannot be enumerated safely"
            ) from error
        for entry in entries:
            relative = _portable_path("/".join((*prefix, entry.name)))
            path = Path(entry.path)
            try:
                observed = os.lstat(path)
            except OSError as error:
                raise CorpusDefinitionError(
                    "corpus entry cannot be inspected safely"
                ) from error
            if _link_like(path, observed):
                raise CorpusDefinitionError(
                    f"corpus contains a link, junction, or reparse point: {relative}"
                )
            if stat.S_ISDIR(observed.st_mode):
                directories.append(relative)
                visit(path, (*prefix, entry.name))
            elif stat.S_ISREG(observed.st_mode):
                try:
                    files[relative] = path.read_bytes()
                except OSError as error:
                    raise CorpusDefinitionError(
                        "corpus file cannot be read safely"
                    ) from error
            else:
                raise CorpusDefinitionError(
                    f"corpus contains a non-regular entry: {relative}"
                )

    visit(base, ())
    _assert_casefold_unique((*directories, *files))
    return _TreeScan(MappingProxyType(files), tuple(sorted(directories)))


def file_inventory(root: str | Path) -> Mapping[str, bytes]:
    """Return a root-confined immutable inventory, rejecting links."""

    observed = _scan_tree(root)
    return MappingProxyType(
        {path: _normal_bytes(content) for path, content in observed.files.items()}
    )


def tree_digest(root: str | Path) -> str:
    """Seal the complete normalized file inventory below ``root``."""

    return _inventory_digest(file_inventory(root))


def _inventory_digest(inventory: Mapping[str, bytes]) -> str:
    return canonical_digest(
        [
            {"path": path, "content_digest": _sha256(content)}
            for path, content in sorted(inventory.items())
        ]
    )


def _public_checker_digest(repository: Path, test_paths: Sequence[str]) -> str:
    inventory = file_inventory(repository)
    checks = []
    for path in test_paths:
        if path not in inventory:
            raise CorpusDefinitionError(
                "public test is absent from the sealed baseline"
            )
        checks.append({"path": path, "digest": _sha256(inventory[path])})
    return canonical_digest(
        {"schema_version": SCHEMA_VERSION, "evaluator": EVALUATOR_ID, "checks": checks}
    )


def _hidden_checker_digest(checker_id: str, program: str) -> str:
    return canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "evaluator": EVALUATOR_ID,
            "checker_id": checker_id,
            "program": program,
        }
    )


@dataclass(frozen=True, slots=True)
class CandidateProposal:
    """A declarative candidate.  It has no workspace or evaluator handle."""

    proposal_id: str
    writes: Mapping[str, str]
    rationale: str
    deletions: tuple[str, ...] = ()
    claimed_candidate_digest: str | None = None
    claimed_effect_receipts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.rationale.strip():
            raise ValueError("candidate proposal id and rationale are required")
        normalized: dict[str, str] = {}
        for path, content in self.writes.items():
            target = _portable_path(path)
            if not isinstance(content, str):
                raise TypeError("candidate writes require string content")
            if target in normalized:
                raise ValueError("candidate write paths must be unique")
            normalized[target] = content
        object.__setattr__(self, "writes", MappingProxyType(normalized))
        object.__setattr__(
            self, "deletions", tuple(_portable_path(path) for path in self.deletions)
        )
        if (
            self.claimed_candidate_digest is not None
            and _DIGEST.fullmatch(self.claimed_candidate_digest) is None
        ):
            raise ValueError("claimed candidate digest is malformed")
        if any(
            _DIGEST.fullmatch(value) is None for value in self.claimed_effect_receipts
        ):
            raise ValueError("claimed effect receipt digest is malformed")

    @property
    def proposal_digest(self) -> str:
        return canonical_digest(
            {
                "proposal_id": self.proposal_id,
                "writes": dict(self.writes),
                "deletions": self.deletions,
                "rationale": self.rationale,
                "claimed_candidate_digest": self.claimed_candidate_digest,
                "claimed_effect_receipts": self.claimed_effect_receipts,
            }
        )


@dataclass(frozen=True, slots=True)
class AttemptFeedback:
    """Digest-only feedback; no hidden program, input, or expected value leaks."""

    disposition: str
    reason: str
    public_passed: bool
    hidden_passed: bool
    public_outcome_digest: str
    hidden_outcome_digest: str


@dataclass(frozen=True, slots=True)
class BuilderTaskView:
    """The complete lane-visible contract passed to a candidate Builder."""

    schema_version: int
    task_id: str
    shape: str
    objective: str
    allowed_write_paths: tuple[str, ...]
    public_test_paths: tuple[str, ...]
    public_check_digest: str
    hidden_check_digest: str
    baseline_tree_digest: str
    task_contract_digest: str
    visible_files: Mapping[str, str]
    qualification: str = QUALIFICATION


class CodeQABuilder(Protocol):
    identity: str
    qualification: str

    def propose(
        self, task: BuilderTaskView, feedback: tuple[AttemptFeedback, ...]
    ) -> CandidateProposal: ...


@dataclass(frozen=True, slots=True)
class TestOutcome:
    checker_kind: str
    checker_digest: str
    candidate_digest: str
    passed: bool
    returncode: int | None
    stdout_digest: str
    stderr_digest: str
    outcome_digest: str

    @classmethod
    def not_run(cls, checker_kind: str, checker_digest: str) -> TestOutcome:
        candidate = canonical_digest({"candidate": "not-run"})
        outcome = canonical_digest(
            {
                "checker_kind": checker_kind,
                "checker_digest": checker_digest,
                "candidate_digest": candidate,
                "passed": False,
                "returncode": None,
            }
        )
        empty = _sha256(b"")
        return cls(
            checker_kind,
            checker_digest,
            candidate,
            False,
            None,
            empty,
            empty,
            outcome,
        )


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    task_contract_digest: str
    baseline_tree_digest: str
    tree_digest: str
    diff_digest: str
    candidate_digest: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EffectEvidence:
    action_id: str
    intent_digest: str
    receipt_digest: str
    effect_status: str
    adapter_outcome_status: str
    adapter_output_digest: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_number: int
    proposal_id: str
    proposal_digest: str
    disposition: str
    reason: str
    workspace: str | None
    evidence: CandidateEvidence | None
    effects: tuple[EffectEvidence, ...]
    public_outcome: TestOutcome
    hidden_outcome: TestOutcome
    record_digest: str


@dataclass(frozen=True, slots=True)
class BaselineRecord:
    task_contract_digest: str
    tree_digest: str
    candidate_digest: str
    public_outcome: TestOutcome
    hidden_outcome: TestOutcome


@dataclass(frozen=True, slots=True)
class TaskRun:
    task_id: str
    shape: str
    task_contract_digest: str
    status: str
    builder_identity: str
    qualification: str
    baseline: BaselineRecord
    attempts: tuple[AttemptRecord, ...]
    result_digest: str


@dataclass(frozen=True, slots=True)
class CorpusRun:
    schema_version: int
    status: str
    scope: str
    bundle_digest: str
    pin_mode: str
    expected_task_ids: tuple[str, ...]
    selected_task_ids: tuple[str, ...]
    task_contract_digests: tuple[str, ...]
    task_runs: tuple[TaskRun, ...]
    corpus_digest: str
    evaluator_id: str = EVALUATOR_ID
    qualification: str = QUALIFICATION
    operationally_qualified: bool = False
    independent_evaluator: bool = False
    adaptive_intelligence: bool = False
    trust_model: str = TRUST_MODEL
    limitations: tuple[str, ...] = (
        "The bundled Builder is a deterministic scripted test double.",
        "Candidate and checker code execute unsandboxed with the caller's OS authority.",
        "Checker separation is same-trust interface separation, not independent custody.",
        "No adaptive intelligence, live model, provider, network, arbitrary repository, or production path is qualified.",
        "The three fixtures are bounded evidence, not a superiority claim.",
    )


@dataclass(frozen=True, slots=True)
class _PublicTask:
    task_id: str
    shape: str
    objective: str
    repository: Path
    allowed_write_paths: tuple[str, ...]
    public_test_paths: tuple[str, ...]
    baseline_tree_digest: str
    public_check_digest: str
    baseline_public_outcome_digest: str
    hidden_check_digest: str
    max_attempts: int
    task_contract_digest: str

    def builder_view(self) -> BuilderTaskView:
        visible = {
            path: content.decode("utf-8", errors="strict")
            for path, content in file_inventory(self.repository).items()
        }
        return BuilderTaskView(
            SCHEMA_VERSION,
            self.task_id,
            self.shape,
            self.objective,
            self.allowed_write_paths,
            self.public_test_paths,
            self.public_check_digest,
            self.hidden_check_digest,
            self.baseline_tree_digest,
            self.task_contract_digest,
            MappingProxyType(visible),
        )


@dataclass(frozen=True, slots=True)
class _SealedCheck:
    task_id: str
    checker_id: str
    program: str
    hidden_check_digest: str


@dataclass(frozen=True, slots=True)
class _TaskBundle:
    public: _PublicTask
    sealed: _SealedCheck


@dataclass(frozen=True, slots=True)
class _CorpusContract:
    bundle_digest: str
    task_ids: tuple[str, ...]
    task_contract_digests: tuple[str, ...]
    bundles: tuple[_TaskBundle, ...]


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON object key: {key}")
        document[key] = value
    return document


def _strict_object(path: Path, expected_keys: set[str]) -> dict[str, object]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise CorpusDefinitionError(f"invalid corpus document: {path.name}") from error
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise CorpusDefinitionError(
            f"unexpected fields in corpus document: {path.name}"
        )
    return document


def _strings(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise CorpusDefinitionError(f"{label} must be a non-empty string list")
    return tuple(cast(list[str], value))


def _load_task(task_root: Path) -> _TaskBundle:
    public_doc = _strict_object(
        task_root / "manifest.json",
        {
            "schema_version",
            "task_id",
            "shape",
            "objective",
            "allowed_write_paths",
            "public_test_paths",
            "baseline_tree_digest",
            "public_check_digest",
            "baseline_public_outcome_digest",
            "hidden_check_digest",
            "max_attempts",
            "qualification",
            "task_contract_digest",
        },
    )
    sealed_doc = _strict_object(
        task_root / "sealed-check.json",
        {"schema_version", "task_id", "checker_id", "program", "hidden_check_digest"},
    )
    if (
        public_doc["schema_version"] != SCHEMA_VERSION
        or sealed_doc["schema_version"] != SCHEMA_VERSION
    ):
        raise CorpusDefinitionError("unsupported code-QA fixture schema")
    if public_doc["qualification"] != QUALIFICATION:
        raise CorpusDefinitionError("fixture qualification label is missing")
    task_id = public_doc["task_id"]
    shape = public_doc["shape"]
    objective = public_doc["objective"]
    if not all(
        isinstance(value, str) and value for value in (task_id, shape, objective)
    ):
        raise CorpusDefinitionError("task identity, shape, and objective are required")
    if (
        not isinstance(task_id, str)
        or _TASK_ID.fullmatch(task_id) is None
        or task_id != task_root.name
    ):
        raise CorpusDefinitionError("task id is unsafe or differs from its directory")
    if sealed_doc["task_id"] != task_id:
        raise CorpusDefinitionError("sealed checker belongs to another task")
    raw_allowed = _strings(public_doc["allowed_write_paths"], "allowed_write_paths")
    raw_public_tests = _strings(public_doc["public_test_paths"], "public_test_paths")
    allowed = tuple(_portable_path(path) for path in raw_allowed)
    public_tests = tuple(_portable_path(path) for path in raw_public_tests)
    if allowed != raw_allowed or public_tests != raw_public_tests:
        raise CorpusDefinitionError(
            "fixture paths must use canonical portable spelling"
        )
    if len(set(allowed)) != len(allowed) or len(set(public_tests)) != len(public_tests):
        raise CorpusDefinitionError("fixture paths must be unique")
    if any(path.startswith(_PROTECTED_PREFIXES) for path in allowed):
        raise CorpusDefinitionError("allowed writes include a protected path")
    digests = (
        public_doc["baseline_tree_digest"],
        public_doc["public_check_digest"],
        public_doc["baseline_public_outcome_digest"],
        public_doc["hidden_check_digest"],
        sealed_doc["hidden_check_digest"],
        public_doc["task_contract_digest"],
    )
    if any(
        not isinstance(value, str) or _DIGEST.fullmatch(value) is None
        for value in digests
    ):
        raise CorpusDefinitionError("fixture digest is malformed")
    checker_id = sealed_doc["checker_id"]
    program = sealed_doc["program"]
    if (
        not isinstance(checker_id, str)
        or not checker_id
        or not isinstance(program, str)
        or not program
    ):
        raise CorpusDefinitionError("sealed checker is incomplete")
    hidden_digest = _hidden_checker_digest(checker_id, program)
    if (
        hidden_digest != public_doc["hidden_check_digest"]
        or hidden_digest != sealed_doc["hidden_check_digest"]
    ):
        raise CorpusDefinitionError("sealed hidden checker digest mismatch")
    repository = task_root / "repository"
    observed_tree = tree_digest(repository)
    if observed_tree != public_doc["baseline_tree_digest"]:
        raise CorpusDefinitionError("baseline tree digest mismatch")
    observed_public = _public_checker_digest(repository, public_tests)
    if observed_public != public_doc["public_check_digest"]:
        raise CorpusDefinitionError("public checker digest mismatch")
    max_attempts = public_doc["max_attempts"]
    if type(max_attempts) is not int or max_attempts < 1 or max_attempts > 5:
        raise CorpusDefinitionError("max_attempts must be between one and five")
    task_contract = canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "shape": shape,
            "objective": objective,
            "allowed_write_paths": allowed,
            "public_test_paths": public_tests,
            "baseline_tree_digest": observed_tree,
            "public_check_digest": observed_public,
            "baseline_public_outcome_digest": public_doc[
                "baseline_public_outcome_digest"
            ],
            "hidden_check_digest": hidden_digest,
            "max_attempts": max_attempts,
            "qualification": QUALIFICATION,
        }
    )
    if task_contract != public_doc["task_contract_digest"]:
        raise CorpusDefinitionError("task contract digest mismatch")
    public = _PublicTask(
        cast(str, task_id),
        cast(str, shape),
        cast(str, objective),
        repository,
        allowed,
        public_tests,
        cast(str, public_doc["baseline_tree_digest"]),
        cast(str, public_doc["public_check_digest"]),
        cast(str, public_doc["baseline_public_outcome_digest"]),
        hidden_digest,
        max_attempts,
        task_contract,
    )
    sealed = _SealedCheck(cast(str, task_id), checker_id, program, hidden_digest)
    return _TaskBundle(public, sealed)


def _evaluator_implementation_digest() -> str:
    source = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    normalized, replacements = re.subn(
        rb"(?ms)^# evaluator-digest-excluded-bundle-pin-begin\n.*?"
        rb"^# evaluator-digest-excluded-bundle-pin-end$",
        b"# evaluator-digest-excluded-bundle-pin-begin\n"
        b'PINNED_CORPUS_BUNDLE_DIGEST = "<SELF-EXCLUDED>"\n'
        b"# evaluator-digest-excluded-bundle-pin-end",
        source,
        count=1,
        flags=re.MULTILINE,
    )
    if replacements != 1:
        raise CorpusDefinitionError("evaluator implementation pin cannot be normalized")
    return _sha256(normalized)


def _load_corpus_contract(source: Path) -> _CorpusContract:
    observed = _scan_tree(source)
    manifest_path = source / "corpus-manifest.json"
    manifest = _strict_object(
        manifest_path,
        {
            "schema_version",
            "corpus_id",
            "evaluator_id",
            "evaluator_implementation_digest",
            "qualification",
            "trust_model",
            "tasks",
            "directories",
            "inventory",
            "bundle_digest",
        },
    )
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise CorpusDefinitionError("unsupported root corpus manifest schema")
    if manifest["corpus_id"] != "code-qa-v2-bounded-three-shape-corpus":
        raise CorpusDefinitionError("root corpus identity is invalid")
    if manifest["evaluator_id"] != EVALUATOR_ID:
        raise CorpusDefinitionError("root evaluator identity is invalid")
    if (
        manifest["qualification"] != QUALIFICATION
        or manifest["trust_model"] != TRUST_MODEL
    ):
        raise CorpusDefinitionError(
            "root corpus trust or qualification label is invalid"
        )
    evaluator_digest = manifest["evaluator_implementation_digest"]
    bundle_digest = manifest["bundle_digest"]
    if (
        not isinstance(evaluator_digest, str)
        or _DIGEST.fullmatch(evaluator_digest) is None
        or not isinstance(bundle_digest, str)
        or _DIGEST.fullmatch(bundle_digest) is None
    ):
        raise CorpusDefinitionError("root corpus digest is malformed")
    if evaluator_digest != _evaluator_implementation_digest():
        raise CorpusDefinitionError("evaluator implementation digest mismatch")

    task_rows = manifest["tasks"]
    if not isinstance(task_rows, list) or not task_rows:
        raise CorpusDefinitionError("root corpus task inventory is invalid")
    task_ids: list[str] = []
    task_contracts: list[str] = []
    for row in task_rows:
        if not isinstance(row, Mapping) or set(row) != {
            "task_id",
            "task_contract_digest",
        }:
            raise CorpusDefinitionError("root corpus task row is invalid")
        task_id = row["task_id"]
        contract = row["task_contract_digest"]
        if (
            not isinstance(task_id, str)
            or _TASK_ID.fullmatch(task_id) is None
            or not isinstance(contract, str)
            or _DIGEST.fullmatch(contract) is None
        ):
            raise CorpusDefinitionError("root corpus task row is malformed")
        task_ids.append(task_id)
        task_contracts.append(contract)
    if task_ids != sorted(set(task_ids)):
        raise CorpusDefinitionError(
            "root corpus task rows are not canonical and unique"
        )

    directory_rows = manifest["directories"]
    if (
        not isinstance(directory_rows, list)
        or any(not isinstance(value, str) for value in directory_rows)
        or directory_rows != sorted(set(directory_rows))
    ):
        raise CorpusDefinitionError("root corpus directory inventory is invalid")
    normalized_directories = tuple(
        _portable_path(cast(str, value)) for value in directory_rows
    )
    if normalized_directories != tuple(directory_rows):
        raise CorpusDefinitionError("root corpus directories are not portable")
    if normalized_directories != observed.directories:
        raise CorpusDefinitionError("root corpus directory inventory mismatch")
    root_directories = sorted(path for path in observed.directories if "/" not in path)
    if root_directories != task_ids:
        raise CorpusDefinitionError("root corpus task directories mismatch")

    inventory_rows = manifest["inventory"]
    if not isinstance(inventory_rows, list):
        raise CorpusDefinitionError("root corpus file inventory is invalid")
    listed_inventory: list[dict[str, object]] = []
    listed_paths: list[str] = []
    for row in inventory_rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise CorpusDefinitionError("root corpus file row is invalid")
        path = row["path"]
        size = row["bytes"]
        digest = row["sha256"]
        if (
            not isinstance(path, str)
            or _portable_path(path) != path
            or type(size) is not int
            or size < 0
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
        ):
            raise CorpusDefinitionError("root corpus file row is malformed")
        listed_paths.append(path)
        listed_inventory.append({"path": path, "bytes": size, "sha256": digest})
    if listed_paths != sorted(set(listed_paths)):
        raise CorpusDefinitionError(
            "root corpus file rows are not canonical and unique"
        )
    if any(
        "/" not in path for path in observed.files if path != "corpus-manifest.json"
    ):
        raise CorpusDefinitionError("root corpus contains an unexpected root file")
    observed_inventory = [
        {"path": path, "bytes": len(content), "sha256": _sha256(content)}
        for path, content in sorted(observed.files.items())
        if path != "corpus-manifest.json"
    ]
    if listed_inventory != observed_inventory:
        raise CorpusDefinitionError("root corpus file inventory mismatch")

    without_digest = dict(manifest)
    without_digest.pop("bundle_digest")
    if canonical_digest(without_digest) != bundle_digest:
        raise CorpusDefinitionError("root corpus bundle digest mismatch")
    bundles = tuple(_load_task(source / task_id) for task_id in task_ids)
    observed_contracts = tuple(bundle.public.task_contract_digest for bundle in bundles)
    if observed_contracts != tuple(task_contracts):
        raise CorpusDefinitionError("root task contract inventory mismatch")
    return _CorpusContract(
        bundle_digest,
        tuple(task_ids),
        tuple(task_contracts),
        bundles,
    )


def _test_environment(runtime: Path, workspace: Path) -> dict[str, str]:
    allowed = ("PATH", "PATHEXT", "SystemRoot", "SYSTEMROOT", "WINDIR")
    environment = {
        key: value
        for key in allowed
        if (value := os.environ.get(key)) and "\n" not in value and "\r" not in value
    }
    runtime_text = str(runtime.resolve())
    environment.update(
        {
            "HOME": runtime_text,
            "USERPROFILE": runtime_text,
            "TEMP": runtime_text,
            "TMP": runtime_text,
            "TMPDIR": runtime_text,
            "PYTHONPATH": str(workspace.resolve()),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONSAFEPATH": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    return environment


def _test_outcome(
    *,
    kind: str,
    checker_digest: str,
    candidate_digest: str,
    completed: Sequence[subprocess.CompletedProcess[bytes]],
    location_roots: Sequence[Path],
) -> TestOutcome:
    passed = all(item.returncode == 0 for item in completed)
    returncode = (
        0 if passed else next(item.returncode for item in completed if item.returncode)
    )
    stdout = _location_independent_stream(
        b"\x00".join(item.stdout for item in completed), location_roots
    )
    stderr = _location_independent_stream(
        b"\x00".join(item.stderr for item in completed), location_roots
    )
    outcome_digest = canonical_digest(
        {
            "checker_kind": kind,
            "checker_digest": checker_digest,
            "candidate_digest": candidate_digest,
            "passed": passed,
            "returncode": returncode,
        }
    )
    return TestOutcome(
        kind,
        checker_digest,
        candidate_digest,
        passed,
        returncode,
        _sha256(stdout),
        _sha256(stderr),
        outcome_digest,
    )


def _location_independent_stream(stream: bytes, roots: Sequence[Path]) -> bytes:
    """Replace disposable absolute roots before hashing retained test output."""

    normalized = stream
    markers = (b"<CODE-QA-WORKSPACE>", b"<CODE-QA-RUNTIME>")
    for root, marker in zip(roots, markers):
        resolved = root.resolve(strict=False)
        representations = {
            str(root),
            str(resolved),
            root.as_posix(),
            resolved.as_posix(),
        }
        for representation in sorted(representations, key=len, reverse=True):
            for encoding in ("utf-8", sys.getfilesystemencoding()):
                try:
                    encoded = representation.encode(encoding)
                except UnicodeEncodeError:
                    continue
                normalized = normalized.replace(encoded, marker)
    return normalized


def _execute_test(
    arguments: Sequence[str],
    *,
    workspace: Path,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(arguments),
            cwd=workspace,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, bytes) else b""
        stderr = error.stderr if isinstance(error.stderr, bytes) else b""
        return subprocess.CompletedProcess(
            list(arguments), 124, stdout, stderr + b"\ncode-QA check timed out"
        )
    except OSError as error:
        return subprocess.CompletedProcess(
            list(arguments),
            126,
            b"",
            f"code-QA check failed to start: {type(error).__name__}".encode("utf-8"),
        )


def _run_public(
    task: _PublicTask, workspace: Path, runtime: Path, candidate_digest: str
) -> TestOutcome:
    environment = _test_environment(runtime, workspace)
    completed = []
    for path in task.public_test_paths:
        completed.append(
            _execute_test(
                [sys.executable, "-B", "-P", "-S", path],
                workspace=workspace,
                environment=environment,
            )
        )
    return _test_outcome(
        kind="public",
        checker_digest=task.public_check_digest,
        candidate_digest=candidate_digest,
        completed=completed,
        location_roots=(workspace, runtime),
    )


def _run_hidden(
    check: _SealedCheck, workspace: Path, runtime: Path, candidate_digest: str
) -> TestOutcome:
    environment = _test_environment(runtime, workspace)
    completed = _execute_test(
        [sys.executable, "-B", "-P", "-S", "-c", check.program],
        workspace=workspace,
        environment=environment,
    )
    return _test_outcome(
        kind="hidden",
        checker_digest=check.hidden_check_digest,
        candidate_digest=candidate_digest,
        completed=(completed,),
        location_roots=(workspace, runtime),
    )


def _candidate_evidence(
    task: _PublicTask, baseline: Mapping[str, bytes], workspace: Path
) -> CandidateEvidence:
    candidate = file_inventory(workspace)
    paths = sorted(set(baseline) | set(candidate))
    changed = tuple(path for path in paths if baseline.get(path) != candidate.get(path))
    diff = []
    for path in changed:
        before = baseline.get(path)
        after = candidate.get(path)
        diff.append(
            {
                "path": path,
                "kind": "added"
                if before is None
                else "deleted"
                if after is None
                else "modified",
                "before_digest": None if before is None else _sha256(before),
                "after_digest": None if after is None else _sha256(after),
            }
        )
    current_tree = _inventory_digest(candidate)
    diff_digest = canonical_digest(diff)
    candidate_digest = canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "task_id": task.task_id,
            "task_contract_digest": task.task_contract_digest,
            "baseline_tree_digest": task.baseline_tree_digest,
            "tree_digest": current_tree,
            "diff_digest": diff_digest,
            "changed_paths": changed,
        }
    )
    return CandidateEvidence(
        task.task_contract_digest,
        task.baseline_tree_digest,
        current_tree,
        diff_digest,
        candidate_digest,
        changed,
    )


def _baseline_candidate_digest(task: _PublicTask) -> str:
    return canonical_digest(
        {"task_id": task.task_id, "baseline_tree_digest": task.baseline_tree_digest}
    )


def _preflight(task: _PublicTask, proposal: CandidateProposal) -> str | None:
    write_paths = set(proposal.writes)
    if proposal.deletions:
        if any(path.startswith("tests/") for path in proposal.deletions):
            return "public-test-deletion-or-assertion-weakening"
        return "deletions-are-not-authorized-in-this-bounded-corpus"
    if not write_paths:
        return "candidate-has-no-source-change"
    if any(path.startswith("tests/") for path in write_paths):
        return "public-test-modification-or-assertion-weakening"
    if any(path.startswith(_PROTECTED_PREFIXES) for path in write_paths):
        return "evaluator-or-harness-path-is-protected"
    outside = write_paths - set(task.allowed_write_paths)
    if outside:
        return "candidate-write-is-outside-sealed-scope"
    return None


def _coordinator(task: _PublicTask, workspace: Path) -> BuilderCoordinator:
    policy = canonical_digest(
        {
            "task": task.task_id,
            "task_contract_digest": task.task_contract_digest,
            "allowed_write_paths": task.allowed_write_paths,
            "denied": ("command", "branch", "commit", "delete", "network"),
        }
    )
    envelope = ConstraintEnvelope(
        f"AUTH-code-qa-{task.task_id}",
        f"MISSION-code-qa-{task.task_id}",
        f"WORK-code-qa-{task.task_id}",
        None,
        "builder",
        "R1",
        ("write",),
        ("command", "branch", "commit", "delete", "network"),
        ("isolated-workspace",),
        task.allowed_write_paths,
        (),
        (),
        (),
        (),
        Budget(120, 0, 0, 0, 0, len(task.allowed_write_paths), 1, 1),
        EXPIRES,
        policy,
        canonical_digest({"unsealed": task.task_id}),
    ).sealed()
    registry = AuthorityRegistry()
    registry.mint_root(
        envelope,
        issuer="owner:code-qa-corpus-v2",
        authority_ref="AUTHORITY-RECORD-code-qa-corpus-v2",
        recorded_at="2026-01-01T00:00:00Z",
    )
    adapter = IsolatedBuilderAdapter(workspace)
    gateway = EffectGateway(authority=registry, clock=lambda: NOW)
    gateway.register_adapter(
        adapter.adapter_name,
        cast(Callable[[EffectIntent], object], adapter.apply),
        version="1",
    )
    return BuilderCoordinator(
        gateway,
        registry,
        adapter,
        mission_id=f"MISSION-code-qa-{task.task_id}",
        work_id=f"WORK-code-qa-{task.task_id}",
        actor_id="builder:code-qa-scripted-test-double",
        authority_envelope_digest=envelope.digest_value,
        policy_decision_ref=policy,
        risk_tier="R1",
        now=NOW,
    )


def _effect_evidence(executions: Sequence[object]) -> tuple[EffectEvidence, ...]:
    result = []
    for value in executions:
        execution = cast(object, value)
        action = getattr(execution, "action")
        effect = getattr(execution, "effect")
        outcome = getattr(execution, "outcome")
        result.append(
            EffectEvidence(
                action.action_id,
                effect.intent_digest,
                effect.receipt_digest,
                effect.status,
                outcome.status,
                outcome.output_digest,
            )
        )
    return tuple(result)


def _attempt_digest(record: Mapping[str, object]) -> str:
    return canonical_digest(record)


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_bytes(value) + b"\n")


def _record_attempt(
    *,
    number: int,
    proposal: CandidateProposal,
    disposition: str,
    reason: str,
    workspace: Path | None,
    evidence: CandidateEvidence | None,
    effects: tuple[EffectEvidence, ...],
    public: TestOutcome,
    hidden: TestOutcome,
) -> AttemptRecord:
    workspace_ref = (
        None if workspace is None else f"{workspace.parent.name}/{workspace.name}"
    )
    document = {
        "attempt_number": number,
        "proposal_id": proposal.proposal_id,
        "proposal_digest": proposal.proposal_digest,
        "disposition": disposition,
        "reason": reason,
        "workspace": workspace_ref,
        "evidence": None if evidence is None else asdict(evidence),
        "effects": [asdict(value) for value in effects],
        "public_outcome": asdict(public),
        "hidden_outcome": asdict(hidden),
    }
    return AttemptRecord(
        number,
        proposal.proposal_id,
        proposal.proposal_digest,
        disposition,
        reason,
        workspace_ref,
        evidence,
        effects,
        public,
        hidden,
        _attempt_digest(document),
    )


def _attempt_feedback(record: AttemptRecord) -> AttemptFeedback:
    return AttemptFeedback(
        record.disposition,
        record.reason,
        record.public_outcome.passed,
        record.hidden_outcome.passed,
        record.public_outcome.outcome_digest,
        record.hidden_outcome.outcome_digest,
    )


class DeterministicBuilderDouble:
    """Two-round scripted challenger used only by the bounded fixture corpus."""

    identity = BUILDER_ID
    qualification = QUALIFICATION

    _rounds: Mapping[str, tuple[CandidateProposal, ...]] = MappingProxyType(
        {
            "shipping-boundary": (
                CandidateProposal(
                    "local-boundary-fix",
                    {
                        "shipping.py": (
                            "def shipping_tier(weight: int) -> str:\n"
                            "    return 'parcel' if weight <= 5 else 'freight'\n"
                        )
                    },
                    "Repair only the observed failing boundary.",
                ),
                CandidateProposal(
                    "objective-faithful-range-fix",
                    {
                        "shipping.py": (
                            "def shipping_tier(weight: int) -> str:\n"
                            "    return 'parcel' if 0 <= weight <= 10 else 'freight'\n"
                        )
                    },
                    "Rethink from the public objective and implement its complete range.",
                ),
            ),
            "tag-parser": (
                CandidateProposal(
                    "literal-space-fix",
                    {
                        "tag_parser.py": (
                            "def parse_tags(text: str) -> list[str]:\n"
                            "    return text.replace(' ', '').split(',')\n"
                        )
                    },
                    "Repair the literal space shown by the public example.",
                ),
                CandidateProposal(
                    "normalized-token-fix",
                    {
                        "tag_parser.py": (
                            "def parse_tags(text: str) -> list[str]:\n"
                            "    return [part.strip() for part in text.split(',') if part.strip()]\n"
                        )
                    },
                    "Normalize every token and discard empty fields as the objective requires.",
                ),
            ),
            "inventory-aggregation": (
                CandidateProposal(
                    "adjacent-group-fix",
                    {
                        "src/inventory/totals.py": (
                            "from itertools import groupby\n\n"
                            "def total_by_sku(lines: list[tuple[str, int]]) -> dict[str, int]:\n"
                            "    return {sku: sum(qty for _, qty in group) "
                            "for sku, group in groupby(lines, key=lambda item: item[0])}\n"
                        )
                    },
                    "Aggregate the adjacent duplicate demonstrated publicly.",
                ),
                CandidateProposal(
                    "whole-input-aggregation-fix",
                    {
                        "src/inventory/totals.py": (
                            "def total_by_sku(lines: list[tuple[str, int]]) -> dict[str, int]:\n"
                            "    totals: dict[str, int] = {}\n"
                            "    for sku, quantity in lines:\n"
                            "        totals[sku] = totals.get(sku, 0) + quantity\n"
                            "    return totals\n"
                        )
                    },
                    "Rethink aggregation across the entire input rather than local adjacency.",
                ),
            ),
        }
    )

    def propose(
        self, task: BuilderTaskView, feedback: tuple[AttemptFeedback, ...]
    ) -> CandidateProposal:
        try:
            rounds = self._rounds[task.task_id]
            return rounds[len(feedback)]
        except (KeyError, IndexError) as error:
            raise CandidateRejected(
                "scripted Builder has no further bounded proposal"
            ) from error


def _run_task(bundle: _TaskBundle, output: Path, builder: CodeQABuilder) -> TaskRun:
    task = bundle.public
    output.mkdir()
    baseline_workspace = output / "baseline"
    shutil.copytree(task.repository, baseline_workspace)
    baseline_inventory = file_inventory(baseline_workspace)
    observed_baseline = _inventory_digest(baseline_inventory)
    if observed_baseline != task.baseline_tree_digest:
        raise CorpusDefinitionError("materialized baseline differs from its seal")
    baseline_candidate = _baseline_candidate_digest(task)
    baseline_runtime = output / "baseline-runtime"
    baseline_runtime.mkdir()
    baseline_public = _run_public(
        task, baseline_workspace, baseline_runtime, baseline_candidate
    )
    if _inventory_digest(file_inventory(baseline_workspace)) != observed_baseline:
        raise CorpusDefinitionError("public baseline check mutated the sealed baseline")
    baseline_hidden = _run_hidden(
        bundle.sealed, baseline_workspace, baseline_runtime, baseline_candidate
    )
    if _inventory_digest(file_inventory(baseline_workspace)) != observed_baseline:
        raise CorpusDefinitionError("hidden baseline check mutated the sealed baseline")
    if baseline_public.passed:
        raise CorpusDefinitionError("baseline-already-green task is not admissible")
    if baseline_public.outcome_digest != task.baseline_public_outcome_digest:
        raise CorpusDefinitionError("baseline failure outcome does not match its seal")
    baseline_record = BaselineRecord(
        task.task_contract_digest,
        observed_baseline,
        baseline_candidate,
        baseline_public,
        baseline_hidden,
    )
    _write_json(output / "baseline-record.json", asdict(baseline_record))

    feedback: list[AttemptFeedback] = []
    attempts: list[AttemptRecord] = []
    view = task.builder_view()
    public_not_run = TestOutcome.not_run("public", task.public_check_digest)
    hidden_not_run = TestOutcome.not_run("hidden", task.hidden_check_digest)
    for number in range(1, task.max_attempts + 1):
        attempt_root = output / f"attempt-{number:02d}"
        attempt_root.mkdir()
        proposal_error: str | None = None
        try:
            proposal = builder.propose(view, tuple(feedback))
            if not isinstance(proposal, CandidateProposal):
                raise TypeError("Builder returned no CandidateProposal")
        except Exception as error:
            proposal_error = f"builder-proposal-error:{type(error).__name__}"
            proposal = CandidateProposal(
                f"builder-error-{number}",
                {},
                "The Builder failed before returning a declarative candidate.",
            )
        _write_json(
            attempt_root / "proposal.json",
            {
                "proposal_id": proposal.proposal_id,
                "proposal_digest": proposal.proposal_digest,
                "writes": dict(proposal.writes),
                "deletions": proposal.deletions,
                "rationale": proposal.rationale,
                "claimed_candidate_digest": proposal.claimed_candidate_digest,
                "claimed_effect_receipts": proposal.claimed_effect_receipts,
            },
        )
        preflight = proposal_error or _preflight(task, proposal)
        if preflight is not None:
            record = _record_attempt(
                number=number,
                proposal=proposal,
                disposition="rejected",
                reason=preflight,
                workspace=None,
                evidence=None,
                effects=(),
                public=public_not_run,
                hidden=hidden_not_run,
            )
        else:
            workspace = attempt_root / "workspace"
            shutil.copytree(baseline_workspace, workspace)
            coordinator = _coordinator(task, workspace)
            actions = tuple(
                BuilderAction(
                    f"{task.task_id}-{number}-{index}",
                    BuilderActionKind.WRITE,
                    path,
                    {"content": content},
                    f"restore {path} from sealed baseline",
                )
                for index, (path, content) in enumerate(
                    sorted(proposal.writes.items()), start=1
                )
            )
            executions = coordinator.execute_round(f"ATTEMPT-code-qa-{number}", actions)
            effects = _effect_evidence(executions)
            evidence = _candidate_evidence(task, baseline_inventory, workspace)
            reason: str | None = None
            if any(
                item.effect_status != "SUCCEEDED"
                or item.adapter_outcome_status != "SUCCEEDED"
                for item in effects
            ):
                reason = "authority-bound-source-effect-failed"
            elif set(evidence.changed_paths) != set(proposal.writes):
                reason = "declared-writes-do-not-match-exact-candidate-diff"
            elif set(evidence.changed_paths) - set(task.allowed_write_paths):
                reason = "exact-candidate-contains-out-of-scope-change"
            elif (
                proposal.claimed_candidate_digest is not None
                and proposal.claimed_candidate_digest != evidence.candidate_digest
            ):
                reason = "claimed-candidate-digest-does-not-bind-exact-candidate"
            elif (
                proposal.claimed_effect_receipts
                and proposal.claimed_effect_receipts
                != tuple(item.receipt_digest for item in effects)
            ):
                reason = "claimed-effect-receipts-are-forged-or-mismatched"
            if reason is not None:
                record = _record_attempt(
                    number=number,
                    proposal=proposal,
                    disposition="rejected",
                    reason=reason,
                    workspace=workspace,
                    evidence=evidence,
                    effects=effects,
                    public=public_not_run,
                    hidden=hidden_not_run,
                )
            else:
                runtime = attempt_root / "runtime"
                runtime.mkdir()
                before_public = _candidate_evidence(task, baseline_inventory, workspace)
                public = _run_public(
                    task, workspace, runtime, evidence.candidate_digest
                )
                after_public = _candidate_evidence(task, baseline_inventory, workspace)
                if not before_public == evidence or not after_public == evidence:
                    hidden = hidden_not_run
                    disposition = "rejected"
                    reason = "test-execution-mutated-or-switched-the-exact-candidate"
                else:
                    hidden = _run_hidden(
                        bundle.sealed,
                        workspace,
                        runtime,
                        evidence.candidate_digest,
                    )
                    after_hidden = _candidate_evidence(
                        task, baseline_inventory, workspace
                    )
                    if after_hidden != evidence:
                        disposition = "rejected"
                        reason = (
                            "test-execution-mutated-or-switched-the-exact-candidate"
                        )
                    elif (
                        public.candidate_digest != evidence.candidate_digest
                        or hidden.candidate_digest != evidence.candidate_digest
                    ):
                        disposition = "rejected"
                        reason = "test-receipt-is-bound-to-the-wrong-candidate"
                    elif public.passed and hidden.passed:
                        disposition = "succeeded"
                        reason = "public-and-hidden-checks-pass-on-the-exact-candidate"
                    else:
                        disposition = "failed"
                        reason = "candidate-failed-one-or-more-independent-checks"
                record = _record_attempt(
                    number=number,
                    proposal=proposal,
                    disposition=disposition,
                    reason=reason,
                    workspace=workspace,
                    evidence=evidence,
                    effects=effects,
                    public=public,
                    hidden=hidden,
                )
        attempts.append(record)
        feedback.append(_attempt_feedback(record))
        _write_json(attempt_root / "attempt-record.json", asdict(record))
        if record.disposition == "succeeded":
            break
    status = "succeeded" if attempts[-1].disposition == "succeeded" else "failed"
    semantic = {
        "task_id": task.task_id,
        "shape": task.shape,
        "task_contract_digest": task.task_contract_digest,
        "status": status,
        "builder_identity": builder.identity,
        "qualification": builder.qualification,
        "baseline_tree_digest": baseline_record.tree_digest,
        "baseline_public_outcome_digest": baseline_public.outcome_digest,
        "attempts": [
            {
                "record_digest": item.record_digest,
                "disposition": item.disposition,
                "candidate_digest": None
                if item.evidence is None
                else item.evidence.candidate_digest,
                "public_outcome_digest": item.public_outcome.outcome_digest,
                "hidden_outcome_digest": item.hidden_outcome.outcome_digest,
            }
            for item in attempts
        ],
    }
    result = TaskRun(
        task.task_id,
        task.shape,
        task.task_contract_digest,
        status,
        builder.identity,
        builder.qualification,
        baseline_record,
        tuple(attempts),
        canonical_digest(semantic),
    )
    _write_json(output / "task-run.json", asdict(result))
    return result


def run_code_qa_corpus(
    fixture_root: str | Path,
    output_root: str | Path,
    *,
    builder: CodeQABuilder | None = None,
    task_ids: Sequence[str] | None = None,
    expected_bundle_digest: str | None = None,
    allow_unpinned_local_test_double: bool = False,
    allow_custom_test_double: bool = False,
) -> CorpusRun:
    """Run sealed fixtures and retain every baseline, losing attempt, and winner.

    ``output_root`` must not exist.  A caller-supplied bundle pin is mandatory
    unless it explicitly selects the unpinned, same-trust local-development
    escape hatch.  Neither path makes the unsandboxed checks independent or
    production-qualified.
    """

    source_input = Path(os.path.abspath(fixture_root))
    destination_input = Path(os.path.abspath(output_root))
    if os.path.lexists(destination_input):
        raise FileExistsError("code-QA run destination already exists")
    _assert_no_link_like_components(
        source_input, label="code-QA fixture root", allow_missing=False
    )
    _assert_no_link_like_components(
        destination_input.parent,
        label="code-QA output parent",
        allow_missing=True,
    )
    source = source_input.resolve(strict=True)
    destination = destination_input.resolve(strict=False)
    if destination.is_relative_to(source):
        raise CorpusDefinitionError("code-QA output must be outside the fixture root")
    contract = _load_corpus_contract(source)
    if expected_bundle_digest is None:
        if allow_unpinned_local_test_double is not True:
            raise CorpusDefinitionError(
                "expected corpus/evaluator bundle digest is required; "
                "unpinned execution requires explicit same-trust local-test-double opt-in"
            )
        pin_mode = "explicit-unpinned-same-trust-local-development"
    else:
        if _DIGEST.fullmatch(expected_bundle_digest) is None:
            raise CorpusDefinitionError(
                "expected corpus/evaluator bundle digest is malformed"
            )
        if expected_bundle_digest != contract.bundle_digest:
            raise CorpusDefinitionError(
                "expected corpus/evaluator bundle digest mismatch"
            )
        pin_mode = "caller-pinned-same-trust-local-development"
    if task_ids is None:
        selected_ids = contract.task_ids
    else:
        selected_ids = tuple(task_ids)
        if not selected_ids or len(set(selected_ids)) != len(selected_ids):
            raise CorpusDefinitionError(
                "selected task ids must be non-empty and unique"
            )
        unknown = set(selected_ids) - set(contract.task_ids)
        if unknown:
            raise CorpusDefinitionError(
                "unknown code-QA task(s): " + ", ".join(sorted(unknown))
            )
        selected_ids = tuple(
            task_id for task_id in contract.task_ids if task_id in set(selected_ids)
        )
    selected = set(selected_ids)
    bundles = tuple(
        bundle for bundle in contract.bundles if bundle.public.task_id in selected
    )
    if len({bundle.public.shape for bundle in contract.bundles}) != len(
        contract.bundles
    ):
        raise CorpusDefinitionError("root corpus task shapes must be distinct")
    active_builder = builder or DeterministicBuilderDouble()
    if (
        builder is not None
        and type(active_builder) is not DeterministicBuilderDouble
        and allow_custom_test_double is not True
    ):
        raise CorpusDefinitionError(
            "custom Builder requires explicit trusted-test-double opt-in"
        )
    if (
        not isinstance(active_builder.identity, str)
        or not active_builder.identity.strip()
        or active_builder.qualification != QUALIFICATION
    ):
        raise CorpusDefinitionError(
            "Builder identity or test-double qualification is invalid"
        )
    destination.mkdir(parents=True)
    task_runs = tuple(
        _run_task(bundle, destination / bundle.public.task_id, active_builder)
        for bundle in bundles
    )
    complete = selected_ids == contract.task_ids
    all_passed = all(run.status == "succeeded" for run in task_runs)
    scope = "complete-bounded-corpus" if complete else "partial-development"
    status = (
        "succeeded"
        if complete and all_passed
        else "partial-development"
        if all_passed
        else "failed"
    )
    corpus_digest = canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "scope": scope,
            "bundle_digest": contract.bundle_digest,
            "pin_mode": pin_mode,
            "evaluator_id": EVALUATOR_ID,
            "qualification": QUALIFICATION,
            "trust_model": TRUST_MODEL,
            "expected_task_ids": contract.task_ids,
            "selected_task_ids": selected_ids,
            "task_contract_digests": contract.task_contract_digests,
            "task_result_digests": [run.result_digest for run in task_runs],
        }
    )
    result = CorpusRun(
        SCHEMA_VERSION,
        status,
        scope,
        contract.bundle_digest,
        pin_mode,
        contract.task_ids,
        selected_ids,
        contract.task_contract_digests,
        task_runs,
        corpus_digest,
    )
    _write_json(destination / "corpus-run.json", asdict(result))
    return result


__all__ = [
    "BUILDER_ID",
    "EVALUATOR_ID",
    "PINNED_CORPUS_BUNDLE_DIGEST",
    "QUALIFICATION",
    "TRUST_MODEL",
    "AttemptFeedback",
    "AttemptRecord",
    "BaselineRecord",
    "BuilderTaskView",
    "CandidateEvidence",
    "CandidateProposal",
    "CandidateRejected",
    "CodeQABuilder",
    "CorpusDefinitionError",
    "CorpusRun",
    "DeterministicBuilderDouble",
    "EffectEvidence",
    "TaskRun",
    "TestOutcome",
    "file_inventory",
    "run_code_qa_corpus",
    "tree_digest",
]
