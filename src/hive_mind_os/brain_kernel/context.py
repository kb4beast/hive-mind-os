"""Deterministic hot/warm/cold context compilation for local kernel primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from .canonical import canonical_bytes, canonical_digest
from .contracts import ContextManifest
from .memory import MemoryCatalog, RankedMemory, RetrievalRequest


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

    @property
    def estimated_tokens(self) -> int:
        return self.manifest.estimated_tokens


class ContextManifestStore:
    """Append-only manifest registry keyed by digest, not a mutable attempt slot."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._manifests: dict[str, ContextManifest] = {}
        self.root = None if root is None else Path(root)
        self._lock = RLock()

    def store(self, manifest: ContextManifest) -> None:
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
            self._persist(manifest)
            self._manifests[manifest.manifest_digest] = manifest

    def get(self, digest: str) -> ContextManifest:
        try:
            return self._manifests[digest]
        except KeyError as error:
            raise KeyError(f"unknown context manifest: {digest}") from error

    def manifests(self) -> tuple[ContextManifest, ...]:
        return tuple(self._manifests[digest] for digest in sorted(self._manifests))

    def restore(self) -> tuple[ContextManifest, ...]:
        """Load every on-disk manifest only if its canonical contract verifies."""

        if self.root is None:
            return self.manifests()
        directory = self.root / "context"
        if not directory.exists():
            return ()
        for path in sorted(directory.rglob("*.json")):
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
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError(f"context manifest is corrupt: {path}") from error
            self.store(manifest)
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
        )
        ranked = self.catalog.rank(retrieval)
        if request.evaluator_mode:
            ranked, isolation_count = self._exclude_evaluator_material(ranked)
        else:
            isolation_count = 0
        warm, cold, budget_count = self._tier(
            ranked, request.token_budget - hot_tokens, request.explicit_pins
        )
        excluded_counts = {"budget": budget_count}
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
        self.manifests.store(manifest)
        return CompiledContext(request, manifest, warm, cold)

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
            )
        )

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
