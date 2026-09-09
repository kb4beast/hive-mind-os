"""Real operator-local tournament execution, independent of V4 release authority.

The local OS account owns the host key. Separate Codex sessions supply distinct
worker identities, not independently administered signing principals. No merge,
push, deployment, or automatic promotion is performed by this runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from .compiled_tournament import (
    CompiledNodeExecution,
    compile_node_execution,
)
from .dag_standard import compile_plan, load_bound_plan
from .local_codex_worker import CodexLocalWorker, resolve_codex_executable
from .local_run_authority import (
    LocalAuthorityError,
    LocalAuthorityStore,
    read_json,
    write_new_json,
)
from .path_boundary import ExternalPathRequired, is_within, require_external_path
from .runtime_contracts import canonical_json_bytes, raw_sha256


class LocalExecutionError(ValueError):
    """The local run cannot advance without violating its recorded contract."""


def _git(directory: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments], capture_output=True,
        encoding="utf-8", errors="replace", timeout=120, check=False,
    )
    if result.returncode:
        raise LocalExecutionError(f"git {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _clone(source: Path, destination: Path, commit: str) -> None:
    # Git creates pack files while cloning, before repository-local configuration
    # exists. Enable the Windows long-path setting on that first invocation.
    _git(source, "-c", "core.longpaths=true", "clone", "--no-local", "--no-hardlinks", "--no-checkout", str(source), str(destination))
    _git(destination, "config", "core.autocrlf", "false")
    _git(destination, "config", "core.longpaths", "true")
    _git(destination, "checkout", "--detach", commit)
    _git(destination, "remote", "remove", "origin")
    _git(destination, "config", "user.name", "Hive Mind local tournament")
    _git(destination, "config", "user.email", "local-tournament@localhost")
    _git(destination, "config", "core.hooksPath", str(destination / ".git" / "disabled-hooks"))
    if _git(destination, "status", "--porcelain"):
        raise LocalExecutionError("fresh clone is incomplete or differs from its pinned tree")


def _is_within(path: Path, directory: Path) -> bool:
    """Resolve containment through the filesystem, including Windows short paths."""
    try:
        current, boundary = path.resolve(), directory.resolve()
        while True:
            if os.path.samefile(current, boundary):
                return True
            if current == current.parent:
                return False
            current = current.parent
    except OSError:
        return False


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def host_digest() -> str:
    """Pin installed Python host bytes; candidate edits cannot upgrade the host."""
    root = Path(__file__).parent
    files: dict[str, Any] = {
        path.name: raw_sha256(path.read_bytes()) for path in sorted(root.glob("*.py"))
    }
    executable = resolve_codex_executable()
    files["codex_executable"] = {"path": str(executable), "digest": raw_sha256(executable.read_bytes())}
    return raw_sha256(canonical_json_bytes(files))


def _consumed_wall(events: list[dict[str, Any]], node_id: str) -> float:
    started = None
    total = 0.0
    for event in events:
        if event.get("node_id") != node_id:
            continue
        if event["kind"] in {"node_started", "host_patch_started"}:
            started = datetime.fromisoformat(event["recorded_at"])
        elif event["kind"] in {"node_completed", "node_failed"} and started is not None:
            total += max(0, (datetime.fromisoformat(event["recorded_at"]) - started).total_seconds())
            started = None
    return total


@contextmanager
def _exclusive_run(directory: Path):
    """Process-scoped lock releases on death; started intents remain durable."""
    with (directory / "controller.lock").open("a+b") as stream:
        stream.seek(0)
        if stream.read(1) == b"":
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise LocalExecutionError("another controller owns this local run") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class LocalTournamentService:
    """Bounded local tournament host with authenticated append-only receipts."""

    def __init__(self, worker: CodexLocalWorker | None = None, *, worker_mode: str = "evidence-packet") -> None:
        if worker_mode not in {"direct", "evidence-packet"}:
            raise LocalExecutionError("unknown local worker mode")
        self.worker = worker or CodexLocalWorker()
        self.worker_mode = worker_mode

    def execute(
        self, *, plan_path: Path, standard_path: Path, expected_plan_digest: str,
        repository: Path, state_directory: Path, host_directory: Path,
        operator_request_file: Path, brain_directory: Path,
        workers: int = 4, node_timeout: float = 900, resume: bool = False,
        refresh_local_host: bool = False,
        recover_recorded_patch: bool = False,
        expected_request_id: str | None = None, expected_subject_id: str | None = None,
    ) -> dict[str, Any]:
        repository, state, brain = repository.resolve(), state_directory.resolve(), brain_directory.resolve()
        plan_bytes, standard_bytes = plan_path.read_bytes(), standard_path.read_bytes()
        plan = load_bound_plan(plan_bytes, expected_plan_digest=expected_plan_digest, standard_bytes=standard_bytes,
            expected_request_id=expected_request_id, expected_subject_id=expected_subject_id)
        compilation = compile_plan(plan_bytes, expected_plan_digest=expected_plan_digest, standard_bytes=standard_bytes)
        policies = compile_node_execution(plan)
        pin = plan.subject.to_document()["repository"]
        if not pin or _git(repository, "rev-parse", "--show-toplevel").casefold() != str(repository).replace("\\", "/").casefold():
            raise LocalExecutionError("an explicit repository root is required")
        if _git(repository, "rev-parse", pin["commit"] + "^{tree}") != pin["tree"]:
            raise LocalExecutionError("repository commit/tree differs from the plan pin")
        if not 1 <= workers <= compilation.maximum_workers or not 30 <= node_timeout <= 3600:
            raise LocalExecutionError("invalid local worker count or node deadline")
        try:
            state = require_external_path(state, repository, label="run state")
            brain = require_external_path(brain, repository, label="brain")
        except ExternalPathRequired as error:
            raise LocalExecutionError(str(error)) from error
        if brain.is_relative_to(state) or state.is_relative_to(brain):
            raise LocalExecutionError("brain and private run state must be separate directories")
        custody = host_directory.resolve()
        if is_within(custody, repository) or is_within(custody, state) or is_within(custody, brain):
            raise LocalExecutionError("host key custody must be outside the subject, run state, and brain")
        directive = operator_request_file.read_bytes()
        request_bytes = (plan_path.parent / "request.txt").read_bytes()
        if raw_sha256(request_bytes) != plan.objective_digest:
            raise LocalExecutionError("original objective bytes are absent or differ from plan")
        if (refresh_local_host or recover_recorded_patch) and (not resume or self.worker_mode != "evidence-packet"):
            raise LocalExecutionError("host refresh requires an explicit packet-mode resume")
        if refresh_local_host and recover_recorded_patch:
            raise LocalExecutionError("model retry and recorded-patch recovery are separate operations")
        authority = LocalAuthorityStore(host_directory, create=not resume)
        frozen_host = host_digest()
        if not resume:
            state.mkdir(parents=True, exist_ok=False)
        elif not state.is_dir():
            raise LocalExecutionError("resume requires existing local run state")
        with _exclusive_run(state):
            if not resume:
                brain.mkdir(parents=True, exist_ok=False)
                for name in ("events", "workers", "workspaces"):
                    (state / name).mkdir()
                grant = authority.issue(
                    plan_digest=expected_plan_digest, repository=repository,
                    commit=pin["commit"], tree=pin["tree"], state_directory=state,
                    operator_request=directive, host_digest=frozen_host,
                )
                write_new_json(state / "grant.json", grant)
                (state / "plan.json").write_bytes(plan_bytes)
                (state / "standard.md").write_bytes(standard_bytes)
                (state / "operator-request.txt").write_bytes(directive)
                (state / "objective.txt").write_bytes(request_bytes)
                write_new_json(state / "configuration.json", authority.seal({
                    "brain_directory": str(brain), "workers": workers, "node_timeout": node_timeout,
                    "worker_mode": self.worker_mode,
                }))
                _clone(repository, state / "candidate", pin["commit"])
            events = self._events(state, authority)
            grant_file = "grant.json"
            for event in events:
                if event["kind"] == "host_updated":
                    name = event["grant_file"]
                    if Path(name).name != name or not name.startswith("grant-") or not name.endswith(".json"):
                        raise LocalAuthorityError("invalid refreshed grant path")
                    if raw_sha256((state / grant_file).read_bytes()) != event["previous_grant_digest"]:
                        raise LocalAuthorityError("host admission history differs from prior grant")
                    if raw_sha256((state / name).read_bytes()) != event["grant_digest"]:
                        raise LocalAuthorityError("refreshed grant bytes changed")
                    grant_file = name
            grant = read_json(state / grant_file)
            prior_host = authority.unseal(grant)["host_digest"]
            document = authority.verify(
                grant, plan_digest=expected_plan_digest, repository=repository, state_directory=state,
                host_digest=prior_host if refresh_local_host or recover_recorded_patch else frozen_host, operator_request=directive,
            )
            if document["commit"] != pin["commit"] or document["tree"] != pin["tree"]:
                raise LocalAuthorityError("signed repository pin differs from plan")
            configuration = authority.unseal(read_json(state / "configuration.json"))
            if configuration != {"brain_directory": str(brain), "workers": workers, "node_timeout": node_timeout, "worker_mode": self.worker_mode}:
                raise LocalAuthorityError("resume configuration differs from authenticated run")
            if (state / "plan.json").read_bytes() != plan_bytes or (state / "standard.md").read_bytes() != standard_bytes:
                raise LocalAuthorityError("stored plan inputs were changed")
            if (state / "objective.txt").read_bytes() != request_bytes or (state / "operator-request.txt").read_bytes() != directive:
                raise LocalAuthorityError("stored operator or objective bytes were changed")
            completed = {event["node_id"]: event for event in events if event["kind"] == "node_completed"}
            latest = {event["node_id"]: event for event in events if event["kind"] in {"node_started", "host_patch_started", "node_completed", "node_failed"}}
            if any(event["kind"] in {"node_started", "host_patch_started"} for event in latest.values()):
                raise LocalExecutionError("RECOVERY_REQUIRED: interrupted worker may have effects; inspect its process and workspace before a new run")
            failed = [event for event in latest.values() if event["kind"] == "node_failed"]
            current_commit = next((event["candidate_after"] for event in reversed(events) if event["kind"] == "node_completed"), pin["commit"])
            if _git(state / "candidate", "rev-parse", "HEAD") != current_commit or _git(state / "candidate", "status", "--porcelain"):
                raise LocalExecutionError("candidate drifted from its last authenticated receipt")
            if failed and not (refresh_local_host or recover_recorded_patch):
                return self._publish(state, brain, plan, events, "BLOCKED")
            if recover_recorded_patch:
                self._validate_patch_recovery(state, failed, events, completed, policies)
                recovered_policy = policies[failed[0]["node_id"]]
                node = next(node for node in plan.nodes if node.node_id == recovered_policy.node_id)
                budget = next(item.policy for item in plan.budgets if item.budget_id == node.budget_id)
                prior = [worker for event in events if event.get("node_id") == node.node_id for worker in event.get("workers", [])]
                for key, limit in (("input_tokens", budget.input_tokens), ("output_tokens", budget.output_tokens)):
                    if sum((receipt.get("usage") or {}).get(key, 0) or 0 for receipt in prior) > limit:
                        raise LocalExecutionError(f"worker exceeded cumulative measured {key} allocation")
                if len(prior) > budget.model_calls:
                    raise LocalExecutionError("cumulative model session budget exceeded")
                session = failed[0]["workers"][0]["session_id"]
                if any(receipt.get("session_id") == session for event in events if event.get("node_id") != node.node_id for receipt in event.get("workers", [])):
                    raise LocalExecutionError("worker session was reused across independent identities")
            if refresh_local_host:
                if not failed:
                    raise LocalExecutionError("host refresh requires a terminal read-only blocker")
                for event in failed:
                    if policies[event["node_id"]].writable or event.get("reason") or not event.get("workers"):
                        raise LocalExecutionError("host refresh cannot retry uncertain or writing effects")
                    if sum(item.get("node_id") == event["node_id"] and item["kind"] == "node_started" for item in events) >= plan.recovery.maximum_attempts:
                        raise LocalExecutionError("node retry budget is exhausted")
                    for receipt in event["workers"]:
                        workspace = Path(receipt["workspace"]).resolve()
                        if (receipt.get("exit_code") != 0 or not receipt.get("session_id")
                                or receipt.get("sandbox") != "read-only"
                                or not _is_within(workspace, state / "workspaces")
                                or _git(workspace, "rev-parse", "HEAD") != event["candidate_before"]
                                or _git(workspace, "status", "--porcelain")):
                            raise LocalExecutionError("read-only retry lacks terminal, unchanged workspace evidence")
            if refresh_local_host or recover_recorded_patch:
                refresh_time = datetime.now(UTC)
                remaining_grant = int((datetime.fromisoformat(document["expires_at"]) - refresh_time).total_seconds())
                previous_grant_digest = raw_sha256((state / grant_file).read_bytes())
                grant = authority.issue(plan_digest=expected_plan_digest, repository=repository,
                    commit=pin["commit"], tree=pin["tree"], state_directory=state,
                    operator_request=directive, host_digest=frozen_host, duration_seconds=remaining_grant, now=refresh_time)
                grant_file = f"grant-{len(events) + 1:04}.json"
                write_new_json(state / grant_file, grant)
                document = authority.verify(grant, plan_digest=expected_plan_digest, repository=repository,
                    state_directory=state, host_digest=frozen_host, operator_request=directive)
                self._append(state, authority, events, {"kind": "host_updated", "grant_file": grant_file,
                    "grant_digest": raw_sha256((state / grant_file).read_bytes()),
                    "previous_grant_digest": previous_grant_digest, "previous_host_digest": prior_host,
                    "host_digest": frozen_host,
                    "retry_nodes": [] if recover_recorded_patch else [event["node_id"] for event in failed],
                    "recover_patch_from_sequence": failed[0]["sequence"] if recover_recorded_patch else None,
                    "reason": "Explicit operator-local host continuation; original evidence retained; expiry not extended; recorded-patch recovery never replays the model."})
            deadline = datetime.fromisoformat(document["expires_at"])
            if recover_recorded_patch:
                recovered_policy = policies[failed[0]["node_id"]]
                node = next(node for node in plan.nodes if node.node_id == recovered_policy.node_id)
                budget = next(item.policy for item in plan.budgets if item.budget_id == node.budget_id)
                timeout = min(node_timeout, budget.wall_seconds) - _consumed_wall(events, node.node_id)
                if timeout <= 0:
                    raise LocalExecutionError("cumulative node wall budget is exhausted")
                recovery = self._recover_patch(state, authority, events, failed[0], current_commit,
                    recovered_policy,
                    timeout=min(timeout, (deadline - datetime.now(UTC)).total_seconds()),
                    verify_host=lambda: authority.verify(grant, plan_digest=expected_plan_digest,
                        repository=repository, state_directory=state, host_digest=host_digest(), operator_request=directive))
                if recovery["kind"] != "node_completed":
                    return self._publish(state, brain, plan, events, "BLOCKED")
                completed[node.node_id] = recovery
                current_commit = recovery["candidate_after"]
            run_binding = {
                "plan_digest": expected_plan_digest, "subject": plan.subject.to_document(),
                "integration": plan.to_document()["integration"],
                "original_request": {"text": request_bytes.decode("utf-8"), "sha256": raw_sha256(request_bytes), "path": str(state / "objective.txt")},
                "operator_request_digest": raw_sha256(directive),
                "local_grant_verified_by_host": document, "brain_directory": str(brain),
                "publication": "host-created new brain directory; status/index projected from authenticated event history",
            }
            nodes = {node.node_id: node.to_document() for node in plan.nodes}
            sessions = {worker["session_id"] for event in events for worker in event.get("workers", []) if worker.get("session_id")}
            budgets = {item.budget_id: item.policy for item in plan.budgets}
            for round_ in compilation.rounds:
                pending = [node_id for node_id in round_.node_ids if node_id not in completed]
                if not pending:
                    continue
                authority.verify(grant, plan_digest=expected_plan_digest, repository=repository, state_directory=state, host_digest=host_digest(), operator_request=directive)
                attempts = {node_id: 1 + sum(event.get("node_id") == node_id and event["kind"] == "node_started" for event in events) for node_id in pending}
                timeouts = {node_id: min(node_timeout, budgets[nodes[node_id]["budget_id"]].wall_seconds) - _consumed_wall(events, node_id) for node_id in pending}
                if any(value <= 0 for value in timeouts.values()):
                    raise LocalExecutionError("cumulative node wall budget is exhausted")
                for node_id in pending:
                    if any(parent not in completed for parent in nodes[node_id]["dependencies"]):
                        raise LocalExecutionError("dependency lacks a completed authenticated receipt")
                    self._append(state, authority, events, {"kind": "node_started", "node_id": node_id, "attempt": attempts[node_id], "candidate_before": current_commit})
                context = [{"node_id": node_id, "workers": event["workers"]} for node_id, event in completed.items()]
                # One writer is admitted only in its compiler-serialized round.
                if any(policies[node_id].exclusive_writer for node_id in pending) and len(pending) != 1:
                    raise LocalExecutionError("candidate writer must occupy an exclusive round")
                self._publish(state, brain, plan, events, "RUNNING")
                failures = False
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    tasks = {pool.submit(
                        self._node, node=nodes[node_id], state=state, commit=current_commit,
                        policy=policies[node_id], policies=policies,
                        context=context, directive=request_bytes.decode("utf-8") + "\nFollow-up authority:\n" + directive.decode("utf-8"),
                        timeout=timeouts[node_id],
                        deadline=deadline,
                        run_binding=run_binding,
                        attempt=attempts[node_id],
                    ): node_id for node_id in pending}
                    for task in as_completed(tasks):
                        node_id = tasks[task]
                        receipts = []
                        try:
                            receipts = task.result()
                            authority.verify(grant, plan_digest=expected_plan_digest, repository=repository, state_directory=state, host_digest=host_digest(), operator_request=directive)
                            good = all(receipt["status"] == "completed" and receipt.get("session_id") for receipt in receipts)
                            budget = budgets[nodes[node_id]["budget_id"]]
                            prior_receipts = [worker for event in events if event.get("node_id") == node_id for worker in event.get("workers", [])]
                            for key, limit in (("input_tokens", budget.input_tokens), ("output_tokens", budget.output_tokens)):
                                measured = [(receipt.get("usage") or {}).get(key) for receipt in prior_receipts + receipts]
                                if sum(value for value in measured if isinstance(value, int)) > limit:
                                    raise LocalExecutionError(f"worker exceeded cumulative measured {key} allocation")
                            if len(prior_receipts) + len(receipts) > budget.model_calls:
                                raise LocalExecutionError("cumulative model session budget exceeded")
                            new_sessions = [receipt["session_id"] for receipt in receipts if receipt.get("session_id")]
                            if len(new_sessions) != len(set(new_sessions)) or sessions.intersection(new_sessions):
                                raise LocalExecutionError("worker session was reused across independent identities")
                            sessions.update(new_sessions)
                            after = current_commit
                            if good and policies[node_id].writable:
                                court_node = self._predecessor_by_stage(
                                    node_id, nodes, completed, policies, "court-selection"
                                )
                                court = completed[court_node]["workers"][0]["report"]
                                if not court["selected_idea_ids"] and _git(state / "candidate", "status", "--porcelain"):
                                    raise LocalExecutionError("builder changed files without a selected experiment")
                                if _git(state / "candidate", "rev-parse", "HEAD") != current_commit:
                                    raise LocalExecutionError("builder changed repository metadata or committed outside host")
                                after = self._commit_candidate(state / "candidate", receipts[0])
                            event = {"kind": "node_completed" if good else "node_failed", "node_id": node_id,
                                     "workers": receipts, "candidate_before": current_commit, "candidate_after": after}
                        except Exception as error:
                            if not receipts:
                                execution_id = node_id if attempts[node_id] == 1 else f"{node_id}-attempt-{attempts[node_id]:02}"
                                for identity in (execution_id, execution_id + "-WITNESS"):
                                    path = state / "workers" / identity / "receipt.json"
                                    if path.is_file():
                                        receipts.append(read_json(path))
                            event = {"kind": "node_failed", "node_id": node_id, "workers": receipts, "reason": f"{type(error).__name__}: {error}"}
                        self._append(state, authority, events, event)
                        if event["kind"] == "node_completed":
                            completed[node_id] = events[-1]
                            current_commit = event["candidate_after"]
                        else:
                            failures = True
                        self._publish(state, brain, plan, events, "BLOCKED" if failures else "RUNNING")
                if failures:
                    return self._publish(state, brain, plan, events, "BLOCKED")
            return self._publish(state, brain, plan, events, "COMPLETED")

    @staticmethod
    def _predecessor_by_stage(
        node_id: str, nodes: dict[str, dict[str, Any]], completed: dict[str, Any],
        policies: dict[str, CompiledNodeExecution], stage_kind: str,
    ) -> str:
        pending = list(nodes[node_id]["dependencies"])
        seen: set[str] = set()
        while pending:
            candidate = pending.pop(0)
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate in completed and policies[candidate].stage_kind == stage_kind:
                return candidate
            pending.extend(nodes[candidate]["dependencies"])
        raise LocalExecutionError(
            f"{node_id} requires a completed {stage_kind} predecessor"
        )

    @staticmethod
    def _validate_patch_recovery(
        state: Path, failed: list[dict[str, Any]], events: list[dict[str, Any]],
        completed: dict[str, Any], policies: dict[str, CompiledNodeExecution],
    ) -> None:
        """Admit one deterministic continuation of an unexecuted model patch."""
        if len(failed) != 1 or not policies[failed[0]["node_id"]].writable:
            raise LocalExecutionError("recorded-patch recovery requires a terminal Builder parse failure")
        event = failed[0]
        if (not str(event.get("reason", "")).startswith("LocalEvidenceError: git apply failed: error: corrupt patch")
                or len(event.get("workers", [])) != 1
                or any(item["kind"] == "host_patch_started" for item in events)):
            raise LocalExecutionError("recorded-patch recovery cannot repeat applied or uncertain effects")
        receipt = event["workers"][0]
        report = receipt["report"]
        if (receipt.get("status") != "completed" or receipt.get("exit_code") != 0
                or receipt.get("execution_mode") != "source-packet" or receipt.get("sandbox") != "read-only"
                or not receipt.get("session_id") or not _same_path(Path(receipt["workspace"]), state / "candidate")
                or report.get("status") != "completed" or not report.get("proposed_patch")
                or receipt.get("host_patch") or receipt.get("host_checks")):
            raise LocalExecutionError("recorded patch lacks terminal model-only evidence before host effects")
        # The writer receipt retains the court selection in its model report.
        court_events = [item for item in completed.values()
                        if policies[item["node_id"]].stage_kind == "court-selection"]
        if not court_events:
            raise LocalExecutionError("recorded patch has no completed selection court")
        court = court_events[-1]["workers"][0]["report"]
        allowed = {idea["idea_id"] for idea in court["ideas"] if idea["disposition"] in {"adopt", "adapt"}} & set(court["selected_idea_ids"])
        selected = set(report["selected_idea_ids"])
        if not selected or not selected.issubset(allowed):
            raise LocalExecutionError("recorded patch lacks a selected local court experiment")

    def _recover_patch(self, state: Path, authority: LocalAuthorityStore, events: list[dict[str, Any]],
                       failed: dict[str, Any], commit: str, policy: CompiledNodeExecution,
                       *, timeout: float, verify_host: Any) -> dict[str, Any]:
        from .local_evidence_packet import apply_proposed_patch, run_focused_checks

        # Copy the signed receipt; its original report and evidence bytes stay intact.
        receipt = json.loads(json.dumps(failed["workers"][0]))
        node_id = policy.node_id
        verify_host()
        self._append(state, authority, events, {"kind": "host_patch_started", "node_id": node_id,
            "candidate_before": commit, "recovered_from_sequence": failed["sequence"],
            "patch_digest": raw_sha256(receipt["report"]["proposed_patch"].encode("utf-8")),
            "model_replayed": False})
        started = time.monotonic()
        try:
            report = receipt["report"]
            receipt["host_patch"] = apply_proposed_patch(state / "candidate", report["proposed_patch"], report["changed_paths"])
            receipt["host_checks"] = run_focused_checks(state / "candidate", report["changed_paths"],
                state / "workers" / f"{node_id}-RECOVERED-HOST-CHECKS", timeout - (time.monotonic() - started))
            verify_host()
            if time.monotonic() - started > timeout:
                raise LocalExecutionError("recorded-patch recovery exceeded remaining node time")
            after = self._commit_candidate(state / "candidate", receipt)
            result = {"kind": "node_completed", "node_id": node_id, "workers": [receipt],
                "candidate_before": commit, "candidate_after": after,
                "recovered_from_sequence": failed["sequence"], "model_replayed": False}
        except Exception as error:
            result = {"kind": "node_failed", "node_id": node_id, "workers": [receipt],
                "recovered_from_sequence": failed["sequence"], "model_replayed": False,
                "reason": f"{type(error).__name__}: {error}"}
        self._append(state, authority, events, result)
        return events[-1]

    @staticmethod
    def _events(state: Path, authority: LocalAuthorityStore) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for index, path in enumerate(sorted((state / "events").glob("*.json")), 1):
            event = authority.unseal(read_json(path))
            previous = raw_sha256(canonical_json_bytes(events[-1])) if events else None
            if event.get("sequence") != index or event.get("previous_digest") != previous:
                raise LocalAuthorityError("event history is incomplete or reordered")
            for receipt in event.get("workers", []):
                for evidence in receipt["evidence"].values():
                    if evidence["sha256"]:
                        evidence_path = Path(evidence["path"]).resolve()
                        if not _is_within(evidence_path, state / "workers") or hashlib.sha256(evidence_path.read_bytes()).hexdigest() != evidence["sha256"]:
                            raise LocalAuthorityError("worker evidence changed or escaped run custody")
                for check in receipt.get("host_checks", {}).get("checks", []):
                    for stream in ("stdout", "stderr"):
                        path = Path(check[f"{stream}_path"]).resolve()
                        if not _is_within(path, state / "workers") or hashlib.sha256(path.read_bytes()).hexdigest() != check[f"{stream}_sha256"]:
                            raise LocalAuthorityError("deterministic test evidence changed or escaped run custody")
            events.append(event)
        head = (len(events), raw_sha256(canonical_json_bytes(events[-1])) if events else None)
        if authority.event_head(state) != head:
            raise LocalAuthorityError("event tail differs from independently stored custody checkpoint")
        return events

    @staticmethod
    def _append(state: Path, authority: LocalAuthorityStore, events: list[dict[str, Any]], event: dict[str, Any]) -> None:
        document = {**event, "sequence": len(events) + 1, "recorded_at": datetime.now(UTC).isoformat(),
                    "previous_digest": raw_sha256(canonical_json_bytes(events[-1])) if events else None}
        write_new_json(state / "events" / f"{len(events) + 1:04}.json", authority.seal(document))
        authority.advance_event_head(state, sequence=document["sequence"], digest=raw_sha256(canonical_json_bytes(document)), previous_digest=document["previous_digest"])
        events.append(document)

    def _node(
        self, *, node: dict[str, Any], policy: CompiledNodeExecution,
        policies: dict[str, CompiledNodeExecution], state: Path, commit: str,
        context: list[dict[str, Any]], directive: str, timeout: float,
        deadline: datetime, run_binding: dict[str, Any] | None = None,
        attempt: int = 1,
    ) -> list[dict[str, Any]]:
        node_deadline = time.monotonic() + timeout

        def remaining() -> float:
            value = min(node_deadline - time.monotonic(), (deadline - datetime.now(UTC)).total_seconds())
            if value <= 0:
                raise LocalAuthorityError("local grant or node execution deadline expired")
            return value

        node_id = node["node_id"]
        execution_id = node_id if attempt == 1 else f"{node_id}-attempt-{attempt:02}"
        writable = policy.writable
        workspace = state / "candidate" if writable else state / "workspaces" / execution_id
        if not writable:
            _clone(state / "candidate", workspace, commit)
        # Pass reports, not transcript bytes, keeping raw command evidence independently available.
        reports = [{"node_id": item["node_id"], "workers": [
            {key: receipt[key] for key in ("actor_id", "role", "session_id", "report", "evidence", "host_checks", "host_patch") if key in receipt}
            for receipt in item["workers"]]} for item in context]
        if policy.stage_kind == "cross-examination":
            # The canonical proposal retains every idea and its provenance.
            # Other full transcripts remain available in authenticated run state.
            reports = [item for item in reports if policies[item["node_id"]].stage_kind == "proposal"]
        elif policy.stage_kind == "integration":
            # The court and final judge retain all canonical ideas. The actual
            # brain snapshot below supplies their complete published histories.
            reports = [item for item in reports if policies[item["node_id"]].stage_kind in {"court-selection", "court-result"}]
        objective = directive + "\nLocal execution context: " + json.dumps({
            "base_commit": commit, "state_directory": str(state), "workspace": str(workspace),
            "execution_scope": "isolated reversible local work; no promotion or superiority assertion",
            "brain_projection": "Host automatically publishes each real report and all idea iterations as Markdown after completion.",
        })
        objective += "\nKeep the experiment focused: champion at most three concrete ideas and select at most one small implementable improvement. Preserve ALL existing idea IDs and record a reason for every defer/reject/return. A node can complete successfully with a reasoned defer verdict. Do not demand implementation evidence at proposal stage. Do not claim a full suite passed unless you ran it; focused acceptance tests are appropriate during this bounded experiment. Verification must actually execute the selected regression tests through a sealed adapter. A revision stage responds to challenges without changing an idea's hypothesis unless a concrete defect requires it. A court-selection stage includes every proposed idea and cites cross-examination plus witness evidence. A build stage implements only ideas selected adopt/adapt by that court; if none, it records a no-change result. Include required ADR/evidence for kernel or policy changes."
        extra: dict[str, Any] = {}
        host_checks = None
        inventory_evidence = None
        if self.worker_mode == "evidence-packet":
            from .local_evidence_packet import (
                build_source_packet,
                inspect_brain_publication,
                run_focused_checks,
            )
            selection_context = reports
            if policy.stage_kind in {"build", "verification"}:
                court_report = next(item for item in reports if policies[item["node_id"]].stage_kind == "court-selection")["workers"][0]["report"]
                selection_context = [{"ideas": [idea for idea in court_report["ideas"] if idea["idea_id"] in court_report["selected_idea_ids"]]}]
            packet = build_source_packet(workspace, node_id, selection_context, max_content_bytes=60_000 if policy.stage_kind in {"cross-examination", "integration"} else 140_000)
            if run_binding is None:
                raise LocalAuthorityError("worker packet requires verified run bindings")
            packet["run_binding"] = {
                **run_binding,
                "candidate_commit": commit, "candidate_tree": _git(workspace, "rev-parse", "HEAD^{tree}"),
            }
            inventory = {key: packet.pop(key) for key in ("inventory", "omitted_files")}
            packet.pop("predecessor_reports", None)
            inventory_path = state / "workers" / f"{execution_id}-source-inventory.json"
            write_new_json(inventory_path, inventory)
            inventory_evidence = {"path": str(inventory_path), "sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest()}
            packet["source_inventory_receipt"] = {**inventory_evidence, "tracked_files": len(inventory["inventory"]), "omitted_files": len(inventory["omitted_files"])}
            if policy.stage_kind == "integration":
                packet["brain_publication"] = inspect_brain_publication(Path(run_binding["brain_directory"]))
                base = run_binding["subject"]["repository"]["commit"]
                diff = _git(workspace, "diff", "--no-ext-diff", "--no-textconv", base, commit, "--")
                verifier = next(item for item in context if policies[item["node_id"]].stage_kind == "verification")["workers"][0]
                packet["delivery_manifest"] = {
                    "artifact": "isolated local candidate", "candidate_directory": str(state / "candidate"),
                    "base_commit": base, "candidate_commit": commit,
                    "candidate_tree": packet["run_binding"]["candidate_tree"],
                    "diff_text": diff, "diff_text_sha256": raw_sha256(diff.encode("utf-8")),
                    "verifier_actor_id": verifier["actor_id"], "verifier_session_id": verifier["session_id"],
                    "verification": verifier.get("host_checks"),
                    "promotion_authorized": False, "protected_merge_authorized": False,
                    "rollback": "Retain all receipts and the source pin; supersede or revert this isolated candidate commit. No protected reference is changed by delivery preparation.",
                }
                objective += "\nThe brain_publication packet records actual files already written by the host, including the index, whole idea histories, hashes, and local link checks. Evaluate that existing publication and the final court verdict. Your current report will be appended by the host after you return; do not claim that future write already occurred. Completion can attest the inspected publication and your reversible delivery recommendation without requiring your own not-yet-returned report to be present. All failed attempts remain in the snapshot."
            if policy.stage_kind == "verification":
                builder = next(item for item in reports if policies[item["node_id"]].stage_kind == "build")
                changed_paths = builder["workers"][0]["report"]["changed_paths"]
                host_checks = run_focused_checks(workspace, changed_paths, state / "workers" / f"{execution_id}-HOST-CHECKS", remaining())
                packet["independent_host_checks"] = host_checks
            elif policy.stage_kind == "runtime-audit":
                inspected_tests = [item["path"] for item in packet["selected_files"] if Path(item["path"]).name.startswith("test_") and item["path"].endswith(".py")]
                host_checks = run_focused_checks(workspace, inspected_tests, state / "workers" / f"{execution_id}-HOST-CHECKS", remaining())
                packet["independent_host_checks"] = host_checks
            extra["source_packet"] = packet
            objective += "\nEVIDENCE-PACKET MODE: native child tool execution is unavailable. The host has already read immutable Git blobs and supplies their exact content/digests. Do not call tools or request policy changes. Perform your role on that supplied evidence and clearly name omitted-source obligations. Independent tests, when supplied, were actually run by the host in this separate verifier clone. You evaluate their evidence; do not claim you personally ran commands. Builder: return one plain unified diff in proposed_patch, with exact changed_paths, for the selected focused idea including its regression test. The host validates and applies it only in the isolated candidate and runs fixed tests. Other roles: proposed_patch=null and changed_paths=[]. A reasoned disposition can complete the node even when it retains limitations; unavailable implementation facts stay explicit."
        witness = None
        if policy.stage_kind == "cross-examination":
            witness_node = {**node, "node_id": f"{node_id}-WITNESS",
                "objective": "Provide independent expert testimony on each proposed idea before cross-examination.",
                "acceptance_criteria": ["Independently assess each proposal using supplied source evidence, identify counterexamples and limits, and retain its idea identity. Do not claim to be its cross-examiner or judge."]}
            witness = self.worker.run(
                node=witness_node, actor_id=f"local:{state.name}:{execution_id}-WITNESS", role="expert-witness",
                workspace=workspace, evidence_directory=state / "workers" / (execution_id + "-WITNESS"),
                predecessor_reports=reports, objective=objective + "\nYou are the independent expert witness. Your testimony precedes the separate examiner. Evaluate supported hypotheses and state remaining obligations proportionately; no prior examiner testimony is required.",
                timeout_seconds=remaining(), writable=False, **extra)
            if witness["status"] != "completed":
                return [witness]
            reports = reports + [{"node_id": witness_node["node_id"], "workers": [{key: witness[key] for key in ("actor_id", "role", "session_id", "report", "evidence")}]}]
        timeout = remaining()
        receipt = self.worker.run(
            node=node, actor_id=f"local:{state.name}:{execution_id}", role=policy.role,
            workspace=workspace, evidence_directory=state / "workers" / execution_id,
            predecessor_reports=reports, objective=objective, timeout_seconds=timeout, writable=writable,
            **extra,
        )
        if receipt.get("status") == "completed":
            report = receipt.get("report")
            if not isinstance(report, dict) or any(name not in report for name in policy.required_outputs):
                raise LocalExecutionError("worker omitted a plan-required output")
        if receipt["status"] == "completed" and policy.stage_kind in {"court-selection", "court-result"}:
            proposal = next(item for item in reports if policies[item["node_id"]].stage_kind == "proposal")["workers"][0]["report"]
            proposed = {idea["idea_id"] for idea in proposal["ideas"]}
            decided = {idea["idea_id"] for idea in receipt["report"]["ideas"]}
            admitted = {idea["idea_id"] for idea in receipt["report"]["ideas"] if idea["disposition"] in {"adopt", "adapt"}}
            if not proposed.issubset(decided) or not set(receipt["report"]["selected_idea_ids"]).issubset(admitted):
                raise LocalExecutionError("court omitted a proposed idea or selected an idea without an adopt/adapt disposition")
        if host_checks is not None:
            receipt["host_checks"] = host_checks
            if policy.stage_kind == "verification" and not host_checks.get("all_passed", False):
                receipt["status"] = "failed"
                receipt["reason"] = "independent sealed verification did not pass"
        if inventory_evidence is not None:
            receipt["evidence"]["source_inventory"] = inventory_evidence
        if writable and self.worker_mode == "evidence-packet" and receipt["status"] == "completed":
            from .local_evidence_packet import apply_proposed_patch, run_focused_checks
            patch = receipt["report"]["proposed_patch"]
            changed_paths = receipt["report"]["changed_paths"]
            if patch:
                court = next(item for item in reports if policies[item["node_id"]].stage_kind == "court-selection")["workers"][0]["report"]
                allowed = {idea["idea_id"] for idea in court["ideas"] if idea["disposition"] in {"adopt", "adapt"}} & set(court["selected_idea_ids"])
                selected = set(receipt["report"]["selected_idea_ids"])
                if not selected or not selected.issubset(allowed):
                    raise LocalExecutionError("builder patch lacks a selected local court experiment")
                remaining()
                receipt["host_patch"] = apply_proposed_patch(workspace, patch, changed_paths)
                receipt["host_checks"] = run_focused_checks(workspace, changed_paths, state / "workers" / f"{node_id}-HOST-CHECKS", remaining())
                if not receipt["host_checks"].get("all_passed", False):
                    receipt["status"] = "failed"
                    receipt["reason"] = "post-patch sealed verification did not pass"
            elif changed_paths:
                raise LocalExecutionError("builder reported changes without a proposed patch")
        receipts = [receipt] + ([witness] if witness is not None else [])
        if not writable and (_git(workspace, "rev-parse", "HEAD") != commit or _git(workspace, "status", "--porcelain")):
            raise LocalExecutionError("read-only worker changed its repository snapshot")
        return receipts

    @staticmethod
    def _commit_candidate(candidate: Path, receipt: dict[str, Any]) -> str:
        changed = set(_git(candidate, "diff", "--name-only", "HEAD").splitlines()) | set(_git(candidate, "ls-files", "--others", "--exclude-standard").splitlines())
        reported = {name.replace("\\", "/") for name in receipt["report"]["changed_paths"]}
        if changed != reported:
            raise LocalExecutionError(f"builder changed-path receipt mismatch: actual={sorted(changed)}, reported={sorted(reported)}")
        if changed:
            _git(candidate, "add", "--all")
            _git(candidate, "-c", "commit.gpgsign=false", "commit", "-m", "Implement independently selected local tournament challenger")
        return _git(candidate, "rev-parse", "HEAD")

    @staticmethod
    def _publish(state: Path, brain: Path, plan: Any, events: list[dict[str, Any]], status: str) -> dict[str, Any]:
        """Derived Markdown may be rebuilt; signed source events are never rewritten."""
        completed = [event for event in events if event["kind"] == "node_completed"]
        ideas: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = {}
        links = []
        for event in events:
            if event["kind"] not in {"node_completed", "node_failed"}:
                continue
            lines = [f"# {event['node_id']}", f"State: {event['kind']}", f"Recorded: {event['recorded_at']}", f"Authenticated event: {state / 'events' / (str(event['sequence']).zfill(4) + '.json')}"]
            for worker in event.get("workers", []):
                lines += [f"\n## {worker['role']}", f"Session: `{worker['session_id']}`", f"Status: {worker['status']}"]
                report = worker.get("report")
                if report:
                    lines += [report["summary"], "\nFindings:\n" + "\n".join(f"- {item}" for item in report["findings"]), "\nAcceptance evidence:\n" + "\n".join(f"- {item}" for item in report["acceptance_evidence"])]
                    for idea in report["ideas"]:
                        ideas.setdefault(idea["idea_id"], []).append((event, worker, idea))
                    if worker.get("host_checks"):
                        lines += ["\nDeterministic host test receipts:\n```json\n" + json.dumps(worker["host_checks"], indent=2) + "\n```"]
                else:
                    lines.append(str(worker.get("reason")))
            if event.get("reason"):
                lines.append(event["reason"])
            name = f"{event['node_id']}-{event['sequence']:04}.md"
            (brain / name).write_text("\n\n".join(lines) + "\n", encoding="utf-8")
            (brain / f"{event['node_id']}.md").write_text("\n\n".join(lines) + f"\n\n[This attempt]({name}); earlier attempts remain linked from INDEX.md.\n", encoding="utf-8")
            links.append(f"- [{event['node_id']}]({name}) — {event['kind']}")
        idea_links = []
        child_ideas: dict[str, list[str]] = {}
        for identity, history in ideas.items():
            parent = history[-1][2]["parent_idea_id"]
            if parent:
                child_ideas.setdefault(parent, []).append(identity)
        for idea_id, history in ideas.items():
            filename = "idea-" + hashlib.sha256(idea_id.encode()).hexdigest() + ".md"
            latest = history[-1][2]
            children = sorted(child_ideas.get(idea_id, ()))
            metadata = {
                "idea_id": idea_id, "title": latest["title"],
                "parent_idea_id": latest["parent_idea_id"], "child_idea_ids": children,
                "same_idea_revision": len(history), "latest_event": history[-1][0]["node_id"],
                "latest_disposition": latest["disposition"],
                "responsible_actor": history[-1][1]["actor_id"],
                "return_to_role": latest["return_to_agent"], "next_action": latest["next_action"],
            }
            def metadata_json(value: object) -> str:
                return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")

            lines = ["---", *[f"{key}: {metadata_json(value)}" for key, value in metadata.items()], "---",
                     f"# {escape(idea_id, quote=False)}", "Stable idea identity; ordered reports below preserve revisions, dissent, returns and decisions. Court-selection and court-result reports are local court verdicts."]
            if latest["parent_idea_id"]:
                parent_name = "idea-" + hashlib.sha256(latest["parent_idea_id"].encode()).hexdigest() + ".md"
                lines.append(f"[Parent idea]({parent_name})")
            if children:
                lines.append("Children: " + ", ".join(
                    f"[{escape(child, quote=False)}](idea-{hashlib.sha256(child.encode()).hexdigest()}.md)"
                    for child in children
                ))
            for event, worker, idea in history:
                evidence_name = f"{event['node_id']}-{event['sequence']:04}.md"
                lines += [f"\n## {escape(event['node_id'], quote=False)} / {escape(worker['session_id'], quote=False)}", f"[Node evidence and result]({evidence_name})", f"Title: {escape(idea['title'], quote=False)}", f"Hypothesis: {escape(idea['hypothesis'], quote=False)}", f"Source: {escape(idea['source'], quote=False)}", f"Parent idea: {escape(str(idea['parent_idea_id']), quote=False)}", f"Disposition: {idea['disposition']}", f"Reason: {escape(idea['reason'], quote=False)}", f"Return to: {escape(str(idea['return_to_agent']), quote=False)}", f"Next action: {escape(idea['next_action'], quote=False)}"]
            (brain / filename).write_text("\n\n".join(lines) + "\n", encoding="utf-8")
            relation = "root" if not latest["parent_idea_id"] else f"parent `{escape(latest['parent_idea_id'], quote=False)}`"
            if children:
                relation += "; children " + ", ".join(f"`{escape(child, quote=False)}`" for child in children)
            idea_links.append(
                f"| {escape(latest['title'], quote=False)} | [{escape(idea_id, quote=False)}]({filename}) | {relation} | "
                f"{escape(history[-1][0]['node_id'], quote=False)} / {latest['disposition']} | {len(history)} | "
                f"{escape(str(latest['return_to_agent'] or history[-1][1]['role']), quote=False)} | "
                f"{escape(latest['reason'], quote=False)} Next: {escape(latest['next_action'], quote=False)} |"
            )
        result = {"status": status, "authority_profile": "operator-local-v1", "plan_digest": plan.digest(),
                  "completed_nodes": len(completed), "total_nodes": len(plan.nodes),
                  "session_count": len({worker["session_id"] for event in events for worker in event.get("workers", []) if worker.get("session_id")}),
                  "state_directory": str(state), "brain_directory": str(brain),
                  "candidate_directory": str(state / "candidate"),
                  "candidate_commit": completed[-1]["candidate_after"] if completed else None,
                  "promotion_authorized": False}
        (brain / "INDEX.md").write_text("\n\n".join([
            "# Live local tournament", f"Status: **{status}** — {len(completed)}/{len(plan.nodes)} nodes",
            "Actual Codex sessions under one operator's local custody. Worker separation is recorded; this is not an externally signed V4 release.",
            f"Plan: `{plan.digest()}`", f"Run evidence: {state}",
            "## Nodes", "\n".join(links), "## Ideas and iterations",
            "| Title | Stable ID | Relationships | Latest event / disposition | Revision | Responsible / return-to | Rationale and next action |\n|---|---|---|---|---:|---|---|\n" + "\n".join(idea_links),
            "Rollback: retain the original source checkout and discard the isolated candidate. No protected merge or promotion occurs here.",
        ]) + "\n", encoding="utf-8")
        (state / "status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
