"""Closed, subject-neutral contracts shared by the portable runtime.

This module deliberately contains data and validation only.  Constructing any of
these records grants no host trust, credential, lease, or permission to perform an
external effect.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class EffectClass(StrEnum):
    """Closed portable-plan effect classification, version 1."""

    NONE = "none"
    LOCAL_REVERSIBLE = "local-reversible"
    EXTERNAL_REVERSIBLE = "external-reversible"


EFFECT_CLASSES_V1 = tuple(item.value for item in EffectClass)
EXTERNAL_EFFECT_CLASSES_V1 = frozenset({EffectClass.EXTERNAL_REVERSIBLE})


def classify_effect(value: str) -> EffectClass:
    """Return the exact V1 effect class or fail closed on unknown spellings."""

    if type(value) is not str:
        raise ContractViolation("effect_class must be a V1 string")
    try:
        return EffectClass(value)
    except ValueError as error:
        raise ContractViolation("effect_class is not in the closed V1 vocabulary") from error


def requires_external_authority(value: str) -> bool:
    """Whether a closed V1 effect class requires external-effect authority."""

    return classify_effect(value) in EXTERNAL_EFFECT_CLASSES_V1


_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
DEFAULT_MAXIMUM_JSON_BYTES = 1_048_576
DEFAULT_MAXIMUM_JSON_DEPTH = 64


class ContractViolation(ValueError):
    """A closed runtime contract could not be authenticated or validated."""


class DurabilityRole(StrEnum):
    NONE = "none"
    PROVIDER = "provider"
    CONSUMER = "consumer"


class WaveState(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    CANDIDATE_SEALED = "CANDIDATE_SEALED"
    VERIFYING = "VERIFYING"
    INTEGRATION_READY = "INTEGRATION_READY"
    RECOVERABLE = "RECOVERABLE"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    INTEGRATED = "INTEGRATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AppealState(StrEnum):
    NONE = "NONE"
    OPEN = "OPEN"
    UPHELD = "UPHELD"
    OVERTURNED = "OVERTURNED"
    SUPERSEDED = "SUPERSEDED"


class SelectionBlockerCode(StrEnum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    AUTHORITY_AMBIGUOUS = "AUTHORITY_AMBIGUOUS"
    UNRESOLVED_TIE = "UNRESOLVED_TIE"
    UNSAFE_WINNER = "UNSAFE_WINNER"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"


def _reject_constant(value: str) -> None:
    raise ContractViolation(f"non-finite JSON number is forbidden: {value}")


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractViolation(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_depth(value: Any) -> int:
    maximum = 1
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        maximum = max(maximum, depth)
        if isinstance(current, Mapping):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return maximum


def strict_json_object(
    raw: bytes,
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_JSON_BYTES,
    maximum_depth: int = DEFAULT_MAXIMUM_JSON_DEPTH,
) -> dict[str, Any]:
    """Parse one bounded UTF-8 JSON object with no ambiguous JSON features."""

    if type(raw) is not bytes:
        raise ContractViolation("JSON input must be immutable bytes")
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise ContractViolation("maximum_bytes must be a positive integer")
    if type(maximum_depth) is not int or maximum_depth <= 0:
        raise ContractViolation("maximum_depth must be a positive integer")
    if not raw or len(raw) > maximum_bytes:
        raise ContractViolation("JSON input is empty or exceeds the byte limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ContractViolation("UTF-8 BOM is forbidden")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ContractViolation("JSON input is not strict UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise ContractViolation("JSON input is malformed") from error
    if not isinstance(value, dict):
        raise ContractViolation("contract JSON must be an object")
    if _json_depth(value) > maximum_depth:
        raise ContractViolation("JSON input exceeds the nesting-depth limit")
    canonical_json_bytes(value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ContractViolation("contract object keys must be strings")
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, "to_document"):
        return _plain(value.to_document())
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractViolation("non-finite values are forbidden")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the sole canonical JSON representation used by these contracts."""

    try:
        return json.dumps(
            _plain(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ContractViolation("contract is not canonically serializable") from error


def raw_sha256(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise ContractViolation("digest input must be immutable bytes")
    return f"sha256:{sha256(raw).hexdigest()}"


def canonical_digest(value: Any) -> str:
    return raw_sha256(canonical_json_bytes(value))


def require_digest(value: str, label: str) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ContractViolation(f"{label} must be lowercase sha256:<64 hex>")


def require_identifier(value: str, label: str) -> None:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise ContractViolation(f"{label} is not a portable identifier")


def require_time(value: str, label: str) -> datetime:
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise ContractViolation(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractViolation(f"{label} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractViolation(f"{label} must include an offset")
    return parsed


def portable_path(value: str) -> str:
    if type(value) is not str or not value:
        raise ContractViolation("path is required")
    candidate = value.replace("\\", "/")
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        raise ContractViolation("path must be repository-relative")
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractViolation("path contains an unsafe segment")
    return PurePosixPath(*parts).as_posix()


def _unique_strings(
    values: tuple[str, ...], label: str, *, required: bool = False
) -> None:
    if type(values) is not tuple or any(
        type(value) is not str or not value for value in values
    ):
        raise ContractViolation(f"{label} must contain non-empty strings")
    if required and not values:
        raise ContractViolation(f"{label} is required")
    if len(set(values)) != len(values):
        raise ContractViolation(f"{label} contains duplicates")


def _closed(document: Mapping[str, Any], fields: set[str], label: str) -> None:
    if not isinstance(document, Mapping) or set(document) != fields:
        raise ContractViolation(f"{label} has missing or unsupported fields")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    digest: str
    source: str
    claim_ids: tuple[str, ...]
    observed_at: str

    def __post_init__(self) -> None:
        require_identifier(self.evidence_id, "evidence_id")
        require_digest(self.digest, "evidence digest")
        if type(self.source) is not str or not self.source:
            raise ContractViolation("evidence source is required")
        _unique_strings(self.claim_ids, "claim_ids", required=True)
        require_time(self.observed_at, "observed_at")

    def to_document(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "digest": self.digest,
            "source": self.source,
            "claim_ids": list(self.claim_ids),
            "observed_at": self.observed_at,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "EvidenceReference":
        _closed(
            document,
            {"evidence_id", "digest", "source", "claim_ids", "observed_at"},
            "evidence reference",
        )
        claims = document["claim_ids"]
        if not isinstance(claims, list) or any(
            type(item) is not str for item in claims
        ):
            raise ContractViolation("claim_ids must be a string list")
        return cls(
            document["evidence_id"],
            document["digest"],
            document["source"],
            tuple(claims),
            document["observed_at"],
        )


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    resource_id: str
    kind: str
    quantity: int
    unit: str
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.resource_id, "resource_id")
        require_identifier(self.kind, "resource kind")
        if type(self.quantity) is not int or self.quantity < 0:
            raise ContractViolation("resource quantity must be a non-negative integer")
        require_identifier(self.unit, "resource unit")
        _unique_strings(self.constraints, "resource constraints")

    def to_document(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "quantity": self.quantity,
            "unit": self.unit,
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    capability_id: str
    operation: str
    effect_class: str
    authority_id: str
    adapter_id: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.capability_id, "capability_id"),
            (self.operation, "operation"),
            (self.authority_id, "authority_id"),
            (self.adapter_id, "adapter_id"),
        ):
            require_identifier(value, label)
        classify_effect(self.effect_class)

    def to_document(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "operation": self.operation,
            "effect_class": self.effect_class,
            "authority_id": self.authority_id,
            "adapter_id": self.adapter_id,
        }


@dataclass(frozen=True, slots=True)
class AdapterRequirement:
    adapter_id: str
    interface: str
    version: str
    configuration_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.adapter_id, "adapter_id")
        require_identifier(self.interface, "adapter interface")
        require_identifier(self.version, "adapter version")
        require_digest(self.configuration_digest, "configuration_digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "interface": self.interface,
            "version": self.version,
            "configuration_digest": self.configuration_digest,
        }


@dataclass(frozen=True, slots=True)
class AuthorityEnvelope:
    authority_id: str
    principal_id: str
    grant_digest: str
    allowed_actions: tuple[str, ...]
    denied_actions: tuple[str, ...]
    expires_at: str
    external_effects: bool

    def __post_init__(self) -> None:
        require_identifier(self.authority_id, "authority_id")
        require_identifier(self.principal_id, "principal_id")
        require_digest(self.grant_digest, "grant_digest")
        _unique_strings(self.allowed_actions, "allowed_actions")
        _unique_strings(self.denied_actions, "denied_actions")
        if set(self.allowed_actions) & set(self.denied_actions):
            raise ContractViolation(
                "authority action cannot be both allowed and denied"
            )
        require_time(self.expires_at, "expires_at")
        if type(self.external_effects) is not bool:
            raise ContractViolation("external_effects must be boolean")

    def to_document(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "principal_id": self.principal_id,
            "grant_digest": self.grant_digest,
            "allowed_actions": list(self.allowed_actions),
            "denied_actions": list(self.denied_actions),
            "expires_at": self.expires_at,
            "external_effects": self.external_effects,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "AuthorityEnvelope":
        fields = {
            "authority_id",
            "principal_id",
            "grant_digest",
            "allowed_actions",
            "denied_actions",
            "expires_at",
            "external_effects",
        }
        _closed(document, fields, "authority envelope")
        allowed = document["allowed_actions"]
        denied = document["denied_actions"]
        if not isinstance(allowed, list) or not isinstance(denied, list):
            raise ContractViolation("authority actions must be lists")
        if any(type(item) is not str for item in (*allowed, *denied)):
            raise ContractViolation("authority actions must contain strings")
        return cls(
            document["authority_id"],
            document["principal_id"],
            document["grant_digest"],
            tuple(allowed),
            tuple(denied),
            document["expires_at"],
            document["external_effects"],
        )


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    wall_seconds: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_microunits: int
    tool_calls: int
    concurrent_workers: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ContractViolation(f"{name} must be a non-negative integer")

    def to_document(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "BudgetPolicy":
        fields = {
            "wall_seconds",
            "model_calls",
            "input_tokens",
            "output_tokens",
            "cost_microunits",
            "tool_calls",
            "concurrent_workers",
        }
        _closed(document, fields, "budget policy")
        return cls(**document)


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    maximum_attempts: int
    checkpoint_required: bool
    rollback_required: bool
    stop_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.maximum_attempts) is not int or self.maximum_attempts < 1:
            raise ContractViolation("maximum_attempts must be a positive integer")
        if (
            type(self.checkpoint_required) is not bool
            or type(self.rollback_required) is not bool
        ):
            raise ContractViolation("recovery flags must be boolean")
        _unique_strings(self.stop_conditions, "stop_conditions", required=True)

    def to_document(self) -> dict[str, Any]:
        return {
            "maximum_attempts": self.maximum_attempts,
            "checkpoint_required": self.checkpoint_required,
            "rollback_required": self.rollback_required,
            "stop_conditions": list(self.stop_conditions),
        }


@dataclass(frozen=True, slots=True)
class IntegrationPolicy:
    strategy: str
    target: str
    expected_base: str
    compare_and_swap: bool
    protected_target: bool

    def __post_init__(self) -> None:
        require_identifier(self.strategy, "integration strategy")
        if type(self.target) is not str or not self.target:
            raise ContractViolation("integration target is required")
        require_digest(self.expected_base, "expected_base")
        if (
            type(self.compare_and_swap) is not bool
            or type(self.protected_target) is not bool
        ):
            raise ContractViolation("integration flags must be boolean")

    def to_document(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "target": self.target,
            "expected_base": self.expected_base,
            "compare_and_swap": self.compare_and_swap,
            "protected_target": self.protected_target,
        }


@dataclass(frozen=True, slots=True)
class TokenPolicy:
    context_tokens: int
    response_tokens: int
    reserve_tokens: int
    accounting: str
    overflow: str

    def __post_init__(self) -> None:
        for name in ("context_tokens", "response_tokens", "reserve_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ContractViolation(f"{name} must be a non-negative integer")
        require_identifier(self.accounting, "token accounting")
        require_identifier(self.overflow, "token overflow policy")

    def to_document(self) -> dict[str, Any]:
        return {
            "context_tokens": self.context_tokens,
            "response_tokens": self.response_tokens,
            "reserve_tokens": self.reserve_tokens,
            "accounting": self.accounting,
            "overflow": self.overflow,
        }


@dataclass(frozen=True, slots=True)
class NodeRuntimeContract:
    node_id: str
    dependencies: tuple[str, ...]
    durability_role: DurabilityRole
    durability_providers: tuple[str, ...]
    write_scope: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.node_id, "node_id")
        _unique_strings(self.dependencies, "dependencies")
        _unique_strings(self.durability_providers, "durability_providers")
        _unique_strings(self.write_scope, "write_scope")
        if self.node_id in self.dependencies:
            raise ContractViolation("node cannot depend on itself")
        if not isinstance(self.durability_role, DurabilityRole):
            raise ContractViolation("durability_role must be typed")
        normalized = tuple(portable_path(path) for path in self.write_scope)
        if normalized != self.write_scope:
            raise ContractViolation(
                "write_scope paths must use normalized POSIX spelling"
            )
        if (
            self.durability_role is not DurabilityRole.CONSUMER
            and self.durability_providers
        ):
            raise ContractViolation("only durability consumers may name providers")

    def to_document(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "dependencies": list(self.dependencies),
            "durability_role": self.durability_role.value,
            "durability_providers": list(self.durability_providers),
            "write_scope": list(self.write_scope),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "NodeRuntimeContract":
        fields = {
            "node_id",
            "dependencies",
            "durability_role",
            "durability_providers",
            "write_scope",
        }
        _closed(document, fields, "node runtime contract")
        for name in ("dependencies", "durability_providers", "write_scope"):
            if not isinstance(document[name], list) or any(
                type(value) is not str for value in document[name]
            ):
                raise ContractViolation(f"{name} must be a string list")
        try:
            role = DurabilityRole(document["durability_role"])
        except (TypeError, ValueError) as error:
            raise ContractViolation("unsupported durability_role") from error
        return cls(
            node_id=document["node_id"],
            dependencies=tuple(document["dependencies"]),
            durability_role=role,
            durability_providers=tuple(document["durability_providers"]),
            write_scope=tuple(document["write_scope"]),
        )


@dataclass(frozen=True, slots=True)
class SharedSurfaceOwner:
    surface: str
    owner: str
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.surface, "surface")
        require_identifier(self.owner, "surface owner")
        _unique_strings(self.paths, "surface paths", required=True)
        normalized = tuple(portable_path(path) for path in self.paths)
        if normalized != self.paths:
            raise ContractViolation("surface paths must use normalized POSIX spelling")

    def to_document(self) -> dict[str, Any]:
        return {"surface": self.surface, "owner": self.owner, "paths": list(self.paths)}


@dataclass(frozen=True, slots=True)
class RuntimeContractSummary:
    node_count: int
    unique_write_path_count: int
    shared_surface_count: int
    digest: str


def _ancestors(node_id: str, by_id: Mapping[str, NodeRuntimeContract]) -> set[str]:
    result: set[str] = set()
    visiting: set[str] = set()

    def visit(current: str) -> None:
        if current in visiting:
            raise ContractViolation("node dependency graph contains a cycle")
        visiting.add(current)
        for dependency in by_id[current].dependencies:
            if dependency not in by_id:
                raise ContractViolation(
                    f"node {current} has unknown dependency {dependency}"
                )
            if dependency not in result:
                result.add(dependency)
                visit(dependency)
        visiting.remove(current)

    visit(node_id)
    return result


def validate_runtime_contracts(
    nodes: Sequence[NodeRuntimeContract],
    shared_surfaces: Sequence[SharedSurfaceOwner],
    *,
    expected_durability: Mapping[str, tuple[DurabilityRole, tuple[str, ...]]],
    expected_shared_surface_owners: Mapping[str, str],
    expected_node_count: int,
    expected_write_path_count: int,
) -> RuntimeContractSummary:
    """Validate graph, Clerk durability assignments, and sole-writer ownership."""

    if len(nodes) != expected_node_count:
        raise ContractViolation(
            "runtime contract node count does not match the sealed expectation"
        )
    by_id = {node.node_id: node for node in nodes}
    if len(by_id) != len(nodes):
        raise ContractViolation("runtime contract contains duplicate node ids")
    if set(by_id) != set(expected_durability):
        raise ContractViolation(
            "durability assignment inventory is incomplete or substituted"
        )
    all_paths: dict[str, str] = {}
    ancestors = {node_id: _ancestors(node_id, by_id) for node_id in by_id}
    for node in nodes:
        expected_role, expected_providers = expected_durability[node.node_id]
        if (
            node.durability_role is not expected_role
            or node.durability_providers != expected_providers
        ):
            raise ContractViolation(f"durability assignment changed for {node.node_id}")
        for provider in node.durability_providers:
            if provider not in ancestors[node.node_id]:
                raise ContractViolation(
                    f"durability provider {provider} is not an ancestor of {node.node_id}"
                )
            if by_id[provider].durability_role is not DurabilityRole.PROVIDER:
                raise ContractViolation(
                    f"durability provider {provider} is not typed provider"
                )
        for path in node.write_scope:
            previous = all_paths.get(path)
            if previous is not None:
                raise ContractViolation(
                    f"write path {path} has multiple owners: {previous}, {node.node_id}"
                )
            all_paths[path] = node.node_id
    if len(all_paths) != expected_write_path_count:
        raise ContractViolation(
            "unique write-path count does not match the sealed expectation"
        )
    surfaces = {surface.surface: surface for surface in shared_surfaces}
    if len(surfaces) != len(shared_surfaces):
        raise ContractViolation("shared surface inventory contains duplicates")
    if {key: value.owner for key, value in surfaces.items()} != dict(
        expected_shared_surface_owners
    ):
        raise ContractViolation("shared surface owner mapping changed")
    for surface in shared_surfaces:
        if surface.owner not in by_id:
            raise ContractViolation(f"shared surface owner {surface.owner} is unknown")
        for path in surface.paths:
            if all_paths.get(path) != surface.owner:
                raise ContractViolation(
                    f"shared surface path {path} is not solely owned by {surface.owner}"
                )
    material = {
        "nodes": [node.to_document() for node in nodes],
        "shared_surfaces": [surface.to_document() for surface in shared_surfaces],
    }
    return RuntimeContractSummary(
        len(nodes), len(all_paths), len(shared_surfaces), canonical_digest(material)
    )


@dataclass(frozen=True, slots=True)
class DecisionAlternative:
    alternative_id: str
    description: str
    evidence_ids: tuple[str, ...]
    counterevidence_ids: tuple[str, ...]
    constraint_results: tuple[tuple[str, bool], ...]
    authority_ids: tuple[str, ...]
    safe: bool

    def __post_init__(self) -> None:
        require_identifier(self.alternative_id, "alternative_id")
        if type(self.description) is not str or not self.description:
            raise ContractViolation("alternative description is required")
        _unique_strings(self.evidence_ids, "alternative evidence_ids")
        _unique_strings(self.counterevidence_ids, "alternative counterevidence_ids")
        _unique_strings(self.authority_ids, "alternative authority_ids")
        if type(self.constraint_results) is not tuple:
            raise ContractViolation("constraint_results must be immutable")
        names: list[str] = []
        for item in self.constraint_results:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not bool
            ):
                raise ContractViolation(
                    "constraint result must be a (name, boolean) pair"
                )
            names.append(item[0])
        if len(set(names)) != len(names):
            raise ContractViolation("constraint_results contains duplicates")
        if type(self.safe) is not bool:
            raise ContractViolation("alternative safe flag must be boolean")

    def to_document(self) -> dict[str, Any]:
        return {
            "alternative_id": self.alternative_id,
            "description": self.description,
            "evidence_ids": list(self.evidence_ids),
            "counterevidence_ids": list(self.counterevidence_ids),
            "constraint_results": {
                name: value for name, value in self.constraint_results
            },
            "authority_ids": list(self.authority_ids),
            "safe": self.safe,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "DecisionAlternative":
        fields = {
            "alternative_id",
            "description",
            "evidence_ids",
            "counterevidence_ids",
            "constraint_results",
            "authority_ids",
            "safe",
        }
        _closed(document, fields, "decision alternative")
        for field in ("evidence_ids", "counterevidence_ids", "authority_ids"):
            if not isinstance(document[field], list) or any(
                type(item) is not str for item in document[field]
            ):
                raise ContractViolation(f"{field} must be a string list")
        constraints = document["constraint_results"]
        if not isinstance(constraints, Mapping) or any(
            type(key) is not str or type(value) is not bool
            for key, value in constraints.items()
        ):
            raise ContractViolation("constraint_results must map strings to booleans")
        return cls(
            document["alternative_id"],
            document["description"],
            tuple(document["evidence_ids"]),
            tuple(document["counterevidence_ids"]),
            tuple(constraints.items()),
            tuple(document["authority_ids"]),
            document["safe"],
        )


@dataclass(frozen=True, slots=True)
class AlternativeScore:
    alternative_id: str
    score: float

    def __post_init__(self) -> None:
        require_identifier(self.alternative_id, "scored alternative_id")
        if (
            type(self.score) not in {int, float}
            or isinstance(self.score, bool)
            or not math.isfinite(self.score)
        ):
            raise ContractViolation("alternative score must be finite")

    def to_document(self) -> dict[str, Any]:
        return {"alternative_id": self.alternative_id, "score": self.score}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "AlternativeScore":
        _closed(document, {"alternative_id", "score"}, "alternative score")
        return cls(document["alternative_id"], document["score"])


@dataclass(frozen=True, slots=True)
class DecisionMemoryDraft:
    schema_version: int
    memory_id: str
    question: str
    snapshot: str
    alternatives: tuple[DecisionAlternative, ...]
    evidence: tuple[EvidenceReference, ...]
    counterevidence: tuple[EvidenceReference, ...]
    constraints: tuple[str, ...]
    authority: tuple[AuthorityEnvelope, ...]
    budget: BudgetPolicy
    scoring_model: str
    scores: tuple[AlternativeScore, ...]
    uncertainty: str
    owner: str
    decided_at: str
    fresh_until: str
    corrections: tuple[str, ...]
    supersession: str | None
    appeal_state: AppealState

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractViolation("unsupported decision-memory schema version")
        require_identifier(self.memory_id, "memory_id")
        if type(self.question) is not str or not self.question:
            raise ContractViolation("decision question is required")
        require_digest(self.snapshot, "decision snapshot")
        if not self.alternatives or len(
            {item.alternative_id for item in self.alternatives}
        ) != len(self.alternatives):
            raise ContractViolation(
                "decision alternatives are required and must be unique"
            )
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ContractViolation("decision evidence ids must be unique")
        if len({item.evidence_id for item in self.counterevidence}) != len(
            self.counterevidence
        ):
            raise ContractViolation("decision counterevidence ids must be unique")
        _unique_strings(self.constraints, "decision constraints", required=True)
        if len({item.authority_id for item in self.authority}) != len(self.authority):
            raise ContractViolation("decision authority ids must be unique")
        require_identifier(self.scoring_model, "scoring_model")
        if len({item.alternative_id for item in self.scores}) != len(self.scores):
            raise ContractViolation("decision scores must be unique")
        if type(self.uncertainty) is not str or not self.uncertainty:
            raise ContractViolation("decision uncertainty is required")
        require_identifier(self.owner, "decision owner")
        decided = require_time(self.decided_at, "decided_at")
        fresh = require_time(self.fresh_until, "fresh_until")
        if fresh < decided:
            raise ContractViolation("fresh_until precedes decided_at")
        _unique_strings(self.corrections, "decision corrections")
        if self.supersession is not None:
            require_identifier(self.supersession, "supersession")
        if not isinstance(self.appeal_state, AppealState):
            raise ContractViolation("appeal_state must be typed")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "memory_id": self.memory_id,
            "question": self.question,
            "snapshot": self.snapshot,
            "alternatives": [item.to_document() for item in self.alternatives],
            "evidence": [item.to_document() for item in self.evidence],
            "counterevidence": [item.to_document() for item in self.counterevidence],
            "constraints": list(self.constraints),
            "authority": [item.to_document() for item in self.authority],
            "budget": self.budget.to_document(),
            "scoring_model": self.scoring_model,
            "scores": [item.to_document() for item in self.scores],
            "uncertainty": self.uncertainty,
            "owner": self.owner,
            "decided_at": self.decided_at,
            "fresh_until": self.fresh_until,
            "corrections": list(self.corrections),
            "supersession": self.supersession,
            "appeal_state": self.appeal_state.value,
        }


@dataclass(frozen=True, slots=True)
class DecisionMemoryEntry:
    draft: DecisionMemoryDraft
    winner: str
    losers: tuple[str, ...]
    entry_digest: str = ""

    def __post_init__(self) -> None:
        alternatives = {item.alternative_id for item in self.draft.alternatives}
        if self.winner not in alternatives:
            raise ContractViolation("decision winner is not an alternative")
        _unique_strings(self.losers, "decision losers")
        if set(self.losers) != alternatives - {self.winner}:
            raise ContractViolation(
                "decision losers must retain every non-winning alternative"
            )
        expected = canonical_digest(self.to_document(include_digest=False))
        if not self.entry_digest:
            object.__setattr__(self, "entry_digest", expected)
        elif self.entry_digest != expected:
            raise ContractViolation("decision-memory entry digest is invalid")

    def to_document(self, *, include_digest: bool = True) -> dict[str, Any]:
        document: dict[str, Any] = {
            **self.draft.to_document(),
            "winner": self.winner,
            "losers": list(self.losers),
        }
        if include_digest:
            document["entry_digest"] = self.entry_digest
        return document

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "DecisionMemoryEntry":
        fields = {
            "schema_version",
            "memory_id",
            "question",
            "snapshot",
            "alternatives",
            "evidence",
            "counterevidence",
            "constraints",
            "authority",
            "budget",
            "scoring_model",
            "scores",
            "winner",
            "losers",
            "uncertainty",
            "owner",
            "decided_at",
            "fresh_until",
            "corrections",
            "supersession",
            "appeal_state",
            "entry_digest",
        }
        _closed(document, fields, "decision-memory entry")
        for field in (
            "alternatives",
            "evidence",
            "counterevidence",
            "authority",
            "scores",
        ):
            if not isinstance(document[field], list) or any(
                not isinstance(item, Mapping) for item in document[field]
            ):
                raise ContractViolation(f"decision {field} must be an object list")
        for field in ("constraints", "losers", "corrections"):
            if not isinstance(document[field], list) or any(
                type(item) is not str for item in document[field]
            ):
                raise ContractViolation(f"decision {field} must be a string list")
        if not isinstance(document["budget"], Mapping):
            raise ContractViolation("decision budget must be an object")
        try:
            appeal_state = AppealState(document["appeal_state"])
        except (TypeError, ValueError) as error:
            raise ContractViolation("unsupported appeal state") from error
        draft = DecisionMemoryDraft(
            document["schema_version"],
            document["memory_id"],
            document["question"],
            document["snapshot"],
            tuple(
                DecisionAlternative.from_document(item)
                for item in document["alternatives"]
            ),
            tuple(
                EvidenceReference.from_document(item) for item in document["evidence"]
            ),
            tuple(
                EvidenceReference.from_document(item)
                for item in document["counterevidence"]
            ),
            tuple(document["constraints"]),
            tuple(
                AuthorityEnvelope.from_document(item) for item in document["authority"]
            ),
            BudgetPolicy.from_document(document["budget"]),
            document["scoring_model"],
            tuple(AlternativeScore.from_document(item) for item in document["scores"]),
            document["uncertainty"],
            document["owner"],
            document["decided_at"],
            document["fresh_until"],
            tuple(document["corrections"]),
            document["supersession"],
            appeal_state,
        )
        return cls(
            draft,
            document["winner"],
            tuple(document["losers"]),
            document["entry_digest"],
        )


@dataclass(frozen=True, slots=True)
class VisionPosture:
    schema_version: int
    a5: str
    active_gate_reference_only_conflict: str
    forbidden_claims: tuple[str, ...]
    maximum_claim: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractViolation("unsupported vision-posture schema version")
        if self.a5 not in {"READY", "NOT_READY"}:
            raise ContractViolation("unsupported A5 posture")
        if self.active_gate_reference_only_conflict not in {"RESOLVED", "UNRESOLVED"}:
            raise ContractViolation("unsupported vision conflict posture")
        _unique_strings(self.forbidden_claims, "forbidden vision claims")
        require_identifier(self.maximum_claim, "maximum_claim")
        if self.active_gate_reference_only_conflict == "UNRESOLVED":
            required = {"full_autonomy", "full_hardened_vision_compliance"}
            if self.a5 != "NOT_READY" or not required <= set(self.forbidden_claims):
                raise ContractViolation(
                    "unresolved vision conflict must keep A5 and broad claims not-ready"
                )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "a5": self.a5,
            "active_gate_reference_only_conflict": self.active_gate_reference_only_conflict,
            "forbidden_claims": list(self.forbidden_claims),
            "maximum_claim": self.maximum_claim,
        }


@dataclass(frozen=True, slots=True)
class SelectionBlocker:
    code: SelectionBlockerCode
    reasons: tuple[str, ...]
    memory_id: str
    snapshot: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, SelectionBlockerCode):
            raise ContractViolation("selection blocker code must be typed")
        _unique_strings(self.reasons, "selection blocker reasons", required=True)
        require_identifier(self.memory_id, "memory_id")
        require_digest(self.snapshot, "decision snapshot")


def select_decision(
    draft: DecisionMemoryDraft,
    *,
    observed_snapshot: str,
    now: str,
) -> DecisionMemoryEntry | SelectionBlocker:
    """Select one safe, evidenced alternative or return a typed blocker."""

    require_digest(observed_snapshot, "observed_snapshot")
    instant = require_time(now, "selection time")
    if observed_snapshot != draft.snapshot or instant > require_time(
        draft.fresh_until, "fresh_until"
    ):
        return SelectionBlocker(
            SelectionBlockerCode.STALE_SNAPSHOT,
            ("decision snapshot is stale or no longer fresh",),
            draft.memory_id,
            draft.snapshot,
        )
    evidence_ids = {item.evidence_id for item in draft.evidence}
    counter_ids = {item.evidence_id for item in draft.counterevidence}
    missing: list[str] = []
    for alternative in draft.alternatives:
        if not alternative.evidence_ids:
            missing.append(f"{alternative.alternative_id}:no-evidence")
        missing.extend(
            f"{alternative.alternative_id}:unknown-evidence:{item}"
            for item in alternative.evidence_ids
            if item not in evidence_ids
        )
        missing.extend(
            f"{alternative.alternative_id}:unknown-counterevidence:{item}"
            for item in alternative.counterevidence_ids
            if item not in counter_ids
        )
        if set(name for name, _ in alternative.constraint_results) != set(
            draft.constraints
        ):
            missing.append(f"{alternative.alternative_id}:incomplete-constraints")
    score_ids = {score.alternative_id for score in draft.scores}
    alternative_ids = {item.alternative_id for item in draft.alternatives}
    if score_ids != alternative_ids:
        missing.append("scores:incomplete-or-unknown")
    if missing:
        return SelectionBlocker(
            SelectionBlockerCode.MISSING_EVIDENCE,
            tuple(sorted(set(missing))),
            draft.memory_id,
            draft.snapshot,
        )
    authorities = {item.authority_id: item for item in draft.authority}
    ambiguous: list[str] = []
    for alternative in draft.alternatives:
        if len(alternative.authority_ids) != 1:
            ambiguous.append(
                f"{alternative.alternative_id}:requires-exactly-one-authority"
            )
            continue
        envelope = authorities.get(alternative.authority_ids[0])
        if envelope is None or instant > require_time(
            envelope.expires_at, "authority expires_at"
        ):
            ambiguous.append(
                f"{alternative.alternative_id}:authority-missing-or-expired"
            )
    if ambiguous:
        return SelectionBlocker(
            SelectionBlockerCode.AUTHORITY_AMBIGUOUS,
            tuple(sorted(ambiguous)),
            draft.memory_id,
            draft.snapshot,
        )
    high = max(float(score.score) for score in draft.scores)
    winners = sorted(
        score.alternative_id for score in draft.scores if float(score.score) == high
    )
    if len(winners) != 1:
        return SelectionBlocker(
            SelectionBlockerCode.UNRESOLVED_TIE,
            ("highest score is shared by: " + ",".join(winners),),
            draft.memory_id,
            draft.snapshot,
        )
    winner = next(
        item for item in draft.alternatives if item.alternative_id == winners[0]
    )
    if not winner.safe or any(not value for _, value in winner.constraint_results):
        return SelectionBlocker(
            SelectionBlockerCode.UNSAFE_WINNER,
            (f"highest-scoring alternative {winner.alternative_id} is unsafe",),
            draft.memory_id,
            draft.snapshot,
        )
    losers = tuple(sorted(alternative_ids - {winner.alternative_id}))
    return DecisionMemoryEntry(draft, winner.alternative_id, losers)


__all__ = [
    "AdapterRequirement",
    "AlternativeScore",
    "AppealState",
    "AuthorityEnvelope",
    "BudgetPolicy",
    "CapabilityRequirement",
    "ContractViolation",
    "DecisionAlternative",
    "DecisionMemoryDraft",
    "DecisionMemoryEntry",
    "DurabilityRole",
    "EFFECT_CLASSES_V1",
    "EXTERNAL_EFFECT_CLASSES_V1",
    "EffectClass",
    "EvidenceReference",
    "IntegrationPolicy",
    "NodeRuntimeContract",
    "RecoveryPolicy",
    "ResourceRequirement",
    "RuntimeContractSummary",
    "SelectionBlocker",
    "SelectionBlockerCode",
    "SharedSurfaceOwner",
    "TokenPolicy",
    "VisionPosture",
    "WaveState",
    "canonical_digest",
    "canonical_json_bytes",
    "classify_effect",
    "portable_path",
    "raw_sha256",
    "require_digest",
    "require_identifier",
    "require_time",
    "requires_external_authority",
    "select_decision",
    "strict_json_object",
    "validate_runtime_contracts",
]
