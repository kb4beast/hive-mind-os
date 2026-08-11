"""Blind-first Curator verification for immutable candidate workspaces.

This module deliberately models the boundary around a verification rather than
performing a repository effect.  A caller must seal every acceptance check
before it supplies a candidate, then present a newly-created, distinct
workspace whose immutable commit and tree identities match the candidate
descriptor.  The Curator receives only the sealed checks and runs them against
that workspace; it cannot reuse Builder scratch space or convert a failed check
into an acceptance.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

from .canonical import canonical_digest
from .verification import TreeSnapshot, snapshot_tree


class CuratorVerificationError(RuntimeError):
    """Raised when independent candidate verification cannot safely proceed."""


class CuratorVerdict(str, Enum):
    """Every completed or fail-closed Curator disposition."""

    ADOPT = "adopt"
    REJECT = "reject"
    REMAND = "remand"
    QUARANTINE = "quarantine"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    """The immutable Git identities a Curator is allowed to verify."""

    commit: str
    tree: str

    def __post_init__(self) -> None:
        _require_sha(self.commit, "candidate commit")
        _require_sha(self.tree, "candidate tree")


@dataclass(frozen=True, slots=True)
class BlindAcceptanceSeal:
    """Acceptance material sealed before the candidate is made available."""

    mission_id: str
    work_id: str
    curator_id: str
    checks: tuple[str, ...]
    failure_verdict: CuratorVerdict
    seal_digest: str

    def __post_init__(self) -> None:
        if not self.mission_id or not self.work_id or not self.curator_id:
            raise CuratorVerificationError("acceptance seal requires mission, work, and Curator identities")
        if not self.checks or any(not item.strip() for item in self.checks):
            raise CuratorVerificationError("acceptance seal requires named checks")
        if len(set(self.checks)) != len(self.checks):
            raise CuratorVerificationError("acceptance checks must be unique")
        if self.failure_verdict not in {CuratorVerdict.REJECT, CuratorVerdict.REMAND}:
            raise CuratorVerificationError("failed acceptance may only reject or remand")
        if self.seal_digest != _seal_digest(self.mission_id, self.work_id, self.curator_id, self.checks, self.failure_verdict):
            raise CuratorVerificationError("acceptance seal digest is invalid")


@dataclass(frozen=True, slots=True)
class IsolatedCandidateWorkspace:
    """A fresh workspace reconstructed independently of the Builder scratchpad."""

    workspace_id: str
    root: Path
    identity: CandidateIdentity
    builder_workspace_id: str
    builder_scratchpad: Path

    def __post_init__(self) -> None:
        if not self.workspace_id or not self.builder_workspace_id:
            raise CuratorVerificationError("workspace identities are required")
        if self.workspace_id == self.builder_workspace_id:
            raise CuratorVerificationError("Curator workspace must differ from Builder workspace")
        root = self.root.resolve()
        scratchpad = self.builder_scratchpad.resolve()
        if root == scratchpad or scratchpad in root.parents or root in scratchpad.parents:
            raise CuratorVerificationError("Curator may not reuse Builder scratchpad")
        if not root.is_dir():
            raise CuratorVerificationError("isolated candidate workspace is unavailable")


@dataclass(frozen=True, slots=True)
class CuratorReport:
    """A fully-bound verification result, including adverse evidence."""

    seal_digest: str
    candidate: CandidateIdentity | None
    workspace_id: str | None
    pre_check_snapshot: TreeSnapshot | None
    post_check_snapshot: TreeSnapshot | None
    check_results: tuple[tuple[str, bool], ...]
    verdict: CuratorVerdict
    reasons: tuple[str, ...]
    report_digest: str

    def __post_init__(self) -> None:
        if self.report_digest != _report_digest(self):
            raise CuratorVerificationError("Curator report digest is invalid")


CheckRunner = Callable[[str, Path], bool]


@dataclass(frozen=True, slots=True)
class _RepositoryBinding:
    """Git metadata which must remain unchanged while the Curator checks run."""

    identity: CandidateIdentity
    index_digest: str
    refs_digest: str


class CuratorRuntime:
    """Run a deterministic, blind-first verification without candidate authority."""

    def seal_acceptance(
        self,
        *,
        mission_id: str,
        work_id: str,
        curator_id: str,
        checks: Sequence[str],
        failure_verdict: CuratorVerdict = CuratorVerdict.REMAND,
    ) -> BlindAcceptanceSeal:
        """Seal complete checks before any candidate workspace is supplied."""

        normalized = tuple(str(item) for item in checks)
        digest = _seal_digest(mission_id, work_id, curator_id, normalized, failure_verdict)
        return BlindAcceptanceSeal(
            mission_id,
            work_id,
            curator_id,
            normalized,
            failure_verdict,
            digest,
        )

    def verify(
        self,
        seal: BlindAcceptanceSeal,
        workspace: IsolatedCandidateWorkspace,
        *,
        candidate: CandidateIdentity,
        check_runner: CheckRunner,
    ) -> CuratorReport:
        """Verify one reconstructed immutable candidate against a prior seal.

        A bad or unavailable workspace is a blocked-evidence verdict.  A
        candidate modified during checks is quarantined because its evidence no
        longer identifies the object which was reviewed.  Ordinary failed
        acceptance checks retain the disposition selected at sealing time.
        """

        if workspace.identity != candidate:
            return self._blocked(seal, "workspace candidate identity does not match requested candidate")
        try:
            before_binding = _repository_binding(workspace.root)
        except CuratorVerificationError as error:
            return self._blocked(seal, f"candidate reconstruction unavailable: {error}")
        if before_binding.identity != candidate:
            return self._blocked(seal, "reconstructed Git commit/tree do not match requested candidate")
        try:
            before = snapshot_tree(workspace.root)
        except (OSError, CuratorVerificationError) as error:
            return self._blocked(seal, f"candidate reconstruction unavailable: {error}")

        results: list[tuple[str, bool]] = []
        for check in seal.checks:
            try:
                passed = bool(check_runner(check, workspace.root))
            except Exception:
                passed = False
            results.append((check, passed))

        try:
            after = snapshot_tree(workspace.root)
        except (OSError, CuratorVerificationError) as error:
            return self._report(seal, candidate, workspace.workspace_id, before, None, results, CuratorVerdict.QUARANTINE, (f"candidate became unreadable during verification: {error}",))
        if after != before:
            return self._report(seal, candidate, workspace.workspace_id, before, after, results, CuratorVerdict.QUARANTINE, ("candidate tree changed during verification",))
        try:
            after_binding = _repository_binding(workspace.root)
        except CuratorVerificationError as error:
            return self._report(seal, candidate, workspace.workspace_id, before, after, results, CuratorVerdict.QUARANTINE, (f"candidate Git metadata became unavailable during verification: {error}",))
        if after_binding != before_binding:
            return self._report(seal, candidate, workspace.workspace_id, before, after, results, CuratorVerdict.QUARANTINE, ("candidate Git commit, tree, index, or refs changed during verification",))
        if all(passed for _, passed in results):
            return self._report(seal, candidate, workspace.workspace_id, before, after, results, CuratorVerdict.ADOPT, ())
        failed = tuple(f"acceptance check failed: {name}" for name, passed in results if not passed)
        return self._report(seal, candidate, workspace.workspace_id, before, after, results, seal.failure_verdict, failed)

    @staticmethod
    def _blocked(seal: BlindAcceptanceSeal, reason: str) -> CuratorReport:
        return CuratorRuntime._report(seal, None, None, None, None, (), CuratorVerdict.BLOCKED, (reason,))

    @staticmethod
    def _report(
        seal: BlindAcceptanceSeal,
        candidate: CandidateIdentity | None,
        workspace_id: str | None,
        before: TreeSnapshot | None,
        after: TreeSnapshot | None,
        results: Sequence[tuple[str, bool]],
        verdict: CuratorVerdict,
        reasons: Sequence[str],
    ) -> CuratorReport:
        document = {
            "seal_digest": seal.seal_digest,
            "candidate": asdict(candidate) if candidate is not None else None,
            "workspace_id": workspace_id,
            "pre_check_snapshot": asdict(before) if before is not None else None,
            "post_check_snapshot": asdict(after) if after is not None else None,
            "check_results": list(results),
            "verdict": verdict.value,
            "reasons": list(reasons),
        }
        return CuratorReport(
            seal.seal_digest,
            candidate,
            workspace_id,
            before,
            after,
            tuple(results),
            verdict,
            tuple(reasons),
            canonical_digest(document),
        )


def _require_sha(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise CuratorVerificationError(f"{label} must be a lowercase 40-hex SHA")


def _repository_identity(root: Path) -> CandidateIdentity:
    """Read the candidate identities from its own Git worktree, fail closed."""

    values = _git_output(root, "rev-parse", "HEAD^{commit}", "HEAD^{tree}").splitlines()
    if len(values) != 2:
        raise CuratorVerificationError("isolated candidate is not a resolvable Git worktree")
    try:
        return CandidateIdentity(values[0], values[1])
    except CuratorVerificationError as error:
        raise CuratorVerificationError("isolated candidate Git identities are malformed") from error


def _repository_binding(root: Path) -> _RepositoryBinding:
    """Capture candidate identity plus mutable Git control metadata."""

    index_location = Path(_git_output(root, "rev-parse", "--git-path", "index"))
    if not index_location.is_absolute():
        index_location = root.resolve() / index_location
    try:
        index_bytes = index_location.read_bytes()
    except OSError as error:
        raise CuratorVerificationError("isolated candidate Git index is unavailable") from error
    refs = _git_output(root, "for-each-ref", "--format=%(refname) %(objectname)")
    return _RepositoryBinding(
        _repository_identity(root),
        canonical_digest({"index": index_bytes.hex()}),
        canonical_digest({"refs": refs.splitlines()}),
    )


def _git_output(root: Path, *arguments: str) -> str:
    """Run one fixed local Git inspection with injected Git controls removed."""

    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        completed = subprocess.run(
            ("git", "-C", str(root.resolve()), *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CuratorVerificationError("cannot read isolated candidate Git metadata") from error
    if completed.returncode != 0:
        raise CuratorVerificationError("isolated candidate Git inspection failed")
    try:
        return completed.stdout.strip()
    except AttributeError as error:
        raise CuratorVerificationError("isolated candidate Git output is malformed") from error


def _seal_digest(
    mission_id: str,
    work_id: str,
    curator_id: str,
    checks: Sequence[str],
    failure_verdict: CuratorVerdict,
) -> str:
    return canonical_digest({
        "mission_id": mission_id,
        "work_id": work_id,
        "curator_id": curator_id,
        "checks": list(checks),
        "failure_verdict": failure_verdict.value,
    })


def _report_digest(report: CuratorReport) -> str:
    document = asdict(report)
    document.pop("report_digest")
    return canonical_digest(document)
