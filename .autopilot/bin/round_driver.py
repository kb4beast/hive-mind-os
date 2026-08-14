"""Drive one dispatch round: integrate, validate, and triage, as code.

The wave supervisor in ``host_execution`` ends when every worker is terminal. The
work that follows it — merging node branches in the wave's declared order, running
the round's single leased repository-wide gate, and deciding what a blocker means
— lived only in ``docs/execution/runbooks/README.md`` as prose an operator or a
model had to re-read and re-obey every round.

This module is that prose as a program. Every phase is idempotent, so re-running
after a stall resumes instead of repeating: integration skips branches already in
the target's ancestry, validation refuses to run before the wave is whole, and
triage acts only on the mechanical class of blocker. Anything requiring judgement
is reported with its evidence rather than guessed at.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import healing
from attended_host import RECEIPT_IDENTITY
from dag_standard import DEFAULT_MAX_SESSIONS, Round, compile_rounds, load_plan_graph
from durable_controller import RECEIPT_COMMIT_MARKER

FULL_SHA = re.compile(r"[0-9a-f]{40}")
AUTHORITY_ID = re.compile(r"sha256:[0-9a-f]{64}")

FIXED_GATE_HARNESS = """\
import pathlib
import sys
import unittest

root = pathlib.Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(root))
source = root / "src"
if source.is_dir():
    sys.path.insert(0, str(source))
suite = unittest.defaultTestLoader.discover(
    start_dir=str(root / "tests"),
    pattern="test*.py",
    top_level_dir=str(root / "tests"),
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""
FIXED_GATE_FORBIDDEN_SHADOWS = (
    Path("sitecustomize.py"),
    Path("usercustomize.py"),
    Path("unittest.py"),
    Path("src/sitecustomize.py"),
    Path("src/usercustomize.py"),
    Path("src/unittest.py"),
)


def fixed_validation_environment_policy() -> Mapping[str, object]:
    return {
        "kind": "hive-mind-fixed-validation-environment-policy-v1",
        "strip_environment_prefixes": ["GIT_", "PYTHON"],
        "isolated_interpreter_flags": ["-I", "-S", "-B"],
        "harness_digest": "sha256:"
        + sha256(FIXED_GATE_HARNESS.encode("utf-8")).hexdigest(),
        "git_no_replace_objects": "1",
        "reject_git_grafts_and_replace_refs": True,
        "forbidden_startup_shadows": [
            path.as_posix() for path in FIXED_GATE_FORBIDDEN_SHADOWS
        ],
    }


# A blocker naming any of these is sealed or external: repairing it would rotate
# the plan fingerprint or fabricate authority, so the driver never touches it.
# The tuple lives in healing so triage and the healer never disagree about what
# is untouchable.
_SEALED_MARKERS = healing.SEALED_MARKERS
# A blocker naming any of these is a stale artifact the control plane owns a verb
# for. These are the only blockers the driver resolves without being asked.
_STALE_MARKERS = (
    "remote branch already exists",
    "already exists; reconcile",
    "does not descend",
    "stale claim",
    "stale target",
)


class RoundDriverError(RuntimeError):
    """Raised when the driver is asked to act from an unsafe position."""


class RoundValidationError(RoundDriverError):
    """Carries every adverse validation/renewal/release outcome without masking."""

    def __init__(self, failures: Sequence[BaseException]) -> None:
        self.failures = tuple(failures)
        detail = "; ".join(
            f"{type(error).__name__}: {error}" for error in self.failures
        )
        super().__init__(
            "validation transaction requires reconciliation"
            + (f": {detail}" if detail else "")
        )


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class FixedValidationRunner:
    """Run the one public gate and retain exact, content-bound gate evidence."""

    def __init__(
        self,
        repo_root: Path,
        *,
        expected_head: str | None = None,
        transaction_ref: str | None = None,
        require_clean: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.expected_head = expected_head
        self.transaction_ref = transaction_ref
        self.require_clean = require_clean
        self.validation_evidence: Mapping[str, object] | None = None

    @staticmethod
    def _environment(repo_root: Path) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(("GIT_", "PYTHON"))
        }
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
        return environment

    def _git_scalar(
        self,
        git_executable: Path,
        environment: Mapping[str, str],
        *arguments: str,
        label: str,
    ) -> str:
        completed = subprocess.run(
            (str(git_executable), *arguments),
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            env=dict(environment),
        )
        value = completed.stdout.strip()
        if completed.returncode != 0 or FULL_SHA.fullmatch(value) is None:
            raise RoundDriverError(f"fixed validation could not seal its {label}")
        return value

    def _status(self, git_executable: Path, environment: Mapping[str, str]) -> str:
        completed = subprocess.run(
            (
                str(git_executable),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            env=dict(environment),
        )
        if completed.returncode != 0:
            raise RoundDriverError("fixed validation could not inspect worktree state")
        return completed.stdout

    def _reject_git_object_overlays(
        self, git_executable: Path, environment: Mapping[str, str]
    ) -> None:
        common = subprocess.run(
            (str(git_executable), "rev-parse", "--git-common-dir"),
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            env=dict(environment),
        )
        if common.returncode != 0 or not common.stdout.strip():
            raise RoundDriverError("fixed validation cannot resolve Git common state")
        common_dir = Path(common.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = self.repo_root / common_dir
        common_dir = common_dir.resolve()
        grafts = common_dir / "info" / "grafts"
        replace_dir = common_dir / "refs" / "replace"
        packed_refs = common_dir / "packed-refs"
        if grafts.exists():
            raise RoundDriverError("fixed validation refuses legacy Git grafts")
        if replace_dir.exists() and any(replace_dir.rglob("*")):
            raise RoundDriverError("fixed validation refuses Git replacement refs")
        if packed_refs.is_file() and " refs/replace/" in packed_refs.read_text(
            encoding="utf-8", errors="strict"
        ):
            raise RoundDriverError("fixed validation refuses packed replacement refs")
        replacements = subprocess.run(
            (
                str(git_executable),
                "for-each-ref",
                "--format=%(refname)",
                "refs/replace",
            ),
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            env=dict(environment),
        )
        if replacements.returncode != 0 or replacements.stdout.strip():
            raise RoundDriverError("fixed validation refuses Git replacement refs")

    def __call__(self) -> tuple[bool, str]:
        environment = self._environment(self.repo_root)
        shadowed = [
            path.as_posix()
            for path in FIXED_GATE_FORBIDDEN_SHADOWS
            if (self.repo_root / path).exists()
        ]
        if shadowed:
            raise RoundDriverError(
                "fixed validation refuses interpreter-startup shadows: "
                + ", ".join(shadowed)
            )
        git_command = shutil.which("git", path=environment.get("PATH"))
        if git_command is None:
            raise RoundDriverError("fixed validation Git executable is unavailable")
        git_executable = Path(git_command).resolve()
        if not git_executable.is_file():
            raise RoundDriverError("fixed validation Git executable is invalid")
        git_before = _file_digest(git_executable)
        self._reject_git_object_overlays(git_executable, environment)
        interpreter = Path(sys.executable).resolve()
        runner_module = Path(__file__).resolve()
        interpreter_before = _file_digest(interpreter)
        runner_before = _file_digest(runner_module)
        tree_before = self._git_scalar(
            git_executable,
            environment,
            "rev-parse",
            "HEAD^{tree}",
            label="worktree tree",
        )
        environment_policy_digest = _canonical_digest(
            fixed_validation_environment_policy()
        )
        argv = (
            str(interpreter),
            "-I",
            "-S",
            "-B",
            "-c",
            FIXED_GATE_HARNESS,
            str(self.repo_root),
        )
        started_at = _utc_now()
        completed = subprocess.run(
            argv,
            cwd=str(self.repo_root),
            capture_output=True,
            env=environment,
        )
        completed_at = _utc_now()
        interpreter_after = _file_digest(interpreter)
        runner_after = _file_digest(runner_module)
        git_after = _file_digest(git_executable)
        tree_after = self._git_scalar(
            git_executable,
            environment,
            "rev-parse",
            "HEAD^{tree}",
            label="worktree tree",
        )
        head_after = self._git_scalar(
            git_executable,
            environment,
            "rev-parse",
            "HEAD",
            label="worktree HEAD",
        )
        ref_after = (
            self._git_scalar(
                git_executable,
                environment,
                "rev-parse",
                self.transaction_ref,
                label="private transaction ref",
            )
            if self.transaction_ref is not None
            else head_after
        )
        status_after = self._status(git_executable, environment)
        if interpreter_after != interpreter_before:
            raise RoundDriverError(
                "fixed validation interpreter changed while the gate was running"
            )
        if runner_after != runner_before:
            raise RoundDriverError(
                "fixed validation runner changed while the gate was running"
            )
        if git_after != git_before:
            raise RoundDriverError(
                "fixed validation Git executable changed while the gate was running"
            )
        if tree_after != tree_before:
            raise RoundDriverError(
                "fixed validation commit tree changed while the gate was running"
            )
        if self.expected_head is not None and (
            head_after != self.expected_head or ref_after != self.expected_head
        ):
            raise RoundDriverError(
                "fixed validation changed the pinned HEAD or private transaction ref"
            )
        if self.require_clean and status_after:
            raise RoundDriverError(
                "fixed validation left tracked or untracked worktree changes"
            )
        stdout = bytes(completed.stdout or b"")
        stderr = bytes(completed.stderr or b"")
        displayed = (stderr or stdout).decode("utf-8", errors="replace")
        tail = displayed.strip().splitlines()
        summary = tail[-1] if tail else "no test output"
        gate_material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-fixed-publication-gate-result-v1",
            "argv": list(argv),
            "interpreter_path": str(interpreter),
            "interpreter_digest_before": interpreter_before,
            "interpreter_digest_after": interpreter_after,
            "round_driver_path": str(runner_module),
            "round_driver_digest_before": runner_before,
            "round_driver_digest_after": runner_after,
            "git_executable_path": str(git_executable),
            "git_executable_digest_before": git_before,
            "git_executable_digest_after": git_after,
            "worktree_tree": tree_before,
            "worktree_head_after": head_after,
            "transaction_ref_after": ref_after,
            "worktree_status_porcelain": status_after,
            "environment_policy_digest": environment_policy_digest,
            "started_at": started_at,
            "completed_at": completed_at,
            "exit_code": int(completed.returncode),
            "output_digest": "sha256:" + sha256(stdout + b"\x00" + stderr).hexdigest(),
            "summary": summary,
        }
        self.validation_evidence = gate_material
        return completed.returncode == 0, summary


class PrivateRoundWorkspace:
    """A disposable detached checkout whose durable authority is a private ref."""

    def __init__(self, plane: Any, transaction: Mapping[str, object]) -> None:
        transaction_id = transaction.get("transaction_id")
        transaction_ref = transaction.get("transaction_ref")
        base_sha = transaction.get("expected_target_sha")
        if (
            not isinstance(transaction_id, str)
            or not isinstance(transaction_ref, str)
            or not isinstance(base_sha, str)
            or FULL_SHA.fullmatch(base_sha) is None
        ):
            raise RoundDriverError(
                "publication transaction workspace authority is malformed"
            )
        expected_ref = getattr(plane, "execution_transaction_ref", lambda _value: None)(
            transaction_id
        )
        if expected_ref != transaction_ref:
            raise RoundDriverError("publication transaction ref is not canonical")
        checked = _git(plane, "check-ref-format", transaction_ref)
        if checked.returncode != 0:
            raise RoundDriverError("publication transaction ref is invalid")
        self.plane = plane
        self.transaction_id = transaction_id
        self.transaction_ref = transaction_ref
        self.base_sha = base_sha
        status = transaction.get("status")
        pinned_sha = transaction.get("pinned_sha")
        if (
            status not in {"PREPARED", "PINNED"}
            or (status == "PREPARED" and pinned_sha is not None)
            or (
                status == "PINNED"
                and (
                    not isinstance(pinned_sha, str)
                    or FULL_SHA.fullmatch(pinned_sha) is None
                )
            )
        ):
            raise RoundDriverError(
                "publication transaction workspace state is not exactly sealed"
            )
        self.sealed_sha = pinned_sha or base_sha
        self.parent: Path | None = None
        self.path: Path | None = None
        self._registered = False

    def __enter__(self) -> PrivateRoundWorkspace:
        current = _git(
            self.plane,
            "rev-parse",
            "--verify",
            f"{self.transaction_ref}^{{commit}}",
        )
        if current.returncode != 0:
            created = _git(
                self.plane,
                "update-ref",
                self.transaction_ref,
                self.base_sha,
                "0" * 40,
            )
            if created.returncode != 0:
                raise RoundDriverError(
                    "cannot initialize the private publication transaction ref"
                )
            current_sha = self.base_sha
        else:
            current_sha = current.stdout.strip()
        if FULL_SHA.fullmatch(current_sha) is None or current_sha != self.sealed_sha:
            raise RoundDriverError(
                "private publication transaction ref differs from its exact sealed state"
            )
        self.parent = Path(tempfile.mkdtemp(prefix="hive-mind-round-"))
        self.path = self.parent / "checkout"
        added = _git(
            self.plane,
            "worktree",
            "add",
            "--detach",
            "--no-checkout",
            str(self.path),
            current_sha,
        )
        if added.returncode != 0:
            try:
                self.parent.rmdir()
            except OSError:
                pass
            raise RoundDriverError(
                "cannot create the disposable publication worktree: "
                + added.stderr.strip()
            )
        self._registered = True
        checked_out = _git_at(
            self.plane, self.path, "checkout", "--detach", current_sha
        )
        if checked_out.returncode != 0:
            primary = RoundDriverError(
                "cannot check out the private publication transaction ref"
            )
            cleanup = self._cleanup()
            if cleanup is not None:
                raise BaseExceptionGroup(
                    "private checkout and cleanup both failed", [primary, cleanup]
                )
            raise primary
        return self

    def _cleanup(self) -> BaseException | None:
        failure: BaseException | None = None
        if self._registered and self.path is not None:
            removed = _git(self.plane, "worktree", "remove", "--force", str(self.path))
            if removed.returncode != 0:
                failure = RoundDriverError(
                    "disposable publication worktree cleanup requires reconciliation: "
                    + removed.stderr.strip()
                )
            else:
                self._registered = False
        if not self._registered and self.parent is not None:
            try:
                self.parent.rmdir()
            except OSError as error:
                failure = failure or error
        return failure

    def __exit__(self, exc_type, exc, traceback) -> bool:
        cleanup = self._cleanup()
        if cleanup is not None and exc is not None:
            raise BaseExceptionGroup(
                "round transaction and workspace cleanup both failed",
                [exc, cleanup],
            )
        if cleanup is not None:
            raise cleanup
        return False


class PublicationLeaseRenewer:
    """Keep one exact coordinator token live without holding authority locks."""

    def __init__(
        self,
        plane: Any,
        transaction: Mapping[str, object],
        *,
        coordinator_id: str,
        lease_minutes: int = 15,
        interval_seconds: float | None = None,
    ) -> None:
        if (
            not coordinator_id.strip()
            or type(lease_minutes) is not int
            or lease_minutes < 1
        ):
            raise RoundDriverError("publication coordinator lease authority is invalid")
        self.plane = plane
        self.coordinator_id = coordinator_id
        self.lease_minutes = lease_minutes
        self.interval = (
            max(0.01, float(interval_seconds))
            if interval_seconds is not None
            else max(1.0, min(30.0, lease_minutes * 20.0))
        )
        self._token: Mapping[str, object] = dict(transaction)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._failures: list[BaseException] = []
        self._thread = threading.Thread(
            target=self._run,
            name=f"publication-lease-renewer:{transaction.get('transaction_id')}",
            daemon=True,
        )

    def start(self) -> PublicationLeaseRenewer:
        self._thread.start()
        return self

    def adopt(self, transaction: Mapping[str, object]) -> None:
        """Adopt a durable state transition without losing the exact lease token."""

        with self._lock:
            current = dict(self._token)
            if any(
                transaction.get(field) != current.get(field)
                for field in ("transaction_id", "transaction_lease_id")
            ):
                raise RoundDriverError(
                    "publication coordinator cannot adopt a different transaction fence"
                )
            self._token = dict(transaction)

    def transition(
        self,
        transition: Callable[[Mapping[str, object]], Mapping[str, object]],
    ) -> Mapping[str, object]:
        """Serialize a durable FSM transition with coordinator lease renewal."""

        with self._lock:
            current = dict(self._token)
            changed = transition(current)
            if not isinstance(changed, Mapping) or any(
                changed.get(field) != current.get(field)
                for field in ("transaction_id", "transaction_lease_id")
            ):
                raise RoundDriverError(
                    "publication transition returned a different transaction fence"
                )
            self._token = dict(changed)
            return dict(changed)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                with self._lock:
                    current = dict(self._token)
                    lease_id = current.get("transaction_lease_id")
                    if not isinstance(lease_id, str):
                        raise RoundDriverError(
                            "publication coordinator token lacks its lease id"
                        )
                    renewed = self.plane.renew_publication_transaction(
                        current,
                        coordinator_id=self.coordinator_id,
                        transaction_lease_id=lease_id,
                        lease_minutes=self.lease_minutes,
                    )
                    if not isinstance(renewed, Mapping):
                        raise RoundDriverError(
                            "publication coordinator renewal returned malformed authority"
                        )
                    self._token = dict(renewed)
            except BaseException as error:
                self._failures.append(error)
                self._stop.set()
                return

    def settle(self) -> Mapping[str, object]:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval + 1.0))
        failures = list(self._failures)
        if self._thread.is_alive():
            failures.append(
                RoundDriverError("publication coordinator lease renewer did not settle")
            )
        if failures:
            raise RoundValidationError(failures)
        with self._lock:
            return dict(self._token)


@dataclass(frozen=True, slots=True)
class Step:
    phase: str
    node_id: str | None
    outcome: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "node_id": self.node_id,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass
class RoundReport:
    round_id: str | None = None
    nodes: tuple[str, ...] = ()
    steps: list[Step] = field(default_factory=list)
    blocked: bool = False

    def record(
        self, phase: str, node_id: str | None, outcome: str, detail: str
    ) -> Step:
        step = Step(phase=phase, node_id=node_id, outcome=outcome, detail=detail)
        self.steps.append(step)
        if outcome in {
            "CONFLICT",
            "FAILED",
            "CLASS_A",
            "CLASS_C",
            "RECOVERY_REQUIRED",
            "PUBLISH_UNKNOWN",
        }:
            self.blocked = True
        return step

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "nodes": list(self.nodes),
            "blocked": self.blocked,
            "steps": [step.to_dict() for step in self.steps],
        }


def _git(
    plane: Any, *arguments: str, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return plane._git(tuple(arguments), check=check)


def _git_at(
    plane: Any,
    worktree: Path,
    *arguments: str,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return plane._git(("-C", str(worktree), *arguments), check=check)


def _parse_canonical_receipt_message(message: str) -> Mapping[str, object] | None:
    """Parse exactly the canonical durable-receipt commit payload.

    An author email is not authority. Duplicate JSON keys, non-finite values, a
    noncanonical representation, or the absence of the completion marker all fail
    closed before the candidate can reach a merge command.
    """

    prefix = RECEIPT_COMMIT_MARKER + "\n"
    stripped = message.rstrip("\n")
    if not stripped.startswith(prefix):
        return None
    payload = stripped[len(prefix) :]

    def object_pairs(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate receipt key: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite receipt constant: {value}")

    try:
        value = json.loads(
            payload,
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    canonical = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return value if canonical == payload else None


def receipt_head(
    plane: Any,
    node_id: str,
    *,
    expected_target_sha: str | None = None,
) -> str | None:
    """Return only a fully authenticated durable receipt-commit head."""

    branch = str(plane.node(node_id).get("branch"))
    head = plane.remote_branch_sha(branch)
    if not isinstance(head, str) or FULL_SHA.fullmatch(head) is None:
        return None
    fetched = _git(
        plane,
        "fetch",
        "--no-tags",
        "--no-write-fetch-head",
        "origin",
        f"refs/heads/{branch}",
    )
    if fetched.returncode != 0:
        return None
    identity = _git(plane, "show", "-s", "--format=%ae%x1f%ce", head)
    if identity.returncode != 0 or identity.stdout.strip().split("\x1f") != [
        RECEIPT_IDENTITY,
        RECEIPT_IDENTITY,
    ]:
        return None
    shown = _git(plane, "show", "-s", "--format=%P%x1f%T%x1f%B", head)
    if shown.returncode != 0:
        return None
    parts = shown.stdout.split("\x1f", 2)
    if len(parts) != 3:
        return None
    parents = tuple(parts[0].split())
    receipt_tree = parts[1].strip()
    receipt = _parse_canonical_receipt_message(parts[2])
    if receipt is None or len(parents) != 1:
        return None
    final = receipt.get("final_commit")
    final_tree = receipt.get("final_tree")
    if (
        receipt.get("node_id") != node_id
        or receipt.get("branch") != branch
        or not isinstance(final, str)
        or parents != (final,)
        or not isinstance(final_tree, str)
        or receipt_tree != final_tree
    ):
        return None
    parent_tree = _git(plane, "rev-parse", f"{final}^{{tree}}")
    if parent_tree.returncode != 0 or parent_tree.stdout.strip() != final_tree:
        return None
    if (
        expected_target_sha is not None
        and receipt.get("base_commit") != expected_target_sha
    ):
        return None
    validate = getattr(plane, "validate_receipt", None)
    provenance = getattr(plane, "_claim_provenance_issues", None)
    if not callable(validate) or not callable(provenance):
        return None
    if tuple(validate(node_id, receipt, require_integrated=False)):
        return None
    if tuple(provenance(node_id, receipt)):
        return None
    # Re-read the remote branch after every object/content check. A worker or stale
    # process that advances it during preflight cannot smuggle an unvalidated head
    # into the pinned wave.
    return head if plane.remote_branch_sha(branch) == head else None


def select_round(
    plane: Any,
    status: Mapping[str, Any],
    *,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    plan_path: Path | None = None,
) -> Round | None:
    """Return the first compiled round that is not already complete."""

    graph = load_plan_graph(plan_path or Path(plane.ap_root) / "plan.json")
    complete = completed_nodes(status)
    for candidate in compile_rounds(graph, max_sessions=max_sessions):
        if not set(candidate.nodes) <= complete:
            return candidate
    return None


def completed_nodes(status: Mapping[str, Any]) -> set[str]:
    """Return the nodes the control plane currently recognises as COMPLETE.

    ``status["complete"]`` is a plan-wide boolean, not a node list; per-node truth
    lives in the ``nodes`` rows. Reading the boolean as a collection silently
    yields an empty set, which makes every compiled round look unfinished and
    re-selects rounds that were integrated weeks ago.
    """

    rows = status.get("nodes")
    if not isinstance(rows, Sequence):
        return set()
    return {
        str(row.get("node_id"))
        for row in rows
        if isinstance(row, Mapping) and row.get("state") == "COMPLETE"
    }


_PUBLIC_AUTHORITY_INVENTORIES = (
    "active_write_launch_reservations",
    "active_host_reservations",
    "execution_global_host_reservations",
    "active_claims",
    "terminal_launch_bindings",
    "terminal_sidecar_bindings",
    "conflicting_global_reservations",
    "reconciliation_obligations",
)


def _strict_public_authority_inventory(
    snapshot: Mapping[str, Any],
) -> Mapping[str, tuple[Mapping[str, object], ...]]:
    """Require every typed inventory from the one locked authority snapshot."""

    inventories: dict[str, tuple[Mapping[str, object], ...]] = {}
    for key in _PUBLIC_AUTHORITY_INVENTORIES:
        value = snapshot.get(key)
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
            or any(not isinstance(item, Mapping) for item in value)
        ):
            raise RoundDriverError(
                f"round authority snapshot is missing a typed {key} inventory"
            )
        inventories[key] = tuple(dict(item) for item in value)
    return inventories


def _strict_round_authority_snapshot(
    plane: Any,
    snapshot: Mapping[str, object],
    *,
    release_id: str,
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, tuple[Mapping[str, object], ...]],
]:
    """Authenticate one atomic controller snapshot without any unlocked reread."""

    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("kind") != "hive-mind-round-authority-snapshot-v1"
        or snapshot.get("release_id") != release_id
        or AUTHORITY_ID.fullmatch(str(snapshot.get("authority_digest"))) is None
    ):
        raise RoundDriverError("round authority snapshot envelope is malformed")
    expected_execution_id = getattr(plane, "execution_id", None)
    expected_namespace = getattr(plane, "execution_namespace", None)
    if (
        not isinstance(expected_execution_id, str)
        or snapshot.get("execution_id") != expected_execution_id
        or not isinstance(expected_namespace, str)
        or snapshot.get("execution_namespace") != expected_namespace
    ):
        raise RoundDriverError("round authority snapshot execution identity mismatch")
    release = snapshot.get("release")
    status = snapshot.get("status")
    if not isinstance(release, Mapping) or not isinstance(status, Mapping):
        raise RoundDriverError("round authority snapshot lacks release or DAG status")
    released_wave = release.get("released_wave")
    if (
        release.get("release_id") != release_id
        or release.get("admission_epoch") != snapshot.get("admission_epoch")
        or release.get("execution_id") != expected_execution_id
        or release.get("execution_namespace") != expected_namespace
        or type(release.get("admission_epoch")) is not int
        or int(release["admission_epoch"]) < 1
        or type(release.get("session_cap")) is not int
        or int(release["session_cap"]) < 1
        or not isinstance(release.get("host_id"), str)
        or not str(release["host_id"]).strip()
        or not isinstance(release.get("target_branch"), str)
        or FULL_SHA.fullmatch(str(release.get("target_sha"))) is None
        or not isinstance(released_wave, list)
        or any(not isinstance(node_id, str) or not node_id for node_id in released_wave)
        or len(released_wave) != len(set(released_wave))
        or len(released_wave) > int(release["session_cap"])
        or AUTHORITY_ID.fullmatch(str(release.get("capacity_generation"))) is None
        or AUTHORITY_ID.fullmatch(str(release.get("capacity_record_id"))) is None
        or type(release.get("capacity_epoch")) is not int
        or int(release["capacity_epoch"]) < 1
        or type(release.get("capacity_max_total_sessions")) is not int
        or int(release["capacity_max_total_sessions"]) < 1
        or int(release["session_cap"]) > int(release["capacity_max_total_sessions"])
        or type(release.get("capacity_validation_slots")) is not int
        or int(release["capacity_validation_slots"]) < 0
        or int(release["capacity_validation_slots"])
        > int(release["capacity_max_total_sessions"])
    ):
        raise RoundDriverError("round authority snapshot release is malformed")
    nodes = status.get("nodes")
    if (
        not isinstance(nodes, Sequence)
        or isinstance(nodes, (str, bytes))
        or any(not isinstance(row, Mapping) for row in nodes)
        or type(status.get("complete")) is not bool
        or type(status.get("reconciliation_required")) is not bool
    ):
        raise RoundDriverError("round authority snapshot DAG status is malformed")
    inventories = _strict_public_authority_inventory(snapshot)
    lease = snapshot.get("active_validation_lease")
    transaction = snapshot.get("publication_transaction_fence")
    capacities = snapshot.get("host_capacity_generations")
    issuance = snapshot.get("release_capacity_issuance_record")
    active_publication_count = snapshot.get("active_publication_count")
    if lease is not None and not isinstance(lease, Mapping):
        raise RoundDriverError("round authority snapshot validation lease is malformed")
    if transaction is not None and not isinstance(transaction, Mapping):
        raise RoundDriverError(
            "round authority snapshot publication fence is malformed"
        )
    if (
        type(active_publication_count) is not int
        or active_publication_count not in {0, 1}
        or active_publication_count != (1 if transaction is not None else 0)
    ):
        raise RoundDriverError(
            "round authority snapshot publication count is malformed"
        )
    if not isinstance(capacities, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, Mapping)
        for key, value in capacities.items()
    ):
        raise RoundDriverError("round authority snapshot capacity map is malformed")
    host_capacity = capacities.get(str(release["host_id"]))
    if not isinstance(host_capacity, Mapping) or any(
        host_capacity.get(capacity_field) != release.get(release_field)
        for capacity_field, release_field in (
            ("capacity_generation", "capacity_generation"),
            ("capacity_epoch", "capacity_epoch"),
            ("max_total_sessions", "capacity_max_total_sessions"),
            ("validation_slots", "capacity_validation_slots"),
        )
    ):
        raise RoundDriverError("round release is not bound to captured host capacity")
    if not isinstance(issuance, Mapping) or any(
        issuance.get(capacity_field) != release.get(release_field)
        for capacity_field, release_field in (
            ("host_id", "host_id"),
            ("capacity_generation", "capacity_generation"),
            ("capacity_epoch", "capacity_epoch"),
            ("record_id", "capacity_record_id"),
            ("max_total_sessions", "capacity_max_total_sessions"),
            ("validation_slots", "capacity_validation_slots"),
        )
    ):
        raise RoundDriverError(
            "round release capacity issuance is outside the authenticated renewal lineage"
        )
    return dict(release), dict(status), inventories


def _round_from_release(release: Mapping[str, object]) -> Round | None:
    """Use the dispatcher-authenticated ordered frontier, never a local plan copy."""

    released = release.get("released_wave")
    if not isinstance(released, list):
        raise RoundDriverError("round release wave is malformed")
    if not released:
        return None
    material = json.dumps(
        {
            "kind": "hive-mind-released-round-key-v1",
            "execution_id": release.get("execution_id"),
            "release_id": release.get("release_id"),
            "admission_epoch": release.get("admission_epoch"),
            "released_wave": released,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    round_id = "sha256:" + sha256(material).hexdigest()
    return Round(
        round_id=round_id,
        level=0,
        nodes=tuple(str(item) for item in released),
        parallel_safe=len(released) > 1,
        reason="exact canonical dispatcher release",
        command=str(release.get("action") or "authenticated release"),
    )


def integrate_private_round(
    plane: Any,
    workspace: PrivateRoundWorkspace,
    round_: Round,
    report: RoundReport,
    *,
    sealed_heads: Mapping[str, str],
) -> str:
    """Integrate a whole pinned wave without changing any shared target checkout."""

    if workspace.path is None:
        raise RoundDriverError("private publication worktree is not active")
    initial = _git_at(plane, workspace.path, "rev-parse", "--verify", "HEAD")
    if initial.returncode != 0 or FULL_SHA.fullmatch(initial.stdout.strip()) is None:
        raise RoundDriverError("private publication worktree has no exact HEAD")
    initial_sha = initial.stdout.strip()
    if (
        _git_at(
            plane,
            workspace.path,
            "merge-base",
            "--is-ancestor",
            workspace.base_sha,
            initial_sha,
        ).returncode
        != 0
    ):
        raise RoundDriverError("private integration ref lost its sealed base ancestry")
    for node_id in round_.nodes:
        head = sealed_heads.get(node_id)
        if not isinstance(head, str) or FULL_SHA.fullmatch(head) is None:
            raise RoundDriverError(
                f"private integration lacks a pinned receipt: {node_id}"
            )
        if (
            _git_at(
                plane,
                workspace.path,
                "merge-base",
                "--is-ancestor",
                head,
                "HEAD",
            ).returncode
            == 0
        ):
            report.record(
                "integrate",
                node_id,
                "ALREADY",
                f"{head[:7]} is already in the transaction",
            )
            continue
        merged = _git_at(
            plane,
            workspace.path,
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "merge.verifySignatures=false",
            "merge",
            "--no-ff",
            "--no-edit",
            head,
        )
        if merged.returncode != 0:
            _git_at(plane, workspace.path, "merge", "--abort")
            report.record(
                "integrate",
                node_id,
                "CONFLICT",
                "the private transaction found a scope-contract merge conflict",
            )
            raise RoundDriverError(f"private round integration conflict for {node_id}")
        report.record("integrate", node_id, "INTEGRATED", f"merged {head[:7]} --no-ff")
    resolved = _git_at(plane, workspace.path, "rev-parse", "--verify", "HEAD")
    pinned_sha = resolved.stdout.strip() if resolved.returncode == 0 else ""
    if FULL_SHA.fullmatch(pinned_sha) is None:
        raise RoundDriverError("private integration did not produce a commit")
    for ancestor in (workspace.base_sha, *sealed_heads.values()):
        if (
            _git_at(
                plane,
                workspace.path,
                "merge-base",
                "--is-ancestor",
                ancestor,
                pinned_sha,
            ).returncode
            != 0
        ):
            raise RoundDriverError(
                "private integration commit lacks sealed base or receipt ancestry"
            )
    updated = _git(
        plane,
        "update-ref",
        workspace.transaction_ref,
        pinned_sha,
        initial_sha,
    )
    if updated.returncode != 0:
        observed = _git(
            plane,
            "rev-parse",
            "--verify",
            f"{workspace.transaction_ref}^{{commit}}",
        )
        if observed.returncode != 0 or observed.stdout.strip() != pinned_sha:
            raise RoundDriverError("private transaction ref compare-and-swap failed")
    return pinned_sha


def assert_private_validation_state(
    plane: Any,
    workspace: PrivateRoundWorkspace,
    *,
    pinned_sha: str,
    sealed_heads: Mapping[str, str],
) -> None:
    """Prove that the fixed gate did not replace or dirty its pinned checkout."""

    if workspace.path is None or FULL_SHA.fullmatch(pinned_sha) is None:
        raise RoundDriverError("private validation state is malformed")
    head = _git_at(plane, workspace.path, "rev-parse", "--verify", "HEAD")
    private_ref = _git(
        plane,
        "rev-parse",
        "--verify",
        f"{workspace.transaction_ref}^{{commit}}",
    )
    status = _git_at(
        plane,
        workspace.path,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if (
        head.returncode != 0
        or head.stdout.strip() != pinned_sha
        or private_ref.returncode != 0
        or private_ref.stdout.strip() != pinned_sha
        or status.returncode != 0
        or bool(status.stdout)
    ):
        raise RoundDriverError(
            "fixed validation changed the pinned transaction checkout or private ref"
        )
    for ancestor in (workspace.base_sha, *sealed_heads.values()):
        if (
            _git_at(
                plane,
                workspace.path,
                "merge-base",
                "--is-ancestor",
                ancestor,
                pinned_sha,
            ).returncode
            != 0
        ):
            raise RoundDriverError(
                "validated transaction no longer contains every sealed ancestor"
            )


def validate_round(
    plane: Any,
    round_: Round,
    report: RoundReport,
    *,
    owner: str,
    runner: Callable[[], tuple[bool, str]],
    lease_minutes: int = 60,
    validation_authority: Mapping[str, object] | None = None,
    keyed_validation_authority: Mapping[str, object] | None = None,
    renew_interval_seconds: float | None = None,
) -> Mapping[str, object]:
    """Run one leased gate, renewing its exact fence until the runner settles.

    Direct Python callers are controller-internal. Legacy hosted callers supply
    ``validation_authority``. A public publication transaction supplies
    ``keyed_validation_authority`` and consumes one host-global VALIDATION slot
    bound to its exact release and pinned transaction SHA. A renewal failure is
    fail-closed evidence; Python cannot forcibly cancel an arbitrary already-
    running external subprocess, so the runner is allowed to settle and the
    round is then rejected.
    """

    anchor = round_.nodes[0]
    if validation_authority is not None and keyed_validation_authority is not None:
        raise RoundValidationError(
            [RoundDriverError("validation authority classes are mutually exclusive")]
        )
    if keyed_validation_authority is not None:
        lease = plane.acquire_keyed_validation_lease_internal(
            anchor,
            owner,
            lease_minutes=lease_minutes,
            **dict(keyed_validation_authority),
        )
    elif validation_authority is None:
        lease = plane.acquire_global_validation_lease_internal(
            anchor,
            owner,
            lease_minutes=lease_minutes,
        )
    else:
        lease = plane.acquire_global_validation_lease(
            anchor,
            owner,
            lease_minutes=lease_minutes,
            **dict(validation_authority),
        )
    interval = (
        max(0.01, float(renew_interval_seconds))
        if renew_interval_seconds is not None
        else max(1.0, min(30.0, lease_minutes * 20.0))
    )
    stop_renewal = threading.Event()
    renewal_errors: list[BaseException] = []

    def renew_until_settled() -> None:
        while not stop_renewal.wait(interval):
            try:
                if keyed_validation_authority is not None:
                    plane.renew_keyed_validation_lease_internal(
                        anchor,
                        owner,
                        lease_id=str(lease["lease_id"]),
                        lease_minutes=lease_minutes,
                        **dict(keyed_validation_authority),
                    )
                elif validation_authority is None:
                    plane.renew_global_validation_lease_internal(
                        anchor,
                        owner,
                        lease_id=str(lease["lease_id"]),
                        lease_minutes=lease_minutes,
                    )
                else:
                    plane.renew_global_validation_lease(
                        anchor,
                        owner,
                        lease_id=str(lease["lease_id"]),
                        lease_minutes=lease_minutes,
                        **dict(validation_authority),
                    )
            except BaseException as error:  # retained until the runner settles
                renewal_errors.append(error)
                stop_renewal.set()
                return

    renewer = threading.Thread(
        target=renew_until_settled,
        name=f"validation-lease-renewer:{anchor}",
        daemon=True,
    )
    renewer.start()
    passed = False
    summary = "validation runner did not produce a verdict"
    failures: list[BaseException] = []
    cleanup: object = None
    try:
        try:
            passed, summary = runner()
        except BaseException as error:
            failures.append(error)
    finally:
        stop_renewal.set()
        renewer.join(timeout=max(1.0, interval + 1.0))
        if renewer.is_alive():
            failures.append(
                RoundDriverError("global validation lease renewer did not settle")
            )
        failures.extend(renewal_errors)
        # Cleanup is attempted even when the runner, renewal loop, or join failed. Exact
        # lease identity makes a late renewal harmless; retaining the cleanup error keeps
        # the durable caller from reporting a successful or cleanly rejected round.
        try:
            if keyed_validation_authority is not None:
                cleanup = plane.release_keyed_validation_lease_internal(
                    anchor,
                    owner,
                    lease_id=str(lease["lease_id"]),
                    **dict(keyed_validation_authority),
                )
            elif validation_authority is None:
                cleanup = plane.release_global_validation_lease_internal(
                    anchor,
                    owner,
                    lease_id=str(lease["lease_id"]),
                )
            else:
                cleanup = plane.release_global_validation_lease(
                    anchor,
                    owner,
                    lease_id=str(lease["lease_id"]),
                    **dict(validation_authority),
                )
        except BaseException as error:
            failures.append(error)
    if failures:
        raise RoundValidationError(failures)
    report.record("validate", anchor, "PASSED" if passed else "FAILED", summary)
    return {
        "lease": dict(lease),
        "cleanup": dict(cleanup) if isinstance(cleanup, Mapping) else cleanup,
        "gate": (
            dict(runner.validation_evidence)
            if isinstance(runner, FixedValidationRunner)
            and isinstance(runner.validation_evidence, Mapping)
            else None
        ),
    }


def default_validation_runner(
    repo_root: Path,
    *,
    expected_head: str | None = None,
    transaction_ref: str | None = None,
    require_clean: bool = False,
) -> FixedValidationRunner:
    """Run the repository-wide gate against THIS checkout's sources.

    An editable install elsewhere on the machine can otherwise win the import:
    observed here resolving ``hive_mind_os`` to an unrelated worktree, which
    would let the round's one authoritative gate pass or fail on source the
    round never touched.  Putting this repository's ``src`` at the front of
    ``PYTHONPATH`` makes the gate test what is actually being integrated.
    """

    return FixedValidationRunner(
        Path(repo_root),
        expected_head=expected_head,
        transaction_ref=transaction_ref,
        require_clean=require_clean,
    )


def classify_blocker(text: str) -> str:
    """Classify a blocker by what authority its repair would need."""

    lowered = text.lower()
    if any(marker in lowered for marker in _SEALED_MARKERS):
        return "CLASS_C"
    if any(marker in lowered for marker in _STALE_MARKERS):
        return "CLASS_B"
    return "CLASS_A"


def _last_blocker(plane: Any, node_id: str) -> str | None:
    path = Path(plane.blockers_dir) / f"{node_id}.jsonl"
    if not path.is_file():
        return None
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return lines[-1] if lines else None


def triage_round(
    plane: Any,
    nodes: Sequence[str],
    report: RoundReport,
    *,
    resolve_stale: bool = True,
) -> None:
    """Classify each node's blocker and resolve only the mechanical class."""

    for node_id in nodes:
        packet = _last_blocker(plane, node_id)
        if packet is None:
            continue
        if getattr(plane, "blockers_fully_resolved", lambda _node: False)(node_id):
            # Every recorded cause carries a verified resolution; the ledger's
            # last line is a resolution event, not a live blocker.
            continue
        verdict = classify_blocker(packet)
        if verdict == "CLASS_B" and resolve_stale:
            outcome, resolved = _resolve_stale_claim(plane, node_id)
            if resolved is not None:
                report.record("triage", node_id, outcome, resolved)
                continue
        report.record(
            "triage",
            node_id,
            verdict,
            {
                "CLASS_A": "runbook may contradict real source; verify and correct the "
                "runbook, then re-dispatch",
                "CLASS_B": "stale artifact blocks a lawful re-claim; retire it through "
                "the controller",
                "CLASS_C": "sealed or external authority; record and continue other rounds",
            }[verdict],
        )


def _resolve_stale_claim(plane: Any, node_id: str) -> tuple[str, str | None]:
    """Retire a dead worker's defunct claim ref, or explain why it must wait.

    Returns ``(outcome, detail)`` so a refusal is reported as RETAINED — a
    refusal used to be recorded as REPAIRED, which read as progress while the
    node stayed wedged.
    """

    policy = healing.load_policy(plane.ap_root)
    if not policy["enabled"]:
        return ("RETAINED", None)
    branch = str(plane.node(node_id).get("branch"))
    head = plane.remote_branch_sha(branch)
    if head is None:
        return ("RETAINED", None)
    _git(plane, "fetch", "origin", f"refs/heads/{branch}")
    record = plane.remote_claim_record(head)
    if not isinstance(record, Mapping):
        return ("RETAINED", None)
    try:
        released = plane.reap_defunct_remote_claim(
            node_id,
            actor="autopilot:round-driver",
            reason="round driver retired a dead worker's defunct claim",
            stall_minutes=int(policy["claim_stall_minutes"]),
        )
    except Exception as error:  # refusal is information, not a driver failure
        return ("RETAINED", f"claim retained: {error}")
    if released.get("outcome") == "absent":
        return ("RETAINED", None)
    proof = released.get("proof", {})
    return (
        "REPAIRED",
        f"retired defunct claim {str(head)[:7]} for {released.get('owner')} "
        f"({proof.get('kind', 'expired')})",
    )


def drive_round(
    plane: Any,
    *,
    actor: str,
    push: bool = True,
    round_authority: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Advance one public round through a short-snapshot/private transaction.

    The caller supplies only an exact release id. Controller truth is captured
    once under the host/repository/execution lock order; no status reread is
    allowed. Git integration and validation happen in a disposable worktree
    after a durable publication intent has been installed, and no authority
    lock is held across Git transport or the repository test gate.
    """

    if not actor.strip():
        raise RoundDriverError("round actor is required")
    if round_authority is None:
        raise RoundDriverError(
            "drive_round requires exact shared dispatcher authority; internal tests and "
            "controller-only recovery must call the private authorized routine explicitly"
        )
    release_id = round_authority.get("release_id")
    if not isinstance(release_id, str):
        raise RoundDriverError("public round authority requires an exact release id")
    with plane.round_admission_guard(release_id=release_id) as snapshot:
        if not isinstance(snapshot, Mapping):
            raise RoundDriverError("round admission guard returned malformed authority")
        # The compatibility context manager returns immediately after obtaining
        # this value; it deliberately holds no lock around the work below.
        captured = deepcopy(dict(snapshot))
    return _drive_public_round(
        plane,
        actor=actor,
        push=push,
        release_id=release_id,
        snapshot=captured,
    )


def _drive_public_round(
    plane: Any,
    *,
    actor: str,
    push: bool,
    release_id: str,
    snapshot: Mapping[str, object],
) -> dict[str, Any]:
    """Execute one exact released wave without touching an ambient checkout."""

    report = RoundReport()

    def finish(
        disposition: str,
        wake_at: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        result = report.to_dict()
        result["disposition"] = disposition
        result["wake_at"] = wake_at
        result.update(extra)
        return result

    try:
        release, status, inventories = _strict_round_authority_snapshot(
            plane,
            snapshot,
            release_id=release_id,
        )
    except RoundDriverError as error:
        report.record("authority", None, "RECOVERY_REQUIRED", str(error))
        return finish("RECOVERY_REQUIRED")

    obligations = inventories["reconciliation_obligations"]
    conflicts = inventories["conflicting_global_reservations"]
    if obligations or conflicts:
        report.record(
            "authority",
            None,
            "RECOVERY_REQUIRED",
            "round authority contains reconciliation obligations or cross-execution conflicts",
        )
        return finish(
            "RECOVERY_REQUIRED",
            reconciliation_obligations=[dict(item) for item in obligations],
            conflicting_global_reservations=[dict(item) for item in conflicts],
        )
    active = {
        key: [dict(item) for item in inventories[key]]
        for key in (
            "active_write_launch_reservations",
            "active_host_reservations",
            "execution_global_host_reservations",
            "active_claims",
        )
        if inventories[key]
    }
    validation_lease = snapshot.get("active_validation_lease")
    if isinstance(validation_lease, Mapping):
        active["active_validation_lease"] = [dict(validation_lease)]
    publication_fence = snapshot.get("publication_transaction_fence")
    if isinstance(publication_fence, Mapping):
        report.record(
            "authority",
            None,
            "RECOVERY_REQUIRED",
            "a prior publication transaction must be adopted or reconciled",
        )
        return finish(
            "RECOVERY_REQUIRED",
            publication_transaction=dict(publication_fence),
        )
    if active:
        wake_at: str | None = None
        for item in active.get("active_validation_lease", []):
            expiry = item.get("expires_at")
            if isinstance(expiry, str):
                wake_at = expiry
        report.record(
            "authority",
            None,
            "ACTIVE",
            "round integration waits for all primary, sidecar, claim, validation, "
            "and host reservations to become terminal",
        )
        return finish("ACTIVE", wake_at, authority=active)
    if status.get("reconciliation_required") is True:
        report.record(
            "authority",
            None,
            "RECOVERY_REQUIRED",
            "the sealed DAG snapshot requires a separate reconcile/snapshot/dispatch transition",
        )
        return finish("RECOVERY_REQUIRED")

    round_ = _round_from_release(release)
    if round_ is None:
        if status.get("complete") is not True:
            report.record(
                "authority",
                None,
                "ACTIVE",
                "the compiled frontier is empty but the controller is not terminal",
            )
            return finish("ACTIVE")
        report.record(
            "select",
            None,
            "CONTROLLER_QUIESCENT_CANDIDATE",
            "the DAG and captured controller authority are terminal; authenticated "
            "host lifecycle must still verify the fixed point",
        )
        return finish(
            "CONTROLLER_QUIESCENT_CANDIDATE",
            controller_authority_digest=str(snapshot["authority_digest"]),
        )

    report.round_id = round_.round_id
    report.nodes = round_.nodes
    report.record(
        "select",
        None,
        "SELECTED",
        f"{round_.round_id} level {round_.level}: {round_.reason}",
    )

    sealed_heads: dict[str, str] = {}
    for node_id in round_.nodes:
        head = receipt_head(
            plane,
            node_id,
            expected_target_sha=str(release["target_sha"]),
        )
        if head is None:
            report.record(
                "integrate",
                node_id,
                "PENDING",
                "no exact sealed receipt on the node branch",
            )
        else:
            sealed_heads[node_id] = head
    if len(sealed_heads) != len(round_.nodes):
        report.record(
            "validate",
            None,
            "SKIPPED",
            "the exact wave is not whole; recover separately and obtain a fresh release",
        )
        return finish("PENDING")

    triage_round(plane, round_.nodes, report, resolve_stale=False)
    if report.blocked:
        return finish("BLOCKED")

    authority_digest = str(snapshot["authority_digest"])
    transaction = plane.begin_publication_transaction(
        release_id=release_id,
        round_id=round_.round_id,
        expected_target_sha=str(release["target_sha"]),
        receipt_heads=sealed_heads,
        coordinator_id=actor,
        actor=actor,
        authority_digest=authority_digest,
    )
    if not isinstance(transaction, Mapping):
        raise RoundDriverError(
            "publication transaction admission returned malformed authority"
        )
    renewer = PublicationLeaseRenewer(
        plane,
        transaction,
        coordinator_id=actor,
    ).start()
    pinned_sha: str | None = None
    validation_error: RoundValidationError | None = None
    transaction_error: BaseException | None = None
    try:
        with PrivateRoundWorkspace(plane, transaction) as workspace:
            pinned_sha = integrate_private_round(
                plane,
                workspace,
                round_,
                report,
                sealed_heads=sealed_heads,
            )
            # Materialize the exact integration commit before running the gate. A crash
            # after this transition leaves PINNED evidence that another clone can
            # reconstruct, but PINNED alone never authorizes target publication.
            assert_private_validation_state(
                plane,
                workspace,
                pinned_sha=pinned_sha,
                sealed_heads=sealed_heads,
            )
            pinned_transaction = renewer.transition(
                lambda current: plane.pin_publication_transaction(
                    current,
                    pinned_sha=pinned_sha,
                    actor=actor,
                )
            )
            if (
                not isinstance(pinned_transaction, Mapping)
                or pinned_transaction.get("status") != "PINNED"
                or pinned_transaction.get("pinned_sha") != pinned_sha
            ):
                raise RoundDriverError(
                    "publication pin transition returned malformed authority"
                )
            # The public publication path never accepts validation evidence assembled
            # by this caller.  The plane-owned broker creates/adopts the durable
            # challenge, owns the keyed host-capacity lease, runs the fixed gate in its
            # separately attested sandbox, and persists the immutable completion.  On
            # platforms where that sandbox cannot prove network isolation the broker
            # fails closed and no VALIDATED transition is possible.
            try:
                completion = plane.run_publication_validation_broker(
                    pinned_transaction,
                    pinned_sha=pinned_sha,
                    actor=actor,
                )
                completion_id = (
                    completion.get("completion_id")
                    if isinstance(completion, Mapping)
                    else None
                )
                if not isinstance(completion_id, str) or not completion_id:
                    raise RoundDriverError(
                        "publication validation broker returned malformed evidence"
                    )
            except BaseException as error:
                validation_error = (
                    error
                    if isinstance(error, RoundValidationError)
                    else RoundValidationError([error])
                )
            if validation_error is None:
                assert_private_validation_state(
                    plane,
                    workspace,
                    pinned_sha=pinned_sha,
                    sealed_heads=sealed_heads,
                )
                validated_transaction = renewer.transition(
                    lambda current: plane.seal_validated_publication_transaction(
                        current,
                        pinned_sha=pinned_sha,
                        validation_evidence={"broker_completion_id": completion_id},
                        actor=actor,
                    )
                )
                if (
                    not isinstance(validated_transaction, Mapping)
                    or validated_transaction.get("status") != "VALIDATED"
                    or validated_transaction.get("pinned_sha") != pinned_sha
                ):
                    raise RoundDriverError(
                        "publication validation seal returned malformed authority"
                    )
                report.record(
                    "validate",
                    str(round_.nodes[0]),
                    "PASSED",
                    "controller-owned publication validation broker completed "
                    f"{completion_id}",
                )
    except BaseException as error:
        transaction_error = error

    try:
        current_transaction = renewer.settle()
    except BaseException as error:
        failures: list[BaseException] = [error]
        if transaction_error is not None:
            failures.insert(0, transaction_error)
        if validation_error is not None:
            failures.insert(0, validation_error)
        report.record(
            "publication",
            None,
            "RECOVERY_REQUIRED",
            "publication coordinator lease could not be settled exactly",
        )
        return finish(
            "RECOVERY_REQUIRED",
            failures=[f"{type(item).__name__}: {item}" for item in failures],
            transaction_id=transaction.get("transaction_id"),
        )

    if transaction_error is not None or validation_error is not None:
        failures = [
            item for item in (validation_error, transaction_error) if item is not None
        ]
        outcome = (
            "RECOVERY_REQUIRED"
            if len(failures) > 1
            else "VALIDATION_FAILED"
            if validation_error is not None
            else "INTEGRATION_CONFLICT"
            if report.blocked
            else "RECOVERY_REQUIRED"
        )
        detail = "; ".join(f"{type(item).__name__}: {item}" for item in failures)
        try:
            terminal = plane.finish_publication_transaction(
                current_transaction,
                pinned_sha=pinned_sha,
                outcome=outcome,
                actor=actor,
                detail=detail,
            )
        except BaseException as cleanup_error:
            report.record(
                "publication",
                None,
                "RECOVERY_REQUIRED",
                "adverse transaction and durable terminalization both failed",
            )
            return finish(
                "RECOVERY_REQUIRED",
                failures=[
                    *[f"{type(item).__name__}: {item}" for item in failures],
                    f"{type(cleanup_error).__name__}: {cleanup_error}",
                ],
                transaction_id=transaction.get("transaction_id"),
            )
        report.record("publication", None, outcome, detail)
        return finish(
            outcome,
            failures=[f"{type(item).__name__}: {item}" for item in failures],
            validation_failures=(
                [
                    {"type": type(item).__name__, "detail": str(item)}
                    for item in validation_error.failures
                ]
                if validation_error is not None
                else []
            ),
            publication_transaction=dict(terminal),
        )

    assert pinned_sha is not None
    passed = any(
        step.phase == "validate" and step.outcome == "PASSED" for step in report.steps
    )
    if not passed:
        terminal = plane.finish_publication_transaction(
            current_transaction,
            pinned_sha=pinned_sha,
            outcome="VALIDATION_FAILED",
            actor=actor,
            detail="fixed repository validation gate rejected the pinned transaction",
        )
        return finish("VALIDATION_FAILED", publication_transaction=dict(terminal))
    if not push:
        terminal = plane.finish_publication_transaction(
            current_transaction,
            pinned_sha=pinned_sha,
            outcome="NO_PUSH",
            actor=actor,
            detail="validated private transaction retained without target publication",
        )
        report.record(
            "publish",
            None,
            "NO_PUSH",
            f"retained validated private transaction {pinned_sha[:12]}",
        )
        return finish(
            "ROUND_VALIDATED_LOCAL",
            publication_transaction=dict(terminal),
        )

    try:
        published = plane.publish_pinned_transaction(
            current_transaction,
            pinned_sha=pinned_sha,
            actor=actor,
        )
        if not isinstance(published, Mapping) or published.get("outcome") not in {
            "PUBLISHED",
            "REJECTED",
            "PUBLISH_UNKNOWN",
        }:
            raise RoundDriverError("publication returned malformed terminal evidence")
    except BaseException as publication_error:
        try:
            terminal = plane.finish_publication_transaction(
                current_transaction,
                pinned_sha=pinned_sha,
                outcome="RECOVERY_REQUIRED",
                actor=actor,
                detail=(
                    "publication boundary raised before a typed outcome: "
                    f"{type(publication_error).__name__}: {publication_error}"
                ),
            )
        except BaseException as cleanup_error:
            report.record(
                "publish",
                None,
                "RECOVERY_REQUIRED",
                "publication outcome and durable reconciliation are both uncertain",
            )
            return finish(
                "RECOVERY_REQUIRED",
                failures=[
                    f"{type(publication_error).__name__}: {publication_error}",
                    f"{type(cleanup_error).__name__}: {cleanup_error}",
                ],
                transaction_id=transaction.get("transaction_id"),
            )
        report.record(
            "publish",
            None,
            "RECOVERY_REQUIRED",
            "publication boundary did not return a typed terminal outcome",
        )
        return finish(
            "RECOVERY_REQUIRED",
            failures=[f"{type(publication_error).__name__}: {publication_error}"],
            publication_transaction=dict(terminal),
        )
    outcome = published.get("outcome")
    if outcome == "PUBLISHED":
        report.record(
            "publish",
            None,
            "PUBLISHED",
            f"published pinned transaction {pinned_sha[:12]}",
        )
        return finish("ROUND_COMPLETE", publication_transaction=dict(published))
    if outcome == "REJECTED":
        report.record("publish", None, "FAILED", str(published.get("detail")))
        return finish("PUBLISH_REJECTED", publication_transaction=dict(published))
    report.record("publish", None, "PUBLISH_UNKNOWN", str(published.get("detail")))
    return finish("PUBLISH_UNKNOWN", publication_transaction=dict(published))
