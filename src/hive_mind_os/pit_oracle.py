"""Physically isolated point-in-time Git replay with sealed predictions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

from .autonomy import EpisodeAllowance
from .contracts import tool_intent_digest
from .ledger import EvidenceLedger
from .models import AutonomyLevel, Role, utc_now
from .policy import PolicyEngine
from .receipts import portable_path_parts, sha256_digest
from .repository_learning import (
    CommitState,
    RepositoryLearningCurriculum,
    RepositoryLearningEpisode,
)
from .sandbox import SandboxRunner, SandboxSpec

_FULL_SHA_LENGTH = 40
_SELF_HISTORY_CAVEAT = (
    "external-world and model-training-data cutoffs are not controlled; a learner may "
    "already know this public repository's future"
)
_SCOPE_CAVEATS = (
    "forge metadata such as issues, pull requests, and CI history is not replayed",
    "dependency versions and external documentation are not time-travelled",
)
_GIT_ENV_LOCK = threading.RLock()


class LeakageError(RuntimeError):
    """The point-in-time boundary could not be proven."""


class SealViolation(RuntimeError):
    """Reveal or grading was attempted without an intact prior seal."""


@dataclass(slots=True)
class PITEnvironment:
    episode_id: str
    root: Path
    target_sha: str
    target_tree_sha: str
    parent_shas: tuple[str, ...]
    ancestor_shas: tuple[str, ...]
    hidden_shas: tuple[str, ...]
    environment_digest: str
    environment_built_at: str
    contamination_caveats: tuple[str, ...]
    receipt_records: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SealedPrediction:
    episode_id: str
    target_position: int
    target_sha: str
    environment_digest: str
    learner_identity: str
    prediction_content: Mapping[str, Any]
    digest: str
    ledger_sequence: int

    def document(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "target_position": self.target_position,
            "target_sha": self.target_sha,
            "environment_digest": self.environment_digest,
            "learner_identity": self.learner_identity,
            "prediction_content": self.prediction_content,
        }


@dataclass(frozen=True, slots=True)
class EpisodeGrade:
    predicted_paths: tuple[str, ...]
    actual_paths: tuple[str, ...]
    overlap_paths: tuple[str, ...]
    score: float
    ledger_sequence: int


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonical JSON") from error


def _prediction_digest(document: Mapping[str, Any]) -> str:
    return f"sha256:{sha256(_canonical_bytes(document)).hexdigest()}"


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("append-only episode record already exists")
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, path)
    except FileExistsError:
        raise FileExistsError(
            "append-only episode record appeared during publication"
        ) from None
    finally:
        temporary.unlink(missing_ok=True)


def _checked_repository(path: str | Path) -> Path:
    repository = Path(path).resolve()
    if not repository.is_dir():
        raise ValueError("repository must be an existing local directory")
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--git-dir"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("repository must be a local Git worktree")
    return repository


@contextmanager
def _isolated_git_environment(config_path: Path) -> Iterator[None]:
    values = {
        "GIT_CONFIG_GLOBAL": str(config_path),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    with _GIT_ENV_LOCK:
        previous = {name: os.environ.get(name) for name in values}
        os.environ.update(values)
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _read_history(repository: Path, rev: str = "HEAD") -> tuple[CommitState, ...]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "rev-list",
            "--topo-order",
            "--reverse",
            "--parents",
            rev,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.decode("utf-8", "replace").strip())
    states: list[CommitState] = []
    for line in completed.stdout.decode("ascii", "strict").splitlines():
        sha_value, *parents = line.split()
        tree = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", f"{sha_value}^{{tree}}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
        if tree.returncode != 0:
            raise ValueError("failed to resolve a curriculum tree")
        states.append(
            CommitState(
                sha_value,
                tree.stdout.decode("ascii", "strict").strip(),
                tuple(parents),
            )
        )
    return tuple(states)


def build_self_curriculum(
    repo_path: str | Path,
    first_n: int,
) -> RepositoryLearningCurriculum:
    """Build and verify the repository's committed, earliest-commit curriculum."""

    if first_n < 1:
        raise ValueError("first_n must be positive")
    repository = _checked_repository(repo_path)
    pins_path = repository / "tests" / "fixtures" / "self_history_pins.json"
    try:
        pins_document = json.loads(pins_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("self-history pins are unavailable or invalid") from error
    pins = pins_document.get("shas") if isinstance(pins_document, dict) else None
    if not isinstance(pins, list) or len(pins) < first_n or not all(
        isinstance(item, str) for item in pins
    ):
        raise ValueError("self-history pins do not cover first_n commits")
    observed = _read_history(repository)
    observed_shas = tuple(state.sha for state in observed[:first_n])
    selected_pins = tuple(pins[:first_n])
    if observed_shas != selected_pins:
        raise LeakageError("self-history pins do not match the repository's earliest commits")
    by_sha = {state.sha: state for state in observed}
    return RepositoryLearningCurriculum(by_sha[item] for item in selected_pins)


class PointInTimeOracle:
    """Construct and police ancestor-only learner environments."""

    def __init__(
        self,
        repository: str | Path,
        state_dir: str | Path | None = None,
        *,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.repository = _checked_repository(repository)
        default_state = self.repository.parent / f".{self.repository.name}-pit-state"
        self.state_dir = Path(state_dir or default_state).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.receipt_root = self.state_dir / "sandbox-evidence"
        self.receipt_root.mkdir(parents=True, exist_ok=True)
        self.hooks_root = self.state_dir / "disabled-hooks"
        self.hooks_root.mkdir(parents=True, exist_ok=True)
        self.git_config = self.state_dir / "isolated-gitconfig"
        if not self.git_config.exists():
            self.git_config.write_bytes(b"")
        self._owns_ledger = ledger is None
        self.ledger = ledger or EvidenceLedger(self.state_dir / "evidence-ledger.sqlite3")
        self._seals: dict[str, SealedPrediction] = {}
        self._reveal_digests: dict[str, str] = {}
        self._git_name = Path(shutil.which("git") or "git").name

    def close(self) -> None:
        if self._owns_ledger:
            self.ledger.close()

    @contextmanager
    def _source_session(
        self,
        episode_id: str,
        records: list[dict[str, Any]],
    ) -> Iterator[tuple[Path, SandboxRunner]]:
        with tempfile.TemporaryDirectory(prefix="hive-pit-source-") as directory:
            root = Path(directory)
            # The oracle's configured source is trusted input, but the sandboxed
            # Git process may only receive paths beneath its own root.  Stage a
            # byte-for-byte local copy first rather than handing Git an absolute
            # path outside the process sandbox.
            shutil.copytree(self.repository, root / "source", symlinks=True)
            runner = self._runner(root, tool_calls=400)
            self._command(
                runner,
                [
                    "git",
                    "clone",
                    "--mirror",
                    "--no-hardlinks",
                    "source",
                    "source.git",
                ],
                episode_id,
                "clone trusted source into isolated oracle staging",
                records,
            )
            yield root, runner

    def _runner(self, root: Path, *, tool_calls: int = 200) -> SandboxRunner:
        return SandboxRunner(
            SandboxSpec(
                root,
                argv_allowlist=(self._git_name, Path(sys.executable).name),
                # PIT verification uses a fixed, receipt-bound Python probe to
                # inspect its isolated learner environment.  Interpreter flags
                # stay denied for the default sandbox and are opted into only by
                # this bounded oracle runner.
                allow_interpreter_flags=True,
                env_allowlist=(
                    "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_NOSYSTEM",
                    "GIT_TERMINAL_PROMPT",
                ),
                timeout_s=120.0,
                max_output_bytes=20_000_000,
            ),
            self.receipt_root,
            EpisodeAllowance(tool_calls, float(tool_calls)),
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            role=Role.OPTIMIZER,
            runner_identity="pit-oracle-sandbox-v1",
            ledger=self.ledger,
        )

    def _command(
        self,
        runner: SandboxRunner,
        argv: Sequence[str],
        episode_id: str,
        description: str,
        records: list[dict[str, Any]],
        *,
        allow_failure: bool = False,
    ) -> tuple[dict[str, Any], bytes, bytes]:
        effective_argv = list(argv)
        if Path(effective_argv[0]).name.casefold().removesuffix(".exe") == "git":
            effective_argv = [
                effective_argv[0],
                "-c",
                f"core.hooksPath={self.hooks_root}",
                "-c",
                "core.autocrlf=false",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.fsmonitor=false",
                *effective_argv[1:],
            ]
        intent: dict[str, Any] = {
            "schema_version": 1,
            "action_id": f"ACT-pit-{uuid4()}",
            "mission_id": episode_id,
            "state_ref": f"PIT_EPISODE:{episode_id}",
            "actor_id": Role.OPTIMIZER.value,
            "kind": "command",
            "description": description,
            "action_digest": f"sha256:{'0' * 64}",
            "policy_decision_ref": f"POLICY-pit-{uuid4()}",
            "lease_id": f"LEASE-pit-{uuid4()}",
            "idempotency_key": f"IDEMPOTENCY-pit-{uuid4()}",
            "rollback_ref": None,
            "command": {"argv": effective_argv, "path_args": []},
            "status": "proposed",
        }
        intent["action_digest"] = tool_intent_digest(intent)
        with _isolated_git_environment(self.git_config):
            receipt = runner.run(intent)
        reference = runner.last_reference
        if reference is None:
            raise LeakageError("sandbox command produced no receipt reference")
        record = {
            "path": reference.path,
            "digest": reference.digest,
            "mission_id": receipt["mission_id"],
            "state_ref": receipt["state_ref"],
            "actor_id": receipt["actor_id"],
            "action_id": receipt["action_id"],
            "action_kind": receipt["action_kind"],
            "action_digest": receipt["action_digest"],
            "result": receipt["result"],
            "description": description,
        }
        records.append(record)
        artifacts: dict[str, bytes] = {}
        for artifact in receipt["artifacts"]:
            relative = Path(*portable_path_parts(artifact["path"]))
            artifacts[artifact["artifact_id"]] = (self.receipt_root / relative).read_bytes()
        stdout = artifacts.get("stdout", b"")
        stderr = artifacts.get("stderr", b"")
        if receipt["execution"]["stdout"]["truncated"]:
            raise LeakageError(f"{description} exceeded the output limit")
        if receipt["result"] != "succeeded" and not allow_failure:
            raise LeakageError(
                f"{description} failed: {stderr.decode('utf-8', 'replace').strip()}"
            )
        return receipt, stdout, stderr

    @staticmethod
    def _lines(content: bytes) -> tuple[str, ...]:
        return tuple(
            line for line in content.decode("ascii", "strict").splitlines() if line
        )

    def build_environment(
        self,
        target_sha: str,
        *,
        self_history: bool = False,
    ) -> PITEnvironment:
        target = target_sha.lower()
        if len(target) != _FULL_SHA_LENGTH or any(
            character not in "0123456789abcdef" for character in target
        ):
            raise ValueError("target must be a full 40-hex commit SHA")
        episode_id = f"PIT-{uuid4()}"
        records: list[dict[str, Any]] = []
        stable_root = self.state_dir / "environments" / episode_id
        if stable_root.exists():
            raise LeakageError("episode environment path already exists")

        with self._source_session(episode_id, records) as (build_root, runner):
            _, target_line, _ = self._command(
                runner,
                ["git", "--git-dir", "source.git", "rev-list", "--parents", "-n", "1", target],
                episode_id,
                "resolve target and parent commits",
                records,
            )
            target_parts = target_line.decode("ascii", "strict").strip().split()
            if not target_parts or target_parts[0] != target:
                raise LeakageError("target commit is not available in the trusted source")
            parents = tuple(target_parts[1:])
            _, tree_output, _ = self._command(
                runner,
                ["git", "--git-dir", "source.git", "rev-parse", f"{target}^{{tree}}"],
                episode_id,
                "resolve target tree",
                records,
            )
            target_tree = tree_output.decode("ascii", "strict").strip()
            _, all_output, _ = self._command(
                runner,
                [
                    "git",
                    "--git-dir",
                    "source.git",
                    "rev-list",
                    "--topo-order",
                    "--reverse",
                    "--all",
                ],
                episode_id,
                "enumerate trusted source commits",
                records,
            )
            all_shas = self._lines(all_output)
            if target not in all_shas:
                raise LeakageError("target is not reachable from a trusted source ref")
            ancestors: tuple[str, ...] = ()
            if parents:
                _, ancestor_output, _ = self._command(
                    runner,
                    [
                        "git",
                        "--git-dir",
                        "source.git",
                        "rev-list",
                        "--topo-order",
                        "--reverse",
                        *parents,
                    ],
                    episode_id,
                    "enumerate exact target-parent ancestor closure",
                    records,
                )
                ancestors = self._lines(ancestor_output)
            hidden = tuple(item for item in all_shas if item not in set(ancestors))

            if parents:
                refs: list[str] = []
                for index, parent in enumerate(parents):
                    ref = f"refs/heads/pit-parent-{index}"
                    refs.append(ref)
                    self._command(
                        runner,
                        ["git", "--git-dir", "source.git", "update-ref", ref, parent],
                        episode_id,
                        "pin one target parent for ancestor bundle export",
                        records,
                    )
                self._command(
                    runner,
                    [
                        "git",
                        "--git-dir",
                        "source.git",
                        "bundle",
                        "create",
                        "ancestor.bundle",
                        *refs,
                    ],
                    episode_id,
                    "export exact ancestor closure bundle",
                    records,
                )
                self._command(
                    runner,
                    ["git", "init", "--initial-branch=pit-base", "environment"],
                    episode_id,
                    "initialize empty learner repository",
                    records,
                )
                # `git -C environment fetch ../ancestor.bundle` would cross the
                # sandbox boundary at the command layer.  Place the generated
                # bundle in the learner workspace instead, then remove it before
                # that workspace becomes an observable learner environment.
                bundle_in_environment = build_root / "environment" / "ancestor.bundle"
                shutil.copyfile(build_root / "ancestor.bundle", bundle_in_environment)
                fetch_specs = [
                    f"{ref}:{ref}"
                    for ref in refs
                ]
                self._command(
                    runner,
                    [
                        "git",
                        "-C",
                        "environment",
                        "fetch",
                        "ancestor.bundle",
                        *fetch_specs,
                    ],
                    episode_id,
                    "import ancestor closure into learner repository",
                    records,
                )
                bundle_in_environment.unlink()
                self._command(
                    runner,
                    ["git", "-C", "environment", "checkout", "--detach", parents[0]],
                    episode_id,
                    "materialize observable parent state",
                    records,
                )
            else:
                self._command(
                    runner,
                    ["git", "init", "--initial-branch=pit-base", "environment"],
                    episode_id,
                    "initialize root-target learner repository",
                    records,
                )
            stable_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(build_root / "environment"), stable_root)

        caveats = _SCOPE_CAVEATS + ((_SELF_HISTORY_CAVEAT,) if self_history else ())
        digest_document = {
            "target_sha": target,
            "target_tree_sha": target_tree,
            "parent_shas": parents,
            "ancestor_shas": ancestors,
        }
        environment = PITEnvironment(
            episode_id=episode_id,
            root=stable_root,
            target_sha=target,
            target_tree_sha=target_tree,
            parent_shas=parents,
            ancestor_shas=ancestors,
            hidden_shas=hidden,
            environment_digest=sha256_digest(_canonical_bytes(digest_document)),
            environment_built_at=utc_now(),
            contamination_caveats=caveats,
            receipt_records=records,
        )
        self.verify_environment(environment)
        self.ledger.append_event(
            episode_id,
            "pit.environment.verified",
            Role.OPTIMIZER.value,
            {
                "environment_digest": environment.environment_digest,
                "ancestor_count": len(ancestors),
                "hidden_count": len(hidden),
            },
        )
        return environment

    def _environment_command(
        self,
        environment: PITEnvironment,
        args: Sequence[str],
        description: str,
        *,
        allow_failure: bool = False,
    ) -> tuple[dict[str, Any], bytes, bytes]:
        runner = self._runner(environment.root)
        return self._command(
            runner,
            ["git", *args],
            environment.episode_id,
            description,
            environment.receipt_records,
            allow_failure=allow_failure,
        )

    def verify_environment(self, environment: PITEnvironment) -> None:
        _, observed_output, _ = self._environment_command(
            environment,
            ["rev-list", "--topo-order", "--reverse", "--all"],
            "verify learner ancestor set",
        )
        observed = self._lines(observed_output)
        if set(observed) != set(environment.ancestor_shas):
            raise LeakageError("learner repository commit set differs from ancestor closure")
        probes = (
            (environment.target_sha, "target commit"),
            (environment.target_tree_sha, "target tree"),
            *((sha_value, "hidden commit") for sha_value in environment.hidden_shas),
        )
        unique_probes = tuple(dict.fromkeys(object_id for object_id, _ in probes))
        found: list[str] = []
        for object_id in unique_probes:
            receipt, _, _ = self._environment_command(
                environment,
                ["cat-file", "-e", object_id],
                "prove physical absence of one target, tree, or hidden commit object",
                allow_failure=True,
            )
            if receipt["result"] == "succeeded":
                found.append(object_id)
        if found:
            raise LeakageError(
                "learner repository contains forbidden object(s): "
                + ", ".join(found)
            )

    def seal_prediction(
        self,
        environment: PITEnvironment,
        *,
        target_position: int,
        learner_identity: str,
        prediction_content: Mapping[str, Any],
    ) -> SealedPrediction:
        if not learner_identity.strip() or target_position < 0:
            raise ValueError("learner identity and non-negative target position are required")
        document = {
            "episode_id": environment.episode_id,
            "target_position": target_position,
            "target_sha": environment.target_sha,
            "environment_digest": environment.environment_digest,
            "learner_identity": learner_identity,
            "prediction_content": prediction_content,
        }
        digest = _prediction_digest(document)
        sequence = self.ledger.append_event(
            environment.episode_id,
            "pit.prediction.sealed",
            learner_identity,
            {"prediction_digest": digest, "target_sha": environment.target_sha},
        )
        sealed = SealedPrediction(
            environment.episode_id,
            target_position,
            environment.target_sha,
            environment.environment_digest,
            learner_identity,
            prediction_content,
            digest,
            sequence,
        )
        self._seals[environment.episode_id] = sealed
        return sealed

    def _require_intact_seal(
        self,
        environment: PITEnvironment,
        sealed: SealedPrediction | None,
    ) -> SealedPrediction:
        recorded = self._seals.get(environment.episode_id)
        if sealed is None or recorded is None:
            self.ledger.append_event(
                environment.episode_id,
                "pit.violation",
                Role.OPTIMIZER.value,
                {"kind": "reveal_without_seal"},
            )
            raise SealViolation("target reveal requires a recorded prediction seal")
        observed_digest = _prediction_digest(sealed.document())
        if (
            sealed.episode_id != environment.episode_id
            or sealed.target_sha != environment.target_sha
            or sealed.environment_digest != environment.environment_digest
            or observed_digest != sealed.digest
            or recorded.digest != sealed.digest
        ):
            self.ledger.append_event(
                environment.episode_id,
                "pit.violation",
                Role.OPTIMIZER.value,
                {"kind": "prediction_digest_mismatch"},
            )
            raise SealViolation("sealed prediction was altered or belongs to another episode")
        return sealed

    def reveal(
        self,
        environment: PITEnvironment,
        sealed: SealedPrediction | None = None,
    ) -> dict[str, Any]:
        intact = self._require_intact_seal(environment, sealed)
        with self._source_session(
            environment.episode_id,
            environment.receipt_records,
        ) as (_, runner):
            _, message_output, _ = self._command(
                runner,
                [
                    "git",
                    "--git-dir",
                    "source.git",
                    "show",
                    "-s",
                    "--format=%B",
                    environment.target_sha,
                ],
                environment.episode_id,
                "reveal sealed target message",
                environment.receipt_records,
            )
            _, paths_output, _ = self._command(
                runner,
                [
                    "git",
                    "--git-dir",
                    "source.git",
                    "diff-tree",
                    "-m",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    environment.target_sha,
                ],
                environment.episode_id,
                "reveal sealed target changed paths",
                environment.receipt_records,
            )
            _, diff_output, _ = self._command(
                runner,
                [
                    "git",
                    "--git-dir",
                    "source.git",
                    "show",
                    "--format=",
                    "--binary",
                    environment.target_sha,
                ],
                environment.episode_id,
                "reveal sealed target diff",
                environment.receipt_records,
            )
        reveal = {
            "target_sha": environment.target_sha,
            "message": message_output.decode("utf-8", "replace").strip(),
            "changed_paths": sorted(
                set(paths_output.decode("utf-8", "strict").splitlines())
            ),
            "diff": diff_output.decode("utf-8", "replace"),
            "seal_digest": intact.digest,
        }
        reveal_digest = _prediction_digest(reveal)
        recorded_digest = self._reveal_digests.get(environment.episode_id)
        if recorded_digest is not None and recorded_digest != reveal_digest:
            self.ledger.append_event(
                environment.episode_id,
                "pit.violation",
                Role.OPTIMIZER.value,
                {"kind": "canonical_reveal_changed"},
            )
            raise SealViolation("canonical target reveal changed after it was recorded")
        self._reveal_digests[environment.episode_id] = reveal_digest
        self.ledger.append_event(
            environment.episode_id,
            "pit.target.revealed",
            Role.OPTIMIZER.value,
            {
                "target_sha": environment.target_sha,
                "seal_digest": intact.digest,
                "reveal_digest": reveal_digest,
                "changed_paths": reveal["changed_paths"],
            },
        )
        return reveal

    def grade(
        self,
        environment: PITEnvironment,
        sealed: SealedPrediction,
        reveal: Mapping[str, Any],
    ) -> EpisodeGrade:
        intact = self._require_intact_seal(environment, sealed)
        recorded_reveal_digest = self._reveal_digests.get(environment.episode_id)
        observed_reveal_digest = _prediction_digest(reveal)
        if (
            recorded_reveal_digest is None
            or observed_reveal_digest != recorded_reveal_digest
        ):
            self.ledger.append_event(
                environment.episode_id,
                "pit.violation",
                Role.OPTIMIZER.value,
                {"kind": "reveal_digest_mismatch"},
            )
            raise SealViolation(
                "grading reveal was altered, foreign, or not recorded by the oracle"
            )
        content = intact.prediction_content
        predicted_value = content.get("changed_paths")
        actual_value = reveal.get("changed_paths")
        if not isinstance(predicted_value, list) or not all(
            isinstance(item, str) for item in predicted_value
        ):
            raise ValueError("prediction content must contain a string changed_paths list")
        if not isinstance(actual_value, list) or not all(
            isinstance(item, str) for item in actual_value
        ):
            raise ValueError("reveal must contain a string changed_paths list")
        predicted = tuple(sorted(set(predicted_value)))
        actual = tuple(sorted(set(actual_value)))
        overlap = tuple(sorted(set(predicted) & set(actual)))
        union = set(predicted) | set(actual)
        score = round(len(overlap) / len(union), 6) if union else 1.0
        sequence = self.ledger.append_event(
            environment.episode_id,
            "pit.episode.graded",
            Role.OPTIMIZER.value,
            {
                "prediction_digest": intact.digest,
                "score": score,
                "overlap_paths": overlap,
            },
        )
        return EpisodeGrade(predicted, actual, overlap, score, sequence)

    def run_adversarial_probes(
        self,
        environment: PITEnvironment,
    ) -> tuple[dict[str, Any], ...]:
        probes: list[dict[str, Any]] = []

        def git_probe(
            name: str,
            args: Sequence[str],
            *,
            must_fail: bool = False,
        ) -> bytes:
            receipt, stdout, _ = self._environment_command(
                environment,
                args,
                f"adversarial learner probe: {name}",
                allow_failure=must_fail,
            )
            if must_fail and receipt["result"] == "succeeded":
                raise LeakageError(f"adversarial probe unexpectedly succeeded: {name}")
            probes.append(
                {
                    "name": name,
                    "result": receipt["result"],
                    "receipt_digest": environment.receipt_records[-1]["digest"],
                    "stdout_digest": sha256_digest(stdout),
                }
            )
            return stdout

        git_probe(
            "target-cat-file",
            ["cat-file", "-e", environment.target_sha],
            must_fail=True,
        )
        log_output = git_probe("all-refs-log", ["log", "--all", "--format=%H"])
        reflog_output = git_probe("reflog", ["reflog", "show", "--all"])
        runner = self._runner(environment.root)
        receipt, packed_output, _ = self._command(
            runner,
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "from pathlib import Path; "
                    "p=Path('.git/packed-refs'); "
                    "print(p.read_text(encoding='utf-8') if p.exists() else '', end='')"
                ),
            ],
            environment.episode_id,
            "adversarial learner probe: packed-refs",
            environment.receipt_records,
        )
        probes.append(
            {
                "name": "packed-refs",
                "result": receipt["result"],
                "receipt_digest": environment.receipt_records[-1]["digest"],
                "stdout_digest": sha256_digest(packed_output),
            }
        )
        forbidden_bytes = tuple(
            sha_value.encode("ascii")
            for sha_value in (environment.target_sha, *environment.hidden_shas)
        )
        if any(
            forbidden in output
            for forbidden in forbidden_bytes
            for output in (log_output, reflog_output, packed_output)
        ):
            raise LeakageError("an adversarial metadata probe exposed hidden history")
        return tuple(probes)

    def validate_curriculum_access(
        self,
        environment: PITEnvironment,
        episode: RepositoryLearningEpisode,
        accessed_shas: Sequence[str],
    ) -> None:
        decision = episode.validate_access(accessed_shas)
        if decision.allowed:
            return
        self.verify_environment(environment)
        raise LeakageError(
            "defense-in-depth discrepancy: bookkeeping reports physically absent SHA(s): "
            + ", ".join(decision.leaked_shas)
        )

    def run_scripted_episode(
        self,
        target_sha: str,
        *,
        self_history: bool = False,
    ) -> Path:
        curriculum = (
            build_self_curriculum(self.repository, self._self_pin_count())
            if self_history
            else RepositoryLearningCurriculum(_read_history(self.repository))
        )
        episodes = curriculum.episodes()
        try:
            target_position = next(
                index for index, item in enumerate(episodes) if item.target.sha == target_sha
            )
        except StopIteration as error:
            raise ValueError("target is not present in the selected curriculum") from error
        learning_episode = episodes[target_position]
        environment = self.build_environment(target_sha, self_history=self_history)
        probes = self.run_adversarial_probes(environment)
        _, files_output, _ = self._environment_command(
            environment,
            ["ls-files"],
            "scripted learner inspects observable files",
        )
        predicted_paths = sorted(
            line for line in files_output.decode("utf-8", "strict").splitlines() if line
        )
        _, access_output, _ = self._environment_command(
            environment,
            ["log", "--all", "--format=%H"],
            "record scripted learner commit access",
        )
        accessed = tuple(access_output.decode("ascii", "strict").splitlines())
        self.validate_curriculum_access(environment, learning_episode, accessed)
        sealed = self.seal_prediction(
            environment,
            target_position=target_position,
            learner_identity="scripted-file-overlap-v1",
            prediction_content={"changed_paths": predicted_paths},
        )
        reveal = self.reveal(environment, sealed)
        grade = self.grade(environment, sealed, reveal)
        record = {
            "schema_version": 1,
            "episode_id": environment.episode_id,
            "repository": str(self.repository),
            "target_sha": environment.target_sha,
            "target_position": target_position,
            "environment": {
                "path": str(environment.root),
                "digest": environment.environment_digest,
                "built_at": environment.environment_built_at,
                "ancestor_shas": environment.ancestor_shas,
                "target_tree_sha": environment.target_tree_sha,
            },
            "prediction": {
                **sealed.document(),
                "digest": sealed.digest,
                "ledger_sequence": sealed.ledger_sequence,
            },
            "reveal": reveal,
            "grade": {
                "predicted_paths": grade.predicted_paths,
                "actual_paths": grade.actual_paths,
                "overlap_paths": grade.overlap_paths,
                "score": grade.score,
                "ledger_sequence": grade.ledger_sequence,
            },
            "contamination_caveats": environment.contamination_caveats,
            "adversarial_probes": probes,
            "receipt_root": str(self.receipt_root),
            "receipts": environment.receipt_records,
            "ledger_events": self.ledger.events(environment.episode_id),
            "recorded_at": utc_now(),
        }
        record_path = self.state_dir / "episodes" / f"{environment.episode_id}.json"
        _atomic_json(record_path, record)
        self.ledger.append_event(
            environment.episode_id,
            "pit.episode.recorded",
            Role.OPTIMIZER.value,
            {
                "path": str(record_path),
                "digest": sha256_digest(record_path.read_bytes()),
            },
        )
        return record_path

    def _self_pin_count(self) -> int:
        pins_path = self.repository / "tests" / "fixtures" / "self_history_pins.json"
        try:
            document = json.loads(pins_path.read_text(encoding="utf-8"))
            shas = document["shas"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("self-history pin fixture is unavailable") from error
        if not isinstance(shas, list) or not shas:
            raise ValueError("self-history pin fixture is empty")
        return len(shas)
