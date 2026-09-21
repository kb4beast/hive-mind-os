"""R4: the trusted, read-only, self-bounded provider lifecycle (ADR-094).

These tests qualify *cooperative* behaviour only: deadlines/limits are passed, one call is in
flight, a timeout poisons the instance, late answers earn nothing, close reports outstanding
work honestly, and a same-store reopen cannot create another worker while one persists.

They do NOT show that a noncooperative provider can be stopped. It cannot: the retained
``test_noncooperative_provider_still_blocks_process_exit`` control documents the current
expected limitation (the Curator's original watchdog result, unchanged in kind). Absolute
termination needs an externally supervised process boundary with kill/reap custody, which is
a DEPLOYMENT BLOCKER this repository does not supply.
"""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.campaign_metrics import (
    AdmissionSnapshot,
    AdmissionUse,
    CampaignMetricsError,
    canonical_digest,
    stage_paired_bootstrap,
)
from hive_mind_os.n30_host_registry import (
    AuthorityBlocked,
    HostPorts,
    N30HostRegistry,
    PortLimits,
    issue_request_digest,
)
from tests.n30_synthetic import ADAPTER_ID, QUALIFICATION_REF
from tests.test_n30_host_registry import N30Base, replace_policy

ROOT = Path(__file__).resolve().parents[1]
D = canonical_digest("lifecycle")

CHILD = r"""
import json
import sys
import threading
import time

from tests.n30_synthetic import World

mode, directory = sys.argv[1], sys.argv[2]
w = World(directory, provider_timeout=0.05)
event = threading.Event()
original = w.authority.current


def inert_blocked(*args):
    event.wait()
    return original(*args)


w.authority.current = inert_blocked
observations = []
for _ in range(5):
    start = time.monotonic()
    try:
        w.admit()
        result = "UNEXPECTED_POSITIVE"
    except Exception as error:
        result = type(error).__name__ + ": " + str(error)
    observations.append({"result": result, "caller_seconds": time.monotonic() - start})
report = w.registry.close()
print(
    json.dumps(
        {
            "calls": observations,
            "outstanding": report.outstanding_provider_calls,
            "poisoned": report.poisoned,
            "alive": [t.name for t in threading.enumerate() if t.name.startswith("n30-port")],
        }
    ),
    flush=True,
)
if mode == "release":
    event.set()
print("MAIN_REACHED_END", flush=True)
"""


class Gate:
    """A provider hook that blocks until released; always released on cleanup."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, port, deadline, limits):
        self.entered.set()
        self.release.wait(30)


def raw_counts(path, *tables):
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
    finally:
        connection.close()


class ProviderContractTests(N30Base):
    def test_ports_receive_absolute_deadline_limits_and_the_reviewed_adapter_pin(self):
        w = self.world(max_response_bytes=123456)
        before = time.monotonic()
        w.admit()
        after = time.monotonic()
        port, deadline, limits = w.authority.seen[-1]
        self.assertEqual(port, "current")
        self.assertEqual(limits, PortLimits(123456, 90))
        # an absolute monotonic instant, one reviewed timeout after the call started
        self.assertGreaterEqual(deadline, before + 2.0)
        self.assertLessEqual(deadline, after + 2.0)

    def test_unqualified_or_mismatched_adapters_block_before_any_provider_call(self):
        w = self.world()
        w.registry.close()
        authority = w.authority
        mapping = w.policy.mappings["n30.current"]

        class Bare:
            bounded = True  # a caller-set flag is not a qualification

            def current(self, *args):
                return authority.current(*args)

        variants = {
            "no adapter pin": (replace(mapping, adapter_id=None, qualification_ref=None), authority),
            "no qualification": (replace(mapping, qualification_ref=None), authority),
            "other adapter": (replace(mapping, adapter_id="adapter:other"), authority),
            "other qualification": (replace(mapping, qualification_ref="qualification:other"), authority),
            "port without declared pin": (mapping, Bare()),
        }
        for index, (label, (changed, port)) in enumerate(variants.items()):
            with self.subTest(label):
                policy = replace_policy(w.policy, {**w.policy.mappings, "n30.current": changed})
                registry = self.track(
                    N30HostRegistry.create(
                        w.path.with_name(f"unqualified-{index}.sqlite"),
                        policy=policy,
                        ports=HostPorts(port, authority, authority),
                        clock=w.clock,
                        adapter_manifest=w.manifest,
                    )
                )
                with self.assertRaises(AuthorityBlocked):
                    registry.admit(w.p, "original", "admission:original")
        self.assertEqual(authority.seen, [])
        self.assertEqual((mapping.adapter_id, mapping.qualification_ref), (ADAPTER_ID, QUALIFICATION_REF))

    def test_answer_shape_and_size_are_checked_before_anything_is_persisted(self):
        w = self.world(max_response_bytes=200)
        with self.assertRaises(AuthorityBlocked):  # oversized against the reviewed byte limit
            w.admit()
        self.assertEqual(self.count(w, "admissions"), 0)

        w = self.world()
        original = w.authority.current

        def returns_object(*args):
            return object()

        def many_issuers(*args):
            evidence = original(*args)
            return replace(
                evidence,
                trusted_lease_issuers=frozenset(f"host:{i}" for i in range(65)),
            )

        for label, port in (("wrong type", returns_object), ("too many issuers", many_issuers)):
            with self.subTest(label):
                w.authority.current = port
                with self.assertRaises(AuthorityBlocked):
                    w.admit()
                self.assertEqual(self.count(w, "admissions"), 0)
        w.authority.current = original
        handle = w.admit()
        w.seal_entrants(handle)
        rows, values = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=0.5) for row in rows)

        def record():
            return stage_paired_bootstrap(
                w.p, "success_difference", "MB0", "MB1", rows,
                left_hard_gates=True, right_hard_gates=True,
                registry=w.registry, admission_handle=handle,
            )

        def too_many_values(measured):
            return replace(measured, values={f"m{i}": 1.0 for i in range(7)})

        def not_finite(measured):
            return replace(measured, values={**measured.values, "success_difference": float("nan")})

        for label, mutator in (("too many values", too_many_values), ("non-finite", not_finite)):
            with self.subTest(label):
                w.authority.measurement_mutator = mutator
                with self.assertRaises(AuthorityBlocked):
                    record()
                self.assertEqual(self.count(w, "measurements"), 0)
                self.assertEqual(self.count(w, "aggregates"), 0)
        w.authority.measurement_mutator = None
        record()
        self.assertEqual(self.count(w, "aggregates"), 1)

    def test_outcome_answer_with_excess_dependencies_is_refused_before_consumption(self):
        w = self.world(outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        scheduled = self.schedule(w, handle, state)
        results = w.script_direct(scheduled.receipts)

        def too_many(outcome):
            return replace(outcome, aggregate_digests=(D, D, D, D))

        w.authority.outcome_mutator = too_many
        with self.assertRaises(AuthorityBlocked):
            self.apply(w, handle, state, results)
        self.assertEqual(self.count(w, "consumptions"), 0)


class ProviderLifecycleTests(N30Base):
    def gated(self, w):
        gate = Gate()
        self.addCleanup(gate.release.set)
        w.authority.on_call = gate
        return gate

    def wait_released(self, registry, seconds=15.0):
        limit = time.monotonic() + seconds
        while time.monotonic() < limit:
            report = registry.close()
            if not report.provider_work_outstanding:
                return report
            time.sleep(0.02)
        self.fail("abandoned provider work did not end")

    def alias_paths(self, w):
        yield os.path.join(str(w.directory), ".", "n30.sqlite")
        yield os.path.join(str(w.directory), "..", w.directory.name, "n30.sqlite")
        if os.name == "nt":
            yield str(w.path).upper()

    def open_path(self, w, path):
        return N30HostRegistry.open(
            path,
            policy=w.policy,
            ports=HostPorts(w.authority, w.authority, w.authority),
            clock=w.clock,
            adapter_manifest=w.manifest,
        )

    def test_timeout_poisons_the_instance_and_a_late_valid_answer_earns_nothing(self):
        w = self.world(provider_timeout=0.2)
        handle = w.admit()
        registry = w.registry
        tables = ("audit", "status_observations", "admissions", "bracket_versions")
        baseline = raw_counts(w.path, *tables)
        gate = self.gated(w)
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")

        with self.assertRaises(AuthorityBlocked) as caught:
            registry.resolve(handle, use)
        self.assertIn("deadline", str(caught.exception))
        self.assertTrue(gate.entered.is_set())
        provider_calls = len(w.authority.seen)
        for label, attempt in (
            ("resolve", lambda: registry.resolve(handle, use)),
            ("open_bracket", lambda: registry.open_bracket(handle, w.p.protocol_digest, "original", "builder-component")),
            ("admit", lambda: registry.admit(w.p, "original", "admission:original")),
        ):
            with self.subTest(label):
                with self.assertRaises(AuthorityBlocked) as poisoned:
                    attempt()
                self.assertIn("poisoned", str(poisoned.exception))
        self.assertEqual(len(w.authority.seen), provider_calls)  # nothing reached the provider

        # reopening the same store (normalized aliases too) cannot create another worker
        with self.assertRaises(AuthorityBlocked):
            self.open_path(w, w.path)
        for alias in self.alias_paths(w):
            with self.subTest(alias=alias):
                with self.assertRaises(AuthorityBlocked):
                    self.open_path(w, alias)

        report = registry.close()
        self.assertFalse(report.already_closed)
        self.assertEqual(report.outstanding_provider_calls, 1)
        self.assertTrue(report.provider_work_outstanding)
        self.assertIsNotNone(report.poisoned)
        again = registry.close()  # idempotent, and still honest about the running worker
        self.assertTrue(again.already_closed)
        self.assertEqual(again.outstanding_provider_calls, 1)
        with self.assertRaises(AuthorityBlocked):  # closing does not release the guard
            self.open_path(w, w.path)

        gate.release.set()  # the worker now returns a perfectly valid answer, too late
        released = self.wait_released(registry)
        self.assertIsNotNone(released.poisoned)
        self.assertEqual(raw_counts(w.path, *tables), baseline)  # no late authority credit
        with self.assertRaises(AuthorityBlocked):  # the poisoned instance stays unusable
            registry.resolve(handle, use)
        fresh = self.track(self.open_path(w, w.path))  # allowed once the worker actually ended
        self.assertIsInstance(fresh.resolve(w.admit(fresh), use), AdmissionSnapshot)

    def test_an_answer_that_arrives_after_the_deadline_is_discarded_even_if_valid(self):
        w = self.world(provider_timeout=0.2)
        handle = w.admit()
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")

        def slightly_late(port, deadline, limits):
            time.sleep(max(0.0, deadline - time.monotonic()) + 0.15)

        w.authority.on_call = slightly_late
        baseline = raw_counts(w.path, "status_observations", "audit")
        with self.assertRaises(AuthorityBlocked) as caught:
            w.registry.resolve(handle, use)
        self.assertIn("deadline", str(caught.exception))
        with self.assertRaises(AuthorityBlocked):
            w.registry.resolve(handle, use)
        self.wait_released(w.registry)
        self.assertEqual(raw_counts(w.path, "status_observations", "audit"), baseline)

    def test_a_single_call_is_in_flight_and_there_is_no_backlog(self):
        w = self.world(provider_timeout=10.0)
        handle = w.admit()
        registry = w.registry
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")
        gate = self.gated(w)
        outcome = {}

        def first():
            try:
                outcome["value"] = registry.resolve(handle, use)
            except BaseException as error:  # reported by the assertions below
                outcome["value"] = error

        worker = threading.Thread(target=first)
        worker.start()
        self.assertTrue(gate.entered.wait(10))
        started = time.monotonic()
        with self.assertRaises(AuthorityBlocked) as caught:  # a concurrent submission
            registry.resolve(handle, use)
        self.assertLess(time.monotonic() - started, 2.0)  # refused at once, never queued
        self.assertIn("in flight", str(caught.exception))
        self.assertEqual(len(w.authority.seen), 2)  # the enrolment call and the one in flight
        gate.release.set()
        worker.join(15)
        self.assertIsInstance(outcome["value"], AdmissionSnapshot)  # the in-flight call is intact
        self.assertIsInstance(registry.resolve(handle, use), AdmissionSnapshot)
        self.assertIsNone(registry.close().poisoned)

    def test_close_during_a_call_reports_outstanding_work_and_grants_no_credit(self):
        w = self.world(provider_timeout=10.0)
        handle = w.admit()
        registry = w.registry
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")
        tables = ("audit", "status_observations")
        baseline = raw_counts(w.path, *tables)
        gate = self.gated(w)
        outcome = {}

        def call():
            try:
                outcome["value"] = registry.resolve(handle, use)
            except BaseException as error:
                outcome["value"] = error

        worker = threading.Thread(target=call)
        worker.start()
        self.assertTrue(gate.entered.wait(10))
        report = registry.close()
        self.assertFalse(report.already_closed)
        self.assertTrue(report.provider_work_outstanding)
        with self.assertRaises(AuthorityBlocked):  # the store guard still refuses a reopen
            self.open_path(w, w.path)
        gate.release.set()
        worker.join(15)
        self.assertIsInstance(outcome["value"], AuthorityBlocked)  # no positive result
        self.wait_released(registry)
        self.assertEqual(raw_counts(w.path, *tables), baseline)
        self.track(self.open_path(w, w.path))  # allowed only after the worker really ended

    def test_provider_exceptions_are_typed_release_the_thread_and_do_not_poison(self):
        w = self.world()
        handle = w.admit()
        registry = w.registry
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")

        class Fatal(BaseException):
            pass

        def raise_runtime(port, deadline, limits):
            raise RuntimeError("provider failed")

        def raise_typed(port, deadline, limits):
            raise CampaignMetricsError("provider refused")

        def raise_fatal(port, deadline, limits):
            raise Fatal()

        for label, hook in (("runtime", raise_runtime), ("fatal", raise_fatal)):
            with self.subTest(label):
                w.authority.on_call = hook
                with self.assertRaises(AuthorityBlocked):
                    registry.resolve(handle, use)
        w.authority.on_call = raise_typed
        with self.assertRaises(CampaignMetricsError) as typed:
            registry.resolve(handle, use)
        self.assertNotIsInstance(typed.exception, AuthorityBlocked)
        w.authority.on_call = None
        self.assertIsInstance(registry.resolve(handle, use), AdmissionSnapshot)  # not poisoned
        limit = time.monotonic() + 5
        while time.monotonic() < limit and any(
            t.name.startswith("n30-port") and t.is_alive() for t in threading.enumerate()
        ):
            time.sleep(0.02)
        self.assertFalse(
            any(t.name.startswith("n30-port") and t.is_alive() for t in threading.enumerate())
        )
        self.assertIsNone(registry.close().poisoned)

    def test_a_cooperative_adapter_that_honours_its_deadline_recovers_without_poison(self):
        w = self.world(provider_timeout=0.4)
        handle = w.admit()
        registry = w.registry
        use = AdmissionUse(w.p.protocol_digest, "original", "schedule")
        release = threading.Event()

        def cooperative(port, deadline, limits):
            # a reviewed adapter bounds its own wait and releases before the host's deadline
            if not release.wait(max(0.0, deadline - time.monotonic() - 0.1)):
                raise TimeoutError("adapter reached its own deadline")

        w.authority.on_call = cooperative
        with self.assertRaises(AuthorityBlocked):
            registry.resolve(handle, use)
        self.assertEqual(registry._guard.live(), [])  # released in time: nothing left running
        release.set()
        self.assertIsInstance(registry.resolve(handle, use), AdmissionSnapshot)  # recovered
        self.assertIsNone(registry.close().poisoned)


class PoisonLinearizationTests(N30Base):
    """Second remand: poison/close linearize against every positive commit/return, and
    ownership of an abandoned worker is published atomically (no same-store handoff gap).

    The pause points are the Curator's unchanged probe inputs
    (``probe_poison_interleavings_v2.py``): a barrier after the unmodified ``_final_read``
    returns, and a barrier before the original ``_guard.adopt``. No answer, SQL or guard
    value is replaced. Events make the interleavings deterministic.

    Semantics: a write transaction holds the instance lifecycle lock from its poison/close
    check through COMMIT, and poison publication takes the same lock, so they are totally
    ordered; a read-only positive return is linearized at a final ``_ensure_live`` check.
    An operation paused before poison therefore gets a typed refusal, never positive credit.
    """

    def use(self, w):
        return AdmissionUse(w.p.protocol_digest, "original", "schedule")

    def blocker(self, w):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def block(port, deadline, limits):
            entered.set()
            release.wait(10)

        w.authority.on_call = block
        return entered, release

    def capture(self, function, output):
        try:
            output["value"] = function()
        except BaseException as error:
            output["value"] = error

    def wait_released(self, registry, seconds=15.0):
        limit = time.monotonic() + seconds
        while time.monotonic() < limit:
            if not registry.close().provider_work_outstanding:
                return
            time.sleep(0.02)
        self.fail("abandoned provider work did not end")

    def test_record_aggregate_paused_after_final_read_cannot_commit_after_poison(self):
        w = self.world(provider_timeout=0.2)
        handle, _ = w.prepared()
        rows, _ = w.measure_pair("MB0", "MB1", success=0.5)
        rows = tuple(replace(row, value=0.5) for row in rows)
        final_done, resume = threading.Event(), threading.Event()
        self.addCleanup(resume.set)
        original = w.registry._final_read

        def paused_final(*args, **kwargs):
            result = original(*args, **kwargs)  # the unmodified final read returns first
            final_done.set()
            resume.wait(10)
            return result

        w.registry._final_read = paused_final
        outcome = {}

        def record():
            return stage_paired_bootstrap(
                w.p, "success_difference", "MB0", "MB1", rows,
                left_hard_gates=True, right_hard_gates=True,
                registry=w.registry, admission_handle=handle,
            )

        worker = threading.Thread(target=self.capture, args=(record, outcome))
        worker.start()
        self.assertTrue(final_done.wait(15))
        entered, _ = self.blocker(w)
        with self.assertRaises(AuthorityBlocked):  # a second public call times out and poisons
            w.registry.resolve(handle, self.use(w))
        self.assertTrue(entered.is_set())
        self.assertIsNotNone(w.registry._poison)
        resume.set()
        worker.join(15)
        self.assertIsInstance(outcome["value"], AuthorityBlocked)
        self.assertIn("poison", str(outcome["value"]))
        self.assertEqual(self.count(w, "aggregates"), 0)
        self.assertEqual(self.count(w, "measurements"), 0)
        self.assertEqual(self.count(w, "aggregate_uses"), 0)

    def test_consume_round_paused_after_final_read_cannot_commit_after_poison(self):
        w = self.world(provider_timeout=0.2, outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        results = w.script_direct(self.schedule(w, handle, state).receipts)
        final_done, resume = threading.Event(), threading.Event()
        self.addCleanup(resume.set)
        original = w.registry._final_read

        def paused_final(*args, **kwargs):
            result = original(*args, **kwargs)
            final_done.set()
            resume.wait(10)
            return result

        w.registry._final_read = paused_final
        outcome = {}
        worker = threading.Thread(
            target=self.capture, args=(lambda: self.apply(w, handle, state, results), outcome)
        )
        worker.start()
        self.assertTrue(final_done.wait(15))
        self.blocker(w)
        with self.assertRaises(AuthorityBlocked):
            w.registry.resolve(handle, self.use(w))
        resume.set()
        worker.join(15)
        self.assertIsInstance(outcome["value"], AuthorityBlocked)
        self.assertEqual(self.count(w, "consumptions"), 0)
        self.assertEqual(self.count(w, "bracket_versions"), 1)

    def test_read_only_positive_returns_are_linearized_with_poison(self):
        for label in ("resolve", "resolve_bracket", "recover_bracket", "recover", "admit"):
            with self.subTest(label):
                w = self.world(provider_timeout=0.2)
                handle, state = w.prepared()
                plans = tuple(r.plan for r in self.schedule(w, handle, state).receipts)
                pd = w.p.protocol_digest
                calls = {
                    "resolve": lambda: w.registry.resolve(handle, self.use(w)),
                    "resolve_bracket": lambda: w.registry.resolve_bracket(
                        handle, state.opaque_handle, pd, "schedule"
                    ),
                    "recover_bracket": lambda: w.registry.recover_bracket(
                        handle, pd, "original", "builder-component"
                    ),
                    "recover": lambda: w.registry.recover(handle, issue_request_digest(plans)),
                    "admit": lambda: w.registry.admit(w.p, "original", "admission:original"),
                }
                paused, resume = threading.Event(), threading.Event()
                self.addCleanup(resume.set)
                original = w.registry._authorize

                def after_authorize(*args, _original=original, **kwargs):
                    result = _original(*args, **kwargs)
                    if threading.current_thread().name == "paused-first":
                        paused.set()
                        resume.wait(10)
                    return result

                w.registry._authorize = after_authorize
                outcome = {}
                worker = threading.Thread(
                    name="paused-first", target=self.capture, args=(calls[label], outcome)
                )
                worker.start()
                self.assertTrue(paused.wait(15))
                self.blocker(w)
                with self.assertRaises(AuthorityBlocked):
                    w.registry.resolve(handle, self.use(w))  # times out: instance poisoned
                resume.set()
                worker.join(15)
                self.assertIsInstance(outcome["value"], AuthorityBlocked, label)
                self.assertIn("poison", str(outcome["value"]))

    def test_same_store_reopen_and_siblings_are_refused_during_the_ownership_handoff(self):
        w = self.world(provider_timeout=0.2)
        handle = w.admit()
        sibling = self.track(w.open_registry())  # a legitimate second instance, opened first
        sibling_handle = w.admit(sibling)
        handoff, allow_adopt = threading.Event(), threading.Event()
        self.addCleanup(allow_adopt.set)
        original_adopt = w.registry._guard.adopt

        def paused_adopt(call):
            handoff.set()  # the timeout/poison decision is made; adoption is paused
            allow_adopt.wait(10)
            return original_adopt(call)

        w.registry._guard.adopt = paused_adopt
        entered, release = self.blocker(w)
        started = len(w.authority.seen)
        outcome = {}
        worker = threading.Thread(
            target=self.capture,
            args=(lambda: w.registry.resolve(handle, self.use(w)), outcome),
        )
        worker.start()
        self.assertTrue(entered.wait(10))
        self.assertTrue(handoff.wait(10))
        alias = w.directory / "alias-link.sqlite"
        try:
            os.link(w.path, alias)
        except OSError:
            alias = None  # hard links unsupported here; path aliases below still run
        candidates = [w.path, *[Path(p) for p in self.alias_paths(w)]] + ([alias] if alias else [])
        for path in candidates:  # public same-store open during the gap
            with self.subTest(path=str(path)):
                with self.assertRaises(AuthorityBlocked):
                    N30HostRegistry.open(
                        path,
                        policy=w.policy,
                        ports=HostPorts(w.authority, w.authority, w.authority),
                        clock=w.clock,
                        adapter_manifest=w.manifest,
                    )
        with self.assertRaises(AuthorityBlocked):  # an existing sibling instance
            sibling.resolve(sibling_handle, self.use(w))
        self.assertEqual(len(w.authority.seen), started + 1)  # exactly one worker ever started
        allow_adopt.set()
        worker.join(10)
        self.assertIsInstance(outcome["value"], AuthorityBlocked)
        self.assertEqual(len(w.registry._guard.live()), 1)  # first worker still outstanding
        release.set()
        self.wait_released(w.registry)
        fresh = self.track(w.open_registry())  # a legitimate reopen after actual release
        self.assertIsInstance(fresh.resolve(w.admit(fresh), self.use(w)), AdmissionSnapshot)

    def alias_paths(self, w):
        yield os.path.join(str(w.directory), ".", "n30.sqlite")
        yield os.path.join(str(w.directory), "..", w.directory.name, "n30.sqlite")

    def test_close_during_a_call_publishes_ownership_to_siblings_at_once(self):
        w = self.world(provider_timeout=10.0)
        handle = w.admit()
        sibling = self.track(w.open_registry())
        sibling_handle = w.admit(sibling)
        entered, release = self.blocker(w)
        started = len(w.authority.seen)
        worker = threading.Thread(
            target=self.capture, args=(lambda: w.registry.resolve(handle, self.use(w)), {})
        )
        worker.start()
        self.assertTrue(entered.wait(10))
        self.assertTrue(w.registry.close().provider_work_outstanding)
        with self.assertRaises(AuthorityBlocked):
            sibling.resolve(sibling_handle, self.use(w))
        with self.assertRaises(AuthorityBlocked):
            w.open_registry()
        self.assertEqual(len(w.authority.seen), started + 1)
        release.set()
        worker.join(15)
        self.wait_released(w.registry)
        self.assertIsInstance(sibling.resolve(sibling_handle, self.use(w)), AdmissionSnapshot)


class ProcessExitTests(N30Base):
    def run_child(self, mode, directory):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (str(ROOT / "src"), str(ROOT), environment.get("PYTHONPATH", "")))
        )
        process = subprocess.Popen(
            [sys.executable, "-c", CHILD, mode, str(directory)],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines = []
        marker_at = None
        limit = time.monotonic() + 90
        while time.monotonic() < limit:
            line = process.stdout.readline()
            if not line:
                break
            lines.append(line)
            if "MAIN_REACHED_END" in line:
                marker_at = time.monotonic()
                break
        self.assertIsNotNone(marker_at, "".join(lines))
        try:
            code = process.wait(timeout=2.0)  # generous, but bounded, exit window
            killed = False
        except subprocess.TimeoutExpired:
            process.kill()  # only this exact child; the watchdog is the test's, not the registry's
            code = process.wait(timeout=10)
            killed = True
        lines.extend(process.stdout.readlines())
        process.stdout.close()
        return code, killed, lines

    @staticmethod
    def details(lines):
        return json.loads(next(line for line in lines if line.startswith("{")))

    def test_cooperative_release_lets_the_process_exit_with_one_bounded_worker(self):
        directory = Path(self._tmp.name) / "cooperative"
        directory.mkdir()
        code, killed, lines = self.run_child("release", directory)
        self.assertFalse(killed, "".join(lines))
        self.assertEqual(code, 0)
        details = self.details(lines)
        self.assertEqual(len(details["alive"]), 1)  # one worker, not a pool of four
        self.assertEqual(details["outstanding"], 1)
        self.assertIsNotNone(details["poisoned"])
        self.assertIn("deadline", details["calls"][0]["result"])
        for call in details["calls"][1:]:  # poisoned: refused at once, no new worker
            self.assertIn("poisoned", call["result"])
            self.assertLess(call["caller_seconds"], 1.0)

    def test_noncooperative_provider_still_blocks_process_exit(self):
        """Retained negative control: the original watchdog failure is *expected* to remain.

        A noncooperative provider never returns, its thread is deliberately non-daemon and
        Future.cancel/daemonization would only hide it, so the interpreter cannot exit. The
        registry reports the outstanding worker honestly; stopping it is an external
        process-boundary obligation (deployment blocker), not something this adapter does.
        """
        directory = Path(self._tmp.name) / "noncooperative"
        directory.mkdir()
        code, killed, lines = self.run_child("noncooperative", directory)
        self.assertTrue(killed, "the noncooperative worker unexpectedly let the process exit")
        details = self.details(lines)
        self.assertEqual(details["outstanding"], 1)
        self.assertEqual(len(details["alive"]), 1)
        self.assertTrue(any("MAIN_REACHED_END" in line for line in lines))
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
