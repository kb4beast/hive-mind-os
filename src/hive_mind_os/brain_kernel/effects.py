"""Local effect gateway that refuses direct execution without a capability token."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .authority import AuthorityDenied, CapabilityToken
from .canonical import canonical_digest
from .contracts import EffectIntent


@dataclass(frozen=True, slots=True)
class EffectResult:
    intent_digest: str
    receipt_digest: str
    status: str


class EffectGateway:
    """An adapter registry; duplicate intents return their prior local receipt."""

    def __init__(self) -> None:
        self._adapters: dict[str, Callable[[EffectIntent], None]] = {}
        self._receipts: dict[str, EffectResult] = {}

    def register_adapter(self, name: str, adapter: Callable[[EffectIntent], None]) -> None:
        if not name or name in self._adapters:
            raise ValueError("adapter name must be new and non-empty")
        self._adapters[name] = adapter

    def execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult:
        if token.envelope_digest != intent.authority_envelope_digest or token.action != intent.action or token.target != intent.target:
            raise AuthorityDenied("capability token does not bind this intent")
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
