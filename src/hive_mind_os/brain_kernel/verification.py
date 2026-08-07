"""Exact-candidate, local-only verification with atomic evidence bundles."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from .canonical import canonical_bytes, canonical_digest
from .contracts import (
    Budget,
    EvaluationPlan,
    EvaluationResult,
    EvaluationState,
    normalize_portable_path,
)
from .events import KernelEvent
from .store import KernelStore

_ZERO_SHA = "0" * 40
_TIME = "1970-01-01T00:00:00Z"


class ExactCandidateVerificationError(RuntimeError):
    """A sealed local verification cannot safely produce an acceptance verdict."""


@dataclass(frozen=True, slots=True)
class TreeSnapshot:
    root_digest: str
    files: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    result: EvaluationResult
    bundle_path: Path
    changed_paths: tuple[str, ...]


CheckRunner = Callable[[str, Path], bool]


def snapshot_tree(root: str | Path) -> TreeSnapshot:
    """Hash regular files only; links and unsafe paths fail closed."""

    supplied_root = Path(root)
    if supplied_root.is_symlink():
        raise ExactCandidateVerificationError("candidate tree root is a symbolic link")
    root_path = supplied_root.resolve()
    if not root_path.is_dir():
        raise ExactCandidateVerificationError("candidate tree is unavailable")
    files: dict[str, str] = {}
    for path in sorted(root_path.rglob("*")):
        if path.is_symlink():
            raise ExactCandidateVerificationError("candidate tree contains a symbolic link")
        if not path.is_file() or ".git" in path.relative_to(root_path).parts:
            continue
        relative = normalize_portable_path(path.relative_to(root_path).as_posix())
        files[relative] = canonical_digest({"bytes": path.read_bytes().hex()})
    return TreeSnapshot(canonical_digest({"files": files}), files)


def evaluation_plan_digest(plan: EvaluationPlan) -> str:
    values = asdict(plan)
    values.pop("plan_digest")
    return canonical_digest(values)


def evaluation_result_digest(result: EvaluationResult) -> str:
    values = asdict(result)
    values.pop("result_digest")
    return canonical_digest(values)


def create_evaluation_plan(
    plan_id: str,
    base_root: str | Path,
    *,
    acceptance_commands: tuple[str, ...],
    allowed_paths: tuple[str, ...],
) -> EvaluationPlan:
    """Create a sealed-state plan from the known base before candidate access."""

    provisional = EvaluationPlan(
        plan_id,
        _ZERO_SHA,
        snapshot_tree(base_root).root_digest,
        acceptance_commands,
        ("local-only",),
        allowed_paths,
        (),
        ("bundle-integrity",),
        ("candidate-mutation", "path-scope"),
        ("distinct-builder-curator",),
        "kernel-verification-bundle-v1",
        ("passed-only-acceptance", "abstain-is-not-pass"),
        Budget(0, 0, 0, 0, 0, len(acceptance_commands), 1, 1),
        EvaluationState.SEALED,
        "sha256:" + "0" * 64,
    )
    return EvaluationPlan(**{**asdict(provisional), "plan_digest": evaluation_plan_digest(provisional)})


def seal_evaluation_plan(
    store: KernelStore,
    work_id: str,
    plan: EvaluationPlan,
    *,
    base_root: str | Path,
    actor_id: str,
) -> int:
    """Durably bind a complete plan before the candidate may be read."""

    if plan.state is not EvaluationState.SEALED or plan.plan_digest != evaluation_plan_digest(plan):
        raise ExactCandidateVerificationError("evaluation plan is not canonically sealed")
    base = snapshot_tree(base_root)
    if base.root_digest != plan.base_tree_digest:
        raise ExactCandidateVerificationError("evaluation base does not match the sealed plan")
    events = store.events()
    if not events:
        raise ExactCandidateVerificationError("evaluation plan requires a kernel mission")
    mission_id = next(
        (event["mission_id"] for event in events if event["work_id"] == work_id),
        None,
    )
    if not isinstance(mission_id, str):
        raise ExactCandidateVerificationError("evaluation plan belongs to unknown work")
    return store.append(
        KernelEvent(
            f"evaluation-plan:{plan.plan_digest}",
            mission_id,
            "evaluation.plan.sealed",
            actor_id,
            _TIME,
            {"plan": plan.to_document(), "base": asdict(base)},
            work_id=work_id,
            actor_role="architect",
            previous_digest=events[-1]["digest"],
        ),
        idempotency_key=plan.plan_digest,
    )


def verify_exact_candidate(
    store: KernelStore,
    work_id: str,
    plan: EvaluationPlan,
    candidate_root: str | Path,
    *,
    builder_id: str,
    evaluator_id: str,
    check_runner: CheckRunner,
    bundle_directory: str | Path,
) -> VerificationOutcome:
    """Verify one resolved candidate; post-resolution mutation fails closed."""

    if not builder_id or not evaluator_id or builder_id == evaluator_id:
        raise ExactCandidateVerificationError("Builder and Curator identities must differ")
    base = _require_sealed_plan(store, work_id, plan)
    candidate = snapshot_tree(candidate_root)
    changed_paths = tuple(sorted(set(base.files) | set(candidate.files)))
    changed_paths = tuple(
        path
        for path in changed_paths
        if base.files.get(path) != candidate.files.get(path)
    )
    scope_valid = set(changed_paths).issubset(set(plan.allowed_test_paths))
    check_results: list[str] = []
    passed = scope_valid
    for command in plan.acceptance_commands:
        try:
            matched = bool(check_runner(command, Path(candidate_root)))
        except Exception:
            matched = False
        check_results.append(f"{command}:{'passed' if matched else 'failed'}")
        passed = passed and matched
    if snapshot_tree(candidate_root) != candidate:
        check_results.append("candidate-mutation:failed")
        passed = False
    state = EvaluationState.PASSED if passed else EvaluationState.FAILED
    provisional = EvaluationResult(
        plan.plan_digest,
        candidate.root_digest,
        evaluator_id,
        state,
        tuple(check_results),
        ("bundle:verification.json",),
        "sha256:" + "0" * 64,
    )
    result = EvaluationResult(**{**asdict(provisional), "result_digest": evaluation_result_digest(provisional)})
    bundle_path = _publish_bundle(bundle_directory, plan, base, candidate, changed_paths, result)
    events = store.events()
    mission_id = _mission_for_work(events, work_id)
    store.append(
        KernelEvent(
            f"evaluation-result:{result.result_digest}",
            mission_id,
            "evaluation.result",
            evaluator_id,
            _TIME,
            {"result": asdict(result)},
            work_id=work_id,
            actor_role="curator",
            previous_digest=events[-1]["digest"],
        ),
        idempotency_key=result.result_digest,
    )
    return VerificationOutcome(result, bundle_path, changed_paths)


def accept_verified_work(
    store: KernelStore,
    work_id: str,
    result: EvaluationResult,
    *,
    actor_id: str,
) -> int:
    """Transition work only through the exact passed result recorded in the spine."""

    if result.state is not EvaluationState.PASSED:
        raise ExactCandidateVerificationError("only a passed evaluation may accept work")
    events = store.events()
    if not any(
        event["event_type"] == "evaluation.result"
        and event["work_id"] == work_id
        and event["payload"].get("result", {}).get("result_digest") == result.result_digest
        for event in events
    ):
        raise ExactCandidateVerificationError("evaluation result is not recorded for this work")
    return store.append(
        KernelEvent(
            f"work-accepted:{work_id}:{result.result_digest}",
            _mission_for_work(events, work_id),
            "work.transition",
            actor_id,
            _TIME,
            {"status": "ACCEPTED", "evaluation_result_digest": result.result_digest},
            work_id=work_id,
            actor_role="integrator",
            previous_digest=events[-1]["digest"],
        )
    )


def verify_bundle(bundle_directory: str | Path) -> None:
    """Re-derive the local bundle digest and embedded evaluation digest."""

    path = Path(bundle_directory) / "verification.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        claimed = document.pop("bundle_digest")
        result = document["result"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ExactCandidateVerificationError("verification bundle is corrupt") from error
    if claimed != canonical_digest(document):
        raise ExactCandidateVerificationError("verification bundle digest is invalid")
    values = dict(result)
    for key in ("check_results", "evidence_refs"):
        values[key] = tuple(values[key])
    try:
        restored = EvaluationResult(**values)
    except (TypeError, ValueError) as error:
        raise ExactCandidateVerificationError("verification result is corrupt") from error
    if restored.result_digest != evaluation_result_digest(restored):
        raise ExactCandidateVerificationError("verification result digest is invalid")


def _require_sealed_plan(store: KernelStore, work_id: str, plan: EvaluationPlan) -> TreeSnapshot:
    if plan.plan_digest != evaluation_plan_digest(plan):
        raise ExactCandidateVerificationError("evaluation plan digest is invalid")
    matches = [
        event
        for event in store.events()
        if event["event_type"] == "evaluation.plan.sealed"
        and event["work_id"] == work_id
        and event["payload"].get("plan", {}).get("plan_digest") == plan.plan_digest
    ]
    if len(matches) != 1:
        raise ExactCandidateVerificationError("evaluation plan was not sealed for this work")
    document = matches[0]["payload"].get("base")
    if not isinstance(document, Mapping):
        raise ExactCandidateVerificationError("sealed plan has no base manifest")
    try:
        base = TreeSnapshot(str(document["root_digest"]), dict(document["files"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ExactCandidateVerificationError("sealed plan base manifest is malformed") from error
    if base.root_digest != plan.base_tree_digest or base.root_digest != canonical_digest({"files": base.files}):
        raise ExactCandidateVerificationError("sealed plan base manifest is invalid")
    return base


def _publish_bundle(
    destination: str | Path,
    plan: EvaluationPlan,
    base: TreeSnapshot,
    candidate: TreeSnapshot,
    changed_paths: tuple[str, ...],
    result: EvaluationResult,
) -> Path:
    output = Path(destination)
    if output.exists():
        raise ExactCandidateVerificationError("verification bundle destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        document: dict[str, object] = {
            "schema_version": 1,
            "plan": plan.to_document(),
            "base": asdict(base),
            "candidate": asdict(candidate),
            "changed_paths": list(changed_paths),
            "result": asdict(result),
        }
        document["bundle_digest"] = canonical_digest(document)
        (staging / "verification.json").write_bytes(canonical_bytes(document) + b"\n")
        os.replace(staging, output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return output


def _mission_for_work(events: list[dict[str, object]], work_id: str) -> str:
    for event in events:
        if event.get("work_id") == work_id and isinstance(event.get("mission_id"), str):
            return str(event["mission_id"])
    raise ExactCandidateVerificationError("work is not recorded in the kernel spine")
