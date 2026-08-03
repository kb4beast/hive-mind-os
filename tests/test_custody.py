from __future__ import annotations

import asyncio
import base64
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.custody import (
    CUSTODY_AUDIENCE,
    CustodyError,
    CustodyProvenanceStore,
    CustodySubject,
    Ed25519CustodyVerifier,
    ExternalCustodyAdapter,
    TrustAnchor,
)
from hive_mind_os.mission import RepositoryMission, ScriptedRepositoryBackend
from hive_mind_os.mission_store import (
    MissionStore,
    MissionStoreError,
    StoreIntegrityError,
    resume_mission,
)
from hive_mind_os.models import WorkStatus
from hive_mind_os.receipts import ReceiptReference, sha256_digest
from tests.fixtures.fixture_repo import build_fixture_repo


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _signed(document: Mapping[str, object], key: Ed25519PrivateKey, domain: bytes) -> dict[str, object]:
    signed = dict(document)
    payload = {name: value for name, value in signed.items() if name != "signature"}
    import json

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    signed["signature"] = _encoded(key.sign(domain + encoded))
    return signed


class _ExternalTestAttestor:
    """Test-only stand-in for a signer outside the kernel; no key is persisted."""

    def __init__(
        self,
        key: Ed25519PrivateKey,
        *,
        authority_id: str = "custody-authority.example",
        key_id: str = "receipt-key-1",
        identity: str = "custody-signer.example/receipt-1",
        sequence: int = 1,
        now: datetime,
    ) -> None:
        self.key = key
        self.authority_id = authority_id
        self.key_id = key_id
        self.identity = identity
        self.sequence = sequence
        self.now = now
        self._counter = 0

    def attest(self, subject: Mapping[str, object]) -> Mapping[str, object]:
        self._counter += 1
        return _signed(
            {
                "schema_version": 1,
                "attestation_id": f"ATT-TEST-{self.key_id}-{self._counter}",
                "authority_id": self.authority_id,
                "keyset_sequence": self.sequence,
                "signer_identity": self.identity,
                "key_id": self.key_id,
                "algorithm": "ed25519",
                "audience": CUSTODY_AUDIENCE,
                "issued_at": self.now.isoformat(),
                "expires_at": (self.now + timedelta(minutes=5)).isoformat(),
                "nonce": f"test-nonce-{self._counter:012d}",
                "subject": dict(subject),
            },
            self.key,
            b"hive-mind-os/custody-attestation/v1\0",
        )


class ExternalCustodyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        self.root_key = Ed25519PrivateKey.generate()
        self.receipt_key = Ed25519PrivateKey.generate()
        self.next_key = Ed25519PrivateKey.generate()
        self.anchor = TrustAnchor(
            "custody-authority.example",
            "root-key-1",
            "custody-authority.example/root",
            _encoded(self.root_key.public_key().public_bytes_raw()),
        )

    def keyset(
        self,
        sequence: int,
        keys: list[dict[str, object]],
        *,
        issued_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, object]:
        issued = issued_at or self.now
        expires = expires_at or (issued + timedelta(hours=2))
        return _signed(
            {
                "schema_version": 1,
                "authority_id": self.anchor.authority_id,
                "sequence": sequence,
                "issued_at": issued.isoformat(),
                "expires_at": expires.isoformat(),
                "issuer_key_id": self.anchor.key_id,
                "issuer_identity": self.anchor.signer_identity,
                "keys": keys,
            },
            self.root_key,
            b"hive-mind-os/custody-keyset/v1\0",
        )

    def custody_key(
        self,
        key: Ed25519PrivateKey,
        *,
        key_id: str,
        identity: str,
        status: str = "active",
    ) -> dict[str, object]:
        return {
            "key_id": key_id,
            "signer_identity": identity,
            "public_key": _encoded(key.public_key().public_bytes_raw()),
            "status": status,
            "not_before": (self.now - timedelta(days=1)).isoformat(),
            "not_after": None,
            "revoked_at": self.now.isoformat() if status == "revoked" else None,
        }

    def verifier(self, path: str | Path = ":memory:") -> tuple[Ed25519CustodyVerifier, CustodyProvenanceStore]:
        provenance = CustodyProvenanceStore(path)
        verifier = Ed25519CustodyVerifier(
            self.anchor,
            provenance,
            now=lambda: self.now,
        )
        verifier.install_keyset(
            self.keyset(
                1,
                [
                    self.custody_key(
                        self.receipt_key,
                        key_id="receipt-key-1",
                        identity="custody-signer.example/receipt-1",
                    )
                ],
            )
        )
        return verifier, provenance

    @staticmethod
    def configuration() -> dict[str, object]:
        return {
            "repository": "C:/approved/source",
            "objective": "Correct the failing test",
            "pin": "a" * 40,
            "risk": "moderate",
            "acceptance_specifications": [
                {"id": "one", "criterion": "test passes", "command": {"argv": ["python"]}}
            ],
        }

    @staticmethod
    def receipt() -> tuple[dict[str, object], ReceiptReference]:
        reference = ReceiptReference("receipts/one.json", sha256_digest(b"exact receipt bytes"))
        return (
            {
                "receipt_id": "REC-1",
                "mission_id": "M-1",
                "state_ref": "MISSION_STATE:M-1:1",
                "action_id": "ACT-1",
                "action_digest": "sha256:" + "b" * 64,
                "policy_decision_ref": "POLICY-1",
                "lease_id": "LEASE-1",
                "provider": "external-sandbox.example",
                "actor_id": "agent-builder",
                "verified_by": "external-sandbox.example/verifier",
            },
            reference,
        )

    def test_external_adapter_binds_configuration_and_receipt_without_private_key(self) -> None:
        verifier, provenance = self.verifier()
        try:
            adapter = ExternalCustodyAdapter(
                _ExternalTestAttestor(self.receipt_key, now=self.now), verifier
            )
            configuration = self.configuration()
            configuration_attestation = adapter.attest_configuration("M-1", configuration)
            self.assertEqual(configuration_attestation["signer_identity"], "custody-signer.example/receipt-1")

            receipt, reference = self.receipt()
            receipt_attestation = adapter.attest_receipt(receipt, reference)
            self.assertEqual(receipt_attestation["subject"], CustodySubject.receipt(receipt, reference).to_dict())
            self.assertEqual(provenance.attestation_count(), 2)

            altered = copy.deepcopy(configuration)
            altered["pin"] = "c" * 40
            with self.assertRaisesRegex(CustodyError, "expected subject"):
                verifier.verify_configuration("M-1", altered, configuration_attestation)
        finally:
            provenance.close()

    def test_replay_is_durable_but_same_byte_revalidation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custody.sqlite3"
            verifier, provenance = self.verifier(path)
            try:
                attestor = _ExternalTestAttestor(self.receipt_key, now=self.now)
                receipt, reference = self.receipt()
                subject = CustodySubject.receipt(receipt, reference)
                first = dict(attestor.attest(subject.to_dict()))
                verifier.verify(subject, first)
                verifier.verify(subject, first)
                self.assertEqual(provenance.attestation_count(), 1)
            finally:
                provenance.close()
            verifier, provenance = self.verifier(path)
            try:
                verifier.verify(subject, first)
                replay = dict(first)
                replay["attestation_id"] = "ATT-TEST-CONFLICT"
                replay = _signed(
                    {name: value for name, value in replay.items() if name != "signature"},
                    self.receipt_key,
                    b"hive-mind-os/custody-attestation/v1\0",
                )
                with self.assertRaisesRegex(CustodyError, "nonce was replayed"):
                    verifier.verify(subject, replay)
            finally:
                provenance.close()

    def test_attestation_id_cannot_be_reused_for_a_different_envelope(self) -> None:
        verifier, provenance = self.verifier()
        try:
            attestor = _ExternalTestAttestor(self.receipt_key, now=self.now)
            receipt, reference = self.receipt()
            subject = CustodySubject.receipt(receipt, reference)
            first = dict(attestor.attest(subject.to_dict()))
            verifier.verify(subject, first)
            duplicate_id = dict(attestor.attest(subject.to_dict()))
            duplicate_id["attestation_id"] = first["attestation_id"]
            duplicate_id = _signed(
                {name: value for name, value in duplicate_id.items() if name != "signature"},
                self.receipt_key,
                b"hive-mind-os/custody-attestation/v1\0",
            )
            with self.assertRaisesRegex(CustodyError, "ID was replayed"):
                verifier.verify(subject, duplicate_id)
        finally:
            provenance.close()

    def test_rotation_overlap_and_revocation_fail_closed(self) -> None:
        verifier, provenance = self.verifier()
        try:
            verifier.install_keyset(
                self.keyset(
                    2,
                    [
                        self.custody_key(
                            self.receipt_key,
                            key_id="receipt-key-1",
                            identity="custody-signer.example/receipt-1",
                        ),
                        self.custody_key(
                            self.next_key,
                            key_id="receipt-key-2",
                            identity="custody-signer.example/receipt-2",
                        ),
                    ],
                )
            )
            receipt, reference = self.receipt()
            overlap = _ExternalTestAttestor(
                self.receipt_key,
                sequence=2,
                now=self.now,
            )
            verifier.verify_receipt(receipt, reference, overlap.attest(CustodySubject.receipt(receipt, reference).to_dict()))

            verifier.install_keyset(
                self.keyset(
                    3,
                    [
                        self.custody_key(
                            self.receipt_key,
                            key_id="receipt-key-1",
                            identity="custody-signer.example/receipt-1",
                            status="revoked",
                        ),
                        self.custody_key(
                            self.next_key,
                            key_id="receipt-key-2",
                            identity="custody-signer.example/receipt-2",
                        ),
                    ],
                )
            )
            revoked = _ExternalTestAttestor(self.receipt_key, sequence=3, now=self.now)
            with self.assertRaisesRegex(CustodyError, "revoked"):
                verifier.verify_receipt(receipt, reference, revoked.attest(CustodySubject.receipt(receipt, reference).to_dict()))
            current = _ExternalTestAttestor(
                self.next_key,
                key_id="receipt-key-2",
                identity="custody-signer.example/receipt-2",
                sequence=3,
                now=self.now,
            )
            verifier.verify_receipt(receipt, reference, current.attest(CustodySubject.receipt(receipt, reference).to_dict()))

            with self.assertRaisesRegex(CustodyError, "cannot reactivate"):
                verifier.install_keyset(
                    self.keyset(
                        4,
                        [
                            self.custody_key(
                                self.receipt_key,
                                key_id="receipt-key-1",
                                identity="custody-signer.example/receipt-1",
                            ),
                            self.custody_key(
                                self.next_key,
                                key_id="receipt-key-2",
                                identity="custody-signer.example/receipt-2",
                            ),
                        ],
                    )
                )
        finally:
            provenance.close()

    def test_stale_or_future_keyset_rejects_before_receipt_verification(self) -> None:
        provenance = CustodyProvenanceStore()
        try:
            old_verifier = Ed25519CustodyVerifier(
                self.anchor,
                provenance,
                now=lambda: self.now,
                max_keyset_age=timedelta(hours=1),
            )
            with self.assertRaisesRegex(CustodyError, "stale"):
                old_verifier.install_keyset(
                    self.keyset(
                        1,
                        [
                            self.custody_key(
                                self.receipt_key,
                                key_id="receipt-key-1",
                                identity="custody-signer.example/receipt-1",
                            )
                        ],
                        issued_at=self.now - timedelta(hours=2),
                        expires_at=self.now + timedelta(hours=1),
                    )
                )
            with self.assertRaisesRegex(CustodyError, "not yet valid"):
                old_verifier.install_keyset(
                    self.keyset(
                        1,
                        [
                            self.custody_key(
                                self.receipt_key,
                                key_id="receipt-key-1",
                                identity="custody-signer.example/receipt-1",
                            )
                        ],
                        issued_at=self.now + timedelta(minutes=1),
                    )
                )
        finally:
            provenance.close()

    def test_legacy_provenance_migrates_without_breaking_append_only_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custody.sqlite3"
            document = {
                "attestation_id": "ATT-LEGACY-1",
                "authority_id": self.anchor.authority_id,
            }
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE custody_attestations (
                        digest TEXT PRIMARY KEY,
                        authority_id TEXT NOT NULL,
                        key_id TEXT NOT NULL,
                        nonce TEXT NOT NULL,
                        subject_json TEXT NOT NULL,
                        document_json TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        UNIQUE(authority_id, key_id, nonce)
                    );
                    CREATE TRIGGER custody_attestations_no_update
                    BEFORE UPDATE ON custody_attestations BEGIN
                        SELECT RAISE(ABORT, 'custody attestations are append-only');
                    END;
                    """
                )
                connection.execute(
                    "INSERT INTO custody_attestations("
                    "digest,authority_id,key_id,nonce,subject_json,document_json,recorded_at"
                    ") VALUES(?,?,?,?,?,?,?)",
                    (
                        "sha256:" + "a" * 64,
                        self.anchor.authority_id,
                        "legacy-key",
                        "legacy-nonce",
                        "{}",
                        json.dumps(document),
                        self.now.isoformat(),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            provenance = CustodyProvenanceStore(path)
            try:
                connection = sqlite3.connect(path)
                try:
                    self.assertEqual(
                        connection.execute(
                            "SELECT attestation_id FROM custody_attestations"
                        ).fetchone()[0],
                        "ATT-LEGACY-1",
                    )
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "UPDATE custody_attestations SET nonce='changed'"
                        )
                finally:
                    connection.close()
            finally:
                provenance.close()

    def test_rewritten_local_keyset_cannot_substitute_an_attacker_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custody.sqlite3"
            verifier, provenance = self.verifier(path)
            attacker_key = Ed25519PrivateKey.generate()
            try:
                rewritten = provenance.latest_keyset(self.anchor.authority_id)
                assert rewritten is not None
                keys = rewritten["keys"]
                assert isinstance(keys, list)
                key = keys[0]
                assert isinstance(key, dict)
                key["public_key"] = _encoded(
                    attacker_key.public_key().public_bytes_raw()
                )
                connection = sqlite3.connect(path)
                try:
                    connection.execute(
                        "DROP TRIGGER custody_keysets_no_update"
                    )
                    connection.execute(
                        "UPDATE custody_keysets SET document_json=?",
                        (json.dumps(rewritten, sort_keys=True, separators=(",", ":")),),
                    )
                    connection.commit()
                finally:
                    connection.close()
                receipt, reference = self.receipt()
                attacker = _ExternalTestAttestor(attacker_key, now=self.now)
                with self.assertRaisesRegex(CustodyError, "signature verification failed"):
                    verifier.verify_receipt(
                        receipt,
                        reference,
                        attacker.attest(CustodySubject.receipt(receipt, reference).to_dict()),
                    )
            finally:
                provenance.close()

    def test_strict_existing_mission_cannot_resume_without_the_configured_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "source")
            verifier, provenance = self.verifier(root / "custody.sqlite3")
            store = MissionStore(
                root / "missions",
                custody_verifier=verifier,
                require_authenticated_custody=True,
            )
            adapter = ExternalCustodyAdapter(
                _ExternalTestAttestor(self.receipt_key, now=self.now), verifier
            )
            kwargs = {
                "acceptance_criteria": ("increment(1) returns 2",),
                "acceptance_specifications": (
                    AcceptanceSpecification(
                        "increment-returns-two",
                        "increment(1) returns 2",
                        (sys.executable, "-B", "-c", "assert True"),
                    ),
                ),
                "backend": ScriptedRepositoryBackend(),
                "pin": fixture.commit_two,
                "output_dir": root / "delivery",
                "mission_store": store,
                "_run_id": "M-STRICT-CUSTODY",
            }
            try:
                RepositoryMission(
                    fixture.root,
                    "Fix the failing test",
                    custody=adapter,
                    **kwargs,
                )
                store.close()
                store = MissionStore(
                    root / "missions",
                    custody_verifier=verifier,
                    require_authenticated_custody=True,
                )
                kwargs["mission_store"] = store
                with self.assertRaisesRegex(MissionStoreError, "requires an external"):
                    asyncio.run(resume_mission(store, "M-STRICT-CUSTODY"))
                with self.assertRaisesRegex(ValueError, "require an external custody adapter"):
                    RepositoryMission(
                        fixture.root,
                        "Fix the failing test",
                        custody=None,
                        **kwargs,
                    )
            finally:
                store.close()
                provenance.close()

    def test_self_issued_expired_and_stale_keyset_evidence_rejects(self) -> None:
        verifier, provenance = self.verifier()
        try:
            receipt, reference = self.receipt()
            subject = CustodySubject.receipt(receipt, reference)
            self_issued = _ExternalTestAttestor(
                self.receipt_key,
                identity="agent-builder",
                now=self.now,
            )
            with self.assertRaisesRegex(CustodyError, "external to the acting"):
                verifier.verify(subject, self_issued.attest(subject.to_dict()))

            expired = dict(_ExternalTestAttestor(self.receipt_key, now=self.now).attest(subject.to_dict()))
            expired["issued_at"] = (self.now - timedelta(minutes=2)).isoformat()
            expired["expires_at"] = (self.now - timedelta(seconds=1)).isoformat()
            expired = _signed(
                {name: value for name, value in expired.items() if name != "signature"},
                self.receipt_key,
                b"hive-mind-os/custody-attestation/v1\0",
            )
            with self.assertRaisesRegex(CustodyError, "expired"):
                verifier.verify(subject, expired)

            verifier.install_keyset(
                self.keyset(
                    2,
                    [
                        self.custody_key(
                            self.receipt_key,
                            key_id="receipt-key-1",
                            identity="custody-signer.example/receipt-1",
                        )
                    ],
                )
            )
            stale = _ExternalTestAttestor(self.receipt_key, sequence=1, now=self.now)
            with self.assertRaisesRegex(CustodyError, "stale"):
                verifier.verify(subject, stale.attest(subject.to_dict()))
        finally:
            provenance.close()

    def test_strict_mission_store_preserves_verified_configuration_custody(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verifier, provenance = self.verifier(root / "custody.sqlite3")
            store = MissionStore(
                root / "missions",
                custody_verifier=verifier,
                require_authenticated_custody=True,
            )
            configuration = {
                **self.configuration(),
                "source_pack_fingerprint": "sha256:" + "d" * 64,
            }
            try:
                with self.assertRaisesRegex(StoreIntegrityError, "signed mission configuration"):
                    store.register_mission(
                        "M-1", configuration, self._budget()
                    )
                adapter = ExternalCustodyAdapter(
                    _ExternalTestAttestor(self.receipt_key, now=self.now), verifier
                )
                attestation = adapter.attest_configuration("M-1", configuration)
                store.register_mission(
                    "M-1",
                    configuration,
                    self._budget(),
                    configuration_attestation=attestation,
                )
                observed = store.mission("M-1")
                self.assertEqual(observed["configuration_custody"], attestation)
            finally:
                store.close()
                provenance.close()

    def test_repository_delivery_custodies_every_local_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "source")
            verifier, provenance = self.verifier(root / "custody.sqlite3")
            try:
                adapter = ExternalCustodyAdapter(
                    _ExternalTestAttestor(self.receipt_key, now=self.now), verifier
                )
                criterion_argv = (
                    sys.executable,
                    "-B",
                    "-c",
                    "from tiny_pkg.maths import increment; assert increment(1) == 2",
                )
                report = asyncio.run(
                    RepositoryMission(
                        fixture.root,
                        "Fix the failing test",
                        acceptance_criteria=("increment(1) returns 2",),
                        acceptance_specifications=(
                            AcceptanceSpecification(
                                "increment-returns-two",
                                "increment(1) returns 2",
                                criterion_argv,
                            ),
                        ),
                        backend=ScriptedRepositoryBackend(),
                        pin=fixture.commit_two,
                        output_dir=root / "delivery",
                        custody=adapter,
                    ).run()
                )
                self.assertIs(report.status, WorkStatus.SUCCEEDED, report.failure)
                self.assertTrue(report.receipts)
                self.assertTrue(
                    all("custody_attestation" in record for record in report.receipts)
                )
            finally:
                provenance.close()

    def test_failed_repository_delivery_reverifies_preserved_custody_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "source")
            verifier, provenance = self.verifier(root / "custody.sqlite3")
            try:
                adapter = ExternalCustodyAdapter(
                    _ExternalTestAttestor(self.receipt_key, now=self.now), verifier
                )
                report = asyncio.run(
                    RepositoryMission(
                        fixture.root,
                        "Fix the failing test",
                        acceptance_criteria=("increment(1) returns 2",),
                        acceptance_specifications=(
                            AcceptanceSpecification(
                                "increment-returns-two",
                                "increment(1) returns 2",
                                (sys.executable, "-B", "-c", "assert True"),
                            ),
                        ),
                        backend=ScriptedRepositoryBackend("sabotage"),
                        pin=fixture.commit_two,
                        output_dir=root / "delivery",
                        custody=adapter,
                    ).run()
                )
                self.assertIs(report.status, WorkStatus.FAILED, report.failure)
                self.assertIsNotNone(report.receipt_root)
                self.assertTrue(
                    all("custody_attestation" in record for record in report.receipts)
                )
                self.assertGreater(provenance.attestation_count(), 0)
            finally:
                provenance.close()

    @staticmethod
    def _budget() -> AutonomyBudget:
        return AutonomyBudget(
            max_episodes=1,
            max_tool_calls=1,
            max_compute_units=1.0,
        )


if __name__ == "__main__":
    unittest.main()
