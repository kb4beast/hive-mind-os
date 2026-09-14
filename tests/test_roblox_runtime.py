import copy
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from typing import cast

from hive_mind_os.contracts import validate_contract
from hive_mind_os.roblox_runtime import (
    RobloxRuntimeAdapter,
    RobloxRuntimeAdmission,
    RobloxRuntimeEvidence,
    RuntimeBlockerKind,
    RuntimeEvidenceClass,
    RuntimeObligation,
    RuntimeReceipt,
    RuntimeVerdict,
    StudioToolReceipt,
    blocked_runtime,
)

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


class ToolVerifier:
    verifier_id = "fixture.tool-verifier"

    def __init__(self, accepted=True):
        self.accepted = accepted
        self.calls = []

    def verify_tool_receipt(self, receipt):
        self.calls.append(receipt)
        return self.accepted


class RuntimeVerifier:
    verifier_id = "fixture.runtime-verifier"

    def __init__(self, accepted=True):
        self.accepted = accepted
        self.calls = []

    def verify_runtime_receipt(self, receipt):
        self.calls.append(receipt)
        return self.accepted


class AuthorityVerifier:
    verifier_id = "fixture.authority-verifier"

    def __init__(self, accepted=True):
        self.accepted = accepted
        self.calls = []

    def verify_runtime_authority(self, admission):
        self.calls.append(admission)
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
        self.adapter = RobloxRuntimeAdapter(
            self.tool_verifier, self.runtime_verifier, self.authority_verifier
        )

    def tearDown(self):
        self.temporary.cleanup()

    def admission(self, **changes):
        values = {
            "candidate_digest": D1,
            "profile_digest": D2,
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
            "resource_lease_ref": "ref:lease/runtime.n27",
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
            "observed_at": 1,
        }
        values.update(changes)
        return StudioToolReceipt(**values)

    def runtime_receipt(self, evidence_class, scenario, device=None, **changes):
        values = {
            "receipt_ref": f"ref:runtime/{evidence_class.value.lower()}/{scenario}",
            "evidence_class": evidence_class,
            "candidate_digest": D1,
            "profile_digest": D2,
            "project_manifest_digest": self.manifest_digest,
            "scenario_manifest_digest": D3,
            "studio_binary_digest": self.studio_digest,
            "studio_version": "0.735.0.7351131",
            "studio_tool_receipt_ref": "ref:host/studio.discovery",
            "environment_id": "test-universe.n27",
            "scenario_id": scenario,
            "device_id": device,
            "passed": True,
            "observed_at": 2,
        }
        values.update(changes)
        return RuntimeReceipt(**values)

    def qualify(self, admission=None, studio_receipt=None, runtime_receipts=()):
        return self.adapter.qualify(
            admission or self.admission(),
            studio_receipt=(
                self.studio_receipt()
                if studio_receipt is None
                else studio_receipt
            ),
            runtime_receipts=runtime_receipts,
            performance_samples=(16.5,),
            persistence_results={"retry-idempotency": "PASS"},
            security_results={"hostile-client": "PASS"},
            asset_results={"load-and-rights": "PASS"},
            cleanup_receipt="ref:cleanup/runtime.n27",
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

    def test_verified_engine_and_device_matrix_can_form_candidate_evidence(self):
        report = self.qualify(runtime_receipts=self.complete_receipts())

        self.assertEqual(report.verdict, RuntimeVerdict.PRODUCTION_CANDIDATE)
        self.assertEqual(report.missing_obligations, ())
        self.assertEqual(len(report.runtime_receipts), 4)
        self.assertEqual(len(self.runtime_verifier.calls), 4)
        validation = validate_contract("roblox-runtime-evidence", report.to_dict())
        self.assertTrue(validation.valid, validation.issues)
        self.assertEqual(RobloxRuntimeEvidence.from_dict(report.to_dict()), report)

    def test_invalid_authenticode_or_unverified_runtime_fails_closed(self):
        bad_tool = self.studio_receipt(signature_status="NotSigned")
        report = self.qualify(
            studio_receipt=bad_tool, runtime_receipts=self.complete_receipts()
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        rejecting = RobloxRuntimeAdapter(
            self.tool_verifier, RuntimeVerifier(False), self.authority_verifier
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
        )
        self.assertEqual(report.verdict, RuntimeVerdict.FAILED)

        blocked = RobloxRuntimeAdapter(
            self.tool_verifier,
            self.runtime_verifier,
            AuthorityVerifier(False),
        ).qualify(
            self.admission(),
            studio_receipt=self.studio_receipt(),
            runtime_receipts=self.complete_receipts(),
            performance_samples=(16.5,),
            persistence_results={"retry-idempotency": "PASS"},
            security_results={"hostile-client": "PASS"},
            asset_results={"load-and-rights": "PASS"},
            cleanup_receipt="ref:cleanup/runtime.n27",
        )
        self.assertEqual(blocked.verdict, RuntimeVerdict.BLOCKED_RUNTIME)
        self.assertIn(
            RuntimeBlockerKind.BLOCKED_AUTHORITY,
            {item.kind for item in blocked.missing_obligations},
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
            resource_lease_ref=None,
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
