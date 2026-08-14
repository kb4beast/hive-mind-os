from __future__ import annotations

import unittest
from importlib.resources import files
from pathlib import Path

import hive_mind_os


class SourceAffinityTests(unittest.TestCase):
    def test_bare_python_uses_this_checkout(self) -> None:
        expected = (Path(__file__).resolve().parents[1] / "src" / "hive_mind_os").resolve()
        observed = Path(hive_mind_os.__file__).resolve()
        self.assertTrue(observed.is_relative_to(expected), f"foreign Hive Mind import: {observed}")

    def test_package_resources_share_the_same_source_tree(self) -> None:
        schema = files("hive_mind_os").joinpath(
            "schemas",
            "mission-state.schema.json",
        )
        self.assertTrue(schema.is_file())
        observed = Path(str(schema)).resolve()
        expected = (Path(__file__).resolve().parents[1] / "src" / "hive_mind_os").resolve()
        self.assertTrue(observed.is_relative_to(expected), f"foreign package resource: {observed}")


if __name__ == "__main__":
    unittest.main()
