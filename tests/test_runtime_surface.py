from __future__ import annotations

import ast
import unittest
from pathlib import Path

import hive_mind_os

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "hive_mind_os"
FROZEN_MODULES = {
    "classic_gpt": "reference/classic_gpt.py",
    "vision": "reference/vision.py",
    "package_system": "reference/package_system/__init__.py",
}


class RuntimeSurfaceTests(unittest.TestCase):
    def test_frozen_subsystems_are_reference_only(self) -> None:
        for module, relative_path in FROZEN_MODULES.items():
            legacy = PACKAGE_ROOT / module
            if module != "package_system":
                legacy = legacy.with_suffix(".py")
            self.assertFalse(legacy.exists())
            reference = PACKAGE_ROOT / relative_path
            self.assertTrue(reference.is_file())
            self.assertIn(
                "Reference implementation. No runtime consumer. Not a gate.",
                ast.get_docstring(ast.parse(reference.read_text(encoding="utf-8")))
                or "",
            )

    def test_every_public_export_has_a_runtime_or_reference_path(self) -> None:
        module = ast.parse((PACKAGE_ROOT / "__init__.py").read_text(encoding="utf-8"))
        bindings = {
            alias.asname or alias.name: import_from.module
            for import_from in module.body
            if isinstance(import_from, ast.ImportFrom) and import_from.module
            for alias in import_from.names
        }
        for name in hive_mind_os.__all__:
            if name == "__version__":
                continue
            module_name = bindings.get(name)
            self.assertIsNotNone(module_name, name)
            relative = Path(*str(module_name).lstrip(".").split("."))
            module_path = PACKAGE_ROOT / relative
            resolved = module_path.with_suffix(".py")
            if not resolved.is_file():
                resolved = module_path / "__init__.py"
            self.assertTrue(
                resolved.is_file() and (
                    "reference" in resolved.parts or PACKAGE_ROOT in resolved.parents
                ),
                name,
            )
