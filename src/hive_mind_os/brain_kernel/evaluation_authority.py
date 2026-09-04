"""External authority and candidate-bound evidence for offline evaluation.

The manifest is caller-digest-pinned and must live outside the source,
candidate, and run roots. Its holdout entry is an opaque commitment: exact
schema checks reject cases, answers, or any other disclosure. Surface scores
reach the evaluator only through an immutable ``ArtifactStore`` envelope and a
candidate-specific qualification receipt.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import Role
from .artifacts import ArtifactIntegrityError, ArtifactStore
from .canonical import canonical_bytes, canonical_digest
from .evaluation_runtime import SealedHoldout, SurfaceKind, SurfaceResult
from .qualification import EvidenceKind, EvidenceReceipt, ExecutionMode

__all__ = [
    "AUTHORITY_SCHEMA_ID",
    "AUTHORITY_SCHEMA_VERSION",
    "SURFACE_SCHEMA_DIGEST",
    "SURFACE_SCHEMA_ID",
    "AuthorityBudget",
    "AuthorityIdentities",
    "BoundSurfaceEvidence",
    "CandidateAuthorityBinding",
    "ComparatorBinding",
    "EvaluationAuthorityError",
    "EvaluationAuthorityManifest",
    "RepositoryBinding",
    "canonical_holdout_commitment",
    "capture_repository_binding",
    "load_evaluation_authority_manifest",
    "store_bound_surface_evidence",
    "sealed_holdout_commitment",
    "validate_bound_surface_evidence",
    "validate_surface_set",
]

AUTHORITY_SCHEMA_ID = "hive-mind-os/evaluation-authority"
AUTHORITY_SCHEMA_VERSION = 1
SURFACE_SCHEMA_ID = "hive-mind-os/evaluation-surface"
SURFACE_SCHEMA_VERSION = "1"
_SURFACE_FIELDS = (
    "schema_version",
    "receipt_id",
    "claim_id",
    "candidate_digest",
    "parent_champion_digest",
    "authority_manifest_digest",
    "evaluation_plan_digest",
    "prior_outcome_digest",
    "generation",
    "evaluator_id",
    "repository_head",
    "repository_tree",
    "contract_fingerprint",
    "harness_fingerprint",
    "holdout_commitment",
    "comparator_id",
    "comparator_pin",
    "surface",
)
SURFACE_SCHEMA_DIGEST = canonical_digest(
    {
        "schema_id": SURFACE_SCHEMA_ID,
        "schema_version": SURFACE_SCHEMA_VERSION,
        "fields": _SURFACE_FIELDS,
    }
)
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_MANIFEST_FIELDS = {
    "schema_id",
    "schema_version",
    "authority_id",
    "repository",
    "role_champions",
    "evaluation",
    "holdout",
    "comparators",
    "identities",
    "budgets",
    "validity",
    "manifest_digest",
}


class EvaluationAuthorityError(ValueError):
    """An authority, binding, or evidence reference failed closed."""


def sealed_holdout_commitment(holdout: SealedHoldout) -> str:
    """Return the semantic commitment for one validated opaque holdout.

    This is a canonical content commitment, not a signature or proof of
    independent custody. The returned digest discloses neither cases nor answers.
    """

    if not isinstance(holdout, SealedHoldout):
        raise EvaluationAuthorityError("holdout must be a SealedHoldout")
    return canonical_digest(
        {
            "schema_id": "hive-mind-os/semantic-holdout-commitment",
            "schema_version": 1,
            "holdout_id": holdout._holdout_id,
            "cases": holdout._cases,
        }
    )


def canonical_holdout_commitment(holdout_id: str, cases: Mapping[str, Any]) -> str:
    """Validate raw cases through ``SealedHoldout`` and return their commitment."""

    try:
        holdout = SealedHoldout(holdout_id, cases)
        return sealed_holdout_commitment(holdout)
    except (TypeError, ValueError) as error:
        raise EvaluationAuthorityError("holdout commitment input is invalid") from error


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise EvaluationAuthorityError(f"{label} must be an exact non-empty string")
    return value


def _sha(value: object, label: str) -> str:
    value = _text(value, label)
    if _SHA.fullmatch(value) is None:
        raise EvaluationAuthorityError(f"{label} must be lowercase sha256:<64 hex>")
    return value


def _oid(value: object, label: str) -> str:
    value = _text(value, label)
    if _OID.fullmatch(value) is None:
        raise EvaluationAuthorityError(f"{label} must be a lowercase Git object id")
    return value


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise EvaluationAuthorityError(f"{label} must be a positive integer")
    return value


def _object(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationAuthorityError(f"{label} must be an object")
    actual = set(value)
    if any(type(key) is not str for key in actual) or actual != fields:
        missing, unknown = sorted(fields - actual), sorted(actual - fields)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise EvaluationAuthorityError(
            f"{label} fields are invalid: {'; '.join(details)}"
        )
    return value


def _time(value: object, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, label).replace("Z", "+00:00"))
    except ValueError as error:
        raise EvaluationAuthorityError(f"{label} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvaluationAuthorityError(f"{label} must include an offset")
    return parsed.astimezone(timezone.utc)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationAuthorityError(
                f"authority manifest contains duplicate key: {key}"
            )
        result[key] = value
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparatorBinding:
    comparator_id: str
    pin: str
    license_id: str

    def __post_init__(self) -> None:
        _text(self.comparator_id, "comparator_id")
        _sha(self.pin, "comparator pin")
        _text(self.license_id, "comparator license")

    def to_document(self) -> dict[str, str]:
        return {
            "comparator_id": self.comparator_id,
            "pin": self.pin,
            "license": self.license_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorityIdentities:
    proposer_id: str
    builder_id: str
    evaluator_id: str
    judge_id: str

    def __post_init__(self) -> None:
        values = tuple(
            _text(getattr(self, name), name)
            for name in ("proposer_id", "builder_id", "evaluator_id", "judge_id")
        )
        if len(set(values)) != 4:
            raise EvaluationAuthorityError(
                "proposer, builder, evaluator, and judge identities must be unique"
            )

    def to_document(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in ("proposer_id", "builder_id", "evaluator_id", "judge_id")
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorityBudget:
    max_generations: int
    max_candidates: int
    max_evaluations: int
    max_surface_receipts: int
    max_prompt_bytes: int
    max_wall_seconds: int

    def __post_init__(self) -> None:
        for name in (
            "max_generations",
            "max_candidates",
            "max_evaluations",
            "max_surface_receipts",
            "max_prompt_bytes",
            "max_wall_seconds",
        ):
            _positive(getattr(self, name), name)
        if self.max_generations != 2:
            raise EvaluationAuthorityError(
                "bounded v2 authority requires exactly two generations"
            )

    def to_document(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__slots__}


@dataclass(frozen=True, slots=True, kw_only=True)
class RepositoryBinding:
    head_commit: str
    tree_oid: str
    state_digest: str

    def __post_init__(self) -> None:
        _oid(self.head_commit, "repository head")
        _oid(self.tree_oid, "repository tree")
        _sha(self.state_digest, "repository state digest")


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateAuthorityBinding:
    candidate_id: str
    candidate_digest: str
    role: str
    parent_champion_digest: str
    authority_manifest_digest: str
    generation: int
    accessed_holdout: bool = False

    def __post_init__(self) -> None:
        _text(self.candidate_id, "candidate_id")
        _sha(self.candidate_digest, "candidate_digest")
        _sha(self.parent_champion_digest, "parent champion digest")
        _sha(self.authority_manifest_digest, "authority manifest digest")
        try:
            object.__setattr__(self, "role", Role(self.role).value)
        except ValueError as error:
            raise EvaluationAuthorityError(
                "candidate role is not a kernel role"
            ) from error
        _positive(self.generation, "candidate generation")
        if type(self.accessed_holdout) is not bool:
            raise EvaluationAuthorityError("accessed_holdout must be a boolean")
        if self.candidate_digest == self.parent_champion_digest:
            raise EvaluationAuthorityError("candidate aliases its parent champion")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationAuthorityManifest:
    authority_id: str
    repository_head: str
    repository_tree: str
    role_champions: tuple[tuple[str, str], ...]
    contract_fingerprint: str
    harness_fingerprint: str
    holdout_id: str
    holdout_commitment: str
    comparators: tuple[ComparatorBinding, ...]
    identities: AuthorityIdentities
    budget: AuthorityBudget
    not_before: str
    expires_at: str
    manifest_digest: str
    source_path: Path
    schema_id: str = AUTHORITY_SCHEMA_ID
    schema_version: int = AUTHORITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (self.schema_id, self.schema_version) != (
            AUTHORITY_SCHEMA_ID,
            AUTHORITY_SCHEMA_VERSION,
        ):
            raise EvaluationAuthorityError("unsupported authority schema")
        _text(self.authority_id, "authority_id")
        _oid(self.repository_head, "repository head")
        _oid(self.repository_tree, "repository tree")
        for value, label in (
            (self.contract_fingerprint, "contract fingerprint"),
            (self.harness_fingerprint, "harness fingerprint"),
            (self.holdout_commitment, "holdout commitment"),
            (self.manifest_digest, "manifest digest"),
        ):
            _sha(value, label)
        _text(self.holdout_id, "holdout_id")
        roles = tuple(sorted(self.role_champions))
        expected_roles = {role.value for role in Role}
        if len(roles) != len(Role) or {item[0] for item in roles} != expected_roles:
            raise EvaluationAuthorityError(
                "role_champions must bind every kernel role exactly once"
            )
        for role, digest in roles:
            _sha(digest, f"{role} champion digest")
        object.__setattr__(self, "role_champions", roles)
        if len(self.comparators) < 2 or any(
            not isinstance(item, ComparatorBinding) for item in self.comparators
        ):
            raise EvaluationAuthorityError(
                "authority requires at least two comparator bindings"
            )
        if len({item.comparator_id for item in self.comparators}) != len(
            self.comparators
        ):
            raise EvaluationAuthorityError("comparator ids must be unique")
        if len({item.pin for item in self.comparators}) != len(self.comparators):
            raise EvaluationAuthorityError("comparator pins must be unique")
        if not isinstance(self.identities, AuthorityIdentities) or not isinstance(
            self.budget, AuthorityBudget
        ):
            raise EvaluationAuthorityError(
                "authority identities or budget are malformed"
            )
        if _time(self.expires_at, "expires_at") <= _time(self.not_before, "not_before"):
            raise EvaluationAuthorityError("expires_at must follow not_before")
        if not self.source_path.is_absolute():
            raise EvaluationAuthorityError("manifest source path must be absolute")

    @property
    def champions(self) -> dict[str, str]:
        return dict(self.role_champions)

    def champion_digest(self, role: Role | str) -> str:
        try:
            return self.champions[Role(role).value]
        except (KeyError, ValueError) as error:
            raise EvaluationAuthorityError(
                "role is not bound by the authority"
            ) from error

    def comparator(self, comparator_id: str) -> ComparatorBinding:
        match = next(
            (item for item in self.comparators if item.comparator_id == comparator_id),
            None,
        )
        if match is None:
            raise EvaluationAuthorityError(
                f"comparator is not authorized: {comparator_id}"
            )
        return match

    def unsigned_document(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "authority_id": self.authority_id,
            "repository": {
                "head_commit": self.repository_head,
                "tree_oid": self.repository_tree,
            },
            "role_champions": dict(self.role_champions),
            "evaluation": {
                "contract_fingerprint": self.contract_fingerprint,
                "harness_fingerprint": self.harness_fingerprint,
            },
            "holdout": {
                "holdout_id": self.holdout_id,
                "commitment": self.holdout_commitment,
            },
            "comparators": [item.to_document() for item in self.comparators],
            "identities": self.identities.to_document(),
            "budgets": self.budget.to_document(),
            "validity": {
                "not_before": self.not_before,
                "expires_at": self.expires_at,
            },
        }

    def to_document(self) -> dict[str, Any]:
        return {**self.unsigned_document(), "manifest_digest": self.manifest_digest}

    def validate_candidate(
        self,
        candidate: CandidateAuthorityBinding,
        *,
        current_champion_digest: str,
    ) -> None:
        if not isinstance(candidate, CandidateAuthorityBinding):
            raise EvaluationAuthorityError("candidate binding is malformed")
        if candidate.authority_manifest_digest != self.manifest_digest:
            raise EvaluationAuthorityError(
                "candidate authority_manifest_digest does not match the authority"
            )
        parent = self.champion_digest(candidate.role)
        if candidate.parent_champion_digest != parent:
            raise EvaluationAuthorityError(
                "candidate parent is not the authority-bound champion"
            )
        if _sha(current_champion_digest, "current champion") != parent:
            raise EvaluationAuthorityError(
                "current champion changed after authority issuance"
            )
        if candidate.generation > self.budget.max_generations:
            raise EvaluationAuthorityError("candidate exceeds generation budget")
        if candidate.accessed_holdout:
            raise EvaluationAuthorityError(
                "candidate accessed protected holdout evidence"
            )

    @classmethod
    def from_document(
        cls, document: Mapping[str, Any], source_path: Path
    ) -> EvaluationAuthorityManifest:
        root = _object(document, _MANIFEST_FIELDS, "authority manifest")
        repository = _object(
            root["repository"], {"head_commit", "tree_oid"}, "repository"
        )
        evaluation = _object(
            root["evaluation"],
            {"contract_fingerprint", "harness_fingerprint"},
            "evaluation",
        )
        # Exactness makes ``answers`` and ``cases`` unsealable disclosures.
        holdout = _object(root["holdout"], {"holdout_id", "commitment"}, "holdout")
        identities = _object(
            root["identities"],
            {"proposer_id", "builder_id", "evaluator_id", "judge_id"},
            "identities",
        )
        budget_fields = {
            "max_generations",
            "max_candidates",
            "max_evaluations",
            "max_surface_receipts",
            "max_prompt_bytes",
            "max_wall_seconds",
        }
        budgets = _object(root["budgets"], budget_fields, "budgets")
        validity = _object(root["validity"], {"not_before", "expires_at"}, "validity")
        champions = root["role_champions"]
        if not isinstance(champions, Mapping):
            raise EvaluationAuthorityError("role_champions must be an object")
        rows = root["comparators"]
        if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
            raise EvaluationAuthorityError("comparators must be an array")
        comparators = []
        for index, raw in enumerate(rows):
            row = _object(
                raw,
                {"comparator_id", "pin", "license"},
                f"comparators[{index}]",
            )
            comparators.append(
                ComparatorBinding(
                    comparator_id=row["comparator_id"],
                    pin=row["pin"],
                    license_id=row["license"],
                )
            )
        return cls(
            authority_id=root["authority_id"],
            repository_head=repository["head_commit"],
            repository_tree=repository["tree_oid"],
            role_champions=tuple(champions.items()),
            contract_fingerprint=evaluation["contract_fingerprint"],
            harness_fingerprint=evaluation["harness_fingerprint"],
            holdout_id=holdout["holdout_id"],
            holdout_commitment=holdout["commitment"],
            comparators=tuple(comparators),
            identities=AuthorityIdentities(**identities),
            budget=AuthorityBudget(**budgets),
            not_before=validity["not_before"],
            expires_at=validity["expires_at"],
            manifest_digest=root["manifest_digest"],
            source_path=source_path,
            schema_id=root["schema_id"],
            schema_version=root["schema_version"],
        )


def load_evaluation_authority_manifest(
    path: str | Path,
    *,
    expected_digest: str,
    repository_root: str | Path,
    candidate_root: str | Path,
    run_root: str | Path,
    as_of: str,
) -> EvaluationAuthorityManifest:
    """Authenticate an external manifest before parsing candidate data."""

    expected = _sha(expected_digest, "expected manifest digest")
    source = Path(path)
    if not source.is_absolute() or source.is_symlink():
        raise EvaluationAuthorityError(
            "authority manifest must be an absolute non-symlink file"
        )
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        raise EvaluationAuthorityError("authority manifest is unavailable") from error
    for label, raw in (
        ("repository", repository_root),
        ("candidate", candidate_root),
        ("run", run_root),
    ):
        root = Path(raw)
        if not root.is_absolute():
            raise EvaluationAuthorityError(f"{label} root must be absolute")
        root = root.resolve(strict=False)
        if source == root or source.is_relative_to(root):
            raise EvaluationAuthorityError(
                f"authority manifest must be outside the {label} root"
            )
    try:
        before, payload, after = source.stat(), source.read_bytes(), source.stat()
    except OSError as error:
        raise EvaluationAuthorityError("authority manifest cannot be read") from error

    def identity(stat: os.stat_result) -> tuple[int, int, int, int]:
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    if identity(before) != identity(after):
        raise EvaluationAuthorityError("authority manifest changed while loading")
    try:
        parsed = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_no_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationAuthorityError(
            "authority manifest is not valid UTF-8 JSON"
        ) from error
    if not isinstance(parsed, Mapping):
        raise EvaluationAuthorityError("authority manifest must be an object")
    supplied = _sha(parsed.get("manifest_digest"), "manifest digest")
    unsigned = dict(parsed)
    unsigned.pop("manifest_digest", None)
    if supplied != canonical_digest(unsigned):
        raise EvaluationAuthorityError("authority manifest self-digest mismatch")
    if supplied != expected:
        raise EvaluationAuthorityError(
            "caller-authenticated authority manifest digest mismatch"
        )
    manifest = EvaluationAuthorityManifest.from_document(parsed, source)
    moment = _time(as_of, "as_of")
    if moment < _time(manifest.not_before, "not_before"):
        raise EvaluationAuthorityError("authority manifest is not yet valid")
    if moment >= _time(manifest.expires_at, "expires_at"):
        raise EvaluationAuthorityError("authority manifest has expired")
    return manifest


def _git(repository: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None or not Path(executable).is_file():
        raise EvaluationAuthorityError("Git executable is unavailable")
    environment = {
        "PATH": str(Path(executable).parent),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        completed = subprocess.run(
            (executable, "-C", str(repository), *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EvaluationAuthorityError("repository Git inspection failed") from error
    if completed.returncode:
        raise EvaluationAuthorityError("repository Git inspection failed")
    return completed.stdout


def capture_repository_binding(repository_root: str | Path) -> RepositoryBinding:
    root = Path(repository_root)
    if not root.is_absolute():
        raise EvaluationAuthorityError("repository root must be absolute")
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise EvaluationAuthorityError("repository root is unavailable") from error
    identity = _git(root, "rev-parse", "HEAD^{commit}", "HEAD^{tree}").splitlines()
    if len(identity) != 2:
        raise EvaluationAuthorityError("repository HEAD/tree binding is malformed")
    status = _git(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    ).splitlines()
    diff = _git(root, "diff", "--binary", "HEAD")
    return RepositoryBinding(
        head_commit=identity[0],
        tree_oid=identity[1],
        state_digest=canonical_digest({"status": status, "diff": diff}),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundSurfaceEvidence:
    surface: SurfaceResult
    receipt: EvidenceReceipt
    parent_champion_digest: str
    authority_manifest_digest: str
    evaluation_plan_digest: str
    generation: int
    evaluator_id: str
    repository_head: str
    repository_tree: str
    contract_fingerprint: str
    harness_fingerprint: str
    holdout_commitment: str
    prior_outcome_digest: str | None = None
    comparator_id: str | None = None
    comparator_pin: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.surface, SurfaceResult) or not isinstance(
            self.receipt, EvidenceReceipt
        ):
            raise EvaluationAuthorityError(
                "bound evidence requires a surface and receipt"
            )
        for name in (
            "parent_champion_digest",
            "authority_manifest_digest",
            "evaluation_plan_digest",
            "contract_fingerprint",
            "harness_fingerprint",
            "holdout_commitment",
        ):
            _sha(getattr(self, name), name)
        _positive(self.generation, "surface generation")
        _text(self.evaluator_id, "surface evaluator")
        _oid(self.repository_head, "surface repository head")
        _oid(self.repository_tree, "surface repository tree")
        if self.generation == 1 and self.prior_outcome_digest is not None:
            raise EvaluationAuthorityError(
                "generation-1 surface cannot cite a prior outcome"
            )
        if self.generation == 2:
            _sha(self.prior_outcome_digest, "generation-2 prior outcome")
        if self.surface.kind is SurfaceKind.COMPARATOR:
            _text(self.comparator_id, "comparator id")
            _sha(self.comparator_pin, "comparator pin")
        elif self.comparator_id is not None or self.comparator_pin is not None:
            raise EvaluationAuthorityError(
                "only comparator surfaces may bind a comparator"
            )

    def content_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "receipt_id": self.receipt.receipt_id,
            "claim_id": self.receipt.claim_id,
            "candidate_digest": self.receipt.candidate_digest,
            "parent_champion_digest": self.parent_champion_digest,
            "authority_manifest_digest": self.authority_manifest_digest,
            "evaluation_plan_digest": self.evaluation_plan_digest,
            "prior_outcome_digest": self.prior_outcome_digest,
            "generation": self.generation,
            "evaluator_id": self.evaluator_id,
            "repository_head": self.repository_head,
            "repository_tree": self.repository_tree,
            "contract_fingerprint": self.contract_fingerprint,
            "harness_fingerprint": self.harness_fingerprint,
            "holdout_commitment": self.holdout_commitment,
            "comparator_id": self.comparator_id,
            "comparator_pin": self.comparator_pin,
            "surface": self.surface.document(),
        }


def _dependencies(
    parent: str, authority: str, plan: str, prior: str | None
) -> tuple[str, ...]:
    values = {
        _sha(parent, "parent digest"),
        _sha(authority, "authority digest"),
        _sha(plan, "plan digest"),
    }
    if prior is not None:
        values.add(_sha(prior, "prior outcome digest"))
    return tuple(sorted(values))


def store_bound_surface_evidence(
    store: ArtifactStore,
    *,
    surface: SurfaceResult,
    receipt_id: str,
    claim_id: str,
    candidate_digest: str,
    parent_champion_digest: str,
    authority_manifest_digest: str,
    evaluation_plan_digest: str,
    generation: int,
    evaluator_id: str,
    evaluator_trust_domain: str,
    repository_head: str,
    repository_tree: str,
    contract_fingerprint: str,
    harness_fingerprint: str,
    holdout_commitment: str,
    observed_at: str,
    expires_at: str,
    evidence_kind: EvidenceKind = EvidenceKind.STRUCTURAL,
    execution_mode: ExecutionMode = ExecutionMode.LOCAL,
    passed: bool = True,
    strict: bool = False,
    score: float | None = None,
    prior_outcome_digest: str | None = None,
    comparator_id: str | None = None,
    comparator_pin: str | None = None,
) -> BoundSurfaceEvidence:
    """External evaluator helper that publishes an immutable surface bundle."""

    if not isinstance(store, ArtifactStore):
        raise EvaluationAuthorityError("surface evidence requires an ArtifactStore")
    placeholder = EvidenceReceipt(
        receipt_id=receipt_id,
        claim_id=claim_id,
        candidate_digest=candidate_digest,
        evidence_kind=evidence_kind,
        passed=passed,
        issuer_id=evaluator_id,
        issuer_trust_domain=evaluator_trust_domain,
        observed_at=observed_at,
        expires_at=expires_at,
        artifact_digest="sha256:" + "0" * 64,
        execution_mode=execution_mode,
        strict=strict,
        score=score,
    )
    values = {
        "surface": surface,
        "parent_champion_digest": parent_champion_digest,
        "authority_manifest_digest": authority_manifest_digest,
        "evaluation_plan_digest": evaluation_plan_digest,
        "generation": generation,
        "evaluator_id": evaluator_id,
        "repository_head": repository_head,
        "repository_tree": repository_tree,
        "contract_fingerprint": contract_fingerprint,
        "harness_fingerprint": harness_fingerprint,
        "holdout_commitment": holdout_commitment,
        "prior_outcome_digest": prior_outcome_digest,
        "comparator_id": comparator_id,
        "comparator_pin": comparator_pin,
    }
    provisional = BoundSurfaceEvidence(receipt=placeholder, **values)  # type: ignore[arg-type]
    dependencies = _dependencies(
        parent_champion_digest,
        authority_manifest_digest,
        evaluation_plan_digest,
        prior_outcome_digest,
    )
    envelope = store.put(
        canonical_bytes(provisional.content_document()),
        media_type="application/vnd.hive-mind.evaluation-surface+json",
        candidate_digest=candidate_digest,
        dependency_digests=dependencies,
        schema_id=SURFACE_SCHEMA_ID,
        schema_version=SURFACE_SCHEMA_VERSION,
        schema_digest=SURFACE_SCHEMA_DIGEST,
        producer_id=evaluator_id,
    )
    receipt = EvidenceReceipt(
        receipt_id=receipt_id,
        claim_id=claim_id,
        candidate_digest=candidate_digest,
        evidence_kind=evidence_kind,
        passed=passed,
        issuer_id=evaluator_id,
        issuer_trust_domain=evaluator_trust_domain,
        observed_at=observed_at,
        expires_at=expires_at,
        artifact_digest=envelope.artifact_digest,
        execution_mode=execution_mode,
        strict=strict,
        score=score,
    )
    return BoundSurfaceEvidence(receipt=receipt, **values)  # type: ignore[arg-type]


def validate_bound_surface_evidence(
    evidence: BoundSurfaceEvidence,
    *,
    store: ArtifactStore,
    manifest: EvaluationAuthorityManifest,
    candidate: CandidateAuthorityBinding,
    evaluation_plan_digest: str,
    prior_outcome_digest: str | None,
) -> None:
    if not isinstance(evidence, BoundSurfaceEvidence):
        raise EvaluationAuthorityError("surface evidence is malformed")
    if evidence.receipt.candidate_digest != candidate.candidate_digest:
        raise EvaluationAuthorityError("surface receipt has wrong candidate binding")
    expected = {
        "parent_champion_digest": candidate.parent_champion_digest,
        "authority_manifest_digest": manifest.manifest_digest,
        "evaluation_plan_digest": evaluation_plan_digest,
        "generation": candidate.generation,
        "evaluator_id": manifest.identities.evaluator_id,
        "repository_head": manifest.repository_head,
        "repository_tree": manifest.repository_tree,
        "contract_fingerprint": manifest.contract_fingerprint,
        "harness_fingerprint": manifest.harness_fingerprint,
        "holdout_commitment": manifest.holdout_commitment,
        "prior_outcome_digest": prior_outcome_digest,
    }
    for name, value in expected.items():
        if getattr(evidence, name) != value:
            raise EvaluationAuthorityError(
                f"surface {name} does not match candidate authority"
            )
    if evidence.receipt.issuer_id != evidence.evaluator_id:
        raise EvaluationAuthorityError("surface receipt issuer is not the evaluator")
    if evidence.surface.kind is SurfaceKind.COMPARATOR:
        comparator = manifest.comparator(evidence.comparator_id or "")
        if evidence.comparator_pin != comparator.pin:
            raise EvaluationAuthorityError("comparator surface has a forged pin")
    dependencies = _dependencies(
        candidate.parent_champion_digest,
        manifest.manifest_digest,
        evaluation_plan_digest,
        prior_outcome_digest,
    )
    try:
        stored = store.read(evidence.receipt.artifact_digest)
    except (KeyError, ArtifactIntegrityError) as error:
        raise EvaluationAuthorityError(
            "surface receipt artifact is missing or mutated"
        ) from error
    envelope_expected = {
        "candidate_digest": candidate.candidate_digest,
        "dependency_digests": dependencies,
        "schema_id": SURFACE_SCHEMA_ID,
        "schema_version": SURFACE_SCHEMA_VERSION,
        "schema_digest": SURFACE_SCHEMA_DIGEST,
        "producer_id": manifest.identities.evaluator_id,
    }
    for name, value in envelope_expected.items():
        if getattr(stored.envelope, name) != value:
            raise EvaluationAuthorityError(
                f"surface artifact {name} binding is invalid"
            )
    # Replace the actual envelope address with the non-self-referential value
    # that was canonicalized before the address existed.
    content = evidence.content_document()
    content["candidate_digest"] = evidence.receipt.candidate_digest
    if stored.content != canonical_bytes(content):
        raise EvaluationAuthorityError(
            "surface artifact does not bind supplied measurements"
        )


def validate_surface_set(
    surfaces: Iterable[BoundSurfaceEvidence],
    *,
    store: ArtifactStore,
    manifest: EvaluationAuthorityManifest,
    candidate: CandidateAuthorityBinding,
    evaluation_plan_digest: str,
    prior_outcome_digest: str | None,
) -> tuple[BoundSurfaceEvidence, ...]:
    items = tuple(surfaces)
    if not items or len(items) > manifest.budget.max_surface_receipts:
        raise EvaluationAuthorityError("surface receipt set is empty or over budget")
    keys: set[tuple[SurfaceKind, str]] = set()
    receipt_ids: set[str] = set()
    for item in items:
        validate_bound_surface_evidence(
            item,
            store=store,
            manifest=manifest,
            candidate=candidate,
            evaluation_plan_digest=evaluation_plan_digest,
            prior_outcome_digest=prior_outcome_digest,
        )
        key = item.surface.kind, item.surface.name
        if key in keys or item.receipt.receipt_id in receipt_ids:
            raise EvaluationAuthorityError("surface or receipt id is duplicated")
        keys.add(key)
        receipt_ids.add(item.receipt.receipt_id)
    return tuple(
        sorted(items, key=lambda item: (item.surface.kind.value, item.surface.name))
    )
