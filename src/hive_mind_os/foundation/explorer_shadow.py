from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .canonical import canonical_bytes, digest
from .contracts import validate_foundation
from .explorer_contracts import validate_explorer
from .explorer_skill_resources import EXPLORER_SKILL_DOCUMENTS
from .opportunities import OpportunityLedger

POLICY_VERSION = "explorer-context-selection-v2"
ACTOR_ID = "explorer-shadow-v1"
MAX_CONTEXT_RECORDS = 256
MAX_CONTEXT_BYTES = 1_000_000
MAX_FINDINGS = 64
MAX_TEXT = 10_000
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
CONTEXT_CLASSES = frozenset(
    (*CRITICAL_CLASSES, "evidence", "history", "telemetry", "user-signal")
)
GENERATED_ORIGINS = frozenset({"explorer-shadow", "generated", "projection"})
DISPOSITIONS = frozenset(
    {None, "abandoned", "filtered", "invalid", "non-material", "policy-blocked"}
)
CATEGORIES = frozenset(
    {"bug", "cross-domain", "improvement", "risk", "serendipity", "user-need"}
)


class ExplorerShadowError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ContextRecord:
    memory_id: str
    tenant_id: str
    repository_id: str
    sequence: int
    context_class: str
    priority: int
    sensitivity: str
    quarantine_state: str
    origin_kind: str
    origin_run_id: str | None
    self_host_depth: int
    content: str


@dataclass(frozen=True, slots=True)
class ContextRequest:
    tenant_id: str
    repository_id: str
    run_id: str
    purpose: str
    cutoff_sequence: int
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
    cutoff_sequence: int
    critical_context_coverage: str
    selection_digest: str


@dataclass(frozen=True, slots=True)
class ShadowResult:
    selection: ContextSelection
    selection_record_id: str
    outcomes: tuple[Mapping[str, Any], ...]
    skill_bundle_digest: str
    activation: str = "inert"


class DiscoveryEngine(Protocol):
    engine_id: str

    def discover(
        self,
        request: ContextRequest,
        context: tuple[ContextRecord, ...],
        skill_bundle: Mapping[str, Any],
    ) -> Iterable[Mapping[str, Any]]: ...


def compile_shadow_skills() -> dict[str, Any]:
    skills: list[dict[str, Any]] = []
    for resource in EXPLORER_SKILL_DOCUMENTS:
        document = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in resource.items()
        }
        validation = validate_foundation("skill-definition-v2", document)
        if not validation.valid:
            raise ValueError(
                "invalid packaged Explorer skill: " + "; ".join(validation.issues)
            )
        skills.append(document)
    if len(skills) != 3 or len({item["skill_id"] for item in skills}) != 3:
        raise ValueError("Explorer shadow requires exactly three unique packaged skills")
    outputs = [
        {"skill_id": item["skill_id"], "digest": digest(item)} for item in skills
    ]
    body = {
        "record_type": "explorer-shadow-skill-bundle",
        "schema_version": 1,
        "skills": skills,
        "outputs": outputs,
        "activation": "inert",
        "authority": "none",
    }
    return {**body, "bundle_digest": digest(body)}


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _bounded_text(value: Any, name: str, *, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ExplorerShadowError(f"{name} must be a bounded nonempty string")
    return value


def _bounded_list(value: Any, name: str, *, maximum: int) -> list[Any]:
    if not isinstance(value, list):
        raise ExplorerShadowError(f"{name} must be a bounded list")
    items: list[Any] = []
    iterator = iter(value)
    for _ in range(maximum + 1):
        try:
            items.append(next(iterator))
        except StopIteration:
            return items
        except Exception as error:
            raise ExplorerShadowError(
                f"{name} iteration failed: {type(error).__name__}"
            ) from error
    raise ExplorerShadowError(f"{name} exceeds item bound")


def _validate_request(request: ContextRequest) -> None:
    for field in ("tenant_id", "repository_id", "run_id"):
        _bounded_text(getattr(request, field), field, maximum=200)
    _bounded_text(request.purpose, "purpose", maximum=500)
    if type(request.cutoff_sequence) is not int or request.cutoff_sequence < 0:
        raise ExplorerShadowError("cutoff_sequence must be a nonnegative integer")
    if (
        type(request.max_records) is not int
        or not len(CRITICAL_CLASSES) <= request.max_records <= MAX_CONTEXT_RECORDS
        or type(request.max_bytes) is not int
        or not 1 <= request.max_bytes <= MAX_CONTEXT_BYTES
        or type(request.max_findings) is not int
        or not 0 <= request.max_findings <= MAX_FINDINGS
    ):
        raise ExplorerShadowError("request bounds are invalid")


def _validate_record(record: Any) -> ContextRecord:
    if not isinstance(record, ContextRecord):
        raise ExplorerShadowError("context entries must be ContextRecord values")
    for field in ("memory_id", "tenant_id", "repository_id"):
        _bounded_text(getattr(record, field), field, maximum=200)
    _bounded_text(record.content, "content", maximum=100_000)
    if (
        type(record.sequence) is not int
        or record.sequence < 0
        or not isinstance(record.context_class, str)
        or record.context_class not in CONTEXT_CLASSES
        or type(record.priority) is not int
        or not 0 <= record.priority <= 1_000_000
        or not isinstance(record.sensitivity, str)
        or record.sensitivity not in {"private", "internal", "safe-public"}
        or not isinstance(record.quarantine_state, str)
        or record.quarantine_state not in {"clear", "quarantined"}
        or not isinstance(record.origin_kind, str)
        or record.origin_kind
        not in {"external", "generated", "human", "explorer-shadow", "projection", "source"}
        or (
            record.origin_run_id is not None
            and (
                not isinstance(record.origin_run_id, str)
                or not record.origin_run_id.strip()
                or len(record.origin_run_id) > 200
            )
        )
        or type(record.self_host_depth) is not int
        or not 0 <= record.self_host_depth <= 64
    ):
        raise ExplorerShadowError("context record metadata is invalid")
    return record


def select_context(
    request: ContextRequest, records: Sequence[ContextRecord]
) -> tuple[ContextSelection, tuple[ContextRecord, ...]]:
    _validate_request(request)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ExplorerShadowError("context inventory must be a bounded sequence")
    checked_items: list[ContextRecord] = []
    iterator = iter(records)
    for _ in range(MAX_CONTEXT_RECORDS + 1):
        try:
            checked_items.append(_validate_record(next(iterator)))
        except StopIteration:
            break
        except ExplorerShadowError:
            raise
        except Exception as error:
            raise ExplorerShadowError(
                f"context inventory iteration failed: {type(error).__name__}"
            ) from error
    else:
        raise ExplorerShadowError("context inventory exceeds record bound")
    if len(checked_items) < len(CRITICAL_CLASSES):
        raise ExplorerShadowError("context inventory size is invalid")
    checked = tuple(checked_items)
    identifiers = [record.memory_id for record in checked]
    if len(identifiers) != len(set(identifiers)):
        raise ExplorerShadowError("context record IDs must be unique")
    eligible: list[ContextRecord] = []
    omitted: list[tuple[str, str]] = []
    for record in checked:
        if (
            record.tenant_id != request.tenant_id
            or record.repository_id != request.repository_id
        ):
            raise ExplorerShadowError("context scope mismatch")
        if record.sequence > request.cutoff_sequence:
            raise ExplorerShadowError("context exceeds sealed sequence cutoff")
        reason = None
        if record.quarantine_state != "clear":
            reason = "quarantined"
        elif record.origin_run_id == request.run_id:
            reason = "same-run-recursion"
        elif record.origin_kind in GENERATED_ORIGINS or record.self_host_depth > 0:
            reason = "generated-recursion"
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
            item.sequence,
            item.memory_id,
        ),
    )
    selected: list[ContextRecord] = []
    used = 0
    for record in ordered:
        size = len(canonical_bytes(asdict(record)))
        if len(selected) >= request.max_records or used + size > request.max_bytes:
            if record.context_class in CRITICAL_CLASSES:
                raise ExplorerShadowError("critical context exceeds whole-record budget")
            omitted.append((record.memory_id, "budget"))
            continue
        selected.append(record)
        used += size
    inventory_document = [asdict(record) for record in sorted(checked, key=lambda x: x.memory_id)]
    inventory_bytes = canonical_bytes(inventory_document)
    if len(inventory_bytes) > MAX_CONTEXT_BYTES:
        raise ExplorerShadowError("canonical context inventory exceeds size bound")
    receipt_body = {
        "policy_version": POLICY_VERSION,
        "inventory_digest": digest(inventory_document),
        "selected_ids": [record.memory_id for record in selected],
        "omitted": sorted(omitted),
        "ordering": [record.memory_id for record in ordered],
        "selected_bytes": used,
        "purpose": request.purpose,
        "cutoff_sequence": request.cutoff_sequence,
        "critical_context_coverage": "complete",
    }
    receipt = ContextSelection(
        POLICY_VERSION,
        receipt_body["inventory_digest"],
        tuple(receipt_body["selected_ids"]),
        tuple(tuple(item) for item in receipt_body["omitted"]),
        tuple(receipt_body["ordering"]),
        used,
        request.purpose,
        request.cutoff_sequence,
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

    def _run_receipt_exists(self, request: ContextRequest) -> bool:
        store = self.ledger.store
        return any(
            store.record_by_idempotency_key(
                tenant_id=request.tenant_id,
                repository_id=request.repository_id,
                idempotency_key=f"{prefix}:{request.run_id}",
            )
            is not None
            for prefix in ("explorer-run", "explorer-selection")
        )

    def _existing(
        self,
        request: ContextRequest,
        selection: ContextSelection,
        bundle_digest: str,
        engine_id: str,
    ) -> ShadowResult | None:
        store = self.ledger.store
        request_digest = digest(asdict(request))
        terminal = store.record_by_idempotency_key(
            tenant_id=request.tenant_id,
            repository_id=request.repository_id,
            idempotency_key=f"explorer-run:{request.run_id}",
        )
        if terminal is not None:
            if (
                terminal["record_type"] != "explorer-shadow-run"
                or terminal["payload"]["request_digest"] != request_digest
            ):
                raise ExplorerShadowError("run identity conflicts with prior receipt")
            payload = terminal["payload"]
            if payload["status"] != "succeeded":
                raise ExplorerShadowError(
                    f"prior shadow run failed: {payload['error_code']}"
                )
            selection_record = store.record_by_idempotency_key(
                tenant_id=request.tenant_id,
                repository_id=request.repository_id,
                idempotency_key=f"explorer-selection:{request.run_id}",
            )
            if (
                selection_record is None
                or selection_record["record_type"] != "explorer-context-selection"
                or selection_record["record_id"] != payload["selection_record_id"]
            ):
                raise ExplorerShadowError("terminal receipt lost its selection")
            stored_selection = _selection_from_payload(selection_record["payload"])
            if (
                payload["skill_bundle_digest"] != bundle_digest
                or payload["engine_id"] != engine_id
                or stored_selection.inventory_digest != selection.inventory_digest
                or stored_selection.selection_digest != selection.selection_digest
            ):
                raise ExplorerShadowError(
                    "run identity conflicts with current engine, skills, or context"
                )
            return ShadowResult(
                stored_selection,
                selection_record["record_id"],
                tuple(payload["outcomes"]),
                payload["skill_bundle_digest"],
            )
        pending = store.record_by_idempotency_key(
            tenant_id=request.tenant_id,
            repository_id=request.repository_id,
            idempotency_key=f"explorer-selection:{request.run_id}",
        )
        if pending is not None:
            if pending["record_type"] != "explorer-context-selection":
                raise ExplorerShadowError("run identity conflicts with prior receipt")
            raise ExplorerShadowError("shadow run has a sealed pending selection")
        return None

    def run(
        self, request: ContextRequest, records: Sequence[ContextRecord]
    ) -> ShadowResult:
        _validate_request(request)
        store = self.ledger.store
        store._require_authority(
            self.ledger.authority,
            "foundation.opportunity.write",
            tenant_id=request.tenant_id,
            repository_id=request.repository_id,
            actor_id=ACTOR_ID,
        )
        # A FoundationStore owns one SQLite connection. Serializing the complete
        # shadow call on that connection makes a concurrent identical invocation
        # wait for and replay the first terminal result instead of calling two
        # engines. A durable selection claim below closes the same race across
        # separate store connections.
        with store._lock:
            return self._run_locked(request, records)

    def _run_locked(
        self, request: ContextRequest, records: Sequence[ContextRecord]
    ) -> ShadowResult:
        store = self.ledger.store
        prior_exists = self._run_receipt_exists(request)
        unavailable_bundle = digest({"status": "skill-bundle-unavailable"})
        try:
            bundle = compile_shadow_skills()
            bundle_digest = str(bundle["bundle_digest"])
        except Exception as error:
            if prior_exists:
                raise ExplorerShadowError(
                    "run identity conflicts with unavailable current skills"
                ) from error
            self._append_terminal(
                request,
                None,
                None,
                unavailable_bundle,
                "unavailable:preselection",
                (),
                "failed",
                type(error).__name__[:200],
            )
            raise ExplorerShadowError(
                f"shadow skill compilation failed: {type(error).__name__}"
            ) from error
        try:
            engine_id = _bounded_text(
                getattr(self.engine, "engine_id", None), "engine_id", maximum=200
            )
        except ExplorerShadowError as error:
            if prior_exists:
                raise ExplorerShadowError(
                    "run identity conflicts with invalid current engine"
                ) from error
            self._append_terminal(
                request,
                None,
                None,
                bundle_digest,
                "unavailable:invalid-engine-id",
                (),
                "failed",
                type(error).__name__,
            )
            raise
        request_digest = digest(asdict(request))
        try:
            selection, selected = select_context(request, records)
        except ExplorerShadowError as error:
            if prior_exists:
                raise ExplorerShadowError(
                    "run identity conflicts with invalid current context"
                ) from error
            self._append_terminal(
                request,
                None,
                None,
                bundle_digest,
                engine_id,
                (),
                "failed",
                type(error).__name__,
            )
            raise
        selection_payload = _selection_payload(
            request, selection, request_digest, bundle_digest
        )
        if not validate_explorer(
            "explorer-context-selection-v1", selection_payload
        ).valid:
            raise ExplorerShadowError("selection payload failed its contract")
        with store._transaction():
            existing = self._existing(
                request, selection, bundle_digest, engine_id
            )
            if existing is not None:
                return existing
            selection_record = store.append_record(
                authority=self.ledger.authority,
                foundation_action="foundation.opportunity.write",
                tenant_id=request.tenant_id,
                repository_id=request.repository_id,
                record_type="explorer-context-selection",
                schema_name="explorer-context-selection-v1",
                stream_id=f"explorer-selection:{request.run_id}",
                payload=selection_payload,
                actor_id=ACTOR_ID,
                idempotency_key=f"explorer-selection:{request.run_id}",
                correlation_id=request.run_id,
            )
        try:
            raw = self.engine.discover(request, selected, _freeze(bundle))
            findings = _consume_bounded(raw, request.max_findings)
            prepared = tuple(
                self._validate_finding(finding, selected) for finding in findings
            )
            finding_ids = [finding["finding_id"] for finding in prepared]
            if len(finding_ids) != len(set(finding_ids)):
                raise ExplorerShadowError("finding IDs must be unique within one batch")
        except Exception as error:
            self._append_terminal(
                request,
                selection_record["record_id"],
                selection.selection_digest,
                bundle_digest,
                engine_id,
                (),
                "failed",
                type(error).__name__[:200],
            )
            if isinstance(error, ExplorerShadowError):
                raise
            raise ExplorerShadowError(
                f"shadow discovery failed: {type(error).__name__}"
            ) from error
        outcomes: list[Mapping[str, Any]] = []
        try:
            with store._lock, store._transaction():
                for finding in prepared:
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
                        evidence_digests=finding["evidence_digests"],
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
                self._append_terminal(
                    request,
                    selection_record["record_id"],
                    selection.selection_digest,
                    bundle_digest,
                    engine_id,
                    outcomes,
                    "succeeded",
                    None,
                )
        except Exception as error:
            self._append_terminal(
                request,
                selection_record["record_id"],
                selection.selection_digest,
                bundle_digest,
                engine_id,
                (),
                "failed",
                type(error).__name__[:200],
            )
            if isinstance(error, ExplorerShadowError):
                raise
            raise ExplorerShadowError(
                f"shadow admission failed: {type(error).__name__}"
            ) from error
        return ShadowResult(
            selection,
            selection_record["record_id"],
            tuple(outcomes),
            bundle_digest,
        )

    def _validate_finding(
        self, finding: Any, selected: Sequence[ContextRecord]
    ) -> dict[str, Any]:
        if not isinstance(finding, Mapping):
            raise ExplorerShadowError("finding shape is not exact")
        keys: list[Any] = []
        iterator = iter(finding)
        for _ in range(len(self._FINDING_FIELDS) + 1):
            try:
                keys.append(next(iterator))
            except StopIteration:
                break
            except Exception as error:
                raise ExplorerShadowError(
                    f"finding key iteration failed: {type(error).__name__}"
                ) from error
        else:
            raise ExplorerShadowError("finding shape exceeds field bound")
        try:
            if set(keys) != self._FINDING_FIELDS:
                raise ExplorerShadowError("finding shape is not exact")
            copied = {key: finding[key] for key in sorted(self._FINDING_FIELDS)}
        except ExplorerShadowError:
            raise
        except Exception as error:
            raise ExplorerShadowError(
                f"finding field access failed: {type(error).__name__}"
            ) from error
        for field in (
            "finding_id",
            "problem",
            "affected_user",
            "scope",
            "proposal",
            "expected_outcome",
            "counterargument",
            "stop_reason",
        ):
            copied[field] = _bounded_text(
                copied[field], field, maximum=200 if field == "finding_id" else MAX_TEXT
            )
        if not isinstance(copied["category"], str) or copied["category"] not in CATEGORIES:
            raise ExplorerShadowError("finding category is unsupported")
        if (
            copied["disposition"] is not None
            and not isinstance(copied["disposition"], str)
        ) or copied["disposition"] not in DISPOSITIONS:
            raise ExplorerShadowError("finding disposition is unsupported")
        selected_by_id = {record.memory_id: record for record in selected}
        evidence_ids = _bounded_list(
            copied["evidence_memory_ids"], "evidence_memory_ids", maximum=64
        )
        if (
            not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or not all(
                isinstance(item, str) and item in selected_by_id for item in evidence_ids
            )
        ):
            raise ExplorerShadowError("finding cites unavailable evidence")
        for field in ("acceptance_criteria", "metrics"):
            values = _bounded_list(copied[field], field, maximum=64)
            if (
                not values
                or not all(
                    isinstance(item, str) and item.strip() and len(item) <= MAX_TEXT
                    for item in values
                )
                or len(values) != len(set(values))
            ):
                raise ExplorerShadowError(f"{field} must be a bounded string list")
            copied[field] = values
        copied["evidence_memory_ids"] = evidence_ids
        copied["evidence_digests"] = [
            digest(asdict(selected_by_id[item])) for item in evidence_ids
        ]
        return copied

    def _append_terminal(
        self,
        request: ContextRequest,
        selection_record_id: str | None,
        selection_digest: str | None,
        bundle_digest: str,
        engine_id: str,
        outcomes: Sequence[Mapping[str, Any]],
        status: str,
        error_code: str | None,
    ) -> dict[str, Any]:
        payload = {
            "record_type": "explorer-shadow-run",
            "schema_version": 1,
            "run_id": request.run_id,
            "tenant_id": request.tenant_id,
            "repository_id": request.repository_id,
            "request_digest": digest(asdict(request)),
            "selection_record_id": selection_record_id,
            "selection_digest": selection_digest,
            "skill_bundle_digest": bundle_digest,
            "engine_id": engine_id,
            "status": status,
            "outcomes": list(outcomes),
            "error_code": error_code,
        }
        validation = validate_explorer("explorer-shadow-run-v1", payload)
        if not validation.valid:
            raise ExplorerShadowError(
                "terminal payload failed its contract: " + "; ".join(validation.issues)
            )
        return self.ledger.store.append_record(
            authority=self.ledger.authority,
            foundation_action="foundation.opportunity.write",
            tenant_id=request.tenant_id,
            repository_id=request.repository_id,
            record_type="explorer-shadow-run",
            schema_name="explorer-shadow-run-v1",
            stream_id=f"explorer-run:{request.run_id}",
            payload=payload,
            actor_id=ACTOR_ID,
            idempotency_key=f"explorer-run:{request.run_id}",
            correlation_id=request.run_id,
        )


def _consume_bounded(raw: Any, maximum: int) -> tuple[Mapping[str, Any], ...]:
    if isinstance(raw, (str, bytes, Mapping)):
        raise ExplorerShadowError("engine output must be an iterable of findings")
    try:
        iterator = iter(raw)
    except TypeError as error:
        raise ExplorerShadowError("engine output is not iterable") from error
    findings: list[Mapping[str, Any]] = []
    for _ in range(maximum + 1):
        try:
            item = next(iterator)
        except StopIteration:
            return tuple(findings)
        findings.append(item)
    raise ExplorerShadowError("engine exceeded finding bound")


def _selection_payload(
    request: ContextRequest,
    selection: ContextSelection,
    request_digest: str,
    bundle_digest: str,
) -> dict[str, Any]:
    return {
        "record_type": "explorer-context-selection",
        "schema_version": 1,
        "run_id": request.run_id,
        "tenant_id": request.tenant_id,
        "repository_id": request.repository_id,
        "request_digest": request_digest,
        "policy_version": selection.policy_version,
        "cutoff_sequence": request.cutoff_sequence,
        "inventory_digest": selection.inventory_digest,
        "selection_digest": selection.selection_digest,
        "skill_bundle_digest": bundle_digest,
        "selected_ids": list(selection.selected_ids),
        "omitted": [
            {"memory_id": memory_id, "reason": reason}
            for memory_id, reason in selection.omitted
        ],
        "ordering": list(selection.ordering),
        "selected_bytes": selection.selected_bytes,
        "purpose": selection.purpose,
        "critical_context_coverage": selection.critical_context_coverage,
        "status": "sealed",
    }


def _selection_from_payload(payload: Mapping[str, Any]) -> ContextSelection:
    return ContextSelection(
        str(payload["policy_version"]),
        str(payload["inventory_digest"]),
        tuple(payload["selected_ids"]),
        tuple(
            (str(item["memory_id"]), str(item["reason"])) for item in payload["omitted"]
        ),
        tuple(payload["ordering"]),
        int(payload["selected_bytes"]),
        str(payload["purpose"]),
        int(payload["cutoff_sequence"]),
        str(payload["critical_context_coverage"]),
        str(payload["selection_digest"]),
    )


def shadow_result_bytes(result: ShadowResult) -> bytes:
    return canonical_bytes(asdict(result))
