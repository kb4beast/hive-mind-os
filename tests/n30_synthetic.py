"""SYNTHETIC-TEST-ONLY authority for the durable N30 registry conformance tests.

Nothing here is an approved N30 external mapping, signer, evaluator, custodian or
lease service. It exists so the real SQLite storage paths can be exercised; a pass
proves storage/contract conformance only and admits no work.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from hive_mind_os.benchmark_adapters import BenchmarkResponse
from hive_mind_os.campaign_metrics import (
    AggregateReceipt,
    FamilyObservation,
    ReceiptOutcome,
    canonical_digest,
    stage_paired_bootstrap,
    validate_and_append_seals,
)
from hive_mind_os.n30_host_registry import (
    PURPOSES,
    AuthenticatedMeasurement,
    AuthenticatedOutcome,
    CurrentAdmissionEvidence,
    HostPolicy,
    HostPorts,
    MeasuredExecution,
    MetricDefinition,
    N30HostRegistry,
    PortLimits,
    ReviewedMapping,
    StatusObservation,
)
from tests.test_benchmark_adapters import adapter_manifest
from tests.test_campaign_metrics import lease, protocol, seal_for, stage_evidence

SYNTHETIC = "SYNTHETIC-TEST-ONLY"
ALL_OPERATIONS = ("schedule", "execute", "apply", "seal", "aggregate", "decide")
METRICS = ("success_difference", "cost_ratio", "time_ratio")
DEFINITIONS = {
    "success_difference": MetricDefinition(
        "success_difference", "probability-difference", "paired-difference", "paired-families"
    ),
    "cost_ratio": MetricDefinition(
        "cost_ratio", "ratio", "lower-is-better", "baseline-family-mean"
    ),
    "time_ratio": MetricDefinition(
        "time_ratio", "ratio", "lower-is-better", "baseline-family-mean"
    ),
}
GATE_DEFINITION = "gate:synthetic-v1"


ADAPTER_ID = "adapter:synthetic-n30-authority"
QUALIFICATION_REF = f"qualification:{SYNTHETIC}"


def make_policy(
    outcome_dependency: str = "aggregates_required",
    provider_timeout: float = 2.0,
    max_response_bytes: int = 1_000_000,
) -> HostPolicy:
    """A visibly synthetic reviewed remit; ``outcome_dependency`` is the host's choice."""
    mappings = {
        purpose: ReviewedMapping(
            purpose,
            f"synthetic-{purpose}",
            f"review:{SYNTHETIC}",
            True,
            60,
            ADAPTER_ID,
            QUALIFICATION_REF,
            max_response_bytes,
        )
        for purpose in PURPOSES
    }
    return HostPolicy(
        mappings, DEFINITIONS, GATE_DEFINITION, outcome_dependency, provider_timeout, 2000
    )


class Clock:
    def __init__(self, now: int) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


class SyntheticAuthority:
    """One object implementing the three ports; every answer is scripted by a test."""

    synthetic = True
    # Reviewed-adapter pins; a mapping must name exactly these to be usable.
    adapter_id = ADAPTER_ID
    qualification_ref = QUALIFICATION_REF

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        # Test-only hooks. ``on_call(port, deadline, limits)`` runs inside the provider
        # thread; ``flip_action`` replaces the default revocation at ``flip_at``.
        self.on_call: Callable[[str, float, PortLimits], None] | None = None
        self.flip_action: Callable[[], None] | None = None
        self.seen: list[tuple[str, float, PortLimits]] = []
        self.records: dict[str, tuple[object, object]] = {}
        self.generation = 1
        self.state = "active"
        self.effective_at: int | None = None
        self.max_age = 60
        self.observed_at_override: int | None = None
        self.unavailable = False
        self.calls = 0
        self.flip_at: int | None = None
        self.outcomes: dict[str, dict[str, object]] = {}
        self.measurements: dict[str, dict[str, object]] = {}
        self.outcome_mutator: Callable[[AuthenticatedOutcome], AuthenticatedOutcome] | None = None
        self.measurement_mutator: (
            Callable[[AuthenticatedMeasurement], AuthenticatedMeasurement] | None
        ) = None

    def revoke(self, at: int | None = None) -> None:
        self.generation += 1
        self.state = "revoked"
        self.effective_at = self.clock() if at is None else at

    def status(self, purpose: str) -> StatusObservation:
        observed = self.clock() if self.observed_at_override is None else self.observed_at_override
        return StatusObservation(
            "authority:synthetic-host",
            f"synthetic-{purpose}",
            self.generation,
            observed,
            self.max_age,
            self.state,
            self.effective_at,
        )

    def _enter(self, port: str, deadline: float, limits: PortLimits) -> None:
        self.seen.append((port, deadline, limits))
        if self.on_call is not None:
            self.on_call(port, deadline, limits)

    def current(self, use, immutable_context, now, deadline, limits):
        self._enter("current", deadline, limits)
        self.calls += 1
        if self.unavailable:
            raise RuntimeError("synthetic provider unavailable")
        if self.flip_at is not None and self.calls >= self.flip_at:
            self.flip_at = None
            (self.flip_action or self.revoke)()
        reference = immutable_context["admission_ref"]
        evidence, lease_record = self.records[reference]
        return CurrentAdmissionEvidence(
            reference,
            evidence,
            lease_record,
            frozenset(("host:lease",)),
            canonical_digest(["synthetic-source", reference]),
            self.status("n30.current"),
        )

    def outcome(self, issued_receipt, now, deadline, limits):
        self._enter("outcome", deadline, limits)
        if self.unavailable:
            raise RuntimeError("synthetic provider unavailable")
        spec = self.outcomes[issued_receipt.receipt_digest]
        plan = issued_receipt.plan
        result = AuthenticatedOutcome(
            plan.plan_digest,
            issued_receipt.receipt_digest,
            plan.evaluator_id,
            plan.custodian_id,
            spec["outcome"],
            spec["derivation"],
            tuple(spec.get("aggregates", ())),
            canonical_digest(["synthetic-outcome", issued_receipt.receipt_digest]),
            issued_receipt.issued_at,
            issued_receipt.issued_at,
            self.status("n30.outcome"),
        )
        return self.outcome_mutator(result) if self.outcome_mutator else result

    def add_measurement(
        self,
        evidence_digest: str,
        *,
        task_id: str,
        repetition: int,
        values: dict[str, float],
        left_gate: bool = True,
        right_gate: bool = True,
        observed_at: int = 15,
        signed_at: int = 16,
    ) -> None:
        self.measurements[evidence_digest] = {
            "task_id": task_id,
            "repetition": repetition,
            "values": values,
            "left_gate": left_gate,
            "right_gate": right_gate,
            "observed_at": observed_at,
            "signed_at": signed_at,
        }

    def measurement(self, evidence_digest, expected_binding, now, deadline, limits):
        self._enter("measurement", deadline, limits)
        if self.unavailable:
            raise RuntimeError("synthetic provider unavailable")
        spec = self.measurements[evidence_digest]
        if (expected_binding.task_id, expected_binding.repetition) != (
            spec["task_id"],
            spec["repetition"],
        ):
            raise KeyError("synthetic evidence belongs to another lane")
        executions = []
        for side in (expected_binding.left, expected_binding.right):
            operation = side.invocation.request.operation_id
            result = canonical_digest([operation, "result"])
            executions.append(
                MeasuredExecution(
                    side.invocation,
                    BenchmarkResponse(
                        operation,
                        "success",
                        result,
                        canonical_digest([operation, "receipt"]),
                        1.0,
                        2.0,
                        3.0,
                        4.0,
                    ),
                    result,
                )
            )
        measured = AuthenticatedMeasurement(
            evidence_digest,
            expected_binding.digest,
            (executions[0], executions[1]),
            dict(spec["values"]),
            dict(DEFINITIONS),
            GATE_DEFINITION,
            bool(spec["left_gate"]),
            bool(spec["right_gate"]),
            int(spec["observed_at"]),
            int(spec["signed_at"]),
            self.status("n30.measurement"),
        )
        return self.measurement_mutator(measured) if self.measurement_mutator else measured


class World:
    """A protocol, synthetic authority and SQLite store in one temporary directory."""

    def __init__(
        self,
        directory: str | Path,
        *,
        now: int = 20,
        outcome_dependency: str = "aggregates_required",
        fault_hook: Callable[[str], None] | None = None,
        lease_changes: dict[str, object] | None = None,
        create: bool = True,
        provider_timeout: float = 2.0,
        max_response_bytes: int = 1_000_000,
    ) -> None:
        self.directory = Path(directory)
        self.path = self.directory / "n30.sqlite"
        initial = protocol()
        self.manifest = adapter_manifest(initial)
        experiment = dict(initial.experiment_manifest)
        experiment["recipe_manifest_digest"] = self.manifest.digest
        self.p = replace(initial, experiment_manifest=experiment)
        self.clock = Clock(now)
        self.authority = SyntheticAuthority(self.clock)
        self.policy = make_policy(outcome_dependency, provider_timeout, max_response_bytes)
        self.evidence = stage_evidence(self.p, "original")
        self.lease = lease(
            self.p, "original", operations=ALL_OPERATIONS, **(lease_changes or {})
        )
        self.authority.records["admission:original"] = (self.evidence, self.lease)
        self.registry = self.open_registry(create=create, fault_hook=fault_hook)

    def open_registry(
        self, *, create: bool = False, fault_hook: Callable[[str], None] | None = None
    ) -> N30HostRegistry:
        factory = N30HostRegistry.create if create else N30HostRegistry.open
        return factory(
            self.path,
            policy=self.policy,
            ports=HostPorts(self.authority, self.authority, self.authority),
            clock=self.clock,
            adapter_manifest=self.manifest,
            _fault_hook=fault_hook,
        )

    def reopen(self, *, fault_hook=None) -> N30HostRegistry:
        self.registry.close()
        self.registry = self.open_registry(fault_hook=fault_hook)
        return self.registry

    def admit(self, registry: N30HostRegistry | None = None):
        return (registry or self.registry).admit(self.p, "original", "admission:original")

    def seal_entrants(self, handle, registry: N30HostRegistry | None = None) -> None:
        registry = registry or self.registry
        seals = tuple(
            seal_for(
                self.p,
                self.evidence,
                variant,
                index,
                canonical_digest(f"candidate-{variant}"),
                10 + index,
            )
            for index, variant in enumerate(("MB0", "MB1", "MB2", "MB3"), 1)
        )
        validate_and_append_seals(self.p, seals, registry=registry, admission_handle=handle)

    def bracket(self, registry: N30HostRegistry | None = None):
        registry = registry or self.registry
        handle = self.admit(registry)
        state = registry.open_bracket(
            handle, self.p.protocol_digest, "original", "builder-component"
        )
        return handle, state

    def prepared(self):
        """Admission, four entrant seals and an initial bracket on the live store."""
        handle = self.admit()
        self.seal_entrants(handle)
        state = self.registry.open_bracket(
            handle, self.p.protocol_digest, "original", "builder-component"
        )
        return handle, state

    def measure_pair(self, left: str, right: str, *, success, cost=0.8, time=0.8):
        rows = []
        values = {"success_difference": success, "cost_ratio": cost, "time_ratio": time}
        for task in self.evidence.tasks:
            for repetition in range(self.evidence.repetitions):
                evidence_digest = canonical_digest(
                    ["synthetic-measurement", left, right, task.task_id, repetition]
                )
                self.authority.add_measurement(
                    evidence_digest,
                    task_id=task.task_id,
                    repetition=repetition,
                    values=dict(values),
                )
                rows.append(
                    FamilyObservation(
                        task.family_id, task.task_id, repetition, evidence_digest, 0.0
                    )
                )
        return tuple(rows), values

    def aggregate_pair(
        self, handle, left: str, right: str, *, success, registry=None
    ) -> tuple[AggregateReceipt, ...]:
        rows, values = self.measure_pair(left, right, success=success)
        return tuple(
            stage_paired_bootstrap(
                self.p,
                metric,
                left,
                right,
                tuple(replace(row, value=values[metric]) for row in rows),
                left_hard_gates=True,
                right_hard_gates=True,
                registry=registry or self.registry,
                admission_handle=handle,
            )
            for metric in METRICS
        )

    def script_direct(self, receipts, outcome: str = "DRAW") -> tuple[ReceiptOutcome, ...]:
        results = []
        for receipt in receipts:
            value = "BYE" if receipt.plan.bye else outcome
            if not receipt.plan.bye:
                self.authority.outcomes[receipt.receipt_digest] = {
                    "outcome": value,
                    "derivation": "evaluator",
                }
            results.append(ReceiptOutcome(receipt, value))
        return tuple(results)
