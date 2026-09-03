"""Exact-snapshot, metadata-only indexing for repositories and other subjects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence
from urllib.parse import urlsplit

from .resource_adapter import ResourceSnapshot
from .subject_adapter import SubjectSnapshot, contract_digest

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SENSITIVE_BASENAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}
_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}


class RepositoryIndexError(ValueError):
    """An index request is stale, unsafe, substituted, or ambiguous."""


def _digest(value: str, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise RepositoryIndexError(f"{label} must be a lowercase sha256 digest")


@dataclass(frozen=True, slots=True)
class AnalyzerIdentity:
    analyzer_id: str
    version: str
    implementation_digest: str
    configuration_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.analyzer_id, str) or not self.analyzer_id.strip():
            raise RepositoryIndexError("analyzer_id is required")
        if not isinstance(self.version, str) or not self.version.strip():
            raise RepositoryIndexError("analyzer version is required")
        _digest(self.implementation_digest, "analyzer implementation_digest")
        _digest(self.configuration_digest, "analyzer configuration_digest")

    @property
    def analyzer_digest(self) -> str:
        return contract_digest(
            {
                "analyzer_id": self.analyzer_id,
                "version": self.version,
                "implementation_digest": self.implementation_digest,
                "configuration_digest": self.configuration_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class IndexEntry:
    subject_id: str
    subject_snapshot_digest: str
    resource_id: str
    resource_snapshot_digest: str
    locator: str
    content_digest: str
    byte_length: int
    analyzer_digest: str
    environment_digest: str
    language: str
    analysis_digest: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for label in (
            "subject_snapshot_digest",
            "resource_snapshot_digest",
            "content_digest",
            "analyzer_digest",
            "environment_digest",
            "analysis_digest",
        ):
            _digest(getattr(self, label), label)
        if (
            not self.subject_id.strip()
            or not self.resource_id.strip()
            or not self.locator.strip()
        ):
            raise RepositoryIndexError("entry identities and locator are required")
        if self.byte_length < 0:
            raise RepositoryIndexError("entry byte_length must be non-negative")
        if not self.language.strip():
            raise RepositoryIndexError("entry language must be explicit")
        if not self.evidence_refs:
            raise RepositoryIndexError("entry evidence_refs are required")

    @property
    def entry_digest(self) -> str:
        return contract_digest(
            {
                "subject_id": self.subject_id,
                "subject_snapshot_digest": self.subject_snapshot_digest,
                "resource_id": self.resource_id,
                "resource_snapshot_digest": self.resource_snapshot_digest,
                "locator": self.locator,
                "content_digest": self.content_digest,
                "byte_length": self.byte_length,
                "analyzer_digest": self.analyzer_digest,
                "environment_digest": self.environment_digest,
                "language": self.language,
                "analysis_digest": self.analysis_digest,
                "evidence_refs": self.evidence_refs,
            }
        )


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    subject_id: str
    subject_identity_digest: str
    subject_snapshot_digest: str
    analyzer_digest: str
    environment_digest: str
    entries: tuple[IndexEntry, ...]
    reused_resource_ids: tuple[str, ...]
    changed_resource_ids: tuple[str, ...]
    deleted_resource_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for label in (
            "subject_identity_digest",
            "subject_snapshot_digest",
            "analyzer_digest",
            "environment_digest",
        ):
            _digest(getattr(self, label), label)
        identifiers = tuple(entry.resource_id for entry in self.entries)
        if identifiers != tuple(sorted(set(identifiers))):
            raise RepositoryIndexError("index entries must be sorted and unique")
        for label in (
            "reused_resource_ids",
            "changed_resource_ids",
            "deleted_resource_ids",
        ):
            values = getattr(self, label)
            if values != tuple(sorted(set(values))):
                raise RepositoryIndexError(f"{label} must be sorted and unique")
        if set(self.reused_resource_ids) & set(self.changed_resource_ids):
            raise RepositoryIndexError("a resource cannot be both reused and changed")
        if not self.evidence_refs:
            raise RepositoryIndexError("index evidence_refs are required")

    @property
    def index_digest(self) -> str:
        return contract_digest(
            {
                "subject_id": self.subject_id,
                "subject_identity_digest": self.subject_identity_digest,
                "subject_snapshot_digest": self.subject_snapshot_digest,
                "analyzer_digest": self.analyzer_digest,
                "environment_digest": self.environment_digest,
                "entries": tuple(entry.entry_digest for entry in self.entries),
                "reused_resource_ids": self.reused_resource_ids,
                "changed_resource_ids": self.changed_resource_ids,
                "deleted_resource_ids": self.deleted_resource_ids,
                "evidence_refs": self.evidence_refs,
            }
        )

    @property
    def by_resource_id(self) -> Mapping[str, IndexEntry]:
        return MappingProxyType({entry.resource_id: entry for entry in self.entries})


@dataclass(frozen=True, slots=True)
class _Analysis:
    language: str
    digest: str


class RepositoryIndexer:
    """Produce immutable indexes and reuse only exact analyzer/blob observations."""

    def __init__(self) -> None:
        self._analysis_cache: dict[tuple[str, str, str, str], _Analysis] = {}

    @property
    def cached_analysis_count(self) -> int:
        return len(self._analysis_cache)

    def build(
        self,
        subject_snapshot: SubjectSnapshot,
        resources: Sequence[ResourceSnapshot],
        analyzer: AnalyzerIdentity,
        environment_digest: str,
        *,
        evidence_refs: tuple[str, ...],
        previous: RepositoryIndex | None = None,
    ) -> RepositoryIndex:
        _digest(environment_digest, "environment_digest")
        if not evidence_refs or any(
            not isinstance(item, str) or not item.strip() for item in evidence_refs
        ):
            raise RepositoryIndexError("index evidence_refs are required")
        if len(set(evidence_refs)) != len(evidence_refs):
            raise RepositoryIndexError("index evidence_refs must be unique")
        supplied = tuple(resources)
        resource_ids = tuple(item.resource.resource_id for item in supplied)
        if len(set(resource_ids)) != len(resource_ids):
            raise RepositoryIndexError("resource ids must be unique within a snapshot")
        if any(
            item.resource.subject_id != subject_snapshot.subject.subject_id
            for item in supplied
        ):
            raise RepositoryIndexError("resource belongs to a different subject")
        if previous is not None and (
            previous.subject_id != subject_snapshot.subject.subject_id
            or previous.subject_identity_digest
            != subject_snapshot.subject.identity_digest
        ):
            raise RepositoryIndexError(
                "previous index belongs to a different subject identity"
            )
        prior = previous.by_resource_id if previous is not None else {}
        entries: list[IndexEntry] = []
        reused: list[str] = []
        changed: list[str] = []
        for resource in sorted(supplied, key=lambda item: item.resource.resource_id):
            self._reject_sensitive_locator(resource.resource.locator)
            language = self._language(resource.resource.locator)
            key = (
                resource.content_digest,
                language,
                analyzer.analyzer_digest,
                environment_digest,
            )
            analysis = self._analysis_cache.get(key)
            if analysis is None:
                analysis = _Analysis(
                    language,
                    contract_digest(
                        {
                            "content_digest": resource.content_digest,
                            "byte_length": resource.byte_length,
                            "binary": resource.binary,
                            "language": language,
                            "analyzer_digest": analyzer.analyzer_digest,
                            "environment_digest": environment_digest,
                        }
                    ),
                )
                self._analysis_cache[key] = analysis
            old = prior.get(resource.resource.resource_id)
            if old is not None and (
                old.resource_snapshot_digest == resource.snapshot_digest
                and old.analyzer_digest == analyzer.analyzer_digest
                and old.environment_digest == environment_digest
                and old.analysis_digest == analysis.digest
            ):
                reused.append(resource.resource.resource_id)
            else:
                changed.append(resource.resource.resource_id)
            entries.append(
                IndexEntry(
                    subject_id=subject_snapshot.subject.subject_id,
                    subject_snapshot_digest=subject_snapshot.snapshot_digest,
                    resource_id=resource.resource.resource_id,
                    resource_snapshot_digest=resource.snapshot_digest,
                    locator=resource.resource.locator,
                    content_digest=resource.content_digest,
                    byte_length=resource.byte_length,
                    analyzer_digest=analyzer.analyzer_digest,
                    environment_digest=environment_digest,
                    language=analysis.language,
                    analysis_digest=analysis.digest,
                    evidence_refs=tuple(
                        dict.fromkeys((*resource.evidence_refs, *evidence_refs))
                    ),
                )
            )
        deleted = sorted(set(prior) - set(resource_ids))
        return RepositoryIndex(
            subject_id=subject_snapshot.subject.subject_id,
            subject_identity_digest=subject_snapshot.subject.identity_digest,
            subject_snapshot_digest=subject_snapshot.snapshot_digest,
            analyzer_digest=analyzer.analyzer_digest,
            environment_digest=environment_digest,
            entries=tuple(entries),
            reused_resource_ids=tuple(sorted(reused)),
            changed_resource_ids=tuple(sorted(changed)),
            deleted_resource_ids=tuple(deleted),
            evidence_refs=evidence_refs,
        )

    index = build

    @staticmethod
    def _language(locator: str) -> str:
        normalized = locator.split("?", 1)[0].casefold()
        filename = normalized.rsplit("/", 1)[-1]
        suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
        return _LANGUAGES.get(suffix, "unknown")

    @staticmethod
    def _reject_sensitive_locator(locator: str) -> None:
        parsed = urlsplit(locator.replace("\\", "/"))
        name = parsed.path.rstrip("/").rsplit("/", 1)[-1].casefold()
        if name in _SENSITIVE_BASENAMES or name.endswith(
            (".pem", ".key", ".p12", ".pfx")
        ):
            raise RepositoryIndexError(
                "secret-like resource locators cannot be indexed"
            )


ExactSnapshotIndex = RepositoryIndex
