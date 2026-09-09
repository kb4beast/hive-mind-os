"""Filesystem boundary checks shared by tournament preparation and execution."""

from __future__ import annotations

import os
from pathlib import Path


class ExternalPathRequired(ValueError):
    """A durable orchestration path overlaps the target repository."""


def resolved_path(path: str | Path) -> Path:
    """Resolve aliases through the longest existing prefix.

    ``Path.resolve(strict=False)`` follows symlinks and Windows junctions in the
    existing portion and normalizes the non-existing suffix.  ``normcase`` is
    used for the comparison so case aliases cannot evade the boundary on
    Windows while similarly-prefixed sibling names remain distinct paths.
    """

    return Path(path).resolve(strict=False)


def is_within(path: str | Path, directory: str | Path) -> bool:
    candidate = resolved_path(path)
    boundary = resolved_path(directory)
    candidate_key = os.path.normcase(os.path.abspath(str(candidate)))
    boundary_key = os.path.normcase(os.path.abspath(str(boundary)))
    try:
        return os.path.commonpath((candidate_key, boundary_key)) == boundary_key
    except ValueError:  # Different Windows drives.
        return False


def require_external_path(
    path: str | Path,
    repository: str | Path,
    *,
    label: str,
) -> Path:
    """Return a canonical path or fail before callers perform any write."""

    candidate = resolved_path(path)
    root = resolved_path(repository)
    if is_within(candidate, root):
        raise ExternalPathRequired(f"{label} must be outside the target repository")
    return candidate


__all__ = ["ExternalPathRequired", "is_within", "require_external_path", "resolved_path"]
