"""Self-healing runtime for bounded kernel mission recovery.

Composes the desired-state reconciler; applying a repair is always an explicit,
authority-checked handler call.

Fault classification stays entirely in :class:`~.reconciler.DesiredStateReconciler`.
This module adds only the three things the planner deliberately refuses to own:
a provider failover chain that preserves contract identity, a semantic
no-progress ledger whose counts feed the planner's existing quarantine bound,
and a handler registry whose dispatch is gated by the authority actually granted
to the pass.  Nothing here executes an effect on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..model_provider import (
    MissingModelCredential,
    ModelRequest,
    ModelResponse,
    ModelTransportError,
)
from .canonical import canonical_digest
from .events import KernelEvent
from .reconciler import (
    DesiredStateReconciler,
    ObservedState,
    ReconciliationPolicy,
    ReconciliationResult,
    RepairAction,
    RepairKind,
)
from .store import KernelStore

_EPOCH = "1970-01-01T00:00:00Z"
_SELF_HEALING_EVENT_TYPE = "self_healing.pass"


class SelfHealingError(RuntimeError):
    """Base error for the self-healing runtime."""


class AuthorityViolationError(SelfHealingError):
    """A repair required authority outside the granted scope.

    The runtime itself never widens authority: an out-of-scope proposal is
    escalated, not executed.  Handlers that discover a narrower authority than
    the planner assumed raise this so the failure is legible in the receipt.
    """


class FailoverExhaustedError(SelfHealingError):
    """Every provider in the chain failed at the transport layer."""

    def __init__(self, message: str, attempts: tuple["FailoverAttempt", ...]) -> None:
        super().__init__(message)
        self.attempts = tuple(attempts)


class FailoverProvider(Protocol):
    """Duck-typed subset of :class:`~..model_provider.ModelProvider`."""

    def complete(self, request: ModelRequest) -> ModelResponse: ...

    @property
    def credential_reference(self) -> str: ...


def request_identity(request: ModelRequest) -> str:
    """Return the contract identity digest of a provider-neutral request."""

    return canonical_digest(
        {
            "corrective_message": request.corrective_message,
            "system": request.system,
            "user": request.user,
        }
    )


@dataclass(frozen=True, slots=True)
class FailoverAttempt:
    """One provider attempt, recorded without any secret material."""

    provider_index: int
    credential_reference: str
    outcome: str
    detail: str

    def to_document(self) -> dict[str, Any]:
        return {
            "provider_index": self.provider_index,
            "credential_reference": self.credential_reference,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class FailoverReceipt:
    """Evidence that failover changed the transport, never the contract."""

    request_digest: str
    response_digest: str
    attempts: tuple[FailoverAttempt, ...]
    served_by: int

    def to_document(self) -> dict[str, Any]:
        return {
            "request_digest": self.request_digest,
            "response_digest": self.response_digest,
            "attempts": [attempt.to_document() for attempt in self.attempts],
            "served_by": self.served_by,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


class ProviderFailoverChain:
    """Ordered provider chain that fails over on transport faults only."""

    def __init__(self, providers: Sequence[FailoverProvider]) -> None:
        chain = tuple(providers)
        if not chain:
            raise ValueError("failover chain requires at least one provider")
        self.providers = chain

    def complete(self, request: ModelRequest) -> tuple[ModelResponse, FailoverReceipt]:
        """Return the first successful response plus its identity receipt.

        The request digest is computed once, before any attempt: every provider
        receives the exact same immutable :class:`ModelRequest`, so the contract
        identity cannot drift while the transport does.  A
        :class:`ModelResponseError` is a semantic failure and propagates
        unchanged -- it belongs on the no-progress ledger, not in a silent
        provider switch.
        """

        request_digest = request_identity(request)
        attempts: list[FailoverAttempt] = []
        for index, provider in enumerate(self.providers):
            reference = provider.credential_reference
            try:
                response = provider.complete(request)
            except ModelTransportError as error:
                attempts.append(
                    FailoverAttempt(index, reference, "transport-error", str(error))
                )
                continue
            except MissingModelCredential as error:
                attempts.append(
                    FailoverAttempt(index, reference, "missing-credential", str(error))
                )
                continue
            attempts.append(FailoverAttempt(index, reference, "success", ""))
            receipt = FailoverReceipt(
                request_digest=request_digest,
                response_digest=canonical_digest({"content": response.content}),
                attempts=tuple(attempts),
                served_by=index,
            )
            return response, receipt
        raise FailoverExhaustedError(
            f"provider failover exhausted after {len(attempts)} attempts",
            tuple(attempts),
        )


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """Persisted no-progress position for one mission."""

    signature: str | None
    no_progress_count: int


class ProgressLedger:
    """Pure signature comparator; the caller persists the returned counts."""

    def advance(
        self, previous: ProgressUpdate, current_signature: str | None
    ) -> ProgressUpdate:
        if current_signature is not None and current_signature == previous.signature:
            return ProgressUpdate(current_signature, previous.no_progress_count + 1)
        return ProgressUpdate(current_signature, 0)


RepairHandler = Callable[[RepairAction], Any]


class RepairHandlerRegistry:
    """Explicit, single-binding map from repair kind to its effect handler."""

    def __init__(self) -> None:
        self._handlers: dict[RepairKind, RepairHandler] = {}

    def register(self, kind: RepairKind, handler: RepairHandler) -> None:
        if kind in self._handlers:
            raise ValueError(f"handler already registered: {kind.value}")
        self._handlers[kind] = handler

    def handlers(self) -> dict[RepairKind, RepairHandler]:
        return dict(self._handlers)


@dataclass(frozen=True, slots=True)
class HealingOutcome:
    """What one pass actually did with one proposal."""

    action_id: str
    kind: str
    status: str
    reason: str

    def to_document(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class HealingReceipt:
    """Deterministic evidence for one self-healing pass."""

    mission_id: str
    observed_digest: str
    desired_digest: str
    outcomes: tuple[HealingOutcome, ...]
    quarantined: bool
    escalations: tuple[str, ...]
    progress: ProgressUpdate

    def to_document(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "observed_digest": self.observed_digest,
            "desired_digest": self.desired_digest,
            "outcomes": [outcome.to_document() for outcome in self.outcomes],
            "quarantined": self.quarantined,
            "escalations": list(self.escalations),
            "progress": {
                "signature": self.progress.signature,
                "no_progress_count": self.progress.no_progress_count,
            },
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


class SelfHealingRuntime:
    """Applies reconciler proposals through registered, authority-bound handlers."""

    def __init__(
        self,
        registry: RepairHandlerRegistry,
        *,
        policy: ReconciliationPolicy | None = None,
        reconciler: DesiredStateReconciler | None = None,
        store: KernelStore | None = None,
        actor_id: str = "self-healing-runtime",
    ) -> None:
        self.registry = registry
        self.reconciler = reconciler or DesiredStateReconciler(policy)
        self.store = store
        self.actor_id = actor_id

    def heal(
        self,
        observed: ObservedState | Mapping[str, Any],
        *,
        now: float,
        granted_authority: Sequence[str] = (),
    ) -> HealingReceipt:
        """Reconcile once, then apply only what is registered and authorised."""

        result: ReconciliationResult = self.reconciler.reconcile(observed, now=now)
        handlers = self.registry.handlers()
        granted = set(str(item) for item in granted_authority)
        outcomes: list[HealingOutcome] = []
        escalations: list[str] = []
        for action in result.actions:
            handler = handlers.get(action.kind)
            if handler is None:
                outcomes.append(
                    HealingOutcome(
                        action.action_id,
                        action.kind.value,
                        "skipped-no-handler",
                        "no handler registered; proposal retained",
                    )
                )
                continue
            if not set(action.authority_scope) <= granted:
                escalations.append(action.action_id)
                outcomes.append(
                    HealingOutcome(
                        action.action_id,
                        action.kind.value,
                        "escalated-authority",
                        "repair scope exceeds the authority granted to this pass",
                    )
                )
                continue
            try:
                handler(action)
            except Exception as error:
                raise SelfHealingError(
                    f"repair handler failed: {action.action_id}"
                ) from error
            outcomes.append(
                HealingOutcome(
                    action.action_id,
                    action.kind.value,
                    "applied",
                    action.reason,
                )
            )

        progress = ProgressLedger().advance(
            ProgressUpdate(
                result.observed.progress_signature, result.observed.no_progress_count
            ),
            result.desired.desired_digest
            if result.actions
            else result.observed.progress_signature,
        )
        receipt = HealingReceipt(
            mission_id=result.observed.mission_id,
            observed_digest=result.observed.digest,
            desired_digest=result.desired.desired_digest,
            outcomes=tuple(outcomes),
            quarantined=result.quarantined,
            escalations=tuple(escalations),
            progress=progress,
        )
        if self.store is not None:
            self._append_pass(receipt)
        return receipt

    def _append_pass(self, receipt: HealingReceipt) -> None:
        """Record one durable, replay-safe healing-pass fact."""

        store = self.store
        if store is None:
            return
        rows = store.events()
        previous_digest = str(rows[-1]["digest"]) if rows else None
        event = KernelEvent(
            event_id=f"self-healing:{receipt.mission_id}:{receipt.digest}",
            mission_id=receipt.mission_id,
            event_type=_SELF_HEALING_EVENT_TYPE,
            actor_id=self.actor_id,
            occurred_at=_EPOCH,
            payload=receipt.to_document(),
            actor_role="steward",
            previous_digest=previous_digest,
        )
        store.append(event, idempotency_key=receipt.digest)


__all__ = [
    "AuthorityViolationError",
    "FailoverAttempt",
    "FailoverExhaustedError",
    "FailoverProvider",
    "FailoverReceipt",
    "HealingOutcome",
    "HealingReceipt",
    "ProgressLedger",
    "ProgressUpdate",
    "ProviderFailoverChain",
    "RepairHandler",
    "RepairHandlerRegistry",
    "SelfHealingError",
    "SelfHealingRuntime",
    "request_identity",
]
