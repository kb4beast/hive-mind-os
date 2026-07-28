"""Immutable, content-addressed role prompts with atomic champion pointers."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
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
    """Return the canonical UTF-8 bytes used for prompt identity."""

    if isinstance(content, bytes):
        text = content.decode("utf-8")
    else:
        text = content
    return text.replace("\r\n", "\n").replace("\r", "\n").removesuffix("\n").encode(
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


class PromptRegistry:
    """Content-addressed prompt artifacts and per-role champion pointers."""

    def __init__(
        self,
        root: str | Path,
        *,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.artifact_root = self.root / "artifacts"
        self.lineage_root = self.root / "lineage"
        self.event_root = self.root / "events"
        self.pointer_path = self.root / "champions.json"
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
                    raise RuntimeError("content-addressed prompt artifact was mutated")
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
        if prompt_digest(content) != digest:
            raise RuntimeError("prompt artifact digest does not match its path")
        return content.decode("utf-8")

    def champion_digest(self, role: Role | str) -> str | None:
        role_value = self._role_value(role)
        document = self._read_pointers()
        value = document["champions"].get(role_value)
        if value is None:
            return None
        if not isinstance(value, str) or not self.artifact_path(value).is_file():
            raise RuntimeError("champion pointer does not resolve to an artifact")
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
        self,
        role: Role | str,
        digest: str,
        *,
        promoted_by: str,
        experiment_id: str,
        expected_current: str | None,
        decision_event_sequence: int | None = None,
    ) -> str | None:
        role_value = self._role_value(role)
        if not promoted_by.strip() or not experiment_id.strip():
            raise ValueError("promotion identity and experiment id are required")
        with self._pointer_transaction():
            self.read(digest)
            if self.is_quarantined(digest):
                raise RuntimeError("cannot promote a quarantined prompt artifact")
            pointers = self._read_pointers()
            prior = pointers["champions"].get(role_value)
            if prior != expected_current:
                raise RuntimeError("champion changed since the experiment was bound")
            registration = self._promotion_registration(
                role_value,
                digest,
                experiment_id=experiment_id,
                expected_current=expected_current,
                promoted_by=promoted_by,
            )
            generation_zero = (
                experiment_id == "generation-0"
                and expected_current is None
                and registration.get("parent_digest") is None
                and registration.get("created_by") == promoted_by
                and promoted_by in _GENERATION_ZERO_PROMOTERS
                and self.read(digest)
                == generation_zero_prompt(ROLE_CONTRACTS[Role(role_value)])
            )
            if not generation_zero:
                self._validate_decision_event(
                    role_value=role_value,
                    digest=digest,
                    promoted_by=promoted_by,
                    experiment_id=experiment_id,
                    expected_current=expected_current,
                    registration=registration,
                    decision_event_sequence=decision_event_sequence,
                )
            updated = {
                "schema_version": 1,
                "champions": {**pointers["champions"], role_value: digest},
            }
            self._atomic_json(self.pointer_path, updated)
            record = {
                "schema_version": 1,
                "kind": "promotion",
                "role": role_value,
                "artifact_digest": digest,
                "parent_digest": prior,
                "created_by": promoted_by,
                "created_at": utc_now(),
                "experiment_id": experiment_id,
                "decision_event_sequence": decision_event_sequence,
                "rollback_digest": prior,
            }
            self._write_immutable_record(self.lineage_root, record)
            self.ledger.append_event(
                experiment_id,
                "prompt.promoted",
                promoted_by,
                record,
            )
            return prior

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
    ) -> None:
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
        if event.get("actor") != judge_id or promoted_by != judge_id:
            raise RuntimeError(
                "promotion actor and promoted_by must be the decision judge"
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

    def rollback_champion(
        self,
        role: Role | str,
        to_digest: str,
        *,
        actor: str,
        reason: str,
    ) -> str:
        role_value = self._role_value(role)
        if not actor.strip() or not reason.strip():
            raise ValueError("rollback actor and reason are required")
        with self._pointer_transaction():
            self.read(to_digest)
            if self.is_quarantined(to_digest):
                raise RuntimeError("cannot roll back to a quarantined prompt artifact")
            pointers = self._read_pointers()
            prior = pointers["champions"].get(role_value)
            if not isinstance(prior, str):
                raise RuntimeError("cannot roll back a role without a champion")
            if prior == to_digest:
                raise RuntimeError("rollback target is already the active champion")
            was_promoted = any(
                record.get("kind") == "promotion"
                and record.get("role") == role_value
                for record in self.lineage(to_digest)
            )
            if not was_promoted:
                raise RuntimeError(
                    "rollback target was never a promoted champion for this role"
                )
            updated = {
                "schema_version": 1,
                "champions": {**pointers["champions"], role_value: to_digest},
            }
            self._atomic_json(self.pointer_path, updated)
            record = {
                "schema_version": 1,
                "kind": "rollback",
                "role": role_value,
                "artifact_digest": to_digest,
                "parent_digest": prior,
                "created_by": actor,
                "created_at": utc_now(),
                "experiment_id": None,
                "reason": reason,
            }
            self._write_immutable_record(self.lineage_root, record)
            self.ledger.append_event(
                f"prompt:{role_value}",
                "prompt.rollback",
                actor,
                record,
            )
        return prior

    def quarantine(
        self,
        role: Role | str,
        digest: str,
        *,
        actor: str,
        experiment_id: str,
        reasons: tuple[str, ...],
    ) -> None:
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
            or document.get("schema_version") != 1
            or not isinstance(document.get("champions"), dict)
        ):
            raise RuntimeError("prompt champion index is malformed")
        return document

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
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
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
