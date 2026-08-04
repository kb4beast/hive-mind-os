from __future__ import annotations

from pathlib import Path

from .catalog import PackageCatalog


def hive_core_root() -> Path:
    """Return the explicit built-in package root without loading or activating it."""

    return Path(__file__).resolve().parents[2] / "builtin_packages" / "hive-core"


def hive_core_catalog() -> PackageCatalog:
    return PackageCatalog.from_roots((hive_core_root(),))


__all__ = ["hive_core_catalog", "hive_core_root"]
