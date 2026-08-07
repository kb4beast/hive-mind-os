from __future__ import annotations

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hive_mind_os.brain_kernel.context import (
    ContextCompiler,
    ContextManifestStore,
    ContextRequest,
)
from hive_mind_os.brain_kernel.contracts import MemoryRecord, MemoryState
from hive_mind_os.brain_kernel.memory import (
    MemoryAccess,
    MemoryArtifactStore,
    MemoryCatalog,
    MemoryCatalogStore,
)
from hive_mind_os.cli import (
    _run_kernel_context,
    _run_kernel_memory_expire,
    _run_kernel_memory_inspect,
    _run_kernel_memory_search,
    build_kernel_parser,
)

DIGEST = "sha256:" + "0" * 64
TIME = "2026-08-07T12:00:00Z"
LATER = "2026-08-08T12:00:00Z"


class KernelMemoryCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        artifacts = MemoryArtifactStore(self.root)
        artifact = artifacts.put("local durable evidence")
        self.catalog = MemoryCatalog(artifacts)
        self.catalog.register(
            MemoryRecord(
                "MEMORY-one", "fact", "mission", ("MISSION-one",), artifact.digest,
                ("SRC-one",), "verified", "internal", TIME, None, TIME, TIME,
                MemoryState.ACTIVE, (), (), None, (), "retain", DIGEST,
            ),
            MemoryAccess(("builder",), ("internal",)),
        )
        self.snapshot = MemoryCatalogStore(self.root).persist(self.catalog)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_local_memory_search_inspect_expire_and_context_commands(self) -> None:
        common = {"snapshot": self.snapshot, "state_dir": str(self.root), "json_output": True}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(
                0,
                _run_kernel_memory_search(
                    argparse.Namespace(
                        **common,
                        mission="MISSION-one", work="WORK-one", role="builder", query="evidence", now=LATER,
                        data_scope=["internal"], sensitivity_scope=["public", "internal"],
                        require_sensitivity=[], repository_key=None,
                    )
                ),
            )
        self.assertIn("MEMORY-one", stdout.getvalue())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, _run_kernel_memory_inspect(argparse.Namespace(**common, record_id="MEMORY-one")))
        self.assertNotIn("local durable evidence", stdout.getvalue())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, _run_kernel_memory_expire(argparse.Namespace(**common, now=LATER)))
        self.assertIn("snapshot", stdout.getvalue())

        manifests = ContextManifestStore(self.root)
        compiled = ContextCompiler(self.catalog, manifests).compile(
            ContextRequest(
                "MISSION-one", "WORK-one", "ATTEMPT-one", "builder", DIGEST, DIGEST,
                40, "evidence", LATER, ("internal",), (),
            )
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(
                0,
                _run_kernel_context(
                    argparse.Namespace(state_dir=str(self.root), manifest=compiled.manifest.manifest_digest, json_output=True)
                ),
            )
        self.assertIn(compiled.manifest.manifest_digest, stdout.getvalue())

    def test_kernel_parser_exposes_only_local_memory_and_context_commands(self) -> None:
        parser = build_kernel_parser()
        memory = parser.parse_args(
            ["memory", "inspect", "MEMORY-one", "--snapshot", DIGEST, "--state-dir", "state"]
        )
        self.assertEqual("memory", memory.kernel_command)
        self.assertEqual("inspect", memory.memory_command)
        context = parser.parse_args(["context", "--manifest", DIGEST, "--state-dir", "state"])
        self.assertEqual("context", context.kernel_command)
