from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Sequence

from .acceptance import (
    AcceptanceSpecification,
    AcceptanceSpecificationError,
    normalize_acceptance_specifications,
)
from .autonomy import AutonomyBudget
from .benchmark_harness import BenchmarkHarness
from .courtroom import CaseParticipants
from .current_state_audit import (
    collect_current_state_audit,
    create_audit_artifact,
    write_audit_artifact,
)
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
from .prompt_registry import PromptRegistry
from .runtime import HiveKernel
from .scheduler import Scheduler
from .source_docket import load_source_docket
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
        choices=("scripted", "model"),
        default="scripted",
        help="Repository backend (default: deterministic offline scripted backend)",
    )
    parser.add_argument(
        "--provider",
        choices=("openai_compatible", "anthropic"),
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
    if arguments and arguments[0] == "audit":
        args = build_audit_parser().parse_args(arguments[1:])
        raise SystemExit(_run_audit(args, ("hive-mind", *arguments)))
    if arguments and arguments[0] == "deliver":
        args = build_deliver_parser().parse_args(arguments[1:])
        raise SystemExit(asyncio.run(_run_deliver(args)))
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
    if arguments and arguments[0] == "enqueue":
        args = build_enqueue_parser().parse_args(arguments[1:])
        raise SystemExit(_run_enqueue(args))
    if arguments and arguments[0] == "serve":
        args = build_serve_parser().parse_args(arguments[1:])
        raise SystemExit(_run_serve(args))
    if arguments and arguments[0] == "status":
        args = build_status_parser().parse_args(arguments[1:])
        raise SystemExit(_run_status(args))
    args = build_parser().parse_args(arguments)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
