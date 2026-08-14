from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _install_fixture_origin(repo_root: Path) -> None:
    control_path = repo_root / ".autopilot" / "control-plane.json"
    if not control_path.is_file():
        return
    control = json.loads(control_path.read_text(encoding="utf-8"))
    repository = control.get("target", {}).get("repository")
    if not isinstance(repository, str) or not repository.strip():
        raise ValueError("fixture control plane has no repository identity")
    git_dir = repo_root / ".git"
    git_dir.mkdir(exist_ok=True)
    config = git_dir / "config"
    if not config.is_file():
        config.write_text(
            '[core]\n'
            '\tautocrlf = false\n'
            '[remote "origin"]\n'
            f"\turl = https://github.com/{repository}.git\n",
            encoding="utf-8",
            newline="\n",
        )


def copy_autopilot_fixture(source: Path, destination: Path) -> Path:
    """Copy only Git-tracked ``.autopilot`` inputs into an isolated fixture.

    Runtime state and bytecode caches must never make a controller test depend on
    the invoking checkout.  The execution supervisor is copied explicitly while
    this candidate is uncommitted because ``autopilot.py`` imports it at startup;
    once tracked, the ordinary Git inventory copy is idempotent.
    """

    fixture_root = source.resolve()
    repository = fixture_root.parent
    if fixture_root.name != ".autopilot":
        raise ValueError("fixture source must be the repository .autopilot directory")
    listed = subprocess.run(
        ("git", "-C", str(repository), "ls-files", "-z", "--", ".autopilot"),
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    tracked = [Path(item) for item in listed if item]
    destination.mkdir(parents=True)
    for relative in tracked:
        if relative.parts[:2] == (".autopilot", "state"):
            continue
        source_path = repository / relative
        target = destination.joinpath(*relative.parts[1:])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
    supervisor = fixture_root / "bin" / "execution_supervisor.py"
    if supervisor.is_file():
        target = destination / "bin" / supervisor.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(supervisor, target)
    (destination / "state").mkdir()
    # Runtime-root authority is anchored in the shared Git common directory.
    # Lightweight controller fixtures do not need Git objects, but they still
    # need that canonical metadata anchor so tests exercise the production path.
    (destination.parent / ".git").mkdir(exist_ok=True)
    _install_fixture_origin(destination.parent)
    return destination


def ready_runtime(
    controller: Any,
    repo_root: Path,
    *,
    actor: str = "test:runtime-fixture",
    state_dir: Path | None = None,
) -> Path:
    """Explicitly migrate an empty production fixture to runtime readiness."""

    source_autopilot = Path(__file__).resolve().parents[1]
    # Runtime readiness authenticates the complete loaded kernel, not just the
    # prompt templates.  Lightweight fixtures therefore need a byte-identical
    # copy of every missing kernel component; otherwise they would exercise an
    # impossible production state in which authority is initialized by code
    # that is absent from the selected checkout.
    for relative in controller.KERNEL_BUNDLE_COMPONENTS:
        parts = Path(relative).parts
        source = source_autopilot.parent.joinpath(*parts)
        destination = repo_root.joinpath(*parts)
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    (repo_root / ".git").mkdir(exist_ok=True)
    _install_fixture_origin(repo_root)
    coordination_dir = controller.resolve_repository_state_dir(repo_root, state_dir)
    bootstrap_lock = coordination_dir / controller.RUNTIME_BOOTSTRAP_LOCK
    attended_lock = coordination_dir / "locks" / "attended-host.lock"
    arbiter_lock = (
        coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock"
    )
    with controller.runtime_file_lock(bootstrap_lock, timeout_seconds=120.0):
        controller.bootstrap_runtime_authority_migration(
            repo_root,
            coordination_dir,
            actor=actor,
        )
        controller.stage_repository_runtime_authority(repo_root, coordination_dir)
        with controller.runtime_file_lock(arbiter_lock, timeout_seconds=120.0):
            with controller.runtime_file_lock(attended_lock, timeout_seconds=120.0):
                controller.initialize_repository_runtime_authority(
                    repo_root,
                    coordination_dir,
                    attended_migration={"outcome": "ABSENT", "entries": 0},
                )
    return coordination_dir
