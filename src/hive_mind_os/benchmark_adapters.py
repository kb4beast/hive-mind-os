"""Fail-closed adapters for N30 whole-OS benchmark execution.

Adapters materialize pinned recipes into broker requests.  They never invoke a
shell, select credentials, or import a comparator's control logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol, cast

from .campaign_metrics import (
    AdmissionRegistry,
    MatchProtocol,
    StageEvidence,
    VariantSeal,
    canonical_digest,
    load_match_protocol,
    resolve_execution_admission,
)


class BenchmarkAdapterError(ValueError):
    pass


def _identifier(value: object, name: str) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(char.isspace() for char in value)
    ):
        raise BenchmarkAdapterError(f"{name} must be an exact identifier")


def _sha(value: object, name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or set(value[7:]) - set("0123456789abcdef")
    ):
        raise BenchmarkAdapterError(f"{name} must be a lowercase SHA-256 digest")


class RecipeClass(StrEnum):
    CURRENT_BASELINE = "current-baseline"
    SELECTED_DESIGN = "selected-design"
    MINIMAL_BUILDER = "minimal-builder"
    SDK_BUILDER = "sdk-builder"
    ABLATION = "ablation"


@dataclass(frozen=True, slots=True)
class RecipeManifest:
    recipe_id: str
    recipe_class: RecipeClass
    source_or_binary_digest: str
    prompt_digest: str
    model_digest: str
    command_profile_digest: str
    tool_digest: str
    context_digest: str
    check_policy_digest: str
    learning_policy_digest: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    disabled_optimizations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.recipe_id, "recipe")
        if type(self.recipe_class) is not RecipeClass:
            raise BenchmarkAdapterError("recipe class must be typed")
        for name in (
            "source_or_binary_digest",
            "prompt_digest",
            "model_digest",
            "command_profile_digest",
            "tool_digest",
            "context_digest",
            "check_policy_digest",
            "learning_policy_digest",
        ):
            _sha(getattr(self, name), name)
        if not self.argv or any(
            type(part) is not str or not part or "\x00" in part for part in self.argv
        ):
            raise BenchmarkAdapterError(
                "recipe requires a direct non-shell argument vector"
            )
        if set(self.environment) - {
            "LANG",
            "LC_ALL",
            "PYTHONHASHSEED",
            "TZ",
            "NO_COLOR",
        }:
            raise BenchmarkAdapterError(
                "recipe environment includes an unadmitted variable"
            )
        if (
            self.recipe_class is RecipeClass.ABLATION
            and not self.disabled_optimizations
        ):
            raise BenchmarkAdapterError("ablation must name a disabled optimization")
        if (
            self.recipe_class is not RecipeClass.ABLATION
            and self.disabled_optimizations
        ):
            raise BenchmarkAdapterError("only ablations may disable optimizations")
        forbidden = {
            "privacy",
            "tenant-isolation",
            "independent-qualification",
            "authority",
        }
        if forbidden.intersection(self.disabled_optimizations):
            raise BenchmarkAdapterError(
                "ablation cannot disable a safety or qualification boundary"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> Mapping[str, object]:
        return {
            "recipe_id": self.recipe_id,
            "recipe_class": self.recipe_class.value,
            "source_or_binary_digest": self.source_or_binary_digest,
            "prompt_digest": self.prompt_digest,
            "model_digest": self.model_digest,
            "command_profile_digest": self.command_profile_digest,
            "tool_digest": self.tool_digest,
            "context_digest": self.context_digest,
            "check_policy_digest": self.check_policy_digest,
            "learning_policy_digest": self.learning_policy_digest,
            "argv": self.argv,
            "environment": dict(self.environment),
            "disabled_optimizations": self.disabled_optimizations,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, object]) -> "RecipeManifest":
        required = {
            "recipe_id",
            "recipe_class",
            "source_or_binary_digest",
            "prompt_digest",
            "model_digest",
            "command_profile_digest",
            "tool_digest",
            "context_digest",
            "check_policy_digest",
            "learning_policy_digest",
            "argv",
            "environment",
            "disabled_optimizations",
        }
        if set(value) != required:
            raise BenchmarkAdapterError("recipe document has an unknown shape")
        argv = value["argv"]
        environment = value["environment"]
        disabled = value["disabled_optimizations"]
        if (
            not isinstance(argv, list)
            or not isinstance(environment, Mapping)
            or not isinstance(disabled, list)
            or any(type(key) is not str or type(item) is not str for key, item in environment.items())
        ):
            raise BenchmarkAdapterError("recipe document has invalid container fields")
        try:
            return cls(
                recipe_id=cast(str, value["recipe_id"]),
                recipe_class=RecipeClass(cast(str, value["recipe_class"])),
                source_or_binary_digest=cast(str, value["source_or_binary_digest"]),
                prompt_digest=cast(str, value["prompt_digest"]),
                model_digest=cast(str, value["model_digest"]),
                command_profile_digest=cast(str, value["command_profile_digest"]),
                tool_digest=cast(str, value["tool_digest"]),
                context_digest=cast(str, value["context_digest"]),
                check_policy_digest=cast(str, value["check_policy_digest"]),
                learning_policy_digest=cast(str, value["learning_policy_digest"]),
                argv=tuple(cast(list[str], argv)),
                environment=MappingProxyType(dict(cast(Mapping[str, str], environment))),
                disabled_optimizations=tuple(cast(list[str], disabled)),
            )
        except (TypeError, ValueError) as exc:
            raise BenchmarkAdapterError("recipe document is invalid") from exc


@dataclass(frozen=True, slots=True)
class BenchmarkAdapterManifest:
    """Exact direct-command recipes sealed by the N02 manifest digest."""

    manifest_id: str
    protocol_id: str
    recipes: Mapping[str, RecipeManifest]
    signature_refs: Mapping[str, str]

    def __post_init__(self) -> None:
        _identifier(self.manifest_id, "adapter manifest")
        _identifier(self.protocol_id, "protocol")
        recipes = dict(self.recipes)
        signatures = dict(self.signature_refs)
        if not recipes or any(key != recipe.recipe_id for key, recipe in recipes.items()):
            raise BenchmarkAdapterError("adapter recipes require exact variant identities")
        if set(signatures) != {"original", "hybrid", "final"}:
            raise BenchmarkAdapterError("adapter manifest must bind every stage signature")
        for reference in signatures.values():
            _identifier(reference, "manifest signature")
        object.__setattr__(self, "recipes", MappingProxyType(recipes))
        object.__setattr__(self, "signature_refs", MappingProxyType(signatures))

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document(include_digest=False))

    def to_document(self, *, include_digest: bool = True) -> Mapping[str, object]:
        document: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-benchmark-adapter-manifest",
            "manifest_id": self.manifest_id,
            "protocol_id": self.protocol_id,
            "recipes": {
                key: recipe.to_document() for key, recipe in sorted(self.recipes.items())
            },
            "signature_refs": dict(sorted(self.signature_refs.items())),
        }
        if include_digest:
            document["manifest_digest"] = self.digest
        return document

    def validate_for(self, protocol: MatchProtocol, evidence: StageEvidence) -> None:
        if self.protocol_id != protocol.protocol_id:
            raise BenchmarkAdapterError("adapter manifest targets another protocol")
        expected = protocol.experiment_manifest["recipe_manifest_digest"]
        if self.digest != expected or evidence.recipe_manifest_digest != expected:
            raise BenchmarkAdapterError("adapter manifest is not the admitted manifest")
        if self.signature_refs[evidence.stage] != evidence.manifest_signature_ref:
            raise BenchmarkAdapterError("adapter manifest signature is not admitted")
        variants = {**dict(protocol.entrant_recipes), **dict(protocol.hybrid_recipes)}
        if set(self.recipes) != set(variants):
            raise BenchmarkAdapterError("adapter manifest does not bind every variant")
        dimensions = (
            "source_or_binary_digest",
            "prompt_digest",
            "model_digest",
            "command_profile_digest",
            "tool_digest",
            "context_digest",
            "check_policy_digest",
            "learning_policy_digest",
        )
        for variant_id, protocol_recipe in variants.items():
            recipe = self.recipes[variant_id]
            if any(getattr(recipe, name) != protocol_recipe[name] for name in dimensions):
                raise BenchmarkAdapterError("adapter recipe differs from frozen protocol")

    @classmethod
    def from_document(cls, value: Mapping[str, object]) -> "BenchmarkAdapterManifest":
        required = {
            "schema_version",
            "kind",
            "manifest_id",
            "protocol_id",
            "recipes",
            "signature_refs",
            "manifest_digest",
        }
        if (
            set(value) != required
            or value["schema_version"] != 1
            or value["kind"] != "hive-mind-benchmark-adapter-manifest"
            or not isinstance(value["recipes"], Mapping)
            or not isinstance(value["signature_refs"], Mapping)
        ):
            raise BenchmarkAdapterError("adapter manifest document has an unknown shape")
        recipes: dict[str, RecipeManifest] = {}
        for key, item in value["recipes"].items():
            if type(key) is not str or not isinstance(item, Mapping):
                raise BenchmarkAdapterError("adapter manifest recipe is invalid")
            recipes[key] = RecipeManifest.from_document(cast(Mapping[str, object], item))
        manifest = cls(
            cast(str, value["manifest_id"]),
            cast(str, value["protocol_id"]),
            recipes,
            cast(Mapping[str, str], value["signature_refs"]),
        )
        if value["manifest_digest"] != manifest.digest:
            raise BenchmarkAdapterError("adapter manifest digest mismatch")
        return manifest


def load_benchmark_adapter_manifest(path: str | Path) -> BenchmarkAdapterManifest:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkAdapterError("adapter manifest is unreadable") from exc
    if not isinstance(value, Mapping):
        raise BenchmarkAdapterError("adapter manifest root must be an object")
    return BenchmarkAdapterManifest.from_document(cast(Mapping[str, object], value))


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    operation_id: str
    experiment_id: str
    stage: str
    task_id: str
    family_id: str
    candidate_digest: str
    recipe_digest: str
    budget_digest: str
    environment_digest: str
    lease_handle: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    execution_binding_digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("experiment_id", "task_id", "family_id", "lease_handle"):
            _identifier(getattr(self, name), name)
        for name in (
            "operation_id",
            "candidate_digest",
            "recipe_digest",
            "budget_digest",
            "environment_digest",
        ):
            _sha(getattr(self, name), name)
        if self.stage not in {"original", "hybrid", "final", "ablation"}:
            raise BenchmarkAdapterError("invalid benchmark stage")
        if not self.argv:
            raise BenchmarkAdapterError("empty benchmark command")
        if any(type(part) is not str or not part or "\x00" in part for part in self.argv):
            raise BenchmarkAdapterError("benchmark command contains an invalid argument")
        environment = dict(self.environment)
        if any(type(key) is not str or type(value) is not str for key, value in environment.items()):
            raise BenchmarkAdapterError("benchmark environment must contain strings")
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "environment", MappingProxyType(environment))
        if self.execution_binding_digest is not None:
            _sha(self.execution_binding_digest, "execution binding")


@dataclass(frozen=True, slots=True)
class BenchmarkResponse:
    operation_id: str
    status: str
    result_digest: str
    receipt_digest: str
    active_seconds: float | None
    wall_seconds: float | None
    usage_units: float | None
    provider_cost: float | None
    failure_category: str | None = None

    def __post_init__(self) -> None:
        for name in ("operation_id", "result_digest", "receipt_digest"):
            _sha(getattr(self, name), name)
        if self.status not in {
            "success",
            "failure",
            "timeout",
            "budget_exhausted",
            "no_change",
            "blocked",
            "inconclusive",
        }:
            raise BenchmarkAdapterError("invalid broker response status")
        for name in ("active_seconds", "wall_seconds", "usage_units", "provider_cost"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
            ):
                raise BenchmarkAdapterError(f"{name} must be nonnegative or unknown")
        if self.status != "success" and not self.failure_category:
            raise BenchmarkAdapterError("non-success response needs a failure category")


class BenchmarkExecutionBroker(Protocol):
    def inspect(self, operation_id: str) -> BenchmarkResponse | None: ...
    def execute(self, request: BenchmarkRequest) -> BenchmarkResponse: ...


class PinnedRecipeAdapter:
    def __init__(self, manifest: RecipeManifest) -> None:
        self.manifest = manifest

    def request(
        self,
        *,
        experiment_id: str,
        stage: str,
        task_id: str,
        family_id: str,
        candidate_digest: str,
        budget_digest: str,
        environment_digest: str,
        lease_handle: str,
        execution_binding_digest: str | None = None,
    ) -> BenchmarkRequest:
        identity = {
            "experiment_id": experiment_id,
            "stage": stage,
            "task_id": task_id,
            "family_id": family_id,
            "candidate_digest": candidate_digest,
            "recipe_digest": self.manifest.digest,
            "budget_digest": budget_digest,
            "environment_digest": environment_digest,
        }
        if execution_binding_digest is not None:
            identity["execution_binding_digest"] = execution_binding_digest
        operation_id = canonical_digest(identity)
        return BenchmarkRequest(
            operation_id=operation_id,
            experiment_id=experiment_id,
            stage=stage,
            task_id=task_id,
            family_id=family_id,
            candidate_digest=candidate_digest,
            recipe_digest=self.manifest.digest,
            budget_digest=budget_digest,
            environment_digest=environment_digest,
            lease_handle=lease_handle,
            argv=self.manifest.argv,
            environment=dict(self.manifest.environment),
            execution_binding_digest=execution_binding_digest,
        )

    def run(
        self, request: BenchmarkRequest, broker: BenchmarkExecutionBroker
    ) -> BenchmarkResponse:
        if (
            request.recipe_digest != self.manifest.digest
            or request.argv != self.manifest.argv
            or dict(request.environment) != dict(self.manifest.environment)
        ):
            raise BenchmarkAdapterError("request diverges from pinned recipe")
        existing = broker.inspect(request.operation_id)
        response = existing if existing is not None else broker.execute(request)
        if response.operation_id != request.operation_id:
            raise BenchmarkAdapterError("broker returned a cross-operation receipt")
        return response


@dataclass(frozen=True, slots=True)
class AdmittedBenchmarkInvocation:
    """One deterministic adapter request bound to registry-owned evidence."""

    request: BenchmarkRequest
    variant_id: str
    admission_digest: str
    stage_evidence_digest: str
    lease_digest: str
    variant_seal_digest: str
    repetition: int
    seed: int

    def __post_init__(self) -> None:
        _identifier(self.variant_id, "variant")
        for name in (
            "admission_digest",
            "stage_evidence_digest",
            "lease_digest",
            "variant_seal_digest",
        ):
            _sha(getattr(self, name), name)
        if type(self.repetition) is not int or self.repetition < 0:
            raise BenchmarkAdapterError("repetition must be a nonnegative integer")
        if type(self.seed) is not int or self.seed < 0:
            raise BenchmarkAdapterError("seed must be a nonnegative integer")

    @property
    def execution_binding_digest(self) -> str:
        return canonical_digest(
            {
                "admission_digest": self.admission_digest,
                "stage_evidence_digest": self.stage_evidence_digest,
                "lease_digest": self.lease_digest,
                "variant_seal_digest": self.variant_seal_digest,
                "repetition": self.repetition,
                "seed": self.seed,
            }
        )


class AdmittedBenchmarkRunner:
    """Generate and execute commands only from a live N02 registry admission."""

    def __init__(
        self,
        protocol_path: str | Path,
        manifest: BenchmarkAdapterManifest,
        registry: AdmissionRegistry,
        admission_handle: object,
        broker: BenchmarkExecutionBroker,
    ) -> None:
        # Validation order is intentional: the checked-in OPEN document fails
        # before an untrusted manifest or any registry/broker callback is used.
        self.protocol = load_match_protocol(protocol_path)
        self.manifest = manifest
        self.registry = registry
        self.admission_handle = admission_handle
        self.broker = broker

    @staticmethod
    def _variant_seal(
        evidence: StageEvidence,
        history: tuple[VariantSeal, ...],
        variant_id: str,
    ) -> VariantSeal:
        matches = tuple(
            seal
            for seal in history
            if seal.variant_id == variant_id and seal.stage == evidence.stage
        )
        if len(matches) != 1:
            raise BenchmarkAdapterError(
                "execution requires exactly one admitted stage candidate seal"
            )
        return matches[0]

    def plan(
        self,
        *,
        stage: str,
        variant_id: str,
        task_id: str,
        repetition: int = 0,
    ) -> AdmittedBenchmarkInvocation:
        snapshot = resolve_execution_admission(
            self.protocol,
            registry=self.registry,
            admission_handle=self.admission_handle,
            stage=stage,
        )
        evidence = snapshot.stage_evidence
        self.manifest.validate_for(self.protocol, evidence)
        tasks = tuple(task for task in evidence.tasks if task.task_id == task_id)
        if len(tasks) != 1:
            raise BenchmarkAdapterError("task is not uniquely admitted for this stage")
        task = tasks[0]
        if type(repetition) is not int or repetition < 0 or repetition >= evidence.repetitions:
            raise BenchmarkAdapterError("repetition is outside the admitted task shape")
        if len(task.repetition_seeds) != evidence.repetitions:
            raise BenchmarkAdapterError("task seeds differ from the admitted shape")
        if variant_id not in self.manifest.recipes:
            raise BenchmarkAdapterError("variant is absent from the adapter manifest")
        protocol_recipe = self.protocol.recipe(variant_id)
        if protocol_recipe is None:
            raise BenchmarkAdapterError("variant is absent from the frozen protocol")
        seal = self._variant_seal(evidence, snapshot.seal_history, variant_id)
        if seal.recipe_digest != self.protocol.recipe_digest(variant_id, protocol_recipe):
            raise BenchmarkAdapterError("candidate seal targets another recipe")
        binding = {
            "admission_digest": snapshot.admission_digest,
            "stage_evidence_digest": evidence.evidence_digest,
            "lease_digest": snapshot.lease.lease_digest,
            "variant_seal_digest": seal.seal_digest,
            "repetition": repetition,
            "seed": task.repetition_seeds[repetition],
        }
        binding_digest = canonical_digest(binding)
        adapter = PinnedRecipeAdapter(self.manifest.recipes[variant_id])
        request = adapter.request(
            experiment_id=self.protocol.protocol_id,
            stage=stage,
            task_id=task.task_id,
            family_id=task.family_id,
            candidate_digest=seal.candidate_digest,
            budget_digest=snapshot.lease.budget_digest,
            environment_digest=evidence.evidence_digest,
            lease_handle=snapshot.lease.lease_digest,
            execution_binding_digest=binding_digest,
        )
        return AdmittedBenchmarkInvocation(
            request,
            variant_id,
            snapshot.admission_digest,
            evidence.evidence_digest,
            snapshot.lease.lease_digest,
            seal.seal_digest,
            repetition,
            task.repetition_seeds[repetition],
        )

    def execute(self, invocation: AdmittedBenchmarkInvocation) -> BenchmarkResponse:
        # Re-plan the *entire* lane from the live registry immediately before the
        # broker boundary.  Checking only the seal leaves task/family, seed,
        # budget, environment and operation-id fields forgeable on a manually
        # constructed invocation.
        expected = self.plan(
            stage=invocation.request.stage,
            variant_id=invocation.variant_id,
            task_id=invocation.request.task_id,
            repetition=invocation.repetition,
        )
        if invocation != expected:
            raise BenchmarkAdapterError(
                "execution request differs from the live admitted lane"
            )
        recipe = self.manifest.recipes[invocation.variant_id]
        return PinnedRecipeAdapter(recipe).run(expected.request, self.broker)

    def run(
        self,
        *,
        stage: str,
        variant_id: str,
        task_id: str,
        repetition: int = 0,
    ) -> BenchmarkResponse:
        return self.execute(
            self.plan(
                stage=stage,
                variant_id=variant_id,
                task_id=task_id,
                repetition=repetition,
            )
        )
