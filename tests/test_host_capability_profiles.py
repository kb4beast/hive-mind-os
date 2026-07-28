from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from hive_mind_os.contracts import validate_contract
from hive_mind_os.package_system import (
    ConformanceStatus,
    EvidenceLevel,
    HostCapability,
    HostCapabilityProfile,
    load_builtin_host_profile,
    load_builtin_host_profiles,
)
from hive_mind_os.package_system.builtins import hive_core_catalog, hive_core_root


def test_capabilities_are_explicit_and_evidence_level_is_not_inflated() -> None:
    profile = HostCapabilityProfile(
        host_id="codex",
        host_version_ref="docs:2026-07-28",
        adapter_version="1.0.0",
        evidence_level=EvidenceLevel.DOCUMENTED,
        conformance_status=ConformanceStatus.UNVERIFIED,
        capabilities=frozenset(
            {
                HostCapability.INSTRUCTION_PROJECTION,
                HostCapability.SKILL_MD,
                HostCapability.CUSTOM_AGENTS,
            }
        ),
        evidence_refs=("https://learn.chatgpt.com/docs/customization/overview",),
        evidence_obligations=("source admission pending",),
    )
    required = frozenset(
        {HostCapability.SKILL_MD, HostCapability.WORKTREE_ISOLATION}
    )
    assert not profile.supports(required)
    assert not profile.supports(frozenset({HostCapability.SKILL_MD}))
    assert profile.declares(frozenset({HostCapability.SKILL_MD}))
    assert profile.missing(required) == {HostCapability.WORKTREE_ISOLATION}
    assert profile.to_contract()["evidence_level"] == "documented"
    assert profile.fingerprint.startswith("sha256:")


def test_profile_requires_versioned_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        HostCapabilityProfile(
            host_id="hermes",
            host_version_ref="commit:abc",
            adapter_version="1.0.0",
            evidence_level=EvidenceLevel.DECLARED,
            conformance_status=ConformanceStatus.UNVERIFIED,
            capabilities=frozenset(),
            evidence_refs=(),
            evidence_obligations=("source admission pending",),
        )


def test_passed_conformance_requires_tested_evidence() -> None:
    with pytest.raises(ValueError, match="passed conformance requires tested"):
        HostCapabilityProfile(
            host_id="codex",
            host_version_ref="evidence:test",
            adapter_version="1.0.0",
            evidence_level=EvidenceLevel.DOCUMENTED,
            conformance_status=ConformanceStatus.PASSED,
            capabilities=frozenset({HostCapability.SKILL_MD}),
            evidence_refs=("docs:skills",),
            evidence_obligations=(),
        )

    with pytest.raises(ValueError, match="cannot retain evidence obligations"):
        HostCapabilityProfile(
            host_id="codex",
            host_version_ref="evidence:test",
            adapter_version="1.0.0",
            evidence_level=EvidenceLevel.TESTED,
            conformance_status=ConformanceStatus.PASSED,
            capabilities=frozenset({HostCapability.SKILL_MD}),
            evidence_refs=("receipt:conformance",),
            evidence_obligations=("source admission pending",),
        )
    invalid_contract = {
        "schema_version": 1,
        "host_id": "codex",
        "host_version_ref": "evidence:test",
        "adapter_version": "1.0.0",
        "evidence_level": "tested",
        "conformance_status": "passed",
        "capabilities": ["skill_md"],
        "evidence_refs": ["receipt:conformance"],
        "evidence_obligations": ["source admission pending"],
    }
    assert not validate_contract("host-capability-profile", invalid_contract).valid


def test_from_contract_rejects_duplicate_capability_and_unknown_status() -> None:
    baseline = {
        "schema_version": 1,
        "host_id": "test-host",
        "host_version_ref": "evidence:test",
        "adapter_version": "1.0.0",
        "evidence_level": "tested",
        "conformance_status": "passed",
        "capabilities": ["skill_md"],
        "evidence_refs": ["receipt:conformance"],
        "evidence_obligations": [],
    }
    profile = HostCapabilityProfile.from_contract(baseline)
    assert not profile.supports(frozenset({HostCapability.SKILL_MD}))
    assert profile.supports(
        frozenset({HostCapability.SKILL_MD}),
        conformance_verifier=lambda candidate: candidate.fingerprint
        == profile.fingerprint,
    )
    assert not profile.supports(
        frozenset({HostCapability.SKILL_MD}),
        conformance_verifier=lambda candidate: {"passed": False},  # type: ignore[return-value]
    )

    duplicate = dict(baseline, capabilities=["skill_md", "skill_md"])
    with pytest.raises(ValueError, match="cannot contain duplicates"):
        HostCapabilityProfile.from_contract(duplicate)
    unknown = dict(baseline, conformance_status="assumed")
    with pytest.raises(ValueError, match="invalid host capability"):
        HostCapabilityProfile.from_contract(unknown)


@pytest.mark.parametrize(
    "field",
    ("host_id", "host_version_ref", "adapter_version"),
)
def test_formal_schema_and_runtime_reject_whitespace_identifiers(field: str) -> None:
    document = {
        "schema_version": 1,
        "host_id": "test-host",
        "host_version_ref": "evidence:test",
        "adapter_version": "1.0.0",
        "evidence_level": "documented",
        "conformance_status": "unverified",
        "capabilities": [],
        "evidence_refs": ["docs:test"],
        "evidence_obligations": ["source admission pending"],
    }
    document[field] = "   "
    assert not validate_contract("host-capability-profile", document).valid
    with pytest.raises(ValueError):
        HostCapabilityProfile.from_contract(document)


def test_formal_schema_and_runtime_reject_whitespace_evidence_refs() -> None:
    document = {
        "schema_version": 1,
        "host_id": "test-host",
        "host_version_ref": "evidence:test",
        "adapter_version": "1.0.0",
        "evidence_level": "documented",
        "conformance_status": "unverified",
        "capabilities": [],
        "evidence_refs": ["   "],
        "evidence_obligations": ["source admission pending"],
    }
    assert not validate_contract("host-capability-profile", document).valid
    with pytest.raises(ValueError):
        HostCapabilityProfile.from_contract(document)


def test_builtin_profiles_are_declared_evidence_not_support_claims() -> None:
    profiles = load_builtin_host_profiles()
    assert {profile.host_id for profile in profiles} == {
        "codex",
        "claude-code",
        "hermes",
    }
    for profile in profiles:
        assert profile.evidence_level is EvidenceLevel.DECLARED
        assert profile.conformance_status is ConformanceStatus.UNVERIFIED
        assert not profile.supports(frozenset())
        assert profile.evidence_refs
        assert profile.evidence_obligations


def test_builtin_profile_rechecks_digest_at_the_read_boundary(
    tmp_path: Path,
) -> None:
    catalog = hive_core_catalog()
    copied = tmp_path / "hive-core"
    shutil.copytree(hive_core_root(), copied)
    path = copied / "host_profiles" / "codex.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["capabilities"].append("receipts")
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")

    with (
        patch(
            "hive_mind_os.package_system.builtins.hive_core_catalog",
            return_value=catalog,
        ),
        patch(
            "hive_mind_os.package_system.builtins.hive_core_root",
            return_value=copied,
        ),
        pytest.raises(ValueError, match="digest changed"),
    ):
        load_builtin_host_profile("codex")
