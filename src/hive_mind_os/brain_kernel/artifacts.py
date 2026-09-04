"""Immutable, content-addressed evidence artifacts for the brain kernel.

An artifact address covers both the payload digest and the provenance needed to
interpret that payload.  Consequently, identical bytes produced for a different
candidate, dependency set, or schema are deliberately different artifacts.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .canonical import canonical_bytes, canonical_digest

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ENVELOPE_FIELDS = frozenset(
    {
        "envelope_version",
        "artifact_digest",
        "content_digest",
        "media_type",
        "candidate_digest",
        "dependency_digests",
        "schema_id",
        "schema_version",
        "schema_digest",
        "producer_id",
    }
)


class ArtifactIntegrityError(ValueError):
    """An artifact is malformed, mutated, or stored under the wrong address."""


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase sha256:<64 hex>")
    return value


def _content_digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ArtifactEnvelope:
    """Canonical provenance and identity for one immutable byte payload."""

    envelope_version: int
    artifact_digest: str
    content_digest: str
    media_type: str
    candidate_digest: str
    dependency_digests: tuple[str, ...]
    schema_id: str
    schema_version: str
    schema_digest: str
    producer_id: str

    def __post_init__(self) -> None:
        if type(self.envelope_version) is not int or self.envelope_version != 1:
            raise ValueError("unsupported artifact envelope version")
        _require_digest(self.artifact_digest, "artifact_digest")
        _require_digest(self.content_digest, "content_digest")
        _require_digest(self.candidate_digest, "candidate_digest")
        _require_digest(self.schema_digest, "schema_digest")
        _require_text(self.media_type, "media_type")
        _require_text(self.schema_id, "schema_id")
        _require_text(self.schema_version, "schema_version")
        _require_text(self.producer_id, "producer_id")
        if any(
            not isinstance(item, str) or _DIGEST.fullmatch(item) is None
            for item in self.dependency_digests
        ):
            raise ValueError("dependency_digests must contain lowercase sha256 digests")
        if tuple(sorted(set(self.dependency_digests))) != self.dependency_digests:
            raise ValueError("dependency_digests must be sorted and unique")
        if self.artifact_digest != canonical_digest(self.identity_document()):
            raise ArtifactIntegrityError("artifact envelope digest mismatch")

    @classmethod
    def create(
        cls,
        content: bytes,
        *,
        media_type: str,
        candidate_digest: str,
        dependency_digests: tuple[str, ...] = (),
        schema_id: str,
        schema_version: str,
        schema_digest: str,
        producer_id: str,
    ) -> ArtifactEnvelope:
        """Create a deterministic envelope after validating all provenance."""

        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        if not isinstance(dependency_digests, tuple):
            raise TypeError("dependency_digests must be a tuple")
        if any(not isinstance(item, str) for item in dependency_digests):
            raise ValueError("dependency_digests must contain sha256 digests")
        dependencies = tuple(sorted(set(dependency_digests)))
        identity: dict[str, object] = {
            "envelope_version": 1,
            "content_digest": _content_digest(content),
            "media_type": _require_text(media_type, "media_type"),
            "candidate_digest": _require_digest(
                candidate_digest, "candidate_digest"
            ),
            "dependency_digests": dependencies,
            "schema_id": _require_text(schema_id, "schema_id"),
            "schema_version": _require_text(schema_version, "schema_version"),
            "schema_digest": _require_digest(schema_digest, "schema_digest"),
            "producer_id": _require_text(producer_id, "producer_id"),
        }
        return cls(
            artifact_digest=canonical_digest(identity),
            **identity,  # type: ignore[arg-type]
        )

    def identity_document(self) -> dict[str, object]:
        """Return the canonical fields covered by ``artifact_digest``."""

        return {
            "envelope_version": self.envelope_version,
            "content_digest": self.content_digest,
            "media_type": self.media_type,
            "candidate_digest": self.candidate_digest,
            "dependency_digests": list(self.dependency_digests),
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "schema_digest": self.schema_digest,
            "producer_id": self.producer_id,
        }

    def to_document(self) -> dict[str, object]:
        return {
            "envelope_version": self.envelope_version,
            "artifact_digest": self.artifact_digest,
            "content_digest": self.content_digest,
            "media_type": self.media_type,
            "candidate_digest": self.candidate_digest,
            "dependency_digests": list(self.dependency_digests),
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "schema_digest": self.schema_digest,
            "producer_id": self.producer_id,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> ArtifactEnvelope:
        if not isinstance(document, Mapping) or set(document) != _ENVELOPE_FIELDS:
            raise ArtifactIntegrityError("artifact envelope fields are malformed")
        dependencies = document["dependency_digests"]
        if not isinstance(dependencies, list):
            raise ArtifactIntegrityError("artifact dependency list is malformed")
        try:
            envelope_version = document["envelope_version"]
            if type(envelope_version) is not int:
                raise ValueError("envelope_version must be an integer")
            return cls(
                envelope_version=envelope_version,
                artifact_digest=_require_digest(
                    document["artifact_digest"], "artifact_digest"
                ),
                content_digest=_require_digest(
                    document["content_digest"], "content_digest"
                ),
                media_type=_require_text(document["media_type"], "media_type"),
                candidate_digest=_require_digest(
                    document["candidate_digest"], "candidate_digest"
                ),
                dependency_digests=tuple(
                    _require_digest(item, "dependency_digest")
                    for item in dependencies
                ),
                schema_id=_require_text(document["schema_id"], "schema_id"),
                schema_version=_require_text(
                    document["schema_version"], "schema_version"
                ),
                schema_digest=_require_digest(
                    document["schema_digest"], "schema_digest"
                ),
                producer_id=_require_text(
                    document["producer_id"], "producer_id"
                ),
            )
        except (TypeError, ValueError) as error:
            raise ArtifactIntegrityError("artifact envelope is invalid") from error


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """A verified envelope and its verified immutable bytes."""

    envelope: ArtifactEnvelope
    content: bytes


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactIntegrityError("artifact document contains duplicate keys")
        result[key] = value
    return result


class ArtifactStore:
    """Filesystem store that never overwrites a content-addressed artifact."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = RLock()

    def put(
        self,
        content: bytes | str,
        *,
        media_type: str,
        candidate_digest: str,
        dependency_digests: tuple[str, ...] = (),
        schema_id: str,
        schema_version: str,
        schema_digest: str,
        producer_id: str,
    ) -> ArtifactEnvelope:
        """Persist one artifact or verify the exact existing immutable bundle."""

        encoded = content.encode("utf-8") if isinstance(content, str) else content
        if not isinstance(encoded, bytes):
            raise TypeError("artifact content must be bytes or text")
        envelope = ArtifactEnvelope.create(
            encoded,
            media_type=media_type,
            candidate_digest=candidate_digest,
            dependency_digests=dependency_digests,
            schema_id=schema_id,
            schema_version=schema_version,
            schema_digest=schema_digest,
            producer_id=producer_id,
        )
        document = {
            "envelope": envelope.to_document(),
            "content_base64": base64.b64encode(encoded).decode("ascii"),
        }
        serialized = canonical_bytes(document)
        target = self._path(envelope.artifact_digest)
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, pending_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=".artifact-pending-",
                suffix=".json",
            )
            pending = Path(pending_name)
            try:
                with os.fdopen(descriptor, "wb") as artifact:
                    artifact.write(serialized)
                    artifact.flush()
                    os.fsync(artifact.fileno())
                try:
                    os.link(pending, target)
                except FileExistsError:
                    existing = self.read(envelope.artifact_digest)
                    if existing.envelope != envelope or existing.content != encoded:
                        raise ArtifactIntegrityError(
                            "content-addressed artifact cannot be rewritten"
                        )
            finally:
                pending.unlink(missing_ok=True)
        return envelope

    def read(self, artifact_digest: str) -> StoredArtifact:
        """Read and fully re-verify a stored bundle against its requested address."""

        target = self._path(artifact_digest)
        try:
            serialized = target.read_bytes()
        except OSError as error:
            raise KeyError(f"unknown artifact: {artifact_digest}") from error
        try:
            document = json.loads(
                serialized.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
            )
            if not isinstance(document, dict) or set(document) != {
                "envelope",
                "content_base64",
            }:
                raise ArtifactIntegrityError("artifact bundle fields are malformed")
            envelope_document = document["envelope"]
            if not isinstance(envelope_document, dict):
                raise ArtifactIntegrityError("artifact envelope is malformed")
            envelope = ArtifactEnvelope.from_document(envelope_document)
            content_base64 = document["content_base64"]
            if not isinstance(content_base64, str):
                raise ArtifactIntegrityError("artifact content is malformed")
            content = base64.b64decode(content_base64, validate=True)
        except (
            ArtifactIntegrityError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            binascii.Error,
        ) as error:
            if isinstance(error, ArtifactIntegrityError):
                raise
            raise ArtifactIntegrityError("artifact bundle is malformed") from error
        if envelope.artifact_digest != artifact_digest:
            raise ArtifactIntegrityError("artifact stored under the wrong address")
        if _content_digest(content) != envelope.content_digest:
            raise ArtifactIntegrityError("artifact content digest mismatch")
        return StoredArtifact(envelope, content)

    def get(self, artifact_digest: str) -> bytes:
        return self.read(artifact_digest).content

    def _path(self, artifact_digest: str) -> Path:
        digest = _require_digest(artifact_digest, "artifact_digest")
        value = digest.removeprefix("sha256:")
        return self.root / "artifacts" / "sha256" / value[:2] / f"{value}.json"
