"""UNVERIFIED DRAFT acceptance specifications; authored for a later execution pass."""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
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
