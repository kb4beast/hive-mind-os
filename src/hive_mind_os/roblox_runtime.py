"""Fail-closed Roblox Studio/runtime evidence adapter (N27).

Discovery of a signed Studio binary is static host evidence. Runtime and device
claims are accepted only through separately injected receipt verifiers and exact
candidate/profile/project/tool bindings. This module never launches Studio,
reads an account, or discovers assets on its own.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Protocol, cast

from .brain_kernel.canonical import canonical_digest, canonical_document

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_REF = re.compile(r"^ref:[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$")
_THUMBPRINT = re.compile(r"^[0-9A-Fa-f]{40,128}$")


class RuntimeVerdict(StrEnum):
    RUNTIME_VALIDATED = "RUNTIME_VALIDATED"
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
    BLOCKED_RUNTIME = "BLOCKED_RUNTIME"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    DEPLOYED_OBSERVED = "DEPLOYED_OBSERVED"


class RuntimeEvidenceClass(StrEnum):
    STATIC_DISCOVERY = "STATIC_DISCOVERY"
    STUDIO_ENGINE = "STUDIO_ENGINE"
    PHYSICAL_DEVICE = "PHYSICAL_DEVICE"


class QualificationEvidenceKind(StrEnum):
    METRIC = "METRIC"
    PERSISTENCE = "PERSISTENCE"
    SECURITY = "SECURITY"
    ASSET = "ASSET"
    CLEANUP = "CLEANUP"


class VerifierEvidenceScope(StrEnum):
    CONTRACT_FIXTURE = "CONTRACT_FIXTURE"
    EXTERNAL_ATTESTATION = "EXTERNAL_ATTESTATION"


class RuntimeBlockerKind(StrEnum):
    BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
    BLOCKED_SOURCE = "BLOCKED_SOURCE"
    BLOCKED_AUTHORITY = "BLOCKED_AUTHORITY"


def _require_digest(value: str, label: str) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_id(value: str, label: str) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical identifier")


def _require_ref(value: str, label: str) -> None:
    if type(value) is not str or _REF.fullmatch(value) is None:
        raise ValueError(f"{label} must be an opaque ref: reference")


def _absolute_path(value: str, label: str) -> Path:
    if type(value) is not str or not value or not Path(value).is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    raw = Path(value)
    if ".." in raw.parts:
        raise ValueError(f"{label} must not contain parent traversal")
    return raw.resolve(strict=False)


def _unique(values: tuple[str, ...], label: str, *, refs: bool = False) -> None:
    if type(values) is not tuple or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be a sorted unique tuple")
    for value in values:
        (_require_ref if refs else _require_id)(value, label)


@dataclass(frozen=True, slots=True)
class RuntimeObligation:
    obligation_id: str
    kind: RuntimeBlockerKind
    description: str
    blocks_claims: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_id(self.obligation_id, "obligation_id")
        if not isinstance(self.kind, RuntimeBlockerKind):
            object.__setattr__(self, "kind", RuntimeBlockerKind(self.kind))
        if type(self.description) is not str or not self.description.strip():
            raise ValueError("obligation description is required")
        _unique(self.blocks_claims, "blocks_claims")
        if not self.blocks_claims:
            raise ValueError("obligation must identify blocked claims")


@dataclass(frozen=True, slots=True)
class StudioToolReceipt:
    """Host-observed static tool identity; never a runtime receipt."""

    receipt_ref: str
    executable_path: str
    binary_digest: str
    file_version: str
    product_version: str
    signature_status: str
    signer_subject: str
    signer_thumbprint: str
    verifier_id: str
    observed_at: int
    expires_at: int
    evidence_class: RuntimeEvidenceClass = RuntimeEvidenceClass.STATIC_DISCOVERY

    def __post_init__(self) -> None:
        _require_ref(self.receipt_ref, "receipt_ref")
        object.__setattr__(
            self,
            "executable_path",
            str(_absolute_path(self.executable_path, "executable_path")),
        )
        _require_digest(self.binary_digest, "binary_digest")
        for label in (
            "file_version",
            "product_version",
            "signature_status",
            "signer_subject",
        ):
            value = getattr(self, label)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{label} is required")
        if _THUMBPRINT.fullmatch(self.signer_thumbprint) is None:
            raise ValueError("signer_thumbprint must be a certificate fingerprint")
        _require_id(self.verifier_id, "verifier_id")
        if type(self.observed_at) is not int or self.observed_at < 0:
            raise ValueError("observed_at must be a nonnegative integer")
        if type(self.expires_at) is not int or self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")
        if self.evidence_class is not RuntimeEvidenceClass.STATIC_DISCOVERY:
            raise ValueError("Studio tool discovery cannot claim runtime evidence")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    """Opaque engine/device observation bound to one exact candidate."""

    receipt_ref: str
    evidence_class: RuntimeEvidenceClass
    qualification_id: str
    candidate_digest: str
    profile_digest: str
    project_manifest_digest: str
    scenario_manifest_digest: str
    studio_binary_digest: str
    studio_version: str
    studio_tool_receipt_ref: str
    environment_id: str
    broker_lease_ref: str
    environment_lease_ref: str
    verifier_id: str
    scenario_id: str
    device_id: str | None
    passed: bool
    observed_at: int
    expires_at: int

    def __post_init__(self) -> None:
        _require_ref(self.receipt_ref, "receipt_ref")
        if not isinstance(self.evidence_class, RuntimeEvidenceClass):
            object.__setattr__(
                self, "evidence_class", RuntimeEvidenceClass(self.evidence_class)
            )
        if self.evidence_class is RuntimeEvidenceClass.STATIC_DISCOVERY:
            raise ValueError("static discovery cannot be used as runtime evidence")
        _require_id(self.qualification_id, "qualification_id")
        for label in (
            "candidate_digest",
            "profile_digest",
            "project_manifest_digest",
            "scenario_manifest_digest",
            "studio_binary_digest",
        ):
            _require_digest(getattr(self, label), label)
        _require_ref(self.studio_tool_receipt_ref, "studio_tool_receipt_ref")
        _require_ref(self.broker_lease_ref, "broker_lease_ref")
        _require_ref(self.environment_lease_ref, "environment_lease_ref")
        for label in (
            "studio_version",
            "environment_id",
            "scenario_id",
            "verifier_id",
        ):
            _require_id(getattr(self, label), label)
        if self.evidence_class is RuntimeEvidenceClass.PHYSICAL_DEVICE:
            if self.device_id is None:
                raise ValueError("physical-device receipt requires device_id")
            _require_id(self.device_id, "device_id")
        elif self.device_id is not None:
            raise ValueError("Studio-engine receipt must not invent a device")
        if type(self.passed) is not bool:
            raise ValueError("passed must be boolean")
        if type(self.observed_at) is not int or self.observed_at < 0:
            raise ValueError("observed_at must be a nonnegative integer")
        if type(self.expires_at) is not int or self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")


@dataclass(frozen=True, slots=True)
class QualificationReceipt:
    """Independent attestation for one exact qualification result group."""

    receipt_ref: str
    evidence_kind: QualificationEvidenceKind
    qualification_id: str
    candidate_digest: str
    profile_digest: str
    project_manifest_digest: str
    scenario_manifest_digest: str
    studio_binary_digest: str
    studio_tool_receipt_ref: str
    environment_id: str
    broker_lease_ref: str
    environment_lease_ref: str
    payload_digest: str
    verifier_id: str
    observed_at: int
    expires_at: int

    def __post_init__(self) -> None:
        _require_ref(self.receipt_ref, "receipt_ref")
        if not isinstance(self.evidence_kind, QualificationEvidenceKind):
            object.__setattr__(
                self,
                "evidence_kind",
                QualificationEvidenceKind(self.evidence_kind),
            )
        _require_id(self.qualification_id, "qualification_id")
        for label in (
            "candidate_digest",
            "profile_digest",
            "project_manifest_digest",
            "scenario_manifest_digest",
            "studio_binary_digest",
            "payload_digest",
        ):
            _require_digest(getattr(self, label), label)
        _require_ref(self.studio_tool_receipt_ref, "studio_tool_receipt_ref")
        _require_ref(self.broker_lease_ref, "broker_lease_ref")
        _require_ref(self.environment_lease_ref, "environment_lease_ref")
        _require_id(self.environment_id, "environment_id")
        _require_id(self.verifier_id, "verifier_id")
        if type(self.observed_at) is not int or self.observed_at < 0:
            raise ValueError("observed_at must be a nonnegative integer")
        if type(self.expires_at) is not int or self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")


@dataclass(frozen=True, slots=True)
class RobloxRuntimeAdmission:
    """Owner/host-supplied inputs for one non-production runtime qualification."""

    candidate_digest: str
    profile_digest: str
    qualification_id: str
    verifier_manifest_ref: str
    verifier_manifest_digest: str
    studio_verifier_id: str
    runtime_verifier_id: str
    authority_verifier_id: str
    qualification_verifier_id: str
    verifier_evidence_scope: VerifierEvidenceScope
    project_root: str
    project_manifest_path: str
    project_manifest_digest: str
    studio_executable_path: str
    studio_binary_digest: str
    studio_version: str
    scenario_manifest_digest: str
    required_scenarios: tuple[str, ...]
    required_device_ids: tuple[str, ...]
    environment_id: str
    account_capability_refs: tuple[str, ...]
    authority_refs: tuple[str, ...]
    asset_rights_refs: tuple[str, ...]
    broker_lease_ref: str | None
    resource_lease_ref: str | None
    broker_lease_expires_at: int | None
    resource_lease_expires_at: int | None
    evidence_max_age_seconds: int

    def __post_init__(self) -> None:
        for label in (
            "candidate_digest",
            "profile_digest",
            "verifier_manifest_digest",
            "project_manifest_digest",
            "studio_binary_digest",
            "scenario_manifest_digest",
        ):
            _require_digest(getattr(self, label), label)
        root = _absolute_path(self.project_root, "project_root")
        manifest = _absolute_path(self.project_manifest_path, "project_manifest_path")
        studio = _absolute_path(self.studio_executable_path, "studio_executable_path")
        object.__setattr__(self, "project_root", str(root))
        object.__setattr__(self, "project_manifest_path", str(manifest))
        object.__setattr__(self, "studio_executable_path", str(studio))
        _require_id(self.qualification_id, "qualification_id")
        _require_ref(self.verifier_manifest_ref, "verifier_manifest_ref")
        verifier_ids = (
            self.studio_verifier_id,
            self.runtime_verifier_id,
            self.authority_verifier_id,
            self.qualification_verifier_id,
        )
        for verifier_id in verifier_ids:
            _require_id(verifier_id, "verifier_id")
        if len(set(verifier_ids)) != len(verifier_ids):
            raise ValueError("admitted verifier identities must be independent")
        if not isinstance(self.verifier_evidence_scope, VerifierEvidenceScope):
            object.__setattr__(
                self,
                "verifier_evidence_scope",
                VerifierEvidenceScope(self.verifier_evidence_scope),
            )
        _require_id(self.studio_version, "studio_version")
        _require_id(self.environment_id, "environment_id")
        _unique(self.required_scenarios, "required_scenarios")
        if not self.required_scenarios:
            raise ValueError("required_scenarios cannot be empty")
        _unique(self.required_device_ids, "required_device_ids")
        _unique(self.account_capability_refs, "account_capability_refs", refs=True)
        _unique(self.authority_refs, "authority_refs", refs=True)
        _unique(self.asset_rights_refs, "asset_rights_refs", refs=True)
        for label in ("broker_lease_ref", "resource_lease_ref"):
            value = getattr(self, label)
            if value is not None:
                _require_ref(value, label)
        for label in ("broker_lease_expires_at", "resource_lease_expires_at"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{label} must be a nonnegative integer")
        if (
            type(self.evidence_max_age_seconds) is not int
            or self.evidence_max_age_seconds <= 0
        ):
            raise ValueError("evidence_max_age_seconds must be a positive integer")


class StudioReceiptVerifier(Protocol):
    verifier_id: str
    evidence_scope: VerifierEvidenceScope

    def verify_tool_receipt(self, receipt: StudioToolReceipt) -> bool: ...


class RuntimeReceiptVerifier(Protocol):
    verifier_id: str
    evidence_scope: VerifierEvidenceScope

    def verify_runtime_receipt(self, receipt: RuntimeReceipt) -> bool: ...


class RuntimeAuthorityVerifier(Protocol):
    verifier_id: str
    evidence_scope: VerifierEvidenceScope

    def verify_runtime_authority(self, admission: RobloxRuntimeAdmission) -> bool: ...


class QualificationReceiptVerifier(Protocol):
    verifier_id: str
    evidence_scope: VerifierEvidenceScope

    def verify_qualification_receipt(self, receipt: QualificationReceipt) -> bool: ...


@dataclass(frozen=True, slots=True)
class RobloxRuntimeEvidence:
    candidate_digest: str
    profile_digest: str
    platform_tool_version: str
    environment_id: str
    scenario_manifest_digest: str
    account_capability_refs: tuple[str, ...]
    runtime_receipts: tuple[str, ...]
    performance_samples: tuple[float, ...]
    persistence_results: dict[str, str]
    security_results: dict[str, str]
    asset_results: dict[str, str]
    cleanup_receipt: str
    verdict: RuntimeVerdict
    missing_obligations: tuple[RuntimeObligation, ...] = ()
    project_manifest_digest: str = "unknown"
    studio_tool_receipt_ref: str = "none"
    qualification_id: str = "unknown"
    qualified_at: int = 0
    broker_lease_ref: str = "none"
    environment_lease_ref: str = "none"
    verifier_ids: tuple[str, ...] = ()
    qualification_receipts: tuple[str, ...] = ()
    verifier_manifest_ref: str = "none"
    verifier_manifest_digest: str = "unknown"
    verifier_evidence_scope: VerifierEvidenceScope = (
        VerifierEvidenceScope.CONTRACT_FIXTURE
    )

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, RuntimeVerdict):
            object.__setattr__(self, "verdict", RuntimeVerdict(self.verdict))
        if not isinstance(self.verifier_evidence_scope, VerifierEvidenceScope):
            object.__setattr__(
                self,
                "verifier_evidence_scope",
                VerifierEvidenceScope(self.verifier_evidence_scope),
            )
        raw_obligations = cast(
            tuple[RuntimeObligation | str, ...], self.missing_obligations
        )
        if any(type(item) is str for item in raw_obligations):
            object.__setattr__(
                self,
                "missing_obligations",
                tuple(
                    _obligation(
                        f"n27.legacy-obligation-{index}",
                        RuntimeBlockerKind.BLOCKED_CAPABILITY,
                        item,
                        "roblox-runtime",
                        "roblox-production-candidate",
                    )
                    if type(item) is str
                    else item
                    for index, item in enumerate(raw_obligations)
                ),
            )
        qualified = {
            RuntimeVerdict.RUNTIME_VALIDATED,
            RuntimeVerdict.PRODUCTION_CANDIDATE,
        }
        if self.verdict in qualified and self.missing_obligations:
            raise ValueError("qualified runtime evidence cannot have missing obligations")
        if (
            self.verdict is RuntimeVerdict.PRODUCTION_CANDIDATE
            and self.verifier_evidence_scope
            is not VerifierEvidenceScope.EXTERNAL_ATTESTATION
        ):
            raise ValueError("fixture evidence cannot form a production candidate")
        if self.verdict is RuntimeVerdict.DEPLOYED_OBSERVED:
            raise ValueError(
                "DEPLOYED_OBSERVED requires a separate authorized release receipt"
            )
        if self.verdict in qualified:
            for label in (
                "candidate_digest",
                "profile_digest",
                "project_manifest_digest",
                "scenario_manifest_digest",
            ):
                _require_digest(getattr(self, label), label)
            _require_id(self.qualification_id, "qualification_id")
            if type(self.qualified_at) is not int or self.qualified_at <= 0:
                raise ValueError("qualified_at must be a positive integer")
            if not self.runtime_receipts:
                raise ValueError("runtime verdict requires receipts")
            if len(self.qualification_receipts) != len(QualificationEvidenceKind):
                raise ValueError("runtime verdict requires all qualification receipts")
            if not self.performance_samples:
                raise ValueError("runtime verdict requires performance samples")
            if not self.account_capability_refs:
                raise ValueError("runtime verdict requires account capability references")
            if not all(
                (self.persistence_results, self.security_results, self.asset_results)
            ):
                raise ValueError("runtime verdict requires all acceptance result groups")
            for label, results in (
                ("persistence", self.persistence_results),
                ("security", self.security_results),
                ("asset", self.asset_results),
            ):
                if any(
                    value != "PASS"
                    and not (
                        type(value) is str
                        and value.startswith("NOT_APPLICABLE:")
                        and value.removeprefix("NOT_APPLICABLE:").strip()
                    )
                    for value in results.values()
                ):
                    raise ValueError(f"{label} acceptance contains a failing result")
            _require_ref(self.studio_tool_receipt_ref, "studio_tool_receipt_ref")
            _require_ref(self.cleanup_receipt, "cleanup_receipt")
            _require_ref(self.broker_lease_ref, "broker_lease_ref")
            _require_ref(self.environment_lease_ref, "environment_lease_ref")
            _require_ref(self.verifier_manifest_ref, "verifier_manifest_ref")
            _require_digest(self.verifier_manifest_digest, "verifier_manifest_digest")
            _unique(self.verifier_ids, "verifier_ids")
            if len(self.verifier_ids) != 4:
                raise ValueError("qualified evidence requires four independent verifiers")
            _unique(
                self.qualification_receipts,
                "qualification_receipts",
                refs=True,
            )
        for ref in (
            *self.account_capability_refs,
            *self.runtime_receipts,
            *self.qualification_receipts,
        ):
            _require_ref(ref, "evidence reference")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            for value in self.performance_samples
        ):
            raise ValueError("performance samples must be finite nonnegative numbers")
        if any(
            type(item) is not RuntimeObligation for item in self.missing_obligations
        ):
            raise ValueError("missing obligations must be typed")

    @property
    def digest(self) -> str:
        return canonical_digest(self)

    def to_dict(self) -> dict[str, object]:
        return canonical_document(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "RobloxRuntimeEvidence":
        required = set(cls.__dataclass_fields__)
        if set(value) != required:
            raise ValueError("closed runtime evidence schema")
        return cls(
            **{
                **value,
                "verdict": RuntimeVerdict(value["verdict"]),
                "verifier_evidence_scope": VerifierEvidenceScope(
                    value["verifier_evidence_scope"]
                ),
                "account_capability_refs": tuple(
                    cast(list[str], value["account_capability_refs"])
                ),
                "runtime_receipts": tuple(
                    cast(list[str], value["runtime_receipts"])
                ),
                "verifier_ids": tuple(cast(list[str], value["verifier_ids"])),
                "qualification_receipts": tuple(
                    cast(list[str], value["qualification_receipts"])
                ),
                "performance_samples": tuple(
                    cast(list[float], value["performance_samples"])
                ),
                "missing_obligations": tuple(
                    RuntimeObligation(
                        obligation_id=cast(str, item["obligation_id"]),
                        kind=RuntimeBlockerKind(cast(str, item["kind"])),
                        description=cast(str, item["description"]),
                        blocks_claims=tuple(
                            cast(list[str], item["blocks_claims"])
                        ),
                    )
                    for item in cast(
                        list[dict[str, object]], value["missing_obligations"]
                    )
                ),
            }
        )


def _obligation(
    obligation_id: str,
    kind: RuntimeBlockerKind,
    description: str,
    *blocks_claims: str,
) -> RuntimeObligation:
    return RuntimeObligation(
        obligation_id,
        kind,
        description,
        tuple(sorted(set(blocks_claims))),
    )


def _result_payload_digest(
    kind: QualificationEvidenceKind,
    *,
    performance_samples: tuple[float, ...] = (),
    results: Mapping[str, str] | None = None,
    cleanup_receipt: str | None = None,
) -> str:
    if kind is QualificationEvidenceKind.METRIC:
        payload: object = {
            "evidence_kind": kind.value,
            "performance_samples": list(performance_samples),
        }
    elif kind is QualificationEvidenceKind.CLEANUP:
        payload = {
            "cleanup_receipt": cleanup_receipt,
            "evidence_kind": kind.value,
        }
    else:
        payload = {
            "evidence_kind": kind.value,
            "results": dict(sorted((results or {}).items())),
        }
    return canonical_digest(payload)


def _timestamp_failure(
    label: str,
    *,
    observed_at: int,
    expires_at: int,
    qualified_at: int,
    max_age_seconds: int,
) -> str | None:
    if observed_at > qualified_at:
        return f"{label} has a future observation timestamp"
    if qualified_at - observed_at > max_age_seconds:
        return f"{label} is outside the evidence freshness window"
    if expires_at <= qualified_at:
        return f"{label} expired before qualification"
    return None


class RobloxRuntimeAdapter:
    """Validate exact host/runtime receipts without performing external effects."""

    def __init__(
        self,
        studio_verifier: StudioReceiptVerifier,
        runtime_verifier: RuntimeReceiptVerifier,
        authority_verifier: RuntimeAuthorityVerifier,
        qualification_verifier: QualificationReceiptVerifier,
    ) -> None:
        if not callable(getattr(studio_verifier, "verify_tool_receipt", None)):
            raise ValueError("Studio verifier is required")
        if not callable(getattr(runtime_verifier, "verify_runtime_receipt", None)):
            raise ValueError("runtime verifier is required")
        if not callable(
            getattr(authority_verifier, "verify_runtime_authority", None)
        ):
            raise ValueError("runtime authority verifier is required")
        if not callable(
            getattr(
                qualification_verifier,
                "verify_qualification_receipt",
                None,
            )
        ):
            raise ValueError("qualification receipt verifier is required")
        raw_verifier_ids = tuple(
            getattr(verifier, "verifier_id", None)
            for verifier in (
                studio_verifier,
                runtime_verifier,
                authority_verifier,
                qualification_verifier,
            )
        )
        if any(type(verifier_id) is not str for verifier_id in raw_verifier_ids):
            raise ValueError("verifier_id must be a canonical identifier")
        verifier_ids = cast(tuple[str, ...], raw_verifier_ids)
        for verifier_id in verifier_ids:
            _require_id(verifier_id, "verifier_id")
        if len(set(verifier_ids)) != len(verifier_ids):
            raise ValueError("receipt and authority verifiers must be independent")
        self.studio_verifier = studio_verifier
        self.runtime_verifier = runtime_verifier
        self.authority_verifier = authority_verifier
        self.qualification_verifier = qualification_verifier
        raw_scopes = tuple(
            getattr(verifier, "evidence_scope", None)
            for verifier in (
                studio_verifier,
                runtime_verifier,
                authority_verifier,
                qualification_verifier,
            )
        )
        try:
            scopes = tuple(VerifierEvidenceScope(scope) for scope in raw_scopes)
        except (TypeError, ValueError) as error:
            raise ValueError("verifier evidence scope is required") from error
        if len(set(scopes)) != 1:
            raise ValueError("verifiers must use one admitted evidence scope")
        self.verifier_ids = verifier_ids
        self.verifier_evidence_scope = scopes[0]

    def qualify(
        self,
        admission: RobloxRuntimeAdmission,
        *,
        studio_receipt: StudioToolReceipt | None,
        runtime_receipts: tuple[RuntimeReceipt, ...],
        performance_samples: tuple[float, ...],
        persistence_results: Mapping[str, str],
        security_results: Mapping[str, str],
        asset_results: Mapping[str, str],
        cleanup_receipt: str | None,
        qualification_receipts: tuple[QualificationReceipt, ...],
        qualified_at: int,
    ) -> RobloxRuntimeEvidence:
        if type(qualified_at) is not int or qualified_at <= 0:
            raise ValueError("qualified_at must be a positive integer")
        obligations: list[RuntimeObligation] = []
        failures: list[str] = []
        project_root = Path(admission.project_root)
        manifest = Path(admission.project_manifest_path)

        admitted_verifier_ids = (
            admission.studio_verifier_id,
            admission.runtime_verifier_id,
            admission.authority_verifier_id,
            admission.qualification_verifier_id,
        )
        if admitted_verifier_ids != self.verifier_ids:
            failures.append("injected verifier identities do not match admitted manifest")
        if admission.verifier_evidence_scope is not self.verifier_evidence_scope:
            failures.append("injected verifier scope does not match admitted manifest")

        try:
            if not project_root.is_dir() or not manifest.is_file():
                obligations.append(
                    _obligation(
                        "n27.project-source",
                        RuntimeBlockerKind.BLOCKED_SOURCE,
                        "admitted Roblox project and manifest are unavailable",
                        "roblox-runtime",
                        "roblox-production-candidate",
                    )
                )
            else:
                manifest.relative_to(project_root)
                if manifest.is_symlink() or project_root.is_symlink():
                    failures.append("project binding uses a symbolic link")
                else:
                    observed = "sha256:" + sha256(manifest.read_bytes()).hexdigest()
                    if observed != admission.project_manifest_digest:
                        failures.append("project manifest digest is stale or substituted")
        except ValueError:
            failures.append("project manifest is outside admitted project root")
        except OSError:
            obligations.append(
                _obligation(
                    "n27.project-file-observation",
                    RuntimeBlockerKind.BLOCKED_SOURCE,
                    "project source could not be independently read",
                    "roblox-runtime",
                    "roblox-production-candidate",
                )
            )

        if not admission.asset_rights_refs:
            obligations.append(
                _obligation(
                    "n27.asset-rights",
                    RuntimeBlockerKind.BLOCKED_SOURCE,
                    "asset and license rights references are absent",
                    "asset-provenance",
                    "roblox-production-candidate",
                )
            )

        if studio_receipt is None:
            obligations.append(
                _obligation(
                    "n27.studio-tool",
                    RuntimeBlockerKind.BLOCKED_CAPABILITY,
                    "host-issued Roblox Studio discovery receipt is absent",
                    "roblox-runtime",
                    "roblox-production-candidate",
                )
            )
        else:
            if (
                studio_receipt.executable_path != admission.studio_executable_path
                or studio_receipt.binary_digest != admission.studio_binary_digest
                or studio_receipt.file_version != admission.studio_version
                or studio_receipt.product_version != admission.studio_version
            ):
                failures.append("Studio path, binary, or version binding changed")
            if (
                studio_receipt.signature_status != "Valid"
                or "Roblox Corporation" not in studio_receipt.signer_subject
            ):
                failures.append("Studio Authenticode identity is invalid")
            if studio_receipt.verifier_id != self.studio_verifier.verifier_id:
                failures.append("Studio receipt verifier identity is substituted")
            timestamp_failure = _timestamp_failure(
                "Studio receipt",
                observed_at=studio_receipt.observed_at,
                expires_at=studio_receipt.expires_at,
                qualified_at=qualified_at,
                max_age_seconds=admission.evidence_max_age_seconds,
            )
            if timestamp_failure:
                failures.append(timestamp_failure)
            try:
                if self.studio_verifier.verify_tool_receipt(studio_receipt) is not True:
                    failures.append("host verifier rejected Studio discovery receipt")
            except Exception:  # verifier boundaries fail closed into typed evidence
                obligations.append(
                    _obligation(
                        "n27.studio-verifier-unavailable",
                        RuntimeBlockerKind.BLOCKED_CAPABILITY,
                        "Studio receipt verifier failed without a verdict",
                        "roblox-runtime",
                        "roblox-production-candidate",
                    )
                )
            studio_path = Path(admission.studio_executable_path)
            try:
                if not studio_path.is_file():
                    obligations.append(
                        _obligation(
                            "n27.studio-binary",
                            RuntimeBlockerKind.BLOCKED_CAPABILITY,
                            "profile-bound Roblox Studio executable is unavailable",
                            "roblox-runtime",
                            "roblox-production-candidate",
                        )
                    )
                elif studio_path.is_symlink():
                    failures.append("Studio executable binding uses a symbolic link")
                else:
                    observed_studio_digest = (
                        "sha256:" + sha256(studio_path.read_bytes()).hexdigest()
                    )
                    if observed_studio_digest != admission.studio_binary_digest:
                        failures.append("Studio executable digest is stale or substituted")
            except OSError:
                obligations.append(
                    _obligation(
                        "n27.studio-file-observation",
                        RuntimeBlockerKind.BLOCKED_CAPABILITY,
                        "Studio executable could not be independently read",
                        "roblox-runtime",
                        "roblox-production-candidate",
                    )
                )

        if not admission.account_capability_refs:
            obligations.append(
                _obligation(
                    "n27.account-capability",
                    RuntimeBlockerKind.BLOCKED_AUTHORITY,
                    "brokered test-account capability is absent",
                    "roblox-runtime",
                    "roblox-production-candidate",
                )
            )
        leases_missing = (
            not admission.authority_refs
            or admission.broker_lease_ref is None
            or admission.resource_lease_ref is None
            or admission.broker_lease_expires_at is None
            or admission.resource_lease_expires_at is None
        )
        if leases_missing:
            obligations.append(
                _obligation(
                    "n27.runtime-authority",
                    RuntimeBlockerKind.BLOCKED_AUTHORITY,
                    "runtime environment authority or resource lease is absent",
                    "roblox-runtime",
                    "runtime-cleanup",
                )
            )
        elif (
            cast(int, admission.broker_lease_expires_at) <= qualified_at
            or cast(int, admission.resource_lease_expires_at) <= qualified_at
        ):
            obligations.append(
                _obligation(
                    "n27.runtime-lease-expired",
                    RuntimeBlockerKind.BLOCKED_AUTHORITY,
                    "broker or environment lease expired before qualification",
                    "roblox-runtime",
                    "runtime-cleanup",
                )
            )
        else:
            try:
                authority_verified = self.authority_verifier.verify_runtime_authority(
                    admission
                )
            except Exception:  # verifier boundaries fail closed into typed evidence
                obligations.append(
                    _obligation(
                        "n27.runtime-authority-verifier-unavailable",
                        RuntimeBlockerKind.BLOCKED_AUTHORITY,
                        "runtime authority verifier failed without a verdict",
                        "roblox-runtime",
                        "runtime-cleanup",
                    )
                )
            else:
                if authority_verified is not True:
                    obligations.append(
                        _obligation(
                            "n27.runtime-authority-verification",
                            RuntimeBlockerKind.BLOCKED_AUTHORITY,
                            "host broker rejected runtime authority or lease binding",
                            "roblox-runtime",
                            "runtime-cleanup",
                        )
                    )
        if not admission.required_device_ids:
            obligations.append(
                _obligation(
                    "n27.target-devices",
                    RuntimeBlockerKind.BLOCKED_CAPABILITY,
                    "production profile declares no physical target device",
                    "device-performance",
                    "roblox-production-candidate",
                )
            )

        receipt_refs: list[str] = []
        engine_pairs: set[str] = set()
        device_pairs: set[tuple[str, str]] = set()
        seen_observations: set[tuple[RuntimeEvidenceClass, str, str | None]] = set()
        if len({receipt.receipt_ref for receipt in runtime_receipts}) != len(
            runtime_receipts
        ):
            failures.append("runtime receipt references are duplicated")
        expected_binding = (
            admission.qualification_id,
            admission.candidate_digest,
            admission.profile_digest,
            admission.project_manifest_digest,
            admission.scenario_manifest_digest,
            admission.studio_binary_digest,
            admission.studio_version,
            studio_receipt.receipt_ref if studio_receipt else None,
            admission.environment_id,
            admission.broker_lease_ref,
            admission.resource_lease_ref,
            self.runtime_verifier.verifier_id,
        )
        for receipt in runtime_receipts:
            actual_binding = (
                receipt.qualification_id,
                receipt.candidate_digest,
                receipt.profile_digest,
                receipt.project_manifest_digest,
                receipt.scenario_manifest_digest,
                receipt.studio_binary_digest,
                receipt.studio_version,
                receipt.studio_tool_receipt_ref,
                receipt.environment_id,
                receipt.broker_lease_ref,
                receipt.environment_lease_ref,
                receipt.verifier_id,
            )
            if actual_binding != expected_binding:
                failures.append(
                    f"runtime receipt {receipt.receipt_ref} has a stale binding"
                )
                continue
            timestamp_failure = _timestamp_failure(
                f"runtime receipt {receipt.receipt_ref}",
                observed_at=receipt.observed_at,
                expires_at=receipt.expires_at,
                qualified_at=qualified_at,
                max_age_seconds=admission.evidence_max_age_seconds,
            )
            if timestamp_failure:
                failures.append(timestamp_failure)
                continue
            if studio_receipt and receipt.observed_at < studio_receipt.observed_at:
                failures.append(
                    f"runtime receipt {receipt.receipt_ref} predates Studio discovery"
                )
                continue
            try:
                runtime_verified = self.runtime_verifier.verify_runtime_receipt(receipt)
            except Exception:  # verifier boundaries fail closed into typed evidence
                obligations.append(
                    _obligation(
                        "n27.runtime-verifier-unavailable",
                        RuntimeBlockerKind.BLOCKED_CAPABILITY,
                        "runtime receipt verifier failed without a verdict",
                        "roblox-runtime",
                        "device-performance",
                    )
                )
                continue
            if runtime_verified is not True:
                failures.append(
                    f"runtime receipt {receipt.receipt_ref} was not independently verified"
                )
                continue
            if receipt.scenario_id not in admission.required_scenarios:
                failures.append(
                    f"runtime receipt {receipt.receipt_ref} names an undeclared scenario"
                )
                continue
            if not receipt.passed:
                failures.append(f"runtime scenario {receipt.scenario_id} failed")
            observation = (
                receipt.evidence_class,
                receipt.scenario_id,
                receipt.device_id,
            )
            if observation in seen_observations:
                failures.append(
                    f"runtime observation {receipt.scenario_id} is duplicated"
                )
            seen_observations.add(observation)
            if receipt.evidence_class is RuntimeEvidenceClass.STUDIO_ENGINE:
                engine_pairs.add(receipt.scenario_id)
            else:
                assert receipt.device_id is not None
                if receipt.device_id not in admission.required_device_ids:
                    failures.append(
                        f"runtime receipt {receipt.receipt_ref} names an undeclared device"
                    )
                device_pairs.add((receipt.scenario_id, receipt.device_id))
            receipt_refs.append(receipt.receipt_ref)

        missing_engine = set(admission.required_scenarios) - engine_pairs
        missing_device = {
            (scenario, device)
            for scenario in admission.required_scenarios
            for device in admission.required_device_ids
        } - device_pairs
        if missing_engine or missing_device:
            detail = []
            if missing_engine:
                detail.append("engine=" + ",".join(sorted(missing_engine)))
            if missing_device:
                detail.append(
                    "device="
                    + ",".join(
                        f"{scenario}@{device}"
                        for scenario, device in sorted(missing_device)
                    )
                )
            obligations.append(
                _obligation(
                    "n27.runtime-matrix",
                    RuntimeBlockerKind.BLOCKED_CAPABILITY,
                    "actual Studio/device receipts are incomplete: "
                    + "; ".join(detail),
                    "roblox-runtime",
                    "device-performance",
                )
            )

        samples = tuple(performance_samples)
        if not samples:
            obligations.append(
                _obligation(
                    "n27.performance-samples",
                    RuntimeBlockerKind.BLOCKED_CAPABILITY,
                    "runtime performance samples are absent",
                    "device-performance",
                )
            )
        elif any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            for value in samples
        ):
            failures.append("runtime performance samples are invalid")

        result_groups = (
            (
                "persistence",
                QualificationEvidenceKind.PERSISTENCE,
                persistence_results,
            ),
            ("security", QualificationEvidenceKind.SECURITY, security_results),
            ("asset", QualificationEvidenceKind.ASSET, asset_results),
        )
        for label, _, results in result_groups:
            if not results:
                obligations.append(
                    _obligation(
                        f"n27.{label}-results",
                        RuntimeBlockerKind.BLOCKED_CAPABILITY,
                        f"actual {label} runtime results are absent",
                        f"{label}-runtime",
                        "roblox-production-candidate",
                    )
                )
            elif any(
                type(key) is not str
                or not key
                or (
                    value != "PASS"
                    and not (
                        type(value) is str
                        and value.startswith("NOT_APPLICABLE:")
                        and value.removeprefix("NOT_APPLICABLE:").strip()
                    )
                )
                for key, value in results.items()
            ):
                failures.append(f"{label} runtime acceptance failed")

        if cleanup_receipt is None:
            obligations.append(
                _obligation(
                    "n27.cleanup-receipt",
                    RuntimeBlockerKind.BLOCKED_AUTHORITY,
                    "leased test environment cleanup receipt is absent",
                    "runtime-cleanup",
                    "roblox-production-candidate",
                )
            )
            cleanup = "none"
        else:
            _require_ref(cleanup_receipt, "cleanup_receipt")
            cleanup = cleanup_receipt

        qualification_refs: list[str] = []
        expected_kinds = set(QualificationEvidenceKind)
        supplied_kinds = [receipt.evidence_kind for receipt in qualification_receipts]
        if len(set(supplied_kinds)) != len(supplied_kinds):
            failures.append("qualification receipt kinds are duplicated")
        all_refs = [receipt.receipt_ref for receipt in runtime_receipts]
        all_refs.extend(receipt.receipt_ref for receipt in qualification_receipts)
        if studio_receipt is not None:
            all_refs.append(studio_receipt.receipt_ref)
        if cleanup_receipt is not None:
            all_refs.append(cleanup_receipt)
        if len(set(all_refs)) != len(all_refs):
            failures.append("receipt reference replay was detected")

        result_by_kind = {
            kind: results for _, kind, results in result_groups
        }
        latest_runtime_observation = max(
            (receipt.observed_at for receipt in runtime_receipts),
            default=studio_receipt.observed_at if studio_receipt else 0,
        )
        verified_kinds: set[QualificationEvidenceKind] = set()
        qualification_binding = (
            admission.qualification_id,
            admission.candidate_digest,
            admission.profile_digest,
            admission.project_manifest_digest,
            admission.scenario_manifest_digest,
            admission.studio_binary_digest,
            studio_receipt.receipt_ref if studio_receipt else None,
            admission.environment_id,
            admission.broker_lease_ref,
            admission.resource_lease_ref,
            self.qualification_verifier.verifier_id,
        )
        for receipt in qualification_receipts:
            actual_binding = (
                receipt.qualification_id,
                receipt.candidate_digest,
                receipt.profile_digest,
                receipt.project_manifest_digest,
                receipt.scenario_manifest_digest,
                receipt.studio_binary_digest,
                receipt.studio_tool_receipt_ref,
                receipt.environment_id,
                receipt.broker_lease_ref,
                receipt.environment_lease_ref,
                receipt.verifier_id,
            )
            if actual_binding != qualification_binding:
                failures.append(
                    f"qualification receipt {receipt.receipt_ref} has a stale binding"
                )
                continue
            timestamp_failure = _timestamp_failure(
                f"qualification receipt {receipt.receipt_ref}",
                observed_at=receipt.observed_at,
                expires_at=receipt.expires_at,
                qualified_at=qualified_at,
                max_age_seconds=admission.evidence_max_age_seconds,
            )
            if timestamp_failure:
                failures.append(timestamp_failure)
                continue
            if receipt.observed_at < latest_runtime_observation:
                failures.append(
                    f"qualification receipt {receipt.receipt_ref} predates runtime evidence"
                )
                continue
            if receipt.evidence_kind is QualificationEvidenceKind.METRIC:
                expected_payload = _result_payload_digest(
                    receipt.evidence_kind,
                    performance_samples=samples,
                )
            elif receipt.evidence_kind is QualificationEvidenceKind.CLEANUP:
                expected_payload = _result_payload_digest(
                    receipt.evidence_kind,
                    cleanup_receipt=cleanup_receipt,
                )
            else:
                expected_payload = _result_payload_digest(
                    receipt.evidence_kind,
                    results=result_by_kind[receipt.evidence_kind],
                )
            if receipt.payload_digest != expected_payload:
                failures.append(
                    f"qualification receipt {receipt.receipt_ref} payload is substituted"
                )
                continue
            try:
                qualification_verified = (
                    self.qualification_verifier.verify_qualification_receipt(receipt)
                )
            except Exception:  # verifier boundaries fail closed into typed evidence
                obligations.append(
                    _obligation(
                        "n27.qualification-verifier-"
                        + receipt.evidence_kind.value.lower(),
                        RuntimeBlockerKind.BLOCKED_CAPABILITY,
                        "qualification receipt verifier failed without a verdict",
                        "roblox-runtime",
                        "roblox-production-candidate",
                    )
                )
                continue
            if qualification_verified is not True:
                failures.append(
                    f"qualification receipt {receipt.receipt_ref} was not independently verified"
                )
                continue
            verified_kinds.add(receipt.evidence_kind)
            qualification_refs.append(receipt.receipt_ref)

        for missing_kind in sorted(expected_kinds - verified_kinds):
            obligations.append(
                _obligation(
                    "n27.qualification-receipt-" + missing_kind.value.lower(),
                    RuntimeBlockerKind.BLOCKED_CAPABILITY,
                    f"verified {missing_kind.value.lower()} receipt is absent",
                    "roblox-runtime",
                    "roblox-production-candidate",
                )
            )

        verdict = (
            RuntimeVerdict.FAILED
            if failures
            else RuntimeVerdict.BLOCKED_RUNTIME
            if obligations
            else RuntimeVerdict.PRODUCTION_CANDIDATE
            if self.verifier_evidence_scope
            is VerifierEvidenceScope.EXTERNAL_ATTESTATION
            else RuntimeVerdict.RUNTIME_VALIDATED
        )
        return RobloxRuntimeEvidence(
            candidate_digest=admission.candidate_digest,
            profile_digest=admission.profile_digest,
            project_manifest_digest=admission.project_manifest_digest,
            platform_tool_version=admission.studio_version,
            studio_tool_receipt_ref=(
                studio_receipt.receipt_ref if studio_receipt else "none"
            ),
            qualification_id=admission.qualification_id,
            qualified_at=qualified_at,
            broker_lease_ref=admission.broker_lease_ref or "none",
            environment_lease_ref=admission.resource_lease_ref or "none",
            verifier_ids=tuple(sorted(self.verifier_ids)),
            qualification_receipts=tuple(sorted(set(qualification_refs))),
            verifier_manifest_ref=admission.verifier_manifest_ref,
            verifier_manifest_digest=admission.verifier_manifest_digest,
            verifier_evidence_scope=self.verifier_evidence_scope,
            environment_id=admission.environment_id,
            scenario_manifest_digest=admission.scenario_manifest_digest,
            account_capability_refs=admission.account_capability_refs,
            runtime_receipts=tuple(sorted(set(receipt_refs))),
            performance_samples=samples,
            persistence_results=dict(persistence_results),
            security_results=dict(security_results),
            asset_results=dict(asset_results),
            cleanup_receipt=cleanup,
            verdict=verdict,
            missing_obligations=tuple(
                sorted(
                    {item.obligation_id: item for item in obligations}.values(),
                    key=lambda item: item.obligation_id,
                )
            ),
        )


def blocked_runtime(
    reason: str,
    *,
    kind: RuntimeBlockerKind = RuntimeBlockerKind.BLOCKED_CAPABILITY,
    obligation_id: str = "n27.runtime-unavailable",
) -> RobloxRuntimeEvidence:
    """Create an explicit blocker without implying tool or runtime discovery."""

    return RobloxRuntimeEvidence(
        candidate_digest="unknown",
        profile_digest="unknown",
        project_manifest_digest="unknown",
        platform_tool_version="unknown",
        studio_tool_receipt_ref="none",
        environment_id="unavailable",
        scenario_manifest_digest="unknown",
        account_capability_refs=(),
        runtime_receipts=(),
        performance_samples=(),
        persistence_results={},
        security_results={},
        asset_results={},
        cleanup_receipt="none",
        verdict=RuntimeVerdict.BLOCKED_RUNTIME,
        missing_obligations=(
            _obligation(
                obligation_id,
                kind,
                reason,
                "roblox-runtime",
                "roblox-production-candidate",
            ),
        ),
    )


__all__ = [
    "RobloxRuntimeAdapter",
    "RobloxRuntimeAdmission",
    "RobloxRuntimeEvidence",
    "QualificationEvidenceKind",
    "QualificationReceipt",
    "QualificationReceiptVerifier",
    "RuntimeBlockerKind",
    "RuntimeAuthorityVerifier",
    "RuntimeEvidenceClass",
    "RuntimeObligation",
    "RuntimeReceipt",
    "RuntimeReceiptVerifier",
    "RuntimeVerdict",
    "StudioReceiptVerifier",
    "StudioToolReceipt",
    "VerifierEvidenceScope",
    "blocked_runtime",
]
