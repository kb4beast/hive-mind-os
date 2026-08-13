"""Effect gateway with strict capability binding and an optional durable outbox."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Callable

from .authority import AuthorityDenied, AuthorityRegistry, CapabilityToken
from .canonical import canonical_digest
from .contracts import ConstraintEnvelope, EffectIntent, EffectReceipt

if TYPE_CHECKING:
    from .store import KernelStore


@dataclass(frozen=True, slots=True)
class EffectResult:
    intent_digest: str
    receipt_digest: str
    status: str


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def intent_seal(intent: EffectIntent) -> str:
    """Pure seal over every field of an intent except the seal itself."""

    document = intent.to_document()
    document.pop("intent_digest")
    return canonical_digest(document)


def sealed_intent(intent: EffectIntent) -> EffectIntent:
    """Return the same intent carrying the digest its fields imply."""

    return replace(intent, intent_digest=intent_seal(intent))


def _admitted_envelope(authority: AuthorityRegistry, digest: str) -> ConstraintEnvelope:
    """Read the admitted envelope behind an authorized digest, or fail closed."""

    envelope = authority._envelopes.get(digest)
    if envelope is None:
        raise AuthorityDenied("authority envelope is unavailable")
    return envelope


def validate_capability_token(
    intent: EffectIntent,
    token: CapabilityToken,
    *,
    authority: AuthorityRegistry | None = None,
    now: str | None = None,
    network_hosts: tuple[str, ...] = (),
) -> None:
    """Bind a token to an intent and, given an issuer, to live authority state."""

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
    if authority is None:
        if network_hosts:
            raise AuthorityDenied("a network effect requires an authority-bound gateway")
        return
    if intent.intent_digest != intent_seal(intent):
        raise AuthorityDenied("intent digest does not seal this intent")
    issued = authority.authorize(
        token.envelope_digest, token.action, token.target, now=now or _now()
    )
    if issued != token:
        raise AuthorityDenied("capability token was not issued by this authority")
    if network_hosts:
        envelope = _admitted_envelope(authority, token.envelope_digest)
        outside = sorted(set(network_hosts) - set(envelope.network_allowlist))
        if outside:
            raise AuthorityDenied(
                "effect reaches a host outside the network allowlist: "
                + ", ".join(outside)
            )


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
    """An adapter registry; duplicate intents return their prior local receipt.

    A gateway built with an ``authority`` registry verifies every token against
    live issuance state -- registration, expiry, revocation and scope -- plus the
    intent seal and the envelope's network allowlist, before any adapter runs. A
    gateway built without one can only bind a token to its intent, so an issuer
    should be supplied wherever the registry that minted the token is in hand.
    """

    def __init__(
        self,
        store: KernelStore | None = None,
        *,
        authority: AuthorityRegistry | None = None,
        clock: Callable[[], str] = _now,
    ) -> None:
        self._adapters: dict[str, Callable[[EffectIntent], object]] = {}
        self._adapter_versions: dict[str, str] = {}
        self._adapter_hosts: dict[str, tuple[str, ...]] = {}
        self._receipts: dict[str, EffectResult] = {}
        self._store = store
        self._authority = authority
        self._clock = clock

    def register_adapter(
        self,
        name: str,
        adapter: Callable[[EffectIntent], object],
        *,
        version: str = "1",
        network_hosts: tuple[str, ...] = (),
    ) -> None:
        if not name or name in self._adapters:
            raise ValueError("adapter name must be new and non-empty")
        if not version or not version.strip():
            raise ValueError("adapter version must be non-empty")
        self._adapters[name] = adapter
        self._adapter_versions[name] = version
        self._adapter_hosts[name] = tuple(network_hosts)

    def execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult:
        validate_capability_token(
            intent,
            token,
            authority=self._authority,
            now=self._clock(),
            network_hosts=self._adapter_hosts.get(intent.target_adapter, ()),
        )
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
