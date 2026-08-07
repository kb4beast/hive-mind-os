"""Read-only environment diagnostics for the additive kernel surface.

The doctor intentionally reports uncertainty instead of attempting a remote action,
creating a state directory, or loading credential values.  It is therefore safe to
run before a mission has authority to perform effects.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from hive_mind_os.model_provider import ProviderConfig, ProviderKind

_CI_COMMANDS = (
    "python -m pip install --disable-pip-version-check --no-deps -e .",
    "python -m compileall -q src tests",
    "python -m unittest discover -s tests -v",
    "ruff check src tests",
    "pyright",
)
_PROTECTED_BRANCHES = frozenset({"main", "master"})
_PROVIDER_CONFIGURATION_NAMES = frozenset(
    {
        "HIVE_MIND_MODEL_PROVIDER",
        "HIVE_MIND_MODEL_BASE_URL",
        "HIVE_MIND_MODEL_MODEL",
        "HIVE_MIND_MODEL_ID",
        "HIVE_MIND_MODEL_API_KEY_ENV",
        "HIVE_MIND_MODEL_TIMEOUT_S",
        "HIVE_MIND_MODEL_MAX_OUTPUT_TOKENS",
        "HIVE_MIND_MODEL_TEMPERATURE",
        "HIVE_MIND_MODEL_MAX_RETRIES",
    }
)


def _check(name: str, status: str, detail: str, **fields: object) -> dict[str, object]:
    return {"name": name, "status": status, "detail": detail, **fields}


def _run_git(
    git_executable: str, arguments: Sequence[str], repository: Path | None = None
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            (git_executable, *arguments),
            cwd=repository,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _state_directory_check(state_dir: Path) -> dict[str, object]:
    if state_dir.exists() and not state_dir.is_dir():
        return _check(
            "state_directory",
            "unusable",
            "State path exists but is not a directory.",
            path=str(state_dir),
        )
    parent = _nearest_existing_parent(state_dir if state_dir.exists() else state_dir.parent)
    if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
        return _check(
            "state_directory",
            "unusable",
            "State directory cannot be created or written without changing the filesystem.",
            path=str(state_dir),
        )
    detail = (
        "Existing state directory is writable."
        if state_dir.exists()
        else "State directory is absent; its existing parent is writable."
    )
    return _check("state_directory", "ready", detail, path=str(state_dir))


def _provider_check(environment: Mapping[str, str]) -> dict[str, object]:
    configured = sorted(set(environment) & _PROVIDER_CONFIGURATION_NAMES)
    if not configured:
        return _check(
            "provider",
            "not_configured",
            "No model configuration is set; offline kernel diagnostics remain available.",
        )
    raw_kind = environment.get("HIVE_MIND_MODEL_PROVIDER", "openai_compatible")
    try:
        kind = ProviderKind(raw_kind)
    except ValueError:
        return _check(
            "provider",
            "invalid",
            "Model provider kind is not supported.",
            configured_variables=configured,
        )
    defaults = {
        ProviderKind.OPENAI_COMPATIBLE: ("https://api.openai.com/v1", "OPENAI_API_KEY"),
        ProviderKind.ANTHROPIC: ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    }
    default_url, default_credential_name = defaults[kind]
    model = environment.get("HIVE_MIND_MODEL_MODEL") or environment.get(
        "HIVE_MIND_MODEL_ID", ""
    )
    try:
        config = ProviderConfig(
            kind=kind,
            base_url=environment.get("HIVE_MIND_MODEL_BASE_URL", default_url),
            model=model,
            api_key_env=environment.get(
                "HIVE_MIND_MODEL_API_KEY_ENV", default_credential_name
            ),
            timeout_s=float(environment.get("HIVE_MIND_MODEL_TIMEOUT_S", "60")),
            max_output_tokens=int(
                environment.get("HIVE_MIND_MODEL_MAX_OUTPUT_TOKENS", "2048")
            ),
            temperature=float(environment.get("HIVE_MIND_MODEL_TEMPERATURE", "0")),
            max_retries=int(environment.get("HIVE_MIND_MODEL_MAX_RETRIES", "2")),
        )
    except (TypeError, ValueError):
        return _check(
            "provider",
            "invalid",
            "Model configuration fails local validation.",
            configured_variables=configured,
        )
    credential_present = bool(environment.get(config.api_key_env))
    return _check(
        "provider",
        "configured" if credential_present else "credentials_missing",
        (
            "Model configuration is locally valid."
            if credential_present
            else "Model configuration is locally valid but its credential is unavailable."
        ),
        configured_variables=configured,
        credential_environment=config.api_key_env,
    )


def _ci_check(repository: Path) -> dict[str, object]:
    workflow = repository / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        return _check(
            "ci_commands",
            "unavailable",
            "The constitutional CI workflow is absent.",
            commands=list(_CI_COMMANDS),
        )
    content = workflow.read_text(encoding="utf-8")
    declared = {
        "python -m pip install --disable-pip-version-check --no-deps -e .": (
            "python -m pip install --disable-pip-version-check --no-deps -e ." in content
        ),
        "python -m compileall -q src tests": "python -m compileall -q src tests"
        in content,
        "python -m unittest discover -s tests -v": "python -m unittest discover -s tests -v"
        in content,
        "ruff check src tests": (
            "astral-sh/ruff-action@" in content and 'args: "check src tests"' in content
        ),
        "pyright": "jakebailey/pyright-action@" in content,
    }
    missing = [command for command in _CI_COMMANDS if not declared[command]]
    local_tools = {tool: shutil.which(tool) is not None for tool in ("ruff", "pyright")}
    status = "declared" if not missing else "mismatch"
    detail = (
        "Doctor command inventory matches the constitutional CI workflow."
        if not missing
        else "The constitutional CI workflow does not contain every documented doctor command."
    )
    return _check(
        "ci_commands",
        status,
        detail,
        commands=list(_CI_COMMANDS),
        missing_commands=missing,
        local_tools=local_tools,
    )


def inspect_kernel_environment(
    repository: str | Path,
    *,
    state_dir: str | Path,
    environment: Mapping[str, str] | None = None,
    python_version: tuple[int, int, int] | None = None,
    git_executable: str = "git",
) -> dict[str, object]:
    """Return a redacted, deterministic diagnostic report without remote effects."""

    repository_path = Path(repository).resolve()
    state_path = Path(state_dir).resolve()
    values = dict(os.environ if environment is None else environment)
    version = python_version or sys.version_info[:3]
    checks: list[dict[str, object]] = []

    supported_python = version >= (3, 11, 0)
    checks.append(
        _check(
            "python",
            "supported" if supported_python else "unsupported",
            "Python version is supported." if supported_python else "Python 3.11 or newer is required.",
            version=".".join(str(part) for part in version),
        )
    )
    git_version = _run_git(git_executable, ("--version",))
    if git_version is None or git_version.returncode != 0:
        checks.append(_check("git", "missing", "Git executable is unavailable."))
        checks.append(
            _check("repository", "unverified", "Repository cannot be checked without Git.")
        )
        checks.append(
            _check(
                "protected_branch",
                "uncertain",
                "Protected-branch status cannot be checked without Git.",
            )
        )
    else:
        checks.append(_check("git", "available", "Git executable is available."))
        top_level = _run_git(git_executable, ("rev-parse", "--show-toplevel"), repository_path)
        if top_level is None or top_level.returncode != 0:
            checks.append(
                _check("repository", "not_repository", "Path is not a Git worktree.")
            )
            checks.append(
                _check(
                    "protected_branch",
                    "uncertain",
                    "Protected-branch status requires a Git worktree.",
                )
            )
        else:
            root = Path(top_level.stdout.strip()).resolve()
            porcelain = _run_git(
                git_executable, ("status", "--porcelain=v1", "--untracked-files=all"), root
            )
            entries = [] if porcelain is None else porcelain.stdout.splitlines()
            clean = porcelain is not None and porcelain.returncode == 0 and not entries
            checks.append(
                _check(
                    "repository",
                    "clean" if clean else "dirty",
                    "Repository worktree is clean." if clean else "Repository worktree has uncommitted changes.",
                    root=str(root),
                    entries=entries,
                )
            )
            branch = _run_git(git_executable, ("branch", "--show-current"), root)
            branch_name = "" if branch is None else branch.stdout.strip()
            if branch_name in _PROTECTED_BRANCHES:
                checks.append(
                    _check(
                        "protected_branch",
                        "uncertain",
                        "Local inspection cannot verify remote branch-protection rules.",
                        branch=branch_name,
                    )
                )
            else:
                checks.append(
                    _check(
                        "protected_branch",
                        "not_applicable",
                        "Current local branch is not a conventional protected branch.",
                        branch=branch_name or None,
                    )
                )
    checks.append(_state_directory_check(state_path))
    checks.append(_provider_check(values))
    checks.append(_ci_check(repository_path))
    critical_statuses = {
        check["name"]: check["status"]
        for check in checks
        if check["name"] in {"python", "git", "repository", "state_directory"}
    }
    ready = critical_statuses == {
        "python": "supported",
        "git": "available",
        "repository": "clean",
        "state_directory": "ready",
    }
    return {
        "schema_version": 1,
        "status": "ready" if ready else "attention",
        "repository": str(repository_path),
        "state_directory": str(state_path),
        "checks": checks,
    }


def assert_kernel_import_boundary(package_root: str | Path) -> None:
    """Reject a kernel dependency on repository-specific cortex code."""

    root = Path(package_root)
    violations: list[str] = []
    for source_path in sorted(root.rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                module = ", ".join(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
            if module == "hive_mind_os.cortex" or module.startswith(
                "hive_mind_os.cortex."
            ):
                violations.append(str(source_path))
    if violations:
        raise ValueError(
            "brain_kernel must not import repository cortex modules: "
            + ", ".join(violations)
        )
