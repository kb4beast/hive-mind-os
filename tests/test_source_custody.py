from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hive_mind_os.custody import (
    CustodyProvenanceStore,
    Ed25519CustodyVerifier,
    TrustAnchor,
)
from hive_mind_os.git_adapter import GitWorkspace, PinViolation, verify_delivery
from hive_mind_os.policy import Action
from hive_mind_os.source_custody import (
    SOURCE_CUSTODY_AUDIENCE,
    ExternalSourceCustodyAdapter,
    SourceCustodyError,
    SourceCustodyVerifier,
    SourceLock,
    SourceLockEvidence,
    SourceLockProvenanceStore,
)
from tests.fixtures.fixture_repo import build_fixture_repo


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _signed(document: Mapping[str, object], key: Ed25519PrivateKey, domain: bytes) -> dict[str, object]:
    payload = {name: value for name, value in document.items() if name != "signature"}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    signed = dict(payload)
    signed["signature"] = _encoded(key.sign(domain + encoded))
    return signed


class _ExternalSourceAttestor:
    """Test-only external service; it exposes no signing key to production code."""

    def __init__(
        self,
        key: Ed25519PrivateKey,
        *,
        now: datetime,
        key_id: str = "source-key-1",
        identity: str = "custody-authority.example/source-1",
        sequence: int = 1,
    ) -> None:
        self.key = key
        self.now = now
        self.key_id = key_id
        self.identity = identity
        self.sequence = sequence
        self.counter = 0

    def attest_source_lock(self, source_lock: Mapping[str, object]) -> Mapping[str, object]:
        self.counter += 1
        return _signed(
            {
                "schema_version": 1,
                "attestation_id": f"SOURCE-ATT-{self.key_id}-{self.counter}",
                "authority_id": "custody-authority.example",
                "keyset_sequence": self.sequence,
                "signer_identity": self.identity,
                "key_id": self.key_id,
                "algorithm": "ed25519",
                "audience": SOURCE_CUSTODY_AUDIENCE,
                "issued_at": self.now.isoformat(),
                "expires_at": (self.now + timedelta(minutes=5)).isoformat(),
                "nonce": f"source-nonce-{self.counter:012d}",
                "source_lock": dict(source_lock),
            },
            self.key,
            b"hive-mind-os/source-lock-attestation/v1\0",
        )


class SourceCustodyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        self.root_key = Ed25519PrivateKey.generate()
        self.source_key = Ed25519PrivateKey.generate()
        self.next_source_key = Ed25519PrivateKey.generate()
        self.anchor = TrustAnchor(
            "custody-authority.example",
            "root-key-1",
            "custody-authority.example/root",
            _encoded(self.root_key.public_key().public_bytes_raw()),
        )

    def keyset(self, sequence: int, keys: list[dict[str, object]]) -> dict[str, object]:
        return _signed(
            {
                "schema_version": 1,
                "authority_id": self.anchor.authority_id,
                "sequence": sequence,
                "issued_at": self.now.isoformat(),
                "expires_at": (self.now + timedelta(hours=2)).isoformat(),
                "issuer_key_id": self.anchor.key_id,
                "issuer_identity": self.anchor.signer_identity,
                "keys": keys,
            },
            self.root_key,
            b"hive-mind-os/custody-keyset/v1\0",
        )

    def signer_key(
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

    @staticmethod
    def lock_document(
        *,
        lock_id: str = "SRCLOCK-1",
        commit_sha: str = "a" * 40,
        tree_sha: str = "b" * 40,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "lock_id": lock_id,
            "mission_id": "M-source-1",
            "state_ref": "MISSION_STATE:M-source-1:1",
            "repository_url": "https://github.com/octocat/hive-mind-os.git",
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "source_identity": {
                "provider": "github.com",
                "repository_id": "github.com/octocat/hive-mind-os",
                "principal_id": "github-app-installation:4242",
            },
        }

    def verifier(
        self,
        source_provenance_path: str | Path = ":memory:",
        custody_provenance_path: str | Path = ":memory:",
    ) -> tuple[SourceCustodyVerifier, CustodyProvenanceStore, SourceLockProvenanceStore]:
        custody_provenance = CustodyProvenanceStore(custody_provenance_path)
        custody = Ed25519CustodyVerifier(
            self.anchor,
            custody_provenance,
            now=lambda: self.now,
        )
        custody.install_keyset(
            self.keyset(
                1,
                [
                    self.signer_key(
                        self.source_key,
                        key_id="source-key-1",
                        identity="custody-authority.example/source-1",
                    )
                ],
            )
        )
        source_provenance = SourceLockProvenanceStore(source_provenance_path)
        return (
            SourceCustodyVerifier(custody, source_provenance),
            custody_provenance,
            source_provenance,
        )

    def test_external_adapter_binds_exact_source_identity_and_lock(self) -> None:
        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        adapter = ExternalSourceCustodyAdapter(
            _ExternalSourceAttestor(self.source_key, now=self.now), verifier
        )
        evidence = adapter.attest_source_lock(self.lock_document())
        self.assertEqual(verifier.verify(evidence).repository_url, evidence.source_lock.repository_url)
        self.assertEqual(source_provenance.count(), 1)

        tampered = SourceLockEvidence(
            SourceLock.from_dict(self.lock_document(commit_sha="c" * 40)),
            evidence.attestation,
        )
        with self.assertRaises(SourceCustodyError):
            verifier.verify(tampered)
        self.assertEqual(source_provenance.count(), 1)

    def test_provenance_replay_and_conflicting_nonce_fail_closed_across_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provenance_path = Path(directory) / "source-locks.sqlite"
            verifier, custody_provenance, source_provenance = self.verifier(provenance_path)
            self.addCleanup(custody_provenance.close)
            self.addCleanup(source_provenance.close)
            attestor = _ExternalSourceAttestor(self.source_key, now=self.now)
            evidence = SourceLockEvidence(
                SourceLock.from_dict(self.lock_document()),
                attestor.attest_source_lock(self.lock_document()),
            )
            verifier.verify(evidence)
            verifier.verify(evidence)
            self.assertEqual(source_provenance.count(), 1)
            source_provenance.close()

            reopened = SourceLockProvenanceStore(provenance_path)
            self.addCleanup(reopened.close)
            verifier = SourceCustodyVerifier(verifier.custody_verifier, reopened)
            reused_nonce = dict(attestor.attest_source_lock(self.lock_document(lock_id="SRCLOCK-2")))
            reused_nonce["nonce"] = str(evidence.attestation["nonce"])
            reused_nonce = _signed(
                {name: value for name, value in reused_nonce.items() if name != "signature"},
                self.source_key,
                b"hive-mind-os/source-lock-attestation/v1\0",
            )
            with self.assertRaises(SourceCustodyError):
                verifier.verify(
                    SourceLockEvidence(
                        SourceLock.from_dict(self.lock_document(lock_id="SRCLOCK-2")),
                        reused_nonce,
                    )
                )
            reopened.close()

    def test_rotation_and_revocation_reject_stale_source_attestation(self) -> None:
        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        old_attestor = _ExternalSourceAttestor(self.source_key, now=self.now)
        old_evidence = SourceLockEvidence(
            SourceLock.from_dict(self.lock_document()),
            old_attestor.attest_source_lock(self.lock_document()),
        )
        verifier.verify(old_evidence)
        verifier.custody_verifier.install_keyset(
            self.keyset(
                2,
                [
                    self.signer_key(
                        self.source_key,
                        key_id="source-key-1",
                        identity="custody-authority.example/source-1",
                        status="revoked",
                    ),
                    self.signer_key(
                        self.next_source_key,
                        key_id="source-key-2",
                        identity="custody-authority.example/source-2",
                    ),
                ],
            )
        )
        with self.assertRaises(SourceCustodyError):
            verifier.verify(old_evidence)
        next_attestor = _ExternalSourceAttestor(
            self.next_source_key,
            now=self.now,
            key_id="source-key-2",
            identity="custody-authority.example/source-2",
            sequence=2,
        )
        next_evidence = SourceLockEvidence(
            SourceLock.from_dict(self.lock_document(lock_id="SRCLOCK-2")),
            next_attestor.attest_source_lock(self.lock_document(lock_id="SRCLOCK-2")),
        )
        self.assertEqual(verifier.verify(next_evidence).lock_id, "SRCLOCK-2")

    def test_remote_materialization_requires_verified_evidence_before_clone(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        workspace_root = root / "workspace"
        evidence_root = root / "evidence"
        with self.assertRaises(PinViolation):
            GitWorkspace.materialize(
                "https://github.com/octocat/hive-mind-os.git",
                "a" * 40,
                workspace_root,
                evidence_root,
                allow_remote=True,
                require_source_custody=True,
            )
        self.assertFalse(workspace_root.exists())

        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        mismatched_lock = SourceLockEvidence(
            SourceLock.from_dict(self.lock_document(commit_sha="b" * 40)),
            _ExternalSourceAttestor(self.source_key, now=self.now).attest_source_lock(
                self.lock_document(commit_sha="b" * 40)
            ),
        )
        with self.assertRaises(PinViolation):
            GitWorkspace.materialize(
                "https://github.com/octocat/hive-mind-os.git",
                "a" * 40,
                workspace_root,
                evidence_root,
                allow_remote=True,
                source_lock=mismatched_lock,
                source_custody=verifier,
                source_mission_id="M-source-1",
                source_state_ref="MISSION_STATE:M-source-1:1",
            )
        self.assertFalse(workspace_root.exists())

    def test_source_lock_never_treats_a_local_pin_as_authentication(self) -> None:
        lock = SourceLock.from_dict(self.lock_document())
        with self.assertRaises(SourceCustodyError):
            lock.require_tree("c" * 40)

    def test_source_lock_cannot_replay_across_mission_or_state(self) -> None:
        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        evidence = ExternalSourceCustodyAdapter(
            _ExternalSourceAttestor(self.source_key, now=self.now), verifier
        ).attest_source_lock(self.lock_document())
        with self.assertRaisesRegex(SourceCustodyError, "mission does not match"):
            verifier.verify_for_materialization(
                evidence,
                "https://github.com/octocat/hive-mind-os.git",
                "a" * 40,
                mission_id="M-source-other",
                state_ref="MISSION_STATE:M-source-other:1",
                allowed_hosts=("github.com",),
            )

    def test_source_lock_rejects_malformed_state_or_self_custodied_principal(self) -> None:
        malformed = self.lock_document()
        malformed["state_ref"] = "MISSION_STATE:M-source-1:0"
        with self.assertRaisesRegex(SourceCustodyError, "state_ref is malformed"):
            SourceLock.from_dict(malformed)
        misbound = self.lock_document()
        misbound["state_ref"] = "MISSION_STATE:M-source-other:1"
        with self.assertRaisesRegex(SourceCustodyError, "does not bind"):
            SourceLock.from_dict(misbound)

        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        self_custodied = self.lock_document()
        identity = self_custodied["source_identity"]
        assert isinstance(identity, dict)
        self_custodied["source_identity"] = {
            **identity,
            "principal_id": "custody-authority.example/source-1",
        }
        attestor = _ExternalSourceAttestor(
            self.source_key,
            now=self.now,
            identity="custody-authority.example/source-1",
        )
        with self.assertRaisesRegex(SourceCustodyError, "distinct"):
            verifier.verify(
                SourceLockEvidence(
                    SourceLock.from_dict(self_custodied),
                    attestor.attest_source_lock(self_custodied),
                )
            )

    def test_strict_remote_source_custody_requires_durable_provenance(self) -> None:
        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        evidence = ExternalSourceCustodyAdapter(
            _ExternalSourceAttestor(self.source_key, now=self.now), verifier
        ).attest_source_lock(self.lock_document())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PinViolation, "requires durable"):
                GitWorkspace.materialize(
                    "https://github.com/octocat/hive-mind-os.git",
                    "a" * 40,
                    Path(directory) / "workspace",
                    Path(directory) / "evidence",
                    allow_remote=True,
                    source_lock=evidence,
                    source_custody=verifier,
                    require_source_custody=True,
                    source_mission_id="M-source-1",
                    source_state_ref="MISSION_STATE:M-source-1:1",
                )

    def test_strict_remote_source_custody_rejects_empty_sqlite_paths(self) -> None:
        verifier, custody_provenance, source_provenance = self.verifier("", "")
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        evidence = ExternalSourceCustodyAdapter(
            _ExternalSourceAttestor(self.source_key, now=self.now), verifier
        ).attest_source_lock(self.lock_document())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PinViolation, "requires durable"):
                GitWorkspace.materialize(
                    "https://github.com/octocat/hive-mind-os.git",
                    "a" * 40,
                    Path(directory) / "workspace",
                    Path(directory) / "evidence",
                    allow_remote=True,
                    source_lock=evidence,
                    source_custody=verifier,
                    require_source_custody=True,
                    source_mission_id="M-source-1",
                    source_state_ref="MISSION_STATE:M-source-1:1",
                )

    def test_git_materialization_rejects_a_signed_tree_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "source")
            workspace = GitWorkspace.materialize(
                fixture.root,
                fixture.commit_two,
                root / "workspace",
                root / "evidence",
            )
            lock = SourceLock.from_dict(
                self.lock_document(tree_sha="a" * 40)
            )
            with self.assertRaisesRegex(PinViolation, "does not match"):
                GitWorkspace._verify_authenticated_source_tree(
                    workspace,
                    "HEAD^{tree}",
                    lock,
                )

    def test_workspace_receipts_preserve_the_bound_source_state_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "source")
            workspace = GitWorkspace.materialize(
                fixture.root,
                fixture.commit_two,
                root / "workspace",
                root / "evidence",
            )
            workspace.state_ref = "MISSION_STATE:M-source-1:2"
            workspace._run_git(
                ["rev-parse", "HEAD"],
                Action.READ_REPOSITORY,
                "verify state-reference receipt binding",
            )
            self.assertEqual(
                workspace.receipt_records[-1]["state_ref"],
                "MISSION_STATE:M-source-1:2",
            )

    def test_delivery_rejects_tampered_or_cross_mission_source_custody(self) -> None:
        verifier, custody_provenance, source_provenance = self.verifier()
        self.addCleanup(custody_provenance.close)
        self.addCleanup(source_provenance.close)
        evidence = ExternalSourceCustodyAdapter(
            _ExternalSourceAttestor(self.source_key, now=self.now), verifier
        ).attest_source_lock(self.lock_document())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = build_fixture_repo(root / "source")
            manifest = {
                "schema_version": 1,
                "base_sha": "a" * 40,
                "branch_name": "source/locked",
                "head_sha": "b" * 40,
                "head_tree": "c" * 40,
                "diff_digest": "sha256:" + "d" * 64,
                "bundle_digest": "sha256:" + "e" * 64,
                "patch_digest": "sha256:" + "f" * 64,
                "files": [],
                "receipts": [
                    {
                        "mission_id": "M-foreign",
                        "state_ref": "MISSION_STATE:M-foreign:1",
                    }
                ],
                "source_custody": {
                    "digest": evidence.digest(),
                    "source_lock": evidence.source_lock.to_dict(),
                    "attestation": dict(evidence.attestation),
                },
            }
            (root / "delivery.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(verify_delivery(root, fixture.root, source_custody=verifier))

            tampered = dict(evidence.attestation)
            tampered["signature"] = "a" * 86
            tampered_evidence = SourceLockEvidence(evidence.source_lock, tampered)
            manifest["receipts"] = [
                {
                    "mission_id": evidence.source_lock.mission_id,
                    "state_ref": evidence.source_lock.state_ref,
                }
            ]
            manifest["source_custody"] = {
                "digest": tampered_evidence.digest(),
                "source_lock": evidence.source_lock.to_dict(),
                "attestation": tampered,
            }
            (root / "delivery.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(verify_delivery(root, fixture.root, source_custody=verifier))


if __name__ == "__main__":
    unittest.main()
