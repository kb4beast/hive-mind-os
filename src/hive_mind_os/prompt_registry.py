"""Immutable, content-addressed role prompts with atomic champion pointers."""

from __future__ import annotations

import json
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from .ledger import EvidenceLedger
from .models import Role, utc_now
from .roles import RoleContract


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
        self._lock = RLock()

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
        digest = self.champion_digest(role)
        if digest is None:
            raise KeyError(self._role_value(role))
        return self.read(digest), digest

    def promote(
        self,
        role: Role | str,
        digest: str,
        *,
        promoted_by: str,
        experiment_id: str,
        expected_current: str | None,
    ) -> str | None:
        role_value = self._role_value(role)
        if not promoted_by.strip() or not experiment_id.strip():
            raise ValueError("promotion identity and experiment id are required")
        self.read(digest)
        with self._lock:
            pointers = self._read_pointers()
            prior = pointers["champions"].get(role_value)
            if prior != expected_current:
                raise RuntimeError("champion changed since the experiment was bound")
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
        self.read(to_digest)
        with self._lock:
            pointers = self._read_pointers()
            prior = pointers["champions"].get(role_value)
            if not isinstance(prior, str):
                raise RuntimeError("cannot roll back a role without a champion")
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
        with self._lock:
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
