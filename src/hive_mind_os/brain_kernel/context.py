"""Deterministic hot/warm/cold context compilation for local kernel primitives."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Mapping

from .canonical import canonical_bytes, canonical_digest
from .contracts import ContextManifest
from .memory import MemoryCatalog, RankedMemory, RetrievalRequest

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def _binding_time(value: str, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"context binding {label} must be RFC 3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"context binding {label} must include an offset")


@dataclass(frozen=True, slots=True)
class HotContextItem:
    """A required reference whose token cost is declared before compilation."""

    reference: str
    token_count: int

    def __post_init__(self) -> None:
        if not self.reference or type(self.token_count) is not int or self.token_count < 0:
            raise ValueError("hot context item requires a reference and non-negative tokens")


@dataclass(frozen=True, slots=True)
class ContextRequest:
    mission_id: str
    work_id: str
    attempt_id: str
    role: str
    charter_digest: str
    authority_digest: str
    token_budget: int
    query: str
    now: str
    data_scopes: tuple[str, ...]
    hot_items: tuple[HotContextItem, ...]
    repository_key: str | None = None
    evaluator_mode: bool = False
    explicit_pins: tuple[str, ...] = ()
    sensitivity_scopes: tuple[str, ...] = ("public", "internal")
    required_sensitivities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.attempt_id or type(self.token_budget) is not int or self.token_budget < 0:
            raise ValueError("context request requires an attempt and non-negative token budget")
        if len({item.reference for item in self.hot_items}) != len(self.hot_items):
            raise ValueError("hot context references must be unique")
        if len(set(self.explicit_pins)) != len(self.explicit_pins):
            raise ValueError("explicit pins must be unique")


@dataclass(frozen=True, slots=True)
class CompiledContext:
    """A model-ready bounded selection; cold references require a later explicit pin."""

    request: ContextRequest
    manifest: ContextManifest
    warm: tuple[RankedMemory, ...]
    cold: tuple[RankedMemory, ...]
    bindings: tuple["ContextRecordBinding", ...] = ()

    @property
    def estimated_tokens(self) -> int:
        return self.manifest.estimated_tokens


@dataclass(frozen=True, slots=True)
class ContextRecordBinding:
    """Immutable metadata receipt for one record named by a context manifest.

    The manifest contract intentionally stores compact record references.  This
    sidecar binds those references to the source/provenance and access metadata
    used during compilation without exposing durable memory bodies to callers.
    """

    manifest_digest: str
    record_id: str
    record_digest: str
    source_refs: tuple[str, ...]
    sensitivity: str
    valid_from: str
    valid_to: str | None
    freshness_score: float
    authority_level: str
    authority_digest: str
    mission_id: str
    work_id: str
    role: str
    access_roles: tuple[str, ...]
    data_scopes: tuple[str, ...]
    evaluator_visible: bool
    binding_digest: str = ""

    def __post_init__(self) -> None:
        if _DIGEST.fullmatch(self.manifest_digest) is None:
            raise ValueError("context binding requires a manifest digest")
        if not self.record_id or _DIGEST.fullmatch(self.record_digest) is None:
            raise ValueError("context binding requires a record identity and digest")
        if not self.source_refs or any(not ref for ref in self.source_refs) or len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("context binding requires unique provenance references")
        if not self.access_roles or len(set(self.access_roles)) != len(self.access_roles):
            raise ValueError("context binding requires unique access roles")
        if len(set(self.data_scopes)) != len(self.data_scopes):
            raise ValueError("context binding scopes must be unique")
        if type(self.freshness_score) is not float or not 0.0 <= self.freshness_score <= 1.0:
            raise ValueError("context binding freshness must be a float in [0, 1]")
        if type(self.evaluator_visible) is not bool:
            raise ValueError("context binding evaluator visibility must be boolean")
        if _DIGEST.fullmatch(self.authority_digest) is None:
            raise ValueError("context binding requires an authority digest")
        if not self.sensitivity or not self.authority_level or not self.mission_id or not self.work_id or not self.role:
            raise ValueError("context binding identity fields are required")
        _binding_time(self.valid_from, "valid_from")
        if self.valid_to is not None:
            _binding_time(self.valid_to, "valid_to")
        expected_digest = context_binding_digest(
            manifest_digest=self.manifest_digest,
            record_id=self.record_id,
            record_digest=self.record_digest,
            source_refs=self.source_refs,
            sensitivity=self.sensitivity,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            freshness_score=self.freshness_score,
            authority_level=self.authority_level,
            authority_digest=self.authority_digest,
            mission_id=self.mission_id,
            work_id=self.work_id,
            role=self.role,
            access_roles=self.access_roles,
            data_scopes=self.data_scopes,
            evaluator_visible=self.evaluator_visible,
        )
        if not self.binding_digest:
            object.__setattr__(self, "binding_digest", expected_digest)
        elif self.binding_digest != expected_digest:
            raise ValueError("context binding digest is invalid")

    def to_document(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "record_id": self.record_id,
            "record_digest": self.record_digest,
            "source_refs": list(self.source_refs),
            "sensitivity": self.sensitivity,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "freshness_score": self.freshness_score,
            "authority_level": self.authority_level,
            "authority_digest": self.authority_digest,
            "mission_id": self.mission_id,
            "work_id": self.work_id,
            "role": self.role,
            "access_roles": list(self.access_roles),
            "data_scopes": list(self.data_scopes),
            "evaluator_visible": self.evaluator_visible,
            "binding_digest": self.binding_digest,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "ContextRecordBinding":
        expected = {
            "manifest_digest", "record_id", "record_digest", "source_refs",
            "sensitivity", "valid_from", "valid_to", "freshness_score",
            "authority_level", "authority_digest", "mission_id", "work_id", "role",
            "access_roles", "data_scopes", "evaluator_visible", "binding_digest",
        }
        if set(document) != expected:
            raise ValueError("context binding has unsupported fields")
        string_fields = (
            "manifest_digest", "record_id", "record_digest", "sensitivity", "valid_from",
            "authority_level", "authority_digest", "mission_id", "work_id", "role",
            "binding_digest",
        )
        if any(type(document[field]) is not str for field in string_fields):
            raise ValueError("context binding scalar fields are malformed")
        if document["valid_to"] is not None and type(document["valid_to"]) is not str:
            raise ValueError("context binding valid_to is malformed")
        if type(document["freshness_score"]) is not float or type(document["evaluator_visible"]) is not bool:
            raise ValueError("context binding scalar fields are malformed")
        if not isinstance(document["source_refs"], list) or not isinstance(document["access_roles"], list) or not isinstance(document["data_scopes"], list):
            raise ValueError("context binding lists are malformed")
        if any(type(item) is not str for item in (*document["source_refs"], *document["access_roles"], *document["data_scopes"])):
            raise ValueError("context binding lists are malformed")
        return cls(
            str(document["manifest_digest"]),
            str(document["record_id"]),
            str(document["record_digest"]),
            tuple(str(item) for item in document["source_refs"]),
            str(document["sensitivity"]),
            str(document["valid_from"]),
            None if document["valid_to"] is None else str(document["valid_to"]),
            float(document["freshness_score"]),
            str(document["authority_level"]),
            str(document["authority_digest"]),
            str(document["mission_id"]),
            str(document["work_id"]),
            str(document["role"]),
            tuple(str(item) for item in document["access_roles"]),
            tuple(str(item) for item in document["data_scopes"]),
            document["evaluator_visible"],
            str(document["binding_digest"]),
        )


def context_binding_digest(
    *,
    manifest_digest: str,
    record_id: str,
    record_digest: str,
    source_refs: tuple[str, ...],
    sensitivity: str,
    valid_from: str,
    valid_to: str | None,
    freshness_score: float,
    authority_level: str,
    authority_digest: str,
    mission_id: str,
    work_id: str,
    role: str,
    access_roles: tuple[str, ...],
    data_scopes: tuple[str, ...],
    evaluator_visible: bool,
) -> str:
    return canonical_digest(
        {
            "manifest_digest": manifest_digest,
            "record_id": record_id,
            "record_digest": record_digest,
            "source_refs": source_refs,
            "sensitivity": sensitivity,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "freshness_score": freshness_score,
            "authority_level": authority_level,
            "authority_digest": authority_digest,
            "mission_id": mission_id,
            "work_id": work_id,
            "role": role,
            "access_roles": access_roles,
            "data_scopes": data_scopes,
            "evaluator_visible": evaluator_visible,
        }
    )


class ContextManifestStore:
    """Append-only manifest registry keyed by digest, not a mutable attempt slot."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._manifests: dict[str, ContextManifest] = {}
        self._bindings: dict[str, tuple[ContextRecordBinding, ...]] = {}
        self.root = None if root is None else Path(root)
        self._lock = RLock()

    def store(
        self,
        manifest: ContextManifest,
        bindings: tuple[ContextRecordBinding, ...] = (),
    ) -> None:
        if manifest.manifest_digest != manifest_digest(
            mission_id=manifest.mission_id,
            work_id=manifest.work_id,
            attempt_id=manifest.attempt_id,
            role=manifest.role,
            charter_digest=manifest.charter_digest,
            authority_digest=manifest.authority_digest,
            token_budget=manifest.token_budget,
            estimated_tokens=manifest.estimated_tokens,
            hot_items=manifest.hot_items,
            warm_items=manifest.warm_items,
            cold_references=manifest.cold_references,
            excluded_categories=manifest.excluded_categories,
            excluded_counts=manifest.excluded_counts,
            conflict_records=manifest.conflict_records,
            generator_evaluator_separated=manifest.generator_evaluator_separated,
        ):
            raise ValueError("context manifest digest is invalid")
        with self._lock:
            existing = self._manifests.get(manifest.manifest_digest)
            if existing is not None and existing != manifest:
                raise ValueError("context manifest digest is already bound")
            expected_records = (*manifest.warm_items, *manifest.cold_references)
            if tuple(item.record_id for item in bindings) != expected_records:
                raise ValueError("context bindings must cover warm and cold records in manifest order")
            if any(item.manifest_digest != manifest.manifest_digest for item in bindings):
                raise ValueError("context binding references the wrong manifest")
            existing_bindings = self._bindings.get(manifest.manifest_digest)
            if existing_bindings is not None and existing_bindings != bindings:
                raise ValueError("context bindings cannot be rewritten")
            self._persist(manifest)
            if bindings:
                self._persist_bindings(manifest.manifest_digest, bindings)
            self._manifests[manifest.manifest_digest] = manifest
            self._bindings[manifest.manifest_digest] = bindings

    def get(self, digest: str) -> ContextManifest:
        try:
            return self._manifests[digest]
        except KeyError as error:
            raise KeyError(f"unknown context manifest: {digest}") from error

    def manifests(self) -> tuple[ContextManifest, ...]:
        return tuple(self._manifests[digest] for digest in sorted(self._manifests))

    def bindings(self, manifest_digest: str) -> tuple[ContextRecordBinding, ...]:
        try:
            return self._bindings[manifest_digest]
        except KeyError as error:
            raise KeyError(f"unknown context bindings: {manifest_digest}") from error

    def restore(self) -> tuple[ContextManifest, ...]:
        """Load every on-disk manifest only if its canonical contract verifies."""

        if self.root is None:
            return self.manifests()
        directory = self.root / "context"
        if not directory.exists():
            return ()
        for path in sorted(directory.rglob("*.json")):
            if "bindings" in path.relative_to(directory).parts:
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                restored = ContextManifest.from_document(document)
                if not isinstance(restored, ContextManifest):
                    raise ValueError("context manifest has the wrong contract type")
                manifest = ContextManifest(
                    restored.mission_id,
                    restored.work_id,
                    restored.attempt_id,
                    restored.role,
                    restored.charter_digest,
                    restored.authority_digest,
                    restored.token_budget,
                    restored.estimated_tokens,
                    tuple(restored.hot_items),
                    tuple(restored.warm_items),
                    tuple(restored.cold_references),
                    tuple(restored.excluded_categories),
                    dict(restored.excluded_counts),
                    tuple(restored.conflict_records),
                    restored.generator_evaluator_separated,
                    restored.manifest_digest,
                )
                bindings = self._restore_bindings(manifest)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"context manifest is corrupt: {path}") from error
            self.store(manifest, bindings)
        return self.manifests()

    def _persist(self, manifest: ContextManifest) -> None:
        if self.root is None:
            return
        path = self._path(manifest)
        encoded = canonical_bytes(manifest.to_document())
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as output:
                output.write(encoded)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise ValueError("context manifest cannot be rewritten")

    def _persist_bindings(
        self, manifest_digest: str, bindings: tuple[ContextRecordBinding, ...]
    ) -> None:
        if self.root is None:
            return
        path = self._binding_path(manifest_digest)
        document = {
            "manifest_digest": manifest_digest,
            "bindings": [item.to_document() for item in bindings],
        }
        encoded = canonical_bytes(document)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as output:
                output.write(encoded)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise ValueError("context bindings cannot be rewritten")

    def _restore_bindings(
        self, manifest: ContextManifest
    ) -> tuple[ContextRecordBinding, ...]:
        if self.root is None:
            return ()
        path = self._binding_path(manifest.manifest_digest)
        if not path.is_file():
            if manifest.warm_items or manifest.cold_references:
                raise ValueError("context manifest is missing its binding receipt")
            return ()
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {"manifest_digest", "bindings"}:
            raise ValueError("context binding receipt is malformed")
        if document["manifest_digest"] != manifest.manifest_digest or not isinstance(document["bindings"], list):
            raise ValueError("context binding receipt is malformed")
        if any(not isinstance(item, dict) for item in document["bindings"]):
            raise ValueError("context binding receipt is malformed")
        return tuple(ContextRecordBinding.from_document(item) for item in document["bindings"])

    def _path(self, manifest: ContextManifest) -> Path:
        if self.root is None:
            raise ValueError("an in-memory manifest store has no persistence path")
        return (
            self.root
            / "context"
            / manifest.mission_id
            / manifest.work_id
            / manifest.attempt_id
            / f"{manifest.manifest_digest.removeprefix('sha256:')}.json"
        )

    def _binding_path(self, manifest_digest: str) -> Path:
        return self.root / "context" / "bindings" / f"{manifest_digest.removeprefix('sha256:')}.json"  # type: ignore[union-attr]


class ContextCompiler:
    """Build valid, complete manifests by score-based whole-record selection only."""

    def __init__(self, catalog: MemoryCatalog, manifests: ContextManifestStore | None = None) -> None:
        self.catalog = catalog
        self.manifests = manifests if manifests is not None else ContextManifestStore()

    def compile(self, request: ContextRequest) -> CompiledContext:
        hot_tokens = sum(item.token_count for item in request.hot_items)
        if hot_tokens > request.token_budget:
            raise ValueError("required hot context exceeds the hard token budget")
        retrieval = RetrievalRequest(
            mission_id=request.mission_id,
            work_id=request.work_id,
            role=request.role,
            query=request.query,
            now=request.now,
            data_scopes=request.data_scopes,
            repository_key=request.repository_key,
            explicit_pins=request.explicit_pins,
            sensitivity_scopes=request.sensitivity_scopes,
            required_sensitivities=request.required_sensitivities,
        )
        ranked = self.catalog.rank(retrieval)
        ranked, provenance_count = self._exclude_unprovenanced(ranked)
        if request.evaluator_mode:
            ranked, isolation_count = self._exclude_evaluator_material(ranked)
        else:
            isolation_count = 0
        warm, cold, budget_count = self._tier(
            ranked, request.token_budget - hot_tokens, request.explicit_pins
        )
        excluded_counts = {"budget": budget_count}
        if provenance_count:
            excluded_counts["missing_provenance"] = provenance_count
        if isolation_count:
            excluded_counts["evaluator_isolation"] = isolation_count
        included = tuple(item.entry.record.record_id for item in warm)
        manifest = self._manifest(
            request,
            estimated_tokens=hot_tokens + sum(item.token_count for item in warm),
            warm_items=included,
            cold_references=tuple(item.entry.record.record_id for item in cold),
            excluded_counts=excluded_counts,
            conflict_records=self.catalog.conflicts_for(included),
        )
        bindings = self._bindings(request, manifest, (*warm, *cold))
        self.manifests.store(manifest, bindings)
        return CompiledContext(request, manifest, warm, cold, bindings)

    def retrieve_cold(self, compiled: CompiledContext, record_id: str) -> CompiledContext:
        """Record an explicit cold request by compiling a new immutable manifest revision."""

        if record_id not in {item.entry.record.record_id for item in compiled.cold}:
            raise KeyError("requested item is not an available cold reference")
        request = compiled.request
        return self.compile(
            ContextRequest(
                mission_id=request.mission_id,
                work_id=request.work_id,
                attempt_id=request.attempt_id,
                role=request.role,
                charter_digest=request.charter_digest,
                authority_digest=request.authority_digest,
                token_budget=request.token_budget,
                query=request.query,
                now=request.now,
                data_scopes=request.data_scopes,
                hot_items=request.hot_items,
                repository_key=request.repository_key,
                evaluator_mode=request.evaluator_mode,
                explicit_pins=tuple(sorted((*request.explicit_pins, record_id))),
                sensitivity_scopes=request.sensitivity_scopes,
                required_sensitivities=request.required_sensitivities,
            )
        )

    @staticmethod
    def _exclude_unprovenanced(
        ranked: tuple[RankedMemory, ...],
    ) -> tuple[tuple[RankedMemory, ...], int]:
        allowed = tuple(item for item in ranked if item.entry.record.source_refs)
        return allowed, len(ranked) - len(allowed)

    @staticmethod
    def _exclude_evaluator_material(ranked: tuple[RankedMemory, ...]) -> tuple[tuple[RankedMemory, ...], int]:
        allowed = tuple(
            item
            for item in ranked
            if item.entry.access.evaluator_visible
            and item.entry.record.memory_class not in {"scratchpad", "self_assessment"}
        )
        return allowed, len(ranked) - len(allowed)

    @staticmethod
    def _tier(
        ranked: tuple[RankedMemory, ...],
        remaining_tokens: int,
        explicit_pins: tuple[str, ...],
    ) -> tuple[tuple[RankedMemory, ...], tuple[RankedMemory, ...], int]:
        warm: list[RankedMemory] = []
        cold: list[RankedMemory] = []
        budget_count = 0
        ordered = sorted(
            ranked,
            key=lambda item: (
                item.entry.record.record_id not in explicit_pins,
                -item.score,
                item.entry.record.record_id,
            ),
        )
        for item in ordered:
            if item.token_count <= remaining_tokens:
                warm.append(item)
                remaining_tokens -= item.token_count
            else:
                cold.append(item)
                budget_count += 1
        return tuple(warm), tuple(cold), budget_count

    @staticmethod
    def _bindings(
        request: ContextRequest,
        manifest: ContextManifest,
        ranked: tuple[RankedMemory, ...],
    ) -> tuple[ContextRecordBinding, ...]:
        return tuple(
            ContextRecordBinding(
                manifest.manifest_digest,
                item.entry.record.record_id,
                item.entry.record.digest_value,
                tuple(item.entry.record.source_refs),
                item.entry.record.sensitivity,
                item.entry.record.valid_from,
                item.entry.record.valid_to,
                float(item.terms.freshness_score),
                item.entry.record.authority_level,
                request.authority_digest,
                request.mission_id,
                request.work_id,
                request.role,
                tuple(item.entry.access.roles),
                tuple(item.entry.access.data_scopes),
                item.entry.access.evaluator_visible,
            )
            for item in ranked
        )

    @staticmethod
    def _manifest(
        request: ContextRequest,
        *,
        estimated_tokens: int,
        warm_items: tuple[str, ...],
        cold_references: tuple[str, ...],
        excluded_counts: dict[str, int],
        conflict_records: tuple[str, ...],
    ) -> ContextManifest:
        categories = tuple(sorted(key for key, count in excluded_counts.items() if count))
        hot_items = tuple(item.reference for item in request.hot_items)
        digest = manifest_digest(
            mission_id=request.mission_id,
            work_id=request.work_id,
            attempt_id=request.attempt_id,
            role=request.role,
            charter_digest=request.charter_digest,
            authority_digest=request.authority_digest,
            token_budget=request.token_budget,
            estimated_tokens=estimated_tokens,
            hot_items=hot_items,
            warm_items=warm_items,
            cold_references=cold_references,
            excluded_categories=categories,
            excluded_counts=excluded_counts,
            conflict_records=conflict_records,
            generator_evaluator_separated=request.evaluator_mode,
        )
        return ContextManifest(
            request.mission_id,
            request.work_id,
            request.attempt_id,
            request.role,
            request.charter_digest,
            request.authority_digest,
            request.token_budget,
            estimated_tokens,
            hot_items,
            warm_items,
            cold_references,
            categories,
            excluded_counts,
            conflict_records,
            request.evaluator_mode,
            digest,
        )


def manifest_digest(
    *,
    mission_id: str,
    work_id: str,
    attempt_id: str,
    role: str,
    charter_digest: str,
    authority_digest: str,
    token_budget: int,
    estimated_tokens: int,
    hot_items: tuple[str, ...],
    warm_items: tuple[str, ...],
    cold_references: tuple[str, ...],
    excluded_categories: tuple[str, ...],
    excluded_counts: object,
    conflict_records: tuple[str, ...],
    generator_evaluator_separated: bool,
) -> str:
    """Hash the manifest's complete semantic content, excluding its self-reference."""

    return canonical_digest(
        {
            "mission_id": mission_id,
            "work_id": work_id,
            "attempt_id": attempt_id,
            "role": role,
            "charter_digest": charter_digest,
            "authority_digest": authority_digest,
            "token_budget": token_budget,
            "estimated_tokens": estimated_tokens,
            "hot_items": hot_items,
            "warm_items": warm_items,
            "cold_references": cold_references,
            "excluded_categories": excluded_categories,
            "excluded_counts": excluded_counts,
            "conflict_records": conflict_records,
            "generator_evaluator_separated": generator_evaluator_separated,
        }
    )
