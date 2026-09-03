from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from hive_mind_os.dag_executor import (
    DagExecutionError,
    DagExecutor,
    ExecutionJournal,
    RunState,
)
from hive_mind_os.host_runtime import HostOperationJournal
from hive_mind_os.portable_plan import (
    NonRepositorySubject,
    RepositorySubject,
    SubjectBinding,
)
from hive_mind_os.runtime_contracts import canonical_digest, raw_sha256
from hive_mind_os.subject_adapter import (
    SubjectDescriptor,
    SubjectKind,
    SubjectSnapshot,
    require_snapshot_binding,
)
from hive_mind_os.subject_execution import SubjectExecutionMode, SubjectExecutionService
from tests.test_dag_executor import NOW, FakeHost, request_for, runtime
from tests.test_dag_standard_product import STANDARD, compiler_plan

FIXTURES = {
    "python": ({"src/app.py": b"print('fixture')\n"}, SubjectKind.REPOSITORY),
    "node-typescript": (
        {"package.json": b'{"private":true}\n', "src/index.ts": b"export const n = 1;\n"},
        SubjectKind.REPOSITORY,
    ),
    "csharp": (
        {"App.csproj": b"<Project />\n", "Program.cs": b"class Program {}\n"},
        SubjectKind.REPOSITORY,
    ),
    "rust": (
        {"Cargo.toml": b"[package]\nname='fixture'\n", "src/lib.rs": b"pub fn n(){}\n"},
        SubjectKind.REPOSITORY,
    ),
    "monorepo": (
        {"apps/a/main.go": b"package main\n", "packages/b/lib.py": b"VALUE = 1\n"},
        SubjectKind.REPOSITORY,
    ),
    "documentation-only": ({"README.md": b"# Fixture\n"}, SubjectKind.ARTIFACT),
    "no-test": ({"src/tool.go": b"package tool\n"}, SubjectKind.REPOSITORY),
    "target-advancing": ({"change.txt": b"disposable candidate\n"}, SubjectKind.REPOSITORY),
    "offline-local": ({"artifact.bin": b"offline\x00fixture"}, SubjectKind.ARTIFACT),
    "research-artifact": ({"result.json": b'{"finding":"bounded"}\n'}, SubjectKind.DATASET),
    "workflow": ({"workflow.yml": b"steps: []\n"}, SubjectKind.WORKFLOW),
}


def materialize(root: Path, files: dict[str, bytes]) -> str:
    inventory = []
    for relative, body in sorted(files.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        inventory.append({"path": relative, "sha256": raw_sha256(body)})
    return canonical_digest(inventory)


def bound_plan(name: str, content_digest: str, kind: SubjectKind):
    plan = compiler_plan()
    if kind is SubjectKind.REPOSITORY:
        commit = sha256((name + ":commit").encode()).hexdigest()[:40]
        tree = sha256((name + ":tree").encode()).hexdigest()[:40]
        subject = SubjectBinding.for_repository(
            RepositorySubject(canonical_digest({"fixture": name}), commit, tree, "main")
        )
    else:
        subject = SubjectBinding.for_non_repository(
            NonRepositorySubject(kind.value, canonical_digest({"fixture": name}), content_digest)
        )
    return replace(plan, subject=subject)


class GenericDagFixtureTests(unittest.TestCase):
    def test_cross_language_and_non_repository_matrix_uses_public_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            standard = root / "standard.md"
            standard.write_bytes(STANDARD)
            service = SubjectExecutionService()
            observed = []
            for name, (files, kind) in FIXTURES.items():
                with self.subTest(subject=name):
                    subject_root = root / name
                    subject_root.mkdir()
                    content_digest = materialize(subject_root, files)
                    descriptor = SubjectDescriptor(
                        f"fixture-{name}",
                        kind,
                        f"fixture/{name}",
                        ("snapshot",),
                        canonical_digest({"authority": "inert"}),
                        ("evidence:fixture-license",),
                    )
                    snapshot = SubjectSnapshot(
                        descriptor,
                        f"snapshot:{name}",
                        content_digest,
                        "2026-09-02T00:00:00Z",
                        ("evidence:fixture-content",),
                    )
                    self.assertIs(snapshot, require_snapshot_binding(descriptor, snapshot))
                    plan = bound_plan(name, content_digest, kind)
                    plan_path = subject_root / "portable-plan.json"
                    plan_path.write_bytes(plan.canonical_bytes())
                    mode = (
                        SubjectExecutionMode.REPOSITORY
                        if kind is SubjectKind.REPOSITORY
                        else SubjectExecutionMode.WORKFLOW
                        if kind is SubjectKind.WORKFLOW
                        else SubjectExecutionMode.RESEARCH_ARTIFACT
                        if kind is SubjectKind.DATASET
                        else SubjectExecutionMode.OFFLINE_LOCAL
                    )
                    inspection = service.validate_files(
                        plan_path=plan_path.resolve(),
                        standard_path=standard.resolve(),
                        expected_plan_digest=plan.digest(),
                        expected_subject_id=plan.subject.subject_id,
                        mode=mode,
                    )
                    repeated = service.validate_files(
                        plan_path=plan_path.resolve(),
                        standard_path=standard.resolve(),
                        expected_plan_digest=plan.digest(),
                        expected_subject_id=plan.subject.subject_id,
                        mode=mode,
                    )
                    self.assertEqual(inspection, repeated)
                    observed.append(name)
            self.assertEqual(set(FIXTURES), set(observed))

    def test_repository_executes_and_repository_scoped_activation_rejects_artifact(
        self,
    ) -> None:
        for name in ("python", "research-artifact"):
            with self.subTest(subject=name):
                files, kind = FIXTURES[name]
                content = canonical_digest(
                    [{"path": path, "sha256": raw_sha256(body)} for path, body in sorted(files.items())]
                )
                plan = bound_plan(name, content, kind)
                host = FakeHost()
                host_journal = HostOperationJournal()
                execution_journal = ExecutionJournal()
                self.addCleanup(host_journal.close)
                self.addCleanup(execution_journal.close)
                executor = DagExecutor(
                    runtime(host, host_journal), execution_journal, clock=lambda: NOW
                )
                request = request_for(plan, nonce=name)
                if kind is SubjectKind.REPOSITORY:
                    result = SubjectExecutionService(executor).execute(request)
                    self.assertEqual(RunState.COMPLETED, result.state)
                    self.assertEqual(8, len(host.calls))
                else:
                    with self.assertRaisesRegex(
                        DagExecutionError, "repository-scoped activation"
                    ):
                        SubjectExecutionService(executor).execute(request)
                    self.assertEqual(0, host.prepare_calls)
                    self.assertEqual([], host.calls)

    def test_fixture_inventory_forbids_live_external_capabilities(self) -> None:
        forbidden = {
            "credential", "payment", "push", "pull-request", "comment",
            "deployment", "production", "protected-target",
        }
        plan = compiler_plan()
        operations = {capability.operation for capability in plan.capabilities}
        self.assertTrue(operations.isdisjoint(forbidden))
        self.assertTrue(all(not authority.external_effects for authority in plan.authority))


if __name__ == "__main__":
    unittest.main()
