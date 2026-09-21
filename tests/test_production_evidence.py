"""Executable controls for ADR-092 production evidence verification.

Real Ed25519 signatures are required. This module imports ``cryptography`` directly, so a
missing dependency is an import ERROR, never a skip. The keys below are clearly synthetic,
generated per test and never persisted; they prove the implementation, not any custody.

ADR-092's separately reviewed qualification contract admits this exact module/provider
pair. Missing or wrong distribution/loaded-provider versions fail discovery. Install
``requirements/production-evidence-crypto.txt`` with binary-only hash checking.
"""

import base64
import contextvars
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from dataclasses import asdict, replace
from importlib.metadata import version
from itertools import count
from pathlib import Path

import cryptography
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from hive_mind_os.brain_kernel.canonical import canonical_digest as kernel_digest
from hive_mind_os.brain_kernel.promotion_auth import (
    Ed25519SignatureVerifier,
    PrincipalBinding,
    PromotionAuthenticationError,
)
from hive_mind_os.pilot_orchestration import (
    PilotExecutionBlocker,
    PilotExecutionError,
    WholeOSPilotRunner,
)
from hive_mind_os.pilot_runtime import (
    PilotBlockerCode,
    PilotController,
    PilotPlan,
    PilotPrerequisites,
    PilotStore,
)
from hive_mind_os.production_evidence import (
    EVIDENCE_DOMAIN_PREFIX,
    GATE_PURPOSES,
    MODE_PRODUCTION,
    MODE_TRUSTED_LOCAL,
    PURPOSE_SCHEMAS,
    CurrentEvidenceStatus,
    DeterministicReceiptStore,
    EvidenceBlocker,
    EvidencePurpose,
    EvidenceTrustPolicy,
    EvidenceUse,
    IssuerRole,
    PinnedEvidenceResolver,
    ProductionEvidenceContext,
    ProductionEvidenceError,
    StatusState,
    TrustedIssuer,
    evidence_preimage,
)
from hive_mind_os.release_closeout import (
    CloseoutBuilder,
    load_verified_release_manifest,
    manifest_digest,
    verify_production_closeout,
    write_release_manifest,
    write_verified_release_manifest,
)
from hive_mind_os.runtime_contracts import canonical_digest as lease_digest_of
from hive_mind_os.whole_os_qualification import (
    LIFECYCLE_STAGE_IDS,
    NODE_IDS,
    REQUIREMENT_IDS,
    SPECIALIST_ROLE_IDS,
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    OperationalReceipt,
    PilotAttempt,
    QualificationLedger,
    canonical_digest,
)
from hive_mind_os.whole_os_service import ServiceObservation

for _distribution, _expected_version in {
    "cryptography": "50.0.1", "cffi": "2.1.1", "pycparser": "3.0"
}.items():
    if version(_distribution) != _expected_version:
        raise RuntimeError(f"unqualified production-evidence dependency: {_distribution}")
if cryptography.__version__ != "50.0.1":
    raise RuntimeError("unqualified loaded production-evidence provider")

P = EvidencePurpose
CAND = "sha256:" + "a" * 64
AUTH = "sha256:" + "b" * 64
PREV = "sha256:" + "c" * 64
NAMESPACE = "receipt://evidence/"
# Independent spelling of the evidence domain, so the tests do not mirror the module.
PREFIX = b"hive-mind-os/production-evidence/v1\n"
MODE = {"pilot_mode": "self"}
STARTS = 1000
ENDS = STARTS + 72 * 3600


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


ATTESTOR_PURPOSES = frozenset(
    p for p in P if PURPOSE_SCHEMAS[p].roles == {IssuerRole.ATTESTOR}
)
EVALUATOR_PURPOSES = frozenset({P.ATTEMPT_DELIVERY, P.ATTEMPT_RUNTIME})


class Signer:
    """A synthetic issuer with a throwaway key."""

    def __init__(self, principal, administration, role, remit):
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
        self.principal, self.administration = principal, administration
        self.role, self.remit = role, frozenset(remit)
        self.key_id = f"key-{principal}"

    def trusted(self, **changes) -> TrustedIssuer:
        values = dict(
            principal_id=self.principal,
            administration_id=self.administration,
            key_id=self.key_id,
            public_key=self.public,
            role=self.role,
            remit=self.remit,
        )
        values.update(changes)
        return TrustedIssuer(**values)

    def sign(self, message: bytes) -> bytes:
        return self.private.sign(message)


class Clock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class Authority:
    """Test double for the external current-state service."""

    def __init__(self) -> None:
        self.calls = []
        self.revoked_digests = set()
        self.revoked_purposes = set()
        self.fail = False
        self.mutate = None
        self.lease_current = True
        self.lease_digests = []

    def resolve(self, use, issuer_id, key_id, receipt_digest, now):
        self.calls.append((use.purpose, receipt_digest))
        if use.lease_digest is not None:
            self.lease_digests.append(use.lease_digest)
        if self.fail:
            raise TimeoutError("status service unavailable")
        revoked = (
            receipt_digest in self.revoked_digests or use.purpose in self.revoked_purposes
        )
        lease = use.lease_digest
        if lease is not None and not self.lease_current:
            lease = "sha256:" + "0" * 64
        status = CurrentEvidenceStatus(
            use.digest(),
            issuer_id,
            key_id,
            receipt_digest,
            "gen-1",
            now,
            StatusState.ACTIVE,
            StatusState.ACTIVE,
            StatusState.REVOKED if revoked else StatusState.ACTIVE,
            lease,
        )
        return self.mutate(status) if self.mutate else status


class Lease:
    def __init__(self, document) -> None:
        self.document = document

    def to_document(self):
        return self.document


class LeasePort:
    def __init__(self) -> None:
        self.calls = []
        self.missing = False
        self.on_call = None

    def current_lease(self, *, candidate_digest, subject_id, attempt_id):
        self.calls.append(attempt_id)
        if self.on_call:
            self.on_call(len(self.calls))
        if self.missing:
            return None
        return Lease(
            {"lease_id": f"lease-{attempt_id}", "holder": "hé", "subject": subject_id}
        )


class InterleavedStore(PilotStore):
    """A real PilotStore that only schedules: the named thread pauses immediately before
    the load that ``_update`` performs for its compared transition, after every
    pre-check read has already happened. It never changes returned states or bytes."""

    def __init__(self, root):
        super().__init__(root)
        self.hold = None
        self.reached = threading.Event()
        self.release = threading.Event()

    def load(self):
        if (
            self.hold == threading.current_thread().name
            and sys._getframe(1).f_code.co_name == "_state"
            and sys._getframe(2).f_code.co_name == "_update"
        ):
            self.hold = None
            self.reached.set()
            if not self.release.wait(15):
                raise AssertionError("the first caller did not finish")
        return super().load()


class World:
    """Issuers, trust policy, in-memory store, authority, clock and ledger."""

    def __init__(self, ledger_path, *, attestor2_remit=None, maximum_receipt_bytes=4096):
        self.builder = Signer("builder-1", "admin-builder", IssuerRole.BUILDER, ())
        self.attestor = Signer(
            "attestor-1", "admin-attest-1", IssuerRole.ATTESTOR, ATTESTOR_PURPOSES
        )
        self.attestor2 = Signer(
            "attestor-2",
            "admin-attest-2",
            IssuerRole.ATTESTOR,
            ATTESTOR_PURPOSES if attestor2_remit is None else attestor2_remit,
        )
        self.evaluator = Signer(
            "evaluator-1", "admin-eval", IssuerRole.EVALUATOR, EVALUATOR_PURPOSES
        )
        self.judge = Signer(
            "judge-1", "admin-judge", IssuerRole.JUDGE, {P.CLOSEOUT_JUDGMENT}
        )
        self.judge2 = Signer(
            "judge-2", "admin-judge-2", IssuerRole.JUDGE, {P.CLOSEOUT_JUDGMENT}
        )
        self.attacker = Signer("attacker", "admin-x", IssuerRole.ATTESTOR, ATTESTOR_PURPOSES)
        self.signers = (
            self.builder, self.attestor, self.attestor2, self.evaluator, self.judge,
            self.judge2,
        )
        self.promotion_pin = "sha256:" + "9" * 64
        self.policy = self.make_policy(
            [s.trusted() for s in self.signers],
            maximum_receipt_bytes=maximum_receipt_bytes,
        )
        self.store = DeterministicReceiptStore(NAMESPACE, {})
        self.authority = Authority()
        self.lease_port = LeasePort()
        self.clock = Clock(1100)
        self.ledger = QualificationLedger(ledger_path)
        self._names = count()

    def make_policy(self, issuers, **changes):
        values = dict(
            generation="gen-1",
            issuers=tuple(issuers),
            uri_prefixes=(NAMESPACE,),
            gate_maximum_age_seconds={p: 30 * 86400 for p in GATE_PURPOSES},
            status_maximum_age_seconds=60,
            promotion_public_key_digests=frozenset({self.promotion_pin}),
            maximum_receipt_bytes=4096,
        )
        values.update(changes)
        return EvidenceTrustPolicy(**values)

    def resolver(self, **changes):
        values = dict(policy=self.policy, store=self.store, authority=self.authority)
        values.update(changes)
        return PinnedEvidenceResolver(values["policy"], values["store"], values["authority"])

    def context(self, *, lease=True, **changes) -> ProductionEvidenceContext:
        return ProductionEvidenceContext(
            self.resolver(**changes),
            self.clock,
            self.ledger,
            self.lease_port if lease else None,
        )

    def payload(self, purpose, signer, *, subject, operation, claims, observed, issued,
                candidate=CAND, authority=AUTH):
        body = {
            "kind": "hive-production-evidence",
            "schema_version": 1,
            "algorithm": "ed25519",
            "purpose": purpose.value,
            "issuer_id": signer.principal,
            "key_id": signer.key_id,
            "subject_id": subject,
            "operation_id": operation,
            "candidate_digest": candidate,
            "observed_at": observed,
            "issued_at": issued,
            "claims": claims,
        }
        if PURPOSE_SCHEMAS[purpose].binds_authority:
            body["authority_digest"] = authority
        return body

    def receipt(self, purpose, signer, *, subject, operation, claims, observed, issued,
                name=None, candidate=CAND, authority=AUTH, override=None, mutate=None,
                sign_with=None, raw=None, uri=None) -> EvidenceRef:
        body = self.payload(
            purpose, signer, subject=subject, operation=operation, claims=claims,
            observed=observed, issued=issued, candidate=candidate, authority=authority,
        )
        body.update(override or {})
        signature = (sign_with or signer).sign(PREFIX + canonical(body))
        document = {**body, "signature": base64.b64encode(signature).decode()}
        if mutate:
            document = mutate(document)
        data = raw if raw is not None else json.dumps(document).encode()
        uri = uri or NAMESPACE + (name or f"r{next(self._names)}")
        self.store.put(uri, data)
        return EvidenceRef(uri, sha(data), EvidenceKind.EXTERNAL_RECEIPT, subject, observed)

    def prerequisites(self) -> PilotPrerequisites:
        def gate(purpose, subject, claims, name, signer=None):
            return self.receipt(
                purpose, signer or self.attestor, subject=subject, operation="pilot",
                claims=claims, observed=900, issued=950, name=name,
            )

        return PilotPrerequisites(
            gate(P.PILOT_HOST, "pilot", MODE, "host"),
            gate(P.PILOT_SUPERVISOR, "pilot", MODE, "supervisor"),
            gate(P.PILOT_DELIVERY_AUTHORITY, "pilot", MODE, "authority"),
            gate(P.PILOT_BENCHMARK, CAND, {}, "benchmark"),
        )

    def delivery(self, attempt_id, subject, *, started, ended, family="feature",
                 units=1, domain=None, signer=None, name=None) -> EvidenceRef:
        return self.receipt(
            P.ATTEMPT_DELIVERY, signer or self.evaluator, subject=subject,
            operation=attempt_id,
            claims={"family_id": family, "started_at": started, "ended_at": ended,
                    "resource_units": units, "domain": domain or ""},
            observed=ended, issued=ended, name=name or f"delivery-{attempt_id}",
        )


def use_for(purpose, subject, operation, claims, **fields):
    schema = PURPOSE_SCHEMAS[purpose]
    return EvidenceUse(
        purpose, subject, operation, CAND, AUTH if schema.binds_authority else None,
        claims, **fields,
    )


class ProductionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.world = World(self.tmp / "ledger.jsonl")

    def assertBlocked(self, blocker, action, *args, detail=None, **kwargs):
        with self.assertRaises(ProductionEvidenceError) as raised:
            action(*args, **kwargs)
        self.assertEqual(raised.exception.blocker, blocker, str(raised.exception))
        if detail is not None:
            self.assertIn(detail, raised.exception.detail)
        return raised.exception


class ResolverTests(ProductionCase):
    def host(self, **receipt_changes):
        ref = self.world.receipt(
            P.PILOT_HOST, self.world.attestor, subject="pilot", operation="pilot",
            claims=MODE, observed=900, issued=950, **receipt_changes,
        )
        return ref, use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)

    def resolve(self, ref, use, now=1100, resolver=None):
        return (resolver or self.world.resolver()).require(ref, use, now)

    def test_real_ed25519_positive_observation_before_signing(self):
        ref, use = self.host()
        resolution = self.resolve(ref, use)
        self.assertEqual(resolution.issuer_id, "attestor-1")
        self.assertEqual(resolution.public_key_digest, sha(self.world.attestor.public))
        self.assertEqual(
            (resolution.observed_at, resolution.issued_at, resolution.verified_at),
            (900, 950, 1100),
        )
        self.assertEqual(len(self.world.authority.calls), 1)

    def test_schema_table_is_closed_and_preimage_is_domain_separated(self):
        self.assertEqual(set(PURPOSE_SCHEMAS), set(P))
        self.assertEqual(
            GATE_PURPOSES,
            {P.PILOT_HOST, P.PILOT_SUPERVISOR, P.PILOT_DELIVERY_AUTHORITY,
             P.PILOT_BENCHMARK, P.PILOT_TARGET, P.PILOT_RUNTIME_CAPABILITY},
        )
        self.assertEqual(EVIDENCE_DOMAIN_PREFIX, PREFIX)
        body = {"a": 1}
        self.assertEqual(evidence_preimage(body), PREFIX + canonical(body))
        self.assertBlocked(
            EvidenceBlocker.RECEIPT_MALFORMED, evidence_preimage, {"signature": "x"}
        )
        self.assertBlocked(
            EvidenceBlocker.USE_INVALID, use_for, P.CLOSEOUT_ROLE, "architect",
            "release-1", {"role_id": "architect"}, lease_digest=CAND,
        )

    def test_fake_external_receipt_with_valid_labels_and_no_bytes(self):
        ref = EvidenceRef(
            NAMESPACE + "ghost", CAND, EvidenceKind.EXTERNAL_RECEIPT, "pilot", 900
        )
        use = use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)
        self.assertBlocked(EvidenceBlocker.STORE_UNAVAILABLE, self.resolve, ref, use)
        outside = replace(ref, uri="receipt://elsewhere/ghost")
        self.world.store.reads.clear()
        self.assertBlocked(EvidenceBlocker.URI_NOT_ALLOWED, self.resolve, outside, use)
        self.assertEqual(self.world.store.reads, [])
        synthetic = replace(ref, kind=EvidenceKind.SYNTHETIC)
        self.assertBlocked(EvidenceBlocker.USE_INVALID, self.resolve, synthetic, use)
        self.assertEqual(self.world.authority.calls, [])

    def test_tampering_and_signature_failures(self):
        ref, use = self.host()
        original = self.world.store._objects[ref.uri]
        self.world.store.put(ref.uri, original + b" ")
        self.assertBlocked(EvidenceBlocker.DIGEST_MISMATCH, self.resolve, ref, use)

        def flip(document):
            raw = bytearray(base64.b64decode(document["signature"]))
            raw[0] ^= 1
            return {**document, "signature": base64.b64encode(bytes(raw)).decode()}

        body = self.world.payload(
            P.PILOT_HOST, self.world.attestor, subject="pilot", operation="pilot",
            claims=MODE, observed=900, issued=950,
        )
        unprefixed = {
            **body,
            "signature": base64.b64encode(self.world.attestor.sign(canonical(body))).decode(),
        }
        cases = {
            "bit-flipped signature": self.host(mutate=flip),
            "field changed after signing": self.host(
                mutate=lambda d: {**d, "issued_at": 951}
            ),
            "signed without the domain prefix": self.host(
                raw=json.dumps(unprefixed).encode()
            ),
        }
        for label, (ref2, use2) in cases.items():
            with self.subTest(label):
                self.assertBlocked(
                    EvidenceBlocker.SIGNATURE_INVALID, self.resolve, ref2, use2
                )
        unsigned = self.world.payload(
            P.PILOT_HOST, self.world.attestor, subject="pilot", operation="pilot",
            claims=MODE, observed=900, issued=950,
        )
        ref3, use3 = self.host(raw=json.dumps(unsigned).encode())
        self.assertBlocked(EvidenceBlocker.RECEIPT_MALFORMED, self.resolve, ref3, use3)

    def test_key_injection_is_rejected(self):
        world = self.world
        cases = {
            "unpinned key claimed by the attacker": (
                dict(override={"key_id": world.attacker.key_id}, sign_with=world.attacker),
                EvidenceBlocker.ISSUER_UNKNOWN,
            ),
            "another issuer's pinned key": (
                dict(override={"key_id": world.attestor2.key_id}),
                EvidenceBlocker.ISSUER_UNKNOWN,
            ),
            "attacker signature under a pinned identity": (
                dict(sign_with=world.attacker),
                EvidenceBlocker.SIGNATURE_INVALID,
            ),
            "embedded public key field": (
                dict(mutate=lambda d: {**d, "public_key": "AAAA"}),
                EvidenceBlocker.RECEIPT_MALFORMED,
            ),
        }
        for label, (changes, blocker) in cases.items():
            with self.subTest(label):
                ref, use = self.host(**changes)
                self.assertBlocked(blocker, self.resolve, ref, use)

    def test_wrong_context_fields_purpose_and_claims(self):
        world = self.world
        base = dict(subject="pilot", operation="pilot", claims=MODE, observed=900, issued=950)
        cases = {
            "subject": dict(override={"subject_id": "other"}),
            "operation": dict(override={"operation_id": "other-op"}),
            "candidate": dict(override={"candidate_digest": PREV}),
            "authority": dict(override={"authority_digest": PREV}),
            "claims": dict(override={"claims": {"pilot_mode": "external"}}),
        }
        for label, changes in cases.items():
            with self.subTest(label):
                ref = world.receipt(P.PILOT_HOST, world.attestor, **base, **changes)
                use = use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)
                self.assertBlocked(EvidenceBlocker.CONTEXT_MISMATCH, self.resolve, ref, use)
        supervisor = world.receipt(P.PILOT_SUPERVISOR, world.attestor, **base)
        use = use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)
        self.assertBlocked(EvidenceBlocker.CONTEXT_MISMATCH, self.resolve, supervisor, use)
        ref, use = self.host()
        wrong_subject = replace(ref, subject_id="other")
        self.assertBlocked(EvidenceBlocker.CONTEXT_MISMATCH, self.resolve, wrong_subject, use)
        stale_observation = replace(ref, observed_at=901)
        self.assertBlocked(
            EvidenceBlocker.CONTEXT_MISMATCH, self.resolve, stale_observation, use
        )

    def test_time_ordering_windows_and_gate_freshness(self):
        world = self.world
        base = dict(subject="pilot", operation="pilot", claims=MODE)
        use = use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)
        cases = {
            "observed after signing": (dict(observed=960, issued=950), 1100),
            "signed in the future": (dict(observed=900, issued=1200), 1100),
            "observed after pilot start": (dict(observed=1001, issued=1001), 1100),
        }
        for label, (times, now) in cases.items():
            with self.subTest(label):
                ref = world.receipt(P.PILOT_HOST, world.attestor, **base, **times)
                self.assertBlocked(EvidenceBlocker.TIME_WINDOW, self.resolve, ref, use, now)
        ref, use = self.host()
        self.assertBlocked(
            EvidenceBlocker.EVIDENCE_STALE, self.resolve, ref, use, 950 + 30 * 86400 + 1
        )
        for label, bad in {"bool": True, "float": 900.0, "huge": 10**30}.items():
            with self.subTest(label):
                ref2, use2 = self.host(override={"observed_at": bad})
                self.assertBlocked(EvidenceBlocker.RECEIPT_MALFORMED, self.resolve, ref2, use2)
        ref4 = world.receipt(
            P.ATTEMPT_DELIVERY, world.evaluator, subject="self", operation="attempt-1",
            claims={"family_id": "feature", "started_at": 1100, "ended_at": 1100,
                    "resource_units": 1, "domain": ""},
            observed=1050, issued=1050,
        )
        attempt_use = use_for(
            P.ATTEMPT_DELIVERY, "self", "attempt-1",
            {"family_id": "feature", "started_at": 1100, "ended_at": 1100,
             "resource_units": 1, "domain": ""},
            window_start=1100, window_end=ENDS,
        )
        self.assertBlocked(EvidenceBlocker.TIME_WINDOW, self.resolve, ref4, attempt_use)

    def test_record_evidence_outlives_freshness_but_status_must_still_be_current(self):
        world = self.world
        ref = world.delivery("attempt-1", "self", started=1100, ended=1100)
        claims = {"family_id": "feature", "started_at": 1100, "ended_at": 1100,
                  "resource_units": 1, "domain": ""}
        use = use_for(P.ATTEMPT_DELIVERY, "self", "attempt-1", claims,
                      window_start=1100, window_end=ENDS)
        later = 1100 + 72 * 3600 + 30 * 86400
        self.assertEqual(self.resolve(ref, use, later).issued_at, 1100)
        world.authority.revoked_digests.add(ref.digest)
        self.assertBlocked(EvidenceBlocker.EVIDENCE_REVOKED, self.resolve, ref, use, later)

    def test_current_status_is_required_exact_active_and_fresh(self):
        ref, use = self.host()
        states = {
            "retired": (StatusState.RETIRED, EvidenceBlocker.STATUS_NOT_ACTIVE),
            "rotated": (StatusState.ROTATED, EvidenceBlocker.STATUS_NOT_ACTIVE),
            "unknown": (StatusState.UNKNOWN, EvidenceBlocker.STATUS_NOT_ACTIVE),
            "revoked": (StatusState.REVOKED, EvidenceBlocker.EVIDENCE_REVOKED),
        }
        for label, (state, blocker) in states.items():
            for field in ("issuer_state", "key_state", "receipt_state"):
                with self.subTest(label=label, field=field):
                    self.world.authority.mutate = lambda s, f=field, v=state: replace(s, **{f: v})
                    self.assertBlocked(blocker, self.resolve, ref, use)
        mismatches = {
            "another use": dict(use_digest=CAND),
            "another issuer": dict(issuer_id="attestor-2"),
            "another key": dict(key_id="key-x"),
            "another receipt": dict(receipt_digest=CAND),
            "another policy generation": dict(policy_generation="gen-2"),
            "lease not requested": dict(lease_digest=CAND),
            "future observation": dict(observed_at=1101),
        }
        for label, changes in mismatches.items():
            with self.subTest(label):
                self.world.authority.mutate = lambda s, c=changes: replace(s, **c)
                self.assertBlocked(EvidenceBlocker.STATUS_MISMATCH, self.resolve, ref, use)
        for label, observed in {"stale": 1100 - 61, "before issuance": 949}.items():
            with self.subTest(label):
                self.world.authority.mutate = lambda s, o=observed: replace(s, observed_at=o)
                self.assertBlocked(EvidenceBlocker.STATUS_STALE, self.resolve, ref, use)
        self.world.authority.mutate = lambda s: {"not": "a status"}
        self.assertBlocked(EvidenceBlocker.STATUS_UNAVAILABLE, self.resolve, ref, use)
        self.world.authority.mutate = None
        self.world.authority.fail = True
        self.assertBlocked(EvidenceBlocker.STATUS_UNAVAILABLE, self.resolve, ref, use)

    def test_bounds_and_strict_json(self):
        world = self.world
        ref, use = self.host()
        valid = world.store._objects[ref.uri]
        # Exactly at the byte bound is accepted; one more byte is not.
        padded = valid + b" " * (4096 - len(valid))
        at_limit, use = self.host(raw=padded)
        self.assertEqual(len(padded), 4096)
        self.assertEqual(self.resolve(at_limit, use).issuer_id, "attestor-1")
        over, use = self.host(raw=padded + b" ")
        self.assertBlocked(EvidenceBlocker.RECEIPT_OVERSIZE, self.resolve, over, use)

        class HugeStore:
            def read(self, uri, max_bytes, deadline_seconds):
                return bytes(10**6)

        huge = replace(ref, digest=sha(bytes(10**6)))
        self.assertBlocked(
            EvidenceBlocker.RECEIPT_OVERSIZE, self.resolve, huge, use,
            resolver=world.resolver(store=HugeStore()),
        )
        text = valid.decode()
        malformed = {
            "nesting": ('{"a":' + "[" * 10 + "]" * 10 + "}").encode(),
            "duplicate object key": (text[:-1] + ',"subject_id":"pilot"}').encode(),
            "non-finite": text.replace('"observed_at": 900', '"observed_at": NaN').encode(),
            "closed schema": json.dumps({**json.loads(text), "extra": 1}).encode(),
            "bounded": json.dumps({**json.loads(text), "x": list(range(500))}).encode(),
            "UTF-8": b"\xff\xfe{}",
            "floating": text.replace('"observed_at": 900', '"observed_at": 900.5').encode(),
        }
        for detail, raw in malformed.items():
            with self.subTest(detail):
                ref2, use2 = self.host(raw=raw)
                self.assertBlocked(
                    EvidenceBlocker.RECEIPT_MALFORMED, self.resolve, ref2, use2, detail=detail
                )
        overrides = {
            "unknown schema version": {"schema_version": 2},
            "unknown algorithm": {"algorithm": "rsa"},
            "unknown kind": {"kind": "promotion-attestation"},
            "unknown purpose": {"purpose": "pilot-anything"},
        }
        for label, override in overrides.items():
            with self.subTest(label):
                ref2, use2 = self.host(override=override)
                self.assertBlocked(EvidenceBlocker.RECEIPT_MALFORMED, self.resolve, ref2, use2)
        for label, signature in {"short": "AAAA", "whitespace": " " * 88}.items():
            with self.subTest(label):
                ref2, use2 = self.host(mutate=lambda d, s=signature: {**d, "signature": s})
                self.assertBlocked(EvidenceBlocker.RECEIPT_MALFORMED, self.resolve, ref2, use2)

    def test_configured_identity_and_pin_separation(self):
        w = self.world
        alias = w.judge.trusted(public_key=w.builder.public)
        self.assertBlocked(
            EvidenceBlocker.POLICY_INVALID, w.make_policy,
            [w.builder.trusted(), alias, w.attestor.trusted(), w.evaluator.trusted()],
        )
        for left, right in ((w.judge, w.builder), (w.judge, w.evaluator), (w.builder, w.evaluator)):
            with self.subTest(left=left.principal, right=right.principal):
                issuers = [s.trusted() for s in w.signers if s is not left]
                issuers.append(left.trusted(administration_id=right.administration))
                self.assertBlocked(EvidenceBlocker.POLICY_INVALID, w.make_policy, issuers)
        self.assertBlocked(
            EvidenceBlocker.POLICY_INVALID, w.make_policy, [s.trusted() for s in w.signers],
            promotion_public_key_digests=frozenset({sha(w.builder.public)}),
        )
        self.assertBlocked(
            EvidenceBlocker.POLICY_INVALID, w.make_policy, [s.trusted() for s in w.signers],
            gate_maximum_age_seconds={p: 10 for p in GATE_PURPOSES if p is not P.PILOT_HOST},
        )
        self.assertBlocked(
            EvidenceBlocker.POLICY_INVALID, w.make_policy, [s.trusted() for s in w.signers],
            gate_maximum_age_seconds={p: True for p in GATE_PURPOSES},
        )
        self.assertBlocked(
            EvidenceBlocker.POLICY_INVALID, w.attestor.trusted, remit={P.ATTEMPT_DELIVERY}
        )
        self.assertBlocked(EvidenceBlocker.POLICY_INVALID, w.builder.trusted, remit={P.PILOT_HOST})
        self.assertBlocked(EvidenceBlocker.POLICY_INVALID, w.attestor.trusted, public_key=b"x" * 31)
        policy = w.policy
        self.assertBlocked(EvidenceBlocker.SEPARATION, policy.require_separation, "builder-1", "builder-1")
        self.assertBlocked(EvidenceBlocker.ISSUER_UNKNOWN, policy.require_separation, "someone", "judge-1")
        self.assertBlocked(EvidenceBlocker.SEPARATION, policy.require_separation, "builder-1", "attestor-1")
        self.assertEqual(len(policy.require_separation("builder-1", "judge-1")), 2)
        # The existing adapter really binds a pin to its digest.
        verifier = Ed25519SignatureVerifier({w.attestor.key_id: w.attestor.public})
        good = PrincipalBinding("attestor-1", "receipt", "admin", w.attestor.key_id, sha(w.attestor.public))
        bad = PrincipalBinding("attestor-1", "receipt", "admin", w.attestor.key_id, CAND)
        message = b"x"
        signature = w.attestor.sign(message)
        self.assertTrue(verifier.verify(good, message, signature))
        self.assertFalse(verifier.verify(bad, message, signature))

    def test_issuer_remit_and_missing_dependencies_are_typed(self):
        limited = World(self.tmp / "limited.jsonl", attestor2_remit={P.PILOT_SUPERVISOR})
        ref = limited.receipt(
            P.PILOT_HOST, limited.attestor2, subject="pilot", operation="pilot",
            claims=MODE, observed=900, issued=950,
        )
        use = use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)
        self.assertBlocked(
            EvidenceBlocker.ISSUER_REMIT, limited.resolver().require, ref, use, 1100
        )
        ref, use = self.host()
        for blocker, changes in (
            (EvidenceBlocker.TRUST_STORE_MISSING, dict(policy=None)),
            (EvidenceBlocker.RECEIPT_STORE_MISSING, dict(store=None)),
            (EvidenceBlocker.CURRENT_AUTHORITY_MISSING, dict(authority=None)),
        ):
            with self.subTest(blocker):
                resolver = self.world.resolver(**changes)
                self.assertBlocked(blocker, resolver.require, ref, use, 1100)
                self.assertBlocked(blocker, resolver.require_all, [], 1100)

        class Unavailable:
            def verify(self, principal, message, signature):
                raise PromotionAuthenticationError("authentication-unavailable", "no provider")

        class Permissive:
            def verify(self, principal, message, signature):
                return 1

        for blocker, verifier in (
            (EvidenceBlocker.CRYPTO_UNAVAILABLE, Unavailable()),
            (EvidenceBlocker.SIGNATURE_INVALID, Permissive()),
        ):
            with self.subTest(blocker):
                resolver = PinnedEvidenceResolver(
                    self.world.policy, self.world.store, self.world.authority,
                    signature_verifier=verifier,
                )
                self.assertBlocked(blocker, resolver.require, ref, use, 1100)

    def test_same_use_replay_multiple_witnesses_and_no_double_counting(self):
        w = self.world
        ref, use = self.host()
        self.resolve(ref, use)
        self.resolve(ref, use)  # identical evidence for the identical use stays legal
        self.assertEqual(len(w.authority.calls), 2)
        second = w.receipt(
            P.PILOT_HOST, w.attestor2, subject="pilot", operation="pilot",
            claims=MODE, observed=900, issued=950, name="host-witness-2",
        )
        resolutions = w.resolver().require_all([(ref, use), (second, use)], 1100)
        self.assertEqual({r.issuer_id for r in resolutions}, {"attestor-1", "attestor-2"})
        self.assertEqual(len({r.receipt_digest for r in resolutions}), 2)
        self.assertBlocked(
            EvidenceBlocker.DUPLICATE_EVIDENCE, w.resolver().require_all, [(ref, use), (ref, use)], 1100
        )
        resigned = w.receipt(
            P.PILOT_HOST, w.attestor, subject="pilot", operation="pilot",
            claims=MODE, observed=901, issued=950, name="host-same-issuer",
        )
        self.assertBlocked(
            EvidenceBlocker.DUPLICATE_EVIDENCE, w.resolver().require_all,
            [(ref, use), (resigned, use)], 1100,
        )
        role = w.receipt(
            P.CLOSEOUT_ROLE, w.attestor, subject="architect", operation="release-1",
            claims={"role_id": "architect"}, observed=100, issued=110, candidate=CAND,
        )
        stage_use = use_for(P.CLOSEOUT_STAGE, "architect", "release-1", {"stage_id": "architect"})
        self.assertBlocked(EvidenceBlocker.CONTEXT_MISMATCH, self.resolve, role, stage_use)

    def test_no_cached_authorization_across_calls_copied_contexts_or_threads(self):
        ref, use = self.host()
        resolver = self.world.resolver()
        self.assertEqual(resolver.require(ref, use, 1100).issuer_id, "attestor-1")
        copied = contextvars.copy_context()
        self.world.authority.revoked_digests.add(ref.digest)
        self.assertBlocked(EvidenceBlocker.EVIDENCE_REVOKED, resolver.require, ref, use, 1100)
        with self.assertRaises(ProductionEvidenceError):
            copied.run(resolver.require, ref, use, 1100)
        failures = []

        def attempt():
            try:
                resolver.require(ref, use, 1100)
            except ProductionEvidenceError as error:
                failures.append(error.blocker)

        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [EvidenceBlocker.EVIDENCE_REVOKED] * 8)


class ProductionPilotTests(ProductionCase):
    class Service:
        def __init__(self, controller, *, fail=False):
            self.controller, self.fail = controller, fail
            self.run_calls = self.observe_calls = 0

        @staticmethod
        def observation():
            return ServiceObservation("campaign", "running", (), ("package",), ())

        def run_once(self):
            self.run_calls += 1
            if not self.controller.store.load().active_attempts:
                raise AssertionError("host ran before the pilot intent was durable")
            if self.fail:
                raise TimeoutError("uncertain host boundary")
            return self.observation()

        def observe(self):
            self.observe_calls += 1
            return self.observation()

    class Evaluator:
        def __init__(self, world, hook=None):
            self.world, self.hook = world, hook

        def __call__(self, **v):
            if self.hook:
                self.hook()
            delivery = self.world.delivery(
                v["attempt_id"], v["subject_id"], started=v["started_at"],
                ended=v["ended_at"], family=v["family_id"], units=v["resource_units"],
                domain=v["domain"],
            )
            return PilotAttempt(
                v["attempt_id"], v["subject_id"], v["family_id"], v["candidate_digest"],
                "accepted", delivery, v["started_at"], v["ended_at"],
                v["resource_units"], v["domain"],
            )

    def plan(self, prerequisites=None):
        return PilotPlan(
            "pilot", "self", CAND, ("self",), STARTS, ENDS, 1, 10, 3, AUTH,
            self.world.prerequisites() if prerequisites is None else prerequisites,
        )

    def build(self, *, plan=None, root=None, hook=None, fail=False, **context_changes):
        plan = plan or self.plan()
        root = root or self.tmp / "pilot"
        controller = PilotController(
            PilotStore(root), plan, production=self.world.context(**context_changes)
        )
        service = self.Service(controller, fail=fail)
        runner = WholeOSPilotRunner(
            controller, service, self.Evaluator(self.world, hook), clock=self.world.clock
        )
        return controller, service, runner, plan

    def run_attempt(self, runner, attempt_id="attempt-1"):
        return runner.run_once(attempt_id=attempt_id, subject_id="self", family_id="feature")

    def test_accepted_attempt_is_resolved_at_every_boundary(self):
        controller, service, runner, _ = self.build()
        result = self.run_attempt(runner)
        self.assertEqual(result.attempt.status, "accepted")
        self.assertEqual(service.run_calls, 1)
        self.assertEqual(controller.snapshot().evidence_mode, MODE_PRODUCTION)
        # begin gate, pre-dispatch recheck and completion each ask for the actual lease.
        self.assertEqual(self.world.lease_port.calls, ["attempt-1"] * 3)
        expected = lease_digest_of(
            {"lease_id": "lease-attempt-1", "holder": "hé", "subject": "self"}
        )
        self.assertEqual(set(self.world.authority.lease_digests), {expected})
        self.assertNotEqual(
            expected,
            canonical_digest({"lease_id": "lease-attempt-1", "holder": "hé", "subject": "self"}),
        )
        kinds = [entry.kind for entry in self.world.ledger.read()]
        self.assertIn("production-evidence-success", kinds)
        self.assertNotIn("production-evidence-failure", kinds)

    def test_label_only_prerequisites_never_reach_the_host(self):
        for label, uri in {
            "receipt-store-unavailable": NAMESPACE + "ghost",
            "receipt-uri-not-allowed": "receipt:host",
        }.items():
            with self.subTest(label):
                def fake(subject, name, uri=uri):
                    return EvidenceRef(
                        uri + name, canonical_digest(name),
                        EvidenceKind.EXTERNAL_RECEIPT, subject, 0,
                    )

                plan = self.plan(
                    PilotPrerequisites(
                        fake("pilot", "host"), fake("pilot", "supervisor"),
                        fake("pilot", "authority"), fake(CAND, "benchmark"),
                    )
                )
                root = self.tmp / label
                controller, service, runner, _ = self.build(plan=plan, root=root)
                with self.assertRaises(PilotExecutionError) as raised:
                    self.run_attempt(runner)
                self.assertEqual(
                    raised.exception.blocker, PilotExecutionBlocker.PREREQUISITES_UNRESOLVED
                )
                self.assertIn(
                    f"production-evidence-{label}",
                    {item.obligation_id for item in raised.exception.obligations},
                )
                self.assertEqual(service.run_calls, 0)
                self.assertEqual(controller.snapshot().active_attempts, ())
                # The unchanged trusted-local controller still accepts labels structurally.
                local = PilotController(PilotStore(self.tmp / f"local-{label}"), plan)
                local_service = self.Service(local)
                WholeOSPilotRunner(
                    local, local_service, self.Evaluator(self.world), clock=self.world.clock
                ).run_once(attempt_id="a", subject_id="self", family_id="f")
                self.assertEqual(local_service.run_calls, 1)
                self.assertEqual(local.snapshot().evidence_mode, MODE_TRUSTED_LOCAL)

    def test_missing_trust_store_receipt_store_authority_and_lease_are_typed_blockers(self):
        cases = {
            "trust-store-missing": dict(policy=None),
            "receipt-store-missing": dict(store=None),
            "current-authority-missing": dict(authority=None),
        }
        for label, changes in cases.items():
            with self.subTest(label):
                _, service, runner, _ = self.build(root=self.tmp / label, **changes)
                with self.assertRaises(PilotExecutionError) as raised:
                    self.run_attempt(runner)
                self.assertEqual(
                    raised.exception.blocker, PilotExecutionBlocker.PREREQUISITES_UNRESOLVED
                )
                self.assertIn(
                    f"production-evidence-{label}",
                    {item.obligation_id for item in raised.exception.obligations},
                )
                self.assertEqual(service.run_calls, 0)
        controller, service, runner, _ = self.build(root=self.tmp / "lease", lease=False)
        with self.assertRaises(PilotExecutionError) as raised:
            self.run_attempt(runner)
        self.assertEqual(
            raised.exception.blocker, PilotExecutionBlocker.PRODUCTION_EVIDENCE_BLOCKED
        )
        self.assertEqual(
            raised.exception.obligations[0].obligation_id,
            "production-evidence-host-lease-mapping-missing",
        )
        self.assertEqual(service.run_calls, 0)
        self.assertEqual(controller.snapshot().active_attempts, ())
        self.assertBlocked(
            EvidenceBlocker.LEASE_MAPPING_MISSING, controller.begin_attempt,
            attempt_id="direct", subject_id="self", family_id="f", started_at=1100,
        )
        self.world.lease_port.missing = True
        controller2, _, _, _ = self.build(root=self.tmp / "no-mapping")
        self.assertBlocked(
            EvidenceBlocker.LEASE_MAPPING_MISSING, controller2.begin_attempt,
            attempt_id="direct", subject_id="self", family_id="f", started_at=1100,
        )
        failures = [e.kind for e in self.world.ledger.read()]
        self.assertIn("production-evidence-failure", failures)

    def test_revocation_between_begin_and_dispatch_closes_blocked_without_effect(self):
        controller, service, runner, plan = self.build()
        host = plan.prerequisites.whole_os_host

        def revoke(call_number):
            if call_number == 2:  # the immediate pre-dispatch recheck
                self.world.authority.revoked_digests.add(host.digest)

        self.world.lease_port.on_call = revoke
        with self.assertRaises(PilotExecutionError) as raised:
            self.run_attempt(runner)
        self.assertEqual(
            raised.exception.blocker, PilotExecutionBlocker.PRODUCTION_EVIDENCE_BLOCKED
        )
        self.assertEqual(service.run_calls, 0)
        state = controller.snapshot()
        self.assertEqual(state.active_attempts, ())
        self.assertEqual([(a.status, a.ended_at) for a in state.attempts], [("blocked", 1100)])
        self.assertIsNone(state.attempts[0].delivery_receipt)
        self.world.authority.revoked_digests.clear()
        self.world.lease_port.on_call = None
        self.assertEqual(self.run_attempt(runner, "attempt-2").attempt.status, "accepted")

    def test_revocation_before_completion_then_recovery_is_inconclusive_without_admission(self):
        controller, service, runner, _ = self.build(
            hook=lambda: self.world.authority.revoked_purposes.add(P.ATTEMPT_DELIVERY)
        )
        with self.assertRaises(PilotExecutionError) as raised:
            self.run_attempt(runner)
        self.assertEqual(
            raised.exception.blocker, PilotExecutionBlocker.PRODUCTION_EVIDENCE_BLOCKED
        )
        self.assertEqual(service.run_calls, 1)
        self.assertEqual([a.attempt_id for a in controller.snapshot().active_attempts], ["attempt-1"])
        # Recovery needs no live admission, never calls the service, never re-dispatches.
        self.world.authority.fail = True
        recovered = runner.reconcile_from_observation("attempt-1")
        self.assertEqual(recovered.attempt.status, "inconclusive")
        self.assertIsNone(recovered.observation)
        self.assertEqual((service.run_calls, service.observe_calls), (1, 0))
        state = controller.snapshot()
        self.assertEqual(state.active_attempts, ())
        self.assertEqual([a.status for a in state.attempts], ["inconclusive"])
        self.assertIsNone(state.attempts[0].delivery_receipt)

    def test_crash_recovered_attempt_is_never_credited_or_closed_no_effect(self):
        controller, service, runner, plan = self.build(fail=True)
        with self.assertRaises(PilotExecutionError) as raised:
            self.run_attempt(runner)
        self.assertEqual(raised.exception.blocker, PilotExecutionBlocker.RECONCILIATION_REQUIRED)
        resumed, resumed_service, resumed_runner, _ = self.build()
        with self.assertRaises(PilotExecutionError):
            self.run_attempt(resumed_runner)
        result = resumed_runner.reconcile_from_observation("attempt-1")
        self.assertEqual(result.attempt.status, "inconclusive")
        self.assertEqual(resumed_service.run_calls, 0)
        self.assertEqual(
            [a.status for a in resumed.snapshot().attempts].count("accepted"), 0
        )

    def test_recovery_after_the_pilot_window_is_not_clamped_or_fabricated(self):
        controller, _, runner, plan = self.build(fail=True)
        with self.assertRaises(PilotExecutionError):
            self.run_attempt(runner)
        before = controller.snapshot()
        self.world.clock.value = plan.ends_at + 50
        with self.assertRaises(PilotExecutionError) as raised:
            runner.reconcile_from_observation("attempt-1")
        self.assertEqual(
            raised.exception.blocker, PilotExecutionBlocker.ATTEMPT_UNRESOLVED_AFTER_WINDOW
        )
        after = controller.snapshot()
        self.assertEqual([a.attempt_id for a in after.active_attempts], ["attempt-1"])
        self.assertEqual(after.attempts, ())
        self.assertEqual(after.observed_through, before.observed_through)
        self.assertIn(
            "pilot-attempt-attempt-1-unresolved", {o.obligation_id for o in after.obligations}
        )

    def test_reload_and_repeated_public_calls_revalidate_and_never_replay_cached_success(self):
        _, _, runner, plan = self.build()
        result = self.run_attempt(runner)
        reloaded = PilotController(
            PilotStore(self.tmp / "pilot"), plan, production=self.world.context()
        )
        first = len(self.world.authority.calls)
        self.assertEqual(reloaded.report().obligations, ())
        second = len(self.world.authority.calls)
        reloaded.report()
        self.assertGreater(second, first)
        self.assertGreater(len(self.world.authority.calls), second)
        revision = reloaded.snapshot().revision
        self.world.authority.revoked_purposes.add(P.ATTEMPT_DELIVERY)
        report = reloaded.report()
        self.assertIn(
            "production-evidence-evidence-revoked", {o.obligation_id for o in report.obligations}
        )
        self.assertEqual(report.disposition(), Disposition.BLOCKED_AUTHORITY)
        for action in (reloaded.complete_attempt, reloaded.record_attempt):
            with self.subTest(action.__name__):
                self.assertBlocked(EvidenceBlocker.EVIDENCE_REVOKED, action, result.attempt)
        self.assertEqual(reloaded.snapshot().revision, revision)

    def test_mode_is_fixed_by_construction_and_checked_on_every_entry(self):
        _, _, _, plan = self.build()
        root = self.tmp / "pilot"
        self.assertBlocked(
            EvidenceBlocker.MODE_MISMATCH, PilotController, PilotStore(root), plan
        )
        local_root = self.tmp / "local"
        PilotController(PilotStore(local_root), plan)
        self.assertBlocked(
            EvidenceBlocker.MODE_MISMATCH, PilotController, PilotStore(local_root), plan,
            production=self.world.context(),
        )
        path = local_root / "pilot-current.json"
        document = json.loads(path.read_text())
        del document["evidence_mode"]
        path.write_text(json.dumps(document))
        self.assertBlocked(
            EvidenceBlocker.MODE_MISMATCH, PilotController, PilotStore(local_root), plan,
            production=self.world.context(),
        )
        PilotController(PilotStore(local_root), plan)  # legacy state still opens locally
        controller = PilotController(
            PilotStore(self.tmp / "fresh"), plan, production=self.world.context()
        )
        fresh = self.tmp / "fresh" / "pilot-current.json"
        document = json.loads(fresh.read_text())
        document["evidence_mode"] = MODE_TRUSTED_LOCAL
        fresh.write_text(json.dumps(document))
        for name, action in {
            "report": controller.report,
            "begin": lambda: controller.begin_attempt(
                attempt_id="x", subject_id="self", family_id="f", started_at=1100
            ),
            "observation": lambda: controller.record_observation(1500),
            "controls": lambda: controller.record_controls(duplicate_effects=0),
            "snapshot": controller.snapshot,
        }.items():
            with self.subTest(name):
                self.assertBlocked(EvidenceBlocker.MODE_MISMATCH, action)

    def test_hand_edited_empty_obligations_do_not_clear_rederived_blockers(self):
        plan = self.plan(PilotPrerequisites())
        controller, service, runner, _ = self.build(plan=plan)
        path = self.tmp / "pilot" / "pilot-current.json"
        document = json.loads(path.read_text())
        self.assertTrue(document["obligations"])
        document["obligations"] = []
        path.write_text(json.dumps(document))
        ids = {item.obligation_id for item in controller.report().obligations}
        self.assertTrue(
            {PilotBlockerCode.MISSING_WHOLE_OS_HOST, PilotBlockerCode.MISSING_SUPERVISOR,
             PilotBlockerCode.MISSING_AUTHORITY, PilotBlockerCode.MISSING_BENCHMARK} <= ids
        )
        with self.assertRaises(PilotExecutionError):
            self.run_attempt(runner)
        self.assertEqual(service.run_calls, 0)

    def test_forged_cross_attempt_and_wrong_issuer_delivery_receipts_are_refused(self):
        controller, _, _, _ = self.build()
        state = controller.snapshot()

        def accepted(attempt_id, receipt):
            return PilotAttempt(
                attempt_id, "self", "feature", CAND, "accepted", receipt, 1100, 1100
            )

        ghost = EvidenceRef(
            NAMESPACE + "ghost", CAND, EvidenceKind.EXTERNAL_RECEIPT, "self", 1100
        )
        other = self.world.delivery("attempt-a", "self", started=1100, ended=1100)
        by_attestor = self.world.delivery(
            "attempt-b", "self", started=1100, ended=1100, signer=self.world.attestor
        )
        cases = {
            "forged": (accepted("attempt-b", ghost), EvidenceBlocker.STORE_UNAVAILABLE),
            "cross-attempt": (accepted("attempt-b", other), EvidenceBlocker.CONTEXT_MISMATCH),
            "wrong role": (accepted("attempt-b", by_attestor), EvidenceBlocker.ISSUER_REMIT),
        }
        for label, (attempt, blocker) in cases.items():
            with self.subTest(label):
                self.assertBlocked(blocker, controller.record_attempt, attempt)
                after = controller.snapshot()
                self.assertEqual((after.revision, after.attempts, after.active_attempts),
                                 (state.revision, (), ()))

    def test_nonaccepted_records_need_no_admission_or_lease_but_accepted_needs_both(self):
        controller, _, _, _ = self.build(lease=False)
        self.world.authority.fail = True
        failed = PilotAttempt("attempt-f", "self", "feature", CAND, "failed", None, 1100, 1100)
        controller.record_attempt(failed)
        self.assertEqual([a.status for a in controller.snapshot().attempts], ["failed"])
        self.world.authority.fail = False
        receipt = self.world.delivery("attempt-g", "self", started=1100, ended=1100)
        accepted = PilotAttempt(
            "attempt-g", "self", "feature", CAND, "accepted", receipt, 1100, 1100
        )
        self.assertBlocked(EvidenceBlocker.LEASE_MAPPING_MISSING, controller.record_attempt, accepted)

    def successes(self):
        return sum(
            row.kind == "production-evidence-success" for row in self.world.ledger.read()
        )

    def racing(self, plan=None, *, production=True):
        store = InterleavedStore(Path(tempfile.mkdtemp(dir=self.tmp)))
        controller = PilotController(
            store, plan or self.plan(),
            production=self.world.context() if production else None,
        )
        return store, controller

    def race(self, store, first, second):
        """Run ``second`` until it has read its pre-check state, complete ``first`` on this
        thread, then let ``second`` reach its compared transition."""
        outcomes = {}

        def call(name, action):
            try:
                outcomes[name] = ("ok", action())
            except Exception as error:  # noqa: BLE001 - captured for the assertions
                outcomes[name] = ("error", error)

        store.hold = "second"
        thread = threading.Thread(target=call, args=("second", second), name="second")
        thread.start()
        self.assertTrue(store.reached.wait(15), "second caller never reached its transition")
        try:
            call("first", first)
        finally:
            store.release.set()
        thread.join(15)
        self.assertFalse(thread.is_alive())
        return outcomes

    BEGIN = dict(attempt_id="same", subject_id="self", family_id="feature", started_at=1100)

    def accepted_same(self):
        receipt = self.world.delivery("same", "self", started=1100, ended=1100)
        return PilotAttempt("same", "self", "feature", CAND, "accepted", receipt, 1100, 1100)

    def test_concurrent_identical_completions_credit_and_charge_exactly_once(self):
        plan = PilotPlan(
            "pilot", "self", CAND, ("self",), STARTS, ENDS, 1, 10, 1, AUTH,
            self.world.prerequisites(),
        )
        store, controller = self.racing(plan)
        controller.begin_attempt(**self.BEGIN)
        begun = controller.snapshot().revision
        attempt = self.accepted_same()
        outcomes = self.race(
            store, lambda: controller.complete_attempt(attempt),
            lambda: controller.complete_attempt(attempt),
        )
        self.assertEqual({k: v[0] for k, v in outcomes.items()}, {"first": "ok", "second": "ok"})
        state = controller.snapshot()
        self.assertEqual([a.attempt_id for a in state.attempts], ["same"])
        self.assertEqual((state.revision, state.active_attempts), (begun + 1, ()))
        self.assertEqual(outcomes["second"][1], state)  # the same bound state, not a copy
        self.assertEqual(sum(a.resource_units for a in state.attempts), 1)
        self.assertEqual(len(store.history.read_text().splitlines()), 3)  # no extra write
        self.assertEqual(controller.report().obligations, ())  # unique identities

    def test_concurrent_conflicting_completion_never_appends_or_replaces(self):
        inconclusive = PilotAttempt(
            "same", "self", "feature", CAND, "inconclusive", None, 1100, 1100
        )
        for label, first_is_accepted in {
            "accepted then inconclusive": True, "inconclusive then accepted": False,
        }.items():
            with self.subTest(label):
                store, controller = self.racing()
                controller.begin_attempt(**self.BEGIN)
                accepted = self.accepted_same()
                first, second = (
                    (accepted, inconclusive) if first_is_accepted else (inconclusive, accepted)
                )
                outcomes = self.race(
                    store, lambda f=first: controller.complete_attempt(f),
                    lambda s=second: controller.complete_attempt(s),
                )
                self.assertEqual(outcomes["first"][0], "ok")
                self.assertEqual(outcomes["second"][0], "error")
                self.assertIsInstance(outcomes["second"][1], ValueError)
                self.assertIn("different content", str(outcomes["second"][1]))
                state = controller.snapshot()
                self.assertEqual(state.attempts, (first,))
                self.assertEqual(state.active_attempts, ())
                self.assertEqual(
                    sum(a.status == "accepted" for a in state.attempts), int(first_is_accepted)
                )

    def test_concurrent_begins_charge_once_and_never_reopen_or_duplicate(self):
        units = dict(self.BEGIN, resource_units=3)
        store, controller = self.racing()
        outcomes = self.race(
            store, lambda: controller.begin_attempt(**units),
            lambda: controller.begin_attempt(**units),
        )
        self.assertEqual({k: v[0] for k, v in outcomes.items()}, {"first": "ok", "second": "ok"})
        state = controller.snapshot()
        self.assertEqual([(a.attempt_id, a.resource_units) for a in state.active_attempts],
                         [("same", 3)])
        self.assertEqual((state.revision, len(store.history.read_text().splitlines())), (1, 2))

        store, controller = self.racing()
        outcomes = self.race(
            store, lambda: controller.begin_attempt(**self.BEGIN),
            lambda: controller.begin_attempt(**dict(self.BEGIN, family_id="other")),
        )
        self.assertIn("different content", str(outcomes["second"][1]))
        self.assertEqual(
            [a.family_id for a in controller.snapshot().active_attempts], ["feature"]
        )

        store, controller = self.racing()
        failed = PilotAttempt("same", "self", "feature", CAND, "failed", None, 1100, 1100)
        outcomes = self.race(
            store, lambda: controller.record_attempt(failed),
            lambda: controller.begin_attempt(**self.BEGIN),
        )
        self.assertEqual(outcomes["first"][0], "ok")
        self.assertIn("already complete", str(outcomes["second"][1]))
        state = controller.snapshot()
        self.assertEqual((state.attempts, state.active_attempts), ((failed,), ()))

    def test_concurrent_crash_recoveries_close_one_inconclusive_attempt(self):
        store, controller = self.racing()
        service = self.Service(controller)
        runner = WholeOSPilotRunner(
            controller, service, self.Evaluator(self.world), clock=self.world.clock
        )
        controller.begin_attempt(**self.BEGIN)
        outcomes = self.race(
            store, lambda: runner.reconcile_from_observation("same"),
            lambda: runner.reconcile_from_observation("same"),
        )
        self.assertEqual({k: v[0] for k, v in outcomes.items()}, {"first": "ok", "second": "ok"})
        state = controller.snapshot()
        self.assertEqual([(a.attempt_id, a.status) for a in state.attempts],
                         [("same", "inconclusive")])
        self.assertEqual((state.active_attempts, service.run_calls), ((), 0))

    def test_trusted_local_completion_race_and_store_compare_and_swap_are_preserved(self):
        store, controller = self.racing(production=False)
        controller.begin_attempt(**self.BEGIN)
        stale = store.load()
        failed = PilotAttempt("same", "self", "feature", CAND, "failed", None, 1100, 1100)
        outcomes = self.race(
            store, lambda: controller.complete_attempt(failed),
            lambda: controller.complete_attempt(failed),
        )
        self.assertEqual({k: v[0] for k, v in outcomes.items()}, {"first": "ok", "second": "ok"})
        self.assertEqual(controller.snapshot().attempts, (failed,))
        # The real compare-and-swap still refuses a write over a newer revision.
        before = controller.snapshot()
        with self.assertRaisesRegex(ValueError, "stale"):
            store.save(replace(stale, revision=stale.revision + 1), expected_revision=stale.revision)
        self.assertEqual(controller.snapshot(), before)

    def test_accepted_credit_replay_and_completion_rederive_every_structural_prerequisite(self):
        w = self.world
        receipt = w.delivery("direct", "self", started=1100, ended=1100)
        attempt = PilotAttempt("direct", "self", "feature", CAND, "accepted", receipt, 1100, 1100)
        full, _, _, _ = self.build(root=self.tmp / "full")
        # Valid positive: the complete plan credits, audits success, and replays.
        credited = full.record_attempt(attempt)
        self.assertEqual([a.status for a in credited.attempts], ["accepted"])
        self.assertEqual(full.record_attempt(attempt), credited)
        self.assertEqual(full.complete_attempt(attempt), credited)
        durable = json.loads((self.tmp / "full" / "pilot-current.json").read_text())
        full_prerequisites = w.prerequisites()
        omissions = {
            "whole_os_host": "missing-whole-os-host",
            "supervisor": "missing-supervisor",
            "delivery_authority": "missing-delivery-authority",
            "benchmark_candidate": "missing-benchmark-candidate",
            "all": "missing-whole-os-host",
        }
        for omission, blocker_id in omissions.items():
            with self.subTest(omission):
                prerequisites = (
                    PilotPrerequisites()
                    if omission == "all"
                    else replace(full_prerequisites, **{omission: None})
                )
                root = self.tmp / f"missing-{omission}"
                controller, service, runner, _ = self.build(
                    plan=self.plan(prerequisites), root=root
                )
                # Fresh accepted record: refused before any durable credit or success audit.
                before = (controller.snapshot(), self.successes())
                error = self.assertBlocked(
                    EvidenceBlocker.INCOMPLETE, controller.record_attempt, attempt
                )
                self.assertIn(blocker_id, error.detail)
                self.assertEqual((controller.snapshot(), self.successes()), before)
                self.assertEqual(self.world.ledger.read()[-1].kind, "production-evidence-failure")
                # Active accepted completion is refused and the attempt stays active.
                controller._begin(
                    attempt_id="direct", subject_id="self", family_id="feature", started_at=1100
                )
                active = controller.snapshot()
                self.assertBlocked(EvidenceBlocker.INCOMPLETE, controller.complete_attempt, attempt)
                self.assertEqual(controller.snapshot(), active)
                self.assertEqual(self.successes(), before[1])
                # Permitted recovery needs no admission and is still an inconclusive close.
                self.world.authority.fail = True
                closed = controller.complete_attempt(
                    PilotAttempt("direct", "self", "feature", CAND, "inconclusive", None, 1100, 1100)
                )
                self.world.authority.fail = False
                self.assertEqual([a.status for a in closed.attempts], ["inconclusive"])
                self.assertEqual(closed.active_attempts, ())
                # Idempotent replay / reload of hand-edited durable credit is not trusted.
                path = root / "pilot-current.json"
                document = json.loads(path.read_text())
                document["attempts"], document["active_attempts"] = durable["attempts"], []
                path.write_text(json.dumps(document))
                reloaded = PilotController(
                    PilotStore(root), self.plan(prerequisites), production=self.world.context()
                )
                edited = reloaded.snapshot()
                for action in (reloaded.record_attempt, reloaded.complete_attempt):
                    with self.subTest(omission=omission, replay=action.__name__):
                        self.assertBlocked(EvidenceBlocker.INCOMPLETE, action, attempt)
                self.assertEqual(reloaded.snapshot(), edited)
                self.assertIn(
                    blocker_id, {o.obligation_id for o in reloaded.report().obligations}
                )
                # The runner never reaches the host for the same plan.
                with self.assertRaises(PilotExecutionError):
                    self.run_attempt(runner, "other")
                self.assertEqual(service.run_calls, 0)

    def test_controls_and_observation_evidence_are_authenticated(self):
        self.world.clock.value = 2000
        controller, _, _, _ = self.build()
        ghost = EvidenceRef(NAMESPACE + "ghost", CAND, EvidenceKind.EXTERNAL_RECEIPT, "pilot", 1500)
        revision = controller.snapshot().revision
        self.assertBlocked(
            EvidenceBlocker.STORE_UNAVAILABLE, controller.record_controls,
            restart_exercised=True, restart_evidence=ghost,
        )
        self.assertBlocked(
            EvidenceBlocker.STORE_UNAVAILABLE, controller.record_observation, 1500, evidence=ghost
        )
        self.assertEqual(controller.snapshot().revision, revision)
        w = self.world
        restart = w.receipt(P.PILOT_RESTART, w.attestor, subject="pilot", operation="pilot",
                            claims=MODE, observed=1500, issued=1500, name="restart")
        rollback = w.receipt(P.PILOT_ROLLBACK_CONTROL, w.attestor, subject="pilot",
                             operation="pilot", claims=MODE, observed=900, issued=950,
                             name="rollback")
        observation = w.receipt(P.PILOT_OBSERVATION, w.attestor, subject="pilot",
                                operation="pilot", claims={"observed_through": 1500},
                                observed=1500, issued=1500, name="observed")
        controller.record_controls(
            restart_exercised=True, restart_evidence=restart, rollback_evidence=rollback
        )
        controller.record_observation(1500, evidence=observation)
        self.assertTrue(controller.snapshot().restart_exercised)
        # Recording an obligation is recovery, so it works while the authority is down.
        w.authority.fail = True
        controller.record_controls(
            obligations=(ExternalObligation("note", Disposition.BLOCKED_SOURCE, "detail", ("N31",)),)
        )
        self.assertBlocked(
            EvidenceBlocker.STATUS_UNAVAILABLE, controller.record_controls,
            restart_exercised=True, restart_evidence=restart,
        )
        w.authority.fail = False
        w.authority.revoked_digests.add(observation.digest)
        report = controller.report()
        self.assertIn(
            "production-evidence-evidence-revoked", {o.obligation_id for o in report.obligations}
        )


class ProductionCloseoutTests(ProductionCase):
    def build_closeout(self, *, broken=None, judge=None, judge_times=(210, 220),
                       sealed_at=200, rationale="All scoped evidence passed.",
                       witnesses=(), same_issuer_twice=False, judge_id="judge-1",
                       builder_id="builder-1"):
        w = self.world

        def evidence(key, purpose, subject, claims, signer=None, **times):
            if key == broken:
                return EvidenceRef(
                    NAMESPACE + f"missing-{key}", CAND, EvidenceKind.EXTERNAL_RECEIPT, subject, 100
                )
            return w.receipt(
                purpose, signer or w.attestor, subject=subject, operation="release-1",
                claims=claims, observed=times.get("observed", 100),
                issued=times.get("issued", 110), authority=None, name=key,
            )

        builder = CloseoutBuilder(
            release_id="release-1", candidate_digest=CAND,
            previous_release_digest=PREV, builder_id=builder_id,
        )
        for rid in REQUIREMENT_IDS:
            disposition = Disposition.DEFER if rid == "R05" else Disposition.ADOPT
            builder.record_requirement(
                rid, disposition,
                (evidence(f"req-{rid}", P.CLOSEOUT_REQUIREMENT, rid,
                          {"disposition": disposition.value, "obligation_ids": []}),),
                rationale="deferred with evidence" if rid == "R05" else "",
            )
        for nid in NODE_IDS:
            builder.disposition_node(
                nid, Disposition.ADOPT,
                (evidence(f"node-{nid}", P.CLOSEOUT_NODE, nid,
                          {"disposition": "adopt", "obligation_ids": []}),),
            )
        for role in sorted(SPECIALIST_ROLE_IDS):
            refs = [evidence(f"role-{role}", P.CLOSEOUT_ROLE, role, {"role_id": role})]
            if role == "architect":
                for index, signer in enumerate(witnesses):
                    refs.append(evidence(f"role-{role}-w{index}", P.CLOSEOUT_ROLE, role,
                                         {"role_id": role}, signer=signer))
                if same_issuer_twice:
                    refs.append(evidence("role-architect-again", P.CLOSEOUT_ROLE, role,
                                         {"role_id": role}, observed=101))
            builder.record_role(role, refs)
        for stage in sorted(LIFECYCLE_STAGE_IDS):
            builder.record_lifecycle_stage(
                stage, (evidence(f"stage-{stage}", P.CLOSEOUT_STAGE, stage, {"stage_id": stage}),)
            )

        def operation(name, purpose):
            claims = {"argv": ["hive-mind", name], "exit_code": 0}
            return OperationalReceipt(
                ("hive-mind", name), CAND, 0, evidence(name, purpose, CAND, claims)
            )

        manifest = builder.seal(
            startup_receipt=operation("start", P.CLOSEOUT_STARTUP),
            rollback_receipt=operation("rollback", P.CLOSEOUT_ROLLBACK),
            independent_judge_id=judge_id, final_disposition=Disposition.ADOPT,
            final_rationale=rationale, sealed_at=sealed_at,
        )
        digest = manifest_digest(manifest)
        observed, issued = judge_times
        judgment = w.receipt(
            P.CLOSEOUT_JUDGMENT, judge or w.judge, subject="release-1", operation="release-1",
            claims={
                "manifest_digest": digest, "release_id": "release-1",
                "previous_release_digest": PREV, "sealed_at": sealed_at,
                "final_disposition": "adopt", "independent_judge_id": judge_id,
            },
            observed=observed, issued=issued, authority=None, name="judgment",
        )
        w.clock.value = 300
        return manifest, digest, judgment

    def test_positive_closeout_after_the_pilot_with_exact_manifest_digest(self):
        manifest, digest, judgment = self.build_closeout(rationale="Résumé passed.")
        verified = verify_production_closeout(manifest, digest, judgment, self.world.context())
        self.assertTrue(verified.positive)
        self.assertEqual(verified.manifest_digest, digest)
        # 18 + 34 assessments, 8 roles, 7 stages, startup, rollback and the detached judge.
        self.assertEqual(len(verified.resolution_digests), 70)
        document = {"schema_version": 1, **asdict(manifest)}
        self.assertEqual(digest, canonical_digest(document))
        self.assertNotEqual(digest, kernel_digest(document))
        path = self.tmp / "release-1.json"
        self.assertEqual(write_release_manifest(path, manifest), digest)
        self.assertNotEqual(digest, sha(path.read_bytes()))
        self.assertEqual(self.world.ledger.read()[-1].kind, "production-evidence-success")
        loaded, again = load_verified_release_manifest(path, judgment, self.world.context())
        self.assertEqual((loaded, again.manifest_digest), (manifest, digest))
        self.assertBlocked(
            EvidenceBlocker.DIGEST_MISMATCH, verify_production_closeout, manifest,
            kernel_digest(document), judgment, self.world.context(),
        )

    def test_every_nested_reference_is_walked_including_negative_dispositions(self):
        keys = ["req-R01", "req-R05", "node-N30", "role-builder", "role-architect",
                "stage-validate", "start", "rollback"]
        for key in keys:
            with self.subTest(key):
                manifest, digest, judgment = self.build_closeout(broken=key)
                self.assertBlocked(
                    EvidenceBlocker.STORE_UNAVAILABLE, verify_production_closeout,
                    manifest, digest, judgment, self.world.context(),
                )
                self.assertEqual(self.world.ledger.read()[-1].kind, "production-evidence-failure")

    def test_label_only_manifest_is_structurally_valid_but_never_production_positive(self):
        manifest, digest, judgment = self.build_closeout(broken="req-R01")
        path = self.tmp / "release-1.json"
        write_release_manifest(path, manifest)  # honest raw structural view still works
        self.assertBlocked(
            EvidenceBlocker.STORE_UNAVAILABLE, load_verified_release_manifest, path, judgment,
            self.world.context(),
        )
        # An existing file is not a fast path: verification runs before any write.
        self.assertBlocked(
            EvidenceBlocker.STORE_UNAVAILABLE, write_verified_release_manifest, path,
            manifest, judgment, self.world.context(),
        )
        fresh = self.tmp / "never-written.json"
        self.assertBlocked(
            EvidenceBlocker.STORE_UNAVAILABLE, write_verified_release_manifest, fresh,
            manifest, judgment, self.world.context(),
        )
        self.assertFalse(fresh.exists())

    def test_detached_judge_binding_time_and_configured_separation(self):
        w = self.world
        manifest, digest, judgment = self.build_closeout(judge_times=(150, 160))
        self.assertBlocked(
            EvidenceBlocker.TIME_WINDOW, verify_production_closeout, manifest, digest,
            judgment, w.context(),
        )
        manifest, digest, judgment = self.build_closeout()
        changed = replace(manifest, final_rationale="Changed after the judge signed.")
        self.assertBlocked(
            EvidenceBlocker.CONTEXT_MISMATCH, verify_production_closeout, changed,
            manifest_digest(changed), judgment, w.context(),
        )
        self.assertBlocked(
            EvidenceBlocker.DIGEST_MISMATCH, verify_production_closeout, manifest, PREV,
            judgment, w.context(),
        )
        m2, d2, j2 = self.build_closeout(judge_id="judge-2", judge=w.judge2)
        self.assertEqual(
            verify_production_closeout(m2, d2, j2, w.context()).independent_judge_id,
            "judge-2",
        )
        # The receipt is signed by judge-1 while the sealed manifest names judge-2.
        m3, d3, j3 = self.build_closeout(judge_id="judge-2", judge=w.judge)
        self.assertBlocked(
            EvidenceBlocker.SEPARATION, verify_production_closeout, m3, d3, j3, w.context()
        )
        # Names alone are insufficient: each must be a configured principal of its role.
        separation_cases = {
            "unconfigured builder name": (
                dict(builder_id="builder-x"), EvidenceBlocker.ISSUER_UNKNOWN),
            "judge is only an attestor": (
                dict(judge_id="attestor-1", judge=w.attestor), EvidenceBlocker.SEPARATION),
            "builder is a judge principal": (
                dict(builder_id="judge-2"), EvidenceBlocker.SEPARATION),
        }
        for label, (kwargs, blocker) in separation_cases.items():
            with self.subTest(label):
                m4, d4, j4 = self.build_closeout(**kwargs)
                self.assertBlocked(blocker, verify_production_closeout, m4, d4, j4, w.context())
        with self.assertRaises(ValueError):  # the existing seal rule still applies
            self.build_closeout(builder_id="judge-1")

    def successes(self):
        return sum(
            row.kind == "production-evidence-success" for row in self.world.ledger.read()
        )

    def rebound_judgment(self, manifest):
        """A genuinely signed, fresh judgment over exactly the (malformed) digest."""
        w = self.world
        return w.receipt(
            P.CLOSEOUT_JUDGMENT, w.judge, subject=manifest.release_id,
            operation=manifest.release_id,
            claims={
                "manifest_digest": manifest_digest(manifest),
                "release_id": manifest.release_id,
                "previous_release_digest": PREV, "sealed_at": manifest.sealed_at,
                "final_disposition": manifest.final_disposition.value,
                "independent_judge_id": manifest.independent_judge_id,
            },
            observed=210, issued=220, authority=None, name="rebound-judgment",
        )

    def test_mutated_manifest_cannot_launder_a_malformed_shape_through_a_real_judge(self):
        w = self.world
        fields = {
            "nodes": ["node_assessments"],
            "requirements": ["requirement_assessments"],
            "roles": ["role_evidence"],
            "lifecycle": ["lifecycle_evidence"],
            "all four": ["node_assessments", "requirement_assessments",
                         "role_evidence", "lifecycle_evidence"],
        }
        for label, selected in fields.items():
            with self.subTest(label):
                manifest, _, _ = self.build_closeout()
                for field in selected:  # ordinary public mapping mutation
                    getattr(manifest, field).clear()
                judgment = self.rebound_judgment(manifest)
                digest = manifest_digest(manifest)  # the raw digest of the malformed content
                target = self.tmp / f"malformed-{label}.json"
                before = (self.successes(), len(w.authority.calls))
                self.assertBlocked(
                    EvidenceBlocker.MANIFEST_MALFORMED, verify_production_closeout,
                    manifest, digest, judgment, w.context(),
                )
                self.assertBlocked(
                    EvidenceBlocker.MANIFEST_MALFORMED, write_verified_release_manifest,
                    target, manifest, judgment, w.context(),
                )
                # Rejected before any resolution, positive audit or file.
                self.assertEqual((self.successes(), len(w.authority.calls)), before)
                self.assertEqual(w.ledger.read()[-1].kind, "production-evidence-failure")
                self.assertFalse(target.exists())

    def test_nested_mutations_and_wrong_types_are_rejected_before_resolution(self):
        w = self.world
        mutations = {
            "assessment replaced by text": lambda m: m.requirement_assessments.update(R01="x"),
            "assessment key dropped": lambda m: m.node_assessments.pop("N07"),
            "assessment moved to another key": lambda m: m.node_assessments.update(
                N07=m.node_assessments["N08"]
            ),
            "role evidence emptied": lambda m: m.role_evidence.update(builder=()),
            "role evidence not references": lambda m: m.role_evidence.update(builder=("x",)),
            "stage evidence replaced by text": lambda m: m.lifecycle_evidence.update(build="x"),
            "unknown role added": lambda m: m.role_evidence.update(
                extra=m.role_evidence["builder"]
            ),
            "collection is not a mapping": lambda m: object.__setattr__(m, "node_assessments", []),
            "wrong manifest type": None,
        }
        for label, mutate in mutations.items():
            with self.subTest(label):
                manifest, digest, judgment = self.build_closeout()
                candidate = manifest if mutate else {"release_id": "release-1"}
                if mutate:
                    mutate(manifest)
                before = (self.successes(), len(w.authority.calls))
                self.assertBlocked(
                    EvidenceBlocker.MANIFEST_MALFORMED, verify_production_closeout,
                    candidate, digest, judgment, w.context(),
                )
                self.assertEqual((self.successes(), len(w.authority.calls)), before)

    def test_verified_content_is_stable_against_mutation_during_resolution(self):
        w = self.world
        manifest, digest, judgment = self.build_closeout()

        class MutatingStore:
            def __init__(self, inner, action):
                self.inner, self.action = inner, action

            def read(self, uri, max_bytes, deadline_seconds):
                action, self.action = self.action, None
                if action:
                    action()
                return self.inner.read(uri, max_bytes, deadline_seconds)

        def tamper():
            manifest.node_assessments.clear()
            manifest.role_evidence.clear()

        store = MutatingStore(w.store, tamper)
        target = self.tmp / "stable.json"
        verified = write_verified_release_manifest(
            target, manifest, judgment, w.context(store=store)
        )
        self.assertEqual(manifest.node_assessments, {})  # the caller's copy really changed
        self.assertEqual(len(verified.resolution_digests), 70)
        self.assertEqual(verified.manifest_digest, digest)
        loaded, again = load_verified_release_manifest(target, judgment, w.context())
        self.assertEqual(again.manifest_digest, digest)
        self.assertEqual(len(loaded.node_assessments), len(NODE_IDS))
        self.assertEqual(manifest_digest(loaded), digest)
        loaded.node_assessments.clear()  # mutating the returned snapshot changes nothing durable
        self.assertEqual(
            load_verified_release_manifest(target, judgment, w.context())[1].manifest_digest,
            digest,
        )

    def test_multiple_witnesses_are_legal_but_one_issuer_is_not_counted_twice(self):
        w = self.world
        manifest, digest, judgment = self.build_closeout(witnesses=(w.attestor2,))
        verified = verify_production_closeout(manifest, digest, judgment, w.context())
        self.assertEqual(len(verified.resolution_digests), 71)
        manifest, digest, judgment = self.build_closeout(same_issuer_twice=True)
        self.assertBlocked(
            EvidenceBlocker.DUPLICATE_EVIDENCE, verify_production_closeout, manifest, digest,
            judgment, w.context(),
        )

    def test_revocation_and_unavailable_status_fail_each_repeated_verification(self):
        w = self.world
        manifest, digest, judgment = self.build_closeout()
        context = w.context()
        verify_production_closeout(manifest, digest, judgment, context)
        w.authority.revoked_digests.add(judgment.digest)
        self.assertBlocked(
            EvidenceBlocker.EVIDENCE_REVOKED, verify_production_closeout, manifest, digest,
            judgment, context,
        )
        w.authority.revoked_digests.clear()
        w.authority.fail = True
        self.assertBlocked(
            EvidenceBlocker.STATUS_UNAVAILABLE, verify_production_closeout, manifest, digest,
            judgment, context,
        )

    def test_unwritable_audit_never_yields_a_positive_result(self):
        manifest, digest, judgment = self.build_closeout()
        directory = self.tmp / "ledger-is-a-directory"
        directory.mkdir()
        context = ProductionEvidenceContext(
            self.world.resolver(), self.world.clock, QualificationLedger(directory)
        )
        self.assertBlocked(
            EvidenceBlocker.AUDIT_UNAVAILABLE, verify_production_closeout, manifest, digest,
            judgment, context,
        )

    def test_concurrent_audit_appends_keep_the_ledger_chain_valid(self):
        w = self.world
        ref = w.receipt(
            P.PILOT_HOST, w.attestor, subject="pilot", operation="pilot", claims=MODE,
            observed=900, issued=950,
        )
        use = use_for(P.PILOT_HOST, "pilot", "pilot", MODE, window_end=STARTS)
        context = w.context()
        errors = []

        def work():
            try:
                context.verify("concurrent", [(ref, use)])
            except Exception as error:  # noqa: BLE001 - reported below
                errors.append(error)

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        rows = w.ledger.read()  # raises if the chain is invalid
        self.assertEqual([row.kind for row in rows], ["production-evidence-success"] * 8)


if __name__ == "__main__":
    unittest.main()
