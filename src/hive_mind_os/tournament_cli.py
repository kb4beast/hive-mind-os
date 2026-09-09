"""Portable tournament preparation and additive second-brain publication.

Preparation compiles a plan. It does not authenticate a host or report execution.
The brain is a local history store, not an authorization or promotion service.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Sequence

from .dag_standard import compile_plan
from .idea_lineage import IdeaLineageStore, idea_note_name
from .path_boundary import require_external_path
from .plan_generation import PinnedArtifact, PlanGenerationRequest
from .portable_plan import RepositorySubject, SubjectBinding
from .runtime_contracts import (
    AuthorityEnvelope,
    EvidenceReference,
    canonical_json_bytes,
    raw_sha256,
)
from .tournament_plan_factory import TournamentPlanFactory

# The CLI emits the current V2 source/version identity, so it must not relabel
# V1 or arbitrary bytes as V2. Accept Git's two ordinary line-ending checkouts.
_STANDARD_V2_LF_DIGEST = "sha256:3b072fee295e75b8c28709d417f9036fa384e31dc53ca85526babd0881d0e90a"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments], capture_output=True, check=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _write(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)


def prepare_tournament(
    *, repository: Path, request_file: Path, standard_file: Path,
    output: Path, target: str = "main",
) -> dict[str, object]:
    """Pin the target's HEAD, preserve the exact request, and compile a fresh DAG."""
    repository = Path(_git(repository.resolve(), "rev-parse", "--show-toplevel"))
    # Resolve filesystem aliases before constructing any preparation artifact.
    output = require_external_path(output, repository, label="tournament output")
    # Validate the branch spelling as data; never turn a target name into a command.
    _git(repository, "check-ref-format", "--branch", target)
    commit = _git(repository, "rev-parse", "HEAD")
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    # Common-dir is shared across worktrees but distinct across local repositories.
    common = _git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
    repository_id = raw_sha256(Path(common).resolve().as_uri().encode("utf-8"))
    subject = SubjectBinding.for_repository(RepositorySubject(repository_id, commit, tree, target))
    request_bytes = request_file.read_bytes()
    if not request_bytes.decode("utf-8").strip():
        raise ValueError("request must contain a UTF-8 objective")
    request_digest = raw_sha256(request_bytes)
    now = datetime.now(UTC)
    observed_at = now.isoformat().replace("+00:00", "Z")
    request = PlanGenerationRequest(
        request_digest, request_digest, subject.subject_id, "repository",
        repository_id, target, commit, tree, None,
    )
    authority = AuthorityEnvelope(
        "local-tournament", "requesting-operator", request_digest,
        ("inspect", "local-edit", "local-test", "prepare-evidence"),
        ("credential", "deployment", "merge", "payment", "production-mutation",
         "protected-merge", "push"),
        (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"), False,
    )
    standard = PinnedArtifact.pin("standard", standard_file.read_bytes())
    if raw_sha256(standard.content.replace(b"\r\n", b"\n")) != _STANDARD_V2_LF_DIGEST:
        raise ValueError("unsupported standard: supply the pinned DAG_AUTHORING_STANDARD_V2.md")
    snapshot = canonical_json_bytes({
        "repository_id": repository_id, "commit": commit, "tree": tree,
        "observed_at": observed_at,
        "working_tree_status": _git(repository, "status", "--porcelain=v1"),
        "scope": "committed HEAD; uncommitted changes are not included",
        "source_ingestion": "snapshot pin only; full source audit is BASELINE-001 work",
    })
    evidence = (
        EvidenceReference("request", request_digest, "request.txt", ("USER-OBJECTIVE",), observed_at),
        EvidenceReference("snapshot", raw_sha256(snapshot), "snapshot.json", ("BASELINE",), observed_at),
    )
    factory = TournamentPlanFactory()
    plan = factory.build(request, standard=standard, authority=authority, evidence=evidence)
    mappings = PinnedArtifact.pin("node-mappings", canonical_json_bytes({
        node.node_id: {"roles": list(node.roles), "acceptance": list(node.acceptance_criteria)}
        for node in plan.nodes
    }))
    compiler = PinnedArtifact.pin("compiler", Path(__file__).with_name("dag_standard.py").read_bytes())
    generated, _ = factory.generate(
        request, standard=standard, authority=authority, evidence=evidence,
        node_mappings=mappings,
        sources=(PinnedArtifact.pin("request", request_bytes), PinnedArtifact.pin("snapshot", snapshot)),
        compiler=compiler,
    )
    compilation = compile_plan(
        plan.canonical_bytes(), expected_plan_digest=plan.digest(), standard_bytes=standard.content,
        expected_request_id=request_digest, expected_subject_id=subject.subject_id,
    )
    manifest = {
        "schema_version": 1, "status": "PREPARED", "execution_status": "AWAITING_AUTHENTICATED_EXECUTION",
        "available_execution_profiles": ["operator-local-v1", "external-host"],
        "plan_id": plan.plan_id, "plan_digest": plan.digest(),
        "generation_id": generated.record.generation_id, "request_id": request_digest,
        "subject_id": subject.subject_id, "repository_id": repository_id,
        "brain_subject_id": repository_id,
        "commit": commit, "tree": tree, "target": target, "observed_at": observed_at,
        "execution_authorized": False, "promotion_authorized": False,
        "next_action": "Use dag execute --runtime local with an explicit operator directive and separate host custody, or configure an external authenticated host; retain actual task and test receipts.",
    }
    documents = {
        "plan.json": plan.canonical_bytes(), "standard.md": standard.content,
        "compiler-source.py": compiler.content,
        "request.txt": request_bytes, "snapshot.json": snapshot, "node-mappings.json": mappings.content,
        "generation.json": canonical_json_bytes(generated.record.to_document()),
        "activation-manifest.json": generated.activation_material.external_manifest_bytes,
        "source-inventory.json": canonical_json_bytes([item.inventory_document() for item in generated.source_inventory]),
        "compilation.json": canonical_json_bytes(compilation.to_document()),
        "manifest.json": canonical_json_bytes(manifest),
        "graph.mmd": ("flowchart TD\n" + "\n".join(
            f'  {dependency} --> {node.node_id}' for node in plan.nodes for dependency in node.dependencies
        ) + "\n").encode("utf-8"),
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, content in documents.items():
        _write(output / name, content)
    store = IdeaLineageStore(output / "brain.sqlite3")
    store.close()
    guide = [
        "# Tournament\n", f"Subject: `{subject.subject_id}`\n",
        f"Base commit: `{commit}`\n", f"Plan digest: `{plan.digest()}`\n",
        "Status: compiled and prepared. Host execution has not occurred.\n",
        f"Stable brain subject: `{repository_id}`. Reuse this ID and the original brain database for future commits and plan generations. The plan subject ID binds only this snapshot.\n",
        "Early proposals need a hypothesis and sources. Independent challenge may find no defect; it must record what was examined. Returns preserve the idea ID and explain the next action.\n",
        "## Execution rounds\n",
    ]
    for index, round_ in enumerate(compilation.rounds, 1):
        guide.append(f"{index}. {', '.join(round_.node_ids)}\n")
    guide.extend((
        "\n## Inspect\n\n```powershell\n",
        f"python -m hive_mind_os.cli dag validate --plan '{output / 'plan.json'}' --standard '{output / 'standard.md'}' --expected-plan-digest {plan.digest()}\n",
        "```\n\nUse `hive-mind tournament propose`, `record`, and `brain` to retain idea history. Actor IDs are local assertions, not authenticated court verdicts.\n",
        "Dispatch with `dag execute --runtime local` under an explicit operator directive and separate host custody, or configure an independently authenticated external host. Preparation creates no execution signature. The local host records execution history in the supplied brain directory.\n",
    ))
    _write(output / "README.md", "\n".join(guide).encode("utf-8"))
    return manifest


def publish_brain(*, database: Path, subject_id: str, idea_ids: Sequence[str], output: Path) -> dict[str, object]:
    """Publish a fresh immutable Markdown snapshot; never replace user notes."""
    if not database.is_file():
        raise ValueError("brain database does not exist")
    store = IdeaLineageStore(database, read_only=True)
    try:
        notes: dict[str, str] = {}
        histories: dict[str, tuple] = {}
        all_ids = store.idea_ids(subject_id)
        children: dict[str, list[str]] = {idea_id: [] for idea_id in all_ids}
        for known_id in all_ids:
            history = store.history(subject_id, known_id)
            histories[known_id] = history
            if history and history[0].parent_idea_id is not None:
                children.setdefault(history[0].parent_idea_id, []).append(known_id)
        pending = list(idea_ids)
        while pending:
            idea_id = pending.pop(0)
            if idea_id in notes:
                continue
            history = histories.get(idea_id) or store.history(subject_id, idea_id)
            if not history:
                raise ValueError(f"unknown idea: {idea_id}")
            histories[idea_id] = history
            related_children = tuple(sorted(children.get(idea_id, ())))
            notes[idea_id] = store.render_markdown(
                subject_id, idea_id, children=related_children
            )
            parent = history[0].parent_idea_id
            if parent is not None:
                pending.append(parent)
            pending.extend(related_children)
    finally:
        store.close()
    if not notes:
        raise ValueError("at least one idea is required")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for idea_id, markdown in notes.items():
        _write(output / idea_note_name(idea_id), markdown.encode("utf-8"))
    def label(value: str) -> str:
        return escape(value).replace("[", "&#91;").replace("]", "&#93;").replace("\n", " ")

    rows = []
    for idea_id in sorted(notes):
        latest = histories[idea_id][-1]
        parent = latest.parent_idea_id
        relation = (
            f"parent [{label(parent)}]({idea_note_name(parent)})"
            if parent is not None else "root"
        )
        child_ids = children.get(idea_id, ())
        if child_ids:
            relation += "; children " + ", ".join(
                f"[{label(child)}]({idea_note_name(child)})" for child in child_ids
            )
        rationale = latest.reason
        if latest.next_action:
            rationale += f" Next: {latest.next_action}"
        rows.append(
            f"| {label(latest.title)} | [{label(idea_id)}]({idea_note_name(idea_id)}) | "
            f"{relation} | {label(latest.event_type)} | {latest.revision} | "
            f"{label(latest.return_to_agent or latest.actor_id)} | {label(rationale)} |"
        )
    index = (
        "# Idea history\n\n" + f"Subject: {label(subject_id)}\n\n"
        "| Title | Stable ID | Relationships | Latest event | Revision | Responsible / return-to | Rationale and next action |\n"
        "|---|---|---|---|---:|---|---|\n" + "\n".join(rows)
        + "\n\nEach idea note links every prior attempt and source reference; runtime projections also link node, candidate, and test receipts. "
        "Derived local history does not authorize execution or promotion.\n"
    )
    _write(output / "INDEX.md", index.encode("utf-8"))
    return {"status": "PUBLISHED", "output": str(output), "ideas": list(notes)}


def build_tournament_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hive-mind tournament")
    commands = parser.add_subparsers(dest="tournament_command", required=True)
    prepare = commands.add_parser("prepare", help="Pin a repository objective and compile an external tournament")
    for name in ("repository", "request-file", "standard", "output"):
        prepare.add_argument(f"--{name}", required=True, type=Path)
    prepare.add_argument("--target", default="main")
    for name in ("propose", "record", "brain"):
        command = commands.add_parser(name)
        command.add_argument("--database", required=True, type=Path)
        command.add_argument("--subject-id", required=True)
        if name == "brain":
            command.add_argument("--idea-id", required=True, action="append")
            command.add_argument("--output", required=True, type=Path)
            continue
        command.add_argument("--idea-id", required=True)
        command.add_argument("--actor-id", required=True)
        if name == "propose":
            for field in ("title", "hypothesis", "source"):
                command.add_argument(f"--{field}", required=True)
            command.add_argument("--parent-idea-id")
        else:
            command.add_argument("--event-type", required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--expected-sequence", required=True, type=int)
            for field in ("hypothesis", "source", "return-to-agent", "next-action"):
                command.add_argument(f"--{field}")
    return parser


def run_tournament_command(args: argparse.Namespace) -> int:
    try:
        if args.tournament_command == "prepare":
            result = prepare_tournament(repository=args.repository, request_file=args.request_file,
                standard_file=args.standard, output=args.output, target=args.target)
        elif args.tournament_command == "brain":
            result = publish_brain(database=args.database, subject_id=args.subject_id,
                idea_ids=args.idea_id, output=args.output)
        else:
            if not args.database.is_file():
                raise ValueError("brain database does not exist; prepare a tournament first")
            store = IdeaLineageStore(args.database)
            try:
                common = dict(subject_id=args.subject_id, idea_id=args.idea_id, actor_id=args.actor_id)
                if args.tournament_command == "propose":
                    event = store.propose(**common, title=args.title, hypothesis=args.hypothesis,
                        source=args.source, parent_idea_id=args.parent_idea_id)
                else:
                    event = store.append(**common, event_type=args.event_type, reason=args.reason,
                        expected_sequence=args.expected_sequence, hypothesis=args.hypothesis,
                        source=args.source, return_to_agent=args.return_to_agent, next_action=args.next_action)
                result = {"status": "RECORDED", "idea_id": args.idea_id, "sequence": event.sequence}
            finally:
                store.close()
    except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(run_tournament_command(build_tournament_parser().parse_args(argv)))


if __name__ == "__main__":
    main()
