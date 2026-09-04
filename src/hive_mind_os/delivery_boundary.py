"""Fail-closed separation between HiveMind orchestration and delivered code.

HiveMind may use a tournament DAG to create and execute implementation work
outside a target repository.  A delivery may not, however, make the target
depend on HiveMind's runtime, workspace, or plan-directory conventions.  This
module checks only dependencies introduced by a delivery; it deliberately does
not prohibit a target's independent use of generic graph algorithms.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from .receipts import portable_path_parts


class DeliveryBoundaryError(ValueError):
    """A target delivery depends on HiveMind orchestration artifacts."""


_SOURCE_SUFFIXES = frozenset(
    {
        ".bat",
        ".c",
        ".cc",
        ".cfg",
        ".cjs",
        ".cmd",
        ".conf",
        ".cpp",
        ".cs",
        ".css",
        ".go",
        ".h",
        ".hpp",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".kt",
        ".kts",
        ".mjs",
        ".php",
        ".ps1",
        ".py",
        ".pyi",
        ".rb",
        ".rs",
        ".sh",
        ".swift",
        ".txt",
        ".toml",
        ".ts",
        ".tsx",
        ".vue",
        ".xml",
        ".yaml",
        ".yml",
    }
)
_HIVEMIND_WORKSPACE_PARTS = frozenset({".hive-mind", ".hivemind"})
_HIVEMIND_RUNTIME_MARKERS = (b"hive_mind_os", b"hive-mind-os")
_SOURCE_MARKERS: tuple[tuple[bytes, str], ...] = (
    (b".hive-mind", "HiveMind workspace reference"),
    (b".hivemind", "HiveMind workspace reference"),
    (b"brain/plans/dags/", "DAG plan-directory reference"),
    (b"plans/dags/", "DAG plan-directory reference"),
)


def external_delivery_boundary_findings(
    entries: Iterable[tuple[str, bytes]],
    *,
    allow_hivemind_runtime_dependencies: bool = False,
) -> tuple[str, ...]:
    """Return deterministic violations in files introduced by one delivery.

    ``entries`` must contain repository-relative paths and their candidate
    bytes.  The caller supplies only added or modified paths, so a HiveMind
    delivery cannot introduce an orchestration dependency while pre-existing
    target design remains an explicit, separately reviewable concern.
    """

    findings: list[str] = []
    seen: set[str] = set()
    for relative, content in entries:
        try:
            parts = portable_path_parts(relative)
        except ValueError as error:
            findings.append(f"{relative!r}: unsafe delivery path ({error})")
            continue
        if relative in seen:
            findings.append(f"{relative}: duplicate delivery path")
            continue
        seen.add(relative)
        lowered_parts = tuple(part.casefold() for part in parts)
        if any(part in _HIVEMIND_WORKSPACE_PARTS for part in lowered_parts):
            findings.append(f"{relative}: HiveMind workspace artifact")
        if any(
            lowered_parts[index : index + 2] == ("plans", "dags")
            for index in range(len(lowered_parts) - 1)
        ):
            findings.append(f"{relative}: DAG plan artifact")
        suffix = PurePosixPath(relative).suffix.casefold()
        if suffix not in _SOURCE_SUFFIXES:
            continue
        lowered_content = content.lower()
        if not allow_hivemind_runtime_dependencies and any(
            marker in lowered_content for marker in _HIVEMIND_RUNTIME_MARKERS
        ):
            findings.append(f"{relative}: HiveMind runtime dependency")
        for marker, label in _SOURCE_MARKERS:
            if marker in lowered_content:
                findings.append(f"{relative}: {label}")
    return tuple(sorted(set(findings)))


def require_external_delivery_independence(
    entries: Iterable[tuple[str, bytes]],
    *,
    allow_hivemind_runtime_dependencies: bool = False,
) -> None:
    """Reject a target delivery that embeds HiveMind orchestration state."""

    findings = external_delivery_boundary_findings(
        entries,
        allow_hivemind_runtime_dependencies=allow_hivemind_runtime_dependencies,
    )
    if findings:
        raise DeliveryBoundaryError(
            "delivery must remain independent of HiveMind orchestration: "
            + "; ".join(findings)
        )


def is_hivemind_source_tree(root: Path) -> bool:
    """Whether ``root`` is HiveMind's own source tree, not an external target."""

    package = root / "src" / "hive_mind_os"
    return package.is_dir() and not package.is_symlink()
