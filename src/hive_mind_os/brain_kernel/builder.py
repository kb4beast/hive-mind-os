"""Typed, authority-bound Builder action planning.

The Builder never receives a repository handle.  It can only describe an
isolated write, test command, branch, or commit and submit that description to
the kernel effect gateway with a capability token.  Concrete local execution
lives in :mod:`hive_mind_os.cortex.repository.builder_adapter`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from .authority import AuthorityRegistry
from .canonical import canonical_digest
from .contracts import EffectIntent, normalize_portable_path
from .effects import EffectGateway, EffectResult


class BuilderActionDenied(PermissionError):
    """An action would exceed Builder's deliberately narrow authority."""


class BuilderIterationExhausted(RuntimeError):
    """A bounded repair loop ended without passing its requested commands."""


class BuilderActionKind(StrEnum):
    WRITE = "write"
    COMMAND = "command"
    BRANCH = "branch"
    COMMIT = "commit"


class BuilderCommandProfile(StrEnum):
    """Closed, portable command behaviors implemented by the trusted adapter."""

    FILE_EXISTS = "file-exists"
    GIT_DIFF_CHECK = "git-diff-check"


_PROTECTED_BRANCHES = {"main", "master", "release"}
_SEALED_OR_DEPENDENCY_PREFIXES = (
    ".autopilot/",
    ".github/",
    ".git/",
    "tests/acceptance/",
    "tests/sealed/",
)
_DEPENDENCY_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "poetry.lock",
    "uv.lock",
}
def _deny_target(target: str) -> str:
    normalized = normalize_portable_path(target)
    folded = normalized.casefold()
    if folded in {value.casefold() for value in _DEPENDENCY_FILES} or folded.startswith(
        "requirements/"
    ):
        raise BuilderActionDenied("dependency changes require a separate authority grant")
    if folded == ".git" or folded.startswith(
        tuple(value.casefold() for value in _SEALED_OR_DEPENDENCY_PREFIXES)
    ):
        raise BuilderActionDenied("sealed acceptance or control-plane path is not writable")
    return normalized


def _command_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    if set(payload) != {"profile", "paths"}:
        raise BuilderActionDenied("command actions accept only profile and paths")
    try:
        profile = BuilderCommandProfile(str(payload.get("profile")))
    except ValueError as error:
        raise BuilderActionDenied("command profile is not allowlisted") from error
    raw_paths = payload.get("paths")
    if not isinstance(raw_paths, (tuple, list)) or not raw_paths:
        raise ValueError("command profile requires non-empty paths")
    paths: list[str] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("command profile paths must be non-empty strings")
        paths.append(normalize_portable_path(raw_path))
    return MappingProxyType({"profile": profile.value, "paths": tuple(paths)})


@dataclass(frozen=True, slots=True)
class BuilderAction:
    """One declarative Builder effect request.

    ``payload`` is intentionally opaque to the planner.  Its canonical digest,
    rather than its contents, is embedded in the durable effect intent.
    """

    action_id: str
    kind: BuilderActionKind
    target: str
    payload: Mapping[str, object]
    rollback_description: str

    def __post_init__(self) -> None:
        if not self.action_id.strip() or not self.rollback_description.strip():
            raise ValueError("Builder action_id and rollback_description are required")
        if not isinstance(self.payload, Mapping):
            raise TypeError("Builder payload must be a mapping")
        normalized = normalize_portable_path(self.target)
        sealed_payload: Mapping[str, object]
        if self.kind is BuilderActionKind.WRITE:
            normalized = _deny_target(normalized)
            content = self.payload.get("content")
            if set(self.payload) != {"content"} or not isinstance(content, str):
                raise ValueError("write action requires string content")
            sealed_payload = MappingProxyType({"content": content})
        elif self.kind is BuilderActionKind.COMMAND:
            if normalized != "isolated-workspace":
                raise ValueError("command action requires isolated-workspace")
            sealed_payload = _command_payload(self.payload)
        elif self.kind is BuilderActionKind.BRANCH:
            if normalized in _PROTECTED_BRANCHES or normalized.startswith("release/"):
                raise BuilderActionDenied("protected branch mutation is forbidden")
            if set(self.payload) - {"base"}:
                raise ValueError("branch action only accepts an optional base")
            if "base" in self.payload and (
                not isinstance(self.payload["base"], str) or not self.payload["base"].strip()
            ):
                raise ValueError("branch base must be a non-empty string")
            sealed_payload = MappingProxyType(dict(self.payload))
        elif self.kind is BuilderActionKind.COMMIT:
            if normalized in _PROTECTED_BRANCHES or normalized.startswith("release/"):
                raise BuilderActionDenied("protected branch mutation is forbidden")
            paths = self.payload.get("paths")
            message = self.payload.get("message")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("commit action requires a message")
            if not isinstance(paths, (tuple, list)) or not paths:
                raise ValueError("commit action requires non-empty declared paths")
            for path in paths:
                if not isinstance(path, str):
                    raise ValueError("commit paths must be strings")
                _deny_target(path)
            sealed_payload = MappingProxyType(
                {"message": message, "paths": tuple(_deny_target(str(path)) for path in paths)}
            )
        else:  # pragma: no cover - protects callers passing a forged enum-like value.
            raise BuilderActionDenied("Builder action kind is not supported")
        object.__setattr__(self, "target", normalized)
        object.__setattr__(self, "payload", sealed_payload)

    @property
    def parameters_digest(self) -> str:
        return canonical_digest({"kind": self.kind, "target": self.target, "payload": dict(self.payload)})

    @property
    def idempotency_key(self) -> str:
        return canonical_digest({"builder_action": self.action_id, "parameters": self.parameters_digest})


@dataclass(frozen=True, slots=True)
class BuilderActionOutcome:
    action_id: str
    intent_digest: str
    status: str
    detail: str
    output_digest: str
    exit_code: int | None = None

    def __post_init__(self) -> None:
        if self.status not in {"SUCCEEDED", "FAILED"}:
            raise ValueError("invalid Builder action outcome")


class BuilderEffectAdapter(Protocol):
    """The minimal adapter surface required by the Builder coordinator."""

    adapter_name: str

    def register_action(self, action: BuilderAction) -> str: ...

    def outcome_for(self, intent_digest: str) -> BuilderActionOutcome: ...


@dataclass(frozen=True, slots=True)
class BuilderExecution:
    action: BuilderAction
    effect: EffectResult
    outcome: BuilderActionOutcome


class BuilderCoordinator:
    """Submit bounded Builder action rounds exclusively through ``EffectGateway``."""

    def __init__(
        self,
        gateway: EffectGateway,
        authority: AuthorityRegistry,
        adapter: BuilderEffectAdapter,
        *,
        mission_id: str,
        work_id: str,
        actor_id: str,
        authority_envelope_digest: str,
        policy_decision_ref: str,
        risk_tier: str = "R1",
        now: str,
    ) -> None:
        self.gateway = gateway
        self.authority = authority
        self.adapter = adapter
        self.mission_id = mission_id
        self.work_id = work_id
        self.actor_id = actor_id
        self.authority_envelope_digest = authority_envelope_digest
        self.policy_decision_ref = policy_decision_ref
        self.risk_tier = risk_tier
        self.now = now

    def execute_round(self, attempt_id: str, actions: Sequence[BuilderAction]) -> tuple[BuilderExecution, ...]:
        if not actions:
            raise ValueError("Builder round requires at least one action")
        executions: list[BuilderExecution] = []
        for action in actions:
            parameters_digest = self.adapter.register_action(action)
            if parameters_digest != action.parameters_digest:
                raise BuilderActionDenied("adapter changed the sealed Builder payload")
            intent = EffectIntent(
                self.mission_id,
                self.work_id,
                attempt_id,
                self.actor_id,
                "builder",
                str(action.kind),
                self.risk_tier,
                self.adapter.adapter_name,
                action.target,
                parameters_digest,
                action.idempotency_key,
                self.authority_envelope_digest,
                ("isolated workspace is present",),
                action.rollback_description,
                self.policy_decision_ref,
                canonical_digest({"action": action.action_id, "attempt": attempt_id, "parameters": parameters_digest}),
            )
            token = self.authority.authorize(
                self.authority_envelope_digest, str(action.kind), action.target, now=self.now
            )
            effect = self.gateway.execute(intent, token)
            outcome = self.adapter.outcome_for(intent.intent_digest)
            executions.append(BuilderExecution(action, effect, outcome))
        return tuple(executions)

    def repair(self, rounds: Sequence[Sequence[BuilderAction]], *, max_retries: int) -> tuple[BuilderExecution, ...]:
        """Run bounded repair rounds; a failing test may be followed by a repair round."""

        if max_retries < 0 or not rounds or len(rounds) > max_retries + 1:
            raise BuilderIterationExhausted("Builder repair rounds exceed the sealed retry budget")
        all_executions: list[BuilderExecution] = []
        for number, actions in enumerate(rounds, start=1):
            executions = self.execute_round(f"ATTEMPT-builder-{number}", actions)
            all_executions.extend(executions)
            failures = [item for item in executions if item.outcome.status != "SUCCEEDED"]
            if not failures:
                return tuple(all_executions)
        raise BuilderIterationExhausted("Builder tests still fail after the sealed retry budget")
