"""Root-confined local implementation of typed Builder effects.

This is deliberately an adapter, not a convenience API: callers must register
it with :class:`EffectGateway` and present a capability token through the
Builder coordinator.  It never pushes, merges, deploys, or installs packages.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from ...brain_kernel.authority import AuthorityDenied
from ...brain_kernel.builder import (
    BuilderAction,
    BuilderActionKind,
    BuilderActionOutcome,
    BuilderCommandProfile,
)
from ...brain_kernel.canonical import canonical_digest
from ...brain_kernel.contracts import EffectIntent, normalize_portable_path


class BuilderAdapterError(RuntimeError):
    """The adapter could not safely materialize a declared Builder action."""


@dataclass(frozen=True, slots=True)
class _RegisteredAction:
    action: BuilderAction
    parameters_digest: str


class IsolatedBuilderAdapter:
    """Execute registered Builder actions in one explicit local workspace."""

    adapter_name = "isolated-builder"

    def __init__(self, root: str | Path, *, command_timeout_seconds: int = 30) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise BuilderAdapterError("isolated Builder workspace is unavailable")
        if command_timeout_seconds < 1 or command_timeout_seconds > 300:
            raise ValueError("command timeout must be between 1 and 300 seconds")
        self.command_timeout_seconds = command_timeout_seconds
        self._actions: dict[str, _RegisteredAction] = {}
        self._outcomes: dict[str, BuilderActionOutcome] = {}

    def register_action(self, action: BuilderAction) -> str:
        digest = action.parameters_digest
        previous = self._actions.setdefault(
            action.idempotency_key, _RegisteredAction(action, digest)
        )
        if previous.action != action:
            raise AuthorityDenied("Builder idempotency key is already bound to another action")
        return digest

    def outcome_for(self, intent_digest: str) -> BuilderActionOutcome:
        try:
            return self._outcomes[intent_digest]
        except KeyError as error:
            raise BuilderAdapterError("Builder effect has no recorded adapter outcome") from error

    def apply(self, intent: EffectIntent) -> Mapping[str, object]:
        action = self._action_for(intent)
        if intent.intent_digest in self._outcomes:
            outcome = self._outcomes[intent.intent_digest]
            return self._effect_document(outcome)
        outcome = self._execute(intent.intent_digest, action)
        self._outcomes[intent.intent_digest] = outcome
        return self._effect_document(outcome)

    def _action_for(self, intent: EffectIntent) -> BuilderAction:
        try:
            registered = self._actions[intent.idempotency_key]
        except KeyError as error:
            raise AuthorityDenied("Builder effect payload was not registered") from error
        action = registered.action
        if (
            intent.target_adapter != self.adapter_name
            or intent.action != str(action.kind)
            or intent.target != action.target
            or intent.parameters_digest != registered.parameters_digest
        ):
            raise AuthorityDenied("Builder effect intent is not bound to its registered action")
        return action

    def _execute(self, intent_digest: str, action: BuilderAction) -> BuilderActionOutcome:
        try:
            if action.kind is BuilderActionKind.WRITE:
                return self._write(intent_digest, action)
            if action.kind is BuilderActionKind.COMMAND:
                return self._command(intent_digest, action)
            if action.kind is BuilderActionKind.BRANCH:
                arguments = ["switch", "-c", action.target]
                if "base" in action.payload:
                    arguments.append(str(action.payload["base"]))
                return self._git(intent_digest, action, arguments)
            if action.kind is BuilderActionKind.COMMIT:
                return self._commit(intent_digest, action)
        except (OSError, subprocess.SubprocessError, BuilderAdapterError) as error:
            return self._outcome(intent_digest, action, "FAILED", str(error), None)
        raise AuthorityDenied("unsupported Builder action")

    def _write(self, intent_digest: str, action: BuilderAction) -> BuilderActionOutcome:
        path = self._path(action.target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(action.payload["content"]), encoding="utf-8")
        return self._outcome(intent_digest, action, "SUCCEEDED", "isolated write completed", 0)

    def _command(self, intent_digest: str, action: BuilderAction) -> BuilderActionOutcome:
        profile, paths = self._command_profile(action)
        if profile is BuilderCommandProfile.FILE_EXISTS:
            missing = tuple(path for path in paths if not self._path(path).is_file())
            detail = canonical_digest({"profile": profile.value, "missing": missing})
            return self._outcome(
                intent_digest,
                action,
                "FAILED" if missing else "SUCCEEDED",
                detail,
                1 if missing else 0,
            )
        if profile is not BuilderCommandProfile.GIT_DIFF_CHECK:  # pragma: no cover
            raise BuilderAdapterError("validated command profile has no implementation")
        completed = self._run_git(
            ["diff", "--no-ext-diff", "--no-textconv", "--check", "--", *paths]
        )
        # Command streams are bytes and may contain secrets.  Retain only their
        # individual digests in the outcome evidence; canonical JSON must never
        # receive raw bytes or command output.
        detail = canonical_digest(
            {"stdout_digest": self._stream_digest(completed.stdout), "stderr_digest": self._stream_digest(completed.stderr)}
        )
        return self._outcome(
            intent_digest, action, "SUCCEEDED" if completed.returncode == 0 else "FAILED", detail, completed.returncode
        )

    def _command_profile(
        self, action: BuilderAction
    ) -> tuple[BuilderCommandProfile, tuple[str, ...]]:
        try:
            profile = BuilderCommandProfile(str(action.payload.get("profile")))
        except ValueError as error:  # pragma: no cover - BuilderAction seals this value.
            raise BuilderAdapterError("validated command profile is unavailable") from error
        raw_paths = action.payload.get("paths")
        if not isinstance(raw_paths, (tuple, list)):
            raise BuilderAdapterError("validated command paths are unavailable")
        paths = tuple(normalize_portable_path(str(path)) for path in raw_paths)
        for path in paths:
            self._path(path)
        return profile, paths

    @staticmethod
    def _command_environment(runtime: Path) -> dict[str, str]:
        allowed = ("PATH", "PATHEXT", "SystemRoot", "SYSTEMROOT", "WINDIR")
        environment = {
            key: value
            for key in allowed
            if (value := os.environ.get(key))
            and not any(character in value for character in "\r\n")
        }
        runtime_text = str(runtime)
        environment.update(
            {
                "HOME": runtime_text,
                "USERPROFILE": runtime_text,
                "XDG_CONFIG_HOME": runtime_text,
                "TEMP": runtime_text,
                "TMP": runtime_text,
                "TMPDIR": runtime_text,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_ALLOW_PROTOCOL": "file",
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return environment

    def _git(self, intent_digest: str, action: BuilderAction, args: list[str]) -> BuilderActionOutcome:
        completed = self._run_git(args)
        detail = canonical_digest(
            {"stdout_digest": self._stream_digest(completed.stdout), "stderr_digest": self._stream_digest(completed.stderr), "argv": args}
        )
        return self._outcome(
            intent_digest, action, "SUCCEEDED" if completed.returncode == 0 else "FAILED", detail, completed.returncode
        )

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        with tempfile.TemporaryDirectory(prefix=".hive-builder-", dir=self.root) as runtime:
            runtime_path = Path(runtime)
            environment = self._command_environment(runtime_path)
            executable = shutil.which("git", path=environment.get("PATH"))
            if executable is None:
                raise BuilderAdapterError("Builder Git profile requires Git on the trusted host PATH")
            try:
                Path(executable).resolve().relative_to(self.root)
            except ValueError:
                pass
            else:
                raise BuilderAdapterError("command executable must not come from the target workspace")
            return subprocess.run(
                [
                    executable,
                    "-c",
                    f"core.hooksPath={runtime_path / 'hooks'}",
                    "-c",
                    "credential.helper=",
                    "-c",
                    "protocol.ext.allow=never",
                    "-c",
                    "core.fsmonitor=false",
                    *args,
                ],
                cwd=self.root,
                shell=False,
                capture_output=True,
                timeout=self.command_timeout_seconds,
                check=False,
                env=environment,
            )

    def _commit(self, intent_digest: str, action: BuilderAction) -> BuilderActionOutcome:
        raw_paths = action.payload.get("paths")
        if not isinstance(raw_paths, (tuple, list)):
            raise BuilderAdapterError("validated commit paths are unavailable")
        paths = [normalize_portable_path(str(path)) for path in raw_paths]
        staged = self._git(intent_digest, action, ["add", "--", *paths])
        if staged.status != "SUCCEEDED":
            return staged
        return self._git(intent_digest, action, ["commit", "--no-gpg-sign", "-m", str(action.payload["message"])])

    def _path(self, target: str) -> Path:
        candidate = self.root.joinpath(*normalize_portable_path(target).split("/"))
        try:
            candidate.parent.resolve().relative_to(self.root)
            if candidate.exists():
                candidate.resolve().relative_to(self.root)
        except ValueError as error:
            raise AuthorityDenied("Builder path escapes isolated workspace") from error
        return candidate

    @staticmethod
    def _outcome(
        intent_digest: str, action: BuilderAction, status: str, detail: str, exit_code: int | None
    ) -> BuilderActionOutcome:
        return BuilderActionOutcome(
            action.action_id, intent_digest, status, detail,
            canonical_digest({"action": action.action_id, "status": status, "detail": detail, "exit": exit_code}), exit_code,
        )

    @staticmethod
    def _effect_document(outcome: BuilderActionOutcome) -> Mapping[str, object]:
        return {
            "produced_identifiers": (f"builder-action:{outcome.action_id}",),
            "postcondition_digest": outcome.output_digest,
        }

    @staticmethod
    def _stream_digest(value: bytes) -> str:
        return f"sha256:{sha256(value).hexdigest()}"
