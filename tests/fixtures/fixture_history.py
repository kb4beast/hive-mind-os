from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

EXPECTED_SHAS = (
    "6ccb6532520c031bb5c666d25ae5acaa73b3dd07",
    "d027e0f43635b2fae86ea68e68c7361c19241382",
    "bc631bf35a95f4e5a6e2c73488a10ce546864686",
    "ff36f8236c71022a05dc4e44a03373108d020e5c",
    "8cc6c2c9f83046e8b6ac3ebf786974fe9c900fbe",
    "6227202fe03ab9675964a9396a95470917c02590",
    "40e22de7aaa90db61c1fd4ab190255bb116c9740",
    "e09560c8e8f832437d5315e9f93b31df5018eb1d",
    "3c7fbcec285947e25146dca9ee397df04a6b4d3d",
    "58d12d2be4584c4fbbdf73bdc98245218d926c65",
)

_IDENTITY = (
    "-c",
    "user.name=pit-fixture-builder",
    "-c",
    "user.email=pit-fixture-builder@hive-mind.invalid",
    "-c",
    "core.autocrlf=false",
    "-c",
    "commit.gpgsign=false",
)


@dataclass(frozen=True, slots=True)
class FixtureHistory:
    root: Path
    commits: tuple[str, ...]
    merge_sha: str
    tag_name: str


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
            "fixture history git command failed: "
            + completed.stderr.decode("utf-8", "replace")
        )
    return completed.stdout.decode("utf-8").strip()


def _write(root: Path, relative: str, content: str) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")


def _commit(root: Path, message: str, date: str) -> str:
    _git(root, "add", "--all")
    _git(root, "commit", "-m", message, date=date)
    return _git(root, "rev-parse", "HEAD")


def build_fixture_history(parent: Path) -> FixtureHistory:
    root = parent / "pit-fixture-history"
    root.mkdir(parents=True)
    _git(root, "init", "--initial-branch=main")

    commits: list[str] = []
    _write(root, "README.md", "# PIT fixture\n")
    commits.append(_commit(root, "fixture: establish repository", "2025-01-01T00:00:00Z"))

    _write(root, "src/core.txt", "core-v1\n")
    commits.append(_commit(root, "fixture: add core", "2025-01-02T00:00:00Z"))
    branch_point = commits[-1]

    _write(root, "docs/design.md", "design-v1\n")
    commits.append(_commit(root, "fixture: document design", "2025-01-03T00:00:00Z"))

    _git(root, "switch", "-c", "feature", branch_point)
    _write(root, "src/feature.txt", "feature-v1\n")
    feature_one = _commit(root, "fixture: start feature", "2025-01-04T00:00:00Z")
    _write(root, "src/feature.txt", "feature-v2\n")
    feature_two = _commit(root, "fixture: finish feature", "2025-01-05T00:00:00Z")

    _git(root, "switch", "main")
    _write(root, "src/core.txt", "core-v2\n")
    commits.append(_commit(root, "fixture: evolve core", "2025-01-06T00:00:00Z"))
    _write(root, "tests/core.txt", "core-v2 is covered\n")
    commits.append(_commit(root, "fixture: cover core", "2025-01-07T00:00:00Z"))

    _git(
        root,
        "merge",
        "--no-ff",
        "feature",
        "-m",
        "fixture: merge feature",
        date="2025-01-08T00:00:00Z",
    )
    merge_sha = _git(root, "rev-parse", "HEAD")
    commits.extend((feature_one, feature_two, merge_sha))
    _git(root, "tag", "fixture-v1", merge_sha)

    _write(root, "CHANGELOG.md", "fixture-v1\n")
    commits.append(_commit(root, "fixture: record release", "2025-01-09T00:00:00Z"))
    _write(root, "src/core.txt", "core-v3\n")
    commits.append(_commit(root, "fixture: refine core", "2025-01-10T00:00:00Z"))

    ordered = tuple(
        _git(root, "rev-list", "--topo-order", "--reverse", "HEAD").splitlines()
    )
    if EXPECTED_SHAS and ordered != EXPECTED_SHAS:
        raise AssertionError(
            f"fixture history SHA drift: expected {EXPECTED_SHAS}, observed {ordered}"
        )
    if set(commits) != set(ordered):
        raise AssertionError("fixture history builder lost a commit from the DAG")
    return FixtureHistory(root, ordered, merge_sha, "fixture-v1")
