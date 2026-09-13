"""Immutable, content-addressed role prompts with atomic champion pointers."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Iterator, Mapping
from uuid import uuid4

from .ledger import EvidenceLedger
from .models import Role, utc_now
from .roles import ROLE_CONTRACTS, RoleContract

_GENERATION_ZERO_PROMOTERS = frozenset(
    {
        "repository:generation-0",
        "model-backend:generation-0",
    }
)
_ROOT_LOCKS: dict[Path, RLock] = {}
_ROOT_LOCKS_GUARD = Lock()


def _shared_root_lock(root: Path) -> RLock:
    with _ROOT_LOCKS_GUARD:
        return _ROOT_LOCKS.setdefault(root, RLock())


@contextmanager
def _interprocess_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def canonical_prompt_bytes(content: str | bytes) -> bytes:
    """Normalize line endings and remove all trailing LF, idempotently.

    Legacy artifacts produced by removing only one LF are never rewritten by
    this function's callers; conflicting retained bytes require explicit review.
    """

    if isinstance(content, bytes):
        text = content.decode("utf-8")
    else:
        text = content
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n").encode(
        "utf-8"
    )


def prompt_digest(content: str | bytes) -> str:
    return f"sha256:{sha256(canonical_prompt_bytes(content)).hexdigest()}"


def generation_zero_prompt(contract: RoleContract) -> str:
    """Render the exact P02 system prompt that predates the registry."""

    return (
        "You are the Hive Mind OS specialist for role "
        f"{contract.role.value}. Mission: {contract.mission}\n"
        "Return only a JSON object with summary, outputs, proposed_actions, lessons, "
        "and success. outputs must contain exactly these keys: "
        + ", ".join(contract.required_outputs)
        + ". Quality gates: "
        + "; ".join(contract.quality_gates)
    )


class PromotionAdmissionError(RuntimeError):
    """A typed refusal before champion and consumption commit."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RejectionPersistenceError(PromotionAdmissionError):
    """The refusal happened, but its durable observation could not be saved."""


class PromotionCommittedEvidencePending(RuntimeError):
    """The pointer committed; retry observation, never the promotion."""

    def __init__(self, admission_digest: str, prior_digest: str | None,
                 pointer_after: str | None, pending_operation: str) -> None:
        super().__init__(f"promotion committed; evidence pending: {pending_operation}")
        self.admission_digest = admission_digest
        self.prior_digest = prior_digest
        self.pointer_after = pointer_after
        self.pending_operation = pending_operation


class PromptRegistry:
    """Content-addressed prompt artifacts and per-role champion pointers."""

    def __init__(
        self,
        root: str | Path,
        *,
        ledger: EvidenceLedger | None = None,
        principal_verifier: Any = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.artifact_root = self.root / "artifacts"
        self.lineage_root = self.root / "lineage"
        self.event_root = self.root / "events"
        self.pointer_path = self.root / "champions.json"
        self.admission_root = self.root / "admissions"
        self.admission_root.mkdir(parents=True, exist_ok=True)
        self.principal_verifier = principal_verifier
        self.unknown_commit_path = self.root / "commit-state-unknown.json"
        for path in (self.artifact_root, self.lineage_root, self.event_root):
            path.mkdir(parents=True, exist_ok=True)
        self._owns_ledger = ledger is None
        self.ledger = ledger or EvidenceLedger(self.root / "prompt-ledger.sqlite3")
        self._lock = _shared_root_lock(self.root)
        self._pointer_lock_path = self.root / ".prompt-pointer.lock"

    @contextmanager
    def _pointer_transaction(self) -> Iterator[None]:
        with self._lock:
            with _interprocess_lock(self._pointer_lock_path):
                yield

    def close(self) -> None:
        if self._owns_ledger:
            self.ledger.close()

    @staticmethod
    def _role_value(role: Role | str) -> str:
        return Role(role).value

    @staticmethod
    def _digest_hex(digest: str) -> str:
        prefix, separator, value = digest.partition(":")
        if (
            prefix != "sha256"
            or separator != ":"
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("prompt digest must be canonical sha256:<64 lowercase hex>")
        return value

    def artifact_path(self, digest: str) -> Path:
        return self.artifact_root / f"{self._digest_hex(digest)}.prompt"

    def register(
        self,
        role: Role | str,
        content: str | bytes,
        *,
        parent_digest: str | None,
        created_by: str,
        experiment_id: str | None = None,
    ) -> str:
        role_value = self._role_value(role)
        if not created_by.strip():
            raise ValueError("prompt author identity is required")
        canonical = canonical_prompt_bytes(content)
        digest = prompt_digest(canonical)
        path = self.artifact_path(digest)
        with self._lock:
            try:
                with path.open("xb") as handle:
                    handle.write(canonical)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError:
                if path.read_bytes() != canonical:
                    raise PromotionAdmissionError(
                        "artifact-conflict", "content-addressed prompt artifact was mutated or uses legacy "
                        "canonicalization; preserve retained bytes for explicit migration review")
            record = {
                "schema_version": 1,
                "artifact_digest": digest,
                "role": role_value,
                "parent_digest": parent_digest,
                "created_by": created_by,
                "created_at": utc_now(),
                "experiment_id": experiment_id,
                "kind": "registration",
            }
            self._write_immutable_record(self.lineage_root, record)
            self.ledger.append_event(
                experiment_id or f"prompt:{role_value}",
                "prompt.registered",
                created_by,
                record,
            )
        return digest

    def bootstrap(
        self,
        prompt_dir: str | Path,
        *,
        created_by: str = "repository:generation-0",
    ) -> dict[str, str]:
        """Register committed generation-zero files and fill missing champions."""

        directory = Path(prompt_dir)
        digests: dict[str, str] = {}
        for role in Role:
            path = directory / f"{role.value}.txt"
            digest = self.register(
                role,
                path.read_bytes(),
                parent_digest=None,
                created_by=created_by,
            )
            digests[role.value] = digest
            if self.champion_digest(role) is None:
                self.promote(
                    role,
                    digest,
                    promoted_by=created_by,
                    experiment_id="generation-0",
                    expected_current=None,
                )
        return digests

    def read(self, digest: str) -> str:
        path = self.artifact_path(digest)
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise KeyError(digest) from None
        if content != canonical_prompt_bytes(content):
            raise PromotionAdmissionError(
                "artifact-noncanonical", "prompt artifact digest cannot authorize noncanonical bytes; "
                "preserve retained bytes for explicit migration review")
        if prompt_digest(content) != digest:
            raise RuntimeError("prompt artifact digest does not match its path")
        return content.decode("utf-8")

    def champion_digest(self, role: Role | str) -> str | None:
        role_value = self._role_value(role)
        self._ensure_known_commit()
        document = self._read_pointers()
        value = document["champions"].get(role_value)
        if value is None:
            return None
        if not isinstance(value, str) or not self.artifact_path(value).is_file():
            raise RuntimeError("champion pointer does not resolve to an artifact")
        if not self._champion_promotion_resolves(role_value, value):
            raise PromotionAdmissionError("legacy-promotion-evidence-required",
                                          "champion pointer lacks a resolving promotion record; explicit migration required")
        return value

    def champion_prompt(self, role: Role | str) -> tuple[str, str]:
        with self._pointer_transaction():
            digest = self.champion_digest(role)
            if digest is None:
                raise KeyError(self._role_value(role))
            if self.is_quarantined(digest):
                raise RuntimeError("active champion is quarantined")
            return self.read(digest), digest

    def promote(
        self, role: Role | str, digest: str, *, promoted_by: str,
        experiment_id: str, expected_current: str | None,
        decision_event_sequence: int | None = None,
    ) -> str | None:
        from .brain_kernel.canonical import canonical_digest

        role_value = self._role_value(role)
        if not promoted_by.strip() or not experiment_id.strip():
            raise ValueError("promotion identity and experiment id are required")
        with self._pointer_transaction():
            self._ensure_known_commit()
            pointers = self._read_pointers()
            prior = pointers["champions"].get(role_value)
            committed = False
            admission_digest = ""
            try:
                self.read(digest)
                if self.is_quarantined(digest):
                    raise PromotionAdmissionError("candidate-quarantined", "cannot promote a quarantined prompt artifact")
                if prior != expected_current:
                    raise PromotionAdmissionError("parent-stale", "champion changed since the experiment was bound")
                registration = self._promotion_registration(
                    role_value, digest, experiment_id=experiment_id,
                    expected_current=expected_current, promoted_by=promoted_by,
                )
                generation_zero = (
                    experiment_id == "generation-0" and expected_current is None
                    and registration.get("parent_digest") is None
                    and registration.get("created_by") == promoted_by
                    and promoted_by in _GENERATION_ZERO_PROMOTERS
                    and self.read(digest) == generation_zero_prompt(ROLE_CONTRACTS[Role(role_value)])
                )
                manifest: dict[str, Any]
                event: dict[str, Any] = {}
                if not generation_zero:
                    event = self._validate_decision_event(
                        role_value=role_value, digest=digest, promoted_by=promoted_by,
                        experiment_id=experiment_id, expected_current=expected_current,
                        registration=registration, decision_event_sequence=decision_event_sequence,
                    )
                    if event["payload"].get("action") != "apply":
                        raise PromotionAdmissionError("action-mismatch", "KEEP requires an apply authorization")
                    subject, reference, authorization = self._resolve_event_evidence(event, promoted_by=promoted_by)
                    if reference.record_digest in pointers.get("consumed_evaluations", {}):
                        raise PromotionAdmissionError("evaluation-replayed", "evaluation record was already consumed")
                    if any(nonce in pointers.get("consumed_nonces", {}) for nonce in authorization.nonce_ids):
                        raise PromotionAdmissionError("authorization-replayed", "authenticated principal nonce was already consumed")
                    manifest = {
                        "schema_version": 1, "kind": "prompt-promotion-admission",
                        "role": role_value, "candidate_digest": digest, "parent_digest": prior,
                        "experiment_id": experiment_id, "decision_event_sequence": decision_event_sequence,
                        "decision_event_digest": canonical_digest(event),
                        "evaluation_subject_digest": subject.subject_digest,
                        "evaluation_record": reference.document(),
                        "contract_fingerprint": subject.contract_fingerprint,
                        "evaluator_id": event["payload"]["evaluator_id"],
                        "judge_id": event["payload"]["judge_id"],
                        "promoter_id": promoted_by, "artifact_refs": list(subject.evidence_refs),
                        "rollback_digest": prior,
                        "admitted_at": utc_now(),
                        "authority_policy_digest": authorization.policy_digest,
                        "authorization_digest": authorization.authorization_digest,
                        "authorization_nonces": list(authorization.nonce_ids),
                    }
                    admission_digest = canonical_digest(manifest)
                    self._persist_manifest(admission_digest, manifest)
                    self.ledger.append_event(experiment_id, "prompt.promotion_prepared", promoted_by,
                                             {"admission_digest": admission_digest, "manifest": manifest})
                else:
                    manifest = {"schema_version": 1, "kind": "prompt-bootstrap-admission",
                                "role": role_value, "candidate_digest": digest, "parent_digest": None,
                                "experiment_id": experiment_id, "promoter_id": promoted_by,
                                "admitted_at": utc_now(), "rollback_digest": None,
                                "decision_event_sequence": None, "registration": registration}
                    admission_digest = canonical_digest(manifest)
                    self._persist_manifest(admission_digest, manifest)
                    self.ledger.append_event(experiment_id, "prompt.promotion_prepared", promoted_by,
                                             {"admission_digest": admission_digest, "manifest": manifest})
                updated = {**pointers, "champions": {**pointers["champions"], role_value: digest}}
                if generation_zero:
                    updated.update({"schema_version": 2,
                                    "promotion_bindings": {**pointers.get("promotion_bindings", {}), role_value: admission_digest},
                                    "consumed_evaluations": dict(pointers.get("consumed_evaluations", {})),
                                    "consumed_nonces": dict(pointers.get("consumed_nonces", {})),
                                    "bootstrap_bindings": {**pointers.get("bootstrap_bindings", {}), role_value: admission_digest}})
                else:
                    updated.update({
                        "schema_version": 2,
                        "promotion_bindings": {**pointers.get("promotion_bindings", {}), role_value: admission_digest},
                        "consumed_evaluations": {**pointers.get("consumed_evaluations", {}),
                                                 manifest["evaluation_record"]["record_digest"]: admission_digest},
                        "consumed_nonces": {**pointers.get("consumed_nonces", {}),
                                            **{nonce: admission_digest for nonce in manifest["authorization_nonces"]}},
                    })
                if not generation_zero:
                    # Re-open evidence at the commit boundary after preparation writes.
                    self._resolve_event_evidence(event, promoted_by=promoted_by)
                elif self.read(digest) != generation_zero_prompt(ROLE_CONTRACTS[Role(role_value)]):
                    raise PromotionAdmissionError("artifact-mismatch", "bootstrap prompt changed before commit")
                self._commit_pointer(pointers, updated, admission_digest, prior, digest)
                committed = True
                try:
                    self._observe_promotion(admission_digest, manifest)
                except Exception as error:
                    raise PromotionCommittedEvidencePending(admission_digest, prior, digest, "promotion-observation") from error
                return prior
            except Exception as error:
                if not committed and not isinstance(error, PromotionCommittedEvidencePending) and getattr(error, "code", "") != "commit-state-unknown":
                    self._retain_rejection(error, role_value, digest, promoted_by, experiment_id,
                                           expected_current, prior, decision_event_sequence)
                raise

    def _commit_pointer(self, prior: Mapping[str, Any], proposed: Mapping[str, Any],
                        admission: str, before: str | None, after: str | None) -> None:
        try:
            self._atomic_json(self.pointer_path, proposed)
        except Exception as error:
            try:
                observed = self._read_pointers()
            except (OSError, ValueError, RuntimeError) as read_error:
                self._mark_unknown_commit({"prior": prior, "proposed": proposed,
                                           "observation_error": str(read_error)})
                raise PromotionAdmissionError("commit-state-unknown", "pointer commit state cannot be read") from error
            if observed == proposed:
                raise PromotionCommittedEvidencePending(admission, before, after, "pointer-write-observation") from error
            if observed != prior:
                self._mark_unknown_commit({"prior": prior, "proposed": proposed, "observed": observed})
                raise PromotionAdmissionError("commit-state-unknown", "pointer commit state is unknown; recovery is blocked") from error
            raise

    def _mark_unknown_commit(self, observation: Mapping[str, Any]) -> None:
        from .brain_kernel.canonical import canonical_bytes

        # Do not depend on the pointer replacement primitive that just failed.
        # Even an interrupted partial marker blocks restart until explicitly repaired.
        try:
            with self.unknown_commit_path.open("xb") as handle:
                handle.write(canonical_bytes(dict(observation)) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return
        except OSError as error:
            raise PromotionAdmissionError("commit-state-unknown",
                                          "pointer state is unknown and blocker persistence failed") from error

    def _ensure_known_commit(self) -> None:
        if self.unknown_commit_path.exists():
            raise PromotionAdmissionError("commit-state-unknown", "registry has an unresolved pointer commit")

    def _persist_manifest(self, digest: str, manifest: Mapping[str, Any]) -> None:
        from .brain_kernel.canonical import canonical_bytes

        path = self.admission_root / (self._digest_hex(digest) + ".json")
        payload = canonical_bytes(dict(manifest)) + b"\n"
        if path.exists():
            if path.read_bytes() != payload:
                raise PromotionAdmissionError("admission-persistence-failed", "admission manifest was substituted")
            return
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _resolve_event_evidence(self, event: Mapping[str, Any], *, promoted_by: str,
                                admitted_at: str | None = None) -> tuple[Any, Any, Any]:
        from .brain_kernel.canonical import canonical_digest
        from .brain_kernel.evaluation_admission import (
            load_evaluation_record,
            recheck_resolved_evidence,
            resolve_decision_evidence,
        )
        from .brain_kernel.evaluation_runtime import (
            EvaluationError,
            EvaluationRecordReference,
            EvaluationVerdict,
            PromptEvaluationSubject,
        )

        payload = event["payload"]
        if not payload.get("evaluation_subject") or not payload.get("evaluation_record"):
            raise PromotionAdmissionError("evaluation-missing", "promotion requires an exact evaluation subject and record")
        try:
            subject = PromptEvaluationSubject.from_document(payload["evaluation_subject"])
            reference = EvaluationRecordReference.from_document(payload["evaluation_record"])
        except (EvaluationError, TypeError, KeyError) as error:
            raise PromotionAdmissionError("evaluation-malformed", str(error)) from error
        expected = {
            "candidate_id": subject.candidate_id, "role": subject.role,
            "candidate_digest": subject.artifact_digest, "current_digest": subject.parent_champion_digest,
            "registration_experiment_id": subject.experiment_id, "proposer_id": subject.proposer_id,
            "builder_id": subject.builder_id, "contract_fingerprint": subject.contract_fingerprint,
            "retained_artifact_refs": list(subject.evidence_refs),
            "evaluation_subject_digest": subject.subject_digest,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise PromotionAdmissionError("subject-mismatch", "evaluation subject does not match decision candidate")
        candidate_binding = {
            "candidate_id": subject.candidate_id, "role": subject.role, "experiment_id": subject.experiment_id,
            "artifact_digest": subject.artifact_digest, "parent_champion_digest": subject.parent_champion_digest,
            "proposer_id": subject.proposer_id, "builder_id": subject.builder_id,
            "evidence_refs": list(subject.evidence_refs),
        }
        if payload.get("decision_binding_digest") != canonical_digest(candidate_binding):
            raise PromotionAdmissionError("decision-binding-mismatch", "candidate decision binding was substituted")
        # STOP is a court decision to close work, not a measured evaluation
        # outcome. Reproduce its exact referenced outcome without relabelling it.
        verdict = (load_evaluation_record(reference).verdict if payload["verdict"] == "stop"
                   else EvaluationVerdict(payload["verdict"]))
        resolved = resolve_decision_evidence(subject, reference, evaluator_id=payload["evaluator_id"],
                                             verdict=verdict)
        if self.principal_verifier is None:
            raise PromotionAdmissionError("authority-unconfigured", "promotion requires a trusted principal verifier")
        authorization = self._verify_principals(payload, subject, reference, promoted_by, admitted_at=admitted_at)
        recheck_resolved_evidence(resolved)
        for digest in (subject.artifact_digest, subject.parent_champion_digest):
            if digest is not None:
                raw = self.artifact_path(digest).read_bytes()
                if raw != canonical_prompt_bytes(raw) or prompt_digest(raw) != digest:
                    raise PromotionAdmissionError("artifact-mismatch", "registered prompt bytes do not match the bound artifact")
        return subject, reference, authorization

    def _verify_principals(self, payload: Mapping[str, Any], subject: Any, reference: Any,
                           promoted_by: str, *, admitted_at: str | None) -> Any:
        from .brain_kernel.canonical import canonical_digest

        if payload.get("promoter_id") != promoted_by or promoted_by == subject.proposer_id:
            raise PromotionAdmissionError("identity-mismatch", "promotion requires an explicit authenticated promoter")
        return self.principal_verifier.verify_authorization(
            payload.get("authorization"), subject_digest=subject.subject_digest,
            record_digest=reference.record_digest, builder_id=subject.builder_id,
            evaluator_id=payload["evaluator_id"], judge_id=payload["judge_id"],
            promoter_id=promoted_by,
            decision_digest=canonical_digest({key: value for key, value in payload.items() if key != "authorization"}),
            now=datetime.fromisoformat(admitted_at) if admitted_at else datetime.now(timezone.utc),
        )

    def _retain_rejection(self, error: BaseException, role: str, digest: str, actor: str,
                          experiment: str, expected: str | None, observed: str | None,
                          sequence: int | None) -> None:
        from .brain_kernel.canonical import canonical_digest

        record: dict[str, Any] = {
            "schema_version": 1, "attempt_id": str(uuid4()),
            "code": getattr(error, "code", "decision-binding-mismatch"),
            "role": role, "candidate_digest": digest, "expected_current": expected,
            "actor": actor, "experiment_id": experiment,
            "observed_current": observed, "decision_event_sequence": sequence,
            "pointer_unchanged": True, "message": str(error), "recorded_at": utc_now(),
        }
        try:
            event = next((event for event in self.ledger.events(experiment) if event["sequence"] == sequence), None)
            payload = event["payload"] if event is not None else {}
            record["evaluation_subject_digest"] = payload.get("evaluation_subject_digest")
            record["evaluation_record"] = payload.get("evaluation_record")
            record["decision_binding_digest"] = payload.get("decision_binding_digest")
            record["decision_event_digest"] = canonical_digest(event) if event is not None else None
            reference = payload.get("evaluation_record")
            record["evaluation_record_digest"] = reference.get("record_digest") if isinstance(reference, Mapping) else None
            auth = payload.get("authorization")
            record["authorization_digest"] = canonical_digest(auth) if auth is not None else None
            record["binding_status"] = "declared-unvalidated"
            if self.principal_verifier is not None:
                record["authentication"] = self.principal_verifier.sign_rejection(record)
            else:
                record["authentication_status"] = "unconfigured"
            self._write_immutable_record(self.event_root, {"kind": "promotion-rejection", **record})
            self.ledger.append_event(experiment, "prompt.promotion_rejected", actor, record)
            # Carry the under-lock observation to higher-level receipts; an
            # earlier caller-side read may already be stale under competing writers.
            setattr(error, "observed_current", observed)
        except Exception as failure:
            # A custody outage must remain observable without claiming a signature.
            diagnostic = {"kind": "promotion-rejection-unavailable", **record,
                          "authentication_status": "unavailable", "persistence_error": str(failure)}
            diagnostic.pop("authentication", None)
            try:
                self._write_immutable_record(self.event_root, diagnostic)
            except OSError:
                pass  # The typed error below explicitly reports that retention failed.
            raise RejectionPersistenceError("rejection-persistence-failed",
                                             f"{record['code']}: rejection persistence failed: {failure}") from error

    def _observe_promotion(self, digest: str, manifest: Mapping[str, Any]) -> None:
        if manifest.get("kind") == "prompt-adverse-admission":
            self._observe_adverse(digest, manifest)
            return
        records = [item for item in self.lineage(manifest["candidate_digest"])
                   if item.get("admission_digest") == digest and item.get("kind") == "promotion"]
        if records:
            record = records[0]
        else:
            record = {
                "schema_version": 2, "kind": "promotion", "role": manifest["role"],
                "artifact_digest": manifest["candidate_digest"], "parent_digest": manifest["parent_digest"],
                "created_by": manifest["promoter_id"], "created_at": manifest["admitted_at"],
                "experiment_id": manifest["experiment_id"],
                "decision_event_sequence": manifest["decision_event_sequence"],
                "rollback_digest": manifest["rollback_digest"], "admission_digest": digest,
                "evaluation_record_digest": manifest.get("evaluation_record", {}).get("record_digest"),
            }
            self._write_immutable_record(self.lineage_root, record)
        if not any(item["event_type"] == "prompt.promoted" and item["payload"].get("admission_digest") == digest
                   for item in self.ledger.events(manifest["experiment_id"])):
            self.ledger.append_event(manifest["experiment_id"], "prompt.promoted", manifest["promoter_id"], record)

    def _committed_manifest(self, digest: str, pointers: Mapping[str, Any]) -> dict[str, Any]:
        from .brain_kernel.canonical import canonical_bytes, canonical_digest

        path = self.admission_root / (self._digest_hex(digest) + ".json")
        raw = path.read_bytes()
        manifest = json.loads(raw)
        if canonical_digest(manifest) != digest or raw != canonical_bytes(manifest) + b"\n":
            raise PromotionAdmissionError("admission-mismatch", "admission manifest does not resolve")
        if (type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
                or manifest.get("kind") not in {"prompt-promotion-admission", "prompt-bootstrap-admission", "prompt-adverse-admission"}):
            raise PromotionAdmissionError("admission-mismatch", "unsupported admission schema or kind")
        if manifest.get("kind") == "prompt-adverse-admission":
            return self._committed_adverse(digest, manifest, pointers)
        if manifest.get("kind") == "prompt-bootstrap-admission":
            if (pointers.get("bootstrap_bindings", {}).get(manifest["role"]) != digest
                    or manifest["parent_digest"] is not None or manifest["rollback_digest"] is not None
                    or manifest["experiment_id"] != "generation-0" or manifest["decision_event_sequence"] is not None
                    or manifest["promoter_id"] not in _GENERATION_ZERO_PROMOTERS
                    or self.read(manifest["candidate_digest"]) != generation_zero_prompt(ROLE_CONTRACTS[Role(manifest["role"])])
                    or manifest["registration"] not in self.lineage(manifest["candidate_digest"])
                    or manifest["registration"].get("kind") != "registration"
                    or manifest["registration"].get("parent_digest") is not None
                    or manifest["registration"].get("role") != manifest["role"]
                    or manifest["registration"].get("created_by") != manifest["promoter_id"]
                    or not any(event["event_type"] == "prompt.promotion_prepared"
                               and event["payload"] == {"admission_digest": digest, "manifest": manifest}
                               for event in self.ledger.events("generation-0"))):
                raise PromotionAdmissionError("admission-mismatch", "bootstrap admission does not resolve")
            return manifest
        if pointers.get("consumed_evaluations", {}).get(manifest["evaluation_record"]["record_digest"]) != digest:
            raise PromotionAdmissionError("admission-uncommitted", "preparation has no committed consumption")
        events = self.ledger.events(manifest["experiment_id"])
        if not any(event["event_type"] == "prompt.promotion_prepared"
                   and event["payload"] == {"admission_digest": digest, "manifest": manifest} for event in events):
            raise PromotionAdmissionError("admission-unprepared", "committed admission has no preparation")
        event = next((event for event in events if event["sequence"] == manifest["decision_event_sequence"]), None)
        if event is None or canonical_digest(event) != manifest["decision_event_digest"]:
            raise PromotionAdmissionError("decision-binding-mismatch", "admission decision does not resolve")
        if self.principal_verifier is None or manifest.get("authority_policy_digest") != self.principal_verifier.policy_digest:
            raise PromotionAdmissionError("authority-policy-mismatch", "committed admission requires its trusted policy")
        self._validate_decision_event(
            role_value=manifest["role"], digest=manifest["candidate_digest"],
            promoted_by=manifest["promoter_id"], experiment_id=manifest["experiment_id"],
            expected_current=manifest["parent_digest"],
            registration=self._promotion_registration(
                manifest["role"], manifest["candidate_digest"], experiment_id=manifest["experiment_id"],
                expected_current=manifest["parent_digest"], promoted_by=manifest["promoter_id"],
            ), decision_event_sequence=manifest["decision_event_sequence"],
        )
        subject, reference, authorization = self._resolve_event_evidence(
            event, promoted_by=manifest["promoter_id"], admitted_at=manifest["admitted_at"],
        )
        if (authorization.authorization_digest != manifest.get("authorization_digest")
                or list(authorization.nonce_ids) != manifest.get("authorization_nonces")
                or any(pointers.get("consumed_nonces", {}).get(nonce) != digest for nonce in authorization.nonce_ids)):
            raise PromotionAdmissionError("authorization-mismatch", "committed principal authorization does not resolve")
        if (subject.subject_digest != manifest["evaluation_subject_digest"]
                or reference.document() != manifest["evaluation_record"]
                or subject.artifact_digest != manifest["candidate_digest"]
                or subject.role != manifest["role"] or subject.parent_champion_digest != manifest["parent_digest"]
                or subject.experiment_id != manifest["experiment_id"]
                or subject.contract_fingerprint != manifest["contract_fingerprint"]
                or list(subject.evidence_refs) != manifest["artifact_refs"]
                or manifest["rollback_digest"] != manifest["parent_digest"]
                or event["payload"]["evaluator_id"] != manifest["evaluator_id"]
                or event["payload"]["judge_id"] != manifest["judge_id"]):
            raise PromotionAdmissionError("admission-mismatch", "admission cross-binding is invalid")
        return manifest

    def recover_promotion_observation(self, admission_digest: str, *, actor: str) -> None:
        if not actor.strip():
            raise ValueError("recovery actor is required")
        with self._pointer_transaction():
            self._ensure_known_commit()
            manifest = self._committed_manifest(admission_digest, self._read_pointers())
            self._observe_promotion(admission_digest, manifest)

    def _promotion_registration(
        self,
        role_value: str,
        digest: str,
        *,
        experiment_id: str,
        expected_current: str | None,
        promoted_by: str,
    ) -> dict[str, Any]:
        registrations = [
            record
            for record in self.lineage(digest)
            if record.get("kind") == "registration"
            and record.get("role") == role_value
            and record.get("parent_digest") == expected_current
            and (
                (
                    experiment_id == "generation-0"
                    and record.get("created_by") == promoted_by
                )
                or record.get("experiment_id") == experiment_id
            )
        ]
        if not registrations:
            raise RuntimeError(
                "promotion lacks a matching artifact registration"
            )
        return registrations[-1]

    def _champion_promotion_resolves(self, role_value: str, digest: str) -> bool:
        """Require the pointer to be anchored by a still-resolving promotion."""

        self._ensure_known_commit()
        pointers = self._read_pointers()
        binding = pointers.get("promotion_bindings", {}).get(role_value)
        if binding:
            manifest = self._committed_manifest(binding, pointers)
            return (manifest["kind"] in {"prompt-promotion-admission", "prompt-bootstrap-admission"}
                    and manifest["role"] == role_value and manifest["candidate_digest"] == digest)
        return self._bootstrap_promotion_resolves(role_value, digest)

    def _bootstrap_promotion_resolves(self, role_value: str, digest: str) -> bool:
        promotions = [
            record
            for record in self.lineage(digest)
            if record.get("kind") == "promotion"
            and record.get("role") == role_value
            and record.get("artifact_digest") == digest
        ]
        for record in reversed(promotions):
            experiment_id = record.get("experiment_id")
            if not isinstance(experiment_id, str) or not experiment_id:
                continue
            sequence = record.get("decision_event_sequence")
            if experiment_id == "generation-0" and sequence is None:
                if (record.get("created_by") not in _GENERATION_ZERO_PROMOTERS
                        or record.get("parent_digest") is not None
                        or self.read(digest) != generation_zero_prompt(ROLE_CONTRACTS[Role(role_value)])):
                    continue
                if any(
                    event.get("event_type") == "prompt.promoted"
                    and event.get("run_id") == experiment_id
                    and event.get("payload") == record
                    for event in self.ledger.events(experiment_id)
                ):
                    return True
                continue
            # Historical non-bootstrap records remain inspectable, but cannot
            # activate a pointer without committed evaluation admission.
            continue
        return False

    def _validate_decision_event(
        self,
        *,
        role_value: str,
        digest: str,
        promoted_by: str,
        experiment_id: str,
        expected_current: str | None,
        registration: Mapping[str, Any],
        decision_event_sequence: int | None,
    ) -> dict[str, Any]:
        if type(decision_event_sequence) is not int or decision_event_sequence < 1:
            raise RuntimeError(
                "non-generation-zero promotion requires an experiment.decision event"
            )
        matches = [
            event
            for event in self.ledger.events(experiment_id)
            if event.get("sequence") == decision_event_sequence
        ]
        if len(matches) != 1:
            raise RuntimeError("promotion decision event sequence does not resolve")
        event = matches[0]
        if (
            event.get("run_id") != experiment_id
            or event.get("event_type") != "experiment.decision"
        ):
            raise RuntimeError("promotion decision event has the wrong binding")
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise RuntimeError("promotion decision payload is malformed")
        expected_fields = {
            "verdict": "keep",
            "action": "apply",
            "role": role_value,
            "candidate_digest": digest,
            "current_digest": expected_current,
            "registration_experiment_id": experiment_id,
            "registration_role": role_value,
            "registration_author": registration.get("created_by"),
            "registration_parent_digest": expected_current,
        }
        for field, expected in expected_fields.items():
            if payload.get(field) != expected:
                raise RuntimeError(
                    f"promotion decision has mismatched {field}"
                )
        if (
            registration.get("experiment_id") != experiment_id
            or registration.get("role") != role_value
            or registration.get("parent_digest") != expected_current
        ):
            raise RuntimeError("promotion registration is not experiment-bound")
        identities = (
            payload.get("proposer_id"),
            payload.get("builder_id"),
            payload.get("evaluator_id"),
            payload.get("judge_id"),
        )
        if any(
            not isinstance(identity, str) or not identity.strip()
            for identity in identities
        ) or len(set(identities)) != 4:
            raise RuntimeError(
                "promotion requires four distinct proposer, builder, evaluator, "
                "and judge identities"
            )
        judge_id = identities[-1]
        if event.get("actor") != judge_id:
            raise RuntimeError(
                "promotion event actor must be the decision judge"
            )
        if payload.get("registration_author") != identities[0]:
            raise RuntimeError(
                "promotion proposer must be the registered artifact author"
            )
        artifact_refs = payload.get("retained_artifact_refs")
        if (
            not isinstance(artifact_refs, list)
            or not artifact_refs
            or len(artifact_refs) != len(set(artifact_refs))
            or any(
                not isinstance(reference, str) or not reference.strip()
                for reference in artifact_refs
            )
        ):
            raise RuntimeError(
                "promotion decision requires retained artifact references"
            )
        fingerprint = payload.get("contract_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise RuntimeError(
                "promotion decision requires a contract fingerprint"
            )

        return event

    def rollback_champion(
        self,
        role: Role | str,
        to_digest: str,
        *,
        actor: str,
        reason: str,
        experiment_id: str | None = None,
        decision_event_sequence: int | None = None,
        expected_current: str | None = None,
    ) -> str:
        """Restore an exact retained binding using a fresh signed adverse decision.

        Legacy callers remain callable, but actor labels alone grant no authority.
        """
        prior = self._admit_adverse(role, actor=actor, action="rollback", to_digest=to_digest,
                                    reason=reason, experiment_id=experiment_id,
                                    decision_event_sequence=decision_event_sequence,
                                    expected_current=expected_current)
        if prior is None:
            raise RuntimeError("rollback committed without a prior champion")
        return prior

    def apply_adverse_decision(self, role: Role | str, *, actor: str, experiment_id: str,
                               decision_event_sequence: int) -> str | None:
        return self._admit_adverse(role, actor=actor, action="apply", experiment_id=experiment_id,
                                    decision_event_sequence=decision_event_sequence)

    def _rollback_binding(self, role_value: str, to_digest: str, pointers: Mapping[str, Any]) -> str | None:
        self.read(to_digest)
        if self.is_quarantined(to_digest):
            raise RuntimeError("cannot roll back to a quarantined prompt artifact")
        bootstrap = pointers.get("bootstrap_bindings", {}).get(role_value)
        if bootstrap is not None:
            manifest = self._committed_manifest(bootstrap, pointers)
            if manifest["kind"] != "prompt-bootstrap-admission" or manifest["role"] != role_value:
                raise PromotionAdmissionError("admission-mismatch", "bootstrap target has a different admission kind or role")
            if manifest["candidate_digest"] == to_digest:
                return bootstrap
        # Consumption is authoritative even when final lineage observation is pending.
        for binding in set(pointers.get("consumed_evaluations", {}).values()):
            path = self.admission_root / (self._digest_hex(binding) + ".json")
            manifest = json.loads(path.read_bytes())
            if (manifest.get("kind") == "prompt-promotion-admission"
                    and manifest.get("role") == role_value and manifest.get("candidate_digest") == to_digest):
                self._committed_manifest(binding, pointers)
                return binding
        if not any(record.get("kind") == "promotion" and record.get("role") == role_value
                   for record in self.lineage(to_digest)):
            raise RuntimeError("rollback target was never a promoted champion for this role")
        if (self.read(to_digest) == generation_zero_prompt(ROLE_CONTRACTS[Role(role_value)])
                and self._bootstrap_promotion_resolves(role_value, to_digest)):
            return None
        raise PromotionAdmissionError("legacy-promotion-evidence-required", "rollback target requires evaluation admission")

    def _adverse_event(self, role_value: str, experiment: str, sequence: int | None,
                       actor: str, action: str, *, admitted_at: str | None = None) -> tuple[Any, Any, Any, Any]:
        if type(sequence) is not int or sequence < 1:
            raise PromotionAdmissionError("decision-missing", "adverse action requires an experiment.decision event")
        event = next((item for item in self.ledger.events(experiment) if item["sequence"] == sequence), None)
        if event is None or event["event_type"] != "experiment.decision" or event["run_id"] != experiment:
            raise PromotionAdmissionError("decision-binding-mismatch", "adverse decision event does not resolve")
        payload = event["payload"]
        allowed = {"discard", "quarantine"} if action == "rollback" else {"discard", "quarantine", "retest", "stop"}
        if (payload.get("verdict") not in allowed or payload.get("action") != action
                or payload.get("role") != role_value or payload.get("registration_role") != role_value
                or payload.get("registration_experiment_id") != experiment
                or event["actor"] != payload.get("judge_id")
                or payload.get("registration_author") != payload.get("proposer_id")
                or payload.get("registration_parent_digest") != payload.get("current_digest")):
            raise PromotionAdmissionError("decision-binding-mismatch", "adverse decision action or candidate binding differs")
        identities = [payload.get(key) for key in ("proposer_id", "builder_id", "evaluator_id", "judge_id", "promoter_id")]
        if any(type(value) is not str or not value.strip() for value in identities) or len(set(identities)) != 5:
            raise PromotionAdmissionError("identity-mismatch", "adverse action requires five distinct identities")
        if not any(record.get("kind") == "registration" and record.get("role") == role_value
                   and record.get("created_by") == payload["proposer_id"]
                   and record.get("parent_digest") == payload["current_digest"]
                   and (action == "rollback" or record.get("experiment_id") == experiment)
                   for record in self.lineage(payload["candidate_digest"])):
            raise PromotionAdmissionError("registration-mismatch", "adverse action lacks a matching artifact registration")
        reasons = payload.get("reasons")
        if (type(reasons) is not list or not reasons
                or any(type(reason) is not str or not reason.strip() for reason in reasons)
                or len(set(reasons)) != len(reasons)):
            raise PromotionAdmissionError("decision-malformed", "adverse decision requires exact nonempty reasons")
        subject, reference, authorization = self._resolve_event_evidence(event, promoted_by=actor, admitted_at=admitted_at)
        return event, subject, reference, authorization

    def _admit_adverse(self, role: Role | str, *, actor: str, action: str,
                       experiment_id: str | None, decision_event_sequence: int | None,
                       to_digest: str | None = None, reason: str | None = None,
                       expected_current: str | None = None) -> str | None:
        from .brain_kernel.canonical import canonical_digest

        role_value = self._role_value(role)
        experiment = experiment_id or f"prompt:{role_value}"
        candidate_digest = to_digest or "unresolved"
        with self._pointer_transaction():
            self._ensure_known_commit()
            pointers = self._read_pointers()
            prior = pointers["champions"].get(role_value)
            committed = False
            try:
                target_binding = None
                if action == "rollback":
                    if to_digest is None:
                        raise PromotionAdmissionError("target-missing", "rollback requires an exact target")
                    target_binding = self._rollback_binding(role_value, to_digest, pointers)
                    if prior is None or prior == to_digest:
                        raise PromotionAdmissionError("parent-stale", "rollback requires a different active champion")
                event, subject, reference, authorization = self._adverse_event(
                    role_value, experiment, decision_event_sequence, actor, action)
                candidate_digest = subject.artifact_digest
                if action == "rollback":
                    if (expected_current != prior or subject.artifact_digest != prior
                            or subject.parent_champion_digest != to_digest
                            or reason != "; ".join(event["payload"]["reasons"])):
                        raise PromotionAdmissionError("parent-stale", "rollback live candidate, target or reason differs from authorization")
                elif subject.parent_champion_digest != prior or subject.artifact_digest == prior:
                    raise PromotionAdmissionError("parent-stale", "adverse candidate no longer matches the live parent")
                if reference.record_digest in pointers.get("consumed_evaluations", {}):
                    raise PromotionAdmissionError("evaluation-replayed", "evaluation record was already consumed")
                if any(nonce in pointers.get("consumed_nonces", {}) for nonce in authorization.nonce_ids):
                    raise PromotionAdmissionError("authorization-replayed", "authenticated principal nonce was already consumed")
                manifest = {
                    "schema_version": 1, "kind": "prompt-adverse-admission", "action": action,
                    "role": role_value, "candidate_digest": subject.artifact_digest,
                    "prior_digest": prior, "pointer_after": to_digest if action == "rollback" else prior,
                    "target_binding": target_binding, "experiment_id": experiment,
                    "decision_event_sequence": decision_event_sequence, "decision_event_digest": canonical_digest(event),
                    "evaluation_subject_digest": subject.subject_digest, "evaluation_record": reference.document(),
                    "authorization_digest": authorization.authorization_digest,
                    "authorization_nonces": list(authorization.nonce_ids),
                    "authority_policy_digest": authorization.policy_digest, "promoter_id": actor,
                    "admitted_at": utc_now(),
                }
                admission = canonical_digest(manifest)
                self._persist_manifest(admission, manifest)
                self.ledger.append_event(experiment, "prompt.promotion_prepared", actor,
                                         {"admission_digest": admission, "manifest": manifest})
                updated = {**pointers, "schema_version": 2,
                           "promotion_bindings": dict(pointers.get("promotion_bindings", {})),
                           "consumed_evaluations": {**pointers.get("consumed_evaluations", {}), reference.record_digest: admission},
                           "consumed_nonces": {**pointers.get("consumed_nonces", {}),
                                               **{nonce: admission for nonce in authorization.nonce_ids}}}
                if action == "rollback":
                    updated["champions"] = {**pointers["champions"], role_value: to_digest}
                    if target_binding is None:
                        updated["promotion_bindings"].pop(role_value, None)
                    else:
                        updated["promotion_bindings"][role_value] = target_binding
                if event["payload"]["verdict"] == "quarantine":
                    updated["quarantined_artifacts"] = {**pointers.get("quarantined_artifacts", {}),
                                                        subject.artifact_digest: admission}
                self._adverse_event(role_value, experiment, decision_event_sequence, actor, action)
                if action == "rollback" and to_digest is not None:
                    self._rollback_binding(role_value, to_digest, pointers)
                self._commit_pointer(pointers, updated, admission, prior, manifest["pointer_after"])
                committed = True
                try:
                    self._observe_adverse(admission, manifest)
                except Exception as error:
                    raise PromotionCommittedEvidencePending(admission, prior, manifest["pointer_after"], "adverse-observation") from error
                return prior
            except Exception as error:
                if not committed and not isinstance(error, PromotionCommittedEvidencePending) and getattr(error, "code", "") != "commit-state-unknown":
                    self._retain_rejection(error, role_value, candidate_digest, actor, experiment,
                                           expected_current, prior, decision_event_sequence)
                raise

    def _committed_adverse(self, digest: str, manifest: dict[str, Any], pointers: Mapping[str, Any]) -> dict[str, Any]:
        from .brain_kernel.canonical import canonical_digest

        event, subject, reference, authorization = self._adverse_event(
            manifest["role"], manifest["experiment_id"], manifest["decision_event_sequence"],
            manifest["promoter_id"], manifest["action"], admitted_at=manifest["admitted_at"])
        if (manifest["decision_event_digest"] != canonical_digest(event)
                or manifest["evaluation_subject_digest"] != subject.subject_digest
                or manifest["candidate_digest"] != subject.artifact_digest
                or manifest["evaluation_record"] != reference.document()
                or pointers.get("consumed_evaluations", {}).get(reference.record_digest) != digest
                or manifest["authorization_digest"] != authorization.authorization_digest
                or manifest["authority_policy_digest"] != authorization.policy_digest
                or manifest["authorization_nonces"] != list(authorization.nonce_ids)
                or any(pointers.get("consumed_nonces", {}).get(nonce) != digest for nonce in authorization.nonce_ids)):
            raise PromotionAdmissionError("admission-mismatch", "adverse admission bindings do not resolve")
        if manifest["action"] == "rollback":
            if manifest["prior_digest"] != subject.artifact_digest or manifest["pointer_after"] != subject.parent_champion_digest:
                raise PromotionAdmissionError("admission-mismatch", "rollback transition differs from its signed decision")
            target = manifest["target_binding"]
            if target is not None:
                retained = self._committed_manifest(target, pointers)
                if (retained.get("kind") not in {"prompt-promotion-admission", "prompt-bootstrap-admission"}
                        or retained["role"] != manifest["role"] or retained["candidate_digest"] != manifest["pointer_after"]):
                    raise PromotionAdmissionError("admission-mismatch", "rollback target binding was substituted")
            elif not self._bootstrap_promotion_resolves(manifest["role"], manifest["pointer_after"]):
                raise PromotionAdmissionError("admission-mismatch", "rollback legacy bootstrap does not resolve")
        elif (manifest["prior_digest"] != subject.parent_champion_digest
              or manifest["pointer_after"] != manifest["prior_digest"] or manifest["target_binding"] is not None):
            raise PromotionAdmissionError("admission-mismatch", "adverse retain transition differs from its signed decision")
        if not any(item["event_type"] == "prompt.promotion_prepared"
                   and item["payload"] == {"admission_digest": digest, "manifest": manifest}
                   for item in self.ledger.events(manifest["experiment_id"])):
            raise PromotionAdmissionError("admission-unprepared", "adverse admission has no preparation")
        return manifest

    def _observe_adverse(self, digest: str, manifest: Mapping[str, Any]) -> None:
        event = next(item for item in self.ledger.events(manifest["experiment_id"])
                     if item["sequence"] == manifest["decision_event_sequence"])
        payload = event["payload"]
        record = {"schema_version": 2, "kind": "rollback" if manifest["action"] == "rollback" else "adverse-decision",
                  "admission_digest": digest, "role": manifest["role"],
                  "artifact_digest": manifest["pointer_after"], "parent_digest": manifest["prior_digest"],
                  "candidate_digest": manifest["candidate_digest"], "created_by": manifest["promoter_id"],
                  "created_at": manifest["admitted_at"], "experiment_id": manifest["experiment_id"],
                  "verdict": payload["verdict"], "reasons": payload["reasons"]}
        if not any(item.get("admission_digest") == digest for item in self._read_records(self.lineage_root)):
            self._write_immutable_record(self.lineage_root, record)
        event_type = "prompt.rollback" if manifest["action"] == "rollback" else "prompt.adverse_decision"
        if not any(item["event_type"] == event_type and item["payload"].get("admission_digest") == digest
                   for item in self.ledger.events(manifest["experiment_id"])):
            self.ledger.append_event(manifest["experiment_id"], event_type, manifest["promoter_id"], record)

    def quarantine(
        self,
        role: Role | str,
        digest: str,
        *,
        actor: str,
        experiment_id: str,
        reasons: tuple[str, ...],
    ) -> None:
        """Retain a restriction-only safety signal, never an authenticated decision.

        Evaluators may fail closed on unsafe bytes without activation authority.
        Court-approved QUARANTINE actions use apply_adverse_decision instead.
        """
        if not actor.strip() or not experiment_id.strip():
            raise ValueError("quarantine actor and experiment id are required")
        if (
            not reasons
            or len(reasons) != len(set(reasons))
            or any(not reason.strip() for reason in reasons)
        ):
            raise ValueError(
                "quarantine reasons must be nonempty, unique, and nonblank"
            )
        self.read(digest)
        record = {
            "schema_version": 1,
            "kind": "quarantine",
            "authority": "restriction-only-safety-signal",
            "role": self._role_value(role),
            "artifact_digest": digest,
            "created_by": actor,
            "created_at": utc_now(),
            "experiment_id": experiment_id,
            "reasons": list(reasons),
        }
        with self._pointer_transaction():
            self._write_immutable_record(self.event_root, record)
            self.ledger.append_event(
                experiment_id,
                "prompt.quarantined",
                actor,
                record,
            )

    def is_quarantined(self, digest: str) -> bool:
        self._ensure_known_commit()
        pointers = self._read_pointers()
        binding = pointers.get("quarantined_artifacts", {}).get(digest)
        if binding is not None:
            manifest = self._committed_manifest(binding, pointers)
            if manifest.get("kind") != "prompt-adverse-admission" or manifest["candidate_digest"] != digest:
                raise PromotionAdmissionError("admission-mismatch", "quarantine binding does not resolve")
            event = next(item for item in self.ledger.events(manifest["experiment_id"])
                         if item["sequence"] == manifest["decision_event_sequence"])
            if event["payload"]["verdict"] != "quarantine":
                raise PromotionAdmissionError("admission-mismatch", "quarantine binding has a different verdict")
            return True
        return any(
            record.get("kind") == "quarantine"
            and record.get("artifact_digest") == digest
            for record in self.events()
        )

    def lineage(self, digest: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            record
            for record in self._read_records(self.lineage_root)
            if record.get("artifact_digest") == digest
        )

    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._read_records(self.event_root))

    def _read_pointers(self) -> dict[str, Any]:
        if not self.pointer_path.exists():
            return {"schema_version": 1, "champions": {}}
        document = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        if (
            not isinstance(document, dict)
            or type(document.get("schema_version")) is not int
            or document.get("schema_version") not in (1, 2)
            or not isinstance(document.get("champions"), dict)
        ):
            raise RuntimeError("prompt champion index is malformed")
        if document["schema_version"] == 2:
            if set(document) - {"schema_version", "champions", "promotion_bindings", "consumed_evaluations",
                                "consumed_nonces", "quarantined_artifacts", "bootstrap_bindings"}:
                raise RuntimeError("prompt champion admission index has unsupported fields")
            for key in ("promotion_bindings", "consumed_evaluations", "consumed_nonces"):
                if not isinstance(document.get(key), dict) or any(
                    not isinstance(k, str) or not isinstance(v, str) for k, v in document[key].items()
                ):
                    raise RuntimeError("prompt champion admission index is malformed")
            for key in ("quarantined_artifacts", "bootstrap_bindings"):
                values = document.get(key, {})
                if type(values) is not dict or any(type(k) is not str or type(v) is not str for k, v in values.items()):
                    raise RuntimeError("prompt optional admission index is malformed")
        elif set(document) != {"schema_version", "champions"}:
            raise PromotionAdmissionError("downgrade-unsupported", "legacy schema cannot carry or discard admission state")
        try:
            for role, digest in document["champions"].items():
                self._role_value(role)
                self._digest_hex(digest)
            for key in ("promotion_bindings", "bootstrap_bindings"):
                for role, digest in document.get(key, {}).items():
                    self._role_value(role)
                    self._digest_hex(digest)
            for key in ("consumed_evaluations", "consumed_nonces", "quarantined_artifacts"):
                for identity, digest in document.get(key, {}).items():
                    self._digest_hex(identity)
                    self._digest_hex(digest)
            if set(document.get("promotion_bindings", {})) - set(document["champions"]):
                raise ValueError("binding without a champion")
        except (ValueError, TypeError, AttributeError) as error:
            raise RuntimeError("prompt champion index contains invalid identities") from error
        return document

    def migration_status(self) -> dict[str, Any]:
        """Inspect legacy serving dispositions without rewriting any historical bytes."""
        with self._pointer_transaction():
            self._ensure_known_commit()
            pointers = self._read_pointers()
            dispositions = {}
            for role, digest in pointers["champions"].items():
                try:
                    self.read(digest)
                    resolved = self._champion_promotion_resolves(role, digest)
                    dispositions[role] = "admitted" if resolved else "migration-required"
                except (OSError, ValueError, RuntimeError, KeyError) as error:
                    dispositions[role] = "blocked:" + getattr(error, "code", "evidence-unresolved")
            return {"schema_version": pointers["schema_version"], "roles": dispositions,
                    "downgrade": "unsupported-preserve-admission-and-replay-state" if pointers["schema_version"] == 2 else "legacy-readable",
                    "automatic_migration": False}

    @staticmethod
    def _read_records(root: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.json"), key=lambda item: item.name):
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise RuntimeError("prompt registry record is malformed")
            records.append(document)
        return records

    @staticmethod
    def _write_immutable_record(root: Path, record: Mapping[str, Any]) -> Path:
        payload = (
            json.dumps(
                dict(record),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        path = root / f"{uuid4()}.json"
        # Publish only complete observations. An interrupted .tmp is never an
        # audit record; the committed manifest permits idempotent reconstruction.
        temporary = root / f".{uuid4()}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)  # Exclusive, atomic publication without overwrite.
        finally:
            temporary.unlink(missing_ok=True)
        return path

    @staticmethod
    def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
        payload = (
            json.dumps(
                dict(document),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
