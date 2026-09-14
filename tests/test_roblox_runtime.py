import copy
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from typing import cast
from unittest.mock import patch

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.contracts import load_schema, validate_contract
from hive_mind_os.roblox_runtime import (
    QualificationEvidenceKind,
    QualificationReceipt,
    RobloxRuntimeAdapter,
    RobloxRuntimeAdmission,
    RobloxRuntimeEvidence,
    RuntimeBlockerKind,
    RuntimeEvidenceClass,
    RuntimeObligation,
    RuntimeReceipt,
    RuntimeVerdict,
    StudioToolReceipt,
    VerifierEvidenceScope,
    blocked_runtime,
)

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


class ToolVerifier:
    verifier_id = "fixture.tool-verifier"
    evidence_scope = VerifierEvidenceScope.CONTRACT_FIXTURE

    def __init__(self, accepted=True, error=None):
        self.accepted = accepted
        self.error = error
        self.calls = []

    def verify_tool_receipt(self, receipt):
        self.calls.append(receipt)
        if self.error is not None:
            raise self.error
        return self.accepted


class RuntimeVerifier:
    verifier_id = "fixture.runtime-verifier"
    evidence_scope = VerifierEvidenceScope.CONTRACT_FIXTURE

    def __init__(self, accepted=True, error=None):
        self.accepted = accepted
        self.error = error
        self.calls = []

    def verify_runtime_receipt(self, receipt):
        self.calls.append(receipt)
        if self.error is not None:
            raise self.error
        return self.accepted


class AuthorityVerifier:
    verifier_id = "fixture.authority-verifier"
    evidence_scope = VerifierEvidenceScope.CONTRACT_FIXTURE

    def __init__(self, accepted=True, error=None):
        self.accepted = accepted
        self.error = error
        self.calls = []

    def verify_runtime_authority(self, admission):
        self.calls.append(admission)
        if self.error is not None:
            raise self.error
        return self.accepted


class QualificationVerifier:
    verifier_id = "fixture.qualification-verifier"
    evidence_scope = VerifierEvidenceScope.CONTRACT_FIXTURE

    def __init__(self, accepted=True, error=None):
        self.accepted = accepted
        self.error = error
        self.calls = []

    def verify_qualification_receipt(self, receipt):
        self.calls.append(receipt)
        if self.error is not None:
            raise self.error
        return self.accepted


class RobloxRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.manifest = self.root / "default.project.json"
        self.manifest.write_text('{"name":"fixture"}\n', encoding="utf-8")
        self.manifest_digest = "sha256:" + sha256(self.manifest.read_bytes()).hexdigest()
        self.studio = Path(self.temporary.name) / "RobloxStudioBeta.exe"
        self.studio.write_bytes(b"signed fixture bytes")
        self.studio_digest = "sha256:" + sha256(self.studio.read_bytes()).hexdigest()
        self.tool_verifier = ToolVerifier()
        self.runtime_verifier = RuntimeVerifier()
        self.authority_verifier = AuthorityVerifier()
        self.qualification_verifier = QualificationVerifier()
        self.adapter = RobloxRuntimeAdapter(
            self.tool_verifier,
            self.runtime_verifier,
            self.authority_verifier,
            self.qualification_verifier,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def admission(self, **changes):
        values = {
            "candidate_digest": D1,
            "profile_digest": D2,
            "qualification_id": "qualification.n27.001",
            "verifier_manifest_ref": "ref:verifiers/n27.fixture",
            "verifier_manifest_digest": D4,
            "studio_verifier_id": "fixture.tool-verifier",
            "runtime_verifier_id": "fixture.runtime-verifier",
            "authority_verifier_id": "fixture.authority-verifier",
            "qualification_verifier_id": "fixture.qualification-verifier",
            "verifier_evidence_scope": VerifierEvidenceScope.CONTRACT_FIXTURE,
            "project_root": str(self.root),
            "project_manifest_path": str(self.manifest),
            "project_manifest_digest": self.manifest_digest,
            "studio_executable_path": str(self.studio),
            "studio_binary_digest": self.studio_digest,
            "studio_version": "0.735.0.7351131",
            "scenario_manifest_digest": D3,
            "required_scenarios": ("core-loop", "rejoin"),
            "required_device_ids": ("device.windows-low",),
            "environment_id": "test-universe.n27",
            "account_capability_refs": ("ref:broker/account.n27",),
            "authority_refs": ("ref:authority/runtime.n27",),
            "asset_rights_refs": ("ref:rights/assets.n27",),
            "broker_lease_ref": "ref:lease/broker.n27",
            "resource_lease_ref": "ref:lease/runtime.n27",
            "broker_lease_expires_at": 1100,
            "resource_lease_expires_at": 1100,
            "evidence_max_age_seconds": 200,
        }
        values.update(changes)
        return RobloxRuntimeAdmission(**values)

    def studio_receipt(self, **changes):
        values = {
            "receipt_ref": "ref:host/studio.discovery",
            "executable_path": str(self.studio),
            "binary_digest": self.studio_digest,
            "file_version": "0.735.0.7351131",
            "product_version": "0.735.0.7351131",
            "signature_status": "Valid",
            "signer_subject": "CN=Roblox Corporation, O=Roblox Corporation",
            "signer_thumbprint": "A" * 40,
            "verifier_id": "fixture.tool-verifier",
            "observed_at": 900,
            "expires_at": 1100,
        }
        values.update(changes)
        return StudioToolReceipt(**values)

    def runtime_receipt(self, evidence_class, scenario, device=None, **changes):
        values = {
            "receipt_ref": f"ref:runtime/{evidence_class.value.lower()}/{scenario}",
            "evidence_class": evidence_class,
            "qualification_id": "qualification.n27.001",
            "candidate_digest": D1,
            "profile_digest": D2,
            "project_manifest_digest": self.manifest_digest,
            "scenario_manifest_digest": D3,
            "studio_binary_digest": self.studio_digest,
            "studio_version": "0.735.0.7351131",
            "studio_tool_receipt_ref": "ref:host/studio.discovery",
            "environment_id": "test-universe.n27",
            "broker_lease_ref": "ref:lease/broker.n27",
            "environment_lease_ref": "ref:lease/runtime.n27",
            "verifier_id": "fixture.runtime-verifier",
            "scenario_id": scenario,
            "device_id": device,
            "passed": True,
            "observed_at": 920,
            "expires_at": 1100,
        }
        values.update(changes)
        return RuntimeReceipt(**values)

    def qualification_receipt(self, kind, **changes):
        if kind is QualificationEvidenceKind.METRIC:
            payload = {
                "evidence_kind": kind.value,
                "performance_samples": [16.5],
            }
        elif kind is QualificationEvidenceKind.CLEANUP:
            payload = {
                "cleanup_receipt": "ref:cleanup/runtime.n27",
                "evidence_kind": kind.value,
            }
        else:
            result_names = {
                QualificationEvidenceKind.PERSISTENCE: "retry-idempotency",
                QualificationEvidenceKind.SECURITY: "hostile-client",
                QualificationEvidenceKind.ASSET: "load-and-rights",
            }
            payload = {
                "evidence_kind": kind.value,
                "results": {result_names[kind]: "PASS"},
            }
        values = {
            "receipt_ref": f"ref:qualification/{kind.value.lower()}",
            "evidence_kind": kind,
            "qualification_id": "qualification.n27.001",
            "candidate_digest": D1,
            "profile_digest": D2,
            "project_manifest_digest": self.manifest_digest,
            "scenario_manifest_digest": D3,
            "studio_binary_digest": self.studio_digest,
            "studio_tool_receipt_ref": "ref:host/studio.discovery",
            "environment_id": "test-universe.n27",
            "broker_lease_ref": "ref:lease/broker.n27",
            "environment_lease_ref": "ref:lease/runtime.n27",
            "payload_digest": canonical_digest(payload),
            "verifier_id": "fixture.qualification-verifier",
            "observed_at": 930,
            "expires_at": 1100,
        }
        values.update(changes)
        return QualificationReceipt(**values)

    def complete_qualification_receipts(self):
        return tuple(
            self.qualification_receipt(kind) for kind in QualificationEvidenceKind
        )

    def qualify(
        self,
        admission=None,
        studio_receipt=None,
        runtime_receipts=(),
        qualification_receipts=None,
        **changes,
    ):
        values = {
            "performance_samples": (16.5,),
            "persistence_results": {"retry-idempotency": "PASS"},
            "security_results": {"hostile-client": "PASS"},
            "asset_results": {"load-and-rights": "PASS"},
            "cleanup_receipt": "ref:cleanup/runtime.n27",
            "qualification_receipts": (
                self.complete_qualification_receipts()
                if qualification_receipts is None
                else qualification_receipts
            ),
            "qualified_at": 1000,
        }
        values.update(changes)
        return self.adapter.qualify(
            admission or self.admission(),
            studio_receipt=(
                self.studio_receipt()
                if studio_receipt is None
                else studio_receipt
            ),
            runtime_receipts=runtime_receipts,
            **values,
        )

    def complete_receipts(self):
        receipts = []
        for scenario in ("core-loop", "rejoin"):
            receipts.append(
                self.runtime_receipt(RuntimeEvidenceClass.STUDIO_ENGINE, scenario)
            )
            receipts.append(
                self.runtime_receipt(
                    RuntimeEvidenceClass.PHYSICAL_DEVICE,
                    scenario,
                    "device.windows-low",
                    receipt_ref=f"ref:runtime/device/{scenario}",
                )
            )
        return tuple(receipts)

    def test_static_tool_discovery_does_not_satisfy_runtime(self):
        report = self.qualify(runtime_receipts=())

        self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        self.assertEqual(report.studio_tool_receipt_ref, "ref:host/studio.discovery")
        self.assertEqual(len(self.tool_verifier.calls), 1)
        self.assertEqual(self.runtime_verifier.calls, [])
        self.assertIn(
            "n27.runtime-matrix",
            {item.obligation_id for item in report.missing_obligations},
        )
        self.assertTrue(validate_contract("roblox-runtime-evidence", report.to_dict()).valid)

    def test_verified_fixture_matrix_forms_runtime_validated_evidence_only(self):
        report = self.qualify(runtime_receipts=self.complete_receipts())

        self.assertEqual(report.verdict, RuntimeVerdict.RUNTIME_VALIDATED)
        self.assertEqual(
            report.verifier_evidence_scope,
            VerifierEvidenceScope.CONTRACT_FIXTURE,
        )
        self.assertEqual(report.missing_obligations, ())
        self.assertEqual(len(report.runtime_receipts), 4)
        self.assertEqual(len(self.runtime_verifier.calls), 4)
        self.assertEqual(len(self.qualification_verifier.calls), 5)
        self.assertEqual(report.broker_lease_ref, "ref:lease/broker.n27")
        self.assertEqual(report.environment_lease_ref, "ref:lease/runtime.n27")
        self.assertEqual(len(report.verifier_ids), 4)
        self.assertEqual(len(report.qualification_receipts), 5)
        validation = validate_contract("roblox-runtime-evidence", report.to_dict())
        self.assertTrue(validation.valid, validation.issues)
        self.assertEqual(RobloxRuntimeEvidence.from_dict(report.to_dict()), report)

        with self.assertRaisesRegex(ValueError, "fixture evidence"):
            RobloxRuntimeEvidence.from_dict(
                {**report.to_dict(), "verdict": "PRODUCTION_CANDIDATE"}
            )

    def test_invalid_authenticode_or_unverified_runtime_fails_closed(self):
        bad_tool = self.studio_receipt(signature_status="NotSigned")
        report = self.qualify(
            studio_receipt=bad_tool, runtime_receipts=self.complete_receipts()
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        rejecting = RobloxRuntimeAdapter(
            self.tool_verifier,
            RuntimeVerifier(False),
            self.authority_verifier,
            self.qualification_verifier,
        )
        report = rejecting.qualify(
            self.admission(),
            studio_receipt=self.studio_receipt(),
            runtime_receipts=self.complete_receipts(),
            performance_samples=(16.5,),
            persistence_results={"retry-idempotency": "PASS"},
            security_results={"hostile-client": "PASS"},
            asset_results={"load-and-rights": "PASS"},
            cleanup_receipt="ref:cleanup/runtime.n27",
            qualification_receipts=self.complete_qualification_receipts(),
            qualified_at=1000,
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        blocked = RobloxRuntimeAdapter(
            self.tool_verifier,
            self.runtime_verifier,
            AuthorityVerifier(False),
            self.qualification_verifier,
        ).qualify(
            self.admission(),
            studio_receipt=self.studio_receipt(),
            runtime_receipts=self.complete_receipts(),
            performance_samples=(16.5,),
            persistence_results={"retry-idempotency": "PASS"},
            security_results={"hostile-client": "PASS"},
            asset_results={"load-and-rights": "PASS"},
            cleanup_receipt="ref:cleanup/runtime.n27",
            qualification_receipts=self.complete_qualification_receipts(),
            qualified_at=1000,
        )
        self.assertEqual(blocked.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        self.assertIn(
            RuntimeBlockerKind.BLOCKED_AUTHORITY,
            {item.kind for item in blocked.missing_obligations},
        )

    def test_verifier_identities_are_independent_and_receipt_bound(self):
        duplicate = RuntimeVerifier()
        duplicate.verifier_id = self.tool_verifier.verifier_id
        with self.assertRaisesRegex(ValueError, "must be independent"):
            RobloxRuntimeAdapter(
                self.tool_verifier,
                duplicate,
                self.authority_verifier,
                self.qualification_verifier,
            )

        substituted = self.runtime_receipt(
            RuntimeEvidenceClass.STUDIO_ENGINE,
            "core-loop",
            verifier_id="foreign.runtime-verifier",
        )
        report = self.qualify(runtime_receipts=(substituted,))
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        substituted_result = self.qualification_receipt(
            QualificationEvidenceKind.SECURITY,
            verifier_id="foreign.qualification-verifier",
        )
        receipts = tuple(
            substituted_result
            if item.evidence_kind is QualificationEvidenceKind.SECURITY
            else item
            for item in self.complete_qualification_receipts()
        )
        report = self.qualify(
            runtime_receipts=self.complete_receipts(),
            qualification_receipts=receipts,
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        injected_runtime_verifier = RuntimeVerifier()
        injected_runtime_verifier.verifier_id = "injected.runtime-verifier"
        injected_adapter = RobloxRuntimeAdapter(
            self.tool_verifier,
            injected_runtime_verifier,
            self.authority_verifier,
            self.qualification_verifier,
        )
        original = self.adapter
        self.adapter = injected_adapter
        try:
            injected_receipts = tuple(
                self.runtime_receipt(
                    receipt.evidence_class,
                    receipt.scenario_id,
                    receipt.device_id,
                    receipt_ref=receipt.receipt_ref,
                    verifier_id="injected.runtime-verifier",
                )
                for receipt in self.complete_receipts()
            )
            report = self.qualify(runtime_receipts=injected_receipts)
        finally:
            self.adapter = original
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

    def test_result_groups_require_independent_receipts(self):
        report = self.qualify(
            runtime_receipts=self.complete_receipts(),
            qualification_receipts=(),
        )

        self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        obligation_ids = {item.obligation_id for item in report.missing_obligations}
        for kind in QualificationEvidenceKind:
            self.assertIn(
                "n27.qualification-receipt-" + kind.value.lower(),
                obligation_ids,
            )

        bad_payload = self.qualification_receipt(
            QualificationEvidenceKind.METRIC,
            payload_digest=D4,
        )
        receipts = tuple(
            bad_payload
            if item.evidence_kind is QualificationEvidenceKind.METRIC
            else item
            for item in self.complete_qualification_receipts()
        )
        report = self.qualify(
            runtime_receipts=self.complete_receipts(),
            qualification_receipts=receipts,
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

    def test_expired_leases_and_stale_or_future_receipts_fail_closed(self):
        expired = self.admission(
            broker_lease_expires_at=999,
            resource_lease_expires_at=999,
        )
        report = self.qualify(
            admission=expired,
            runtime_receipts=self.complete_receipts(),
        )
        self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        self.assertIn(
            "n27.runtime-lease-expired",
            {item.obligation_id for item in report.missing_obligations},
        )

        stale = self.studio_receipt(observed_at=700, expires_at=1100)
        report = self.qualify(
            admission=self.admission(evidence_max_age_seconds=200),
            studio_receipt=stale,
            runtime_receipts=self.complete_receipts(),
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        future = self.qualification_receipt(
            QualificationEvidenceKind.CLEANUP,
            observed_at=1001,
        )
        receipts = tuple(
            future
            if item.evidence_kind is QualificationEvidenceKind.CLEANUP
            else item
            for item in self.complete_qualification_receipts()
        )
        report = self.qualify(
            runtime_receipts=self.complete_receipts(),
            qualification_receipts=receipts,
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

    def test_qualification_and_runtime_receipt_replay_is_rejected(self):
        replayed = self.qualification_receipt(
            QualificationEvidenceKind.METRIC,
            receipt_ref="ref:runtime/studio_engine/core-loop",
        )
        receipts = tuple(
            replayed
            if item.evidence_kind is QualificationEvidenceKind.METRIC
            else item
            for item in self.complete_qualification_receipts()
        )
        report = self.qualify(
            runtime_receipts=self.complete_receipts(),
            qualification_receipts=receipts,
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        old_run = self.runtime_receipt(
            RuntimeEvidenceClass.STUDIO_ENGINE,
            "core-loop",
            qualification_id="qualification.n27.old",
        )
        report = self.qualify(runtime_receipts=(old_run,))
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

    def test_verifier_and_file_exceptions_become_typed_blockers(self):
        adapters = (
            RobloxRuntimeAdapter(
                ToolVerifier(error=OSError("tool unavailable")),
                self.runtime_verifier,
                self.authority_verifier,
                self.qualification_verifier,
            ),
            RobloxRuntimeAdapter(
                self.tool_verifier,
                RuntimeVerifier(error=TimeoutError("runtime unavailable")),
                self.authority_verifier,
                self.qualification_verifier,
            ),
            RobloxRuntimeAdapter(
                self.tool_verifier,
                self.runtime_verifier,
                AuthorityVerifier(error=ConnectionError("broker unavailable")),
                self.qualification_verifier,
            ),
            RobloxRuntimeAdapter(
                self.tool_verifier,
                self.runtime_verifier,
                self.authority_verifier,
                QualificationVerifier(error=TimeoutError("curator unavailable")),
            ),
        )
        expected_ids = (
            "n27.studio-verifier-unavailable",
            "n27.runtime-verifier-unavailable",
            "n27.runtime-authority-verifier-unavailable",
            "n27.qualification-verifier-metric",
        )
        for adapter, expected_id in zip(adapters, expected_ids, strict=True):
            with self.subTest(expected_id=expected_id):
                original = self.adapter
                self.adapter = adapter
                try:
                    report = self.qualify(runtime_receipts=self.complete_receipts())
                finally:
                    self.adapter = original
                self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
                self.assertIn(
                    expected_id,
                    {item.obligation_id for item in report.missing_obligations},
                )

        with patch(
            "hive_mind_os.roblox_runtime.Path.read_bytes",
            side_effect=OSError("file busy"),
        ):
            report = self.qualify(runtime_receipts=self.complete_receipts())
        self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        self.assertIn(
            "n27.project-file-observation",
            {item.obligation_id for item in report.missing_obligations},
        )

    def test_stale_candidate_receipt_and_manifest_substitution_fail(self):
        stale = self.runtime_receipt(
            RuntimeEvidenceClass.STUDIO_ENGINE,
            "core-loop",
            candidate_digest=D4,
        )
        report = self.qualify(runtime_receipts=(stale,))
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        stale_scenario = self.runtime_receipt(
            RuntimeEvidenceClass.STUDIO_ENGINE,
            "core-loop",
            scenario_manifest_digest=D4,
        )
        report = self.qualify(runtime_receipts=(stale_scenario,))
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        self.manifest.write_text('{"name":"changed"}\n', encoding="utf-8")
        report = self.qualify(runtime_receipts=())
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        self.manifest.write_text('{"name":"fixture"}\n', encoding="utf-8")
        self.studio.write_bytes(b"substituted executable")
        report = self.qualify(runtime_receipts=())
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

    def test_absent_project_rights_device_and_authority_are_typed(self):
        absent = Path(self.temporary.name) / "absent"
        admission = self.admission(
            project_root=str(absent),
            project_manifest_path=str(absent / "default.project.json"),
            required_device_ids=(),
            account_capability_refs=(),
            authority_refs=(),
            asset_rights_refs=(),
            broker_lease_ref=None,
            resource_lease_ref=None,
            broker_lease_expires_at=None,
            resource_lease_expires_at=None,
        )
        report = self.adapter.qualify(
            admission,
            studio_receipt=None,
            runtime_receipts=(),
            performance_samples=(),
            persistence_results={},
            security_results={},
            asset_results={},
            cleanup_receipt=None,
            qualification_receipts=(),
            qualified_at=1000,
        )

        self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        kinds = {item.kind for item in report.missing_obligations}
        self.assertEqual(
            kinds,
            {
                RuntimeBlockerKind.BLOCKED_CAPABILITY,
                RuntimeBlockerKind.BLOCKED_SOURCE,
                RuntimeBlockerKind.BLOCKED_AUTHORITY,
            },
        )
        self.assertTrue(validate_contract("roblox-runtime-evidence", report.to_dict()).valid)

    def test_static_discovery_cannot_be_constructed_as_runtime_receipt(self):
        with self.assertRaisesRegex(ValueError, "static discovery"):
            self.runtime_receipt(
                RuntimeEvidenceClass.STATIC_DISCOVERY,
                "core-loop",
            )

        with self.assertRaisesRegex(ValueError, "separate authorized release"):
            report = self.qualify(runtime_receipts=self.complete_receipts())
            RobloxRuntimeEvidence(
                **{
                    **report.to_dict(),
                    "verdict": RuntimeVerdict.DEPLOYED_OBSERVED,
                }
            )

    def test_duplicate_runtime_observation_fails_closed(self):
        receipt = self.runtime_receipt(
            RuntimeEvidenceClass.STUDIO_ENGINE, "core-loop"
        )
        report = self.qualify(runtime_receipts=(receipt, receipt))
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

    def test_closed_schema_and_candidate_conditions_reject_substitution(self):
        blocker = blocked_runtime(
            "rights-cleared project absent",
            kind=RuntimeBlockerKind.BLOCKED_SOURCE,
            obligation_id="n27.owner-project",
        )
        document = blocker.to_dict()
        self.assertTrue(validate_contract("roblox-runtime-evidence", document).valid)

        unknown = copy.deepcopy(document)
        unknown["invented_runtime_pass"] = True
        self.assertFalse(validate_contract("roblox-runtime-evidence", unknown).valid)

        candidate = self.qualify(runtime_receipts=self.complete_receipts()).to_dict()
        candidate["runtime_receipts"] = []
        self.assertFalse(validate_contract("roblox-runtime-evidence", candidate).valid)

        candidate = self.qualify(runtime_receipts=self.complete_receipts()).to_dict()
        candidate["security_results"] = {"required": "FAIL"}
        self.assertFalse(validate_contract("roblox-runtime-evidence", candidate).valid)
        with self.assertRaisesRegex(ValueError, "security acceptance"):
            RobloxRuntimeEvidence.from_dict(candidate)

        for result_group in (
            "persistence_results",
            "security_results",
            "asset_results",
        ):
            empty = self.qualify(runtime_receipts=self.complete_receipts()).to_dict()
            empty[result_group] = {}
            with self.assertRaisesRegex(ValueError, "all acceptance result groups"):
                RobloxRuntimeEvidence.from_dict(empty)
            qualified_properties = load_schema("roblox-runtime-evidence")["allOf"][0][
                "then"
            ]["properties"]
            self.assertEqual(qualified_properties[result_group]["minProperties"], 1)

        candidate["verdict"] = "DEPLOYED_OBSERVED"
        self.assertFalse(validate_contract("roblox-runtime-evidence", candidate).valid)

    def test_legacy_constructor_order_retains_fail_closed_blocker_semantics(self):
        report = RobloxRuntimeEvidence(
            "unknown",
            "unknown",
            "unknown",
            "unavailable",
            "unknown",
            (),
            (),
            (),
            {},
            {},
            {},
            "none",
            RuntimeVerdict.BLOCKED_RUNTIME,
            cast(tuple[RuntimeObligation, ...], ("Studio worker unavailable",)),
        )

        self.assertEqual(report.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        self.assertEqual(
            report.missing_obligations[0].kind,
            RuntimeBlockerKind.BLOCKED_CAPABILITY,
        )
        self.assertTrue(validate_contract("roblox-runtime-evidence", report.to_dict()).valid)


if __name__ == "__main__":
    unittest.main()
