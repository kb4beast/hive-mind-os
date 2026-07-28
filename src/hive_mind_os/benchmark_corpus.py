"""Deterministic local task corpus for the P13 benchmark court MVP."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .autonomy import AutonomyBudget
from .receipts import sha256_digest

_IDENTITY = (
    "-c",
    "user.name=benchmark-corpus",
    "-c",
    "user.email=benchmark-corpus@hive-mind.invalid",
    "-c",
    "core.autocrlf=false",
    "-c",
    "commit.gpgsign=false",
)
_COMMIT_DATE = "2026-07-27T00:00:00Z"


@dataclass(frozen=True, slots=True)
class BudgetSpec:
    """Common resource envelope issued independently to every lane attempt."""

    max_episodes: int = 1000
    max_tool_calls: int = 500
    max_compute_units: float = 500.0
    max_tool_calls_per_episode: int = 100
    max_compute_units_per_episode: float = 100.0

    def create(self) -> AutonomyBudget:
        return AutonomyBudget(**asdict(self))

    def to_dict(self) -> dict[str, int | float]:
        return dict(asdict(self))


@dataclass(frozen=True, slots=True)
class TaskManifest:
    """Lane-visible task contract; the hidden checker is represented only by a digest."""

    schema_version: int
    task_id: str
    family: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    budget: BudgetSpec
    allowed_backends: tuple[str, ...]
    hidden_check_digest: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["acceptance_criteria"] = list(self.acceptance_criteria)
        payload["allowed_backends"] = list(self.allowed_backends)
        return payload


@dataclass(frozen=True, slots=True)
class CorpusTask:
    manifest: TaskManifest
    repository: Path
    base_sha: str
    tree_digest: str
    checker_id: str

    def lane_view(self) -> LaneTask:
        return LaneTask(
            task_id=self.manifest.task_id,
            repository=self.repository,
            base_sha=self.base_sha,
            objective=self.manifest.objective,
            acceptance_criteria=self.manifest.acceptance_criteria,
            allowed_backends=self.manifest.allowed_backends,
        )


@dataclass(frozen=True, slots=True)
class LaneTask:
    """Restricted view passed to a lane; it deliberately has no hidden-check field."""

    task_id: str
    repository: Path
    base_sha: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    allowed_backends: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CorpusSnapshot:
    tasks: tuple[CorpusTask, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class _TaskSeed:
    task_id: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    files: Mapping[str, bytes]
    checker_id: str


_PUBLIC_TEST = b"""import unittest

from tiny_pkg.maths import increment


class MathsTests(unittest.TestCase):
    def test_documented_example(self) -> None:
        self.assertEqual(increment(1), 2)


if __name__ == "__main__":
    unittest.main()
"""

_GREEN_WEAK_TEST = b"""import unittest

from tiny_pkg.maths import increment


class MathsTests(unittest.TestCase):
    def test_zero_smoke(self) -> None:
        self.assertEqual(increment(0), 0)


if __name__ == "__main__":
    unittest.main()
"""

_TASKS = (
    _TaskSeed(
        "failing-test-fix",
        "Repair increment so the failing documented example passes.",
        ("increment(1) returns 2",),
        {
            "tiny_pkg/__init__.py": b"from .maths import increment\n",
            "tiny_pkg/maths.py": b"def increment(value: int) -> int:\n    return value - 1\n",
            "tests/test_maths.py": _PUBLIC_TEST,
        },
        "increment-wide",
    ),
    _TaskSeed(
        "off-by-one-green-tests",
        "Correct the off-by-one behavior despite the weak green smoke test.",
        ("increment adds exactly one for ordinary integers",),
        {
            "tiny_pkg/__init__.py": b"from .maths import increment\n",
            "tiny_pkg/maths.py": b"def increment(value: int) -> int:\n    return value\n",
            "tests/test_maths.py": _GREEN_WEAK_TEST,
        },
        "increment-wide",
    ),
    _TaskSeed(
        "missing-edge-case",
        "Repair the missing negative-input edge case without regressing positive inputs.",
        ("increment handles both positive and negative integers",),
        {
            "tiny_pkg/__init__.py": b"from .maths import increment\n",
            "tiny_pkg/maths.py": (
                b"def increment(value: int) -> int:\n"
                b"    return value + 1 if value >= 0 else value - 1\n"
            ),
            "tests/test_maths.py": _PUBLIC_TEST,
        },
        "increment-negative",
    ),
    _TaskSeed(
        "doc-code-drift",
        "Bring the implementation back into agreement with the documented increment API.",
        ("README and implementation both describe adding one",),
        {
            "README.md": b"# Tiny package\n\n`increment(value)` adds one.\n",
            "tiny_pkg/__init__.py": b"from .maths import increment\n",
            "tiny_pkg/maths.py": b"def increment(value: int) -> int:\n    return value - 1\n",
            "tests/test_maths.py": _PUBLIC_TEST,
        },
        "documentation-aligned",
    ),
    _TaskSeed(
        "dependency-free-refactor",
        "Inline the increment behavior and remove the obsolete local implementation dependency.",
        ("behavior remains locked while legacy.py is eliminated",),
        {
            "tiny_pkg/__init__.py": b"from .maths import increment\n",
            "tiny_pkg/legacy.py": (
                b"def increment_impl(value: int) -> int:\n    return value - 1\n"
            ),
            "tiny_pkg/maths.py": (
                b"from .legacy import increment_impl\n\n"
                b"def increment(value: int) -> int:\n"
                b"    return increment_impl(value)\n"
            ),
            "tests/test_maths.py": _PUBLIC_TEST,
        },
        "legacy-eliminated",
    ),
)


def _git(root: Path, *args: str, date: str | None = None) -> str:
    environment = dict(os.environ)
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
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
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "benchmark corpus Git command failed: "
            + completed.stderr.decode("utf-8", "replace")
        )
    return completed.stdout.decode("utf-8", "strict").strip()


def _canonical_digest(value: object) -> str:
    return sha256_digest(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _tree_digest(files: Mapping[str, bytes]) -> str:
    inventory = [
        {"path": path, "digest": sha256_digest(content)}
        for path, content in sorted(files.items())
    ]
    return _canonical_digest(inventory)


def _checker_digest(checker_id: str) -> str:
    return sha256_digest(f"p13-hidden-check:v1:{checker_id}".encode())


def build_corpus(
    root: str | Path,
    *,
    task_ids: Sequence[str] | None = None,
    budget: BudgetSpec = BudgetSpec(),
) -> CorpusSnapshot:
    """Build pinned repositories. ``root`` must be absent to prevent silent rewrites."""

    destination = Path(root)
    if destination.exists():
        raise FileExistsError("benchmark corpus destination already exists")
    destination.mkdir(parents=True)
    selected = set(task_ids) if task_ids is not None else None
    unknown = set(selected or ()) - {seed.task_id for seed in _TASKS}
    if unknown:
        raise ValueError("unknown benchmark task(s): " + ", ".join(sorted(unknown)))

    tasks: list[CorpusTask] = []
    for seed in _TASKS:
        if selected is not None and seed.task_id not in selected:
            continue
        repository = destination / seed.task_id
        repository.mkdir()
        _git(repository, "init", "--initial-branch=main")
        for relative, content in seed.files.items():
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        manifest = TaskManifest(
            schema_version=1,
            task_id=seed.task_id,
            family="repository-issue-to-verified-delivery",
            objective=seed.objective,
            acceptance_criteria=seed.acceptance_criteria,
            budget=budget,
            allowed_backends=("scripted",),
            hidden_check_digest=_checker_digest(seed.checker_id),
        )
        (repository / "task-manifest.json").write_text(
            json.dumps(
                manifest.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        _git(repository, "add", "--all")
        _git(
            repository,
            "commit",
            "-m",
            f"benchmark: seed {seed.task_id}",
            date=_COMMIT_DATE,
        )
        tasks.append(
            CorpusTask(
                manifest=manifest,
                repository=repository,
                base_sha=_git(repository, "rev-parse", "HEAD"),
                tree_digest=_tree_digest(
                    {**seed.files, "task-manifest.json": (
                        repository / "task-manifest.json"
                    ).read_bytes()}
                ),
                checker_id=seed.checker_id,
            )
        )
    digest = _canonical_digest(
        [
            {
                "manifest": task.manifest.to_dict(),
                "tree_digest": task.tree_digest,
            }
            for task in tasks
        ]
    )
    return CorpusSnapshot(tuple(tasks), digest)


__all__ = [
    "BudgetSpec",
    "CorpusSnapshot",
    "CorpusTask",
    "LaneTask",
    "TaskManifest",
    "build_corpus",
]
