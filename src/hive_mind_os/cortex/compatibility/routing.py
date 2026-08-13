"""Single-authority routing and reversible legacy rollback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from .models import AdapterMode, CompatibilityError
from .parity import ParityVerdict

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class RouteDecision:
    active: AdapterMode
    qualified: bool
    rollback_ref: str


class RollbackRouter(Generic[_T]):
    """Choose one owner for an operation and retain a route back to legacy."""

    def __init__(
        self,
        legacy: Callable[..., _T],
        canonical: Callable[..., _T] | None = None,
        *,
        rollback_ref: str = "route:legacy",
    ) -> None:
        if not callable(legacy):
            raise ValueError("legacy route is required")
        if not rollback_ref.strip():
            raise ValueError("rollback_ref is required")
        self._legacy = legacy
        self._canonical = canonical
        self._rollback_ref = rollback_ref
        self._active = AdapterMode.LEGACY
        self._qualified = False
        self._history: list[RouteDecision] = [self.decision]

    @property
    def decision(self) -> RouteDecision:
        return RouteDecision(self._active, self._qualified, self._rollback_ref)

    @property
    def history(self) -> tuple[RouteDecision, ...]:
        return tuple(self._history)

    def qualify(self, verdict: ParityVerdict) -> RouteDecision:
        if not verdict.matched:
            raise CompatibilityError("canonical route requires accepted behavior and evidence parity")
        if self._canonical is None:
            raise CompatibilityError("canonical route is not registered")
        self._qualified = True
        self._history.append(self.decision)
        return self.decision

    def route(self, mode: AdapterMode) -> RouteDecision:
        selected = AdapterMode(mode)
        if selected is AdapterMode.CANONICAL and not self._qualified:
            raise CompatibilityError("canonical route is blocked until parity qualification")
        if selected is AdapterMode.SHADOW:
            raise CompatibilityError("shadow is a probe mode, not an authority route")
        if selected is AdapterMode.CANONICAL and self._canonical is None:
            raise CompatibilityError("canonical route is not registered")
        self._active = selected
        self._history.append(self.decision)
        return self.decision

    def rollback(self) -> RouteDecision:
        self._active = AdapterMode.LEGACY
        self._history.append(self.decision)
        return self.decision

    def invoke(self, *args: Any, **kwargs: Any) -> _T:
        """Invoke one route exactly once; no shadow call is made."""

        owner = self._legacy if self._active is AdapterMode.LEGACY else self._canonical
        if owner is None:
            raise CompatibilityError("selected authority route is unavailable")
        return owner(*args, **kwargs)
