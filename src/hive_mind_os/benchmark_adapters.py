"""Fail-closed adapters for N30 whole-OS benchmark execution.

Adapters materialize pinned recipes into broker requests.  They never invoke a
shell, select credentials, or import a comparator's control logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol

from .campaign_metrics import canonical_digest


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
        return canonical_digest(
            {
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
        )


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
    ) -> BenchmarkRequest:
        operation_id = canonical_digest(
            {
                "experiment_id": experiment_id,
                "stage": stage,
                "task_id": task_id,
                "family_id": family_id,
                "candidate_digest": candidate_digest,
                "recipe_digest": self.manifest.digest,
                "budget_digest": budget_digest,
                "environment_digest": environment_digest,
            }
        )
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
