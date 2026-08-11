"""Effect gateway with strict capability binding and an optional durable outbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .authority import AuthorityDenied, CapabilityToken
from .canonical import canonical_digest
from .contracts import EffectIntent, EffectReceipt

if TYPE_CHECKING:
    from .store import KernelStore


@dataclass(frozen=True, slots=True)
class EffectResult:
    intent_digest: str
    receipt_digest: str
    status: str


def validate_capability_token(intent: EffectIntent, token: CapabilityToken) -> None:
    """Require a token to bind cryptographically to the complete intent target."""

    expected_token_digest = canonical_digest(
        {
            "envelope": token.envelope_digest,
            "action": token.action,
            "target": token.target,
        }
    )
    if (
        token.token_digest != expected_token_digest
        or token.envelope_digest != intent.authority_envelope_digest
        or token.action != intent.action
        or token.target != intent.target
    ):
        raise AuthorityDenied("capability token does not bind this intent")


def build_effect_receipt(
    intent: EffectIntent,
    *,
    adapter_identity: str,
    adapter_version: str,
    started_at: str,
    ended_at: str,
    status: str = "SUCCEEDED",
    produced_identifiers: tuple[str, ...] = (),
    observed_precondition_digest: str | None = None,
    postcondition_digest: str | None = None,
    retry_of: str | None = None,
    rollback_receipt: str | None = None,
) -> EffectReceipt:
    """Build a schema-valid receipt without retaining parameters or secrets."""

    return EffectReceipt(
        intent.intent_digest,
        started_at,
        ended_at,
        adapter_identity,
        adapter_version,
        observed_precondition_digest
        or canonical_digest(intent.expected_preconditions),
        status,
        None,
        None,
        produced_identifiers,
        postcondition_digest
        or canonical_digest({"intent": intent.intent_digest, "status": status}),
        retry_of,
        rollback_receipt,
    )


class EffectGateway:
    """An adapter registry; duplicate intents return their prior local receipt."""

    def __init__(self, store: KernelStore | None = None) -> None:
        self._adapters: dict[str, Callable[[EffectIntent], None]] = {}
        self._adapter_versions: dict[str, str] = {}
        self._receipts: dict[str, EffectResult] = {}
        self._store = store

    def register_adapter(
        self,
        name: str,
        adapter: Callable[[EffectIntent], None],
        *,
        version: str = "1",
    ) -> None:
        if not name or name in self._adapters:
            raise ValueError("adapter name must be new and non-empty")
        if not version or not version.strip():
            raise ValueError("adapter version must be non-empty")
        self._adapters[name] = adapter
        self._adapter_versions[name] = version

    def execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult:
        validate_capability_token(intent, token)
        if self._store is not None:
            # Lazy import keeps the original in-memory gateway dependency-free and
            # avoids a module cycle between the gateway and durable adapter.
            from .effect_outbox import DurableEffectOutbox

            return DurableEffectOutbox(
                self._store,
                adapters=self._adapters,
                adapter_versions=self._adapter_versions,
            ).execute(intent, token)
        previous = self._receipts.get(intent.idempotency_key)
        if previous is not None:
            return previous
        adapter = self._adapters.get(intent.target_adapter)
        if adapter is None:
            raise AuthorityDenied("adapter is not registered")
        adapter(intent)
        result = EffectResult(intent.intent_digest, canonical_digest({"intent": intent.intent_digest, "status": "SUCCEEDED"}), "SUCCEEDED")
        self._receipts[intent.idempotency_key] = result
        return result
