"""Conformance tests for the durable N30 registry (ADR-094).

Every positive path runs against a real SQLite store with a distinctly labelled
SYNTHETIC authority (tests/n30_synthetic.py). Passing proves storage and contract
conformance only; it admits nothing and grants no authority.
"""

import tempfile
import threading
import unittest
from dataclasses import replace

from hive_mind_os.campaign_metrics import (
    AdmissionUse,
    AggregateReceipt,
    BracketTransition,
    CampaignMetricsError,
    ConsumeRoundRequest,
    DescriptiveInterval,
    FamilyObservation,
    FinalistBinding,
    IssuedReceipt,
    LeaseExhausted,
    ReceiptOutcome,
    build_aggregate_evidence,
    canonical_digest,
    decide_match,
    plan_next_round,
    stage_paired_bootstrap,
    transition_after_round,
    validate_and_append_seals,
)
from hive_mind_os.n30_host_registry import (
    AuthorityBlocked,
    HostPolicy,
    HostPorts,
    MetricDefinition,
    N30HostError,
    N30HostRegistry,
    N30StoreError,
    ReviewedMapping,
    aggregate_request_digest,
    commit_request_digest,
    consume_request_digest,
    issue_request_digest,
)
from tests.n30_synthetic import (
    ALL_OPERATIONS,
    DEFINITIONS,
    METRICS,
    SYNTHETIC,
    World,
    make_policy,
)
from tests.test_campaign_metrics import lease, seal_for, stage_evidence

D = canonical_digest("unrelated")


class N30Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def world(self, **kwargs):
        directory = tempfile.mkdtemp(dir=self._tmp.name)
        world = World(directory, **kwargs)
        self.addCleanup(lambda: world.registry.close())
        return world

    def track(self, registry):
        self.addCleanup(registry.close)
        return registry

    def scheduled(self, **kwargs):
        world = self.world(**kwargs)
        handle, state = world.prepared()
        return world, handle, state

    def count(self, world, table):
        return world.registry._query(f"SELECT COUNT(*) FROM {table}")[0][0]

    def bracket(self, world, handle, state, operation="schedule"):
        return world.registry.resolve_bracket(
            handle, state.opaque_handle, world.p.protocol_digest, operation
        )

    def schedule(self, world, handle, state):
        return state.schedule(world.p, registry=world.registry, admission_handle=handle)

    def apply(self, world, handle, state, results):
        return state.apply(
            world.p, results, registry=world.registry, admission_handle=handle
        )

    def not_exhaustion(self, action):
        with self.assertRaises(CampaignMetricsError) as caught:
            action()
        self.assertNotIsInstance(caught.exception, LeaseExhausted)
        return caught.exception


class TemporalAndRestartTests(N30Base):
    def test_advancing_clock_schedule_apply_restart_keep_receipt_digests(self):
        w = self.world(outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        first = self.schedule(w, handle, state)
        self.assertEqual(len(first.receipts), 2)
        digests = [receipt.receipt_digest for receipt in first.receipts]
        self.assertEqual({receipt.issued_at for receipt in first.receipts}, {20})

        w.clock.now = 21  # a delayed schedule must not rewrite issuance
        again = self.schedule(w, handle, state)
        self.assertEqual([r.receipt_digest for r in again.receipts], digests)
        self.assertTrue(
            all(a.opaque_handle is b.opaque_handle for a, b in zip(first.receipts, again.receipts))
        )
        self.assertEqual({r.issued_at for r in again.receipts}, {20})
        self.assertEqual(self.count(w, "issuances"), 1)

        advanced = self.apply(w, handle, state, w.script_direct(again.receipts))
        self.assertEqual(self.bracket(w, handle, advanced).round_number, 1)
        self.assertEqual(self.count(w, "consumptions"), 2)

        w.clock.now = 22
        registry = w.reopen()  # full schema/integrity/digest/lineage verification
        handle2 = w.admit()
        state2 = registry.recover_bracket(
            handle2, w.p.protocol_digest, "original", "builder-component"
        )
        recovered = registry.recover(
            handle2, issue_request_digest(tuple(r.plan for r in first.receipts))
        )
        self.assertEqual([r.receipt_digest for r in recovered.receipts], digests)
        self.assertEqual({r.issued_at for r in recovered.receipts}, {20})
        with self.assertRaises(CampaignMetricsError):  # old instance's wrappers
            registry.resolve(handle, AdmissionUse(w.p.protocol_digest, "original", "apply"))
        with self.assertRaises(CampaignMetricsError):
            registry.resolve_bracket(
                handle2, advanced.opaque_handle, w.p.protocol_digest, "apply"
            )
        second = state2.schedule(w.p, registry=registry, admission_handle=handle2)
        self.assertEqual({r.issued_at for r in second.receipts}, {22})

    def test_status_clock_and_provider_negatives_block_without_fabricating_exhaustion(self):
        def stale(w):
            w.clock.now = 200
            w.authority.observed_at_override = 100

        cases = {
            "future observation": lambda w: setattr(w.authority, "observed_at_override", 30),
            "stale observation": stale,
            "unknown status": lambda w: setattr(w.authority, "state", "unknown"),
            "unavailable provider": lambda w: setattr(w.authority, "unavailable", True),
            "unreviewed freshness": lambda w: setattr(w.authority, "max_age", 61),
            "generation rollback": lambda w: setattr(w.authority, "generation", 0),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                w, handle, state = self.scheduled()
                mutate(w)
                self.not_exhaustion(lambda: self.schedule(w, handle, state))
                self.assertEqual(self.count(w, "issuances"), 0)

    def test_clock_regression_after_positive_use_blocks(self):
        w, handle, state = self.scheduled()
        self.schedule(w, handle, state)
        w.clock.now = 19
        exc = self.not_exhaustion(lambda: self.schedule(w, handle, state))
        self.assertIsInstance(exc, AuthorityBlocked)

    def test_future_activation_is_a_blocker_and_exact_expiry_is_not_enrollable(self):
        w = self.world(lease_changes={"issued_at": 25})
        self.not_exhaustion(lambda: w.admit())
        w = self.world(lease_changes={"expires_at": 20})
        with self.assertRaises(LeaseExhausted):
            w.admit()

    def test_revocation_between_issuance_and_fresh_recheck_closes_without_usable_receipts(self):
        w, handle, state = self.scheduled()
        # schedule() makes: resolve_bracket, _resolve, issue_round, then the fresh recheck.
        w.authority.flip_at = w.authority.calls + 4
        result = self.schedule(w, handle, state)
        self.assertEqual(result.terminal, "lease_exhausted")
        self.assertEqual(result.receipts, ())
        closed = self.bracket(w, handle, result.state)
        self.assertEqual(closed.terminal, "lease_exhausted")
        self.assertEqual(closed.round_number, 0)
        self.assertEqual(closed.applied_receipt_digests, frozenset())
        self.assertEqual(self.count(w, "consumptions"), 0)
        with self.assertRaises(CampaignMetricsError):  # superseded state cannot be reused
            self.schedule(w, handle, state)

    def test_exact_expiry_and_confirmed_revocation_close_only_unchanged_history(self):
        def expire(w):
            w.clock.now = 1000

        def revoke(w):
            w.authority.revoke()

        for label, trigger in (("exact expiry", expire), ("revocation", revoke)):
            with self.subTest(label):
                w, handle, state = self.scheduled()
                scheduled = self.schedule(w, handle, state)
                trigger(w)
                results = w.script_direct(scheduled.receipts)
                with self.assertRaises(CampaignMetricsError):  # nonempty apply rejects
                    self.apply(w, handle, state, results)
                self.assertEqual(self.count(w, "consumptions"), 0)
                closed = self.apply(w, handle, state, ())  # empty apply closes
                snapshot = self.bracket(w, handle, closed)
                self.assertEqual(snapshot.terminal, "lease_exhausted")
                self.assertEqual(snapshot.round_number, 0)
                self.assertEqual(snapshot.applied_receipt_digests, frozenset())
                self.assertFalse(snapshot.losses or snapshot.quarantined)
                # repeated terminal access is idempotent and never invents a new version
                again = self.schedule(w, handle, closed)
                self.assertEqual((again.terminal, again.receipts), ("lease_exhausted", ()))
                self.assertIs(again.state, closed)
                self.assertIs(self.apply(w, handle, closed, ()), closed)
                versions = self.count(w, "bracket_versions")
                self.apply(w, handle, closed, ())
                self.assertEqual(self.count(w, "bracket_versions"), versions)
                # unknown status may neither confirm nor overwrite the terminal reason
                if label == "revocation":
                    w.authority.state = "unknown"
                    w.authority.effective_at = None
                    self.not_exhaustion(lambda: self.schedule(w, handle, closed))
                    w.authority.state = "revoked"
                    w.authority.effective_at = 20
                bracket = self.bracket(w, handle, closed)
                overwrite = BracketTransition(
                    0, {}, {}, {}, frozenset(), "one_survivor", frozenset()
                )
                with self.assertRaises(CampaignMetricsError):
                    w.registry.commit_bracket(
                        handle, closed.opaque_handle, bracket.bracket_digest, overwrite
                    )
                self.assertEqual(
                    self.bracket(w, handle, closed).terminal, "lease_exhausted"
                )

    def test_active_lease_cannot_be_declared_exhausted(self):
        w, handle, state = self.scheduled()
        bracket = self.bracket(w, handle, state)
        invented = BracketTransition(
            0, {}, {}, {}, frozenset(), "lease_exhausted", frozenset()
        )
        with self.assertRaises(CampaignMetricsError):
            w.registry.commit_bracket(
                handle, state.opaque_handle, bracket.bracket_digest, invented
            )


class EvidencePathTests(N30Base):
    def test_measurements_aggregates_outcomes_and_one_atomic_round_consumption(self):
        w, handle, state = self.scheduled()
        scheduled = self.schedule(w, handle, state)
        first, second = scheduled.receipts
        self.assertEqual((first.plan.left, first.plan.right), ("MB0", "MB1"))
        self.assertEqual((second.plan.left, second.plan.right), ("MB2", "MB3"))
        left_wins = w.aggregate_pair(handle, "MB0", "MB1", success=0.5)
        right_wins = w.aggregate_pair(handle, "MB2", "MB3", success=-0.5)
        self.assertEqual(
            decide_match(w.p, *left_wins, registry=w.registry, admission_handle=handle), "LEFT"
        )
        self.assertEqual(
            decide_match(w.p, *right_wins, registry=w.registry, admission_handle=handle), "RIGHT"
        )
        # 12 admitted task/repetition measurements per pair are reused by all three metrics
        self.assertEqual(self.count(w, "measurements"), 24)
        self.assertEqual(self.count(w, "aggregate_uses"), 72)
        self.assertEqual(self.count(w, "aggregates"), 6)
        # aggregate evidence-use links are not bracket token consumption
        self.assertEqual(self.count(w, "consumptions"), 0)

        def digests(triple):
            return tuple(item.aggregate_digest for item in triple)

        good = {
            first.receipt_digest: ("LEFT", digests(left_wins)),
            second.receipt_digest: ("RIGHT", digests(right_wins)),
        }

        def script(table):
            for receipt in scheduled.receipts:
                outcome, aggregates = table[receipt.receipt_digest]
                w.authority.outcomes[receipt.receipt_digest] = {
                    "outcome": outcome,
                    "derivation": "aggregates",
                    "aggregates": aggregates,
                }
            return tuple(
                ReceiptOutcome(receipt, table[receipt.receipt_digest][0])
                for receipt in scheduled.receipts
            )

        relabelled = script(good)
        for receipt in scheduled.receipts:  # evaluator remit requires aggregates
            w.authority.outcomes[receipt.receipt_digest]["derivation"] = "evaluator"
            w.authority.outcomes[receipt.receipt_digest]["aggregates"] = ()
        with self.assertRaises(CampaignMetricsError):
            self.apply(w, handle, state, relabelled)

        forged_tables = {
            "decision differs": {
                first.receipt_digest: ("RIGHT", digests(left_wins)),
                second.receipt_digest: ("RIGHT", digests(right_wins)),
            },
            "wrong pair": {
                first.receipt_digest: ("RIGHT", digests(right_wins)),
                second.receipt_digest: ("RIGHT", digests(right_wins)),
            },
            "two aggregates": {
                first.receipt_digest: ("LEFT", digests(left_wins)[:2]),
                second.receipt_digest: ("RIGHT", digests(right_wins)),
            },
            "unrecorded aggregate": {
                first.receipt_digest: ("LEFT", (D, D, D)),
                second.receipt_digest: ("RIGHT", digests(right_wins)),
            },
        }
        for label, table in forged_tables.items():
            with self.subTest(label):
                results = script(table)
                with self.assertRaises(CampaignMetricsError):
                    self.apply(w, handle, state, results)
                self.assertEqual(self.count(w, "consumptions"), 0)
                self.assertEqual(self.bracket(w, handle, state).round_number, 0)

        def plan_digest(outcome):
            return replace(outcome, plan_digest=D)

        results = script(good)
        w.authority.outcome_mutator = plan_digest
        with self.assertRaises(CampaignMetricsError):
            self.apply(w, handle, state, results)
        w.authority.outcome_mutator = None
        self.assertEqual(self.count(w, "consumptions"), 0)

        advanced = self.apply(w, handle, state, results)
        snapshot = self.bracket(w, handle, advanced)
        self.assertEqual(snapshot.round_number, 1)
        self.assertEqual(dict(snapshot.losses), {"MB1": 1, "MB2": 1})
        self.assertEqual(self.count(w, "consumptions"), 2)
        w.reopen()  # every digest, reference and lineage verifies again

    def test_forged_measurement_boundaries_reject_atomically_then_reuse_is_exact(self):
        w, handle, _ = self.scheduled()
        rows, _ = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=0.5) for row in rows)

        def one_execution(mutation):
            def apply(measured):
                changed = mutation(measured.executions[0])
                return replace(measured, executions=(changed, measured.executions[1]))

            return apply

        invalid = DEFINITIONS["cost_ratio"]
        mutators = {
            "swapped ancestry": lambda m: replace(m, executions=(m.executions[1], m.executions[0])),
            "duplicated ancestry": lambda m: replace(m, executions=(m.executions[0],) * 2),
            "seed": one_execution(
                lambda e: replace(e, invocation=replace(e.invocation, seed=e.invocation.seed + 1))
            ),
            "operation": one_execution(
                lambda e: replace(e, response=replace(e.response, operation_id=D))
            ),
            "raw result": one_execution(lambda e: replace(e, raw_result_digest=D)),
            "value": lambda m: replace(m, values={**m.values, "success_difference": 0.4}),
            "gate": lambda m: replace(m, left_hard_gates=False),
            "unit": lambda m: replace(
                m,
                definitions={
                    **m.definitions,
                    "cost_ratio": MetricDefinition("cost_ratio", "percent", invalid.direction, invalid.denominator),
                },
            ),
            "denominator": lambda m: replace(
                m,
                definitions={
                    **m.definitions,
                    "cost_ratio": MetricDefinition("cost_ratio", invalid.unit, invalid.direction, "other"),
                },
            ),
            "gate definition": lambda m: replace(m, gate_definition="gate:other"),
            "binding": lambda m: replace(m, binding_digest=D),
            "evidence": lambda m: replace(m, evidence_digest=D),
            "future window": lambda m: replace(m, observed_at=99, signed_at=99),
        }

        def record(candidate=rows):
            return stage_paired_bootstrap(
                w.p,
                "success_difference",
                "MB0",
                "MB1",
                candidate,
                left_hard_gates=True,
                right_hard_gates=True,
                registry=w.registry,
                admission_handle=handle,
            )

        for label, mutator in mutators.items():
            with self.subTest(label):
                w.authority.measurement_mutator = mutator
                with self.assertRaises(CampaignMetricsError):
                    record()
                self.assertEqual(self.count(w, "measurements"), 0)
                self.assertEqual(self.count(w, "aggregates"), 0)
        w.authority.measurement_mutator = None
        with self.assertRaises(CampaignMetricsError):  # duplicate rows within one aggregate
            record((rows[0],) + rows[:-1])
        with self.assertRaises(CampaignMetricsError):  # incomplete 12x1 membership
            record(rows[:-1])
        with self.assertRaises(CampaignMetricsError):  # caller value differs from evidence
            record(tuple(replace(row, value=0.25) for row in rows))
        unregistered = replace(rows[0], receipt_digest=D)
        with self.assertRaises(CampaignMetricsError):
            record((unregistered,) + rows[1:])

        receipt = record()
        self.assertEqual(self.count(w, "measurements"), 12)
        # the same evidence may support another named metric under the exact same binding
        for metric, value in (("cost_ratio", 0.8), ("time_ratio", 0.8)):
            stage_paired_bootstrap(
                w.p,
                metric,
                "MB0",
                "MB1",
                tuple(replace(row, value=value) for row in rows),
                left_hard_gates=True,
                right_hard_gates=True,
                registry=w.registry,
                admission_handle=handle,
            )
        self.assertEqual(self.count(w, "measurements"), 12)
        self.assertEqual(self.count(w, "aggregate_uses"), 36)
        # but never under a different pair binding
        with self.assertRaises(N30StoreError):
            stage_paired_bootstrap(
                w.p,
                "success_difference",
                "MB2",
                "MB3",
                rows,
                left_hard_gates=True,
                right_hard_gates=True,
                registry=w.registry,
                admission_handle=handle,
            )
        self.assertEqual(w.registry.resolve_aggregate(handle, receipt).metric, "success_difference")
        # revoked/changed measurement status rejects a later resolve
        w.authority.measurement_mutator = lambda m: replace(m, evidence_digest=D)
        with self.assertRaises(CampaignMetricsError):
            w.registry.resolve_aggregate(handle, receipt)

    def test_final_thirty_by_three_aggregate_is_authenticated_and_decided(self):
        w = self.world(now=15)
        p = w.p
        original_evidence = stage_evidence(p, "original", stage_opened_at=2)
        hybrid_evidence = stage_evidence(p, "hybrid", stage_opened_at=3)
        original_seal = seal_for(p, original_evidence, "MC0", 1, canonical_digest("candidate-MC0"), 5)
        hybrid_seal = seal_for(p, hybrid_evidence, "MH1", 2, canonical_digest("candidate-MH1"), 6)
        finalists = (
            FinalistBinding("MC0", original_seal.candidate_digest, original_seal.recipe_digest,
                            "whole-default", "original", original_seal.seal_digest),
            FinalistBinding("MH1", hybrid_seal.candidate_digest, hybrid_seal.recipe_digest,
                            "whole-default", "hybrid", hybrid_seal.seal_digest),
        )
        final_evidence = stage_evidence(
            p, "final", final_pair=finalists, stage_opened_at=10, holdout_opened_at=20
        )
        for stage, evidence in (("original", original_evidence), ("hybrid", hybrid_evidence),
                                ("final", final_evidence)):
            w.authority.records[f"admission:{stage}"] = (
                evidence,
                lease(p, stage, operations=ALL_OPERATIONS),
            )
        registry = w.registry
        original = registry.admit(p, "original", "admission:original")
        validate_and_append_seals(p, (original_seal,), registry=registry, admission_handle=original)
        hybrid = registry.admit(p, "hybrid", "admission:hybrid")
        validate_and_append_seals(p, (hybrid_seal,), registry=registry, admission_handle=hybrid)
        final = registry.admit(p, "final", "admission:final")
        final_seals = (
            seal_for(p, final_evidence, "MC0", 3, original_seal.candidate_digest, 11),
            seal_for(p, final_evidence, "MH1", 4, hybrid_seal.candidate_digest, 12),
        )
        validate_and_append_seals(p, final_seals, registry=registry, admission_handle=final)
        w.clock.now = 21  # the promotion holdout has opened

        rows = []
        for task in final_evidence.tasks:
            for repetition in range(3):
                digest = canonical_digest(["final-measurement", task.task_id, repetition])
                w.authority.add_measurement(
                    digest,
                    task_id=task.task_id,
                    repetition=repetition,
                    values={"success_difference": 0.5, "cost_ratio": 0.8, "time_ratio": 0.8},
                    observed_at=21,
                    signed_at=21,
                )
                rows.append(FamilyObservation(task.family_id, task.task_id, repetition, digest, 0.0))
        self.assertEqual(len(rows), 90)
        receipts = []
        for metric, value in (("success_difference", 0.5), ("cost_ratio", 0.8), ("time_ratio", 0.8)):
            receipts.append(
                stage_paired_bootstrap(
                    p, metric, "MC0", "MH1", tuple(replace(row, value=value) for row in rows),
                    left_hard_gates=True, right_hard_gates=True,
                    registry=registry, admission_handle=final,
                )
            )
        self.assertEqual(
            decide_match(p, *receipts, registry=registry, admission_handle=final), "LEFT"
        )
        with self.assertRaises(CampaignMetricsError):  # 30x1 is not the admitted 30x3 shape
            stage_paired_bootstrap(
                p, "success_difference", "MC0", "MH1", tuple(rows[::3]),
                left_hard_gates=True, right_hard_gates=True,
                registry=registry, admission_handle=final,
            )
        with self.assertRaises(CampaignMetricsError):  # wrong final pair
            stage_paired_bootstrap(
                p, "success_difference", "MC1", "MH2", tuple(rows),
                left_hard_gates=True, right_hard_gates=True,
                registry=registry, admission_handle=final,
            )
        self.assertEqual(self.count(w, "measurements"), 90)


class DirectCallTests(N30Base):
    def test_all_nine_methods_reject_malformed_or_forged_direct_calls(self):
        w, handle, state = self.scheduled()
        registry, p = w.registry, w.p
        scheduled = self.schedule(w, handle, state)
        receipts = scheduled.receipts
        bracket = self.bracket(w, handle, state)
        pd = p.protocol_digest
        use = AdmissionUse(pd, "original", "schedule")

        def rejects(label, call, *, error=CampaignMetricsError):
            with self.subTest(label):
                with self.assertRaises(error):
                    call()

        # 1 resolve
        rejects("resolve foreign", lambda: registry.resolve(object(), use))
        rejects("resolve non-use", lambda: registry.resolve(handle, "schedule"))
        rejects("resolve wrong stage", lambda: registry.resolve(handle, replace(use, stage="final")))
        rejects("resolve bad operation", lambda: registry.resolve(handle, replace(use, operation="x")))
        rejects("resolve foreign protocol", lambda: registry.resolve(handle, replace(use, protocol_digest=D)))
        rejects("resolve wrong wrapper kind", lambda: registry.resolve(state.opaque_handle, use))
        rejects("resolve edited handle", lambda: registry.resolve(type(handle)(), use))
        rejects("resolve foreign state", lambda: registry.resolve(handle, replace(use, state_admission_digest=D)))
        # 2 open_bracket
        rejects("open foreign", lambda: registry.open_bracket(object(), pd, "original", "builder-component"))
        rejects("open wrong track", lambda: registry.open_bracket(handle, pd, "original", "no-such-track"))
        rejects("open wrong stage", lambda: registry.open_bracket(handle, pd, "hybrid", "builder-component"))
        rejects("open wrong protocol", lambda: registry.open_bracket(handle, D, "original", "builder-component"))
        # 3 resolve_bracket
        rejects("bracket foreign state", lambda: registry.resolve_bracket(handle, object(), pd, "schedule"))
        rejects("bracket wrong protocol", lambda: registry.resolve_bracket(handle, state.opaque_handle, D, "schedule"))
        rejects("bracket bad operation", lambda: registry.resolve_bracket(handle, state.opaque_handle, pd, "x"))
        rejects("bracket foreign admission", lambda: registry.resolve_bracket(object(), state.opaque_handle, pd, "schedule"))
        # 4 issue_round
        plans = tuple(receipt.plan for receipt in receipts)
        rejects("issue empty", lambda: registry.issue_round(handle, ()))
        rejects("issue non-plan", lambda: registry.issue_round(handle, ("plan",)))
        rejects("issue partial", lambda: registry.issue_round(handle, plans[:1]))
        rejects("issue seed", lambda: registry.issue_round(handle, (replace(plans[0], seed=plans[0].seed + 1),) + plans[1:]))
        rejects("issue principal", lambda: registry.issue_round(handle, (replace(plans[0], evaluator_id="evaluator:other"),) + plans[1:]))
        rejects("issue duplicate", lambda: registry.issue_round(handle, (plans[0], plans[0])))
        rejects("issue foreign admission", lambda: registry.issue_round(handle, tuple(replace(x, admission_digest=D) for x in plans)))
        rejects("issue unknown bracket", lambda: registry.issue_round(handle, tuple(replace(x, bracket_digest=D) for x in plans)))
        # 5 consume_round: malformed, missing, extra, duplicate, forged, unauthenticated
        results = w.script_direct(receipts)
        transition = transition_after_round(p, bracket, results)
        admission = bracket.admission_digest

        def request(items=results, moved=transition, **changes):
            base = ConsumeRoundRequest(admission, pd, "original", 1, bracket.bracket_digest, tuple(items), moved)
            return replace(base, **changes)

        foreign = ReceiptOutcome(IssuedReceipt(object(), plans[0], receipts[0].issued_at), "DRAW")
        rejects("consume junk", lambda: registry.consume_round(handle, state.opaque_handle, "junk"))
        rejects("consume missing", lambda: registry.consume_round(handle, state.opaque_handle, request(results[:1])))
        rejects("consume duplicate", lambda: registry.consume_round(handle, state.opaque_handle, request((results[0], results[0]))))
        rejects("consume extra", lambda: registry.consume_round(handle, state.opaque_handle, request(results + (results[0],))))
        rejects("consume forged wrapper", lambda: registry.consume_round(handle, state.opaque_handle, request((foreign, results[1]))))
        rejects("consume wrong round", lambda: registry.consume_round(handle, state.opaque_handle, request(round_number=2)))
        rejects("consume wrong digest", lambda: registry.consume_round(handle, state.opaque_handle, request(expected_bracket_digest=D)))
        forged = replace(transition, losses={"MB0": 3})
        rejects("consume forged transition", lambda: registry.consume_round(handle, state.opaque_handle, request(moved=forged)))
        w.authority.outcomes.clear()
        rejects("consume unauthenticated outcomes", lambda: registry.consume_round(handle, state.opaque_handle, request()), error=AuthorityBlocked)
        self.assertEqual(self.count(w, "consumptions"), 0)  # no partial writes
        self.assertEqual(self.bracket(w, handle, state).round_number, 0)
        # 6 commit_bracket
        invented = BracketTransition(0, {}, {}, {}, frozenset(), "one_survivor", frozenset())
        rejects("commit invented", lambda: registry.commit_bracket(handle, state.opaque_handle, bracket.bracket_digest, invented))
        rejects("commit non-terminal", lambda: registry.commit_bracket(handle, state.opaque_handle, bracket.bracket_digest, replace(invented, terminal=None)))
        rejects("commit rewind/loss", lambda: registry.commit_bracket(handle, state.opaque_handle, bracket.bracket_digest, replace(invented, losses={"MB0": 3})))
        rejects("commit stale digest", lambda: registry.commit_bracket(handle, state.opaque_handle, D, invented))
        rejects("commit junk", lambda: registry.commit_bracket(handle, state.opaque_handle, bracket.bracket_digest, "x"))
        rejects("commit foreign state", lambda: registry.commit_bracket(handle, object(), bracket.bracket_digest, invented))
        # 7 append_seals
        snapshot = registry.resolve(handle, AdmissionUse(pd, "original", "seal"))
        history = canonical_digest(snapshot.seal_history)
        seal = seal_for(p, w.evidence, "MC0", 5, canonical_digest("candidate-MC0"), 15)
        rejects("seals empty", lambda: registry.append_seals(handle, history, 20, ()))
        rejects("seals stale history", lambda: registry.append_seals(handle, D, 20, (seal,)))
        rejects("seals future time", lambda: registry.append_seals(handle, history, 999, (seal,)))
        rejects("seals early time", lambda: registry.append_seals(handle, history, 14, (seal,)))
        rejects("seals gap", lambda: registry.append_seals(handle, history, 20, (replace(seal, sequence=7),)))
        rejects("seals backdated", lambda: registry.append_seals(handle, history, 20, (replace(seal, sealed_at=9),)))
        rejects("seals junk", lambda: registry.append_seals(handle, history, 20, ("seal",)))
        self.assertEqual(len(registry.resolve(handle, AdmissionUse(pd, "original", "seal")).seal_history), 4)
        # 8 record_aggregate
        rows, values = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=0.5) for row in rows)
        aggregate_snapshot = registry.resolve(handle, AdmissionUse(pd, "original", "aggregate"))
        evidence = build_aggregate_evidence(
            p, aggregate_snapshot, "success_difference", "MB0", "MB1", rows,
            left_hard_gates=True, right_hard_gates=True,
        )
        rejects("aggregate junk", lambda: registry.record_aggregate(handle, "x", rows))
        rejects("aggregate foreign", lambda: registry.record_aggregate(object(), evidence, rows))
        rejects("aggregate forged interval", lambda: registry.record_aggregate(handle, replace(evidence, interval=DescriptiveInterval(0.9, 0.8, 1.0, 12)), rows))
        rejects("aggregate forged gate", lambda: registry.record_aggregate(handle, replace(evidence, left_hard_gates=False), rows))
        rejects("aggregate forged digest", lambda: registry.record_aggregate(handle, replace(evidence, observation_digest=D), rows))
        rejects("aggregate short shape", lambda: registry.record_aggregate(handle, evidence, rows[:-1]))
        rejects("aggregate non-row", lambda: registry.record_aggregate(handle, evidence, rows[:-1] + ("row",)))
        self.assertEqual(self.count(w, "aggregates"), 0)
        receipt = registry.record_aggregate(handle, evidence, rows)
        # 9 resolve_aggregate
        rejects("resolve aggregate foreign", lambda: registry.resolve_aggregate(handle, AggregateReceipt(object(), D)))
        rejects("resolve aggregate substituted", lambda: registry.resolve_aggregate(handle, replace(receipt, aggregate_digest=D)))
        rejects("resolve aggregate junk", lambda: registry.resolve_aggregate(handle, "receipt"))
        rejects("resolve aggregate foreign admission", lambda: registry.resolve_aggregate(object(), receipt))
        self.assertEqual(registry.resolve_aggregate(handle, receipt), evidence)
        recovered = registry.recover(handle, aggregate_request_digest(evidence, rows))
        self.assertIs(recovered.aggregate.opaque_handle, receipt.opaque_handle)
        self.assertEqual(recovered.result_digest, receipt.aggregate_digest)

    def test_thread_interning_foreign_and_stale_handles(self):
        w, handle, state = self.scheduled(outcome_dependency="direct_permitted")
        seen = []
        errors = []

        def worker():
            try:
                seen.append(w.admit())
            except BaseException as error:  # pragma: no cover - reported below
                errors.append(error)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        # One provider call is in flight per registry and there is no backlog, so a
        # concurrent caller is either served the same interned wrapper or refused with a
        # typed block; it is never given a second wrapper or a hang.
        self.assertTrue(seen)
        self.assertTrue(all(item is handle for item in seen))
        self.assertTrue(all(isinstance(error, AuthorityBlocked) for error in errors), errors)
        self.assertEqual(len(seen) + len(errors), 12)
        self.assertIs(w.admit(), handle)

        # Interning itself is thread safe: many threads asking for one durable record
        # always receive the identical wrapper.
        key = w.registry._interner.key(handle, type(handle))
        wrappers = []

        def intern():
            wrappers.append(w.registry._interner.wrapper(type(handle), key))

        interners = [threading.Thread(target=intern) for _ in range(16)]
        for thread in interners:
            thread.start()
        for thread in interners:
            thread.join()
        self.assertTrue(all(item is handle for item in wrappers))
        self.assertEqual(len(wrappers), 16)

        other = self.track(w.open_registry())  # independent instance, same database
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")
        with self.assertRaises(CampaignMetricsError):
            other.resolve(handle, use)
        with self.assertRaises(CampaignMetricsError):
            other.resolve_bracket(w.admit(other), state.opaque_handle, w.p.protocol_digest, "schedule")

        scheduled = self.schedule(w, handle, state)
        advanced = self.apply(w, handle, state, w.script_direct(scheduled.receipts))
        for stale in (
            lambda: self.schedule(w, handle, state),
            lambda: w.registry.resolve_bracket(handle, state.opaque_handle, w.p.protocol_digest, "schedule"),
            lambda: self.apply(w, handle, state, w.script_direct(scheduled.receipts)),
        ):
            with self.assertRaises(CampaignMetricsError):
                stale()
        self.assertEqual(self.bracket(w, handle, advanced).round_number, 1)
        self.assertEqual(self.count(w, "consumptions"), 2)


class RecoveryAndIdentityTests(N30Base):
    def test_ambiguous_acknowledgment_recovery_is_exact_and_never_duplicates(self):
        w, handle, state = self.scheduled(outcome_dependency="direct_permitted")
        registry, p = w.registry, w.p
        receipts = self.schedule(w, handle, state).receipts
        bracket = self.bracket(w, handle, state)
        results = w.script_direct(receipts)
        transition = transition_after_round(p, bracket, results)
        request = ConsumeRoundRequest(
            bracket.admission_digest, p.protocol_digest, "original", 1,
            bracket.bracket_digest, results, transition,
        )
        bracket_id, _ = registry.state_identity(state.opaque_handle)
        digest = consume_request_digest(bracket_id, request)
        with self.assertRaises(CampaignMetricsError):
            registry.recover(handle, digest)  # nothing recorded yet
        acknowledged = registry.consume_round(handle, state.opaque_handle, request)  # ack "lost"
        recovered = registry.recover(handle, digest)
        self.assertTrue(recovered.current)
        self.assertIs(recovered.state.opaque_handle, acknowledged.opaque_handle)
        self.assertEqual(registry.recover(handle, digest).result_digest, recovered.result_digest)
        # ordinary replay from the stale handle still rejects; nothing is consumed twice
        with self.assertRaises(CampaignMetricsError):
            registry.consume_round(handle, state.opaque_handle, request)
        self.assertEqual(self.count(w, "consumptions"), 2)
        with self.assertRaises(CampaignMetricsError):
            registry.recover(handle, D)
        # after a later transition the recorded result is reported, never revived
        later = self.apply(
            w, handle, recovered.state,
            w.script_direct(self.schedule(w, handle, recovered.state).receipts),
        )
        old = registry.recover(handle, digest)
        self.assertFalse(old.current)
        self.assertIsNone(old.state)
        self.assertEqual(old.result_digest, recovered.result_digest)
        self.assertEqual(self.bracket(w, handle, later).round_number, 2)
        # recovery is authenticated: unknown status blocks it
        w.authority.state = "unknown"
        self.not_exhaustion(lambda: registry.recover(handle, digest))

    def test_conflict_idempotency_immutable_history_and_audit_only_reads(self):
        # This control submits direct evaluator outcomes, so it needs a truthful, explicit
        # SYNTHETIC reviewed remit that permits direct outcomes. The production default
        # (aggregates_required) is not weakened; tests of that gate keep the default.
        w = self.world(outcome_dependency="direct_permitted")
        handle = w.admit()
        self.assertIs(w.admit(), handle)
        self.assertEqual(self.count(w, "admissions"), 1)
        with self.assertRaises(CampaignMetricsError):  # same reference, other protocol
            w.registry.admit(replace(w.p, version="9.9.9"), "original", "admission:original")
        w.authority.records["admission:other"] = (w.evidence, w.lease)
        with self.assertRaises(N30StoreError):  # same protocol/stage/content, new identity
            w.registry.admit(w.p, "original", "admission:other")
        self.assertEqual(self.count(w, "admissions"), 1)

        w.seal_entrants(handle)
        state = w.registry.open_bracket(handle, w.p.protocol_digest, "original", "builder-component")
        again = w.registry.open_bracket(handle, w.p.protocol_digest, "original", "builder-component")
        self.assertIs(state.opaque_handle, again.opaque_handle)
        scheduled = self.schedule(w, handle, state)
        plans = tuple(r.plan for r in scheduled.receipts)
        reissued = w.registry.issue_round(handle, plans)
        self.assertEqual([r.receipt_digest for r in reissued], [r.receipt_digest for r in scheduled.receipts])
        self.assertTrue(all(a.opaque_handle is b.opaque_handle for a, b in zip(reissued, scheduled.receipts)))
        self.assertEqual(self.count(w, "issuances"), 1)
        self.apply(w, handle, state, w.script_direct(scheduled.receipts))
        with self.assertRaises(CampaignMetricsError):  # progressed history cannot be reset
            w.registry.open_bracket(handle, w.p.protocol_digest, "original", "builder-component")
        # conflicting seal identity (same sequence, other candidate) never overwrites history
        history = canonical_digest(
            w.registry.resolve(handle, AdmissionUse(w.p.protocol_digest, "original", "seal")).seal_history
        )
        clash = seal_for(w.p, w.evidence, "MB0", 4, canonical_digest("other"), 16)
        with self.assertRaises(CampaignMetricsError):
            w.registry.append_seals(handle, history, 20, (clash,))
        self.assertEqual(
            canonical_digest(
                w.registry.resolve(handle, AdmissionUse(w.p.protocol_digest, "original", "seal")).seal_history
            ),
            history,
        )
        # audit-only history is readable but is neither authority nor a handle
        audit = w.registry.audit_history()
        self.assertEqual(audit[0]["kind"], "create")
        self.assertIn("issue_round", {row["kind"] for row in audit})
        with self.assertRaises(CampaignMetricsError):
            w.registry.resolve(audit[0], AdmissionUse(w.p.protocol_digest, "original", "schedule"))
        self.assertTrue(w.registry.synthetic)
        self.assertIn(SYNTHETIC, "".join(m.review_ref for m in w.policy.mappings.values()))

    def test_recorded_results_bind_request_digests(self):
        w, handle, state = self.scheduled()
        scheduled = self.schedule(w, handle, state)
        plans = tuple(r.plan for r in scheduled.receipts)
        recovered = w.registry.recover(handle, issue_request_digest(plans))
        self.assertEqual([r.receipt_digest for r in recovered.receipts], [r.receipt_digest for r in scheduled.receipts])
        bracket = self.bracket(w, handle, state)
        bracket_id, _ = w.registry.state_identity(state.opaque_handle)
        self.assertNotEqual(
            commit_request_digest(bracket_id, bracket.bracket_digest, BracketTransition(0, {}, {}, {}, frozenset(), "one_survivor", frozenset())),
            commit_request_digest(bracket_id, bracket.bracket_digest, BracketTransition(0, {}, {}, {}, frozenset(), "max_rounds", frozenset())),
        )


class UnsupportedMappingTests(N30Base):
    def registry(self, policy, ports, manifest="default"):
        w = self.world()
        w.registry.close()
        path = w.path.with_name("blocked.sqlite")
        registry = self.track(
            N30HostRegistry.create(
                path,
                policy=policy,
                ports=ports,
                clock=w.clock,
                adapter_manifest=w.manifest if manifest == "default" else manifest,
            )
        )
        return w, registry

    def test_missing_ports_or_mappings_block_every_positive_use(self):
        w = self.world()
        authority = w.authority
        full = make_policy().mappings
        for label, policy, ports in (
            ("no ports", make_policy(), HostPorts()),
            ("no mapping", replace_policy(make_policy(), {}), HostPorts(authority, authority, authority)),
            (
                "no current mapping",
                replace_policy(make_policy(), {k: v for k, v in full.items() if k != "n30.current"}),
                HostPorts(authority, authority, authority),
            ),
        ):
            with self.subTest(label):
                _, registry = self.registry(policy, ports)
                with self.assertRaises(AuthorityBlocked):
                    registry.admit(w.p, "original", "admission:original")
        self.assertEqual(w.authority.calls, 0)

    def test_outcome_measurement_and_manifest_mappings_are_separately_required(self):
        w = self.world()
        authority = w.authority
        full = make_policy().mappings
        only_current = replace_policy(make_policy(), {"n30.current": full["n30.current"]})
        _, registry = self.registry(only_current, HostPorts(authority, None, None))
        handle = registry.admit(w.p, "original", "admission:original")
        w.seal_entrants(handle, registry)
        state = registry.open_bracket(handle, w.p.protocol_digest, "original", "builder-component")
        receipts = state.schedule(w.p, registry=registry, admission_handle=handle).receipts
        results = w.script_direct(receipts)
        with self.assertRaises(AuthorityBlocked):
            state.apply(w.p, results, registry=registry, admission_handle=handle)
        rows, values = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=0.5) for row in rows)
        with self.assertRaises(AuthorityBlocked):
            stage_paired_bootstrap(
                w.p, "success_difference", "MB0", "MB1", rows,
                left_hard_gates=True, right_hard_gates=True,
                registry=registry, admission_handle=handle,
            )
        # with ports and mappings but no admitted adapter manifest, measurement still blocks
        _, no_manifest = self.registry(make_policy(), HostPorts(authority, authority, authority), manifest=None)
        handle = no_manifest.admit(w.p, "original", "admission:original")
        w.seal_entrants(handle, no_manifest)
        with self.assertRaises(AuthorityBlocked):
            stage_paired_bootstrap(
                w.p, "success_difference", "MB0", "MB1", rows,
                left_hard_gates=True, right_hard_gates=True,
                registry=no_manifest, admission_handle=handle,
            )
        self.assertEqual(self.count_of(no_manifest, "aggregates"), 0)

    def count_of(self, registry, table):
        return registry._query(f"SELECT COUNT(*) FROM {table}")[0][0]

    def test_pilot_purposes_and_unreviewed_policy_are_rejected(self):
        with self.assertRaises(N30HostError):
            ReviewedMapping("pilot.host_lease", "pilot", "review:x", False, 60)
        with self.assertRaises(N30HostError):
            ReviewedMapping("n30.current", "m", "review:x", "yes", 60)  # type: ignore[arg-type]
        good = make_policy()
        with self.assertRaises(N30HostError):
            HostPolicy({"n30.outcome": good.mappings["n30.current"]}, good.metric_definitions, "g", "aggregates_required")
        with self.assertRaises(N30HostError):
            HostPolicy(good.mappings, {}, "g", "aggregates_required")
        with self.assertRaises(N30HostError):
            HostPolicy(good.mappings, good.metric_definitions, "g", "caller-chooses")
        with self.assertRaises(N30HostError):
            HostPolicy(good.mappings, good.metric_definitions, "g", "aggregates_required", 0)
        with self.assertRaises(N30HostError):
            HostPolicy(good.mappings, good.metric_definitions, "g", "aggregates_required", 1.0, 10**9)
        self.assertTrue(good.synthetic)
        self.assertEqual(set(good.metric_definitions), set(METRICS))


class FinalAuthorityReadTests(N30Base):
    """R1: current authority is re-read after the last provider dependency.

    Each scenario changes authority *before the last dependency returns* and alters no SQL,
    production function or receipt content (the Curator's frozen counterexamples).
    """

    NOW = 100
    TRIGGERS = {
        "revoked": lambda w: w.authority.revoke(),
        "unknown": lambda w: setattr(w.authority, "state", "unknown"),
        "unavailable": lambda w: setattr(w.authority, "unavailable", True),
        "future": lambda w: setattr(w.authority, "observed_at_override", w.clock.now + 5),
        "stale": lambda w: setattr(w.authority, "observed_at_override", w.clock.now - 60),
        "clock regressed": lambda w: setattr(w.clock, "now", w.clock.now - 1),
    }

    def assert_blocked(self, mode, action):
        if mode == "revoked":
            with self.assertRaises(LeaseExhausted):
                action()
        else:  # unknown/unavailable/stale/future/regressed are blockers, never exhaustion
            self.not_exhaustion(action)

    def consume_scenario(self, mode):
        w = self.world(now=self.NOW, outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        issued = self.schedule(w, handle, state)
        results = w.script_direct(issued.receipts)
        seen = {"calls": 0, "at_trigger": None}

        def mutator(answer):
            seen["calls"] += 1
            if seen["calls"] == len(issued.receipts) and mode is not None:
                self.TRIGGERS[mode](w)
                seen["at_trigger"] = w.authority.calls
            return answer  # the legitimate pre-change answer

        w.authority.outcome_mutator = mutator
        return w, handle, state, results, seen

    def test_consume_round_rereads_authority_after_the_last_outcome(self):
        w, handle, state, results, _ = self.consume_scenario(None)
        advanced = self.apply(w, handle, state, results)  # active control commits once
        self.assertEqual(self.count(w, "consumptions"), 2)
        self.assertEqual(self.bracket(w, handle, advanced).round_number, 1)
        for mode in self.TRIGGERS:
            with self.subTest(mode):
                w, handle, state, results, seen = self.consume_scenario(mode)
                self.assert_blocked(mode, lambda: self.apply(w, handle, state, results))
                self.assertEqual(self.count(w, "consumptions"), 0)
                self.assertEqual(self.count(w, "bracket_versions"), 1)  # still version 0
                if mode != "clock regressed":
                    # the registry really made a current-authority call after the change
                    self.assertGreater(w.authority.calls, seen["at_trigger"])

    def test_confirmed_revocation_after_last_outcome_still_permits_only_closure(self):
        w, handle, state, results, _ = self.consume_scenario("revoked")
        with self.assertRaises(LeaseExhausted):
            self.apply(w, handle, state, results)
        closed = self.apply(w, handle, state, ())
        snapshot = self.bracket(w, handle, closed)
        self.assertEqual(snapshot.terminal, "lease_exhausted")
        self.assertEqual(snapshot.round_number, 0)
        self.assertEqual(snapshot.applied_receipt_digests, frozenset())
        self.assertEqual(self.count(w, "consumptions"), 0)

    def aggregate_scenario(self, mode, *, resolve):
        w = self.world(now=self.NOW)
        handle, _ = w.prepared()
        rows, values = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=values["success_difference"]) for row in rows)

        def record():
            return stage_paired_bootstrap(
                w.p, "success_difference", "MB0", "MB1", rows,
                left_hard_gates=True, right_hard_gates=True,
                registry=w.registry, admission_handle=handle,
            )

        receipt = record() if resolve else None
        seen = {"calls": 0, "at_trigger": None}

        def mutator(answer):
            seen["calls"] += 1
            if seen["calls"] == len(rows) and mode is not None:
                self.TRIGGERS[mode](w)
                seen["at_trigger"] = w.authority.calls
            return answer

        w.authority.measurement_mutator = mutator
        if resolve:
            return w, handle, (lambda: w.registry.resolve_aggregate(handle, receipt)), seen
        return w, handle, record, seen

    def test_record_aggregate_rereads_authority_after_the_last_measurement(self):
        w, handle, action, _ = self.aggregate_scenario(None, resolve=False)
        action()  # active control persists exactly one aggregate
        self.assertEqual(self.count(w, "aggregates"), 1)
        for mode in self.TRIGGERS:
            with self.subTest(mode):
                w, handle, action, seen = self.aggregate_scenario(mode, resolve=False)
                self.assert_blocked(mode, action)
                self.assertEqual(self.count(w, "aggregates"), 0)
                self.assertEqual(self.count(w, "measurements"), 0)
                self.assertEqual(self.count(w, "aggregate_uses"), 0)
                if mode != "clock regressed":
                    self.assertGreater(w.authority.calls, seen["at_trigger"])

    def test_resolve_aggregate_rereads_authority_and_returns_no_positive_evidence(self):
        w, handle, action, _ = self.aggregate_scenario(None, resolve=True)
        self.assertEqual(action().metric, "success_difference")
        for mode in self.TRIGGERS:
            with self.subTest(mode):
                w, handle, action, seen = self.aggregate_scenario(mode, resolve=True)
                self.assert_blocked(mode, action)
                self.assertEqual(self.count(w, "aggregates"), 1)  # recorded evidence unchanged
                if mode != "clock regressed":
                    self.assertGreater(w.authority.calls, seen["at_trigger"])

    def test_every_positive_entry_blocks_after_confirmed_revocation(self):
        w = self.world(now=self.NOW, outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        registry, p = w.registry, w.p
        pd = p.protocol_digest
        scheduled = self.schedule(w, handle, state)
        plans = tuple(receipt.plan for receipt in scheduled.receipts)
        rows, values = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=0.5) for row in rows)
        snapshot = registry.resolve(handle, AdmissionUse(pd, "original", "aggregate"))
        evidence = build_aggregate_evidence(
            p, snapshot, "success_difference", "MB0", "MB1", rows,
            left_hard_gates=True, right_hard_gates=True,
        )
        receipt = registry.record_aggregate(handle, evidence, rows)
        bracket = self.bracket(w, handle, state)
        outcomes = w.script_direct(scheduled.receipts)
        request = ConsumeRoundRequest(
            bracket.admission_digest, pd, "original", 1, bracket.bracket_digest,
            outcomes, transition_after_round(p, bracket, outcomes),
        )
        history = canonical_digest(
            registry.resolve(handle, AdmissionUse(pd, "original", "seal")).seal_history
        )
        seal = seal_for(p, w.evidence, "MC0", 5, canonical_digest("candidate-MC0"), 15)
        one_survivor = BracketTransition(0, {}, {}, {}, frozenset(), "one_survivor", frozenset())
        aggregates = self.count(w, "aggregates")
        seals = self.count(w, "seals")

        w.authority.revoke()
        for label, call in (
            ("resolve", lambda: registry.resolve(handle, AdmissionUse(pd, "original", "schedule"))),
            ("open_bracket", lambda: registry.open_bracket(handle, pd, "original", "builder-component")),
            ("issue_round", lambda: registry.issue_round(handle, plans)),
            ("consume_round", lambda: registry.consume_round(handle, state.opaque_handle, request)),
            ("commit_bracket", lambda: registry.commit_bracket(handle, state.opaque_handle, bracket.bracket_digest, one_survivor)),
            ("append_seals", lambda: registry.append_seals(handle, history, self.NOW, (seal,))),
            ("record_aggregate", lambda: registry.record_aggregate(handle, evidence, rows)),
            ("resolve_aggregate", lambda: registry.resolve_aggregate(handle, receipt)),
        ):
            with self.subTest(label):
                with self.assertRaises(LeaseExhausted):
                    call()
        # authenticated history stays readable for closure only
        self.assertIsNone(registry.resolve_bracket(handle, state.opaque_handle, pd, "schedule").terminal)
        # positive recoveries return the immutable record but no usable receipts/aggregate
        recovered = registry.recover(handle, issue_request_digest(plans))
        self.assertFalse(recovered.current)
        self.assertEqual(recovered.receipts, ())
        again = registry.recover(handle, aggregate_request_digest(evidence, rows))
        self.assertFalse(again.current)
        self.assertIsNone(again.aggregate)
        self.assertEqual(self.count(w, "consumptions"), 0)
        self.assertEqual(self.count(w, "aggregates"), aggregates)
        self.assertEqual(self.count(w, "seals"), seals)


class LateTerminalClosureTests(N30Base):
    """R2: confirmed exhaustion during the ordinary terminal commit closes the bracket."""

    def reach_one_survivor(self):
        w = self.world(outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        rounds = 0
        while True:
            bracket = self.bracket(w, handle, state)
            admission = w.registry.resolve(
                handle, AdmissionUse(w.p.protocol_digest, "original", "schedule")
            )
            terminal, _ = plan_next_round(w.p, bracket, admission)
            if terminal is not None:
                break
            scheduled = self.schedule(w, handle, state)
            state = self.apply(w, handle, state, w.script_direct(scheduled.receipts, "LEFT"))
            rounds += 1
            self.assertLess(rounds, 30)
        self.assertEqual((rounds, terminal), (7, "one_survivor"))  # the frozen seven-round input
        return w, handle, state

    def test_schedule_and_empty_apply_close_when_revoked_at_terminal_commit(self):
        # schedule: resolve_bracket, _resolve, then the terminal commit authorizes (3rd call);
        # apply(()) makes two more calls first (snapshot for apply) before that terminal commit.
        for label, offset, act in (
            ("schedule", 3, lambda w, h, s: self.schedule(w, h, s)),
            ("empty apply", 5, lambda w, h, s: self.apply(w, h, s, ())),
        ):
            with self.subTest(label):
                w, handle, state = self.reach_one_survivor()
                before = self.bracket(w, handle, state)
                versions = self.count(w, "bracket_versions")
                w.authority.flip_at = w.authority.calls + offset
                outcome = act(w, handle, state)
                closed = outcome.state if label == "schedule" else outcome
                if label == "schedule":
                    self.assertEqual((outcome.terminal, outcome.receipts), ("lease_exhausted", ()))
                after = self.bracket(w, handle, closed)
                self.assertEqual(after.terminal, "lease_exhausted")
                self.assertEqual(dict(after.losses), dict(before.losses))
                self.assertEqual(after.quarantined, before.quarantined)
                self.assertEqual(after.applied_receipt_digests, before.applied_receipt_digests)
                self.assertEqual(after.round_number, before.round_number)
                self.assertEqual(self.count(w, "bracket_versions"), versions + 1)

    def test_unknown_authority_at_terminal_commit_stays_an_error(self):
        w, handle, state = self.reach_one_survivor()
        w.authority.flip_action = lambda: setattr(w.authority, "state", "unknown")
        w.authority.flip_at = w.authority.calls + 3
        self.not_exhaustion(lambda: self.schedule(w, handle, state))
        self.assertIsNone(self.bracket_terminal(w, handle, state))

    def bracket_terminal(self, w, handle, state):
        w.authority.state = "active"
        return self.bracket(w, handle, state).terminal

    def test_previous_terminal_is_never_relabelled_and_direct_positive_commit_rejects(self):
        w, handle, state = self.reach_one_survivor()
        done = self.schedule(w, handle, state)
        self.assertEqual(done.terminal, "one_survivor")
        w.authority.revoke()
        again = self.schedule(w, handle, done.state)
        self.assertEqual(again.terminal, "one_survivor")  # recorded reason preserved
        self.assertIs(again.state, done.state)
        bracket = self.bracket(w, handle, done.state)
        with self.assertRaises(CampaignMetricsError):
            w.registry.commit_bracket(
                handle, done.state.opaque_handle, bracket.bracket_digest,
                BracketTransition(
                    bracket.round_number, bracket.losses, bracket.byes, bracket.inconclusive,
                    bracket.quarantined, "lease_exhausted", bracket.applied_receipt_digests,
                ),
            )


def replace_policy(policy, mappings):
    return HostPolicy(
        mappings,
        policy.metric_definitions,
        policy.gate_definition,
        policy.outcome_dependency,
        policy.provider_timeout_seconds,
        policy.busy_timeout_ms,
    )


if __name__ == "__main__":
    unittest.main()
