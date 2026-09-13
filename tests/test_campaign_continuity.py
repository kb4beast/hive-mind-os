"""Opt-in continuity acceptance cases; execution receipts belong to qualification."""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.campaign_continuity import (
    AuthorityObservation,
    CampaignCandidate,
    CampaignContinuityController,
    CompletedDelivery,
    ContinuityError,
    ContinuityScope,
    EvidenceReference,
    LaunchReceipt,
    LaunchStatus,
    Phase,
    RepositorySubject,
)


def digest(character):
    return "sha256:" + character * 64


class MemoryAdapter:
    """Test double only; no independent observation or real launch authority."""

    def __init__(self):
        self.operations = {}
        self.observations = 0
        self.inspections = []
        self.launches = []
        self.observation_changes = {}
        self.inspect_status = LaunchStatus.ABSENT
        self.launch_status = LaunchStatus.STARTED
        self.raise_after_effect = False
        self.raise_before_effect = False

    def observe(self, scope, required_evidence):
        self.observations += 1
        observation = AuthorityObservation(
            scope.subject, scope.scope_digest, scope.authority_digest, scope.owner_id,
            "independent-observer", 100, True, required_evidence,
            EvidenceReference("receipt:authority-observation", digest("e")),
        )
        return replace(observation, **self.observation_changes)

    def receipt(self, operation_id, candidate, status, *, authoritative=True):
        return LaunchReceipt(operation_id, candidate.version_digest, status, authoritative,
                             EvidenceReference("receipt:" + status.value, digest("f")))

    def inspect(self, operation_id, candidate):
        self.inspections.append(operation_id)
        status = LaunchStatus.STARTED if operation_id in self.operations else self.inspect_status
        return self.receipt(operation_id, candidate, status)

    def launch(self, operation_id, candidate, scope):
        self.launches.append(operation_id)
        if self.raise_before_effect:
            raise SystemExit("interrupted after durable intent, before effect")
        if self.launch_status == LaunchStatus.STARTED:
            self.operations.setdefault(operation_id, candidate.version_digest)
        if self.raise_after_effect:
            raise OSError("response lost after external side effect")
        return self.receipt(operation_id, candidate, self.launch_status)


def _hold_transaction(root, scope, entered, release, results):
    """Spawn-compatible cooperating writer, also exercises native Windows locking."""
    controller = CampaignContinuityController(root, scope, clock=lambda: 100)

    class HeldAdapter(MemoryAdapter):
        def observe(self, scope, required_evidence):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test release timed out")
            return super().observe(scope, required_evidence)

    adapter = HeldAdapter()
    state = controller.step(adapter)
    results.put((state["phase"], len(adapter.launches)))


def _compete_transaction(root, scope, results):
    try:
        CampaignContinuityController(root, scope, clock=lambda: 100)
    except ContinuityError as error:
        results.put(error.code)
    else:
        results.put("unexpected-lock-acquisition")


def _hold_after_launch_intent(root, scope, effect_path, after_effect, entered):
    """Kill fixture: retained intent, optional durable synthetic effect, no real work."""
    class HeldLaunchAdapter(MemoryAdapter):
        def launch(self, operation_id, candidate, scope):
            if after_effect:
                with Path(effect_path).open("wb") as handle:
                    handle.write(json.dumps({"operation_id": operation_id,
                                             "candidate_digest": candidate.version_digest}).encode())
                    handle.flush()
                    os.fsync(handle.fileno())
            entered.set()
            # Do not wait on a shared synchronization lock that a kill could
            # abandon while the parent attempts cleanup.
            time.sleep(20)
            raise SystemExit("kill fixture deadline elapsed without receipt")

    CampaignContinuityController(root, scope, clock=lambda: 100).step(HeldLaunchAdapter())


class CampaignContinuityDraftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.subject = RepositorySubject("repository:fixture", "worktree:fixture", "a" * 40, "b" * 40)
        self.evidence = (EvidenceReference("source:fixture", digest("c")),)
        self.scope = ContinuityScope(
            "campaign-1", "delivery-1", self.subject, "owner-1", digest("a"), digest("b"),
            self.evidence, ("alpha", "beta", "deferred"), 1000,
        )
        self.delivery = CompletedDelivery("delivery-1", self.subject, self.scope.scope_digest,
                                          True, True, self.evidence)
        self.adapter = MemoryAdapter()
        self.controller = self.reopen()

    def reopen(self):
        return CampaignContinuityController(self.root, self.scope, clock=lambda: 100)

    def candidate(self, candidate_id="alpha", **changes):
        return replace(CampaignCandidate(
            candidate_id, digest("d"), self.subject, self.scope.scope_digest,
            self.scope.authority_digest, 10, True, "adapt", self.evidence,
            ("Retain the failed alternative and verify this draft later.",),
        ), **changes)

    def ready(self):
        self.controller.record_delivery(self.delivery)
        self.controller.record_candidate(self.candidate())

    def test_restart_waiting_selected_and_launched_preserves_one_operation(self):
        self.controller.record_delivery(self.delivery)
        self.controller = self.reopen()
        self.assertEqual(self.controller.checkpoint()["phase"], Phase.WAITING)
        self.controller.record_candidate(self.candidate())
        selected = self.controller.step(self.adapter)
        self.assertEqual(selected["phase"], Phase.SELECTED)
        self.assertEqual(self.adapter.launches, [])
        self.controller = self.reopen()
        launched = self.controller.step(self.adapter)
        self.assertEqual(launched["phase"], Phase.LAUNCHED)
        self.assertEqual(self.adapter.launches, [selected["operation_id"]])
        self.controller = self.reopen()
        observations = self.adapter.observations
        self.assertEqual(self.controller.step(self.adapter), launched)
        self.assertEqual(self.adapter.observations, observations)

    def test_duplicate_delivery_and_candidate_intake_are_idempotent(self):
        self.ready()
        before = self.controller.events()
        self.controller.record_delivery(self.delivery)
        self.controller.record_candidate(self.candidate())
        self.assertEqual(self.controller.events(), before)

    def test_candidate_replacement_is_retained_and_stops_campaign(self):
        self.ready()
        changed = self.candidate(version_digest=digest("e"))
        state = self.controller.record_candidate(changed)
        self.assertEqual(state["blocker"], "candidate-conflict")
        self.assertEqual(state["candidates"]["alpha"]["version_digest"], digest("d"))
        self.assertEqual(self.controller.events()[-1]["payload"]["evidence"]["version_digest"], digest("e"))
        self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.BLOCKED)
        self.assertFalse(self.adapter.launches)

    def test_delivery_replacement_cannot_relaunch(self):
        self.ready()
        self.controller.step(self.adapter)
        self.controller.step(self.adapter)
        state = self.controller.record_delivery(replace(self.delivery, delivery_id="other-delivery"))
        self.assertEqual(state["phase"], Phase.LAUNCHED)
        self.assertEqual(self.controller.events()[-1]["payload"]["code"], "delivery-conflict")
        self.controller.step(self.adapter)
        self.assertEqual(len(self.adapter.launches), 1)

    def test_completed_merge_without_green_checks_is_ineligible(self):
        state = self.controller.record_delivery(replace(self.delivery, required_checks_green=False))
        self.assertEqual(state["blocker"], "delivery-incomplete")
        self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.BLOCKED)
        self.assertEqual(self.adapter.observations, 0)

    def test_deterministic_selection_retains_every_disposition_and_dissent(self):
        self.controller.record_delivery(self.delivery)
        for candidate in (self.candidate("beta"), self.candidate("deferred", priority=999, disposition="defer"), self.candidate()):
            self.controller.record_candidate(candidate)
        state = self.controller.step(self.adapter)
        self.assertEqual(state["selected"], "alpha")
        self.assertEqual(set(state["candidates"]), {"alpha", "beta", "deferred"})
        selection = self.controller.events()[-1]["payload"]
        self.assertEqual(selection["eligible"], ["alpha", "beta"])
        self.assertEqual(selection["not_selected"], ["beta", "deferred"])
        self.assertEqual(len(selection["dispositions"]), 3)
        self.assertTrue(all(row["dissent"] for row in selection["dispositions"]))
        other = CampaignContinuityController(self.root / "other", self.scope, clock=lambda: 100)
        other.record_candidate(self.candidate())
        other.record_delivery(self.delivery)
        self.assertEqual(other.step(MemoryAdapter())["operation_id"], state["operation_id"])

    def test_stale_or_out_of_scope_candidates_remain_retained_but_cannot_launch(self):
        for index, changed in enumerate((
            self.candidate(scope_digest=digest("e")),
            self.candidate(authority_digest=digest("f")),
            self.candidate(reversible=False),
            self.candidate(subject=replace(self.subject, commit="c" * 40)),
        )):
            with self.subTest(candidate=changed):
                path = self.root / "candidate-variants" / str(index)
                controller = CampaignContinuityController(path, self.scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(changed)
                state = controller.step(MemoryAdapter())
                self.assertEqual(state["blocker"], "no-eligible-candidate")
                self.assertIn("alpha", state["candidates"])

    def test_scope_change_on_reopen_is_typed_and_preserves_original_bytes(self):
        self.ready()
        before = {path.name: path.read_bytes() for path in self.root.glob("event-*.json")}
        changed = replace(self.scope, scope_digest=digest("e"))
        with self.assertRaises(ContinuityError) as raised:
            CampaignContinuityController(self.root, changed, clock=lambda: 100)
        self.assertEqual(raised.exception.code, "scope-changed")
        self.assertEqual({path.name: path.read_bytes() for path in self.root.glob("event-*.json")}, before)

    def test_observed_scope_worktree_authority_and_evidence_must_match(self):
        mutations = (
            ({"scope_digest": digest("e")}, "scope-changed"),
            ({"subject": replace(self.subject, worktree_id="worktree:substituted")}, "subject-changed"),
            ({"authority_digest": digest("e")}, "authority-changed"),
            ({"verified_evidence": (EvidenceReference("substituted", digest("e")),)}, "evidence-mismatch"),
            ({"observed_at": 1}, "observation-stale"),
            ({"observed_at": 101}, "observation-stale"),
        )
        for index, (changes, code) in enumerate(mutations):
            with self.subTest(code=code):
                controller = CampaignContinuityController(self.root / str(index), self.scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                adapter = MemoryAdapter()
                adapter.observation_changes = changes
                self.assertEqual(controller.step(adapter)["blocker"], code)
                self.assertFalse(adapter.launches)

    def test_denied_authority_is_terminal_and_never_retried(self):
        self.ready()
        self.adapter.observation_changes = {"launch_allowed": False}
        state = self.controller.step(self.adapter)
        self.assertEqual(state["blocker"], "authority-denied")
        self.adapter.observation_changes = {}
        self.controller = self.reopen()
        self.assertEqual(self.controller.step(self.adapter), state)
        self.assertEqual(self.adapter.observations, 1)
        self.assertFalse(self.adapter.inspections)

    def test_launch_denial_is_terminal_without_retry(self):
        self.ready()
        self.controller.step(self.adapter)
        self.adapter.launch_status = LaunchStatus.DENIED
        state = self.controller.step(self.adapter)
        self.assertEqual(state["blocker"], "launch-denied")
        self.controller = self.reopen()
        self.controller.step(self.adapter)
        self.assertEqual(len(self.adapter.launches), 1)

    def test_lost_launch_response_is_observed_before_any_possible_retry(self):
        self.ready()
        selected = self.controller.step(self.adapter)
        self.adapter.raise_after_effect = True
        state = self.controller.step(self.adapter)
        self.assertEqual(state["phase"], Phase.RECONCILING)
        self.assertEqual(self.controller.events()[-1]["kind"], "launch-outcome-unknown")
        self.controller = self.reopen()
        self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.LAUNCHED)
        self.assertEqual(self.adapter.launches, [selected["operation_id"]])
        self.assertEqual(self.adapter.inspections, [selected["operation_id"], selected["operation_id"]])

    def test_unknown_effect_never_authorizes_retry_and_reconciliation_is_bounded(self):
        self.ready()
        self.controller.step(self.adapter)
        self.adapter.inspect_status = LaunchStatus.UNKNOWN
        for _ in range(self.scope.maximum_reconciliations):
            self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.RECONCILING)
            self.controller = self.reopen()
        state = self.controller.step(self.adapter)
        self.assertEqual(state["phase"], Phase.EXHAUSTED)
        self.assertEqual(state["blocker"], "reconciliation-budget-exhausted")
        self.assertFalse(self.adapter.launches)

    def test_unconfirmed_absence_does_not_authorize_launch(self):
        self.ready()
        self.controller.step(self.adapter)
        original = self.adapter.inspect
        with patch.object(self.adapter, "inspect", side_effect=lambda operation, candidate: replace(original(operation, candidate), authoritative=False)):
            self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.RECONCILING)
        self.assertFalse(self.adapter.launches)

    def test_launch_budget_is_durable_across_restart(self):
        self.ready()
        self.controller.step(self.adapter)
        self.adapter.launch_status = LaunchStatus.ABSENT
        for _ in range(self.scope.maximum_launches):
            self.controller.step(self.adapter)
            self.controller = self.reopen()
        state = self.controller.step(self.adapter)
        self.assertEqual(state["blocker"], "launch-budget-exhausted")
        self.assertEqual(state["launches"], self.scope.maximum_launches)
        self.assertEqual(len(set(self.adapter.launches)), 1)

    def test_interruption_after_intent_preserves_attempt_and_requires_inspection(self):
        self.ready()
        self.controller.step(self.adapter)
        self.adapter.raise_before_effect = True
        with self.assertRaises(SystemExit):
            self.controller.step(self.adapter)
        self.controller = self.reopen()
        checkpoint = self.controller.checkpoint()
        self.assertEqual(checkpoint["phase"], Phase.RECONCILING)
        self.assertEqual(checkpoint["launches"], 1)
        self.adapter.raise_before_effect = False
        self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.LAUNCHED)
        self.assertEqual(len(self.adapter.inspections), 2)
        self.assertEqual(len(set(self.adapter.launches)), 1)

    def test_receipt_persistence_failure_recovers_external_result_without_relaunch(self):
        self.ready()
        self.controller.step(self.adapter)
        original = self.controller._append
        def fail_receipt(kind, payload, state):
            if kind == "launch-receipt":
                raise ContinuityError("checkpoint-persistence", "simulated publication failure")
            return original(kind, payload, state)
        with patch.object(self.controller, "_append", side_effect=fail_receipt):
            with self.assertRaises(ContinuityError):
                self.controller.step(self.adapter)
        self.controller = self.reopen()
        self.assertEqual(self.controller.step(self.adapter)["phase"], Phase.LAUNCHED)
        self.assertEqual(len(self.adapter.launches), 1)
        kinds = [event["kind"] for event in self.controller.events()]
        self.assertIn("launch-intent", kinds)
        self.assertIn("reconciliation-receipt", kinds)

    def test_substituted_launch_receipt_is_retained_as_a_typed_blocker(self):
        self.ready()
        self.controller.step(self.adapter)
        original = self.adapter.inspect
        with patch.object(self.adapter, "inspect", side_effect=lambda operation, candidate: replace(original(operation, candidate), candidate_digest=digest("e"))):
            state = self.controller.step(self.adapter)
        self.assertEqual(state["blocker"], "launch-receipt-mismatch")
        self.assertIn("receipt", self.controller.events()[-1]["payload"]["evidence"])
        self.assertFalse(self.adapter.launches)

    def test_corrupt_checkpoint_never_reaches_adapter(self):
        self.ready()
        checkpoint = next(self.root.glob("event-*.json"))
        checkpoint.write_bytes(checkpoint.read_bytes() + b" ")
        with self.assertRaises(ContinuityError) as raised:
            self.controller.step(self.adapter)
        self.assertEqual(raised.exception.code, "checkpoint-corrupt")
        self.assertEqual(self.adapter.observations, 0)

    def test_wrong_scope_restore_is_rejected_by_every_public_read(self):
        self.ready()
        foreign_scope = replace(self.scope, campaign_id="foreign", subject=replace(self.subject, worktree_id="foreign"))
        foreign = CampaignContinuityController(self.root / "foreign", foreign_scope, clock=lambda: 100)
        foreign.record_delivery(replace(self.delivery, subject=foreign_scope.subject))
        foreign.record_candidate(self.candidate(subject=foreign_scope.subject))
        foreign.step(MemoryAdapter())
        for path in self.root.glob("event-*.json"):
            path.unlink()
        for path in foreign.root.glob("event-*.json"):
            (self.root / path.name).write_bytes(path.read_bytes())
        for call in (self.controller.checkpoint, self.controller.events,
                     lambda: self.controller.step(self.adapter), lambda: self.controller.recover(self.adapter),
                     lambda: self.controller.record_delivery(self.delivery),
                     lambda: self.controller.record_candidate(self.candidate())):
            with self.assertRaises(ContinuityError) as raised:
                call()
            self.assertEqual(raised.exception.code, "scope-changed")
        self.assertEqual(self.adapter.observations, 0)
        self.assertFalse(self.adapter.inspections)
        self.assertFalse(self.adapter.launches)

    def test_pending_effect_recovery_after_expiry_denial_and_final_attempt(self):
        for index, (failure, stop) in enumerate((
            ("response", "expiry"), ("response", "denial"), ("response", "budget"),
            ("persistence", "expiry"), ("persistence", "denial"), ("persistence", "budget"),
        )):
            with self.subTest(failure=failure, stop=stop):
                scope = replace(self.scope, maximum_launches=1, maximum_reconciliations=1)
                now = [100]
                root = self.root / str(index)
                controller = CampaignContinuityController(root, scope, clock=lambda: now[0])
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                adapter = MemoryAdapter()
                selected = controller.step(adapter)
                if failure == "response":
                    adapter.raise_after_effect = True
                    controller.step(adapter)
                else:
                    link = os.link

                    def fail_receipt(source, destination):
                        if json.loads(Path(source).read_bytes())["kind"] == "launch-receipt":
                            raise OSError("fixture receipt publication failure")
                        return link(source, destination)

                    with patch("hive_mind_os.campaign_continuity.os.link", side_effect=fail_receipt):
                        with self.assertRaises(ContinuityError):
                            controller.step(adapter)
                if stop == "expiry":
                    now[0] = scope.expires_at
                elif stop == "denial":
                    adapter.observation_changes = {"launch_allowed": False}
                controller = CampaignContinuityController(root, scope, clock=lambda: now[0])
                stopped = controller.step(adapter)
                self.assertTrue(stopped["outcome_pending"])
                self.assertEqual(stopped["blocker"], {
                    "expiry": "authority-expired", "denial": "authority-denied",
                    "budget": "reconciliation-budget-exhausted",
                }[stop])
                observations = adapter.observations
                recovered = controller.recover(adapter)
                self.assertEqual(recovered["phase"], Phase.LAUNCHED)
                self.assertFalse(recovered["outcome_pending"])
                self.assertEqual(recovered["blocker"], stopped["blocker"])
                self.assertEqual(recovered["recoveries"], 1)
                self.assertEqual(recovered["operation_id"], selected["operation_id"])
                self.assertEqual(adapter.observations, observations)
                self.assertEqual(adapter.launches, [selected["operation_id"]])
                self.assertEqual(len(adapter.operations), 1)
                self.assertEqual(controller.step(adapter), recovered)

    def test_recovery_unknown_is_bounded_and_never_reopens_dispatch(self):
        self.ready()
        self.controller.step(self.adapter)
        self.adapter.raise_before_effect = True
        with self.assertRaises(SystemExit):
            self.controller.step(self.adapter)
        self.adapter.inspect_status = LaunchStatus.UNKNOWN
        for count in range(1, self.scope.maximum_recoveries + 1):
            state = self.reopen().recover(self.adapter)
            self.assertEqual(state["recoveries"], count)
            self.assertTrue(state["outcome_pending"])
        state = self.reopen().recover(self.adapter)
        self.assertEqual(state["phase"], Phase.EXHAUSTED)
        self.assertTrue(state["outcome_pending"])
        before = self.controller.events()
        self.assertEqual(self.reopen().recover(self.adapter), state)
        self.assertEqual(self.controller.events(), before)
        self.assertEqual(len(self.adapter.inspections), 1 + self.scope.maximum_recoveries)
        self.assertEqual(len(self.adapter.launches), 1)
        self.assertEqual(self.controller.events()[-1]["payload"]["code"], "recovery-budget-exhausted")

    def test_recovery_absence_closes_unknown_without_launching(self):
        self.ready()
        self.controller.step(self.adapter)
        self.adapter.raise_before_effect = True
        with self.assertRaises(SystemExit):
            self.controller.step(self.adapter)
        self.adapter.raise_before_effect = False
        state = self.reopen().recover(self.adapter)
        self.assertEqual(state["phase"], Phase.BLOCKED)
        self.assertFalse(state["outcome_pending"])
        self.assertEqual(self.reopen().step(self.adapter), state)
        self.assertEqual(len(self.adapter.launches), 1)
        self.assertFalse(self.adapter.operations)

    def test_typed_observer_denial_is_retained_once(self):
        self.ready()
        with patch.object(self.adapter, "observe", side_effect=ContinuityError("authority-denied", "sanitized denial")) as observe:
            state = self.controller.step(self.adapter)
            self.assertEqual(self.reopen().step(self.adapter), state)
        self.assertEqual(observe.call_count, 1)
        self.assertEqual(state["blocker"], "authority-denied")
        self.assertEqual(self.controller.events()[-1]["payload"]["evidence"], {
            "error": "ContinuityError", "code": "authority-denied", "message": "sanitized denial",
        })

    def test_observation_persistence_failure_is_not_an_adapter_denial(self):
        self.ready()
        append = self.controller._append

        def fail_observation(kind, payload, state):
            if kind == "authority-observed":
                raise ContinuityError("checkpoint-persistence", "fixture")
            return append(kind, payload, state)

        with patch.object(self.controller, "_append", side_effect=fail_observation):
            with self.assertRaises(ContinuityError) as raised:
                self.controller.step(self.adapter)
        self.assertEqual(raised.exception.code, "checkpoint-persistence")
        self.assertIsNone(self.controller.checkpoint()["blocker"])

    def test_typed_launch_denial_after_effect_stops_dispatch_but_allows_recovery(self):
        self.ready()
        self.controller.step(self.adapter)
        launch = self.adapter.launch

        def denied_after_effect(operation, candidate, scope):
            launch(operation, candidate, scope)
            raise ContinuityError("authority-denied", "sanitized refusal after possible effect")

        with patch.object(self.adapter, "launch", side_effect=denied_after_effect):
            state = self.controller.step(self.adapter)
        self.assertEqual(state["blocker"], "authority-denied")
        self.assertTrue(state["outcome_pending"])
        self.assertEqual(self.reopen().step(self.adapter), state)
        self.assertEqual(self.reopen().recover(self.adapter)["phase"], Phase.LAUNCHED)
        self.assertEqual(len(self.adapter.launches), 1)
        evidence = [event["payload"] for event in self.controller.events()
                    if event["kind"] == "launch-outcome-unknown"]
        self.assertEqual(evidence[0]["code"], "authority-denied")

    def test_typed_inspect_failure_is_retained_without_authorizing_launch(self):
        self.ready()
        self.controller.step(self.adapter)
        with patch.object(self.adapter, "inspect", side_effect=ContinuityError("authority-denied", "sanitized inspection denial")) as inspect:
            state = self.controller.step(self.adapter)
            self.assertEqual(self.reopen().step(self.adapter), state)
        self.assertEqual(state["blocker"], "authority-denied")
        self.assertEqual(inspect.call_count, 1)
        self.assertEqual(state["reconciliations"], 1)
        self.assertFalse(self.adapter.launches)

    def test_response_dataclasses_require_exact_fields(self):
        observation = self.adapter.observe(self.scope, self.evidence)
        for changes in ({"observer_id": ["invalid"]}, {"observer_id": " observer "}, {"owner_id": ""},
                        {"observed_at": True}, {"launch_allowed": 1}, {"verified_evidence": list(self.evidence)},
                        {"verified_evidence": self.evidence * 2}, {"scope_digest": "bad"}, {"receipt": {}},
                        {"subject": {}}, {"authority_digest": "bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(observation, **changes)
        receipt = self.adapter.receipt(digest("a"), self.candidate(), LaunchStatus.STARTED)
        for changes in ({"detail": object()}, {"operation_id": "bad"}, {"status": "started"},
                        {"authoritative": 1}, {"receipt": {}}, {"candidate_digest": "bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(receipt, **changes)

    def test_mutated_observation_cannot_bypass_boundary_validation(self):
        self.ready()
        observed = self.adapter.observe(self.scope, self.evidence)
        object.__setattr__(observed, "observer_id", ["not-an-identifier"])
        with patch.object(self.adapter, "observe", return_value=observed):
            self.assertEqual(self.controller.step(self.adapter)["blocker"], "observation-malformed")
        self.assertFalse(self.adapter.launches)

    def test_malformed_or_denied_launch_receipt_keeps_effect_recoverable(self):
        for index, malformed in enumerate((True, False)):
            controller = CampaignContinuityController(self.root / str(index), self.scope, clock=lambda: 100)
            controller.record_delivery(self.delivery)
            controller.record_candidate(self.candidate())
            adapter = MemoryAdapter()
            controller.step(adapter)
            launch = adapter.launch

            def bad_receipt(operation, candidate, scope):
                receipt = launch(operation, candidate, scope)
                if malformed:
                    object.__setattr__(receipt, "detail", object())
                    return receipt
                return replace(receipt, status=LaunchStatus.DENIED)

            with patch.object(adapter, "launch", side_effect=bad_receipt):
                state = controller.step(adapter)
            self.assertTrue(state["outcome_pending"])
            self.assertEqual(state["phase"], Phase.BLOCKED)
            self.assertEqual(controller.recover(adapter)["phase"], Phase.LAUNCHED)
            self.assertEqual(len(adapter.launches), 1)

    @staticmethod
    def rewrite_event(path, change):
        document = json.loads(path.read_bytes())
        change(document)
        body = {key: value for key, value in document.items() if key != "event_digest"}
        def canonical(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

        document["event_digest"] = "sha256:" + sha256(canonical(body)).hexdigest()
        path.write_bytes(canonical(document) + b"\n")

    def test_invalid_journal_shapes_fail_closed_even_with_valid_digest(self):
        changes = (
            lambda doc: doc["checkpoint"].pop("phase"),
            lambda doc: doc["checkpoint"].update(launches=True),
            lambda doc: doc["checkpoint"].update(reconciliations=-1),
            lambda doc: doc["checkpoint"].update(candidates=[]),
            lambda doc: doc["checkpoint"].update(selected="missing"),
            lambda doc: doc["checkpoint"].update(phase="invalid"),
            lambda doc: doc["checkpoint"].update(outcome_pending=True),
        )
        for index, change in enumerate(changes):
            root = self.root / str(index)
            CampaignContinuityController(root, self.scope, clock=lambda: 100)
            self.rewrite_event(root / "event-00000001.json", change)
            with self.subTest(index=index), self.assertRaises(ContinuityError) as raised:
                CampaignContinuityController(root, self.scope, clock=lambda: 100)
            self.assertEqual(raised.exception.code, "checkpoint-corrupt")

    def test_invalid_json_roots_and_deleted_journal_are_typed(self):
        for index, raw in enumerate((b"[]\n", b"null\n", b"1\n", b"{}\n", b"invalid")):
            root = self.root / str(index)
            controller = CampaignContinuityController(root, self.scope, clock=lambda: 100)
            (root / "event-00000001.json").write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ContinuityError) as raised:
                controller.step(self.adapter)
            self.assertEqual(raised.exception.code, "checkpoint-corrupt")
        self.ready()
        latest = sorted(self.root.glob("event-*.json"))[-1]
        latest.unlink()
        with self.assertRaises(ContinuityError) as raised:
            self.controller.checkpoint()
        self.assertEqual(raised.exception.code, "checkpoint-corrupt")
        for path in self.root.glob("event-*.json"):
            path.unlink()
        for call in (self.controller.checkpoint, self.reopen):
            with self.assertRaises(ContinuityError) as raised:
                call()
            self.assertEqual(raised.exception.code, "checkpoint-corrupt")

    def test_selected_candidate_and_operation_are_revalidated_on_restart(self):
        for index, change in enumerate((
            lambda doc: doc["checkpoint"]["candidates"]["alpha"].update(authority_digest=digest("e")),
            lambda doc: doc["checkpoint"].update(operation_id=digest("e")),
        )):
            root = self.root / str(index)
            controller = CampaignContinuityController(root, self.scope, clock=lambda: 100)
            controller.record_delivery(self.delivery)
            controller.record_candidate(self.candidate())
            controller.step(self.adapter)
            self.rewrite_event(sorted(root.glob("event-*.json"))[-1], change)
            with self.assertRaises(ContinuityError) as raised:
                CampaignContinuityController(root, self.scope, clock=lambda: 100)
            self.assertEqual(raised.exception.code, "checkpoint-corrupt")
        self.assertFalse(self.adapter.inspections)

    def test_publication_and_cleanup_errors_preserve_primary_failure(self):
        before = self.controller.events()
        unlink = Path.unlink

        def refuse_cleanup(path, *args, **kwargs):
            if path.name.startswith(".pending-"):
                raise PermissionError("fixture cleanup failure")
            return unlink(path, *args, **kwargs)

        with patch("hive_mind_os.campaign_continuity.os.link", side_effect=OSError("fixture link failure")), \
                patch.object(Path, "unlink", refuse_cleanup):
            with self.assertRaises(ContinuityError) as raised:
                self.controller.record_delivery(self.delivery)
        self.assertEqual(raised.exception.code, "checkpoint-persistence")
        self.assertEqual(str(raised.exception.__cause__), "fixture link failure")
        self.assertEqual(self.controller.events(), before)
        with patch.object(Path, "unlink", refuse_cleanup):
            with self.assertRaises(ContinuityError) as raised:
                self.controller.record_delivery(self.delivery)
        self.assertEqual(raised.exception.code, "checkpoint-cleanup")
        self.assertIsNotNone(self.reopen().checkpoint()["delivery"])
        self.assertEqual(len(self.controller.events()), len(before) + 1)
        self.controller.record_delivery(self.delivery)
        self.assertEqual(len(self.controller.events()), len(before) + 1)

    def test_hardlinked_lock_never_writes_external_target(self):
        outside = self.root / "external-lock-target"
        outside.write_bytes(b"")
        root = self.root / "linked-lock"
        root.mkdir()
        os.link(outside, root / ".writer.lock")
        with self.assertRaises(ContinuityError) as raised:
            CampaignContinuityController(root, self.scope, clock=lambda: 100)
        self.assertEqual(raised.exception.code, "unsafe-storage-path")
        self.assertEqual(outside.read_bytes(), b"")
        self.assertFalse(list(root.glob("event-*.json")))

    def test_hardlinked_event_is_rejected_before_adapter(self):
        os.link(self.root / "event-00000001.json", self.root / "external-event")
        with self.assertRaises(ContinuityError) as raised:
            self.controller.step(self.adapter)
        self.assertEqual(raised.exception.code, "unsafe-storage-path")
        self.assertEqual(self.adapter.observations, 0)

    def test_symbolic_directory_and_lock_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"platform does not permit fixture symlinks: {error}")
        with self.assertRaises(ContinuityError) as raised:
            CampaignContinuityController(alias, self.scope, clock=lambda: 100)
        self.assertEqual(raised.exception.code, "unsafe-storage-path")
        target = outside / "lock-target"
        target.write_bytes(b"")
        linked = self.root / "linked-symlink-lock"
        linked.mkdir()
        (linked / ".writer.lock").symlink_to(target)
        with self.assertRaises(ContinuityError) as raised:
            CampaignContinuityController(linked, self.scope, clock=lambda: 100)
        self.assertEqual(raised.exception.code, "unsafe-storage-path")
        self.assertEqual(target.read_bytes(), b"")

    def test_spawned_process_exclusion_and_single_launch(self):
        self.ready()
        selected = self.controller.step(self.adapter)
        context = multiprocessing.get_context("spawn")
        entered, release = context.Event(), context.Event()
        results = context.Queue()
        first = context.Process(target=_hold_transaction, args=(self.root, self.scope, entered, release, results))
        second = context.Process(target=_compete_transaction, args=(self.root, self.scope, results))
        try:
            first.start()
            self.assertTrue(entered.wait(10), "writer did not enter observation")
            second.start()
            second.join(10)
            self.assertFalse(second.is_alive())
            self.assertEqual(second.exitcode, 0)
            self.assertEqual(results.get(timeout=5), "writer-busy")
            release.set()
            first.join(10)
            self.assertFalse(first.is_alive())
            self.assertEqual(first.exitcode, 0)
            self.assertEqual(results.get(timeout=5), (Phase.LAUNCHED, 1))
            state = self.reopen().checkpoint()
            self.assertEqual(state["phase"], Phase.LAUNCHED)
            self.assertEqual(state["launches"], 1)
            self.assertEqual(state["operation_id"], selected["operation_id"])
        finally:
            release.set()
            for process in (first, second):
                if process.pid is not None and process.is_alive():
                    process.terminate()
                    process.join(5)
            results.close()
            results.join_thread()

    @staticmethod
    def append_fixture_event(controller, kind, payload, **changes):
        last = controller.events()[-1]
        document = {"schema_version": 2, "sequence": last["sequence"] + 1,
                    "previous_digest": last["event_digest"], "kind": kind, "payload": payload,
                    "checkpoint": {**last["checkpoint"], **changes}}
        raw = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        document["event_digest"] = "sha256:" + sha256(raw).hexdigest()
        destination = controller.root / f"event-{document['sequence']:08d}.json"
        destination.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                          allow_nan=False).encode() + b"\n")

    def assert_corrupt_replay(self, controller, scope, adapter):
        calls = (adapter.observations, len(adapter.inspections), len(adapter.launches))
        for read in (lambda: CampaignContinuityController(controller.root, scope, clock=lambda: 100),
                     controller.checkpoint, controller.events, lambda: controller.step(adapter),
                     lambda: controller.recover(adapter)):
            with self.assertRaises(ContinuityError) as raised:
                read()
            self.assertEqual(raised.exception.code, "checkpoint-corrupt")
        self.assertEqual((adapter.observations, len(adapter.inspections), len(adapter.launches)), calls)

    def test_replay_rejects_appended_terminal_dispatch_regressions(self):
        for index, terminal in enumerate((Phase.BLOCKED, Phase.EXHAUSTED, Phase.LAUNCHED)):
            with self.subTest(terminal=terminal):
                scope = replace(self.scope, maximum_reconciliations=1)
                controller = CampaignContinuityController(self.root / str(index), scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                adapter = MemoryAdapter()
                controller.step(adapter)
                if terminal == Phase.BLOCKED:
                    with patch.object(adapter, "inspect", side_effect=ContinuityError("authority-denied", "fixture")):
                        state = controller.step(adapter)
                elif terminal == Phase.EXHAUSTED:
                    adapter.inspect_status = LaunchStatus.UNKNOWN
                    controller.step(adapter)
                    state = controller.step(adapter)
                else:
                    state = controller.step(adapter)
                self.assertEqual(state["phase"], terminal)
                self.append_fixture_event(controller, "reconciliation-receipt", {},
                                          phase=Phase.RECONCILING, blocker=None)
                self.assert_corrupt_replay(controller, scope, adapter)

    def test_replay_requires_intent_and_payload_for_success(self):
        self.ready()
        self.controller.step(self.adapter)
        self.append_fixture_event(self.controller, "reconciliation-receipt", {},
                                  phase=Phase.LAUNCHED, reconciliations=1)
        self.assert_corrupt_replay(self.controller, self.scope, self.adapter)

    def test_replay_rejects_receipt_state_and_binding_contradictions(self):
        mutations = (
            (lambda payload: payload.clear(), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(authoritative=False), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(status="absent"), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(operation_id=digest("e")), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(candidate_digest=digest("e")), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(authoritative=1), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(receipt={}), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(detail=[]), {"phase": Phase.LAUNCHED, "outcome_pending": False}),
            (lambda payload: payload.update(status="unknown"), {"outcome_pending": False}),
            (lambda payload: None, {}),
        )
        for index, (mutate, changes) in enumerate(mutations):
            with self.subTest(index=index):
                controller = CampaignContinuityController(self.root / str(index), self.scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                adapter = MemoryAdapter()
                selected = controller.step(adapter)
                adapter.raise_before_effect = True
                with self.assertRaises(SystemExit):
                    controller.step(adapter)
                payload = asdict(adapter.receipt(selected["operation_id"], self.candidate(), LaunchStatus.STARTED))
                mutate(payload)
                self.append_fixture_event(controller, "launch-receipt", payload, **changes)
                self.assert_corrupt_replay(controller, self.scope, adapter)

    def test_replay_rejects_unexplained_counters_pending_blocker_and_event_kind(self):
        cases = (("unrecognized-event", {}), ("authority-observed", {"reconciliations": 1}),
                 ("authority-observed", {"blocker": "invented"}),
                 ("authority-observed", {"launches": 1, "reconciliations": 1, "outcome_pending": True}))
        for index, (kind, changes) in enumerate(cases):
            with self.subTest(index=index):
                controller = CampaignContinuityController(self.root / str(index), self.scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                adapter = MemoryAdapter()
                controller.step(adapter)
                payload = asdict(adapter.observe(self.scope, self.evidence))
                self.append_fixture_event(controller, kind, payload, **changes)
                self.assert_corrupt_replay(controller, self.scope, adapter)

    def test_replay_preserves_exhausted_recovery_receipt_outcomes(self):
        for index, status in enumerate(LaunchStatus):
            with self.subTest(status=status):
                scope = replace(self.scope, maximum_reconciliations=1)
                root = self.root / str(index)
                controller = CampaignContinuityController(root, scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                adapter = MemoryAdapter()
                selected = controller.step(adapter)
                adapter.raise_before_effect = True
                with self.assertRaises(SystemExit):
                    controller.step(adapter)
                stopped = controller.step(adapter)
                self.assertEqual(stopped["phase"], Phase.EXHAUSTED)
                adapter.inspect_status = status
                with patch.object(adapter, "observe", side_effect=AssertionError("recovery cannot observe authority")), \
                        patch.object(adapter, "launch", side_effect=AssertionError("recovery cannot dispatch")):
                    state = controller.recover(adapter)
                    reopened = CampaignContinuityController(root, scope, clock=lambda: scope.expires_at)
                    self.assertEqual(reopened.checkpoint(), state)
                    self.assertEqual(reopened.step(adapter), state)
                self.assertEqual(state["operation_id"], selected["operation_id"])
                self.assertEqual(state["blocker"], stopped["blocker"])
                self.assertEqual(state["launches"], 1)
                self.assertEqual(state["recoveries"], 1)
                self.assertEqual(state["outcome_pending"], status in {LaunchStatus.UNKNOWN, LaunchStatus.DENIED})
                self.assertEqual(state["phase"], Phase.LAUNCHED if status == LaunchStatus.STARTED else Phase.BLOCKED)

    def test_process_kill_releases_lock_and_preserves_pending_effect_recovery(self):
        for index, after_effect in enumerate((False, True)):
            with self.subTest(after_effect=after_effect):
                root = self.root / str(index)
                controller = CampaignContinuityController(root, self.scope, clock=lambda: 100)
                controller.record_delivery(self.delivery)
                controller.record_candidate(self.candidate())
                selected = controller.step(MemoryAdapter())
                effect_path = root / "fixture-effect.json"
                context = multiprocessing.get_context("spawn")
                entered = context.Event()
                process = context.Process(target=_hold_after_launch_intent,
                    args=(root, self.scope, effect_path, after_effect, entered))
                try:
                    process.start()
                    self.assertTrue(entered.wait(10), "child did not retain launch intent")
                    process.kill()
                    process.join(10)
                    self.assertFalse(process.is_alive(), "killed child did not exit")
                    self.assertNotEqual(process.exitcode, 0)
                    restarted = CampaignContinuityController(root, self.scope, clock=lambda: self.scope.expires_at)
                    pending = restarted.checkpoint()
                    self.assertTrue(pending["outcome_pending"])
                    self.assertEqual(pending["launches"], 1)
                    self.assertEqual(pending["operation_id"], selected["operation_id"])
                    adapter = MemoryAdapter()
                    if after_effect:
                        effect = json.loads(effect_path.read_bytes())
                        self.assertEqual(effect, {"operation_id": selected["operation_id"],
                                                  "candidate_digest": self.candidate().version_digest})
                        adapter.operations[effect["operation_id"]] = effect["candidate_digest"]
                    else:
                        self.assertFalse(effect_path.exists())
                    recovered = restarted.recover(adapter)
                    self.assertFalse(recovered["outcome_pending"])
                    self.assertEqual(recovered["phase"], Phase.LAUNCHED if after_effect else Phase.BLOCKED)
                    self.assertEqual(restarted.step(adapter), recovered)
                    self.assertEqual(adapter.observations, 0)
                    self.assertFalse(adapter.launches)
                    self.assertEqual(adapter.inspections, [selected["operation_id"]])
                finally:
                    if process.pid is not None:
                        if process.is_alive():
                            process.kill()
                        process.join(5)
                        if not process.is_alive():
                            process.close()

    def test_long_path_journal_roundtrip_or_explicit_platform_refusal(self):
        # A generic mkdir refusal is an error with no adapter effects, never a
        # reason to skip the executable long-path acceptance below.
        refused = self.root / "refused-long-path-fixture"
        failure = FileNotFoundError(2, "fixture directory creation refused", str(refused))
        with patch.object(Path, "mkdir", side_effect=failure):
            with self.assertRaises(ContinuityError) as raised:
                CampaignContinuityController(refused, self.scope, clock=lambda: 100)
        self.assertEqual(raised.exception.code, "checkpoint-storage")
        self.assertIs(raised.exception.__cause__, failure)
        self.assertEqual(self.adapter.observations, 0)
        self.assertFalse(self.adapter.inspections)
        self.assertFalse(self.adapter.launches)
        self.assertFalse(refused.exists())

        fixture = self.root / "long-path-fixture"
        if os.name == "nt":
            # The caller explicitly opts into Windows extended-length syntax.
            # No registry/global path setting or library authority changes.
            absolute = str(fixture.absolute())
            if not absolute.startswith("\\\\?\\"):
                absolute = "\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute
            fixture = Path(absolute)
        fixture.mkdir()
        # Cleanup uses the same prefix; unprefixed recursive traversal can hit
        # MAX_PATH even though all the journal operations used extended paths.
        self.addCleanup(shutil.rmtree, fixture)
        root = fixture
        while len(str(root)) < 320:
            root /= "continuity-long-path-component"
        self.assertGreaterEqual(len(str(root)), 320)
        controller = CampaignContinuityController(root, self.scope, clock=lambda: 100)
        self.assertEqual(controller.root, root)
        controller.record_delivery(self.delivery)
        controller.record_candidate(self.candidate())
        controller.step(self.adapter)
        state = controller.step(self.adapter)
        reopened = CampaignContinuityController(root, self.scope, clock=lambda: 100)
        self.assertEqual(reopened.step(self.adapter), state)
        self.assertEqual(state["phase"], Phase.LAUNCHED)
        self.assertEqual(len(self.adapter.launches), 1)
        self.assertEqual(reopened.events(), controller.events())

    def test_qualification_manifest_binds_canonical_git_artifacts_and_exact_evidence(self):
        repository = Path(__file__).resolve().parents[1]
        manifest = json.loads((repository / "docs/architecture/CONTINUITY-QUALIFICATION-REPAIR-MANIFEST.json").read_bytes())
        self.assertEqual(manifest["status"], "IMPLEMENTED_AWAITING_ROOT_QUALIFICATION")
        self.assertTrue(manifest["artifacts"])
        self.assertEqual(len({item["path"] for item in manifest["artifacts"]}), len(manifest["artifacts"]))
        for item in manifest["artifacts"]:
            with self.subTest(path=item["path"]):
                raw = (repository / item["path"]).read_bytes()
                if item["representation"] == "repository-lf":
                    raw = raw.replace(b"\r\n", b"\n")
                else:
                    self.assertEqual(item["representation"], "exact-evidence-bytes")
                    self.assertTrue(item["path"].startswith("evidence/live/continuity-qualification/"))
                self.assertEqual(len(raw), item["bytes"])
                self.assertEqual(sha256(raw).hexdigest(), item["sha256"])
                git_blob = subprocess.run(["git", "hash-object", "--stdin", "--path", item["path"]],
                    cwd=repository, input=(repository / item["path"]).read_bytes(), capture_output=True,
                    check=True, timeout=10).stdout.decode().strip()
                self.assertEqual(git_blob, item["git_blob_oid"])
        for item in manifest["historical_git_artifacts"]:
            with self.subTest(historical=item["path"]):
                # These retained immutable blob bytes also work in shallow CI clones.
                raw = (repository / item["retained_exact_blob"]).read_bytes()
                self.assertEqual(len(raw), item["bytes"])
                self.assertEqual(sha256(raw).hexdigest(), item["sha256"])
                oid = subprocess.run(["git", "hash-object", "--stdin"], cwd=repository, input=raw,
                    capture_output=True, check=True, timeout=10).stdout.decode().strip()
                self.assertEqual(oid, item["git_blob_oid"])
        for item in manifest["original_review_mapping"]:
            original = (repository / item["exact_copy"]).read_bytes()
            view = (repository / item["normalized_view"]).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(sha256(original).hexdigest(), item["original_sha256"])
            self.assertEqual(original.replace(b"\r\n", b"\n"), view)
