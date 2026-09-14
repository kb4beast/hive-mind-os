import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import hive_mind_os.campaign_metrics as metrics
from hive_mind_os.campaign_metrics import (
    RECIPE_FIELDS,
    REQUIRED_STRATA,
    AdmissionSnapshot,
    AggregateEvidence,
    AggregateReceipt,
    AttemptMetric,
    AuthorityBinding,
    BracketSnapshot,
    BracketState,
    CampaignMetricsError,
    DescriptiveInterval,
    FamilyObservation,
    FinalistBinding,
    IssuedReceipt,
    LeaseExhausted,
    LeaseRecord,
    MatchProtocol,
    ObservationShapeEntry,
    ReceiptOutcome,
    StageEvidence,
    TaskBinding,
    VariantSeal,
    canonical_digest,
    decide_match,
    load_match_protocol,
    load_match_protocol_for_inspection,
    paired_family_bootstrap,
    stage_paired_bootstrap,
    summarize_attempts,
    validate_and_append_seals,
)

D = "sha256:" + "a" * 64


def digest(label):
    return canonical_digest(label)


def plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [plain(item) for item in value]
    return value


def recipe(variant, track, regime):
    return {
        "track": track,
        "regime_id": regime,
        "availability": "available",
        "provenance_digest": digest([variant, "provenance"]),
        **{field: digest([variant, field]) for field in RECIPE_FIELDS},
    }


def protocol():
    entrants = {
        **{
            f"MB{i}": recipe(f"MB{i}", "builder-component", "component-default")
            for i in range(4)
        },
        **{
            f"MC{i}": recipe(f"MC{i}", "whole-campaign", "whole-default")
            for i in range(2)
        },
    }
    hybrids = {
        f"MH{i}": recipe(f"MH{i}", "whole-campaign", "whole-default")
        for i in range(1, 5)
    }
    manifest = {
        "selection_seed": 271828,
        "bootstrap_seed": 314159,
        "retry_rule": "invalidated-only",
        "screening_families": 12,
        "final_families": 30,
        "final_repetitions": 3,
        "recipe_manifest_digest": digest("recipe-manifest"),
        "block_manifest_digests": {
            stage: digest([stage, "block"]) for stage in ("original", "hybrid", "final")
        },
        "task_manifest_digests": {
            stage: digest([stage, "tasks"]) for stage in ("original", "hybrid", "final")
        },
        "family_manifest_digests": {
            stage: digest([stage, "families"])
            for stage in ("original", "hybrid", "final")
        },
        "manifest_signature_refs": {
            stage: f"signature:{stage}" for stage in ("original", "hybrid", "final")
        },
        "custody_receipt_ref": "custody:fixture",
    }
    return MatchProtocol(
        "WOS-N02-FIXTURE",
        "2.0.0",
        "whole-os-tournament",
        entrants,
        {"complete_behavior": "eight digest dimensions", "unavailable": "DEFERRED"},
        "registry-authenticated-append-only-stage-seal",
        tuple(f"task-{index:02d}" for index in range(30)),
        ("development-screening", "harder-hybrid-development", "promotion_holdout"),
        "registry-state-cas-loss-id-rotate-odd-bye-two-inconclusive",
        "registry-bound-exact-observation-shape-stage-pair-positive-ratio-bootstrap-hard-gates",
        hybrids,
        manifest,
        "closure:fixture-only",
        3,
        "N30-bounded-lease-required",
        24,
        ("one_survivor", "no_schedulable_pairs", "max_rounds", "lease_exhausted"),
    )


def task_bindings(stage):
    count, repetitions = (30, 3) if stage == "final" else (12, 1)
    rows = []
    for index in range(count):
        strata = (
            (REQUIRED_STRATA[index],)
            if index < len(REQUIRED_STRATA)
            else (REQUIRED_STRATA[0],)
        )
        if count == 12 and index == 0:
            strata = (REQUIRED_STRATA[0], REQUIRED_STRATA[-1])
        rows.append(
            TaskBinding(
                f"task-{index:02d}",
                f"family-{index:02d}",
                strata,
                tuple(index * 10 + rep for rep in range(repetitions)),
            )
        )
    return tuple(rows)


PRINCIPALS = AuthorityBinding(
    "evaluator:independent",
    "custodian:independent",
    ("builder:a", "builder:b"),
    ("champion:current",),
    "signature:evaluator",
    "signature:custody",
)


def stage_evidence(
    p, stage, *, final_pair=(), stage_opened_at=10, holdout_opened_at=None
):
    manifest = p.experiment_manifest
    return StageEvidence(
        p.protocol_digest,
        manifest["recipe_manifest_digest"],
        stage,
        {
            "original": "development-screening",
            "hybrid": "harder-hybrid-development",
            "final": "promotion_holdout",
        }[stage],
        manifest["block_manifest_digests"][stage],
        manifest["task_manifest_digests"][stage],
        manifest["family_manifest_digests"][stage],
        manifest["manifest_signature_refs"][stage],
        task_bindings(stage),
        PRINCIPALS,
        314159 if stage == "final" else 271828,
        3 if stage == "final" else 1,
        stage_opened_at,
        tuple(final_pair),
        holdout_opened_at,
    )


def observation_shape(evidence):
    return tuple(
        sorted(
            ObservationShapeEntry(
                task.family_id,
                task.task_id,
                repetition,
                task.repetition_seeds[repetition],
            )
            for task in evidence.tasks
            for repetition in range(evidence.repetitions)
        )
    )


def lease(
    p,
    stage,
    *,
    issued_by="host:lease",
    issued_at=1,
    expires_at=1000,
    revoked_at=None,
    operations=None,
):
    operations = frozenset(
        operations or ("schedule", "apply", "seal", "aggregate", "decide")
    )
    content = {
        "protocol": p.protocol_id,
        "stage": stage,
        "issuer": issued_by,
        "issued": issued_at,
        "expires": expires_at,
        "revoked": revoked_at,
        "operations": sorted(operations),
    }
    return LeaseRecord(
        digest(content),
        p.protocol_id,
        stage,
        digest([content, "budget"]),
        issued_by,
        issued_at,
        expires_at,
        revoked_at,
        operations,
    )


def seal_for(p, evidence, variant, sequence, candidate, sealed_at):
    r = p.recipe(variant)
    return VariantSeal(
        p.protocol_digest,
        evidence.evidence_digest,
        sequence,
        variant,
        p.recipe_digest(variant, r),
        candidate,
        PRINCIPALS.evaluator_id,
        PRINCIPALS.custodian_id,
        evidence.stage,
        evidence.block_digest,
        evidence.task_manifest_digest,
        evidence.family_manifest_digest,
        r["regime_id"],
        sealed_at,
        f"seal-signature:{sequence}",
    )


class _Handle:
    pass


class _FixtureRegistry:
    """Test-only registry; opaque objects and every ledger are instance-bound."""

    def __init__(self, p, evidence, lease_record, *, observed_at=20, history=()):
        self.handle = _Handle()
        admission = canonical_digest(
            {
                "protocol_digest": p.protocol_digest,
                "stage_evidence": evidence,
                "lease": lease_record,
            }
        )
        self.snapshot = AdmissionSnapshot(
            admission,
            p.protocol_digest,
            evidence,
            lease_record,
            frozenset(("host:lease",)),
            observed_at,
            tuple(history),
        )
        self.issued = {}
        self.receipt_by_handle = {}
        self.consumed = set()
        self.aggregate_by_handle = {}
        self.measurement_receipts = set()
        self.resolve_calls = []
        self.brackets = {}

    def _check(self, handle):
        if handle is not self.handle:
            raise CampaignMetricsError("foreign registry handle")

    def resolve(self, handle, use):
        self._check(handle)
        if (
            use.protocol_digest != self.snapshot.protocol_digest
            or use.stage != self.snapshot.stage_evidence.stage
        ):
            raise CampaignMetricsError("foreign use")
        if (
            use.state_admission_digest is not None
            and use.state_admission_digest != self.snapshot.admission_digest
        ):
            raise CampaignMetricsError("foreign state")
        self.resolve_calls.append(use.operation)
        return replace(self.snapshot, seal_history=self.snapshot.seal_history)

    def open_bracket(self, handle, protocol_digest, stage, track):
        self._check(handle)
        if (
            protocol_digest != self.snapshot.protocol_digest
            or stage != self.snapshot.stage_evidence.stage
        ):
            raise CampaignMetricsError("foreign bracket open")
        return self.fixture_state(stage=stage, track=track)

    def fixture_state(self, *, stage=None, track=None, **changes):
        bracket = BracketSnapshot(
            self.snapshot.protocol_digest,
            self.snapshot.admission_digest,
            stage or self.snapshot.stage_evidence.stage,
            track
            or (
                "builder-component"
                if self.snapshot.stage_evidence.stage == "original"
                else "whole-campaign"
            ),
            **changes,
        )
        opaque = _Handle()
        self.brackets[id(opaque)] = [opaque, bracket, True]
        return BracketState(opaque)

    def bracket_snapshot(self, state):
        record = self.brackets.get(id(state.opaque_handle))
        if record is None:
            raise CampaignMetricsError("unknown bracket")
        return record[1]

    def resolve_bracket(self, handle, state_handle, protocol_digest, operation):
        self._check(handle)
        record = self.brackets.get(id(state_handle))
        if record is None or record[0] is not state_handle or not record[2]:
            raise CampaignMetricsError("foreign, forged, or superseded bracket handle")
        bracket = record[1]
        if bracket.protocol_digest != protocol_digest:
            raise CampaignMetricsError("foreign bracket protocol")
        return bracket

    def commit_bracket(self, handle, state_handle, expected_bracket_digest, transition):
        self._check(handle)
        record = self.brackets.get(id(state_handle))
        if (
            record is None
            or record[0] is not state_handle
            or not record[2]
            or record[1].bracket_digest != expected_bracket_digest
        ):
            raise CampaignMetricsError("bracket compare-and-swap failed")
        prior = record[1]
        next_snapshot = BracketSnapshot(
            prior.protocol_digest,
            prior.admission_digest,
            prior.stage,
            prior.track,
            transition.round_number,
            transition.losses,
            transition.byes,
            transition.inconclusive,
            transition.quarantined,
            transition.terminal,
            transition.applied_receipt_digests,
        )
        record[2] = False
        opaque = _Handle()
        self.brackets[id(opaque)] = [opaque, next_snapshot, True]
        return BracketState(opaque)

    def issue_round(self, handle, plans):
        self._check(handle)
        results = []
        for plan in plans:
            key = plan.plan_digest
            if key not in self.issued:
                receipt = IssuedReceipt(_Handle(), plan, self.snapshot.observed_at)
                self.issued[key] = receipt
                self.receipt_by_handle[id(receipt.opaque_handle)] = receipt
            results.append(self.issued[key])
        return tuple(results)

    def consume_round(self, handle, state_handle, request):
        self._check(handle)
        record = self.brackets.get(id(state_handle))
        if record is None or record[0] is not state_handle or not record[2]:
            raise CampaignMetricsError("foreign, forged, or superseded bracket handle")
        bracket = record[1]
        if (
            request.admission_digest,
            request.protocol_digest,
            request.stage,
            request.expected_bracket_digest,
        ) != (
            bracket.admission_digest,
            bracket.protocol_digest,
            bracket.stage,
            bracket.bracket_digest,
        ):
            raise CampaignMetricsError(
                "round consumption is not bound to bracket state"
            )
        submitted = {
            id(result.receipt.opaque_handle): result.receipt
            for result in request.results
        }
        issued = {
            id(receipt.opaque_handle): receipt
            for receipt in self.issued.values()
            if receipt.plan.round_number == request.round_number
            and receipt.plan.bracket_digest == request.expected_bracket_digest
        }
        if set(submitted) != set(issued):
            raise CampaignMetricsError("registry exact-set mismatch")
        for receipt_handle, receipt in submitted.items():
            stored = self.receipt_by_handle.get(receipt_handle)
            if (
                stored is None
                or stored.plan != receipt.plan
                or stored.receipt_digest != receipt.receipt_digest
            ):
                raise CampaignMetricsError("registry receipt substitution")
            if receipt_handle in self.consumed:
                raise CampaignMetricsError("append-only receipt replay")
        next_state = self.commit_bracket(
            handle, state_handle, request.expected_bracket_digest, request.transition
        )
        self.consumed.update(submitted)
        self.measurement_receipts.update(
            receipt.receipt_digest for receipt in submitted.values()
        )
        return next_state

    def append_seals(
        self, handle, expected_history_digest, expected_observed_at, seals
    ):
        self._check(handle)
        if (
            expected_history_digest != canonical_digest(self.snapshot.seal_history)
            or expected_observed_at != self.snapshot.observed_at
        ):
            raise CampaignMetricsError("seal compare-and-swap failed")
        evidence = self.snapshot.stage_evidence
        if (
            evidence.stage == "final"
            and self.snapshot.observed_at >= evidence.holdout_opened_at
        ):
            raise CampaignMetricsError("registry final seal window closed")
        self.snapshot = replace(
            self.snapshot, seal_history=self.snapshot.seal_history + tuple(seals)
        )

    def record_aggregate(self, handle, evidence, observations):
        self._check(handle)
        if any(
            row.receipt_digest not in self.measurement_receipts for row in observations
        ):
            raise CampaignMetricsError("aggregate references an unconsumed receipt")
        opaque = _Handle()
        receipt = AggregateReceipt(opaque, canonical_digest(evidence))
        self.aggregate_by_handle[id(opaque)] = evidence
        return receipt

    def resolve_aggregate(self, handle, receipt):
        self._check(handle)
        evidence = self.aggregate_by_handle.get(id(receipt.opaque_handle))
        if evidence is None or receipt.aggregate_digest != canonical_digest(evidence):
            raise CampaignMetricsError("foreign aggregate")
        return evidence

    def fixture_aggregate(self, evidence):
        """Install malicious host-returned evidence for decision-boundary tests."""
        opaque = _Handle()
        receipt = AggregateReceipt(opaque, canonical_digest(evidence))
        self.aggregate_by_handle[id(opaque)] = evidence
        return receipt


def admitted(
    stage="original",
    *,
    p=None,
    evidence=None,
    lease_record=None,
    observed_at=20,
    history=(),
):
    p = p or protocol()
    evidence = evidence or stage_evidence(p, stage)
    lease_record = lease_record or lease(p, stage)
    registry = _FixtureRegistry(
        p, evidence, lease_record, observed_at=observed_at, history=history
    )
    state = registry.open_bracket(
        registry.handle,
        p.protocol_digest,
        stage,
        "builder-component" if stage == "original" else "whole-campaign",
    )
    return p, evidence, registry, state


class CampaignMetricsTests(unittest.TestCase):
    def test_production_module_has_no_minter_key_token_or_verifier(self):
        for name in (
            "admit_protocol",
            "AdmittedProtocol",
            "EvidenceVerifier",
            "SignedCustodyEnvelope",
            "_ADMISSION_TOKEN",
        ):
            self.assertFalse(hasattr(metrics, name), name)

    def test_principal_independence_is_not_caller_optional(self):
        for changes in (
            {"evaluator_id": "builder:a"},
            {"custodian_id": "builder:b"},
            {"evaluator_id": "champion:current"},
            {"custodian_id": PRINCIPALS.evaluator_id},
            {"builder_ids": ()},
            {"affected_champion_ids": ()},
            {"builder_ids": ("builder:a", "champion:current")},
            {"affected_champion_ids": ("champion:current", "builder:a")},
        ):
            with self.assertRaises(CampaignMetricsError):
                replace(PRINCIPALS, **changes)

    def test_checked_in_open_and_relabelled_json_are_inert(self):
        path = Path("docs/benchmarks/whole-os-match-protocol.json")
        inspection = load_match_protocol_for_inspection(path)
        self.assertTrue(inspection.blockers)
        with self.assertRaises(CampaignMetricsError):
            load_match_protocol(path)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["status"] = "CLOSED_ADMISSION_CANDIDATE"
        with tempfile.TemporaryDirectory() as folder:
            forged = Path(folder) / "forged.json"
            forged.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CampaignMetricsError):
                load_match_protocol(forged)

    def test_fixture_closed_document_round_trips_without_becoming_authority(self):
        p = protocol()
        document = {
            "kind": "hive-mind-closed-match-protocol",
            "status": "CLOSED_ADMISSION_CANDIDATE",
            "external_evidence_obligations": [],
            "protocol_digest": p.protocol_digest,
            **plain(p.to_document()),
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "closed.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            loaded = load_match_protocol(path)
        self.assertEqual(loaded.protocol_digest, p.protocol_digest)
        state = BracketState(object())
        with self.assertRaises(CampaignMetricsError):
            state.schedule(
                loaded,
                registry=_FixtureRegistry(
                    p, stage_evidence(p, "original"), lease(p, "original")
                ),
                admission_handle=object(),
            )

    def test_fixture_protocol_is_deeply_frozen_and_all_fields_digest_bound(self):
        p = protocol()
        before = p.protocol_digest
        with self.assertRaises(TypeError):
            p.entrant_recipes["MB0"]["track"] = "whole-campaign"
        changed = dict(p.experiment_manifest)
        changed["selection_seed"] += 1
        p2 = replace(p, experiment_manifest=changed)
        self.assertNotEqual(before, p2.protocol_digest)
        duplicate = dict(p.entrant_recipes)
        duplicate["MB1"] = dict(duplicate["MB0"])
        duplicate["MB1"]["track"] = "builder-component"
        with self.assertRaises(CampaignMetricsError):
            replace(p, entrant_recipes=duplicate)

    def test_metric_numeric_unknown_and_summary_controls(self):
        base = ("f", "t", "v", D, D, D, D, "eligible", "not_attempted")
        for bad in (-1, math.nan, math.inf, True):
            with self.assertRaises(CampaignMetricsError):
                AttemptMetric(*base, bad, 0, 0, None, "unknown", None, "unknown")
        with self.assertRaises(CampaignMetricsError):
            AttemptMetric(*base, 0, 0, 0, None, "unknown", 1, "billed")
        row = AttemptMetric(*base, None, None, None, None, "unknown", None, "unknown")
        self.assertEqual(summarize_attempts((row,))["eligible_not_attempted"], 1)
        with self.assertRaises(CampaignMetricsError):
            DescriptiveInterval(None, None, 1, 0)
        with self.assertRaises(CampaignMetricsError):
            DescriptiveInterval(0, 1, -1, 1)

    def test_arbitrary_and_cross_registry_handles_cannot_execute(self):
        p, evidence, registry, state = admitted()
        with self.assertRaises(CampaignMetricsError):
            state.schedule(p, registry=registry, admission_handle=object())
        other = _FixtureRegistry(p, evidence, lease(p, "original"))
        with self.assertRaises(CampaignMetricsError):
            state.schedule(p, registry=other, admission_handle=registry.handle)

    def test_bracket_progress_is_registry_owned_and_rewind_or_field_forgery_rejects(
        self,
    ):
        p, _, registry, state = admitted()
        self.assertEqual(tuple(BracketState.__dataclass_fields__), ("opaque_handle",))
        for changes in (
            {"losses": {"MB0": 3}},
            {"quarantined": frozenset(p.entrant_recipes)},
            {"round_number": 24},
            {"terminal": "one_survivor"},
        ):
            with self.assertRaises(TypeError):
                BracketState(object(), **changes)
        with self.assertRaises(CampaignMetricsError):
            BracketState(object()).schedule(
                p, registry=registry, admission_handle=registry.handle
            )
        scheduled = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        advanced = state.apply(
            p,
            tuple(ReceiptOutcome(receipt, "DRAW") for receipt in scheduled.receipts),
            registry=registry,
            admission_handle=registry.handle,
        )
        self.assertEqual(registry.bracket_snapshot(advanced).round_number, 1)
        with self.assertRaises(CampaignMetricsError):
            state.schedule(p, registry=registry, admission_handle=registry.handle)
        with self.assertRaises(CampaignMetricsError):
            state.apply(
                p,
                tuple(
                    ReceiptOutcome(receipt, "DRAW") for receipt in scheduled.receipts
                ),
                registry=registry,
                admission_handle=registry.handle,
            )

    def test_full_admission_identity_and_revalidation(self):
        p, evidence, registry, state = admitted()
        self.assertTrue(
            state.schedule(
                p, registry=registry, admission_handle=registry.handle
            ).receipts
        )
        mutations = (
            replace(evidence, seed=evidence.seed + 1),
            replace(evidence, task_manifest_digest=digest("other tasks")),
            replace(evidence, family_manifest_digest=digest("other families")),
            replace(evidence, block_digest=digest("other block")),
            replace(
                evidence, principals=replace(PRINCIPALS, evaluator_id="evaluator:other")
            ),
        )
        for changed in mutations:
            new_digest = canonical_digest(
                {
                    "protocol_digest": p.protocol_digest,
                    "stage_evidence": changed,
                    "lease": registry.snapshot.lease,
                }
            )
            self.assertNotEqual(registry.snapshot.admission_digest, new_digest)
            prior = registry.snapshot
            registry.snapshot = replace(prior, stage_evidence=changed)
            with self.assertRaises(CampaignMetricsError):
                state.schedule(p, registry=registry, admission_handle=registry.handle)
            registry.snapshot = prior
        self.assertIn("schedule", registry.resolve_calls)

    def test_lease_issuer_scope_expiry_revocation_and_operation_rechecked(self):
        p = protocol()
        evidence = stage_evidence(p, "original")
        cases = (
            (lease(p, "original", issued_by="builder:a"), 20, CampaignMetricsError),
            (lease(p, "original", expires_at=10), 20, None),
            (lease(p, "original", revoked_at=15), 20, None),
            (lease(p, "original", operations=("seal",)), 20, CampaignMetricsError),
        )
        for record, now, error in cases:
            registry = _FixtureRegistry(p, evidence, record, observed_at=now)
            state = registry.open_bracket(
                registry.handle, p.protocol_digest, "original", "builder-component"
            )
            if error:
                with self.assertRaises(error):
                    state.schedule(
                        p, registry=registry, admission_handle=registry.handle
                    )
            else:
                self.assertEqual(
                    state.schedule(
                        p, registry=registry, admission_handle=registry.handle
                    ).terminal,
                    "lease_exhausted",
                )

    def test_exact_receipts_full_round_and_durable_replay(self):
        p, _, registry, state = admitted()
        scheduled = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(len(scheduled.receipts), 2)
        with self.assertRaises(CampaignMetricsError):
            state.apply(p, (), registry=registry, admission_handle=registry.handle)
        with self.assertRaises(CampaignMetricsError):
            state.apply(
                p,
                (ReceiptOutcome(scheduled.receipts[0], "LEFT"),),
                registry=registry,
                admission_handle=registry.handle,
            )
        first = scheduled.receipts[0]
        for changed_plan in (
            replace(first.plan, left=first.plan.right, right=first.plan.left),
            replace(first.plan, seed=first.plan.seed + 1),
            replace(first.plan, evaluator_id="evaluator:other"),
            replace(first.plan, custodian_id="custodian:other"),
            replace(first.plan, bracket_digest=digest("other bracket")),
            replace(first.plan, block_digest=digest("other block")),
            replace(first.plan, task_id="task-29"),
        ):
            tampered = IssuedReceipt(first.opaque_handle, changed_plan, first.issued_at)
            substituted = (ReceiptOutcome(tampered, "LEFT"),) + tuple(
                ReceiptOutcome(receipt, "LEFT") for receipt in scheduled.receipts[1:]
            )
            with self.assertRaises(CampaignMetricsError):
                state.apply(
                    p, substituted, registry=registry, admission_handle=registry.handle
                )
        changed_digest = IssuedReceipt(
            first.opaque_handle, first.plan, first.issued_at + 1
        )
        substituted = (ReceiptOutcome(changed_digest, "LEFT"),) + tuple(
            ReceiptOutcome(receipt, "LEFT") for receipt in scheduled.receipts[1:]
        )
        with self.assertRaises(CampaignMetricsError):
            state.apply(
                p, substituted, registry=registry, admission_handle=registry.handle
            )
        outcomes = tuple(
            ReceiptOutcome(receipt, "LEFT") for receipt in scheduled.receipts
        )
        next_state = state.apply(
            p, outcomes, registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(registry.bracket_snapshot(next_state).round_number, 1)
        with self.assertRaises(CampaignMetricsError):
            state.apply(
                p, outcomes, registry=registry, admission_handle=registry.handle
            )
        tampered_plan = replace(scheduled.receipts[0].plan, task_id="task-29")
        tampered = IssuedReceipt(
            scheduled.receipts[0].opaque_handle,
            tampered_plan,
            scheduled.receipts[0].issued_at,
        )
        with self.assertRaises(CampaignMetricsError):
            ReceiptOutcome(tampered, "BYE")

    def test_zero_odd_bye_no_schedulable_and_one_survivor(self):
        p, _, registry, state = admitted("hybrid")
        zero = registry.fixture_state(quarantined=frozenset(p.hybrid_recipes))
        self.assertEqual(
            zero.schedule(
                p, registry=registry, admission_handle=registry.handle
            ).terminal,
            "no_schedulable_pairs",
        )
        one = registry.fixture_state(quarantined=frozenset(("MH2", "MH3", "MH4")))
        self.assertEqual(
            one.schedule(
                p, registry=registry, admission_handle=registry.handle
            ).terminal,
            "one_survivor",
        )
        odd = registry.fixture_state(quarantined=frozenset(("MH4",)))
        scheduled = odd.schedule(p, registry=registry, admission_handle=registry.handle)
        self.assertEqual(sum(receipt.plan.bye for receipt in scheduled.receipts), 1)
        results = tuple(
            ReceiptOutcome(receipt, "BYE" if receipt.plan.bye else "INCONCLUSIVE")
            for receipt in scheduled.receipts
        )
        advanced = odd.apply(
            p, results, registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(sum(registry.bracket_snapshot(advanced).byes.values()), 1)
        meetings = {
            frozenset(pair): 2
            for pair in (
                ("MH1", "MH2"),
                ("MH1", "MH3"),
                ("MH1", "MH4"),
                ("MH2", "MH3"),
                ("MH2", "MH4"),
                ("MH3", "MH4"),
            )
        }
        stopped = registry.fixture_state(inconclusive=meetings)
        self.assertEqual(
            stopped.schedule(
                p, registry=registry, admission_handle=registry.handle
            ).terminal,
            "no_schedulable_pairs",
        )

    def test_quarantine_both_and_third_loss(self):
        p, _, registry, state = admitted()
        with self.assertRaises(CampaignMetricsError):
            registry.fixture_state(losses={"MB0": -1})
        state = registry.fixture_state(losses={"MB1": 2})
        scheduled = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        outcomes = []
        for receipt in scheduled.receipts:
            if receipt.plan.left == "MB1":
                outcome = "RIGHT"
            elif receipt.plan.right == "MB1":
                outcome = "LEFT"
            else:
                outcome = "QUARANTINE_BOTH"
            outcomes.append(ReceiptOutcome(receipt, outcome))
        advanced = state.apply(
            p, outcomes, registry=registry, admission_handle=registry.handle
        )
        advanced_snapshot = registry.bracket_snapshot(advanced)
        self.assertEqual(advanced_snapshot.losses.get("MB1"), 3)
        self.assertTrue(advanced_snapshot.quarantined)
        self.assertNotIn(
            "MB1",
            {
                r.plan.left
                for r in advanced.schedule(
                    p, registry=registry, admission_handle=registry.handle
                ).receipts
            },
        )

    def test_final_requires_prior_qualification_same_regime_and_preopen_seals(self):
        p = protocol()
        original_evidence = stage_evidence(p, "original", stage_opened_at=2)
        hybrid_evidence = stage_evidence(p, "hybrid", stage_opened_at=3)
        original_seal = seal_for(
            p, original_evidence, "MC0", 1, digest("candidate-MC0"), 5
        )
        hybrid_seal = seal_for(p, hybrid_evidence, "MH1", 2, digest("candidate-MH1"), 6)
        finalists = (
            FinalistBinding(
                "MC0",
                original_seal.candidate_digest,
                original_seal.recipe_digest,
                "whole-default",
                "original",
                original_seal.seal_digest,
            ),
            FinalistBinding(
                "MH1",
                hybrid_seal.candidate_digest,
                hybrid_seal.recipe_digest,
                "whole-default",
                "hybrid",
                hybrid_seal.seal_digest,
            ),
        )
        final_evidence = stage_evidence(
            p, "final", final_pair=finalists, stage_opened_at=10, holdout_opened_at=20
        )
        final_a = seal_for(
            p, final_evidence, "MC0", 3, original_seal.candidate_digest, 11
        )
        final_b = seal_for(
            p, final_evidence, "MH1", 4, hybrid_seal.candidate_digest, 12
        )
        registry = _FixtureRegistry(
            p,
            final_evidence,
            lease(p, "final"),
            observed_at=15,
            history=(original_seal, hybrid_seal),
        )
        validate_and_append_seals(
            p, (final_a, final_b), registry=registry, admission_handle=registry.handle
        )
        registry.snapshot = replace(registry.snapshot, observed_at=21)
        state = registry.open_bracket(
            registry.handle, p.protocol_digest, "final", "whole-campaign"
        )
        scheduled = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(
            {scheduled.receipts[0].plan.left, scheduled.receipts[0].plan.right},
            {"MC0", "MH1"},
        )
        self.assertEqual(
            scheduled.receipts[0].plan.block_digest, final_evidence.block_digest
        )
        final_rows = []
        for task in final_evidence.tasks:
            for repetition in range(3):
                receipt_digest = digest(["final-measurement", task.task_id, repetition])
                registry.measurement_receipts.add(receipt_digest)
                final_rows.append(
                    FamilyObservation(
                        task.family_id, task.task_id, repetition, receipt_digest, 0.0
                    )
                )
        final_aggregates = []
        for metric, value in (
            ("success_difference", 0.0),
            ("cost_ratio", 0.8),
            ("time_ratio", 0.8),
        ):
            rows = tuple(replace(row, value=value) for row in final_rows)
            final_aggregates.append(
                stage_paired_bootstrap(
                    p,
                    metric,
                    "MC0",
                    "MH1",
                    rows,
                    left_hard_gates=True,
                    right_hard_gates=True,
                    registry=registry,
                    admission_handle=registry.handle,
                )
            )
        self.assertTrue(
            all(
                isinstance(aggregate, AggregateReceipt)
                for aggregate in final_aggregates
            )
        )
        self.assertEqual(
            decide_match(
                p,
                *final_aggregates,
                registry=registry,
                admission_handle=registry.handle,
            ),
            "LEFT",
        )
        expected_shape = observation_shape(final_evidence)

        def forged_final(shape, family_count):
            receipts = []
            for metric, interval in (
                (
                    "success_difference",
                    DescriptiveInterval(0.1, 0.01, 0.2, family_count),
                ),
                ("cost_ratio", DescriptiveInterval(0.8, 0.7, 0.9, family_count)),
                ("time_ratio", DescriptiveInterval(0.8, 0.7, 0.9, family_count)),
            ):
                record = AggregateEvidence(
                    registry.snapshot.admission_digest,
                    p.protocol_digest,
                    "final",
                    "whole-campaign",
                    "whole-default",
                    final_evidence.block_digest,
                    final_evidence.task_manifest_digest,
                    final_evidence.family_manifest_digest,
                    shape,
                    metric,
                    "MC0",
                    "MH1",
                    digest(["forged-final", metric, family_count, shape]),
                    interval,
                    True,
                    True,
                )
                receipts.append(registry.fixture_aggregate(record))
            return receipts

        with self.assertRaises(CampaignMetricsError):
            decide_match(
                p,
                *forged_final(expected_shape, 1),
                registry=registry,
                admission_handle=registry.handle,
            )
        with self.assertRaises(CampaignMetricsError):
            decide_match(
                p,
                *forged_final(expected_shape[:-1], 30),
                registry=registry,
                admission_handle=registry.handle,
            )
        wrong_seed_shape = (
            replace(expected_shape[0], seed=expected_shape[0].seed + 1000),
        ) + expected_shape[1:]
        with self.assertRaises(CampaignMetricsError):
            decide_match(
                p,
                *forged_final(wrong_seed_shape, 30),
                registry=registry,
                admission_handle=registry.handle,
            )
        base_record = registry.resolve_aggregate(registry.handle, final_aggregates[0])
        with self.assertRaises(CampaignMetricsError):
            replace(
                base_record, observation_shape=expected_shape + (expected_shape[0],)
            )
        repeated_repetition = expected_shape[:-1] + (
            replace(expected_shape[-1], repetition=expected_shape[-2].repetition),
        )
        with self.assertRaises(CampaignMetricsError):
            replace(base_record, observation_shape=repeated_repetition)
        for wrong_pair in (("MC1", "MH2"), ("MB0", "MH1")):
            with self.assertRaises(CampaignMetricsError):
                stage_paired_bootstrap(
                    p,
                    "success_difference",
                    *wrong_pair,
                    final_rows,
                    left_hard_gates=True,
                    right_hard_gates=True,
                    registry=registry,
                    admission_handle=registry.handle,
                )
        for left, right, track, regime in (
            ("MC1", "MH2", "whole-campaign", "whole-default"),
            ("MB0", "MH1", "builder-component", "component-default"),
        ):
            wrong_evidence = AggregateEvidence(
                registry.snapshot.admission_digest,
                p.protocol_digest,
                "final",
                track,
                regime,
                final_evidence.block_digest,
                final_evidence.task_manifest_digest,
                final_evidence.family_manifest_digest,
                observation_shape(final_evidence),
                "success_difference",
                left,
                right,
                digest(["wrong-final-observations", left, right]),
                DescriptiveInterval(0.1, 0.01, 0.2, 30),
                True,
                True,
            )
            wrong_receipts = []
            for metric, interval in (
                ("success_difference", wrong_evidence.interval),
                ("cost_ratio", DescriptiveInterval(0.8, 0.7, 0.9, 30)),
                ("time_ratio", DescriptiveInterval(0.8, 0.7, 0.9, 30)),
            ):
                wrong_receipts.append(
                    registry.fixture_aggregate(
                        replace(wrong_evidence, metric=metric, interval=interval)
                    )
                )
            with self.assertRaises(CampaignMetricsError):
                decide_match(
                    p,
                    *wrong_receipts,
                    registry=registry,
                    admission_handle=registry.handle,
                )
        bad_pair = (replace(finalists[0], variant_id="MB0"), finalists[1])
        bad_evidence = stage_evidence(
            p, "final", final_pair=bad_pair, stage_opened_at=10, holdout_opened_at=20
        )
        bad_registry = _FixtureRegistry(
            p,
            bad_evidence,
            lease(p, "final"),
            observed_at=15,
            history=(original_seal, hybrid_seal, final_a, final_b),
        )
        bad_state = bad_registry.open_bracket(
            bad_registry.handle, p.protocol_digest, "final", "whole-campaign"
        )
        with self.assertRaises(CampaignMetricsError):
            bad_state.schedule(
                p, registry=bad_registry, admission_handle=bad_registry.handle
            )
        same = replace(
            finalists[1],
            variant_id="MC0",
            qualification_stage="original",
            qualification_seal_digest=original_seal.seal_digest,
            recipe_digest=original_seal.recipe_digest,
            candidate_digest=original_seal.candidate_digest,
        )
        same_evidence = stage_evidence(
            p,
            "final",
            final_pair=(finalists[0], same),
            stage_opened_at=10,
            holdout_opened_at=20,
        )
        same_registry = _FixtureRegistry(
            p,
            same_evidence,
            lease(p, "final"),
            observed_at=15,
            history=(original_seal, hybrid_seal, final_a, final_b),
        )
        with self.assertRaises(CampaignMetricsError):
            same_registry.open_bracket(
                same_registry.handle, p.protocol_digest, "final", "whole-campaign"
            ).schedule(p, registry=same_registry, admission_handle=same_registry.handle)

    def test_final_seal_operation_rejects_trusted_time_at_or_after_holdout_open(self):
        p = protocol()
        original_evidence = stage_evidence(p, "original", stage_opened_at=2)
        hybrid_evidence = stage_evidence(p, "hybrid", stage_opened_at=3)
        original_seal = seal_for(
            p, original_evidence, "MC0", 1, digest("candidate-MC0"), 5
        )
        hybrid_seal = seal_for(p, hybrid_evidence, "MH1", 2, digest("candidate-MH1"), 6)
        finalists = (
            FinalistBinding(
                "MC0",
                original_seal.candidate_digest,
                original_seal.recipe_digest,
                "whole-default",
                "original",
                original_seal.seal_digest,
            ),
            FinalistBinding(
                "MH1",
                hybrid_seal.candidate_digest,
                hybrid_seal.recipe_digest,
                "whole-default",
                "hybrid",
                hybrid_seal.seal_digest,
            ),
        )
        evidence = stage_evidence(
            p, "final", final_pair=finalists, stage_opened_at=10, holdout_opened_at=20
        )
        late_registry = _FixtureRegistry(
            p,
            evidence,
            lease(p, "final"),
            observed_at=21,
            history=(original_seal, hybrid_seal),
        )
        backdated = (
            seal_for(p, evidence, "MC0", 3, original_seal.candidate_digest, 11),
            seal_for(p, evidence, "MH1", 4, hybrid_seal.candidate_digest, 12),
        )
        with self.assertRaises(CampaignMetricsError):
            validate_and_append_seals(
                p,
                backdated,
                registry=late_registry,
                admission_handle=late_registry.handle,
            )
        self.assertEqual(
            late_registry.snapshot.seal_history, (original_seal, hybrid_seal)
        )

        class _OpeningRaceRegistry(_FixtureRegistry):
            def append_seals(
                self, handle, expected_history_digest, expected_observed_at, seals
            ):
                self.snapshot = replace(self.snapshot, observed_at=20)
                return super().append_seals(
                    handle, expected_history_digest, expected_observed_at, seals
                )

        racing_registry = _OpeningRaceRegistry(
            p,
            evidence,
            lease(p, "final"),
            observed_at=19,
            history=(original_seal, hybrid_seal),
        )
        with self.assertRaises(CampaignMetricsError):
            validate_and_append_seals(
                p,
                backdated,
                registry=racing_registry,
                admission_handle=racing_registry.handle,
            )
        self.assertEqual(
            racing_registry.snapshot.seal_history, (original_seal, hybrid_seal)
        )

    def test_seals_require_order_time_evaluator_stage_block_and_custody(self):
        p, evidence, registry, _ = admitted()
        good = seal_for(p, evidence, "MB0", 1, digest("candidate"), 11)
        validate_and_append_seals(
            p, (good,), registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(registry.snapshot.seal_history, (good,))
        for bad in (
            replace(good, sequence=1, sealed_at=12),
            replace(good, sequence=2, evaluator_id="builder:a", sealed_at=12),
            replace(good, sequence=2, custodian_id="builder:b", sealed_at=12),
            replace(good, sequence=2, block_digest=digest("wrong"), sealed_at=12),
            replace(good, sequence=2, stage="hybrid", sealed_at=12),
            replace(good, sequence=2, sealed_at=9),
            replace(good, sequence=2, sealed_at=21),
        ):
            with self.assertRaises(CampaignMetricsError):
                validate_and_append_seals(
                    p, (bad,), registry=registry, admission_handle=registry.handle
                )
        with self.assertRaises(CampaignMetricsError):
            replace(good, sequence=2, sealed_at="not-a-time")

    def test_stage_aggregation_exact_membership_and_registry_bound_decision(self):
        p, evidence, registry, state = admitted()
        scheduled = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        state.apply(
            p,
            tuple(ReceiptOutcome(receipt, "DRAW") for receipt in scheduled.receipts),
            registry=registry,
            admission_handle=registry.handle,
        )
        observation_receipts = {
            task.task_id: digest(["measurement", task.task_id, 0])
            for task in evidence.tasks
        }
        registry.measurement_receipts.update(observation_receipts.values())
        observations = tuple(
            FamilyObservation(
                task.family_id, task.task_id, 0, observation_receipts[task.task_id], 0.0
            )
            for task in evidence.tasks
        )
        receipts = []
        for metric, value in (
            ("success_difference", 0.0),
            ("cost_ratio", 0.8),
            ("time_ratio", 1.0),
        ):
            rows = tuple(replace(row, value=value) for row in observations)
            receipts.append(
                stage_paired_bootstrap(
                    p,
                    metric,
                    "MB0",
                    "MB1",
                    rows,
                    left_hard_gates=True,
                    right_hard_gates=True,
                    registry=registry,
                    admission_handle=registry.handle,
                )
            )
        self.assertTrue(
            all(
                registry.resolve_aggregate(registry.handle, receipt).observation_shape
                == observation_shape(evidence)
                for receipt in receipts
            )
        )
        self.assertEqual(
            decide_match(
                p, *receipts, registry=registry, admission_handle=registry.handle
            ),
            "LEFT",
        )
        with self.assertRaises(CampaignMetricsError):
            stage_paired_bootstrap(
                p,
                "success_difference",
                "MB0",
                "MB1",
                observations[:-1],
                left_hard_gates=True,
                right_hard_gates=True,
                registry=registry,
                admission_handle=registry.handle,
            )
        for metric in ("cost_ratio", "time_ratio"):
            for invalid in (0.0, -2.0):
                with self.assertRaises(CampaignMetricsError):
                    stage_paired_bootstrap(
                        p,
                        metric,
                        "MB0",
                        "MB1",
                        tuple(replace(row, value=invalid) for row in observations),
                        left_hard_gates=True,
                        right_hard_gates=True,
                        registry=registry,
                        admission_handle=registry.handle,
                    )
        raw = paired_family_bootstrap(
            {task.family_id: (0.0,) for task in evidence.tasks}, seed=1
        )
        with self.assertRaises((CampaignMetricsError, AttributeError)):
            decide_match(
                p, raw, raw, raw, registry=registry, admission_handle=registry.handle
            )
        raw_final_like = paired_family_bootstrap(
            {f"family-{index:02d}": (0.0,) for index in range(30)}, seed=1
        )
        with self.assertRaises(CampaignMetricsError):
            decide_match(
                p,
                raw_final_like,
                raw_final_like,
                raw_final_like,
                registry=registry,
                admission_handle=registry.handle,
            )

    def test_registry_bound_decision_symmetry_noninferiority_and_quarantine(self):
        p, evidence, registry, _ = admitted()

        def decision(success_i, cost_i, time_i, gates=(True, True), shape=None):
            receipts = []
            for metric, interval in (
                ("success_difference", success_i),
                ("cost_ratio", cost_i),
                ("time_ratio", time_i),
            ):
                aggregate = AggregateEvidence(
                    registry.snapshot.admission_digest,
                    p.protocol_digest,
                    "original",
                    "builder-component",
                    "component-default",
                    evidence.block_digest,
                    evidence.task_manifest_digest,
                    evidence.family_manifest_digest,
                    shape or observation_shape(evidence),
                    metric,
                    "MB0",
                    "MB1",
                    digest([metric, interval.to_document(), gates]),
                    interval,
                    *gates,
                )
                opaque = _Handle()
                receipt = AggregateReceipt(opaque, canonical_digest(aggregate))
                registry.aggregate_by_handle[id(opaque)] = aggregate
                receipts.append(receipt)
            return decide_match(
                p, *receipts, registry=registry, admission_handle=registry.handle
            )

        symmetric = DescriptiveInterval(0, -0.04, 0.04, 12)
        self.assertEqual(
            decision(
                DescriptiveInterval(0, -0.04, 0.20, 12),
                DescriptiveInterval(0.8, 0.7, 0.9, 12),
                DescriptiveInterval(1.0, 0.9, 1.05, 12),
            ),
            "DRAW",
        )
        self.assertEqual(
            decision(
                symmetric,
                DescriptiveInterval(1.0, 0.9, 1.1, 12),
                DescriptiveInterval(0.8, 0.7, 0.9, 12),
            ),
            "LEFT",
        )
        self.assertEqual(
            decision(
                symmetric,
                DescriptiveInterval(1.2, 1.1, 1.3, 12),
                DescriptiveInterval(1.0, 0.95, 1.05, 12),
            ),
            "RIGHT",
        )
        self.assertEqual(
            decision(
                symmetric,
                DescriptiveInterval(1.0, 0.9, 1.1, 12),
                DescriptiveInterval(1.0, 0.9, 1.1, 12),
                (False, False),
            ),
            "QUARANTINE_BOTH",
        )
        for invalid in (
            DescriptiveInterval(-2.0, -3.0, -1.0, 12),
            DescriptiveInterval(0.0, 0.0, 0.0, 12),
        ):
            with self.assertRaises(CampaignMetricsError):
                decision(symmetric, invalid, DescriptiveInterval(1.0, 0.9, 1.1, 12))
        with self.assertRaises(CampaignMetricsError):
            decision(
                DescriptiveInterval(0.1, 0.01, 0.2, 1),
                DescriptiveInterval(0.8, 0.7, 0.9, 1),
                DescriptiveInterval(0.8, 0.7, 0.9, 1),
            )
        with self.assertRaises(CampaignMetricsError):
            decision(
                symmetric,
                DescriptiveInterval(0.8, 0.7, 0.9, 12),
                DescriptiveInterval(0.8, 0.7, 0.9, 12),
                shape=observation_shape(evidence)[:-1],
            )

    def test_every_execution_surface_revalidates_lease(self):
        p, evidence, registry, state = admitted()
        scheduled = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        outcomes = tuple(
            ReceiptOutcome(receipt, "DRAW") for receipt in scheduled.receipts
        )
        state = state.apply(
            p, outcomes, registry=registry, admission_handle=registry.handle
        )
        seal = seal_for(p, evidence, "MB0", 1, digest("candidate"), 20)
        validate_and_append_seals(
            p, (seal,), registry=registry, admission_handle=registry.handle
        )
        receipt_digests = {
            task.task_id: digest(["measurement", task.task_id])
            for task in evidence.tasks
        }
        registry.measurement_receipts.update(receipt_digests.values())
        rows = tuple(
            FamilyObservation(
                task.family_id, task.task_id, 0, receipt_digests[task.task_id], 0.0
            )
            for task in evidence.tasks
        )
        aggregates = [
            stage_paired_bootstrap(
                p,
                metric,
                "MB0",
                "MB1",
                tuple(
                    replace(row, value=0.0 if metric == "success_difference" else 1.0)
                    for row in rows
                ),
                left_hard_gates=True,
                right_hard_gates=True,
                registry=registry,
                admission_handle=registry.handle,
            )
            for metric in ("success_difference", "cost_ratio", "time_ratio")
        ]
        decide_match(
            p, *aggregates, registry=registry, admission_handle=registry.handle
        )
        self.assertTrue(
            set(("schedule", "apply", "seal", "aggregate", "decide"))
            <= set(registry.resolve_calls)
        )
        registry.snapshot = replace(
            registry.snapshot, observed_at=registry.snapshot.lease.expires_at
        )
        expired_schedule = state.schedule(
            p, registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(expired_schedule.terminal, "lease_exhausted")
        expired_state = expired_schedule.state.apply(
            p, (), registry=registry, admission_handle=registry.handle
        )
        self.assertEqual(
            registry.bracket_snapshot(expired_state).terminal, "lease_exhausted"
        )
        with self.assertRaises(LeaseExhausted):
            validate_and_append_seals(
                p,
                (replace(seal, sequence=2, sealed_at=22),),
                registry=registry,
                admission_handle=registry.handle,
            )
        with self.assertRaises(LeaseExhausted):
            stage_paired_bootstrap(
                p,
                "success_difference",
                "MB0",
                "MB1",
                rows,
                left_hard_gates=True,
                right_hard_gates=True,
                registry=registry,
                admission_handle=registry.handle,
            )
        with self.assertRaises(LeaseExhausted):
            decide_match(
                p, *aggregates, registry=registry, admission_handle=registry.handle
            )

    def test_final_aggregation_requires_thirty_by_three(self):
        p = protocol()
        # The StageEvidence constructor itself rejects any claimed final 30x1 shape.
        with self.assertRaises(CampaignMetricsError):
            replace(
                stage_evidence(p, "original"),
                stage="final",
                tasks=task_bindings("final"),
                repetitions=1,
                final_pair=(),
                holdout_opened_at=20,
            )
        with self.assertRaises(CampaignMetricsError):
            replace(task_bindings("final")[0], repetition_seeds=(7, 7, 7))

    def test_raw_bootstrap_repeated_seed_is_byte_equal_but_inert(self):
        pairs = {f"family-{index}": (float(index),) for index in range(12)}
        first = paired_family_bootstrap(pairs, seed=7)
        second = paired_family_bootstrap(pairs, seed=7)
        self.assertEqual(canonical_digest(first), canonical_digest(second))


if __name__ == "__main__":
    unittest.main()
