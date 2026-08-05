"""Deterministic offline fixture used by the ``hive-mind demo`` command.

This module intentionally creates one known regression.  It exists to demonstrate the
local delivery receipt flow; it is not a general repository-analysis capability.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

COMMIT_ONE_SHA = "842376f736beea0350d18dc2b983d0414e827885"
COMMIT_TWO_SHA = "f1c725ed6033f6e484f779fb01cd7939f2ae1863"
GOOD_FIX = b"def increment(value: int) -> int:\n    return value + 1\n"
SABOTAGE_FIX = (
    b"import unittest\n\n"
    b"from tiny_pkg.maths import increment\n\n\n"
    b"class MathsTests(unittest.TestCase):\n"
    b"    def test_increment_regression(self) -> None:\n"
    b"        self.assertEqual(increment(1), 0)\n\n\n"
    b"if __name__ == \"__main__\":\n"
    b"    unittest.main()\n"
)

_IDENTITY = (
    "-c",
    "user.name=fixture-builder",
    "-c",
    "user.email=fixture-builder@hive-mind.invalid",
    "-c",
    "core.autocrlf=false",
    "-c",
    "commit.gpgsign=false",
)


@dataclass(frozen=True, slots=True)
class FixtureRepo:
    """A local Git fixture with a known one-line regression."""

    root: Path
    commit_one: str
    commit_two: str


def fixture_fix(variant: str = "good") -> tuple[str, bytes]:
    """Return the one intentional demo edit for a supported fixture variant."""

    if variant == "good":
        return "tiny_pkg/maths.py", GOOD_FIX
    if variant == "sabotage":
        return "tests/test_maths.py", SABOTAGE_FIX
    raise ValueError("fixture fix variant must be good or sabotage")


def _git(root: Path, *args: str, date: str | None = None) -> str:
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if date is not None:
        environment["GIT_AUTHOR_DATE"] = date
        environment["GIT_COMMITTER_DATE"] = date
    completed = subprocess.run(
        ["git", *_IDENTITY, *args],
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"fixture git command failed: {completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed.stdout.decode("utf-8").strip()


def _write(root: Path, relative: str, content: bytes) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def build_fixture_repo(parent: Path) -> FixtureRepo:
    """Create the pinned demo repository beneath an existing parent directory."""

    root = parent / "fixture-repository"
    root.mkdir(parents=True)
    _git(root, "init", "--initial-branch=main")

    _write(root, "tiny_pkg/__init__.py", b"from .maths import increment\n")
    _write(root, "tiny_pkg/maths.py", GOOD_FIX)
    _write(
        root,
        "tests/test_maths.py",
        (
            b"import unittest\n\n"
            b"from tiny_pkg.maths import increment\n\n\n"
            b"class MathsTests(unittest.TestCase):\n"
            b"    def test_increment(self) -> None:\n"
            b"        self.assertEqual(increment(1), 2)\n\n\n"
            b"if __name__ == \"__main__\":\n"
            b"    unittest.main()\n"
        ),
    )
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "fixture: working package", date="2026-01-01T00:00:00Z")
    commit_one = _git(root, "rev-parse", "HEAD")

    _write(root, "tiny_pkg/maths.py", b"def increment(value: int) -> int:\n    return value - 1\n")
    _write(
        root,
        "tests/test_maths.py",
        (
            b"import unittest\n\n"
            b"from tiny_pkg.maths import increment\n\n\n"
            b"class MathsTests(unittest.TestCase):\n"
            b"    def test_increment_regression(self) -> None:\n"
            b"        self.assertEqual(increment(1), 2)\n\n\n"
            b"if __name__ == \"__main__\":\n"
            b"    unittest.main()\n"
        ),
    )
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "fixture: introduce regression", date="2026-01-02T00:00:00Z")
    commit_two = _git(root, "rev-parse", "HEAD")

    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_bytes(b"#!/bin/sh\nprintf hook-ran > \"../fixture-hook-ran.txt\"\nexit 1\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass

    if (commit_one, commit_two) != (COMMIT_ONE_SHA, COMMIT_TWO_SHA):
        raise AssertionError(
            "fixture repository SHA drift: "
            f"expected {(COMMIT_ONE_SHA, COMMIT_TWO_SHA)}, "
            f"observed {(commit_one, commit_two)}"
        )
    return FixtureRepo(root, commit_one, commit_two)
