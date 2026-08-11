from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def copy_autopilot_fixture(source: Path, destination: Path) -> Path:
    """Copy only Git-tracked ``.autopilot`` inputs into an isolated fixture.

    Runtime state, bytecode caches, and ignored or untracked generated modules must
    never make a controller test depend on the invoking checkout.
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
    (destination / "state").mkdir()
    return destination
