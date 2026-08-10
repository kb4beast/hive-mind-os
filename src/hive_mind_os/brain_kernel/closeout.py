"""Replayable local technical closeout; it grants no authority and mutates no legacy state."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, cast

from .canonical import canonical_digest
from .contracts import (
    EvaluationResult,
    EvaluationState,
    HistoricalEvidenceReference,
    RoleResult,
    TechnicalCloseoutReport,
    TechnicalCloseoutState,
    WorkState,
)
from .events import KernelEvent
from .roles import KERNEL_IMPLEMENTED_ROLES, result_digest
from .store import KernelStore
from .verification import ExactCandidateVerificationError, verify_bundle

_TIME = "1970-01-01T00:00:00Z"


class TechnicalCloseoutError(RuntimeError):
    """A local technical-closeout input is malformed or not durably bound."""


def technical_closeout_digest(report: TechnicalCloseoutReport) -> str:
    """Hash all semantic report fields except the self-referential digest."""

    values = asdict(report)
    values.pop("report_digest")
    return canonical_digest(values)


def declare_closeout_obligations(
    store: KernelStore,
    mission_id: str,
    *,
    required_roles: tuple[str, ...] = KERNEL_IMPLEMENTED_ROLES,
    historical_evidence: tuple[HistoricalEvidenceReference, ...] = (),
    actor_id: str = "orchestrator:local-closeout",
) -> int:
    """Append local-only obligations; referenced historical material stays opaque."""

    if not required_roles or len(set(required_roles)) != len(required_roles):
        raise TechnicalCloseoutError("closeout roles must be non-empty and unique")
    if any(role not in KERNEL_IMPLEMENTED_ROLES for role in required_roles):
        raise TechnicalCloseoutError("closeout role is not registered")
    if len({item.receipt_ref for item in historical_evidence}) != len(historical_evidence):
        raise TechnicalCloseoutError("historical evidence references must be unique")
    events = store.events()
    if not any(event["mission_id"] == mission_id and event["event_type"] == "mission.created" for event in events):
        raise TechnicalCloseoutError("closeout mission is unknown")
    payload = {
        "required_roles": list(required_roles),
        "historical_evidence": [item.to_document() for item in historical_evidence],
    }
    digest = canonical_digest(payload)
    return store.append(
        KernelEvent(
            f"closeout-obligations:{mission_id}:{digest}",
            mission_id,
            "closeout.obligations.declared",
            actor_id,
            _TIME,
            payload,
            actor_role="orchestrator",
            previous_digest=events[-1]["digest"] if events else None,
        ),
        idempotency_key=digest,
    )


def record_evaluation_bundle(
    store: KernelStore,
    work_id: str,
    result: EvaluationResult,
    bundle_directory: str | Path,
    *,
    bundle_ref: str,
    actor_id: str = "curator:local-closeout",
) -> int:
    """Bind a verified Phase 8 bundle digest to its already-recorded passed result."""

    if result.state is not EvaluationState.PASSED or not bundle_ref:
        raise TechnicalCloseoutError("only a named passed result may bind an evidence bundle")
    bundle_digest = _verified_bundle_digest(bundle_directory)
    events = store.events()
    matching = [
        event for event in events
        if event["event_type"] == "evaluation.result"
        and event["work_id"] == work_id
        and event["payload"].get("result", {}).get("result_digest") == result.result_digest
    ]
    if len(matching) != 1:
        raise TechnicalCloseoutError("evaluation result is not recorded for this work")
    payload = {
        "result_digest": result.result_digest,
        "bundle_digest": bundle_digest,
        "bundle_ref": bundle_ref,
    }
    return store.append(
        KernelEvent(
            f"evaluation-bundle:{result.result_digest}:{bundle_digest}",
            str(matching[0]["mission_id"]),
            "evaluation.bundle.recorded",
            actor_id,
            _TIME,
            payload,
            work_id=work_id,
            actor_role="curator",
            previous_digest=events[-1]["digest"],
        ),
        idempotency_key=canonical_digest(payload),
    )


def integrate_verified_work(
    store: KernelStore,
    work_id: str,
    result: EvaluationResult,
    *,
    actor_id: str = "integrator:local-closeout",
) -> int:
    """Move an accepted work item to integrated without performing any external effect."""

    events = store.events()
    mission_id = next((event["mission_id"] for event in events if event["work_id"] == work_id), None)
    if not isinstance(mission_id, str):
        raise TechnicalCloseoutError("work is not recorded in the kernel spine")
    return store.append(
        KernelEvent(
            f"work-integrated:{work_id}:{result.result_digest}",
            mission_id,
            "work.transition",
            actor_id,
            _TIME,
            {"status": WorkState.INTEGRATED.value, "evaluation_result_digest": result.result_digest},
            work_id=work_id,
            actor_role="integrator",
            previous_digest=events[-1]["digest"],
        ),
        idempotency_key=f"integrated:{result.result_digest}",
    )


def derive_technical_closeout(
    store: KernelStore,
    mission_id: str,
    *,
    bundle_directories: Mapping[str, str | Path] | None = None,
) -> TechnicalCloseoutReport:
    """Recompute one closeout finding from validated events and supplied read-only bundles."""

    directories = bundle_directories or {}
    events = store.events()
    if not any(event["mission_id"] == mission_id and event["event_type"] == "mission.created" for event in events):
        raise TechnicalCloseoutError("closeout mission is unknown")
    state = store.projection()
    head = events[-1]["digest"] if events else None
    if not isinstance(head, str):
        raise TechnicalCloseoutError("closeout requires a non-empty event spine")
    obligations = [
        event for event in events
        if event["mission_id"] == mission_id and event["event_type"] == "closeout.obligations.declared"
    ]
    missing: list[str] = []
    required_roles = KERNEL_IMPLEMENTED_ROLES
    blocked = False
    if len(obligations) != 1:
        missing.append("exactly one closeout obligation declaration")
        blocked = True
    else:
        payload = obligations[0]["payload"]
        try:
            required_roles = tuple(payload["required_roles"])
            references = tuple(
                cast(HistoricalEvidenceReference, HistoricalEvidenceReference.from_document(item))
                for item in payload["historical_evidence"]
            )
            if not required_roles or len(set(required_roles)) != len(required_roles):
                raise ValueError("invalid role declaration")
            if len({item.receipt_ref for item in references}) != len(references):
                raise ValueError("duplicate historical receipt reference")
        except (KeyError, TypeError, ValueError):
            missing.append("valid closeout obligation declaration")
            blocked = True

    role_results: dict[str, RoleResult] = {}
    for event in events:
        if event["mission_id"] != mission_id or event["event_type"] != "role.result":
            continue
        try:
            document = dict(event["payload"]["result"])
            for key in ("base_artifact_refs", "candidate_artifact_refs", "output_artifact_refs", "claims", "effect_receipt_refs", "unresolved_risks"):
                document[key] = tuple(document[key])
            role = RoleResult(**document)
            if role.result_digest != result_digest(role):
                raise ValueError("role result digest mismatch")
            if role.role in role_results:
                raise ValueError("duplicate role result")
            role_results[role.role] = role
        except (KeyError, TypeError, ValueError):
            missing.append("valid role result")
            blocked = True
    fulfilled = tuple(role for role in required_roles if role in role_results)
    missing.extend(f"role:{role}" for role in required_roles if role not in role_results)
    executor_ids = [role_results[role].executor_id for role in fulfilled]
    if len(executor_ids) != len(set(executor_ids)):
        missing.append("distinct required role identities")
        blocked = True

    mission_work = {
        work_id: data for work_id, data in state["work"].items() if data["mission_id"] == mission_id
    }
    integrated = tuple(sorted(work_id for work_id, data in mission_work.items() if data["status"] == WorkState.INTEGRATED.value))
    if not mission_work:
        missing.append("integrated local work")
    else:
        missing.extend(f"integrated:{work_id}" for work_id, data in mission_work.items() if data["status"] != WorkState.INTEGRATED.value)

    passed_results: dict[str, set[str]] = {}
    bundle_records: dict[str, tuple[str, str]] = {}
    for event in events:
        if event["mission_id"] != mission_id:
            continue
        if event["event_type"] == "evaluation.result":
            document = event["payload"].get("result", {})
            if document.get("state") == EvaluationState.PASSED.value and isinstance(event["work_id"], str):
                digest = document.get("result_digest")
                if isinstance(digest, str):
                    passed_results.setdefault(event["work_id"], set()).add(digest)
        elif event["event_type"] == "evaluation.bundle.recorded":
            payload = event["payload"]
            try:
                bundle_records[str(payload["result_digest"])] = (str(payload["bundle_digest"]), str(payload["bundle_ref"]))
            except (KeyError, TypeError):
                missing.append("valid evaluation bundle record")
                blocked = True

    result_digests: list[str] = []
    bundle_digests: list[str] = []
    for work_id in integrated:
        result_digest_values = passed_results.get(work_id, set())
        if len(result_digest_values) != 1:
            missing.append(f"passed-evaluation:{work_id}")
            blocked = True
            continue
        result_digest_value = next(iter(result_digest_values))
        result_digests.append(result_digest_value)
        bundle = bundle_records.get(result_digest_value)
        if bundle is None:
            missing.append(f"bundle-record:{work_id}")
            blocked = True
            continue
        expected_digest, bundle_ref = bundle
        bundle_digests.append(expected_digest)
        directory = directories.get(bundle_ref)
        if directory is None:
            missing.append(f"bundle-available:{bundle_ref}")
            blocked = True
            continue
        try:
            if _verified_bundle_digest(directory) != expected_digest:
                raise TechnicalCloseoutError("bundle digest does not match its event")
        except (OSError, TechnicalCloseoutError):
            missing.append(f"bundle-valid:{bundle_ref}")
            blocked = True

    if blocked:
        disposition = TechnicalCloseoutState.BLOCKED
    elif missing:
        disposition = TechnicalCloseoutState.PARTIAL
    else:
        disposition = TechnicalCloseoutState.TECHNICALLY_VERIFIED
    provisional = TechnicalCloseoutReport(
        mission_id,
        head,
        canonical_digest(state),
        required_roles,
        fulfilled,
        tuple(sorted(set(missing))),
        integrated,
        tuple(sorted(result_digests)),
        tuple(sorted(bundle_digests)),
        disposition,
        "sha256:" + "0" * 64,
    )
    return TechnicalCloseoutReport(**{**asdict(provisional), "report_digest": technical_closeout_digest(provisional)})


def _verified_bundle_digest(bundle_directory: str | Path) -> str:
    try:
        verify_bundle(bundle_directory)
    except ExactCandidateVerificationError as error:
        raise TechnicalCloseoutError("verification bundle is corrupt") from error
    try:
        document = json.loads((Path(bundle_directory) / "verification.json").read_text(encoding="utf-8"))
        digest = document["bundle_digest"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise TechnicalCloseoutError("verification bundle is corrupt") from error
    if not isinstance(digest, str):
        raise TechnicalCloseoutError("verification bundle digest is invalid")
    return digest
