"""Prove, from durable evidence alone, whether waiting can still change anything.

The control plane's verbs are individually fail-closed, which is right for a
worker but wrong for the loop that supervises workers: a dead session's live
claim, a superseded dispatch release, and an expired validation lease each
refuse every polite verb while never resolving on their own.  The operator was
always entitled to repair those by hand — inspect the claim commit, retire the
ref, re-run the snapshot, re-dispatch.  This module is that judgement as code,
bounded by three laws:

- every action needs a proof read from durable evidence, never impatience;
- every action preserves evidence — archive, retire, re-issue; never destroy
  published work, rewrite history, or fabricate authority;
- anything needing sealed or external authority is reported with its evidence
  and exact instructions instead of attempted.

The output is a disposition a caller can act on mechanically.  HEALED means
state changed and the loop should re-observe immediately.  WAITING carries the
exact time at which waiting stops being provably useful, so a poll before then
is by construction pointless unless a worker pushes.  OPEN_SESSIONS names the
operator cards that are the one thing code cannot do on an attended host.
STUCK_HUMAN carries the evidence only a human can move.  QUIESCENT means no
candidate needs anything.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import learning
from controller import (
    RECEIPT_COMMIT_EMAIL,
    append_jsonl,
    digest_json,
    format_time,
    parse_time,
)

POLICY_FILE = "healing-policy.json"
DEFAULT_POLICY: Mapping[str, Any] = {
    "enabled": True,
    "auto_reconcile": True,
    "auto_redispatch": True,
    "break_expired_validation_lease": True,
    "claim_stall_minutes": 30,
    "branch_stall_minutes": 45,
    "max_actions_per_run": 8,
    "learn": True,
    "commit_lessons": True,
    "push_lessons": False,
    "retry_disproven_after_minutes": 720,
}

# A blocker naming any of these needs sealed or external authority: healing it
# would rotate the plan fingerprint or fabricate consent, so the healer only
# reports it.  round_driver shares this tuple so triage and healing never
# disagree about what is untouchable.
SEALED_MARKERS = (
    "acceptance_criteria",
    "acceptance criterion",
    "credential",
    "consent",
    "protected branch",
    "protected-branch",
    "production",
    "legal",
    "spending",
    "sealed",
)


def load_policy(ap_root: Path) -> dict[str, Any]:
    """Merge the repository healing policy over safe defaults."""

    policy = dict(DEFAULT_POLICY)
    path = Path(ap_root) / POLICY_FILE
    if not path.is_file():
        return policy
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return policy
    if isinstance(value, Mapping):
        for key, default in DEFAULT_POLICY.items():
            # Exact type match (bool is an int subclass, so isinstance lies):
            # a malformed knob falls back to its safe default instead of
            # poisoning arithmetic or truth tests downstream.
            if key in value and type(value[key]) is type(default):
                policy[key] = value[key]
    return policy


@dataclass(frozen=True, slots=True)
class NodeDiagnosis:
    """One node's evidence-backed verdict on whether waiting can still help."""

    node_id: str
    verdict: str  # SEALED | WORKING | CLAIM_LIVE | CLAIM_DEFUNCT | CLAIM_STALLED
    #             # | BRANCH_DEFUNCT | UNSTARTED | BLOCKED_SEALED
    detail: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    wake_at: str | None = None
    action: str | None = None  # reap | quarantine | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "verdict": self.verdict,
            "detail": self.detail,
            "evidence": dict(self.evidence),
            "wake_at": self.wake_at,
            "action": self.action,
        }


def _last_blocker(plane: Any, node_id: str) -> Mapping[str, Any] | None:
    path = Path(plane.blockers_dir) / f"{node_id}.jsonl"
    if not path.is_file():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, Mapping) else None


def _blocker_is_sealed(packet: Mapping[str, Any] | None) -> bool:
    if packet is None:
        return False
    text = " ".join(
        str(packet.get(key, "")) for key in ("category", "cause", "fix")
    ).lower()
    return any(marker in text for marker in SEALED_MARKERS)


def diagnose_node(plane: Any, node_id: str, *, policy: Mapping[str, Any]) -> NodeDiagnosis:
    """Classify a node's remote evidence and name the lawful next move.

    The verdicts are exhaustive over what a remote node branch can hold:
    nothing (UNSTARTED), a sealed receipt (SEALED), an untouched claim commit
    (CLAIM_*), or unsealed work commits (WORKING / BRANCH_DEFUNCT).  Only the
    defunct verdicts carry an action, and each action's proof is re-verified by
    the controller verb that executes it — a diagnosis is never authority.
    """

    branch = str(plane.node(node_id).get("branch"))
    head = plane.remote_branch_sha(branch)
    if head is None:
        return NodeDiagnosis(node_id, "UNSTARTED", f"{branch} has no remote head")
    plane._git(("fetch", "origin", f"refs/heads/{branch}"), check=False)
    author = plane._git(("show", "-s", "--format=%ae", head), check=False).stdout.strip()
    if author == RECEIPT_COMMIT_EMAIL:
        return NodeDiagnosis(
            node_id,
            "SEALED",
            f"{head[:7]} is a sealed receipt awaiting integration",
            evidence={"head": head},
        )
    now = plane.clock()
    claim_stall = int(policy["claim_stall_minutes"])
    branch_stall = int(policy["branch_stall_minutes"])
    record = plane.remote_claim_record(head)
    if record is not None:
        proof = plane.defunct_remote_claim_proof(record)
        evidence = {"head": head, "claim": dict(record)}
        if proof is not None:
            return NodeDiagnosis(
                node_id,
                "CLAIM_DEFUNCT",
                f"claim {head[:7]} is defunct: {proof['kind']}",
                evidence={**evidence, "proof": dict(proof)},
                action="reap",
            )
        # Every prior stall retirement doubles the bound, and three suspend it:
        # repeats mean a slow-but-alive worker keeps re-claiming, and reaping it
        # again would oscillate forever.  Lease expiry then bounds the wait.
        retirements = _stall_retirements(plane, node_id)
        effective_stall = claim_stall * (2 ** min(retirements, 3))
        claimed_at = plane._commit_time(head)
        idle = now - claimed_at
        if retirements < 3 and idle >= timedelta(minutes=effective_stall):
            return NodeDiagnosis(
                node_id,
                "CLAIM_STALLED",
                f"claim {head[:7]} has produced no work for "
                f"{int(idle.total_seconds() // 60)} minutes (bound {effective_stall})",
                evidence={
                    **evidence,
                    # The proof is what keys this mechanism's lesson; without it
                    # every stall reap would be filed under the same empty key.
                    "proof": {
                        "kind": "stalled-bare-claim",
                        "claimed_at": format_time(claimed_at),
                        "idle_minutes": int(idle.total_seconds() // 60),
                        "stall_minutes": effective_stall,
                    },
                    "effective_stall_minutes": effective_stall,
                    "prior_stall_retirements": retirements,
                },
                action="reap",
            )
        expires = parse_time(record.get("expires_at"))
        if retirements >= 3:
            wake = expires
            detail = (
                f"claim {head[:7]} by {record.get('owner')} is live; the stall "
                f"bound is suspended after {retirements} retirements — waiting "
                f"for lease expiry"
            )
        else:
            stall_matures = claimed_at + timedelta(minutes=effective_stall)
            wake = min(stall_matures, expires)
            detail = (
                f"claim {head[:7]} by {record.get('owner')} is live and current; "
                f"the stall bound matures at {format_time(stall_matures)}"
            )
        return NodeDiagnosis(
            node_id,
            "CLAIM_LIVE",
            detail,
            evidence=evidence,
            wake_at=format_time(wake),
        )
    moved_at = plane._commit_time(head)
    idle = now - moved_at
    governing = plane._governing_claim_record(node_id, head)
    governing_proof = (
        plane.defunct_remote_claim_proof(governing) if governing is not None else None
    )
    evidence: dict[str, Any] = {
        "head": head,
        "head_moved_at": format_time(moved_at),
        "governing_claim": dict(governing) if governing is not None else None,
    }
    claim_defunct_or_absent = governing is None or governing_proof is not None
    if claim_defunct_or_absent and idle >= timedelta(minutes=branch_stall):
        why = (
            "no governing claim"
            if governing is None
            else f"governing claim is defunct: {governing_proof['kind']}"
        )
        return NodeDiagnosis(
            node_id,
            "BRANCH_DEFUNCT",
            f"unsealed work at {head[:7]} idle "
            f"{int(idle.total_seconds() // 60)} minutes with {why}",
            evidence={**evidence, "proof": dict(governing_proof or {})},
            action="quarantine",
        )
    # wake_at must always lie in the future: an already-matured stall bound
    # under a live governing claim would otherwise tell the caller to wake
    # immediately, degenerating WAITING into a busy poll until lease expiry.
    candidates = [moved_at + timedelta(minutes=branch_stall)]
    if not claim_defunct_or_absent:
        candidates.append(parse_time(governing.get("expires_at")))
    future = [item for item in candidates if item > now]
    wake = min(future) if future else now + timedelta(minutes=branch_stall)
    return NodeDiagnosis(
        node_id,
        "WORKING",
        f"unsealed work at {head[:7]}; a worker may still be publishing",
        evidence=evidence,
        wake_at=format_time(wake),
    )


def reconcile_with_snapshot(plane: Any, *, actor: str) -> tuple[bool, str]:
    """Refresh the GitHub snapshot and reconciliation the way the operator would."""

    script = Path(plane.ap_root) / "bin" / "github_snapshot.py"
    try:
        completed = subprocess.run(
            (
                sys.executable,
                str(script),
                "--repo-root",
                str(plane.repo_root),
                "--reconcile",
                "--actor",
                actor,
            ),
            cwd=str(plane.repo_root),
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return False, f"snapshot process could not start: {error}"
    tail = (completed.stderr or completed.stdout).strip().splitlines()
    return completed.returncode == 0, tail[-1] if tail else "no snapshot output"


_MECHANISMS: Mapping[str, str] = {
    "reap": "A remote claim commit is the only cross-session mutex, but a mutex "
    "protects work that could still become an integrable receipt. When the claim "
    "is proven defunct, retiring its ref is what frees the node for a lawful "
    "re-claim; nothing is deleted but an empty claim commit.",
    "quarantine": "An unsealed branch whose governing claim is defunct blocks "
    "every lawful re-claim while no worker can still finish it. Archiving the "
    "head under a quarantine ref preserves the work verbatim and frees the "
    "branch name.",
    "lift-quarantine": "A retry budget spent by a dead session keeps a node "
    "unreachable after its recorded causes have been fixed. Lifting it once "
    "every blocker carries a verified resolution reopens the node without "
    "weakening the guard against blind retry loops.",
}
_GUIDANCE: Mapping[str, str] = {
    "reap": "Read the claim commit (`git log -1 origin/<node-branch>`), confirm "
    "the proof it records, then retire it with `autopilot reap-stale-remote-claim` "
    "or let `autopilot heal` do it.",
    "quarantine": "Confirm the head is unsealed and its governing claim defunct, "
    "then let `autopilot heal` archive it; never delete a node branch by hand.",
    "lift-quarantine": "Resolve every open blocker with `autopilot blocker-resolve` "
    "(each needs a verified fix and a safe retry command), then heal.",
}


def proof_kind_of(diagnosis: NodeDiagnosis) -> str:
    """Return the proof that keys this diagnosis's lesson."""

    proof = diagnosis.evidence.get("proof")
    return str(proof.get("kind", "")) if isinstance(proof, Mapping) else ""


def _record_attempt(
    plane: Any,
    policy: Mapping[str, Any],
    diagnosis: NodeDiagnosis,
    *,
    actor: str,
) -> None:
    """Note that a repair was applied; a later pass judges whether it held."""

    if not policy.get("learn", True) or diagnosis.action is None:
        return
    try:
        learning.record_attempt(
            plane.ap_root,
            verdict=diagnosis.verdict,
            proof_kind=proof_kind_of(diagnosis),
            action=diagnosis.action,
            node_id=diagnosis.node_id,
            actor=actor,
            observed_at=format_time(plane.clock()),
            head=diagnosis.evidence.get("head"),
            mechanism=_MECHANISMS.get(diagnosis.action, ""),
            guidance=_GUIDANCE.get(diagnosis.action, ""),
        )
    except Exception:
        # Learning must never be able to fail a repair that already succeeded.
        return


def _record_refusal(
    plane: Any,
    policy: Mapping[str, Any],
    diagnosis: NodeDiagnosis,
    *,
    actor: str,
    detail: str,
) -> None:
    """Record a refusal, which counts toward neither success nor failure."""

    if not policy.get("learn", True) or diagnosis.action is None:
        return
    try:
        learning.record_outcome(
            plane.ap_root,
            verdict=diagnosis.verdict,
            proof_kind=proof_kind_of(diagnosis),
            action=diagnosis.action,
            outcome="REFUSED",
            node_id=diagnosis.node_id,
            actor=actor,
            observed_at=format_time(plane.clock()),
            # The head distinguishes a lost race (it moved) from an environment
            # that simply will not permit this repair (it never moves).
            head=diagnosis.evidence.get("head"),
            detail=detail,
            mechanism=_MECHANISMS.get(diagnosis.action, ""),
            guidance=_GUIDANCE.get(diagnosis.action, ""),
        )
    except Exception:
        return


def _consult(
    plane: Any, policy: Mapping[str, Any], diagnosis: NodeDiagnosis
) -> learning.Lesson | None:
    if not policy.get("learn", True) or diagnosis.action is None:
        return None
    try:
        return learning.consult(
            plane.ap_root,
            diagnosis.verdict,
            proof_kind_of(diagnosis),
            diagnosis.action,
        )
    except Exception:
        return None


def _withdrawn(plane: Any, policy: Mapping[str, Any], lesson: learning.Lesson) -> bool:
    return lesson.withdrawn(
        plane.clock(),
        cooldown_minutes=int(policy.get("retry_disproven_after_minutes", 720)),
    )


def _report_withdrawn(
    report: dict[str, Any],
    record_action: Any,
    diagnosis: NodeDiagnosis,
    lesson: learning.Lesson,
) -> None:
    why = (
        f"{diagnosis.detail}; the remote refused {diagnosis.action} "
        f"{lesson.stuck_refusals} time(s) in a row without the head moving, so "
        "this is a permission or protection rule, not a lost race"
        if lesson.refusal_stalled()
        else f"{diagnosis.detail}; {diagnosis.action} on this mechanism has "
        f"failed to hold {lesson.counts.get('NO_EFFECT', 0)} time(s) and has "
        "never once held"
    )
    report["stuck"].append(
        {
            "node_id": diagnosis.node_id,
            "resolvable": True,
            "why": why,
            "instructions": lesson.guidance
            or "diagnose this mechanism by hand; the automatic repair is "
            "withdrawn by its own recorded outcomes",
            "lesson": lesson.to_dict(),
        }
    )
    record_action(
        diagnosis.action, diagnosis.node_id, "WITHDRAWN", f"lesson {lesson.signature}"
    )


def current_wedge(plane: Any, node_id: str, policy: Mapping[str, Any]) -> str | None:
    """Return the mechanism signature currently wedging a node, or None.

    This is what settles an earlier repair: if the same mechanism is wedging
    the same node on a later pass, that repair did not hold.
    """

    if (Path(plane.quarantine_dir) / f"{node_id}.json").is_file():
        return learning.signature(
            "RETRY_QUARANTINED", "blockers-resolved", "lift-quarantine"
        )
    diagnosis = diagnose_node(plane, node_id, policy=policy)
    if diagnosis.action is None:
        return None
    return learning.signature(
        diagnosis.verdict, proof_kind_of(diagnosis), diagnosis.action
    )


def _stall_retirements(plane: Any, node_id: str) -> int:
    """Count this node's prior stall-proof claim retirements.

    Each one means a claim was retired purely for silence.  The diagnosis uses
    the count to back the stall bound off exponentially and suspend it after
    three, so a slow-but-alive worker cannot be reaped in a loop forever.
    """

    path = Path(plane.state_dir) / "releases.jsonl"
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, Mapping):
            continue
        proof = record.get("proof")
        if (
            record.get("node_id") == node_id
            and record.get("outcome") == "retired-defunct"
            and isinstance(proof, Mapping)
            and proof.get("kind") == "stalled-bare-claim"
        ):
            count += 1
    return count


def _quarantine_liftable(plane: Any, node_id: str) -> bool:
    """True when a retry quarantine stands but every blocker carries a fix.

    Requires at least one named, resolved cause — an empty or unparseable
    ledger is never proof (the quarantine was earned by real failures).
    """

    if not (Path(plane.quarantine_dir) / f"{node_id}.json").is_file():
        return False
    return bool(plane.blockers_fully_resolved(node_id))


def _expired_lease(plane: Any) -> bool:
    path = Path(plane.validation_lease_path)
    if not path.is_file():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        expires = parse_time(value.get("expires_at")) if isinstance(value, Mapping) else None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return True  # unreadable bounds can never be identity-released
    return expires is None or expires <= plane.clock()


def _evidence_fingerprint(plane: Any, diagnoses: Sequence[NodeDiagnosis]) -> str:
    material = {
        "target": plane.current_target_sha(),
        "nodes": {
            item.node_id: {
                "verdict": item.verdict,
                "head": item.evidence.get("head"),
            }
            for item in diagnoses
        },
    }
    return digest_json(material)


def _record_observation(plane: Any, fingerprint: str) -> int:
    """Append this observation and return minutes the evidence has been frozen."""

    path = Path(plane.state_dir) / "heal" / "observations.jsonl"
    now = plane.clock()
    entries: list[Mapping[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                entries.append(value)
    append_jsonl(path, {"fingerprint": fingerprint, "observed_at": format_time(now)})
    frozen_since = now
    for entry in reversed(entries):
        if entry.get("fingerprint") != fingerprint:
            break
        try:
            frozen_since = parse_time(entry.get("observed_at"))
        except (TypeError, ValueError):
            break
    return int((now - frozen_since).total_seconds() // 60)


def heal_round(
    plane: Any,
    *,
    actor: str,
    nodes: Sequence[str] | None = None,
    policy: Mapping[str, Any] | None = None,
    status: Mapping[str, Any] | None = None,
    apply: bool = True,
    allow_push: bool = True,
) -> dict[str, Any]:
    """Diagnose every candidate node and apply each provable repair once.

    Order matters and mirrors what a careful operator does by hand: repair the
    remote artifacts first (each repair invalidates the dispatch release by
    design), then refresh snapshot + reconciliation so status is trustworthy
    again, then issue a fresh release so the next observation can act.  With
    ``apply=False`` the same report is produced with every action withheld.
    """

    policy = dict(policy or load_policy(plane.ap_root))
    report: dict[str, Any] = {
        "kind": "hive-mind-autopilot-heal-report-v1",
        "actor": actor,
        "enabled": bool(policy["enabled"]),
        "applied": bool(apply and policy["enabled"]),
        "actions": [],
        "diagnoses": [],
        "waiting": [],
        "stuck": [],
        "disposition": "QUIESCENT",
        "wake_at": None,
    }
    if not policy["enabled"]:
        report["disposition"] = "DISABLED"
        return report
    acting = apply

    def record_action(kind: str, node_id: str | None, outcome: str, detail: str) -> None:
        report["actions"].append(
            {"kind": kind, "node_id": node_id, "outcome": outcome, "detail": detail}
        )

    healed = 0
    withheld = 0
    refused = 0
    current = dict(status) if status is not None else plane.status()
    if current.get("reconciliation_required") and policy["auto_reconcile"]:
        if acting:
            ok, detail = reconcile_with_snapshot(plane, actor=actor)
            record_action("reconcile", None, "APPLIED" if ok else "FAILED", detail)
            if ok:
                current = plane.status()
            else:
                report["disposition"] = "BLOCKED"
                return report
        else:
            withheld += 1
            record_action("reconcile", None, "WITHHELD", "dry run")

    if nodes is None:
        rows = current.get("nodes", [])
        nodes = [
            str(row.get("node_id"))
            for row in rows
            if isinstance(row, Mapping) and row.get("state") != "COMPLETE"
        ]

    if policy.get("learn", True):
        # Judge earlier repairs before consulting the record, so this pass acts
        # on what actually held rather than on what merely ran.
        try:
            settled = learning.settle_attempts(
                plane.ap_root,
                observe=lambda node: current_wedge(plane, node, policy),
                actor=actor,
                now=plane.clock(),
            )
        except Exception as error:
            record_action("settle", None, "FAILED", str(error))
            settled = ()
        for record in settled:
            record_action(
                "settle",
                str(record.get("node_id") or ""),
                str(record.get("outcome") or ""),
                f"{record.get('action')}: {record.get('detail')}",
            )

    budget = int(policy["max_actions_per_run"])
    release = current.get("dispatch_release", {})
    release_valid = isinstance(release, Mapping) and release.get("valid") is True
    verdicts = release.get("verdicts", {}) if isinstance(release, Mapping) else {}
    open_sessions: list[str] = []
    diagnoses: list[NodeDiagnosis] = []
    for node_id in nodes:
        if _quarantine_liftable(plane, node_id):
            lift = NodeDiagnosis(
                node_id,
                "RETRY_QUARANTINED",
                "retry budget spent; every recorded cause carries a fix",
                evidence={"proof": {"kind": "blockers-resolved"}},
                action="lift-quarantine",
            )
            lift_lesson = _consult(plane, policy, lift)
            if lift_lesson is not None and _withdrawn(plane, policy, lift_lesson):
                _report_withdrawn(report, record_action, lift, lift_lesson)
            elif not acting:
                withheld += 1
                record_action(
                    "lift-quarantine", node_id, "WITHHELD", "every blocker is resolved"
                )
            elif healed < budget:
                try:
                    lifted = plane.lift_retry_quarantine(node_id, actor=actor)
                except Exception as error:
                    record_action("lift-quarantine", node_id, "REFUSED", str(error))
                    _record_refusal(
                        plane, policy, lift, actor=actor, detail=str(error)
                    )
                else:
                    if lifted is not None:
                        healed += 1
                        record_action(
                            "lift-quarantine",
                            node_id,
                            "APPLIED",
                            "retry budget reopened; every recorded cause carries "
                            "a verified fix",
                        )
                        _record_attempt(plane, policy, lift, actor=actor)
        try:
            diagnosis = diagnose_node(plane, node_id, policy=policy)
        except Exception as error:
            # One node's git trouble must not abort the pass for every other
            # node; the failure itself is a diagnosis worth reporting.
            record_action("diagnose", node_id, "FAILED", str(error))
            continue
        blocker = _last_blocker(plane, node_id)
        fully_resolved = getattr(plane, "blockers_fully_resolved", lambda _node: False)(
            node_id
        )
        if fully_resolved:
            blocker = None  # every recorded cause already carries a verified fix
        if _blocker_is_sealed(blocker):
            diagnosis = NodeDiagnosis(
                node_id,
                "BLOCKED_SEALED",
                "the latest blocker names sealed or external authority",
                evidence={"blocker": dict(blocker or {})},
            )
        diagnoses.append(diagnosis)
        report["diagnoses"].append(diagnosis.to_dict())
        if diagnosis.verdict == "BLOCKED_SEALED":
            report["stuck"].append(
                {
                    "node_id": node_id,
                    "resolvable": False,
                    "why": str((blocker or {}).get("cause", "sealed authority")),
                    "instructions": str((blocker or {}).get("fix", "record and continue")),
                }
            )
            continue
        if diagnosis.action is None:
            unresolved = (
                ()
                if fully_resolved
                else tuple(
                    getattr(plane, "unresolved_blockers", lambda _node: ())(node_id)
                )
            )
            if unresolved:
                # Nothing mechanical remains, but recorded causes lack verified
                # fixes — the loop's orchestrator resolves these, not a poll.
                report["stuck"].append(
                    {
                        "node_id": node_id,
                        "resolvable": True,
                        "why": f"{len(unresolved)} open blocker(s) without a "
                        "verified resolution",
                        "instructions": "verify each cause against real source, "
                        f"then: autopilot blocker-resolve {node_id} <blocker_id> "
                        "--actor <you> --fix <what changed> --retry-command=... ; "
                        "healing lifts any retry quarantine once every cause is "
                        "resolved",
                        "blockers": list(unresolved),
                    }
                )
                continue
            if diagnosis.wake_at is not None:
                report["waiting"].append(
                    {"node_id": node_id, "why": diagnosis.detail, "wake_at": diagnosis.wake_at}
                )
            if diagnosis.verdict == "UNSTARTED" and (
                release_valid
                and isinstance(verdicts, Mapping)
                and verdicts.get(node_id) == "START NOW"
            ):
                open_sessions.append(node_id)
            continue
        lesson = _consult(plane, policy, diagnosis)
        if lesson is not None and _withdrawn(plane, policy, lesson):
            # The record says this repair has never once held. Repeating it
            # would be the polling loop it was written to end.
            _report_withdrawn(report, record_action, diagnosis, lesson)
            continue
        if healed >= budget:
            record_action(diagnosis.action, node_id, "DEFERRED", "action budget exhausted")
            continue
        if not acting:
            withheld += 1
            record_action(diagnosis.action, node_id, "WITHHELD", diagnosis.detail)
            continue
        try:
            if diagnosis.action == "reap":
                result = plane.reap_defunct_remote_claim(
                    node_id,
                    actor=actor,
                    reason=diagnosis.detail,
                    stall_minutes=int(
                        diagnosis.evidence.get(
                            "effective_stall_minutes", policy["claim_stall_minutes"]
                        )
                    ),
                )
            else:
                result = plane.quarantine_defunct_remote_branch(
                    node_id,
                    actor=actor,
                    reason=diagnosis.detail,
                    stall_minutes=int(policy["branch_stall_minutes"]),
                )
        except Exception as error:
            # Refusal is evidence, not failure: the worker either raced us with
            # a push (force-with-lease) or the controller re-proved liveness.
            refused += 1
            record_action(diagnosis.action, node_id, "REFUSED", str(error))
            _record_refusal(plane, policy, diagnosis, actor=actor, detail=str(error))
            continue
        healed += 1
        record_action(
            diagnosis.action, node_id, "APPLIED", str(result.get("outcome", "done"))
        )
        # Whether this held is not knowable yet: the repair just removed the
        # artifact it diagnosed. A later pass settles it by checking whether the
        # same mechanism wedges this node again.
        _record_attempt(plane, policy, diagnosis, actor=actor)

    if policy["break_expired_validation_lease"] and _expired_lease(plane):
        if acting:
            try:
                broken = plane.break_expired_validation_lease(actor=actor)
            except Exception as error:
                record_action("break-lease", None, "REFUSED", str(error))
            else:
                if broken is not None:
                    healed += 1
                    record_action(
                        "break-lease",
                        None,
                        "APPLIED",
                        f"expired lease of {broken.get('owner')} archived",
                    )
        else:
            withheld += 1
            record_action("break-lease", None, "WITHHELD", "dry run")

    if healed and acting:
        # Every remote repair invalidates the pinned release by design; refresh
        # the snapshot and reconciliation, then issue the fresh release that
        # gives the next observation authority to act.
        if policy["auto_reconcile"]:
            ok, detail = reconcile_with_snapshot(plane, actor=actor)
            record_action("reconcile", None, "APPLIED" if ok else "FAILED", detail)
        if policy["auto_redispatch"]:
            try:
                fresh = plane.dispatch(actor=actor)
            except Exception as error:
                record_action("dispatch", None, "FAILED", str(error))
            else:
                record_action(
                    "dispatch",
                    None,
                    "APPLIED",
                    f"release {str(fresh.get('release_id'))[:16]} wave "
                    + (", ".join(fresh.get("released_wave", [])) or "empty"),
                )
    elif acting and not release_valid and policy["auto_redispatch"]:
        # Nothing needed repair, but no valid release exists either: a fresh
        # dispatch is the one lawful move that can authorize an unstarted node.
        unstarted = [d.node_id for d in diagnoses if d.verdict == "UNSTARTED"]
        if unstarted and not current.get("reconciliation_required"):
            try:
                fresh = plane.dispatch(actor=actor)
            except Exception as error:
                record_action("dispatch", None, "FAILED", str(error))
            else:
                wave = [str(item) for item in fresh.get("released_wave", [])]
                record_action(
                    "dispatch",
                    None,
                    "APPLIED",
                    f"release {str(fresh.get('release_id'))[:16]} wave "
                    + (", ".join(wave) or "empty"),
                )
                if any(node_id in wave for node_id in unstarted):
                    healed += 1  # fresh authorization is a state change

    fingerprint = _evidence_fingerprint(plane, diagnoses)
    report["evidence_fingerprint"] = fingerprint
    report["evidence_frozen_minutes"] = _record_observation(plane, fingerprint)

    if acting and policy.get("learn", True) and policy.get("commit_lessons", True):
        # Lessons are worthless to the next session, and to anyone else running
        # this control plane, until they are in the repository.
        try:
            committed = learning.commit_lessons(
                plane,
                actor=actor,
                # `run-round --no-push` means this session advances nothing on
                # the remote; a lesson push would advance the target branch and
                # invalidate the very release the round is working under.
                push=bool(policy.get("push_lessons", False)) and allow_push,
            )
        except Exception as error:
            record_action("commit-lessons", None, "FAILED", str(error))
        else:
            if committed.get("outcome") != "nothing-to-commit":
                record_action(
                    "commit-lessons",
                    None,
                    str(committed.get("outcome", "unknown")).upper(),
                    f"{len(committed.get('paths', []))} lesson file(s)"
                    + (f"; push {committed['push']}" if "push" in committed else ""),
                )

    if healed:
        report["disposition"] = "HEALED"
    elif withheld:
        report["disposition"] = "ACTIONABLE"
    elif open_sessions:
        report["disposition"] = "OPEN_SESSIONS"
        report["open_sessions"] = open_sessions
    elif report["waiting"] or refused:
        # A refused action means the evidence moved under us — the world is
        # live, so the honest disposition is WAITING, never QUIESCENT.
        report["disposition"] = "WAITING"
        if report["waiting"]:
            report["wake_at"] = min(item["wake_at"] for item in report["waiting"])
    elif any(item.get("resolvable") for item in report["stuck"]):
        report["disposition"] = "RESOLVE_BLOCKERS"
    elif report["stuck"]:
        report["disposition"] = "STUCK_HUMAN"
    else:
        report["disposition"] = "QUIESCENT"
    return report
