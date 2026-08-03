from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.autonomy import EpisodeAllowance
from hive_mind_os.custody import (
    CustodyProvenanceStore,
    Ed25519CustodyVerifier,
    TrustAnchor,
)
from hive_mind_os.git_adapter import (
    GitOperationFailed,
    GitWorkspace,
    PinViolation,
    verify_delivery,
)
from hive_mind_os.mission import MissionFailed, RepositoryMission
from hive_mind_os.mission_store import (
    MissionStore,
    MissionStoreError,
    ReconciliationError,
    StepCheckpoint,
    reopen_workspace,
    resume_mission,
)
from hive_mind_os.models import AutonomyLevel, RiskTier, Role
from hive_mind_os.policy import Action, PolicyEngine
from hive_mind_os.source_custody import (
    SOURCE_CUSTODY_AUDIENCE,
    SourceCustodyVerifier,
    SourceLock,
    SourceLockEvidence,
    SourceLockProvenanceStore,
)
from tests.fixtures.fixture_repo import build_fixture_repo


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signed(document: dict[str, object], key: Ed25519PrivateKey, domain: bytes) -> dict[str, object]:
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {**document, "signature": _encoded(key.sign(domain + payload))}


def _specification() -> AcceptanceSpecification:
    return AcceptanceSpecification(
        "source-custody-test",
        "repository source is authenticated before materialization",
        ("python", "-B", "-c", "pass"),
    )


class _CustodyHarness:
    def __init__(self, root: Path, mission_id: str) -> None:
        self.now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        self.mission_id = mission_id
        self.root_key = Ed25519PrivateKey.generate()
        self.source_key = Ed25519PrivateKey.generate()
        self.anchor = TrustAnchor(
            "custody-authority.example",
            "root-key-1",
            "custody-authority.example/root",
            _encoded(self.root_key.public_key().public_bytes_raw()),
        )
        self.custody_provenance = CustodyProvenanceStore(root / "keysets.sqlite3")
        self.source_provenance = SourceLockProvenanceStore(root / "source-locks.sqlite3")
        self.custody = Ed25519CustodyVerifier(
            self.anchor,
            self.custody_provenance,
            now=lambda: self.now,
        )
        self.custody.install_keyset(self._keyset())
        self.verifier = SourceCustodyVerifier(self.custody, self.source_provenance)

    def close(self) -> None:
        self.source_provenance.close()
        self.custody_provenance.close()

    def _keyset(self) -> dict[str, object]:
        return _signed(
            {
                "schema_version": 1,
                "authority_id": self.anchor.authority_id,
                "sequence": 1,
                "issued_at": self.now.isoformat(),
                "expires_at": (self.now + timedelta(hours=1)).isoformat(),
                "issuer_key_id": self.anchor.key_id,
                "issuer_identity": self.anchor.signer_identity,
                "keys": [
                    {
                        "key_id": "source-key-1",
                        "signer_identity": "custody-authority.example/source-1",
                        "public_key": _encoded(
                            self.source_key.public_key().public_bytes_raw()
                        ),
                        "status": "active",
                        "not_before": (self.now - timedelta(minutes=1)).isoformat(),
                        "not_after": None,
                        "revoked_at": None,
                    }
                ],
            },
            self.root_key,
            b"hive-mind-os/custody-keyset/v1\0",
        )

    def source_lock(
        self,
        *,
        commit_sha: str = "a" * 40,
        tree_sha: str = "b" * 40,
    ) -> SourceLockEvidence:
        lock = SourceLock.from_dict(
            {
                "schema_version": 1,
                "lock_id": "SRCLOCK-repository-mission-1",
                "mission_id": self.mission_id,
                "state_ref": f"MISSION_STATE:{self.mission_id}:1",
                "repository_url": "https://github.com/octocat/hive-mind-os.git",
                "commit_sha": commit_sha,
                "tree_sha": tree_sha,
                "source_identity": {
                    "provider": "github.com",
                    "repository_id": "github.com/octocat/hive-mind-os",
                    "principal_id": "github-app-installation:4242",
                },
            }
        )
        attestation = _signed(
            {
                "schema_version": 1,
                "attestation_id": "SOURCE-ATT-repository-mission-1",
                "authority_id": self.anchor.authority_id,
                "keyset_sequence": 1,
                "signer_identity": "custody-authority.example/source-1",
                "key_id": "source-key-1",
                "algorithm": "ed25519",
                "audience": SOURCE_CUSTODY_AUDIENCE,
                "issued_at": self.now.isoformat(),
                "expires_at": (self.now + timedelta(minutes=5)).isoformat(),
                "nonce": "repository-source-nonce-000001",
                "source_lock": lock.to_dict(),
            },
            self.source_key,
            b"hive-mind-os/source-lock-attestation/v1\0",
        )
        return SourceLockEvidence(lock, attestation)


class AuthenticatedRepositorySourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.mission_id = "M-authenticated-source-1"
        self.harness = _CustodyHarness(self.root, self.mission_id)
        self.addCleanup(self.harness.close)

    def mission(self) -> RepositoryMission:
        store = MissionStore(self.root / "missions")
        self.addCleanup(store.close)
        return RepositoryMission(
            "https://github.com/octocat/hive-mind-os.git",
            "Confirm authenticated source admission",
            mission_id=self.mission_id,
            acceptance_specifications=(_specification(),),
            source_lock=self.harness.source_lock(),
            source_custody=self.harness.verifier,
            mission_store=store,
            output_dir=self.root / "delivery",
        )

    def committed_authenticated_workspace(self, label: str) -> GitWorkspace:
        fixture = build_fixture_repo(self.root / f"{label}-fixture")
        workspace = GitWorkspace.materialize(
            fixture.root,
            fixture.commit_two,
            self.root / f"{label}-workspace",
            self.root / f"{label}-evidence",
            source_mission_id=self.mission_id,
        )
        base_tree = workspace._git_text(
            ["rev-parse", "HEAD^{tree}"],
            Action.READ_REPOSITORY,
            "read fixture source tree for authenticated delivery lock",
        )
        workspace.create_branch(f"source/{label}-lock")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        workspace.commit(f"fix: prepare {label} source custody delivery")
        evidence = self.harness.source_lock(
            commit_sha=fixture.commit_two,
            tree_sha=base_tree,
        )
        workspace.source_lock = evidence.source_lock
        workspace.source_lock_evidence = evidence
        workspace.source_custody = self.harness.verifier
        workspace.require_source_custody = True
        return workspace

    def test_remote_mission_rejects_a_git_pin_without_external_source_custody(self) -> None:
        store = MissionStore(self.root / "unattested-missions")
        self.addCleanup(store.close)
        with self.assertRaisesRegex(ValueError, "source-lock evidence"):
            RepositoryMission(
                "https://github.com/octocat/hive-mind-os.git",
                "Do not treat a SHA as authentication",
                mission_id=self.mission_id,
                pin="a" * 40,
                acceptance_specifications=(_specification(),),
                mission_store=store,
                output_dir=self.root / "unattested-delivery",
            )

    def test_authenticated_source_is_sealed_into_the_durable_mission_and_materialization(self) -> None:
        mission = self.mission()
        stored = mission.mission_store.mission(self.mission_id)  # type: ignore[union-attr]
        authenticated_source = stored["config"]["authenticated_source"]
        assert mission._source_lock_evidence is not None
        self.assertEqual(
            authenticated_source["evidence_digest"], mission._source_lock_evidence.digest()
        )
        self.assertEqual(mission.pin, "a" * 40)
        self.assertEqual(self.harness.source_provenance.count(), 1)

        options = mission._source_materialization_options()
        self.assertTrue(options["require_source_custody"])
        self.assertEqual(options["source_mission_id"], self.mission_id)
        self.assertEqual(options["source_state_ref"], f"MISSION_STATE:{self.mission_id}:1")

        assert mission.mission_store is not None

    def test_remote_source_resume_requires_the_original_source_custody_verifier(self) -> None:
        mission = self.mission()
        assert mission.mission_store is not None
        store = mission.mission_store
        with self.assertRaisesRegex(MissionStoreError, "source custody verifier"):
            __import__("asyncio").run(resume_mission(store, self.mission_id))

    def test_mission_materialization_passes_the_verified_remote_lock_back_to_git(self) -> None:
        mission = self.mission()
        mission._evidence_root = self.root / "evidence"
        workspace = type(
            "Workspace",
            (),
            {"root": self.root / "workspace" / "repo", "receipt_records": ()},
        )()
        with patch.object(GitWorkspace, "materialize", return_value=workspace) as materialize:
            observed = mission._materialize_once(
                mission.pin,
                self.root / "workspace",
                Role.EXPLORER,
            )
        self.assertIs(observed, workspace)
        _, kwargs = materialize.call_args
        self.assertTrue(kwargs["allow_remote"])
        self.assertTrue(kwargs["require_source_custody"])
        self.assertIs(kwargs["source_lock"], mission._source_lock_evidence)
        self.assertIs(kwargs["source_custody"], self.harness.verifier)
        self.assertEqual(kwargs["source_mission_id"], self.mission_id)
        self.assertEqual(kwargs["source_state_ref"], f"MISSION_STATE:{self.mission_id}:1")

    def test_local_mission_materialization_binds_workspace_to_mission_identity(self) -> None:
        fixture = build_fixture_repo(self.root / "local-mission-fixture")
        store = MissionStore(self.root / "local-mission-store")
        self.addCleanup(store.close)
        mission = RepositoryMission(
            fixture.root,
            "Bind local workspace receipts to the durable mission",
            mission_id="M-local-workspace-identity-1",
            acceptance_specifications=(_specification(),),
            mission_store=store,
            output_dir=self.root / "local-mission-delivery",
        )
        mission._evidence_root = self.root / "local-mission-evidence"
        workspace = SimpleNamespace(
            root=self.root / "local-mission-workspace" / "repo",
            receipt_records=(),
        )
        with patch.object(GitWorkspace, "materialize", return_value=workspace) as materialize:
            observed = mission._materialize_once(
                mission.pin,
                self.root / "local-mission-workspace",
                Role.EXPLORER,
            )

        self.assertIs(observed, workspace)
        _, kwargs = materialize.call_args
        self.assertEqual(kwargs["source_mission_id"], mission.run_id)

    def test_git_workspace_rejects_a_pathlike_mission_identity_before_materialization(self) -> None:
        fixture = build_fixture_repo(self.root / "identity-fixture")
        workspace_root = self.root / "identity-workspace"
        with self.assertRaisesRegex(PinViolation, "mission identity"):
            GitWorkspace.materialize(
                fixture.root,
                fixture.commit_two,
                workspace_root,
                self.root / "identity-evidence",
                source_mission_id="M/foreign",
            )
        self.assertFalse(workspace_root.exists())

    def test_reopened_workspace_retains_authenticated_source_context_for_delivery(self) -> None:
        fixture = build_fixture_repo(self.root / "fixture")
        workspace = GitWorkspace.materialize(
            fixture.root,
            fixture.commit_two,
            self.root / "workspace",
            self.root / "evidence",
            source_mission_id=self.mission_id,
        )
        base_tree = workspace._git_text(
            ["rev-parse", "HEAD^{tree}"],
            Action.READ_REPOSITORY,
            "read fixture source tree for recovered source lock",
        )
        workspace.create_branch("source/recovery-context")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        workspace.commit("fix: retain source custody through recovery")
        evidence = self.harness.source_lock(
            commit_sha=fixture.commit_two,
            tree_sha=base_tree,
        )

        reopened = reopen_workspace(
            workspace.container_root,
            workspace.trusted_root,
            base_sha=workspace.base_sha,
            role=Role.BUILDER,
            risk=RiskTier.MODERATE,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            allowance=EpisodeAllowance(200, 200.0),
            mission_id=self.mission_id,
            records=workspace.receipt_records,
            source_lock=evidence.source_lock,
            source_lock_evidence=evidence,
            source_custody=self.harness.verifier,
            require_source_custody=True,
        )
        artifact = reopened.export_delivery(self.root / "delivery")
        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(reopened.source_lock, evidence.source_lock)
        self.assertEqual(reopened.source_lock_evidence, evidence)
        self.assertEqual(reopened.state_ref, evidence.source_lock.state_ref)
        self.assertEqual(manifest["source_custody"]["digest"], evidence.digest())

    def test_delivery_rejects_expired_authenticated_source_evidence(self) -> None:
        workspace = self.committed_authenticated_workspace("expired")
        self.harness.now += timedelta(minutes=6)

        with self.assertRaisesRegex(GitOperationFailed, "source custody was rejected"):
            workspace.export_delivery(self.root / "expired-delivery")
        self.assertFalse((self.root / "expired-delivery").exists())

    def test_delivery_rejects_source_evidence_that_expires_during_staging(self) -> None:
        workspace = self.committed_authenticated_workspace("staging")
        verify = self.harness.verifier.verify_for_materialization
        calls = 0

        def advance_clock_after_initial_check(*args: object, **kwargs: object) -> SourceLock:
            nonlocal calls
            calls += 1
            result = verify(*args, **kwargs)
            if calls == 1:
                self.harness.now += timedelta(minutes=6)
            return result

        with patch.object(
            self.harness.verifier,
            "verify_for_materialization",
            side_effect=advance_clock_after_initial_check,
        ):
            with self.assertRaisesRegex(GitOperationFailed, "source custody was rejected"):
                workspace.export_delivery(self.root / "staging-delivery")
        self.assertEqual(calls, 2)
        self.assertFalse((self.root / "staging-delivery").exists())

    def test_reopened_workspace_rejects_mismatched_authenticated_source_bindings(self) -> None:
        evidence = self.harness.source_lock()
        with self.assertRaisesRegex(
            ReconciliationError,
            "authenticated source recovery bindings",
        ):
            reopen_workspace(
                self.root / "missing-workspace",
                self.root / "evidence",
                base_sha="a" * 40,
                role=Role.BUILDER,
                risk=RiskTier.MODERATE,
                policy=PolicyEngine(AutonomyLevel.REPOSITORY),
                allowance=EpisodeAllowance(200, 200.0),
                mission_id="M-a-different-mission",
                records=(),
                source_lock=evidence.source_lock,
                source_lock_evidence=evidence,
                source_custody=self.harness.verifier,
                require_source_custody=True,
            )

    def test_durable_mission_reopen_passes_the_sealed_source_context(self) -> None:
        mission = self.mission()
        mission._evidence_root = self.root / "evidence"
        checkpoint = StepCheckpoint(
            self.mission_id,
            1,
            "a" * 64,
            "completed",
            {},
            {"value": {"git_mission_id": self.mission_id}, "records": []},
            {"path": "receipts/checkpoint.json", "digest": "sha256:" + "b" * 64},
            1,
        )
        reopened_workspace = SimpleNamespace(receipt_records=[])
        with (
            patch.object(mission, "_next_durable_intent", return_value=(1, {})),
            patch.object(mission, "_prepare_checkpoint", return_value=checkpoint),
            patch.object(
                mission,
                "_adopt_checkpoint",
                return_value={"value": {"git_mission_id": self.mission_id}, "records": []},
            ),
            patch(
                "hive_mind_os.mission_store.reopen_workspace",
                return_value=reopened_workspace,
            ) as reopen,
        ):
            observed = mission._durable_materialize(
                mission.pin,
                self.root / "recovered-workspace",
                Role.BUILDER,
            )

        self.assertIs(observed, reopened_workspace)
        _, kwargs = reopen.call_args
        self.assertIs(kwargs["source_lock"], mission._source_lock)
        self.assertIs(kwargs["source_lock_evidence"], mission._source_lock_evidence)
        self.assertIs(kwargs["source_custody"], mission._source_custody)
        self.assertTrue(kwargs["require_source_custody"])

    def test_durable_mission_reopen_rejects_a_malformed_workspace_identity(self) -> None:
        mission = self.mission()
        mission._evidence_root = self.root / "evidence"
        checkpoint = StepCheckpoint(
            self.mission_id,
            1,
            "a" * 64,
            "completed",
            {},
            {"value": {"git_mission_id": self.mission_id}, "records": []},
            {"path": "receipts/checkpoint.json", "digest": "sha256:" + "b" * 64},
            1,
        )
        with (
            patch.object(mission, "_next_durable_intent", return_value=(1, {})),
            patch.object(mission, "_prepare_checkpoint", return_value=checkpoint),
            patch.object(
                mission,
                "_adopt_checkpoint",
                return_value={"value": {"git_mission_id": {"forged": "identity"}}},
            ),
            patch("hive_mind_os.mission_store.reopen_workspace") as reopen,
        ):
            with self.assertRaisesRegex(MissionFailed, "invalid Git mission identity"):
                mission._durable_materialize(
                    mission.pin,
                    self.root / "recovered-workspace",
                    Role.BUILDER,
                )
        reopen.assert_not_called()

    def test_authenticated_delivery_rejects_a_different_requested_repository_url(self) -> None:
        evidence = self.harness.source_lock()
        artifact = self.root / "artifact"
        artifact.mkdir()
        (artifact / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "base_sha": "a" * 40,
                    "branch_name": "source/locked",
                    "head_sha": "b" * 40,
                    "head_tree": "c" * 40,
                    "diff_digest": "sha256:" + "d" * 64,
                    "bundle_digest": "sha256:" + "e" * 64,
                    "patch_digest": "sha256:" + "f" * 64,
                    "files": [],
                    "receipts": [],
                    "source_custody": {
                        "digest": evidence.digest(),
                        "source_lock": evidence.source_lock.to_dict(),
                        "attestation": dict(evidence.attestation),
                    },
                }
            ),
            encoding="utf-8",
        )
        self.assertFalse(
            verify_delivery(
                artifact,
                "https://github.com/octocat/a-different-repository.git",
                source_custody=self.harness.verifier,
            )
        )


if __name__ == "__main__":
    unittest.main()
