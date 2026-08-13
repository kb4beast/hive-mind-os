"""Durable, shareable memory of which repairs actually hold.

Everything the healer learned used to die with the session.  Its ledgers live
under ``.autopilot/state/``, which is gitignored by design — runtime state is
session-local — so a fresh checkout started amnesiac and repeated repairs that
had already been proven useless.  This module is the memory that survives: it
lives in ``.autopilot/lessons/``, which is committed.

**A repair is judged by whether it holds, not by whether it ran.**  Checking
immediately after acting would be theatre: a reap deletes the branch it just
diagnosed, so the wedge is always "gone" one second later.  Instead every
repair is recorded as an *attempt*, and a **later** pass settles it by
re-observing the node: if the same mechanism is wedging the same node again,
the repair did not hold (``NO_EFFECT``); if the node has moved on,
(``UNBLOCKED``).  A repair that must be re-applied every round is exactly the
polling this control plane exists to end, and this is what detects it.

Lessons are keyed by *mechanism* — ``<verdict>|<proof kind>|<action>``, with no
node id, branch, or SHA — so what is learned is about the control plane rather
than about one incident.  Records are append-only JSONL aggregated at read
time, so concurrent sessions union instead of conflicting.

A mechanism that has been settled ``NO_EFFECT`` three times without ever
holding is **withdrawn**: the healer stops attempting it and reports the
evidence.  Withdrawal is a cooldown, not a life sentence — after
``retry_disproven_after_minutes`` one probation attempt is allowed, so a
mechanism that was broken by a since-fixed bug can earn its place back.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from controller import append_jsonl, digest_json, format_time, parse_time

LESSONS_DIR = "lessons"
RECORD_KIND = "hive-mind-autopilot-lesson-record-v1"
LESSON_COMMIT_NAME = "Hive Mind Autopilot Lessons"
# Deliberately NOT the receipt identity: a lesson commit must never be mistaken
# for a sealed receipt by the evidence observers that key on authorship.
LESSON_COMMIT_EMAIL = "autopilot-lessons@hive-mind.invalid"

OUTCOMES = ("UNBLOCKED", "NO_EFFECT", "REFUSED")
# A mechanism is withdrawn only once it has failed often enough to be evidence
# rather than noise, and has never once held.
DISPROVEN_FAILURES = 3
PROVEN_SUCCESSES = 2
# Consecutive refusals against an unchanging head that mean the environment,
# not a race, is refusing the repair.
STUCK_REFUSALS = 3

_SLUG = re.compile(r"[^a-z0-9]+")


def signature(verdict: str, proof_kind: str, action: str) -> str:
    """Return the mechanism key for a repair, free of any instance identity."""

    return f"{verdict}|{proof_kind or 'none'}|{action}"


def slug(value: str) -> str:
    return _SLUG.sub("-", value.lower()).strip("-") or "unknown"


def lessons_dir(ap_root: Path | str) -> Path:
    return Path(ap_root) / LESSONS_DIR


@dataclass(frozen=True, slots=True)
class Lesson:
    """What the settled record says about one repair mechanism."""

    signature: str
    verdict: str
    proof_kind: str
    action: str
    counts: Mapping[str, int]
    confidence: str  # PROVEN | PROVISIONAL | DISPROVEN | UNTRIED
    mechanism: str
    guidance: str
    first_seen: str | None
    last_seen: str | None
    last_failure: str | None
    stuck_refusals: int
    last_refusal: str | None

    @property
    def attempts(self) -> int:
        return sum(self.counts.get(name, 0) for name in OUTCOMES)

    def refusal_stalled(self, *, limit: int = STUCK_REFUSALS) -> bool:
        """True when the environment keeps refusing this repair outright.

        A refusal normally means a worker won the ``--force-with-lease`` race,
        which moves the head — genuinely inconclusive, and worth retrying. A run
        of refusals against an *unchanging* head is a different animal: branch
        protection, or a token without delete rights. Retrying that forever is
        the polling loop this module exists to end, so it withdraws too.
        """

        return self.stuck_refusals >= limit

    def withdrawn(self, now: datetime, *, cooldown_minutes: int) -> bool:
        """True when the record says attempting this again cannot help yet.

        Withdrawal expires: after the cooldown one probation attempt is allowed
        so a mechanism broken by a since-fixed defect can recover.
        """

        if self.confidence == "DISPROVEN":
            marker = self.last_failure
        elif self.refusal_stalled():
            marker = self.last_refusal
        else:
            return False
        if not marker:
            return True
        try:
            marked_at = parse_time(marker)
        except (TypeError, ValueError):
            return True
        return now - marked_at < timedelta(minutes=max(1, cooldown_minutes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "verdict": self.verdict,
            "proof_kind": self.proof_kind,
            "action": self.action,
            "counts": dict(self.counts),
            "attempts": self.attempts,
            "confidence": self.confidence,
            "mechanism": self.mechanism,
            "guidance": self.guidance,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "last_failure": self.last_failure,
            "stuck_refusals": self.stuck_refusals,
            "refusal_stalled": self.refusal_stalled(),
        }


def _confidence(counts: Mapping[str, int]) -> str:
    held = counts.get("UNBLOCKED", 0)
    failed = counts.get("NO_EFFECT", 0)
    if held + failed == 0:  # refusals prove nothing either way
        return "UNTRIED"
    if held == 0 and failed >= DISPROVEN_FAILURES:
        return "DISPROVEN"
    if held >= PROVEN_SUCCESSES and failed == 0:
        return "PROVEN"
    return "PROVISIONAL"


def _records(ap_root: Path | str) -> list[Mapping[str, Any]]:
    """Read every lesson record, de-duplicated by identity.

    Union-merging two branches of an append-only ledger can replay the same
    record twice; counting it twice would let a merge invent evidence.
    """

    directory = lessons_dir(ap_root)
    if not directory.is_dir():
        return []
    seen: set[str] = set()
    records: list[Mapping[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn line is not a reason to lose the rest
            if not isinstance(value, Mapping) or value.get("kind") != RECORD_KIND:
                continue
            identity = str(value.get("record_id") or "")
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
            records.append(value)
    return records


def _append(ap_root: Path | str, record: dict[str, Any]) -> Mapping[str, Any]:
    record["record_id"] = digest_json(record)
    append_jsonl(lessons_dir(ap_root) / f"{slug(record['signature'])}.jsonl", record)
    return record


def load_lessons(ap_root: Path | str) -> dict[str, Lesson]:
    """Aggregate every settled outcome into one lesson per mechanism."""

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in _records(ap_root):
        if record.get("phase") != "OUTCOME":
            continue
        key = str(record.get("signature") or "")
        if key:
            grouped.setdefault(key, []).append(record)
    lessons: dict[str, Lesson] = {}
    for key, records in grouped.items():
        ordered = sorted(records, key=lambda item: str(item.get("observed_at") or ""))
        counts = {name: 0 for name in OUTCOMES}
        last_failure: str | None = None
        last_refusal: str | None = None
        # A refusal run only counts while the head does not move: a moving head
        # is a lost race (retry it), a frozen one is the environment saying no.
        stuck_refusals = 0
        refusal_head: object = object()
        for record in ordered:
            outcome = str(record.get("outcome") or "")
            if outcome in counts:
                counts[outcome] += 1
            if outcome == "NO_EFFECT":
                last_failure = str(record.get("observed_at") or "") or last_failure
            if outcome == "REFUSED":
                head = record.get("head")
                stuck_refusals = stuck_refusals + 1 if head == refusal_head else 1
                refusal_head = head
                last_refusal = str(record.get("observed_at") or "") or last_refusal
            else:
                stuck_refusals = 0
                refusal_head = object()
        newest = ordered[-1]
        parts = key.split("|")
        lessons[key] = Lesson(
            signature=key,
            verdict=parts[0] if parts else "",
            proof_kind=parts[1] if len(parts) > 1 else "",
            action=parts[2] if len(parts) > 2 else "",
            counts=counts,
            confidence=_confidence(counts),
            mechanism=str(newest.get("mechanism") or ""),
            guidance=str(newest.get("guidance") or ""),
            first_seen=str(ordered[0].get("observed_at") or "") or None,
            last_seen=str(newest.get("observed_at") or "") or None,
            last_failure=last_failure,
            stuck_refusals=stuck_refusals,
            last_refusal=last_refusal,
        )
    return lessons


def consult(ap_root: Path | str, verdict: str, proof_kind: str, action: str) -> Lesson | None:
    """Return what the settled record says about this exact repair."""

    return load_lessons(ap_root).get(signature(verdict, proof_kind, action))


def record_attempt(
    ap_root: Path | str,
    *,
    verdict: str,
    proof_kind: str,
    action: str,
    node_id: str,
    actor: str,
    observed_at: str,
    head: str | None = None,
    mechanism: str = "",
    guidance: str = "",
) -> Mapping[str, Any]:
    """Record that a repair was applied. A later pass judges whether it held."""

    return _append(
        ap_root,
        {
            "kind": RECORD_KIND,
            "schema_version": 1,
            "phase": "ATTEMPT",
            "signature": signature(verdict, proof_kind, action),
            "verdict": verdict,
            "proof_kind": proof_kind,
            "action": action,
            "node_id": node_id,
            "head": head,
            "actor": actor,
            "observed_at": observed_at,
            "mechanism": mechanism,
            "guidance": guidance,
        },
    )


def record_outcome(
    ap_root: Path | str,
    *,
    verdict: str,
    proof_kind: str,
    action: str,
    outcome: str,
    node_id: str,
    actor: str,
    observed_at: str,
    settles: str | None = None,
    head: str | None = None,
    detail: str = "",
    mechanism: str = "",
    guidance: str = "",
) -> Mapping[str, Any]:
    """Record how a repair turned out."""

    if outcome not in OUTCOMES:
        raise ValueError(f"unknown lesson outcome: {outcome}")
    return _append(
        ap_root,
        {
            "kind": RECORD_KIND,
            "schema_version": 1,
            "phase": "OUTCOME",
            "signature": signature(verdict, proof_kind, action),
            "verdict": verdict,
            "proof_kind": proof_kind,
            "action": action,
            "outcome": outcome,
            "node_id": node_id,
            "actor": actor,
            "observed_at": observed_at,
            "settles": settles,
            "head": head,
            "detail": detail,
            "mechanism": mechanism,
            "guidance": guidance,
        },
    )


def unsettled_attempts(ap_root: Path | str) -> tuple[Mapping[str, Any], ...]:
    """Return attempts no later pass has judged yet."""

    settled = {
        str(record.get("settles"))
        for record in _records(ap_root)
        if record.get("phase") == "OUTCOME" and record.get("settles")
    }
    return tuple(
        record
        for record in _records(ap_root)
        if record.get("phase") == "ATTEMPT"
        and str(record.get("record_id")) not in settled
    )


def settle_attempts(
    ap_root: Path | str,
    *,
    observe: Callable[[str], str | None],
    actor: str,
    now: datetime,
) -> tuple[Mapping[str, Any], ...]:
    """Judge earlier repairs by whether their wedge came back.

    ``observe(node_id)`` returns the mechanism signature currently wedging that
    node, or None.  An attempt is only judged on a pass later than its own, so
    the deletion a repair just performed is never mistaken for proof that it
    held.
    """

    settled: list[Mapping[str, Any]] = []
    for attempt in unsettled_attempts(ap_root):
        try:
            attempted_at = parse_time(attempt.get("observed_at"))
        except (TypeError, ValueError):
            continue
        if attempted_at >= now:
            continue  # same pass: too early to judge
        node_id = str(attempt.get("node_id") or "")
        key = str(attempt.get("signature") or "")
        try:
            current = observe(node_id)
        except Exception:
            continue  # an unobservable node is not evidence against the repair
        held = current != key
        settled.append(
            record_outcome(
                ap_root,
                verdict=str(attempt.get("verdict") or ""),
                proof_kind=str(attempt.get("proof_kind") or ""),
                action=str(attempt.get("action") or ""),
                outcome="UNBLOCKED" if held else "NO_EFFECT",
                node_id=node_id,
                actor=actor,
                observed_at=format_time(now),
                settles=str(attempt.get("record_id") or ""),
                detail="the wedge did not return"
                if held
                else "the same mechanism is wedging this node again",
                mechanism=str(attempt.get("mechanism") or ""),
                guidance=str(attempt.get("guidance") or ""),
            )
        )
    return tuple(settled)


# --------------------------------------------------------------- checking in


def _run(plane: Any, *arguments: str) -> tuple[int, str]:
    """Run git through the control plane's hardened runner, never a raw shell."""

    completed = plane._git(tuple(arguments), check=False)
    return completed.returncode, (
        (completed.stdout or "") + (completed.stderr or "")
    ).strip()


def uncommitted_lessons(plane: Any) -> tuple[str, ...]:
    """Return lesson paths that differ from HEAD, including untracked ones."""

    code, output = _run(
        plane,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        f".autopilot/{LESSONS_DIR}",
    )
    if code != 0:
        return ()
    return tuple(line[3:].strip() for line in output.splitlines() if line.strip())


def _operation_in_progress(plane: Any) -> str | None:
    code, git_dir = _run(plane, "rev-parse", "--git-dir")
    if code != 0:
        return "the git directory is unreadable"
    root = Path(plane.repo_root) / git_dir if not Path(git_dir).is_absolute() else Path(git_dir)
    for marker, name in (
        ("MERGE_HEAD", "a merge"),
        ("CHERRY_PICK_HEAD", "a cherry-pick"),
        ("REVERT_HEAD", "a revert"),
        ("BISECT_LOG", "a bisect"),
        ("rebase-merge", "a rebase"),
        ("rebase-apply", "a rebase"),
    ):
        if (root / marker).exists():
            return name
    return None


def commit_lessons(
    plane: Any,
    *,
    actor: str,
    push: bool = False,
    remote: str = "origin",
) -> Mapping[str, Any]:
    """Commit newly recorded lessons, and optionally publish them.

    Refused while any git operation is in progress — committing into a
    conflicted index would sweep a half-finished merge into a lesson commit —
    and refused on the final integration branch.  The commit is pathspec-limited
    to ``.autopilot/lessons``, which is disjoint from every node's write scope,
    and carries its own authorship so it is never mistaken for a receipt.
    """

    pending = uncommitted_lessons(plane)
    if not pending:
        return {"outcome": "nothing-to-commit", "paths": []}
    in_progress = _operation_in_progress(plane)
    if in_progress is not None:
        return {
            "outcome": "refused",
            "reason": f"{in_progress} is in progress; lessons are never committed "
            "into an unfinished operation",
            "paths": list(pending),
        }
    code, branch = _run(plane, "symbolic-ref", "--quiet", "--short", "HEAD")
    if code != 0 or not branch:
        return {"outcome": "refused", "reason": "HEAD is detached", "paths": list(pending)}
    protected = {"main", "master"}
    try:
        protected.add(str(plane.final_integration_branch))
    except Exception:
        pass
    if branch in protected:
        return {
            "outcome": "refused",
            "reason": f"lessons are never committed directly to {branch}",
            "paths": list(pending),
        }
    # A pathspec commit only matches paths git already tracks, and a brand-new
    # lesson file is untracked by definition; stage the directory first, then
    # let the pathspec keep every unrelated staged change out of this commit.
    code, output = _run(plane, "add", "--", f".autopilot/{LESSONS_DIR}")
    if code != 0:
        return {"outcome": "failed", "reason": output, "paths": list(pending)}
    message = f"chore(lessons): record {len(pending)} healing outcome(s)\n\nActor: {actor}"
    code, output = _run(
        plane,
        "-c",
        f"user.name={LESSON_COMMIT_NAME}",
        "-c",
        f"user.email={LESSON_COMMIT_EMAIL}",
        "commit",
        "-m",
        message,
        "--",
        f".autopilot/{LESSONS_DIR}",
    )
    if code != 0:
        return {"outcome": "failed", "reason": output, "paths": list(pending)}
    result: dict[str, Any] = {
        "outcome": "committed",
        "branch": branch,
        "paths": list(pending),
    }
    if push:
        code, output = _run(plane, "push", remote, branch)
        result["push"] = "pushed" if code == 0 else f"failed: {output}"
    return result


def summarize(ap_root: Path | str, *, now: datetime | None = None, cooldown_minutes: int = 720) -> dict[str, Any]:
    """Return the whole settled record, newest activity first."""

    lessons = load_lessons(ap_root)
    rows = []
    for lesson in lessons.values():
        row = lesson.to_dict()
        if now is not None:
            row["withdrawn"] = lesson.withdrawn(now, cooldown_minutes=cooldown_minutes)
        rows.append(row)
    rows.sort(key=lambda item: (str(item.get("last_seen") or ""), item["signature"]), reverse=True)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["confidence"]] = counts.get(row["confidence"], 0) + 1
    return {
        "kind": "hive-mind-autopilot-lesson-index-v1",
        "total": len(rows),
        "by_confidence": dict(sorted(counts.items())),
        "pending_attempts": len(unsettled_attempts(ap_root)),
        "lessons": rows,
    }


def seed(ap_root: Path | str, entries: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Write settled outcomes for verified incidents (used by the seeder)."""

    written = []
    for entry in entries:
        written.append(
            record_outcome(
                ap_root,
                verdict=str(entry["verdict"]),
                proof_kind=str(entry["proof_kind"]),
                action=str(entry["action"]),
                outcome=str(entry["outcome"]),
                node_id=str(entry.get("node_id", "")),
                actor=str(entry.get("actor", "verified-incident")),
                observed_at=str(entry["observed_at"]),
                detail=str(entry.get("detail", "")),
                mechanism=str(entry.get("mechanism", "")),
                guidance=str(entry.get("guidance", "")),
            )
        )
    return written


__all__ = [
    "Lesson",
    "commit_lessons",
    "consult",
    "load_lessons",
    "lessons_dir",
    "record_attempt",
    "record_outcome",
    "seed",
    "settle_attempts",
    "signature",
    "slug",
    "summarize",
    "unsettled_attempts",
    "uncommitted_lessons",
]
