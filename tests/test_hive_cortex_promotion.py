from __future__ import annotations

import tempfile
import unittest

from hive_mind_os.brain_kernel.court_runtime import (
    CourtBrief,
    CourtCase,
    CourtClaimKind,
    CourtDisposition,
    CourtHistory,
    CourtParticipant,
    CourtProtocolError,
    CourtSeat,
    CourtVerdict,
    record_case,
)
from hive_mind_os.brain_kernel.promotion import (
    PromotionAuthority,
    PromotionAuthorityError,
    PromotionCandidate,
    PromotionDecision,
    PromotionDecisionLog,
)
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import PromptRegistry
from hive_mind_os.recursive_improvement import ExperimentVerdict

PROPOSER = "proposer-1"
BUILDER = "builder-1"
EVALUATOR = "evaluator-1"
JUDGE = "judge-1"
AFFECTED = (PROPOSER, BUILDER, EVALUATOR)


def _registry(testcase: unittest.TestCase) -> PromptRegistry:
    directory = tempfile.TemporaryDirectory()
    registry = PromptRegistry(directory.name)
    # Cleanups run last-in-first-out: the sqlite ledger must be closed before
    # the temporary directory is removed or Windows raises WinError 32.
    testcase.addCleanup(directory.cleanup)
    testcase.addCleanup(registry.close)
    return registry


def _briefs(judge: str = JUDGE) -> tuple[CourtBrief, ...]:
    return (
        CourtBrief(
            CourtParticipant(
                CourtSeat.ADVOCATE, "advocate-1", "present the strongest supported case"
            ),
            "candidate beats the champion on retained evidence",
            ("evidence:advocate",),
        ),
        CourtBrief(
            CourtParticipant(
                CourtSeat.CROSS_EXAMINER,
                "cross-1",
                "find contradictions and counterexamples",
            ),
            "no unexplained regression was found",
            ("evidence:cross",),
        ),
        CourtBrief(
            CourtParticipant(
                CourtSeat.EXPERT_WITNESS, "expert-1", "assess evidence quality"
            ),
            "measurements reproduce",
            ("evidence:expert",),
        ),
        CourtBrief(
            CourtParticipant(CourtSeat.JUDGE, judge, "weigh the retained record"),
            "decision recorded",
            ("evidence:judge",),
        ),
    )


def _court_history(
    subject_digest: str,
    *,
    disposition: CourtDisposition,
    case_id: str,
    claim_kind: CourtClaimKind = CourtClaimKind.SUPERIORITY,
    judge: str = JUDGE,
    affected: tuple[str, ...] = AFFECTED,
    history: CourtHistory | None = None,
) -> CourtHistory:
    case = CourtCase(case_id, claim_kind, subject_digest, affected)
    verdict = CourtVerdict(
        case_id, disposition, judge, ("burden addressed",), ("evidence:court",)
    )
    return record_case(history or CourtHistory(), case, _briefs(judge), verdict)


def _registered_candidate(
    registry: PromptRegistry,
    *,
    content: str,
    parent: str | None,
    candidate_id: str,
    experiment_id: str,
) -> PromotionCandidate:
    digest = registry.register(
        Role.BUILDER,
        content,
        parent_digest=parent,
        created_by=PROPOSER,
        experiment_id=experiment_id,
    )
    return PromotionCandidate(
        candidate_id,
        Role.BUILDER.value,
        experiment_id,
        digest,
        parent,
        PROPOSER,
        BUILDER,
        (f"evidence:{candidate_id}",),
    )


def _decision(
    candidate: PromotionCandidate,
    verdict: ExperimentVerdict,
    case_id: str,
    decision_id: str,
    *,
    judge: str = JUDGE,
    evaluator: str = EVALUATOR,
) -> PromotionDecision:
    return PromotionDecision(
        decision_id,
        case_id,
        candidate,
        verdict,
        judge,
        evaluator,
        ("court-authorized",),
        "fp-1",
    )


def _keep(
    authority: PromotionAuthority,
    registry: PromptRegistry,
    *,
    content: str,
    parent: str | None,
    candidate_id: str,
    experiment_id: str,
    case_id: str,
    decision_id: str,
) -> PromotionDecision:
    """Run one fully authorized KEEP: register, court, submit, apply."""

    candidate = _registered_candidate(
        registry,
        content=content,
        parent=parent,
        candidate_id=candidate_id,
        experiment_id=experiment_id,
    )
    history = _court_history(
        candidate.artifact_digest,
        disposition=CourtDisposition.ADOPT,
        case_id=case_id,
    )
    decision = _decision(candidate, ExperimentVerdict.KEEP, case_id, decision_id)
    authority.submit(decision, court_history=history)
    authority.apply(decision_id)
    return decision


class HiveCortexPromotionTests(unittest.TestCase):
    def test_promotion_authority_tests(self) -> None:
        registry = _registry(self)
        authority = PromotionAuthority(registry)

        # A full, court-authorized KEEP is the only thing that moves a pointer.
        first = _keep(
            authority,
            registry,
            content="prompt-a",
            parent=None,
            candidate_id="CAND-A",
            experiment_id="EXP-A",
            case_id="CASE-A",
            decision_id="DEC-A",
        )
        champion = first.candidate.artifact_digest
        self.assertEqual(registry.champion_digest(Role.BUILDER), champion)
        promote_receipt = authority.receipts[-1]
        self.assertEqual(promote_receipt["action"], "promote")
        self.assertEqual(promote_receipt["status"], "applied")
        self.assertIsNone(promote_receipt["prior_digest"])
        self.assertEqual(promote_receipt["pointer_after"], champion)
        self.assertIsInstance(authority.log, PromotionDecisionLog)
        self.assertEqual(
            tuple(item.decision_id for item in authority.log.for_candidate("CAND-A")),
            ("DEC-A",),
        )

        # RETEST over a DEFER court record retains the champion, no pointer move.
        retest = _registered_candidate(
            registry,
            content="prompt-retest",
            parent=champion,
            candidate_id="CAND-R",
            experiment_id="EXP-R",
        )
        retest_history = _court_history(
            retest.artifact_digest,
            disposition=CourtDisposition.DEFER,
            case_id="CASE-R",
            claim_kind=CourtClaimKind.ORDINARY,
        )
        authority.submit(
            _decision(retest, ExperimentVerdict.RETEST, "CASE-R", "DEC-R"),
            court_history=retest_history,
        )
        retain_receipt = authority.apply("DEC-R")
        self.assertEqual(retain_receipt["action"], "retain-champion")
        self.assertEqual(retain_receipt["status"], "applied")
        self.assertEqual(registry.champion_digest(Role.BUILDER), champion)

        # A KEEP cannot ride a deferring court record ...
        blocked = _registered_candidate(
            registry,
            content="prompt-blocked",
            parent=champion,
            candidate_id="CAND-D",
            experiment_id="EXP-D",
        )
        defer_history = _court_history(
            blocked.artifact_digest,
            disposition=CourtDisposition.DEFER,
            case_id="CASE-D",
        )
        with self.assertRaisesRegex(PromotionAuthorityError, "does not authorize"):
            authority.submit(
                _decision(blocked, ExperimentVerdict.KEEP, "CASE-D", "DEC-D"),
                court_history=defer_history,
            )

        # ... nor an ordinary claim: beating the champion carries a burden.
        ordinary_history = _court_history(
            blocked.artifact_digest,
            disposition=CourtDisposition.ADOPT,
            case_id="CASE-O",
            claim_kind=CourtClaimKind.ORDINARY,
        )
        with self.assertRaisesRegex(PromotionAuthorityError, "superiority claim"):
            authority.submit(
                _decision(blocked, ExperimentVerdict.KEEP, "CASE-O", "DEC-O"),
                court_history=ordinary_history,
            )

        # ... nor may it proceed with no independent court record at all.
        with self.assertRaisesRegex(
            PromotionAuthorityError, "independent court record"
        ):
            authority.submit(
                _decision(blocked, ExperimentVerdict.KEEP, "CASE-absent", "DEC-X"),
                court_history=defer_history,
            )
        self.assertEqual(registry.champion_digest(Role.BUILDER), champion)

        # Append-only: decision ids are never reused ...
        reuse_history = _court_history(
            retest.artifact_digest,
            disposition=CourtDisposition.DEFER,
            case_id="CASE-R2",
            claim_kind=CourtClaimKind.ORDINARY,
        )
        with self.assertRaisesRegex(PromotionAuthorityError, "ids are append-only"):
            authority.submit(
                _decision(retest, ExperimentVerdict.RETEST, "CASE-R2", "DEC-R"),
                court_history=reuse_history,
            )

        # ... and one court case decides exactly once.
        with self.assertRaisesRegex(
            PromotionAuthorityError, "one promotion decision per court case"
        ):
            authority.submit(
                _decision(retest, ExperimentVerdict.RETEST, "CASE-R", "DEC-R-dup"),
                court_history=retest_history,
            )

        # A terminal verdict closes its candidate for good.
        closed_history = _court_history(
            champion,
            disposition=CourtDisposition.REJECT,
            case_id="CASE-A2",
            claim_kind=CourtClaimKind.ORDINARY,
        )
        with self.assertRaisesRegex(PromotionAuthorityError, "terminal verdict"):
            authority.submit(
                _decision(
                    first.candidate, ExperimentVerdict.DISCARD, "CASE-A2", "DEC-A2"
                ),
                court_history=closed_history,
            )

        # An unlogged decision has no authority whatsoever.
        with self.assertRaisesRegex(PromotionAuthorityError, "logged, unapplied"):
            authority.apply("DEC-never-submitted")
        self.assertEqual(registry.champion_digest(Role.BUILDER), champion)

    def test_self_promotion_attack_tests(self) -> None:
        registry = _registry(self)
        authority = PromotionAuthority(registry)
        established = _keep(
            authority,
            registry,
            content="prompt-a",
            parent=None,
            candidate_id="CAND-A",
            experiment_id="EXP-A",
            case_id="CASE-A",
            decision_id="DEC-A",
        )
        champion = established.candidate.artifact_digest

        candidate = _registered_candidate(
            registry,
            content="prompt-b",
            parent=champion,
            candidate_id="CAND-B",
            experiment_id="EXP-B",
        )

        # The proposer may not judge its own candidate.
        with self.assertRaisesRegex(PromotionAuthorityError, "four distinct"):
            _decision(
                candidate, ExperimentVerdict.KEEP, "CASE-B", "DEC-B", judge=PROPOSER
            )

        # The evaluator may not double as the builder it is evaluating.
        with self.assertRaisesRegex(PromotionAuthorityError, "four distinct"):
            _decision(
                candidate, ExperimentVerdict.KEEP, "CASE-B", "DEC-B", evaluator=BUILDER
            )

        # A judge who did not decide the case may not borrow its verdict.
        history = _court_history(
            candidate.artifact_digest,
            disposition=CourtDisposition.ADOPT,
            case_id="CASE-B",
        )
        with self.assertRaisesRegex(PromotionAuthorityError, "deciding identity"):
            authority.submit(
                _decision(
                    candidate, ExperimentVerdict.KEEP, "CASE-B", "DEC-B", judge="judge-2"
                ),
                court_history=history,
            )

        # The court itself refuses to seat an affected identity as the judge, so
        # a self-judged record cannot exist for this log to consume.
        with self.assertRaisesRegex(CourtProtocolError, "affected generator"):
            _court_history(
                candidate.artifact_digest,
                disposition=CourtDisposition.ADOPT,
                case_id="CASE-SELF",
                affected=(*AFFECTED, JUDGE),
            )

        # The registry's own gate stays shut for an uncourted direct promotion.
        bypass = registry.register(
            Role.BUILDER,
            "prompt-bypass",
            parent_digest=champion,
            created_by=PROPOSER,
            experiment_id="EXP-BYPASS",
        )
        with self.assertRaisesRegex(RuntimeError, r"experiment\.decision"):
            registry.promote(
                Role.BUILDER,
                bypass,
                promoted_by=JUDGE,
                experiment_id="EXP-BYPASS",
                expected_current=champion,
            )
        self.assertEqual(registry.champion_digest(Role.BUILDER), champion)

    def test_atomic_pointer_failure_tests(self) -> None:
        registry = _registry(self)
        authority = PromotionAuthority(registry)
        first = _keep(
            authority,
            registry,
            content="prompt-a",
            parent=None,
            candidate_id="CAND-A",
            experiment_id="EXP-A",
            case_id="CASE-A",
            decision_id="DEC-A",
        )
        digest_a = first.candidate.artifact_digest
        second = _keep(
            authority,
            registry,
            content="prompt-b",
            parent=digest_a,
            candidate_id="CAND-B",
            experiment_id="EXP-B",
            case_id="CASE-B",
            decision_id="DEC-B",
        )
        digest_b = second.candidate.artifact_digest
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_b)

        # C was bound to champion A and is therefore stale against champion B.
        stale = _registered_candidate(
            registry,
            content="prompt-c",
            parent=digest_a,
            candidate_id="CAND-C",
            experiment_id="EXP-C",
        )
        stale_history = _court_history(
            stale.artifact_digest,
            disposition=CourtDisposition.ADOPT,
            case_id="CASE-C",
        )
        authority.submit(
            _decision(stale, ExperimentVerdict.KEEP, "CASE-C", "DEC-C"),
            court_history=stale_history,
        )
        with self.assertRaisesRegex(
            PromotionAuthorityError, "atomic promotion was refused"
        ):
            authority.apply("DEC-C")

        # The pointer never moved and the refusal is retained as a receipt.
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_b)
        failure = authority.receipts[-1]
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["action"], "promote")
        self.assertEqual(failure["candidate_digest"], stale.artifact_digest)
        self.assertEqual(failure["pointer_after"], digest_b)

        # An already applied decision cannot be replayed onto the pointer.
        with self.assertRaisesRegex(PromotionAuthorityError, "logged, unapplied"):
            authority.apply("DEC-B")
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_b)

    def test_rollback_promotion_tests(self) -> None:
        registry = _registry(self)
        authority = PromotionAuthority(registry)
        first = _keep(
            authority,
            registry,
            content="prompt-a",
            parent=None,
            candidate_id="CAND-A",
            experiment_id="EXP-A",
            case_id="CASE-A",
            decision_id="DEC-A",
        )
        digest_a = first.candidate.artifact_digest
        second = _keep(
            authority,
            registry,
            content="prompt-b",
            parent=digest_a,
            candidate_id="CAND-B",
            experiment_id="EXP-B",
            case_id="CASE-B",
            decision_id="DEC-B",
        )
        digest_b = second.candidate.artifact_digest
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_b)

        # A KEEP verdict never authorizes a rollback.
        pending = _registered_candidate(
            registry,
            content="prompt-d",
            parent=digest_b,
            candidate_id="CAND-D",
            experiment_id="EXP-D",
        )
        authority.submit(
            _decision(pending, ExperimentVerdict.KEEP, "CASE-D", "DEC-D"),
            court_history=_court_history(
                pending.artifact_digest,
                disposition=CourtDisposition.ADOPT,
                case_id="CASE-D",
            ),
        )
        retained = len(authority.receipts)
        with self.assertRaisesRegex(PromotionAuthorityError, "discard or quarantine"):
            authority.rollback("DEC-D")
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_b)
        # The authority refused on its own, without reaching the registry.
        self.assertEqual(len(authority.receipts), retained)

        # An adverse quarantine verdict against the live champion restores A.
        adverse = PromotionCandidate(
            "CAND-Q",
            Role.BUILDER.value,
            "EXP-Q",
            digest_b,
            digest_a,
            PROPOSER,
            BUILDER,
            ("evidence:quarantine",),
        )
        authority.submit(
            _decision(adverse, ExperimentVerdict.QUARANTINE, "CASE-Q", "DEC-Q"),
            court_history=_court_history(
                digest_b,
                disposition=CourtDisposition.QUARANTINE,
                case_id="CASE-Q",
                claim_kind=CourtClaimKind.ORDINARY,
            ),
        )
        receipt = authority.rollback("DEC-Q")
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_a)
        self.assertTrue(registry.is_quarantined(digest_b))
        self.assertFalse(registry.is_quarantined(digest_a))
        self.assertEqual(receipt["action"], "rollback")
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(receipt["restored_digest"], digest_a)
        self.assertEqual(receipt["prior_digest"], digest_b)
        self.assertEqual(receipt["pointer_after"], digest_a)
        self.assertTrue(receipt["receipt_digest"].startswith("sha256:"))

        # A rollback whose candidate is no longer the active champion is refused.
        orphan = PromotionCandidate(
            "CAND-Z",
            Role.BUILDER.value,
            "EXP-Z",
            digest_b,
            digest_a,
            PROPOSER,
            BUILDER,
            ("evidence:orphan",),
        )
        authority.submit(
            _decision(orphan, ExperimentVerdict.DISCARD, "CASE-Z", "DEC-Z"),
            court_history=_court_history(
                digest_b,
                disposition=CourtDisposition.REJECT,
                case_id="CASE-Z",
                claim_kind=CourtClaimKind.ORDINARY,
            ),
        )
        retained = len(authority.receipts)
        with self.assertRaisesRegex(
            PromotionAuthorityError,
            "rollback requires the candidate to be the active champion",
        ):
            authority.rollback("DEC-Z")
        self.assertEqual(registry.champion_digest(Role.BUILDER), digest_a)
        # Refused by this module's own binding check, not by a registry error.
        self.assertEqual(len(authority.receipts), retained)


if __name__ == "__main__":
    unittest.main()
