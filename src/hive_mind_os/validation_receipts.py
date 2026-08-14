"""Privacy-safe, append-only validation receipts and bounded recovery state.

This module is intentionally independent of a particular test framework.  A
runner supplies its sealed discovery vector and structured terminal events; the
recorder refuses to infer results from human-oriented stdout.  That makes a
receipt useful for later diagnosis without turning it into a policy, promotion,
or implementation decision.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


class ValidationReceiptError(ValueError):
    """A receipt invariant was not met."""


class TerminalKind(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP_EXPLICIT = "SKIP_EXPLICIT"
    SKIP_CLASS = "SKIP_CLASS"
    SKIP_LIFECYCLE = "SKIP_LIFECYCLE"
    EXPECTED_FAILURE = "EXPECTED_FAILURE"
    UNEXPECTED_SUCCESS = "UNEXPECTED_SUCCESS"
    NOT_RUN_SESSION_ABORTED = "NOT_RUN_SESSION_ABORTED"
    NOT_RUN_POLICY_BLOCKED = "NOT_RUN_POLICY_BLOCKED"


class RecoveryState(StrEnum):
    BLOCKED = "BLOCKED"
    DIAGNOSE = "DIAGNOSE"
    REMEDIATE = "REMEDIATE"
    REVALIDATE = "REVALIDATE"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class CandidateStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    NON_PROMOTED = "NON_PROMOTED"


_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password)\b\s*[:=]\s*\S+|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|\b(?:gh[oprsu]_|sk-)[A-Za-z0-9_-]{8,}|"
    r"\b(?:private-)?api-token-[A-Za-z0-9_-]{4,})"
)
_HEX = re.compile(r"[0-9a-f]{40,64}\Z")
_ENVIRONMENT_KEYS = frozenset(
    {"os", "architecture", "python_implementation", "python_version", "sandbox", "network_policy"}
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest_json(value: object) -> str:
    return "sha256:" + sha256(canonical_bytes(value)).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def redact_text(value: str) -> tuple[str, int]:
    """Return repository-safe diagnostic text, never the original secret."""

    if not isinstance(value, str):
        raise ValidationReceiptError("diagnostic text must be text")
    if "\x00" in value:
        raise ValidationReceiptError("diagnostic text contains a NUL byte")
    redacted, count = _SECRET.subn("<redacted:credential>", value)
    if len(redacted.encode("utf-8")) > 16_384:
        raise ValidationReceiptError("redacted diagnostic text exceeds the receipt limit")
    return redacted, count


def _require_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", value
    ):
        raise ValidationReceiptError(f"{label} must be sha256:<64 lowercase hex>")


def _require_object_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValidationReceiptError(f"{label} must be a full lowercase Git object ID")


@dataclass(frozen=True, slots=True)
class SourceBinding:
    repository_id: str
    source_commit: str
    source_tree: str
    runner_contract_digest: str
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.repository_id.strip():
            raise ValidationReceiptError("repository_id is required")
        _require_object_id(self.source_commit, "source_commit")
        _require_object_id(self.source_tree, "source_tree")
        _require_sha(self.runner_contract_digest, "runner_contract_digest")
        unknown = set(self.environment) - _ENVIRONMENT_KEYS
        if unknown:
            raise ValidationReceiptError("environment contains fields outside the allowlist")
        for key, value in self.environment.items():
            if not isinstance(value, str) or not value:
                raise ValidationReceiptError(f"environment {key} must be a nonempty privacy-safe digest")
            if _SECRET.search(value):
                raise ValidationReceiptError("environment must not contain secret-like values")

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "runner_contract_digest": self.runner_contract_digest,
            "environment": dict(sorted(self.environment.items())),
        }


@dataclass(frozen=True, slots=True)
class CandidateApplicability:
    candidate_id: str
    candidate_commit: str
    candidate_tree: str
    parent_commit: str
    component_kind: str
    changed_path_manifest_digest: str
    source_target_commit: str
    source_target_tree: str
    required_composition: str
    authority_status: str
    status: CandidateStatus
    required_validation_contract_digest: str
    rollback_reference: str

    def __post_init__(self) -> None:
        for label, value in (("candidate_commit", self.candidate_commit), ("candidate_tree", self.candidate_tree),
                             ("parent_commit", self.parent_commit), ("source_target_commit", self.source_target_commit),
                             ("source_target_tree", self.source_target_tree)):
            _require_object_id(value, label)
        _require_sha(self.changed_path_manifest_digest, "changed_path_manifest_digest")
        _require_sha(self.required_validation_contract_digest, "required_validation_contract_digest")
        if not all((self.candidate_id, self.component_kind, self.required_composition, self.rollback_reference)):
            raise ValidationReceiptError("candidate metadata is incomplete")

    def applies_to(self, *, candidate_commit: str, candidate_tree: str, target_commit: str,
                   target_tree: str, composition: str, validation_contract_digest: str) -> bool:
        return (
            self.status is CandidateStatus.ELIGIBLE
            and self.authority_status == "authorized"
            and candidate_commit == self.candidate_commit
            and candidate_tree == self.candidate_tree
            and target_commit == self.source_target_commit
            and target_tree == self.source_target_tree
            and composition == self.required_composition
            and validation_contract_digest == self.required_validation_contract_digest
        )


@dataclass(frozen=True, slots=True)
class RecoveryEvent:
    state: RecoveryState
    blocker_signature: str
    at: str


@dataclass(frozen=True, slots=True)
class RevalidationAttempt:
    session_id: str
    predecessor_receipt_digest: str


@dataclass(slots=True)
class RecoveryCase:
    """Finite, append-only BLOCKED→DIAGNOSE→REMEDIATE→REVALIDATE recovery."""

    case_id: str
    predecessor_receipt_digest: str
    max_automatic_attempts: int = 2
    max_diagnosis_rounds_per_signature: int = 1
    max_remediation_rounds_per_signature: int = 1
    state: RecoveryState = RecoveryState.BLOCKED
    history: list[RecoveryEvent] = field(default_factory=list)
    escalation_reason: str | None = None
    session_id: str = field(default_factory=lambda: str(uuid4()), init=False)

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValidationReceiptError("case_id is required")
        _require_sha(self.predecessor_receipt_digest, "predecessor_receipt_digest")
        if self.max_automatic_attempts not in {1, 2} or self.max_diagnosis_rounds_per_signature != 1 or self.max_remediation_rounds_per_signature != 1:
            raise ValidationReceiptError("recovery budgets must use the sealed v1 bounds")
        if not self.history:
            self.history.append(RecoveryEvent(RecoveryState.BLOCKED, "initial", _utc_now()))

    def _move(self, state: RecoveryState, signature: str) -> None:
        self.state = state
        self.history.append(RecoveryEvent(state, signature, _utc_now()))

    def diagnose(self, blocker_signature: str) -> None:
        if self.state is not RecoveryState.BLOCKED:
            raise ValidationReceiptError("only blocked cases may diagnose")
        self._move(RecoveryState.DIAGNOSE, blocker_signature)

    def remediate(self, blocker_signature: str, *, remediation_id: str) -> None:
        if self.state is not RecoveryState.DIAGNOSE or not remediation_id:
            raise ValidationReceiptError("remediation requires diagnosis and a declared ID")
        self._move(RecoveryState.REMEDIATE, blocker_signature)

    def revalidate(self, *, new_session_id: str) -> RevalidationAttempt:
        if self.state is not RecoveryState.REMEDIATE or not new_session_id:
            raise ValidationReceiptError("revalidation requires remediation and a new session")
        if sum(event.state is RecoveryState.REVALIDATE for event in self.history) >= self.max_automatic_attempts:
            self._move(RecoveryState.ESCALATED, "retry-budget-exhausted")
            self.escalation_reason = "retry-budget-exhausted"
            raise ValidationReceiptError("recovery attempt budget exhausted")
        self._move(RecoveryState.REVALIDATE, "new-attempt")
        return RevalidationAttempt(new_session_id, self.predecessor_receipt_digest)

    def block(self, blocker_signature: str) -> None:
        if self.state is not RecoveryState.REVALIDATE:
            raise ValidationReceiptError("only revalidation may become blocked")
        diagnosed = {event.blocker_signature for event in self.history if event.state is RecoveryState.DIAGNOSE}
        if blocker_signature in diagnosed:
            self._move(RecoveryState.ESCALATED, blocker_signature)
            self.escalation_reason = "repeated-blocker-signature"
        else:
            self._move(RecoveryState.BLOCKED, blocker_signature)


class ValidationReceiptRecorder:
    """Capture a sealed vector and exactly one structured outcome for each ID."""

    def __init__(
        self,
        binding: SourceBinding,
        label_vocabulary: Mapping[str, TerminalKind],
        *,
        receipt_id: str | None = None,
    ) -> None:
        if not label_vocabulary:
            raise ValidationReceiptError("label_vocabulary is required")
        if any(not key or not isinstance(value, TerminalKind) for key, value in label_vocabulary.items()):
            raise ValidationReceiptError("label_vocabulary has an invalid entry")
        self.binding = binding
        self.label_vocabulary = dict(label_vocabulary)
        self.label_vocabulary_digest = digest_json(
            {key: value.value for key, value in sorted(self.label_vocabulary.items())}
        )
        self.receipt_id = receipt_id or str(uuid4())
        self._ids: tuple[str, ...] | None = None
        self._outcomes: dict[str, dict[str, Any]] = {}
        self._aborted: str | None = None

    def seal_discovery(self, test_ids: Iterable[str]) -> str:
        if self._ids is not None:
            raise ValidationReceiptError("discovery is already sealed")
        values = tuple(test_ids)
        if not values or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValidationReceiptError("discovery IDs must be nonempty strings")
        if len(set(values)) != len(values):
            raise ValidationReceiptError("discovery IDs must be unique")
        self._ids = values
        return digest_json([{"discovery_id": index, "test_id": value} for index, value in enumerate(values)])

    def record_outcome(
        self,
        test_id: str,
        label: str,
        *,
        reason_code: str | None = None,
        diagnostic: str | None = None,
    ) -> None:
        if self._ids is None:
            raise ValidationReceiptError("discovery must be sealed before outcomes")
        if test_id not in self._ids:
            raise ValidationReceiptError("outcome is outside the sealed discovery vector")
        if test_id in self._outcomes:
            raise ValidationReceiptError("a discovery ID already has a terminal outcome")
        kind = self.label_vocabulary.get(label)
        if kind is None:
            raise ValidationReceiptError("outcome label is outside the sealed vocabulary")
        needs_reason = kind.name.startswith("SKIP") or kind.name.startswith("NOT_RUN")
        if needs_reason != bool(reason_code):
            raise ValidationReceiptError("skip and not-run outcomes require a reason_code; other outcomes must omit it")
        entry: dict[str, Any] = {"test_id": test_id, "label": label, "terminal_kind": kind.value}
        if reason_code:
            entry["reason_code"] = reason_code
        if diagnostic is not None:
            text, redactions = redact_text(diagnostic)
            entry["diagnostic"] = text
            entry["redaction_count"] = redactions
        self._outcomes[test_id] = entry

    def abort(self, reason_code: str) -> None:
        if self._ids is None:
            raise ValidationReceiptError("discovery must be sealed before abort")
        if not reason_code:
            raise ValidationReceiptError("abort requires a reason_code")
        self._aborted = reason_code
        for test_id in self._ids:
            if test_id not in self._outcomes:
                self.record_outcome(test_id, self._label_for(TerminalKind.NOT_RUN_SESSION_ABORTED), reason_code=reason_code)

    def _label_for(self, kind: TerminalKind) -> str:
        labels = [key for key, candidate in self.label_vocabulary.items() if candidate == kind]
        if len(labels) != 1:
            raise ValidationReceiptError(f"vocabulary must define exactly one label for {kind}")
        return labels[0]

    def finalize(self) -> dict[str, Any]:
        if self._ids is None:
            raise ValidationReceiptError("discovery was not sealed")
        missing = [item for item in self._ids if item not in self._outcomes]
        if missing:
            raise ValidationReceiptError("each discovery ID needs exactly one terminal outcome")
        vector = [{"discovery_id": index, "test_id": item} for index, item in enumerate(self._ids)]
        ledger = [dict({"discovery_id": index}, **self._outcomes[item]) for index, item in enumerate(self._ids)]
        counts: dict[str, int] = {}
        for entry in ledger:
            counts[entry["terminal_kind"]] = counts.get(entry["terminal_kind"], 0) + 1
        result = "VALIDATED_SUCCEEDED" if not any(
            entry["terminal_kind"] in {TerminalKind.FAIL.value, TerminalKind.ERROR.value, TerminalKind.UNEXPECTED_SUCCESS.value}
            for entry in ledger
        ) and self._aborted is None else "VALIDATED_FAILED"
        receipt = {
            "schema_version": 1,
            "kind": "hive-mind-native-validation-receipt-v1",
            "receipt_id": self.receipt_id,
            "state": result,
            "captured_at": _utc_now(),
            "source_binding": self.binding.as_dict(),
            "label_vocabulary_digest": self.label_vocabulary_digest,
            "discovery_vector": vector,
            "discovery_vector_digest": digest_json(vector),
            "terminal_ledger": ledger,
            "terminal_ledger_digest": digest_json(ledger),
            "summary": {"discovery_count": len(vector), "ledger_count": len(ledger), "terminal_counts": dict(sorted(counts.items()))},
            "aborted": self._aborted,
        }
        receipt["receipt_digest"] = digest_json(receipt)
        return receipt

    def commit(self, root: str | Path) -> Path:
        """Atomically publish a complete, content-addressed receipt bundle."""

        receipt = self.finalize()
        store = Path(root).resolve()
        store.mkdir(parents=True, exist_ok=True)
        if store.is_symlink():
            raise ValidationReceiptError("receipt store must not be a symlink")
        name = receipt["receipt_digest"].removeprefix("sha256:")
        target = store / name
        if target.exists():
            existing = target / "receipt.json"
            if existing.is_file() and existing.read_bytes() == canonical_bytes(receipt):
                return target
            raise ValidationReceiptError("receipt identity collision")
        with tempfile.TemporaryDirectory(prefix=".receipt-", dir=store) as staging_name:
            staging = Path(staging_name)
            temporary = staging / "receipt.json"
            temporary.write_bytes(canonical_bytes(receipt))
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            manifest = {"receipt.json": "sha256:" + sha256(temporary.read_bytes()).hexdigest()}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            with (staging / "manifest.json").open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(staging, target)
        return target


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    discovery_id: int
    test_id: str
    selector_status: str

    def __post_init__(self) -> None:
        if self.discovery_id < 0 or not self.test_id or self.selector_status not in {"selected", "excluded_by_declared_selector"}:
            raise ValidationReceiptError("invalid discovery record")


@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    discovery_id: int
    test_id: str
    terminal_kind: TerminalKind
    terminal_label: str
    event_ordinal: int
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class NativeValidationReceipt:
    session_id: str
    source_commit: str
    source_tree: str
    runner_contract_digest: str
    discovery_vector: tuple[DiscoveryRecord, ...]
    terminal_ledger: tuple[TerminalOutcome, ...]
    label_vocabulary_digest: str
    diagnostics: tuple[str, ...]
    redaction_count: int

    @property
    def discovery_vector_digest(self) -> str:
        return digest_json([{"discovery_id": item.discovery_id, "test_id": item.test_id, "selector_status": item.selector_status} for item in self.discovery_vector])

    @property
    def validation_state(self) -> str:
        """Validation failure is evidence, not a reason to restart capture."""

        failed = {TerminalKind.FAIL, TerminalKind.ERROR, TerminalKind.UNEXPECTED_SUCCESS}
        return "VALIDATED_FAILED" if any(item.terminal_kind in failed for item in self.terminal_ledger) else "VALIDATED_SUCCEEDED"

    def to_document(self) -> dict[str, Any]:
        vector = [{"discovery_id": item.discovery_id, "test_id": item.test_id, "selector_status": item.selector_status} for item in self.discovery_vector]
        ledger = [{"discovery_id": item.discovery_id, "test_id": item.test_id, "terminal_kind": item.terminal_kind.value, "terminal_label": item.terminal_label, "event_ordinal": item.event_ordinal, "reason_code": item.reason_code} for item in self.terminal_ledger]
        document: dict[str, Any] = {
            "schema_version": 1, "kind": "hive-mind-native-validation-receipt-v1", "session_id": self.session_id,
            "state": self.validation_state,
            "source_commit": self.source_commit, "source_tree": self.source_tree,
            "runner_contract_digest": self.runner_contract_digest, "discovery_vector": vector,
            "discovery_vector_digest": self.discovery_vector_digest, "terminal_ledger": ledger,
            "terminal_ledger_digest": digest_json(ledger), "label_vocabulary_digest": self.label_vocabulary_digest,
            "privacy": {"redaction_count": self.redaction_count}, "diagnostics": list(self.diagnostics),
        }
        document["receipt_digest"] = digest_json(document)
        return document

    def verify(self) -> bool:
        document = self.to_document()
        return len(self.discovery_vector) == len(self.terminal_ledger) and document["receipt_digest"] == digest_json({key: value for key, value in document.items() if key != "receipt_digest"})


class ValidationReceiptCapture:
    """Framework-neutral structured capture API used by future validation adapters."""

    def __init__(self, *, session_id: str, label_vocabulary: Mapping[str, TerminalKind], source_commit: str, source_tree: str, runner_contract_digest: str) -> None:
        if not session_id or not label_vocabulary:
            raise ValidationReceiptError("session_id and label_vocabulary are required")
        _require_object_id(source_commit, "source_commit")
        _require_object_id(source_tree, "source_tree")
        _require_sha(runner_contract_digest, "runner_contract_digest")
        if any(not key or not isinstance(value, TerminalKind) for key, value in label_vocabulary.items()):
            raise ValidationReceiptError("label vocabulary is invalid")
        self.session_id, self.label_vocabulary = session_id, dict(label_vocabulary)
        self.source_commit, self.source_tree = source_commit, source_tree
        self.runner_contract_digest = runner_contract_digest
        self._vector: tuple[DiscoveryRecord, ...] | None = None
        self._ledger: dict[int, TerminalOutcome] = {}
        self._last_event = -1
        self._diagnostics: list[str] = []
        self._redaction_count = 0

    def seal_discovery(self, records: Iterable[DiscoveryRecord]) -> str:
        if self._vector is not None:
            raise ValidationReceiptError("discovery already sealed")
        vector = tuple(records)
        if not vector or [item.discovery_id for item in vector] != list(range(len(vector))) or len({item.test_id for item in vector}) != len(vector):
            raise ValidationReceiptError("discovery vector must be complete, ordered, and unique")
        self._vector = vector
        return digest_json([{"discovery_id": item.discovery_id, "test_id": item.test_id, "selector_status": item.selector_status} for item in vector])

    def record_diagnostic(self, value: str) -> None:
        text, count = redact_text(value)
        self._diagnostics.append(text.replace("<redacted:credential>", "<REDACTED:SECRET>"))
        self._redaction_count += count

    def record_outcome(self, outcome: TerminalOutcome) -> None:
        if self._vector is None:
            raise ValidationReceiptError("discovery must be sealed first")
        if outcome.discovery_id >= len(self._vector) or outcome.discovery_id < 0:
            raise ValidationReceiptError("outcome is outside the discovery vector")
        expected = self._vector[outcome.discovery_id]
        if expected.test_id != outcome.test_id or outcome.discovery_id in self._ledger:
            raise ValidationReceiptError("outcome has an invalid or duplicate binding")
        if self.label_vocabulary.get(outcome.terminal_label) is not outcome.terminal_kind:
            raise ValidationReceiptError("outcome label is not in the sealed vocabulary")
        if outcome.event_ordinal <= self._last_event:
            raise ValidationReceiptError("event ordinals must be strictly increasing")
        needs_reason = outcome.terminal_kind.name.startswith("SKIP") or outcome.terminal_kind.name.startswith("NOT_RUN")
        if needs_reason != bool(outcome.reason_code):
            raise ValidationReceiptError("skip/not-run outcomes require reason codes only")
        if expected.selector_status == "excluded_by_declared_selector" and outcome.terminal_kind is not TerminalKind.NOT_RUN_POLICY_BLOCKED:
            raise ValidationReceiptError("excluded IDs must be policy-blocked")
        self._ledger[outcome.discovery_id] = outcome
        self._last_event = outcome.event_ordinal

    def record_class_skip(self, *, discovery_ids: Iterable[int], terminal_label: str, event_ordinal: int, reason_code: str) -> None:
        ids = tuple(discovery_ids)
        if not ids:
            raise ValidationReceiptError("class skip must name affected discovery IDs")
        for offset, discovery_id in enumerate(ids):
            if self._vector is None or discovery_id >= len(self._vector):
                raise ValidationReceiptError("class skip is outside discovery")
            record = self._vector[discovery_id]
            self.record_outcome(TerminalOutcome(discovery_id, record.test_id, TerminalKind.SKIP_CLASS, terminal_label, event_ordinal + offset, reason_code))

    def finalize(self) -> NativeValidationReceipt:
        if self._vector is None or len(self._ledger) != len(self._vector):
            raise ValidationReceiptError("exactly one terminal outcome is required for every discovery ID")
        return NativeValidationReceipt(self.session_id, self.source_commit, self.source_tree, self.runner_contract_digest, self._vector, tuple(self._ledger[index] for index in range(len(self._vector))), digest_json({key: value.value for key, value in sorted(self.label_vocabulary.items())}), tuple(self._diagnostics), self._redaction_count)


@dataclass(frozen=True, slots=True)
class ReceiptReference:
    path: str
    digest: str


class ReceiptStore:
    """Same-filesystem atomic, content-addressed storage for complete receipt bundles."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValidationReceiptError("receipt store cannot be a symlink")

    def commit(self, receipt: NativeValidationReceipt) -> ReceiptReference:
        document = receipt.to_document()
        digest = document["receipt_digest"]
        name = digest.removeprefix("sha256:")
        target = self.root / name
        if target.exists():
            reference = ReceiptReference(name, digest)
            if self.verify(reference):
                return reference
            raise ValidationReceiptError("receipt digest collision")
        staging = Path(tempfile.mkdtemp(prefix=".receipt-", dir=self.root))
        try:
            body = canonical_bytes(document)
            (staging / "receipt.json").write_bytes(body)
            manifest = {"receipt.json": "sha256:" + sha256(body).hexdigest()}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.replace(staging, target)
        except Exception:
            if staging.exists():
                for item in staging.iterdir():
                    item.unlink()
                staging.rmdir()
            raise
        return ReceiptReference(name, digest)

    def verify(self, reference: ReceiptReference) -> bool:
        target = self.root / reference.path
        try:
            if target.parent != self.root or not target.is_dir() or target.is_symlink():
                return False
            body = (target / "receipt.json").read_bytes()
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("receipt.json") != "sha256:" + sha256(body).hexdigest():
                return False
            document = json.loads(body.decode("utf-8"))
            digest = document.pop("receipt_digest")
            return digest == reference.digest and digest == digest_json(document)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError):
            return False
