from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence

from .canonical import canonical_bytes, digest
from .opportunities import OpportunityLedger

POLICY_VERSION = "explorer-context-selection-v1"
ACTOR_ID = "explorer-shadow-v1"
CRITICAL_CLASSES = (
    "blocker",
    "dissent",
    "authority",
    "provenance",
    "rollback",
    "acceptance",
    "decision",
    "contradiction",
    "court",
)
SKILLS: tuple[Mapping[str, Any], ...] = (
    {
        "skill_id": "explorer:evidence-capture:v1",
        "purpose": "Capture source-bound evidence while treating repository text as untrusted data.",
        "inputs": ["context-records", "purpose", "cutoff"],
        "outputs": ["evidence-bound-finding"],
        "steps": ["verify-scope", "preserve-provenance", "separate-claims"],
        "requested_capabilities": ["read_repository"],
        "side_effects": [],
        "activation": "inert",
        "authority": "none",
    },
    {
        "skill_id": "explorer:counterargument-bridge:v1",
        "purpose": "Require a counterargument and falsifiable bridge for surprising proposals.",
        "inputs": ["evidence-bound-finding"],
        "outputs": ["cross-examined-finding"],
        "steps": ["state-mechanism", "state-break-point", "state-counterexample"],
        "requested_capabilities": [],
        "side_effects": [],
        "activation": "inert",
        "authority": "none",
    },
    {
        "skill_id": "explorer:honest-stopping:v1",
        "purpose": "Stop on declared bounds while preserving omitted context and unknowns.",
        "inputs": ["budget", "coverage", "unknowns"],
        "outputs": ["stop-reason", "remaining-frontier"],
        "steps": ["check-critical-coverage", "check-budget", "receipt-omissions"],
        "requested_capabilities": [],
        "side_effects": [],
        "activation": "inert",
        "authority": "none",
    },
)


class ExplorerShadowError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ContextRecord:
    memory_id: str
    tenant_id: str
    repository_id: str
    observed_at: str
    context_class: str
    priority: int
    sensitivity: str
    quarantine_state: str
    origin_run_id: str | None
    content: str


@dataclass(frozen=True, slots=True)
class ContextRequest:
    tenant_id: str
    repository_id: str
    run_id: str
    purpose: str
    cutoff: str
    max_records: int
    max_bytes: int
    max_findings: int


@dataclass(frozen=True, slots=True)
class ContextSelection:
    policy_version: str
    inventory_digest: str
    selected_ids: tuple[str, ...]
    omitted: tuple[tuple[str, str], ...]
    ordering: tuple[str, ...]
    selected_bytes: int
    purpose: str
    cutoff: str
    critical_context_coverage: str
    selection_digest: str


@dataclass(frozen=True, slots=True)
class ShadowResult:
    selection: ContextSelection
    outcomes: tuple[Mapping[str, Any], ...]
    skill_bundle_digest: str
    activation: str = "inert"


class DiscoveryEngine(Protocol):
    def discover(
        self,
        request: ContextRequest,
        context: tuple[ContextRecord, ...],
        skill_bundle: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]: ...


def compile_shadow_skills() -> dict[str, Any]:
    records = [dict(skill) for skill in SKILLS]
    outputs = [
        {"skill_id": record["skill_id"], "digest": digest(record)}
        for record in records
    ]
    body = {
        "record_type": "explorer-shadow-skill-bundle",
        "schema_version": 1,
        "skills": records,
        "outputs": outputs,
        "activation": "inert",
        "authority": "none",
    }
    return {**body, "bundle_digest": digest(body)}


def select_context(
    request: ContextRequest, records: Sequence[ContextRecord]
) -> tuple[ContextSelection, tuple[ContextRecord, ...]]:
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            request.tenant_id,
            request.repository_id,
            request.run_id,
            request.purpose,
            request.cutoff,
        )
    ):
        raise ExplorerShadowError("context request identity and purpose are required")
    if (
        request.max_records < len(CRITICAL_CLASSES)
        or request.max_records > 256
        or request.max_bytes < 1
        or request.max_bytes > 1_000_000
        or request.max_findings < 0
        or request.max_findings > 64
    ):
        raise ExplorerShadowError("budget cannot cover mandatory critical context")
    identifiers = [record.memory_id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ExplorerShadowError("context record IDs must be unique")
    eligible: list[ContextRecord] = []
    omitted: list[tuple[str, str]] = []
    for record in records:
        if (
            not record.memory_id.strip()
            or not record.observed_at.strip()
            or not record.context_class.strip()
            or record.sensitivity not in {"private", "internal", "safe-public"}
            or record.quarantine_state not in {"clear", "quarantined"}
            or type(record.priority) is not int
            or not 0 <= record.priority <= 1_000_000
        ):
            raise ExplorerShadowError("context record metadata is invalid")
        if (
            record.tenant_id != request.tenant_id
            or record.repository_id != request.repository_id
        ):
            raise ExplorerShadowError("context scope mismatch")
        if record.observed_at > request.cutoff:
            raise ExplorerShadowError("context exceeds sealed cutoff")
        reason = None
        if record.quarantine_state != "clear":
            reason = "quarantined"
        elif record.origin_run_id == request.run_id:
            reason = "same-run-recursion"
        if reason is not None:
            if record.context_class in CRITICAL_CLASSES:
                raise ExplorerShadowError(f"critical context is {reason}")
            omitted.append((record.memory_id, reason))
        else:
            eligible.append(record)
    by_class = {name: [] for name in CRITICAL_CLASSES}
    for record in eligible:
        if record.context_class in by_class:
            by_class[record.context_class].append(record)
    missing = [name for name, values in by_class.items() if not values]
    if missing:
        raise ExplorerShadowError("missing critical context: " + ", ".join(missing))
    order = {name: index for index, name in enumerate(CRITICAL_CLASSES)}
    ordered = sorted(
        eligible,
        key=lambda item: (
            0 if item.context_class in order else 1,
            order.get(item.context_class, 0),
            -item.priority,
            item.observed_at,
            item.memory_id,
        ),
    )
    selected: list[ContextRecord] = []
    used = 0
    for record in ordered:
        size = len(record.content.encode("utf-8"))
        if len(selected) >= request.max_records or used + size > request.max_bytes:
            if record.context_class in CRITICAL_CLASSES:
                raise ExplorerShadowError("critical context exceeds whole-record budget")
            omitted.append((record.memory_id, "budget"))
            continue
        selected.append(record)
        used += size
    inventory = digest([asdict(record) for record in sorted(records, key=lambda x: x.memory_id)])
    receipt_body = {
        "policy_version": POLICY_VERSION,
        "inventory_digest": inventory,
        "selected_ids": [record.memory_id for record in selected],
        "omitted": sorted(omitted),
        "ordering": [record.memory_id for record in ordered],
        "selected_bytes": used,
        "purpose": request.purpose,
        "cutoff": request.cutoff,
        "critical_context_coverage": "complete",
    }
    receipt = ContextSelection(
        POLICY_VERSION,
        inventory,
        tuple(receipt_body["selected_ids"]),
        tuple(tuple(item) for item in receipt_body["omitted"]),
        tuple(receipt_body["ordering"]),
        used,
        request.purpose,
        request.cutoff,
        "complete",
        digest(receipt_body),
    )
    return receipt, tuple(selected)


class ExplorerShadowRunner:
    _FINDING_FIELDS = {
        "finding_id",
        "category",
        "problem",
        "affected_user",
        "scope",
        "proposal",
        "expected_outcome",
        "evidence_memory_ids",
        "counterargument",
        "acceptance_criteria",
        "metrics",
        "stop_reason",
        "disposition",
    }

    def __init__(self, engine: DiscoveryEngine, ledger: OpportunityLedger) -> None:
        self.engine = engine
        self.ledger = ledger

    def run(
        self, request: ContextRequest, records: Sequence[ContextRecord]
    ) -> ShadowResult:
        selection, selected = select_context(request, records)
        bundle = compile_shadow_skills()
        raw_findings = tuple(self.engine.discover(request, selected, bundle))
        if len(raw_findings) > request.max_findings:
            raise ExplorerShadowError("engine exceeded finding bound")
        selected_by_id = {record.memory_id: record for record in selected}
        outcomes: list[Mapping[str, Any]] = []
        for finding in raw_findings:
            if set(finding) != self._FINDING_FIELDS:
                raise ExplorerShadowError("finding shape is not exact")
            evidence_ids = finding["evidence_memory_ids"]
            if (
                not isinstance(evidence_ids, list)
                or not evidence_ids
                or len(evidence_ids) != len(set(evidence_ids))
                or any(item not in selected_by_id for item in evidence_ids)
            ):
                raise ExplorerShadowError("finding cites unavailable evidence")
            text_fields = self._FINDING_FIELDS - {
                "evidence_memory_ids",
                "acceptance_criteria",
                "metrics",
                "disposition",
            }
            if any(
                not isinstance(finding[field], str) or not finding[field].strip()
                for field in text_fields
            ):
                raise ExplorerShadowError("finding text fields are required")
            for field in ("acceptance_criteria", "metrics"):
                if (
                    not isinstance(finding[field], list)
                    or not finding[field]
                    or not all(isinstance(item, str) and item.strip() for item in finding[field])
                    or len(finding[field]) != len(set(finding[field]))
                ):
                    raise ExplorerShadowError(f"{field} must be a nonempty string list")
            result = self.ledger.register(
                tenant_id=request.tenant_id,
                repository_id=request.repository_id,
                encounter_id=f"{request.run_id}:{finding['finding_id']}",
                problem=finding["problem"],
                proposal=finding["proposal"],
                structured_key={
                    "affected_user": finding["affected_user"],
                    "scope": finding["scope"],
                    "problem": finding["problem"],
                    "proposal": finding["proposal"],
                    "expected_outcome": finding["expected_outcome"],
                },
                actor_id=ACTOR_ID,
                evidence_digests=[
                    digest(asdict(selected_by_id[item])) for item in evidence_ids
                ],
                disposition=finding["disposition"],
            )
            outcomes.append(
                {
                    "finding_id": finding["finding_id"],
                    "encounter_record_id": result.encounter_record_id,
                    "opportunity_record_id": result.opportunity_record_id,
                    "classification": result.classification,
                }
            )
        return ShadowResult(selection, tuple(outcomes), bundle["bundle_digest"])


def shadow_result_bytes(result: ShadowResult) -> bytes:
    return canonical_bytes(asdict(result))
