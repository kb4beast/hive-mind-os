"""Durable, fail-closed delivery for kernel effect intents.

The outbox deliberately provides local guarantees only. It records an intent
before invoking an adapter, uses the intent idempotency key for retries, and
turns every interrupted or ambiguous delivery into an explicit reconciliation
obligation instead of retrying a possibly completed external effect.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from .authority import AuthorityDenied, AuthorityRegistry, CapabilityToken
from .canonical import canonical_bytes, canonical_digest
from .contracts import EffectIntent, EffectReceipt
from .effects import (
    EffectResult,
    build_effect_receipt,
    validate_capability_token,
)
from .store import KernelIntegrityError, KernelStore


class EffectReconciliationRequired(RuntimeError):
    """The physical outcome is unknown and requires an explicit repair witness."""


Adapter = Callable[[EffectIntent], object]


def _time() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class DurableEffectOutbox:
    """SQLite-backed effect intent, delivery, receipt, and repair boundary.

    An outbox requires an ``authority`` registry and re-derives every token
    through live issuance state before it records or delivers anything. Direct
    construction reaches the same boundary a gateway applies; without a registry
    every enqueue and execution is denied.
    """

    def __init__(
        self,
        store: KernelStore,
        *,
        adapters: Mapping[str, Adapter] | None = None,
        adapter_versions: Mapping[str, str] | None = None,
        adapter_hosts: Mapping[str, tuple[str, ...]] | None = None,
        authority: AuthorityRegistry | None = None,
        clock: Callable[[], str] = _time,
    ) -> None:
        self.store = store
        self.adapters = dict(adapters or {})
        self.adapter_versions = dict(adapter_versions or {})
        self.adapter_hosts = dict(adapter_hosts or {})
        self.authority = authority
        self.clock = clock

    def _validate(self, intent: EffectIntent, token: CapabilityToken) -> None:
        """The one boundary every durable entry point crosses."""

        validate_capability_token(
            intent,
            token,
            authority=self.authority,
            now=self.clock(),
            network_hosts=self.adapter_hosts.get(intent.target_adapter, ()),
        )

    def enqueue(self, intent: EffectIntent, token: CapabilityToken) -> dict[str, Any]:
        """Validate and persist an intent without invoking an adapter."""

        self._validate(intent, token)
        if intent.target_adapter not in self.adapters:
            raise AuthorityDenied("adapter is not registered")
        return self.store.enqueue_effect(
            idempotency_key=intent.idempotency_key,
            intent_digest=intent.intent_digest,
            intent=intent.to_document(),
            recorded_at=self.clock(),
        )

    @staticmethod
    def _result(entry: Mapping[str, Any]) -> EffectResult:
        receipt_digest = entry.get("receipt_digest")
        if not isinstance(receipt_digest, str) or not receipt_digest:
            raise KernelIntegrityError("receipt-recorded effect has no receipt digest")
        return EffectResult(str(entry["intent_digest"]), receipt_digest, "SUCCEEDED")

    def execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult:
        """Deliver one effect, never retrying an ambiguous physical outcome."""

        self._validate(intent, token)
        adapter = self.adapters.get(intent.target_adapter)
        if adapter is None:
            raise AuthorityDenied("adapter is not registered")
        entry = self.store.effect_entry(intent_digest=intent.intent_digest)
        if entry is None:
            entry = self.enqueue(intent, token)
        elif entry.get("intent_json") != canonical_bytes(intent.to_document()).decode("utf-8"):
            # The canonical JSON comparison keeps malformed legacy rows from
            # being interpreted as a matching idempotent retry.
            raise KernelIntegrityError("durable intent does not match requested intent")
        state = str(entry["state"])
        if state == "receipt_recorded":
            return self._result(entry)
        if state == "reconciliation_required":
            raise EffectReconciliationRequired(
                f"effect {intent.intent_digest} requires reconciliation"
            )
        if state == "executing":
            self.store.mark_effect_reconciliation_required(
                intent_digest=intent.intent_digest,
                reason="previous delivery was interrupted before receipt",
                recorded_at=self.clock(),
            )
            raise EffectReconciliationRequired(
                f"effect {intent.intent_digest} was interrupted before receipt"
            )
        entry = self.store.begin_effect(
            intent_digest=intent.intent_digest, recorded_at=self.clock()
        )
        if str(entry["state"]) != "executing":
            if str(entry["state"]) == "receipt_recorded":
                return self._result(entry)
            raise EffectReconciliationRequired(
                f"effect {intent.intent_digest} is not deliverable: {entry['state']}"
            )

        started_at = self.clock()
        try:
            raw_result = adapter(intent)
        except Exception as error:
            self.store.mark_effect_reconciliation_required(
                intent_digest=intent.intent_digest,
                reason="adapter failed after durable execution began",
                recorded_at=self.clock(),
                evidence={"error_type": type(error).__name__},
            )
            raise EffectReconciliationRequired(
                f"effect {intent.intent_digest} has an ambiguous adapter outcome"
            ) from error

        if isinstance(raw_result, EffectReceipt):
            receipt = raw_result
            if receipt.intent_digest != intent.intent_digest:
                raise KernelIntegrityError("adapter receipt is bound to another intent")
        else:
            produced = ()
            postcondition = None
            if isinstance(raw_result, Mapping):
                values = raw_result.get("produced_identifiers", ())
                if isinstance(values, (list, tuple)) and all(isinstance(value, str) for value in values):
                    produced = tuple(values)
                postcondition = raw_result.get("postcondition_digest")
                if not isinstance(postcondition, str):
                    postcondition = None
            receipt = build_effect_receipt(
                intent,
                adapter_identity=intent.target_adapter,
                adapter_version=self.adapter_versions.get(intent.target_adapter, "1"),
                started_at=started_at,
                ended_at=self.clock(),
                produced_identifiers=produced,
                postcondition_digest=postcondition,
            )
        receipt_digest = canonical_digest(receipt.to_document())
        try:
            entry = self.store.record_effect_receipt(
                intent_digest=intent.intent_digest,
                receipt_digest=receipt_digest,
                receipt=receipt.to_document(),
                recorded_at=self.clock(),
            )
        except Exception as error:
            self.store.mark_effect_reconciliation_required(
                intent_digest=intent.intent_digest,
                reason="physical effect completed but receipt append failed",
                recorded_at=self.clock(),
                evidence={"error_type": type(error).__name__},
            )
            raise EffectReconciliationRequired(
                f"effect {intent.intent_digest} needs receipt reconciliation"
            ) from error
        return self._result(entry)

    def reconcile(
        self,
        intent_digest: str,
        receipt: EffectReceipt,
        *,
        token: CapabilityToken,
        evidence: Mapping[str, Any] | None = None,
    ) -> EffectResult:
        """Adopt an explicit receipt for an ambiguous effect without re-executing."""

        if receipt.intent_digest != intent_digest:
            raise KernelIntegrityError("reconciliation receipt is bound to another intent")
        entry = self.store.effect_entry(intent_digest=intent_digest)
        if entry is None:
            raise KernelIntegrityError("cannot reconcile an unknown effect intent")
        try:
            stored_intent = cast(
                EffectIntent,
                EffectIntent.from_document(json.loads(str(entry["intent_json"]))),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise KernelIntegrityError("durable effect intent is corrupt") from error
        self._validate(stored_intent, token)
        receipt_digest = canonical_digest(receipt.to_document())
        entry = self.store.record_effect_receipt(
            intent_digest=intent_digest,
            receipt_digest=receipt_digest,
            receipt=receipt.to_document(),
            recorded_at=self.clock(),
        )
        if evidence:
            self.store.mark_effect_reconciliation_required(
                intent_digest=intent_digest,
                reason="receipt adopted from explicit authorized reconciliation witness",
                recorded_at=self.clock(),
                evidence=evidence,
                state="reconciled",
            )
            # The append-only reconciliation record is evidence; the receipt
            # state remains authoritative and already records adoption.
        return self._result(entry)

    def recover(self) -> list[str]:
        """Convert stale executing entries into repair obligations after restart."""

        return self.store.recover_effects(recorded_at=self.clock())

    def status(self, intent_digest: str) -> Mapping[str, Any] | None:
        return self.store.effect_entry(intent_digest=intent_digest)


# Short aliases make the boundary discoverable without weakening the explicit name.
EffectOutbox = DurableEffectOutbox
UnknownEffectOutcome = EffectReconciliationRequired
