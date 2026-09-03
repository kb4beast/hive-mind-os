from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from base64 import b64encode
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any

from hive_mind_os.activation_bundle import (
    CAPABILITY_SECURITY_BOUNDARY,
    ActivationBundleError,
    ActivationPayload,
    AttestedActivation,
    AuthorizedOneRun,
    VerifiedActivation,
    parse_json_object,
    prepare_activation_bundle,
    request_sha256,
    reserve_one_run,
    restore_one_run,
    validate_draft_manifest,
    verify_external_attestations,
    verify_external_signature,
)

REQUEST = (
    "Approve an executable successor to `generic-hive-mind-product-v3`, bind it "
    "to `main` and this exact request, and issue a signed one-run activation bundle "
    "with independent review and frozen-host evidence."
)
NOW = datetime(2026, 9, 2, 12, 5, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


class NullOffset(tzinfo):
    def utcoffset(self, _value: datetime | None) -> None:
        return None

    def dst(self, _value: datetime | None) -> None:
        return None

    def fromutc(self, _value: datetime) -> datetime:
        raise AssertionError("null-offset time must be rejected before conversion")


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def principal(name: str) -> dict[str, str]:
    return {
        "principal_id": f"principal:{name}",
        "authority_domain": f"authority:{name}",
        "key_id": f"key:{name}",
    }


class MemoryNonceLedger:
    def __init__(self) -> None:
        self.consumed: set[str] = set()

    def consume_once(
        self,
        *,
        nonce: str,
        activation_digest: str,
        candidate_commit: str,
        candidate_tree: str,
        candidate_content_sha256: str,
        plan_sha256: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> bytes | None:
        self.last = (nonce, activation_digest, expires_at)
        if nonce in self.consumed:
            return None
        self.consumed.add(nonce)
        return canonical(
            {
                "schema_version": 1,
                "kind": "hive-mind-nonce-reservation-receipt-v1",
                "nonce": nonce,
                "activation_digest": activation_digest,
                "candidate_commit": candidate_commit,
                "candidate_tree": candidate_tree,
                "candidate_content_sha256": candidate_content_sha256,
                "plan_sha256": plan_sha256,
                "issued_at": issued_at.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "expires_at": expires_at.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "consumed_at": "2026-09-02T12:05:00Z",
                "ledger": principal("ledger"),
                "signature": "ledger-signature",
            }
        )


def verify_ledger_receipt(principal_value, _material: bytes, signature: str) -> bool:
    return (
        principal_value.key_id == "key:ledger"
        and signature == "ledger-signature"
    )


class GenericDagV4ActivationTests(unittest.TestCase):
    def artifacts(
        self,
        *,
        plan_bytes: bytes | None = None,
        nonce: str = "sha256:" + "e" * 64,
        candidate_branch: str = "codex/v4-fixture",
        repository_id: str = "sha256:" + "5" * 64,
        candidate_parent_commit: str = "0" * 40,
        candidate_parent_tree: str = "1" * 40,
        target_branch: str = "main",
    ) -> dict[str, Any]:
        if plan_bytes is None:
            plan_bytes = canonical(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-portable-dag-v1",
                    "plan_id": "generic-hive-mind-product-v4",
                    "nodes": [{"node_id": "DISCOVER-010"}],
                }
            )
        predecessor_receipt_bytes = canonical(
            {
                "schema_version": 1,
                "kind": "hive-mind-v3-qualification-receipt-v1",
                "receipt_id": "V3-R4-QUALIFICATION-2026-09-03",
                "case_id": "CASE-GENERIC-V3-BASELINE-RECOVERY-2026-09-02",
                "candidate_commit": "2" * 40,
                "candidate_tree": "3" * 40,
                "status": "QUALIFIED_INERT_PREDECESSOR",
                "disposition": "ADAPT",
                "court": {
                    "builder": "/root",
                    "curator": "/root/v3_r2_curator",
                    "judge": "/root/v3_r4_judge",
                    "verdict": "ADAPT",
                },
                "material_dissent": [{"finding_id": "V4-SBOM-P2-001"}],
                "execution_authorized": False,
                "activation_authorized": False,
                "release_ready": False,
                "deployment_ready": False,
                "production_ready": False,
                "protected_merge_authorized": False,
                "a5_ready": False,
                "superiority_claimed": False,
                "external_attestation": False,
                "signature": None,
            }
        )
        manifest = {
            "schema_version": 2,
            "kind": "hive-mind-generic-product-v4-manifest-v2",
            "plan_id": "generic-hive-mind-product-v4",
            "status": "CANDIDATE_NOT_AUTHORIZED",
            "predecessor": {
                "plan_id": "generic-hive-mind-product-v3",
                "commit": "2" * 40,
                "tree": "3" * 40,
                "qualification_receipt_path": "evidence/audits/generic-v3-baseline-recovery/V3-R4-QUALIFICATION.json",
                "qualification_receipt_sha256": digest(predecessor_receipt_bytes),
            },
            "candidate_base": {
                "commit": candidate_parent_commit,
                "tree": candidate_parent_tree,
            },
            "request_text": REQUEST,
            "request_sha256": request_sha256(REQUEST),
            "repository_id": repository_id,
            "source_intake": {
                "path": "evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json",
                "sha256": "sha256:" + "4" * 64,
                "archive_path": "evidence/sources/v4-successor-recovery/SOURCE-ARCHIVE.json",
                "archive_sha256": "sha256:" + "f" * 64,
                "source_count": 13,
                "unavailable_source_count": 0,
            },
            "target_branch": target_branch,
            "plan": {
                "path": "docs/execution/dags/generic-hive-mind-product-v4/plan.json",
                "sha256": digest(plan_bytes),
                "mode": "host-activated-generic-dag-v1",
                "node_count": 1,
            },
            "activation_policy": {
                "maximum_lease_seconds": 900,
                "nonce_uniqueness": "nonce-primary-key-global-single-use",
                "signature_order": [
                    "independent_review",
                    "frozen_host",
                    "issuer",
                    "nonce_cas",
                ],
                "required_principals": [
                    "builder",
                    "independent_reviewer",
                    "actor",
                    "issuer",
                    "host_attester",
                ],
                "protected_merge_authorized": False,
            },
            "execution_authorized": False,
        }
        manifest_bytes = canonical(manifest)
        common = {
            "candidate_commit": "6" * 40,
            "candidate_tree": "7" * 40,
            "candidate_content_sha256": "sha256:" + "8" * 64,
            "plan_sha256": digest(plan_bytes),
            "manifest_sha256": digest(manifest_bytes),
        }
        review = {
            "schema_version": 1,
            "kind": "hive-mind-independent-review-v1",
            **common,
            "reviewer": principal("reviewer"),
            "verdict": "ADOPT",
            "test_evidence_sha256": "sha256:" + "9" * 64,
            "reviewed_at": "2026-09-02T12:00:00Z",
            "signature": "review-signature",
        }
        review_bytes = canonical(review)
        frozen = {
            "schema_version": 1,
            "kind": "hive-mind-frozen-host-attestation-v1",
            **common,
            "candidate_parent_commit": candidate_parent_commit,
            "candidate_parent_tree": candidate_parent_tree,
            "attester": principal("host"),
            "host_bundle_sha256": "sha256:" + "a" * 64,
            "interpreter_sha256": "sha256:" + "b" * 64,
            "git_executable_sha256": "sha256:" + "c" * 64,
            "execution_client_sha256": "sha256:" + "d" * 64,
            "worktree_clean": True,
            "bytecode_free": True,
            "read_only_custody": True,
            "observed_at": "2026-09-02T12:00:00Z",
            "expires_at": "2026-09-02T12:20:00Z",
            "signature": "host-signature",
        }
        frozen_bytes = canonical(frozen)
        bundle = {
            "schema_version": 2,
            "kind": "hive-mind-one-run-activation-bundle-v2",
            "plan_id": "generic-hive-mind-product-v4",
            "request_sha256": request_sha256(REQUEST),
            "repository_id": manifest["repository_id"],
            "target_branch": target_branch,
            "predecessor_commit": "2" * 40,
            "predecessor_tree": "3" * 40,
            "candidate_parent_commit": candidate_parent_commit,
            "candidate_parent_tree": candidate_parent_tree,
            "candidate_branch": candidate_branch,
            **common,
            "frozen_host_evidence_sha256": digest(frozen_bytes),
            "review_evidence_sha256": digest(review_bytes),
            "builder": principal("builder"),
            "independent_reviewer": principal("reviewer"),
            "actor": principal("actor"),
            "issuer": principal("issuer"),
            "host_attester": principal("host"),
            "nonce": nonce,
            "issued_at": "2026-09-02T12:00:00Z",
            "expires_at": "2026-09-02T12:10:00Z",
            "signature": "issuer-signature",
        }
        return {
            "plan_bytes": plan_bytes,
            "predecessor_receipt_bytes": predecessor_receipt_bytes,
            "manifest": manifest,
            "manifest_bytes": manifest_bytes,
            "review": review,
            "review_bytes": review_bytes,
            "frozen": frozen,
            "frozen_bytes": frozen_bytes,
            "bundle": bundle,
            "bundle_bytes": canonical(bundle),
        }

    def prepare(
        self,
        artifacts: dict[str, Any] | None = None,
        *,
        now: datetime = NOW,
    ):
        values = artifacts or self.artifacts()
        return prepare_activation_bundle(
            bundle_bytes=values["bundle_bytes"],
            manifest_bytes=values["manifest_bytes"],
            plan_bytes=values["plan_bytes"],
            predecessor_receipt_bytes=values["predecessor_receipt_bytes"],
            review_evidence_bytes=values["review_bytes"],
            frozen_host_evidence_bytes=values["frozen_bytes"],
            now=now,
        )

    def authorize(self, artifacts: dict[str, Any] | None = None):
        payload = self.prepare(artifacts)
        attested = verify_external_attestations(
            payload,
            review_verifier=lambda p, _b, s: (
                p.key_id == "key:reviewer" and s == "review-signature"
            ),
            frozen_host_verifier=lambda p, _b, s: (
                p.key_id == "key:host" and s == "host-signature"
            ),
        )
        return verify_external_signature(
            attested,
            lambda p, _b, s: p.key_id == "key:issuer" and s == "issuer-signature",
        )

    def test_manifest_and_all_raw_artifacts_are_bound(self) -> None:
        values = self.artifacts()
        validate_draft_manifest(values["manifest"])
        payload = self.prepare(values)
        self.assertEqual("6" * 40, payload.candidate_commit)
        self.assertEqual(digest(values["plan_bytes"]), payload.plan_sha256)
        self.assertEqual(digest(values["manifest_bytes"]), payload.manifest_sha256)
        self.assertEqual("sha256:" + "5" * 64, payload.repository_id)
        self.assertEqual("main", payload.target_branch)
        self.assertEqual("sha256:" + "d" * 64, payload.execution_client_sha256)
        self.assertEqual(datetime(2026, 9, 2, 12, tzinfo=UTC), payload.issued_at)
        self.assertIs(payload.protected_merge_authorized, False)

        changed = dict(values)
        changed["plan_bytes"] = values["plan_bytes"] + b" "
        with self.assertRaisesRegex(ActivationBundleError, "plan bytes"):
            self.prepare(changed)

        changed = dict(values)
        changed["predecessor_receipt_bytes"] = (
            values["predecessor_receipt_bytes"] + b" "
        )
        with self.assertRaisesRegex(ActivationBundleError, "predecessor qualification"):
            self.prepare(changed)

    def test_current_time_requires_a_real_utc_offset_before_conversion(self) -> None:
        ambiguous = datetime(2026, 9, 2, 12, 5, tzinfo=NullOffset())

        with self.assertRaisesRegex(ActivationBundleError, "include a timezone"):
            self.prepare(now=ambiguous)

    def test_source_intake_binding_is_closed_and_complete(self) -> None:
        for field, value, error in (
            ("path", "other.json", "paths are not canonical"),
            ("source_count", 12, "exactly 13"),
            ("source_count", True, "counts must be integers"),
            ("unavailable_source_count", 1, "unavailable sources"),
            ("unavailable_source_count", False, "counts must be integers"),
        ):
            manifest = dict(self.artifacts()["manifest"])
            manifest["source_intake"] = {
                **manifest["source_intake"],
                field: value,
            }
            with self.subTest(field=field):
                with self.assertRaisesRegex(ActivationBundleError, error):
                    validate_draft_manifest(manifest)
        manifest = dict(self.artifacts()["manifest"])
        manifest["source_intake"] = {
            **manifest["source_intake"],
            "unbound_extension": True,
        }
        with self.assertRaisesRegex(ActivationBundleError, "fields are invalid"):
            validate_draft_manifest(manifest)

        for section, field in (
            ("plan", "node_count"),
            ("activation_policy", "maximum_lease_seconds"),
        ):
            manifest = dict(self.artifacts()["manifest"])
            manifest[section] = {**manifest[section], field: True}
            with self.subTest(section=section, field=field):
                with self.assertRaises(ActivationBundleError):
                    validate_draft_manifest(manifest)

    def test_predecessor_receipt_semantics_and_dissent_are_load_bearing(self) -> None:
        for field, value, error in (
            ("candidate_commit", "0" * 40, "receipt commit"),
            ("status", "QUALIFIED_RELEASE", "adapted inert"),
            ("activation_authorized", True, "deny activation_authorized"),
            ("signature", "repository-signature", "must not claim a signature"),
            ("material_dissent", [], "carried SBOM dissent"),
        ):
            values = self.artifacts()
            receipt = json.loads(values["predecessor_receipt_bytes"])
            receipt[field] = value
            values["predecessor_receipt_bytes"] = canonical(receipt)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ActivationBundleError, error):
                    self.prepare(values)

    def test_ordered_attestation_signature_and_nonce_gate(self) -> None:
        payload = self.prepare()
        with self.assertRaisesRegex(ActivationBundleError, "attestations"):
            verify_external_signature(payload, lambda *_: True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ActivationBundleError, "issuer signature"):
            reserve_one_run(  # type: ignore[arg-type]
                payload,  # pyright: ignore[reportArgumentType]
                MemoryNonceLedger(),
                receipt_verifier=verify_ledger_receipt,
            )

        verified = self.authorize()
        ledger = MemoryNonceLedger()
        authorized = reserve_one_run(
            verified, ledger, receipt_verifier=verify_ledger_receipt
        )
        self.assertEqual(
            verified.payload.activation_digest, authorized.activation_digest
        )
        with self.assertRaisesRegex(ActivationBundleError, "already used"):
            reserve_one_run(
                verified, ledger, receipt_verifier=verify_ledger_receipt
            )

        # The nonce, not (nonce, payload), is the primary key. A changed payload
        # cannot replay the same nonce under another digest.
        changed = self.authorize(
            self.artifacts(candidate_branch="codex/v4-fixture-changed")
        )
        self.assertNotEqual(
            verified.payload.activation_digest, changed.payload.activation_digest
        )
        with self.assertRaisesRegex(ActivationBundleError, "already used"):
            reserve_one_run(
                changed, ledger, receipt_verifier=verify_ledger_receipt
            )

    def test_nonce_receipt_signature_and_exact_activation_are_required(self) -> None:
        verified = self.authorize()
        with self.assertRaisesRegex(ActivationBundleError, "receipt signature"):
            reserve_one_run(
                verified,
                MemoryNonceLedger(),
                receipt_verifier=lambda *_: False,
            )

        authorized = reserve_one_run(
            verified,
            MemoryNonceLedger(),
            receipt_verifier=verify_ledger_receipt,
        )
        changed = json.loads(authorized.reservation_receipt)
        changed["candidate_tree"] = "f" * 40
        with self.assertRaisesRegex(ActivationBundleError, "candidate_tree"):
            restore_one_run(
                verified,
                canonical(changed),
                receipt_verifier=verify_ledger_receipt,
            )

        changed = json.loads(authorized.reservation_receipt)
        changed["consumed_at"] = "2026-09-02T11:59:59Z"
        with self.assertRaisesRegex(ActivationBundleError, "validity interval"):
            restore_one_run(
                verified,
                canonical(changed),
                receipt_verifier=verify_ledger_receipt,
            )

    def test_nonce_ledger_principal_and_key_are_independent(self) -> None:
        verified = self.authorize()
        authorized = reserve_one_run(
            verified,
            MemoryNonceLedger(),
            receipt_verifier=verify_ledger_receipt,
        )
        original = json.loads(authorized.reservation_receipt)
        for field, value, error in (
            ("principal_id", "principal:issuer", "principal must be independent"),
            ("key_id", "key:issuer", "key must be independent"),
        ):
            changed = json.loads(json.dumps(original))
            changed["ledger"][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ActivationBundleError, error):
                    restore_one_run(
                        verified,
                        canonical(changed),
                        receipt_verifier=lambda *_: True,
                    )

    def test_boolean_schema_versions_are_rejected(self) -> None:
        values = self.artifacts()
        predecessor = json.loads(values["predecessor_receipt_bytes"])
        predecessor["schema_version"] = True
        values["predecessor_receipt_bytes"] = canonical(predecessor)
        with self.assertRaisesRegex(ActivationBundleError, "canonical R4"):
            self.prepare(values)

        verified = self.authorize()
        authorized = reserve_one_run(
            verified,
            MemoryNonceLedger(),
            receipt_verifier=verify_ledger_receipt,
        )
        reservation = json.loads(authorized.reservation_receipt)
        reservation["schema_version"] = True
        with self.assertRaisesRegex(ActivationBundleError, "kind or version"):
            restore_one_run(
                verified,
                canonical(reservation),
                receipt_verifier=lambda *_: True,
            )

    def test_signed_nonce_receipt_restores_in_a_fresh_process(self) -> None:
        values = self.artifacts()
        verified = self.authorize(values)
        authorized = reserve_one_run(
            verified,
            MemoryNonceLedger(),
            receipt_verifier=verify_ledger_receipt,
        )
        wire = {
            name: b64encode(values[name]).decode("ascii")
            for name in (
                "bundle_bytes",
                "manifest_bytes",
                "plan_bytes",
                "predecessor_receipt_bytes",
                "review_bytes",
                "frozen_bytes",
            )
        }
        wire["reservation_receipt"] = b64encode(
            authorized.reservation_receipt
        ).decode("ascii")
        script = r"""
import base64
import json
import sys
from datetime import UTC, datetime

sys.path.insert(0, sys.argv[1])
from hive_mind_os.activation_bundle import (
    prepare_activation_bundle,
    restore_one_run,
    verify_external_attestations,
    verify_external_signature,
)

wire = json.load(sys.stdin)
decode = lambda name: base64.b64decode(wire[name], validate=True)
payload = prepare_activation_bundle(
    bundle_bytes=decode("bundle_bytes"),
    manifest_bytes=decode("manifest_bytes"),
    plan_bytes=decode("plan_bytes"),
    predecessor_receipt_bytes=decode("predecessor_receipt_bytes"),
    review_evidence_bytes=decode("review_bytes"),
    frozen_host_evidence_bytes=decode("frozen_bytes"),
    now=datetime(2026, 9, 2, 12, 5, tzinfo=UTC),
)
attested = verify_external_attestations(
    payload,
    review_verifier=lambda p, _b, s: p.key_id == "key:reviewer" and s == "review-signature",
    frozen_host_verifier=lambda p, _b, s: p.key_id == "key:host" and s == "host-signature",
)
verified = verify_external_signature(
    attested,
    lambda p, _b, s: p.key_id == "key:issuer" and s == "issuer-signature",
)
authorized = restore_one_run(
    verified,
    decode("reservation_receipt"),
    receipt_verifier=lambda p, _b, s: p.key_id == "key:ledger" and s == "ledger-signature",
)
print(json.dumps({"activation_digest": authorized.activation_digest, "proof_digest": authorized.proof_digest}))
"""
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script, str(ROOT / "src")],
            input=json.dumps(wire).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
        restored = json.loads(completed.stdout)
        self.assertEqual(authorized.activation_digest, restored["activation_digest"])
        self.assertEqual(authorized.proof_digest, restored["proof_digest"])

    def test_public_construction_fails_and_boundary_is_explicitly_process_local(
        self,
    ) -> None:
        self.assertEqual(
            "trusted-process-integrity-only", CAPABILITY_SECURITY_BOUNDARY
        )
        payload = self.prepare()
        for stage, arguments in (
            (ActivationPayload, ()),
            (AttestedActivation, (payload,)),
            (VerifiedActivation, (payload,)),
            (AuthorizedOneRun, (payload,)),
        ):
            with self.subTest(stage=stage.__name__):
                with self.assertRaisesRegex(
                    ActivationBundleError, "only be issued"
                ):
                    stage(*arguments)

    def test_every_external_signature_is_required(self) -> None:
        payload = self.prepare()
        with self.assertRaisesRegex(ActivationBundleError, "independent-review"):
            verify_external_attestations(
                payload,
                review_verifier=lambda *_: False,
                frozen_host_verifier=lambda *_: True,
            )
        with self.assertRaisesRegex(ActivationBundleError, "frozen-host"):
            verify_external_attestations(
                payload,
                review_verifier=lambda *_: True,
                frozen_host_verifier=lambda *_: False,
            )
        attested = verify_external_attestations(
            payload,
            review_verifier=lambda *_: True,
            frozen_host_verifier=lambda *_: True,
        )
        with self.assertRaisesRegex(ActivationBundleError, "issuer signature"):
            verify_external_signature(attested, lambda *_: False)

    def test_identity_collisions_and_candidate_substitution_fail(self) -> None:
        values = self.artifacts()
        bundle = dict(values["bundle"])
        bundle["actor"] = bundle["independent_reviewer"]
        values["bundle_bytes"] = canonical(bundle)
        with self.assertRaisesRegex(
            ActivationBundleError, "principals must be distinct"
        ):
            self.prepare(values)

        for field, value in (
            ("principal_id", " principal:reviewer"),
            ("key_id", "key:reviewer "),
        ):
            values = self.artifacts()
            bundle = dict(values["bundle"])
            actor = dict(bundle["actor"])
            actor[field] = value
            bundle["actor"] = actor
            values["bundle_bytes"] = canonical(bundle)
            with self.subTest(canonical_identity_field=field):
                with self.assertRaisesRegex(ActivationBundleError, "canonical"):
                    self.prepare(values)

        values = self.artifacts()
        frozen = dict(values["frozen"])
        frozen["candidate_tree"] = "0" * 40
        values["frozen_bytes"] = canonical(frozen)
        bundle = dict(values["bundle"])
        bundle["frozen_host_evidence_sha256"] = digest(values["frozen_bytes"])
        values["bundle_bytes"] = canonical(bundle)
        with self.assertRaisesRegex(ActivationBundleError, "candidate_tree"):
            self.prepare(values)

        values = self.artifacts()
        manifest = dict(values["manifest"])
        manifest["candidate_base"] = {"commit": "a" * 40, "tree": "b" * 40}
        values["manifest_bytes"] = canonical(manifest)
        bundle = dict(values["bundle"])
        bundle["manifest_sha256"] = digest(values["manifest_bytes"])
        values["bundle_bytes"] = canonical(bundle)
        with self.assertRaisesRegex(ActivationBundleError, "candidate_parent_commit"):
            self.prepare(values)

    def test_stale_or_non_adopting_evidence_fails(self) -> None:
        values = self.artifacts()
        review = dict(values["review"])
        review["verdict"] = "DEFER"
        values["review_bytes"] = canonical(review)
        bundle = dict(values["bundle"])
        bundle["review_evidence_sha256"] = digest(values["review_bytes"])
        values["bundle_bytes"] = canonical(bundle)
        with self.assertRaisesRegex(ActivationBundleError, "did not adopt"):
            self.prepare(values)

        values = self.artifacts()
        frozen = dict(values["frozen"])
        frozen["expires_at"] = "2026-09-02T12:09:59Z"
        values["frozen_bytes"] = canonical(frozen)
        bundle = dict(values["bundle"])
        bundle["frozen_host_evidence_sha256"] = digest(values["frozen_bytes"])
        values["bundle_bytes"] = canonical(bundle)
        with self.assertRaisesRegex(ActivationBundleError, "stale"):
            self.prepare(values)

    def test_strict_json_rejects_duplicates_nonfinite_depth_and_size(self) -> None:
        with self.assertRaisesRegex(ActivationBundleError, "duplicate JSON key"):
            parse_json_object(b'{"x":1,"x":2}', label="fixture", maximum_bytes=100)
        with self.assertRaisesRegex(ActivationBundleError, "non-finite"):
            parse_json_object(b'{"x":NaN}', label="fixture", maximum_bytes=100)
        deep = (b'{"x":' * 21) + b"0" + (b"}" * 21)
        with self.assertRaisesRegex(ActivationBundleError, "nesting-depth"):
            parse_json_object(deep, label="fixture", maximum_bytes=1_000)
        with self.assertRaisesRegex(ActivationBundleError, "byte limit"):
            parse_json_object(b'{"x":1}', label="fixture", maximum_bytes=2)


def authorized_one_run_fixture(
    plan_bytes: bytes,
    *,
    nonce_seed: str = "fixture-one-run",
    repository_id: str = "sha256:" + "5" * 64,
    candidate_parent_commit: str = "0" * 40,
    candidate_parent_tree: str = "1" * 40,
    target_branch: str = "main",
) -> AuthorizedOneRun:
    """Issue a real, parser-bound capability for downstream runtime tests."""

    fixture = GenericDagV4ActivationTests()
    artifacts = fixture.artifacts(
        plan_bytes=plan_bytes,
        nonce=digest(nonce_seed.encode("utf-8")),
        repository_id=repository_id,
        candidate_parent_commit=candidate_parent_commit,
        candidate_parent_tree=candidate_parent_tree,
        target_branch=target_branch,
    )
    return reserve_one_run(
        fixture.authorize(artifacts),
        MemoryNonceLedger(),
        receipt_verifier=verify_ledger_receipt,
    )


if __name__ == "__main__":
    unittest.main()
