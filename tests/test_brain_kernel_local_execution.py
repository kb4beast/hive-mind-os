from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.authority import AuthorityDenied
from hive_mind_os.cortex.repository.local_execution import (
    LocalWorkspaceAdapter,
    run_sealed_builder_curator_fixture,
)


class LocalKernelExecutionTests(unittest.TestCase):
    def test_builder_uses_an_isolated_gateway_write_and_curator_verifies_after_seal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_sealed_builder_curator_fixture(root)
            self.assertEqual("adopt", result.verdict)
            self.assertLess(result.seal_sequence, result.candidate_access_sequence)
            self.assertNotEqual(result.builder.executor_id, result.curator.executor_id)
            self.assertTrue(result.builder.effect_receipt_refs)
            self.assertEqual("before\n", (root / "base" / "app.txt").read_text())
            self.assertEqual("after\n", (root / "candidate" / "app.txt").read_text())

    def test_workspace_adapter_refuses_path_escape_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = LocalWorkspaceAdapter(root)
            with self.assertRaises(AuthorityDenied):
                adapter.write("../outside.txt", b"no")
            self.assertFalse((root.parent / "outside.txt").exists())
