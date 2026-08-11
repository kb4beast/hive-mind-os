from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Sequence, cast

from .acceptance import (
    AcceptanceSpecification,
    AcceptanceSpecificationError,
    normalize_acceptance_specifications,
)
from .autonomous_os import (
    AutonomousBrain,
    AutonomousRunError,
    GitHubRestCommentGateway,
    HostKind,
)
from .autonomy import AutonomyBudget
from .autopilot_workflow import (
    DEFAULT_OBJECTIVE,
    DEFAULT_TARGET_BRANCH,
    PortableAutopilotError,
    initialize_repository,
    inspect_repository,
    trust_controller,
)
from .autopilot_workflow import (
    simple_prompt as portable_autopilot_prompt,
)
from .benchmark_harness import BenchmarkHarness
from .brain_kernel.context import ContextManifestStore
from .brain_kernel.contracts import MissionCharter
from .brain_kernel.doctor import inspect_kernel_environment
from .brain_kernel.memory import MemoryCatalogStore, MemoryDenied, RetrievalRequest
from .brain_kernel.planner import (
    DeterministicFixturePlanner,
    graph_from_events,
    persist_plan,
)
from .brain_kernel.store import KernelIntegrityError, KernelStore
from .continuation import (
    ContinuationPacketError,
    export_packet,
    validate_packet,
    write_packet,
)
from .courtroom import CaseParticipants
from .current_state_audit import (
    collect_current_state_audit,
    create_audit_artifact,
    write_audit_artifact,
)
from .demo_fixture import build_fixture_repo
from .experiment_runner import EVALUATION_SURFACE_UNAVAILABLE
from .ingestion import ExhibitStore, defer_obligation, register_exhibit
from .ledger import EvidenceLedger
from .mission import (
    RepositoryMission,
    ScriptedRepositoryBackend,
    resolve_repository_pin,
)
from .mission_store import (
    MissionStore,
    MissionStoreError,
    ReconciliationError,
    resume_mission,
)
from .model_backend import ModelBackend
from .model_provider import ModelProviderError, provider_from_env
from .models import AutonomyLevel, Objective, Role
from .pit_oracle import LeakageError, PointInTimeOracle, SealViolation
from .policy import PolicyEngine
from .projection import build_projection, projection_json, write_projection_html
from .repository_compatibility import record_legacy_enqueue
from .runtime import HiveKernel
from .scheduler import Scheduler
from .source_docket import load_source_docket
from .verify import VerificationError, verify_repository
from .workers import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hive-mind", description="Run the Hive Mind OS bootstrap kernel")
    parser.add_argument("goal", help="Outcome for the specialist agent team")
    parser.add_argument("--repository", help="Optional owner/repository target")
    parser.add_argument("--criterion", action="append", default=[], help="Acceptance criterion; repeatable")
    parser.add_argument(
        "--backend",
        choices=("deterministic", "model"),
        default="deterministic",
        help="Agent backend (default: deterministic offline backend)",
    )
    return parser


def build_audit_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind audit",
        description="Emit a digested CurrentStateAudit for a Git worktree",
    )
    parser.add_argument(
        "--repository",
        default=".",
        help="Git worktree to audit (default: current directory)",
    )
    parser.add_argument(
        "--output",
        help="Write the JSON artifact to this path; omit to print it",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Collect repository and docket facts without executing tests; marks the audit incomplete",
    )
    parser.add_argument(
        "--signing-key-file",
        help="Optional file containing an HMAC key; the key is never written to the artifact",
    )
    parser.add_argument(
        "--signing-key-id",
        help="Required stable identifier when --signing-key-file is used",
    )
    return parser


def build_autopilot_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind autopilot",
        description="Initialize or operate a reusable intent-driven repository DAG.",
    )
    commands = parser.add_subparsers(dest="autopilot_command", required=True)
    init = commands.add_parser("init", help="Record a portable governed DAG-build request")
    init.add_argument("--repository", default=".")
    init.add_argument("--objective", default=DEFAULT_OBJECTIVE)
    init.add_argument("--target-branch", default=DEFAULT_TARGET_BRANCH)
    init.add_argument("--remote", default="origin", help="Git remote to identify, or an empty value for local-only use")
    init.add_argument(
        "--protected-branch",
        action="append",
        default=[],
        help="Additional protected branch name; repeat for repository-specific policy",
    )
    inspect = commands.add_parser("inspect", help="Infer intent and emit the next orchestration contract")
    inspect.add_argument("--repository", default=".")
    inspect.add_argument("--request", default="")
    inspect.add_argument("--actor", default="hive-mind:portable-orchestrator")
    inspect.add_argument("--apply", action="store_true")
    inspect.add_argument("--trust-state-root")
    trust = commands.add_parser(
        "trust-controller",
        help="Pin an independently reviewed target-controller bundle outside the repository",
    )
    trust.add_argument("--repository", default=".")
    trust.add_argument("--actor", required=True)
    trust.add_argument("--authorization-capability", required=True)
    trust.add_argument("--trust-state-root")
    commands.add_parser("prompt", help="Print the one reusable operator prompt")
    return parser


def _run_autopilot(args: argparse.Namespace) -> int:
    try:
        if args.autopilot_command == "init":
            result = initialize_repository(
                args.repository,
                objective=args.objective,
                target_branch=args.target_branch,
                remote_name=args.remote,
                protected_branches=args.protected_branch,
            )
        elif args.autopilot_command == "inspect":
            result = inspect_repository(
                args.repository,
                request=args.request,
                apply=args.apply,
                actor=args.actor,
                trust_state_root=args.trust_state_root,
            )
        elif args.autopilot_command == "trust-controller":
            result = trust_controller(
                args.repository,
                actor=args.actor,
                authorization_capability=args.authorization_capability,
                trust_state_root=args.trust_state_root,
            )
        else:
            print(portable_autopilot_prompt())
            return 0
    except PortableAutopilotError as error:
        print(f"hive-mind autopilot: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_kernel_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind kernel",
        description="Inspect additive Verifiable Hive Kernel capabilities.",
    )
    commands = parser.add_subparsers(dest="kernel_command", required=True)
    doctor = commands.add_parser(
        "doctor",
        help="Report local kernel prerequisites without performing remote effects.",
    )
    doctor.add_argument("--repository", default=".", help="Git worktree to inspect")
    doctor.add_argument(
        "--state-dir",
        default=".hive-mind-kernel-state",
        help="State directory to validate without creating it",
    )
    doctor.add_argument("--json", action="store_true", dest="json_output")
    status = commands.add_parser(
        "status",
        help="Show a read-only event-derived status for one kernel mission.",
    )
    status.add_argument("mission_id", help="Kernel mission identifier")
    status.add_argument(
        "--state-dir",
        default=".hive-mind-kernel-state",
        help="Directory containing brain-kernel.sqlite3",
    )
    status.add_argument("--json", action="store_true", dest="json_output")
    plan = commands.add_parser(
        "plan", help="Persist a deterministic fixture plan for an existing kernel mission."
    )
    plan.add_argument("mission_id", help="Kernel mission identifier")
    plan.add_argument("--charter", required=True, help="Canonical mission charter JSON file")
    plan.add_argument(
        "--fixture", choices=("bugfix", "feature", "refactor", "docs", "integration"), required=True
    )
    plan.add_argument("--state-dir", default=".hive-mind-kernel-state")
    plan.add_argument("--json", action="store_true", dest="json_output")
    graph = commands.add_parser(
        "graph", help="Render a read-only, event-derived kernel work graph."
    )
    graph.add_argument("mission_id", help="Kernel mission identifier")
    graph.add_argument("--charter", required=True, help="Canonical mission charter JSON file")
    graph.add_argument("--state-dir", default=".hive-mind-kernel-state")
    graph.add_argument("--json", action="store_true", dest="json_output")
    closeout = commands.add_parser(
        "closeout", help="Read a local, event-derived technical closeout report."
    )
    closeout.add_argument("mission_id", help="Kernel mission identifier")
    closeout.add_argument("--state-dir", default=".hive-mind-kernel-state")
    closeout.add_argument(
        "--bundle-ref",
        action="append",
        default=[],
        metavar="REFERENCE=PATH",
        help="Local verification bundle directory for one recorded opaque reference.",
    )
    closeout.add_argument("--json", action="store_true", dest="json_output")
    memory = commands.add_parser("memory", help="Inspect bounded local kernel memory.")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    search = memory_commands.add_parser("search", help="Rank scoped memory from a durable snapshot.")
    search.add_argument("--snapshot", required=True, help="Memory snapshot digest")
    search.add_argument("--mission", required=True)
    search.add_argument("--work", required=True)
    search.add_argument("--role", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--now", required=True, help="RFC 3339 retrieval time")
    search.add_argument("--data-scope", action="append", default=[])
    search.add_argument("--sensitivity-scope", action="append", default=["public", "internal"])
    search.add_argument("--require-sensitivity", action="append", default=[])
    search.add_argument("--repository-key")
    search.add_argument("--state-dir", default=".hive-mind-kernel-state")
    search.add_argument("--json", action="store_true", dest="json_output")
    inspect = memory_commands.add_parser("inspect", help="Inspect memory metadata without reading its body.")
    inspect.add_argument("record_id")
    inspect.add_argument("--snapshot", required=True, help="Memory snapshot digest")
    inspect.add_argument("--state-dir", default=".hive-mind-kernel-state")
    inspect.add_argument("--json", action="store_true", dest="json_output")
    expire = memory_commands.add_parser("expire", help="Append expiration facts and save a successor snapshot.")
    expire.add_argument("--snapshot", required=True, help="Memory snapshot digest")
    expire.add_argument("--now", required=True, help="RFC 3339 maintenance time")
    expire.add_argument("--state-dir", default=".hive-mind-kernel-state")
    expire.add_argument("--json", action="store_true", dest="json_output")
    context = commands.add_parser("context", help="Inspect one persisted kernel context manifest.")
    context.add_argument("--manifest", required=True, help="Context manifest digest")
    context.add_argument("--state-dir", default=".hive-mind-kernel-state")
    context.add_argument("--json", action="store_true", dest="json_output")
    return parser


def build_ingest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind ingest",
        description="Capture one human-supplied source exhibit without adjudicating it",
    )
    parser.add_argument("--source", required=True, help="Existing source id, such as SRC-005")
    parser.add_argument("--file", required=True, help="Human-supplied exhibit file")
    parser.add_argument("--locator", required=True, help="Exact source URI and fragment/timestamp")
    parser.add_argument("--media-type", required=True, help="IANA-style media type")
    parser.add_argument(
        "--license",
        required=True,
        help="Locally supported license policy token, unknown, or unresolved-pending-review",
    )
    parser.add_argument(
        "--capturer",
        default="source-ingestion-cli",
        help="Identity performing this capture",
    )
    parser.add_argument(
        "--supply-method",
        choices=("human-provided-file", "agent-derived"),
        default="human-provided-file",
    )
    parser.add_argument("--parent-digest", help="Required SHA-256 digest for derived artifacts")
    parser.add_argument("--expected-digest", help="Optional independently supplied SHA-256")
    parser.add_argument(
        "--evidence-root",
        default="evidence/sources",
        help="Source evidence directory (default: evidence/sources)",
    )
    return parser


def build_defer_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind defer",
        description="Record a dated courtroom defer verdict for unavailable source evidence",
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Existing source id; repeat for an aggregate obligation",
    )
    parser.add_argument("--obligation", help="Stable obligation id")
    parser.add_argument("--reason", required=True, help="Specific uncaptured evidence obligation")
    parser.add_argument("--review-by", required=True, help="Future review date (YYYY-MM-DD)")
    parser.add_argument("--advocate", default="source-evidence-advocate")
    parser.add_argument("--cross-examiner", default="source-evidence-cross-examiner")
    parser.add_argument("--judge", default="source-evidence-judge")
    parser.add_argument(
        "--evidence-root",
        default="evidence/sources",
        help="Source evidence directory (default: evidence/sources)",
    )
    return parser


def build_deliver_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind deliver",
        description="Produce a verified local repository delivery artifact",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="Local Git worktree to improve",
    )
    parser.add_argument(
        "--objective",
        required=True,
        help="Measurable repository outcome",
    )
    parser.add_argument(
        "--criterion",
        action="append",
        default=[],
        help="Acceptance criterion; repeatable",
    )
    parser.add_argument(
        "--acceptance-spec",
        action="append",
        default=[],
        metavar="FILE",
        help="JSON executable acceptance specification; repeat once per criterion",
    )
    parser.add_argument(
        "--backend",
        choices=("fixture-demo", "model"),
        default="fixture-demo",
        help="Repository backend (default: deterministic offline fixture demonstration)",
    )
    parser.add_argument(
        "--provider",
        choices=("openai_compatible", "anthropic", "codex_subscription"),
        help="Model provider; overrides HIVE_MIND_MODEL_PROVIDER",
    )
    parser.add_argument(
        "--base-url",
        help="Provider HTTPS base URL; overrides HIVE_MIND_MODEL_BASE_URL",
    )
    parser.add_argument(
        "--model",
        help="Provider model identifier; overrides HIVE_MIND_MODEL_MODEL",
    )
    parser.add_argument(
        "--pin",
        help="Optional full 40-hex base commit; defaults to the local worktree HEAD",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Absent directory to publish after independent verification",
    )
    parser.add_argument(
        "--scripted-variant",
        choices=("good", "sabotage"),
        default="good",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--state-dir",
        help="Persist checkpoints and receipts here for later resume",
    )
    return parser


def build_demo_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind demo",
        description="Run the deterministic offline fixture delivery demonstration",
    )
    parser.add_argument(
        "--output",
        default="demo-out",
        help="Absent directory for the delivery receipt bundle (default: ./demo-out)",
    )
    return parser


def build_resume_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind resume",
        description="Resume one interrupted durable repository mission",
    )
    parser.add_argument("mission_id", help="Durable mission identifier")
    parser.add_argument(
        "--state-dir",
        default=".hive-mind-state",
        help="Mission state directory (default: .hive-mind-state)",
    )
    return parser


def build_missions_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind missions",
        description="List durable repository missions",
    )
    parser.add_argument(
        "--state-dir",
        default=".hive-mind-state",
        help="Mission state directory (default: .hive-mind-state)",
    )
    return parser


def build_benchmark_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind benchmark run",
        description="Run the offline P13 benchmark measurement harness",
    )
    parser.add_argument(
        "action",
        choices=("run",),
        help="Benchmark action",
    )
    parser.add_argument(
        "--lanes",
        default="hive,baseline",
        help="Comma-separated lanes: hive,baseline",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
        help="Repetitions per task and lane (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Fixed bootstrap seed (default: 7)",
    )
    parser.add_argument(
        "--output",
        default="evidence/benchmarks",
        help="Append-only benchmark evidence root",
    )
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Optional task ID subset; repeatable",
    )
    return parser


def build_pit_episode_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind pit-episode",
        description="Run one physically isolated point-in-time Git episode",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="Local Git worktree containing the target commit",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Full 40-hex target commit SHA",
    )
    parser.add_argument(
        "--learner",
        choices=("scripted",),
        default="scripted",
        help="Offline learner implementation (default: scripted)",
    )
    parser.add_argument(
        "--state-dir",
        help="Episode, ledger, environment, and receipt directory",
    )
    return parser


def build_experiment_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind experiment run",
        description="Unavailable until prompts are evaluated through a real backend",
    )
    parser.add_argument("action", choices=("run",), help="Experiment action")
    parser.add_argument(
        "--role",
        required=True,
        choices=tuple(role.value for role in Role),
    )
    parser.add_argument("--challenger", required=True, help="Prompt variant file")
    parser.add_argument(
        "--surface",
        required=True,
        choices=("fixture-missions",),
        help="Pinned evaluation surface",
    )
    parser.add_argument("--repetitions", required=True, type=int)
    parser.add_argument(
        "--state-dir",
        default=".hive-mind-experiments",
        help="Prompt registry, ledger, and experiment counter state",
    )
    parser.add_argument(
        "--evidence-root",
        default="evidence/experiments",
        help="Append-only experiment record directory",
    )
    return parser


def build_verify_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind verify",
        description="Verify a committed change against one sealed acceptance specification",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--spec", required=True, help="Acceptance specification JSON")
    parser.add_argument(
        "--candidate",
        required=True,
        help="Full 40-hex immutable candidate commit SHA",
    )
    parser.add_argument("--output", required=True, help="New receipt bundle directory")
    return parser


def build_enqueue_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind enqueue",
        description="Enqueue one durable local repository mission",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--criterion", action="append", default=[])
    parser.add_argument(
        "--acceptance-spec",
        action="append",
        default=[],
        metavar="FILE",
        help="Typed executable acceptance specification JSON; repeatable",
    )
    parser.add_argument("--backend", choices=("scripted",), default="scripted")
    parser.add_argument("--pin")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--state-dir", default=".hive-mind-state")
    parser.add_argument(
        "--kernel-state-dir",
        help="Separate kernel migration-record directory (default: sibling .hive-mind-kernel-state)",
    )
    parser.add_argument(
        "--compatibility-mode",
        choices=("kernel-v1", "legacy"),
        default="kernel-v1",
        help="Use the versioned kernel ingress record or retain legacy-only dispatch for rollback.",
    )
    return parser


def build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind serve",
        description="Run durable local mission workers",
    )
    parser.add_argument("--workers", type=int, default=1)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--forever", action="store_true")
    parser.add_argument("--state-dir", default=".hive-mind-state")
    return parser


def build_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind status",
        description="Project scheduler, mission-store, and ledger truth",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", dest="json_output")
    output.add_argument("--html", help="Write a self-contained static status page")
    parser.add_argument("--state-dir", default=".hive-mind-state")
    return parser


def build_continuation_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind continuation",
        description="Export or validate a local-only autonomous continuation packet",
    )
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("export")
    export.add_argument("--repository", required=True, help="Clean local Git worktree")
    export.add_argument("--input", required=True, help="Short structured packet source JSON")
    export.add_argument("--output", required=True, help="New packet path outside the repository")
    validate = commands.add_parser("validate")
    validate.add_argument("--repository", required=True, help="Bound local Git worktree")
    validate.add_argument("--packet", required=True, help="Existing continuation packet JSON")
    return parser


def build_autonomous_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-mind autonomous",
        description="Run a governed, host-neutral autonomous repository worktree",
    )
    commands = parser.add_subparsers(dest="action", required=True)
    kickoff = commands.add_parser("kickoff", help="Create an isolated branch from one user prompt")
    kickoff.add_argument("--repository", required=True, help="Clean local Git repository")
    kickoff.add_argument("--prompt", required=True, help="Kickoff objective; safe text only")
    kickoff.add_argument("--host", choices=tuple(item.value for item in HostKind), required=True)
    kickoff.add_argument("--run-id", help="Optional stable run identifier")
    kickoff.add_argument("--allow-remote-push", action="store_true")
    kickoff.add_argument("--allow-pr-comments", action="store_true")
    kickoff.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    turn = commands.add_parser("turn", help="Run the selected signed-in coding host locally")
    turn.add_argument("--run-id", required=True)
    turn.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    register = commands.add_parser("register-pr", help="Bind this run to its own draft PR")
    register.add_argument("--run-id", required=True)
    register.add_argument("--number", required=True, type=int)
    register.add_argument("--url", required=True)
    register.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    open_pr = commands.add_parser("open-draft-pr", help="Push the run branch and open a draft PR")
    open_pr.add_argument("--run-id", required=True)
    open_pr.add_argument("--owner", required=True)
    open_pr.add_argument("--repository", required=True)
    open_pr.add_argument("--base", required=True)
    open_pr.add_argument("--title", required=True)
    open_pr.add_argument("--body", required=True)
    open_pr.add_argument("--token-env", default="GITHUB_TOKEN")
    open_pr.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    poll = commands.add_parser("poll-pr", help="Handle new conversation comments on the bound PR")
    poll.add_argument("--run-id", required=True)
    poll.add_argument("--owner", required=True)
    poll.add_argument("--repository", required=True)
    poll.add_argument("--token-env", default="GITHUB_TOKEN")
    poll.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    push = commands.add_parser("push", help="Push only the run's own non-protected branch")
    push.add_argument("--run-id", required=True)
    push.add_argument("--remote", default="origin")
    push.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    learn = commands.add_parser("learn", help="PIT-grade every human commit after the run start")
    learn.add_argument("--run-id", required=True)
    learn.add_argument("--human-final-commit", required=True)
    learn.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    supervise = commands.add_parser(
        "supervise",
        help="Boundedly process new PR feedback and local human commits without restating context",
    )
    supervise.add_argument("--run-id", required=True)
    supervise.add_argument("--polls", required=True, type=int)
    supervise.add_argument("--interval-seconds", default=60.0, type=float)
    supervise.add_argument("--owner")
    supervise.add_argument("--repository")
    supervise.add_argument("--token-env", default="GITHUB_TOKEN")
    supervise.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    events = commands.add_parser("events", help="Print the run's safe append-only event ledger")
    events.add_argument("--run-id", required=True)
    events.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    requirements = commands.add_parser(
        "requirements",
        help="Print the sealed carry-forward requirements for an autonomous run",
    )
    requirements.add_argument("--run-id", required=True)
    requirements.add_argument("--state-dir", default=".hive-mind-state/autonomous")
    return parser


async def _run(args: argparse.Namespace) -> int:
    objective = Objective(
        goal=args.goal,
        repository=args.repository,
        acceptance_criteria=tuple(args.criterion),
    )
    ledger = EvidenceLedger()
    backend = None
    if args.backend == "model":
        try:
            backend = ModelBackend(
                provider_from_env(),
                ledger=ledger,
                role_providers={
                    Role.CURATOR: provider_from_env(role=Role.CURATOR)
                },
            )
        except (ModelProviderError, ValueError) as error:
            raise SystemExit(f"model backend configuration failed: {error}") from None
    report = await HiveKernel(backend=backend, ledger=ledger).run_objective(objective)
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "status": report.status.value,
                "roles_completed": [result.role.value for result in report.results],
                "evidence_count": report.evidence_count,
            },
            indent=2,
        )
    )
    return 0 if report.status.value == "succeeded" else 1


async def _run_deliver(args: argparse.Namespace) -> int:
    state_store = MissionStore(args.state_dir) if args.state_dir else None
    ledger = EvidenceLedger(
        state_store.state_dir / "evidence-ledger.sqlite3"
        if state_store is not None
        else ":memory:"
    )
    budget = AutonomyBudget(
        max_episodes=1000,
        max_tool_calls=500,
        max_compute_units=500.0,
        max_tool_calls_per_episode=100,
        max_compute_units_per_episode=100.0,
    )
    if args.backend == "model":
        try:
            missing = _missing_model_configuration(args)
            if missing:
                raise ModelProviderError(
                    "missing required variables: " + ", ".join(missing)
                )
            backend = ModelBackend(
                _provider_from_arguments(args),
                ledger=ledger,
                budget=budget,
                role_providers={
                    Role.CURATOR: _provider_from_arguments(args, role=Role.CURATOR)
                },
            )
        except (ModelProviderError, ValueError) as error:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": f"model backend configuration failed: {error}",
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
    else:
        backend = ScriptedRepositoryBackend(args.scripted_variant)
    try:
        acceptance_specifications = _load_acceptance_specifications(
            args.acceptance_spec
        )
        repository = Path(args.repository).resolve()
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else repository.parent / f"{repository.name}-hive-mind-delivery"
        )
        mission = RepositoryMission(
            repository,
            args.objective,
            acceptance_criteria=tuple(args.criterion),
            acceptance_specifications=acceptance_specifications,
            backend=backend,
            pin=args.pin,
            output_dir=output_dir,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            budget=budget,
            ledger=ledger,
            mission_store=state_store,
        )
        report = await mission.run()
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    stream = sys.stdout if report.status.value == "succeeded" else sys.stderr
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        file=stream,
    )
    return 0 if report.status.value == "succeeded" else 1


async def _run_demo(args: argparse.Namespace) -> int:
    """Run the one deterministic fixture repair and print a human-readable result."""

    output_dir = Path(args.output).resolve()
    if output_dir.exists():
        print(
            f"demo output directory already exists: {output_dir}",
            file=sys.stderr,
        )
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="hive-mind-demo-") as temporary:
            fixture = build_fixture_repo(Path(temporary))
            report = await RepositoryMission(
                fixture.root,
                "Repair the known fixture regression",
                acceptance_criteria=("The fixture regression test passes",),
                acceptance_specifications=(
                    AcceptanceSpecification(
                        "fixture-regression",
                        "The fixture regression test passes",
                        (
                            sys.executable,
                            "-B",
                            "-c",
                            "from tiny_pkg.maths import increment; assert increment(1) == 2",
                        ),
                        declared_paths=("tiny_pkg/maths.py",),
                    ),
                ),
                backend=ScriptedRepositoryBackend(),
                pin=fixture.commit_two,
                output_dir=output_dir,
                policy=PolicyEngine(AutonomyLevel.REPOSITORY),
                budget=AutonomyBudget(
                    max_episodes=1000,
                    max_tool_calls=500,
                    max_compute_units=500.0,
                    max_tool_calls_per_episode=100,
                    max_compute_units_per_episode=100.0,
                ),
                ledger=EvidenceLedger(":memory:"),
            ).run()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"demo failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    if report.status.value != "succeeded":
        print("demo failed before publishing a receipt bundle", file=sys.stderr)
        return 1

    output_label = "./demo-out" if args.output == "demo-out" else str(Path(args.output))
    print("Fixture regression repaired with the deterministic offline demo backend.")
    print("Curator re-ran the sealed checks in a separate local workspace.")
    print(f"Receipt bundle: {output_label}")
    print(
        "Try the same limited fixture backend: hive-mind deliver "
        "--repository <path> --backend fixture-demo --objective <objective> "
        "--criterion <criterion> --output-dir <bundle-dir>"
    )
    print(
        "fixture-demo only edits the bundled fixture layout; it does not inspect or repair arbitrary repositories."
    )
    return 0


def _provider_from_arguments(
    args: argparse.Namespace,
    *,
    role: Role | None = None,
):
    """Build one provider while letting non-secret CLI flags override the environment."""

    overrides = {
        "HIVE_MIND_MODEL_PROVIDER": args.provider,
        "HIVE_MIND_MODEL_BASE_URL": args.base_url,
        "HIVE_MIND_MODEL_MODEL": args.model,
    }
    prior: dict[str, str | None] = {}
    for name, value in overrides.items():
        if value is None:
            continue
        scoped = f"{name}__{role.value.upper()}" if role is not None else name
        prior[scoped] = os.environ.get(scoped)
        os.environ[scoped] = value
    try:
        return provider_from_env(role=role)
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _missing_model_configuration(args: argparse.Namespace) -> tuple[str, ...]:
    """List every absent model input before constructing the provider adapters."""

    missing: list[str] = []
    defaults = {
        "openai_compatible": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    for role in (None, Role.CURATOR):
        suffix = "" if role is None else f"__{role.value.upper()}"

        def configured(name: str) -> str | None:
            if role is not None:
                scoped = os.environ.get(f"{name}{suffix}")
                if scoped is not None:
                    return scoped
            return os.environ.get(name)

        provider = args.provider or configured("HIVE_MIND_MODEL_PROVIDER") or "openai_compatible"
        if provider not in defaults:
            continue
        model = args.model or configured("HIVE_MIND_MODEL_MODEL") or configured(
            "HIVE_MIND_MODEL_ID"
        )
        if not model or not model.strip():
            name = "HIVE_MIND_MODEL_MODEL (or HIVE_MIND_MODEL_ID)"
            if name not in missing:
                missing.append(name)
        api_key_env = configured("HIVE_MIND_MODEL_API_KEY_ENV") or defaults[provider]
        if not os.environ.get(api_key_env) and api_key_env not in missing:
            missing.append(api_key_env)
    return tuple(missing)


def _load_acceptance_specifications(
    paths: Sequence[str],
) -> tuple[AcceptanceSpecification, ...]:
    specifications: list[AcceptanceSpecification] = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"cannot read {path}: {type(error).__name__}: {error}"
            ) from None
        if not isinstance(document, dict):
            raise ValueError(f"{path}: acceptance specification must be a JSON object")
        try:
            specifications.append(AcceptanceSpecification.from_dict(document))
        except AcceptanceSpecificationError as error:
            raise ValueError(f"{path}: {error}") from None
    try:
        return normalize_acceptance_specifications(specifications)
    except AcceptanceSpecificationError as error:
        raise ValueError(str(error)) from None


async def _run_resume(args: argparse.Namespace) -> int:
    store = MissionStore(args.state_dir)
    try:
        report = await resume_mission(store, args.mission_id)
    except ReconciliationError as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(error),
                    "reconciliation": error.report,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except (MissionStoreError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        store.close()
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.status.value == "succeeded" else 1


def _run_missions(args: argparse.Namespace) -> int:
    store = MissionStore(args.state_dir)
    try:
        inventory = store.list_missions()
    finally:
        store.close()
    print(
        json.dumps(
            {"missions": inventory},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_benchmark(args: argparse.Namespace) -> int:
    lanes = tuple(part.strip() for part in args.lanes.split(",") if part.strip())
    try:
        report = BenchmarkHarness().run(
            args.output,
            repetitions=args.repetitions,
            seed=args.seed,
            lane_names=lanes,
            task_ids=tuple(args.task) or None,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_pit_episode(args: argparse.Namespace) -> int:
    repository = Path(args.repository).resolve()
    self_history = False
    pins_path = repository / "tests" / "fixtures" / "self_history_pins.json"
    try:
        pins_document = json.loads(pins_path.read_text(encoding="utf-8"))
        pins = pins_document.get("shas", [])
        self_history = isinstance(pins, list) and args.target in pins
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    oracle: PointInTimeOracle | None = None
    try:
        oracle = PointInTimeOracle(repository, args.state_dir)
        record_path = oracle.run_scripted_episode(
            args.target,
            self_history=self_history,
        )
    except (LeakageError, OSError, RuntimeError, SealViolation, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if oracle is not None:
            oracle.close()
    print(
        json.dumps(
            {
                "status": "succeeded",
                "episode_record": str(record_path),
            },
            indent=2,
        )
    )
    return 0


def _run_experiment(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            {"status": "failed", "error": EVALUATION_SURFACE_UNAVAILABLE},
            indent=2,
        ),
        file=sys.stderr,
    )
    return 1


def _run_verify(args: argparse.Namespace) -> int:
    try:
        report = verify_repository(
            args.repository,
            args.spec,
            args.output,
            args.candidate,
        )
    except (OSError, ValueError, VerificationError) as error:
        print(
            json.dumps({"status": "failed", "error": str(error)}, indent=2),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": report.verdict,
                "report": str(report.report_path),
                "changed_paths": list(report.changed_paths),
                "undeclared_paths": list(report.undeclared_paths),
                "weakened_tests": list(report.weakened_tests),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.verdict == "adopt" else 1


def _run_enqueue(args: argparse.Namespace) -> int:
    repository = Path(args.repository).resolve()
    if not repository.is_dir():
        raise SystemExit("repository must be an existing directory")
    try:
        pin = resolve_repository_pin(repository, args.pin)
    except ValueError as error:
        raise SystemExit(f"repository pin is invalid: {error}") from None
    try:
        acceptance_specifications = _load_acceptance_specifications(
            args.acceptance_spec
        )
    except ValueError as error:
        raise SystemExit(f"acceptance specification is invalid: {error}") from None
    declared_criteria = tuple(args.criterion)
    specification_criteria = tuple(
        item.criterion for item in acceptance_specifications
    )
    if not acceptance_specifications:
        raise SystemExit(
            "queued repository missions require at least one typed executable "
            "acceptance specification"
        )
    if declared_criteria and (
        len(declared_criteria) != len(set(declared_criteria))
        or set(declared_criteria) != set(specification_criteria)
    ):
        raise SystemExit(
            "acceptance criteria must exactly match the typed specification set"
        )
    semantic_payload = {
        "repository": str(repository),
        "objective": args.objective,
        "acceptance_criteria": list(specification_criteria),
        "acceptance_specifications": [
            item.to_dict() for item in acceptance_specifications
        ],
        "backend": args.backend,
        "scripted_variant": "good",
        "pin": pin,
    }
    encoded = json.dumps(
        semantic_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    mission_id = f"M-{sha256(encoded).hexdigest()[:32]}"
    scheduler = Scheduler(args.state_dir)
    try:
        job = scheduler.enqueue(
            "repository-mission",
            {
                "mission_id": mission_id,
                **semantic_payload,
            },
            max_attempts=args.max_attempts,
            mission_id=mission_id,
        )
    finally:
        scheduler.close()
    if getattr(args, "compatibility_mode", "kernel-v1") == "kernel-v1":
        record_legacy_enqueue(
            job,
            legacy_state_dir=args.state_dir,
            kernel_state_dir=getattr(args, "kernel_state_dir", None),
        )
    print(
        json.dumps(
            {
                "status": "enqueued",
                "job_id": job.id,
                "mission_id": mission_id,
                "deduplication_digest": job.payload_digest,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    try:
        return serve(
            args.state_dir,
            worker_count=args.workers,
            once=args.once,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


def _run_status(args: argparse.Namespace) -> int:
    model = build_projection(args.state_dir)
    if args.html:
        output = write_projection_html(model, args.html)
        print(json.dumps({"status": "written", "html": str(output)}, indent=2))
    else:
        print(projection_json(model), end="")
    return 0


def _read_packet_json(path: str) -> dict[str, object]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContinuationPacketError(
            f"packet JSON could not be read: {type(error).__name__}"
        ) from None
    if not isinstance(document, dict):
        raise ContinuationPacketError("packet JSON must be an object")
    return document


def _run_continuation(args: argparse.Namespace) -> int:
    try:
        if args.action == "export":
            packet = export_packet(_read_packet_json(args.input), args.repository)
            output = write_packet(packet, args.output, args.repository)
            print(
                json.dumps(
                    {
                        "status": "exported",
                        "packet": str(output),
                        "canonical_digest": packet["integrity"]["canonical_digest"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        packet = _read_packet_json(args.packet)
        validation = validate_packet(packet, args.repository)
        print(
            json.dumps(
                {"status": "valid" if validation.valid else "rejected", "issues": list(validation.issues)},
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if validation.valid else 1
    except ContinuationPacketError as error:
        print(json.dumps({"status": "rejected", "error": str(error)}, indent=2), file=sys.stderr)
        return 1


def _run_autonomous(args: argparse.Namespace) -> int:
    try:
        with AutonomousBrain(args.state_dir) as brain:
            if args.action == "kickoff":
                contract = brain.start_run(
                    args.repository,
                    args.prompt,
                    args.host,
                    run_id=args.run_id,
                    allow_remote_push=args.allow_remote_push,
                    allow_pr_comments=args.allow_pr_comments,
                )
                print(json.dumps({"status": "prepared", "run": contract}, indent=2, sort_keys=True))
                return 0
            if args.action == "turn":
                result = brain.run_host_turn(args.run_id)
                print(
                    json.dumps(
                        {
                            "status": "completed" if result.returncode == 0 else "blocked",
                            "run_id": result.run_id,
                            "action": result.action,
                            "reply": result.reply,
                            "changed_paths": result.changed_paths,
                            "output_digest": result.output_digest,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0 if result.returncode == 0 else 1
            if args.action == "register-pr":
                brain.register_pull_request(args.run_id, args.number, args.url)
                print(json.dumps({"status": "registered", "run_id": args.run_id, "number": args.number}, indent=2))
                return 0
            if args.action == "open-draft-pr":
                result = brain.open_draft_pull_request(
                    args.run_id,
                    owner=args.owner,
                    repository=args.repository,
                    base=args.base,
                    title=args.title,
                    body=args.body,
                    gateway=GitHubRestCommentGateway(args.token_env),
                )
                print(json.dumps({"status": "opened", "run_id": args.run_id, "pull_request": result}, indent=2))
                return 0
            if args.action == "poll-pr":
                results = brain.handle_pull_request_feedback(
                    args.run_id,
                    owner=args.owner,
                    repository=args.repository,
                    gateway=GitHubRestCommentGateway(args.token_env),
                )
                print(
                    json.dumps(
                        {
                            "status": "processed",
                            "run_id": args.run_id,
                            "comment_count": len(results),
                            "actions": [result.action for result in results],
                        },
                        indent=2,
                    )
                )
                return 0
            if args.action == "push":
                head = brain.push_own_branch(args.run_id, remote=args.remote)
                print(json.dumps({"status": "pushed", "run_id": args.run_id, "head": head}, indent=2))
                return 0
            if args.action == "learn":
                records = brain.learn_from_human_outcome_with_host(
                    args.run_id, args.human_final_commit
                )
                print(
                    json.dumps(
                        {"status": "graded", "run_id": args.run_id, "iterations": list(records)},
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            if args.action == "supervise":
                feedback_requested = args.owner is not None or args.repository is not None
                if feedback_requested and (args.owner is None or args.repository is None):
                    raise AutonomousRunError("supervision owner and repository must be supplied together")
                result = brain.supervise(
                    args.run_id,
                    max_polls=args.polls,
                    poll_interval_seconds=args.interval_seconds,
                    owner=args.owner,
                    repository=args.repository,
                    gateway=(
                        GitHubRestCommentGateway(args.token_env)
                        if feedback_requested
                        else None
                    ),
                )
                print(json.dumps({"status": "supervised", **result}, indent=2, sort_keys=True))
                return 0
            if args.action == "requirements":
                print(
                    json.dumps(
                        {
                            "status": "sealed",
                            "run_id": args.run_id,
                            "requirements": brain.requirements(args.run_id),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            print(json.dumps({"status": "unknown-action"}, indent=2), file=sys.stderr)
            return 1
    except (AutonomousRunError, OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps({"status": "blocked", "error": f"{type(error).__name__}: {error}"}, indent=2),
            file=sys.stderr,
        )
        return 1


def _run_audit(args: argparse.Namespace, invocation: Sequence[str]) -> int:
    if bool(args.signing_key_file) != bool(args.signing_key_id):
        raise SystemExit("--signing-key-file and --signing-key-id must be supplied together")
    signing_key = Path(args.signing_key_file).read_bytes() if args.signing_key_file else None
    audit = collect_current_state_audit(
        args.repository,
        run_tests=not args.skip_tests,
        invocation=invocation,
    )
    artifact = create_audit_artifact(
        audit,
        signing_key=signing_key,
        signing_key_id=args.signing_key_id,
    )
    if args.output:
        write_audit_artifact(artifact, args.output)
        integrity = artifact.get("integrity")
        digest = integrity.get("digest") if isinstance(integrity, dict) else None
        print(
            json.dumps(
                {
                    "artifact": str(Path(args.output).resolve()),
                    "digest": digest,
                    "complete": audit["complete"],
                    "failures": audit["failures"],
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if audit["complete"] else 1


def _run_kernel_doctor(args: argparse.Namespace) -> int:
    report = inspect_kernel_environment(
        args.repository,
        state_dir=args.state_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_kernel_status(args: argparse.Namespace) -> int:
    database = KernelStore.database_path(args.state_dir)
    if not database.is_file():
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"kernel state database does not exist: {database}",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    try:
        store = KernelStore(database, read_only=True)
        try:
            report = store.status(args.mission_id)
        finally:
            store.close()
    except (KernelIntegrityError, OSError, sqlite3.Error, KeyError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['mission_id']}: {report['status']} "
            f"(sequence {report['last_sequence']}, {len(report['work'])} work items)"
        )
    return 0


def _load_kernel_charter(path: str, mission_id: str) -> MissionCharter:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    charter = cast(MissionCharter, MissionCharter.from_document(document))
    if charter.mission_id != mission_id:
        raise ValueError("charter mission_id does not match command mission_id")
    return charter


def _kernel_database_or_error(state_dir: str) -> Path:
    database = KernelStore.database_path(state_dir)
    if not database.is_file():
        raise FileNotFoundError(f"kernel state database does not exist: {database}")
    return database


def _run_kernel_plan(args: argparse.Namespace) -> int:
    try:
        charter = _load_kernel_charter(args.charter, args.mission_id)
        store = KernelStore(_kernel_database_or_error(args.state_dir))
        try:
            if args.mission_id not in store.projection()["missions"]:
                raise KeyError(f"unknown kernel mission: {args.mission_id}")
            plan = DeterministicFixturePlanner().plan(charter, args.fixture)
            sequences = persist_plan(store, plan)
        finally:
            store.close()
    except (FileNotFoundError, KernelIntegrityError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    report = {"mission_id": args.mission_id, "plan_digest": plan.digest, "sequences": sequences}
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else plan.digest)
    return 0


def _run_kernel_graph(args: argparse.Namespace) -> int:
    try:
        charter = _load_kernel_charter(args.charter, args.mission_id)
        store = KernelStore(_kernel_database_or_error(args.state_dir), read_only=True)
        try:
            graph = graph_from_events(charter, store.events())
        finally:
            store.close()
    except (FileNotFoundError, KernelIntegrityError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    report = {
        "mission_id": args.mission_id,
        "graph_digest": graph.digest,
        "ready_work_ids": [item.work_id for item in graph.ready_items()],
        "work_items": [item.to_document() for item in graph.ordered_items()],
    }
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else graph.digest)
    return 0


def _run_kernel_closeout(args: argparse.Namespace) -> int:
    from .brain_kernel.closeout import TechnicalCloseoutError, derive_technical_closeout

    try:
        directories: dict[str, str] = {}
        for value in args.bundle_ref:
            reference, separator, directory = value.partition("=")
            if not separator or not reference or not directory or reference in directories:
                raise ValueError("bundle references must use unique REFERENCE=PATH values")
            directories[reference] = directory
        store = KernelStore(_kernel_database_or_error(args.state_dir), read_only=True)
        try:
            report = derive_technical_closeout(
                store, args.mission_id, bundle_directories=directories
            )
        finally:
            store.close()
    except (FileNotFoundError, KernelIntegrityError, TechnicalCloseoutError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    document = report.to_document()
    print(json.dumps(document, indent=2, sort_keys=True) if args.json_output else f"{report.mission_id}: {report.state}")
    return 0


def _memory_catalog(args: argparse.Namespace):
    return MemoryCatalogStore(args.state_dir).restore(args.snapshot)


def _run_kernel_memory_search(args: argparse.Namespace) -> int:
    try:
        catalog = _memory_catalog(args)
        request = RetrievalRequest(
            args.mission, args.work, args.role, args.query, args.now,
            tuple(args.data_scope), repository_key=args.repository_key,
            sensitivity_scopes=tuple(args.sensitivity_scope),
            required_sensitivities=tuple(args.require_sensitivity),
        )
        ranked = catalog.rank(request)
    except (KeyError, MemoryDenied, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    report = {
        "snapshot": args.snapshot,
        "records": [
            {"record": item.entry.record.to_document(), "score": item.score, "terms": asdict(item.terms)}
            for item in ranked
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else "\n".join(item.entry.record.record_id for item in ranked))
    return 0


def _run_kernel_memory_inspect(args: argparse.Namespace) -> int:
    try:
        entry, state = _memory_catalog(args).inspect(args.record_id)
    except (KeyError, MemoryDenied, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    report = {
        "record": entry.record.to_document(),
        "access": {"roles": entry.access.roles, "data_scopes": entry.access.data_scopes, "evaluator_visible": entry.access.evaluator_visible},
        "derived_state": state.value,
    }
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else f"{entry.record.record_id}: {state.value}")
    return 0


def _run_kernel_memory_expire(args: argparse.Namespace) -> int:
    try:
        store = MemoryCatalogStore(args.state_dir)
        catalog = store.restore(args.snapshot)
        events = catalog.expire(now=args.now)
        successor = store.persist(catalog)
    except (KeyError, MemoryDenied, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    report = {"snapshot": successor, "expired_record_ids": [event.record_id for event in events]}
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else successor)
    return 0


def _run_kernel_context(args: argparse.Namespace) -> int:
    try:
        manifests = ContextManifestStore(args.state_dir)
        manifests.restore()
        manifest = manifests.get(args.manifest)
    except (KeyError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(manifest.to_document(), indent=2, sort_keys=True) if args.json_output else manifest.manifest_digest)
    return 0


def _run_ingest(args: argparse.Namespace) -> int:
    supplied_file = Path(args.file)
    try:
        source_ids = {source.id for source in load_source_docket(Path.cwd()).sources}
        if args.source not in source_ids:
            raise ValueError(f"unknown source: {args.source}")
        exhibit = register_exhibit(
            ExhibitStore(args.evidence_root),
            args.source,
            supplied_file.read_bytes(),
            original_filename=supplied_file.name,
            media_type=args.media_type,
            capturer_id=args.capturer,
            supply_method=args.supply_method,
            locator=args.locator,
            license=args.license,
            parent_exhibit_digest=args.parent_digest,
            expected_digest=args.expected_digest,
        )
    except (OSError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(exhibit.to_record(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_defer(args: argparse.Namespace) -> int:
    try:
        docket = load_source_docket(Path.cwd())
        source_map = {source.id: source for source in docket.sources}
        unknown = sorted(set(args.source) - set(source_map))
        if unknown:
            raise ValueError("unknown source(s): " + ", ".join(unknown))
        obligation = args.obligation or "DEFER-" + "-".join(args.source)
        result = defer_obligation(
            ExhibitStore(args.evidence_root),
            obligation,
            tuple(source_map[source_id] for source_id in args.source),
            reason=args.reason,
            review_by=args.review_by,
            participants=CaseParticipants(
                args.advocate,
                args.cross_examiner,
                (args.judge,),
            ),
        )
    except (OSError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "deferred",
                "obligation_id": result.obligation_id,
                "source_ids": list(result.source_ids),
                "review_by": result.review_by,
                "record": result.record_path.as_posix(),
                "verdict": result.verdict.disposition.value,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "autopilot":
        args = build_autopilot_parser().parse_args(arguments[1:])
        raise SystemExit(_run_autopilot(args))
    if arguments and arguments[0] == "kernel":
        args = build_kernel_parser().parse_args(arguments[1:])
        if args.kernel_command == "doctor":
            raise SystemExit(_run_kernel_doctor(args))
        if args.kernel_command == "status":
            raise SystemExit(_run_kernel_status(args))
        if args.kernel_command == "plan":
            raise SystemExit(_run_kernel_plan(args))
        if args.kernel_command == "graph":
            raise SystemExit(_run_kernel_graph(args))
        if args.kernel_command == "closeout":
            raise SystemExit(_run_kernel_closeout(args))
        if args.kernel_command == "memory":
            if args.memory_command == "search":
                raise SystemExit(_run_kernel_memory_search(args))
            if args.memory_command == "inspect":
                raise SystemExit(_run_kernel_memory_inspect(args))
            raise SystemExit(_run_kernel_memory_expire(args))
        if args.kernel_command == "context":
            raise SystemExit(_run_kernel_context(args))
    if arguments and arguments[0] == "audit":
        args = build_audit_parser().parse_args(arguments[1:])
        raise SystemExit(_run_audit(args, ("hive-mind", *arguments)))
    if arguments and arguments[0] == "deliver":
        args = build_deliver_parser().parse_args(arguments[1:])
        raise SystemExit(asyncio.run(_run_deliver(args)))
    if arguments and arguments[0] == "demo":
        args = build_demo_parser().parse_args(arguments[1:])
        raise SystemExit(asyncio.run(_run_demo(args)))
    if arguments and arguments[0] == "resume":
        args = build_resume_parser().parse_args(arguments[1:])
        raise SystemExit(asyncio.run(_run_resume(args)))
    if arguments and arguments[0] == "missions":
        args = build_missions_parser().parse_args(arguments[1:])
        raise SystemExit(_run_missions(args))
    if arguments and arguments[0] == "benchmark":
        args = build_benchmark_parser().parse_args(arguments[1:])
        raise SystemExit(_run_benchmark(args))
    if arguments and arguments[0] == "ingest":
        args = build_ingest_parser().parse_args(arguments[1:])
        raise SystemExit(_run_ingest(args))
    if arguments and arguments[0] == "defer":
        args = build_defer_parser().parse_args(arguments[1:])
        raise SystemExit(_run_defer(args))
    if arguments and arguments[0] == "pit-episode":
        args = build_pit_episode_parser().parse_args(arguments[1:])
        raise SystemExit(_run_pit_episode(args))
    if arguments and arguments[0] == "experiment":
        args = build_experiment_parser().parse_args(arguments[1:])
        raise SystemExit(_run_experiment(args))
    if arguments and arguments[0] == "verify":
        args = build_verify_parser().parse_args(arguments[1:])
        raise SystemExit(_run_verify(args))
    if arguments and arguments[0] == "enqueue":
        args = build_enqueue_parser().parse_args(arguments[1:])
        raise SystemExit(_run_enqueue(args))
    if arguments and arguments[0] == "serve":
        args = build_serve_parser().parse_args(arguments[1:])
        raise SystemExit(_run_serve(args))
    if arguments and arguments[0] == "status":
        args = build_status_parser().parse_args(arguments[1:])
        raise SystemExit(_run_status(args))
    if arguments and arguments[0] == "continuation":
        args = build_continuation_parser().parse_args(arguments[1:])
        raise SystemExit(_run_continuation(args))
    if arguments and arguments[0] == "autonomous":
        args = build_autonomous_parser().parse_args(arguments[1:])
        raise SystemExit(_run_autonomous(args))
    args = build_parser().parse_args(arguments)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
