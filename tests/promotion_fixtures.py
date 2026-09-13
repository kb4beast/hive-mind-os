"""Real retained evaluation inputs for promotion tests; no production trust defaults."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from promotion_auth_fixtures import authorize, verifier_for

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.evaluation_runtime import (
    ChallengerDescriptor,
    EvaluationContract,
    EvaluationIdentities,
    EvaluationRuntime,
    SealedHoldout,
    SurfaceKind,
    SurfaceResult,
)
from hive_mind_os.brain_kernel.promotion import (
    PromotionAuthority,
    PromotionCandidate,
    PromotionDecision,
)
from hive_mind_os.recursive_improvement import ExperimentVerdict


def evidence_refs(root: Path, candidate_id: str) -> tuple[str, ...]:
    directory = root / "evaluation-inputs" / sha256(candidate_id.encode()).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "surfaces.log"
    path.write_bytes(b"deterministic test measurements; fixture only\n")
    return (f"{path.resolve().as_posix()}#sha256:{sha256(path.read_bytes()).hexdigest()}",)


def bound_decision(candidate: PromotionCandidate, verdict: ExperimentVerdict,
                   case_id: str, decision_id: str, *, judge: str, evaluator: str,
                   promoter: str, action: str = "apply", reasons=("court-authorized",)) -> PromotionDecision:
    contract = EvaluationContract()
    # Preserve existing constructor-identity refusal checks before fixture execution.
    decision = PromotionDecision(decision_id, case_id, candidate, verdict, judge,
                                 evaluator, reasons, contract.fingerprint,
                                 promoter_id=promoter, action=action)
    descriptor = ChallengerDescriptor(candidate.candidate_id, "retained-parent-label",
                                      "refs/heads/codex/test-candidate",
                                      canonical_digest({"proposal": candidate.candidate_id}))
    subject = candidate.evaluation_subject(descriptor, contract_fingerprint=contract.fingerprint)
    holdout = SealedHoldout("holdout:" + decision_id, {"case": {"expected": True}})
    if verdict is not ExperimentVerdict.QUARANTINE:
        holdout.seal_prediction(evaluator, {"prediction": "candidate improves"})
    samples = (0.5,) * 3 if verdict is ExperimentVerdict.RETEST else (0.0,) * 3 if verdict is ExperimentVerdict.DISCARD else (0.9,) * 3
    surfaces = tuple(
        SurfaceResult(kind, kind.value, (0.5, 0.5, 0.5), samples, candidate.evidence_refs)
        for kind in SurfaceKind
    )
    directory = Path(candidate.evidence_refs[0].rsplit("#sha256:", 1)[0]).parent / "evaluations"
    record = EvaluationRuntime(contract).evaluate(
        descriptor, EvaluationIdentities(candidate.proposer_id, candidate.builder_id, evaluator),
        surfaces, holdout, evidence_root=directory, promotion_subject=subject,
    )
    decision = replace(decision, evaluation_subject=subject, evaluation_record=record.reference())
    verifier = verifier_for(builder_id=candidate.builder_id, evaluator_id=evaluator,
                            judge_id=judge, promoter_id=promoter)
    payload = PromotionAuthority.decision_payload(decision, include_authorization=False)
    return replace(decision, authorization=authorize(payload, verifier))


def decision_payload(root: Path, *, candidate_digest: str, parent: str | None,
                     experiment_id: str, proposer: str = "author:test",
                     builder: str = "builder:test", evaluator: str = "evaluator:test",
                     judge: str = "judge:test", promoter: str = "promoter:test") -> dict:
    candidate_id = "candidate:" + experiment_id
    candidate = PromotionCandidate(candidate_id, "builder", experiment_id, candidate_digest,
                                   parent, proposer, builder, evidence_refs(root, candidate_id))
    decision = bound_decision(candidate, ExperimentVerdict.KEEP, "case:" + experiment_id,
                              "decision:" + experiment_id, judge=judge,
                              evaluator=evaluator, promoter=promoter)
    return PromotionAuthority.decision_payload(decision)


def rollback_payload(registry, target, *, reason="regression", verdict=ExperimentVerdict.DISCARD):
    """Fresh adverse measurements and action signatures; never reuse KEEP evidence."""
    from uuid import uuid4

    current = registry.champion_digest("builder")
    registration = next(item for item in registry.lineage(current)
                        if item["kind"] == "registration" and item["role"] == "builder"
                        and item["parent_digest"] == target)
    identities = {binding.stage: binding.principal_id for binding in registry.principal_verifier.test_only_bindings}
    identity = "rollback:" + uuid4().hex
    candidate = PromotionCandidate(identity, "builder", identity, current, target,
                                   registration["created_by"], identities["builder"], evidence_refs(registry.root, identity))
    decision = bound_decision(candidate, verdict, "case:" + identity, "decision:" + identity,
                              judge=identities["judge"], evaluator=identities["verifier"],
                              promoter=identities["promoter"], action="rollback", reasons=(reason,))
    return PromotionAuthority.decision_payload(decision)


def authenticated_rollback(registry, target, *, reason="regression"):
    payload = rollback_payload(registry, target, reason=reason)
    sequence = registry.ledger.append_event(payload["registration_experiment_id"], "experiment.decision",
                                            payload["judge_id"], payload)
    return registry.rollback_champion("builder", target, actor=payload["promoter_id"], reason=reason,
                                      experiment_id=payload["registration_experiment_id"],
                                      decision_event_sequence=sequence, expected_current=payload["candidate_digest"])
