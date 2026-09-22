from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hive_mind_os.receipts import filesystem_path
from hive_mind_os.runtime_contracts import canonical_json_bytes, raw_sha256
from hive_mind_os.whole_os_bootstrap import (
    WholeOSHostFactoryRegistration,
    run_registered_whole_os,
)
from hive_mind_os.whole_os_codex_host import (
    ACCEPTANCE_ID,
    AUTHORITY_REF,
    PROVIDER_ID,
    PROVIDER_VERSION,
    CodexHostBootstrapError,
    DeploymentBundle,
    _admitted_candidate_digest,
    _validated_service_candidate_digest,
    build_deployment_bundle,
    compose_factory,
    execute_trusted_launcher,
)


class _FakeWorker:
    def __init__(self) -> None:
        self.calls = []

    def run(self, **values):
        self.calls.append(values)
        directory = values["evidence_directory"]
        directory.mkdir(parents=True)
        receipt = {
            "protocol": "hive-mind-local-codex-worker-v1",
            "status": "completed",
            "session_id": f"session-{len(self.calls)}",
            "report": {
                "status": "completed",
                "summary": "real adapter seam exercised by deterministic test double",
                "findings": ["checkout is admitted"],
                "acceptance_evidence": ["git identity remained stable"],
                "ideas": [],
                "selected_idea_ids": [],
                "changed_paths": [],
                "tests": ["git identity"],
            },
            "reason": None,
        }
        (directory / "receipt.json").write_bytes(canonical_json_bytes(receipt) + b"\n")
        return receipt


class WholeOSCodexHostTests(unittest.TestCase):
    def _repository(self, root: Path) -> Path:
        repository = root / "target"
        repository.mkdir()
        subprocess.run(["git", "init", "-b", "codex/test-host"], cwd=repository, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Host Test"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.email", "host-test@example.invalid"], cwd=repository, check=True)
        (repository / "README.md").write_text("owned test repository\n", encoding="utf-8")
        contract = repository / "docs" / "plan" / "whole-os-tournament-2026-09-13"
        contract.mkdir(parents=True)
        (contract / "NODES-QUALIFICATION.md").write_text("## N28\n", encoding="utf-8")
        for relative in (
            "AGENTS.md",
            "scripts/whole-os/Invoke-WholeOSCodexService.ps1",
            "src/hive_mind_os/cortex/repository/mission_bindings.py",
            "src/hive_mind_os/local_codex_worker.py",
            "src/hive_mind_os/scheduler.py",
            "src/hive_mind_os/whole_os_bootstrap.py",
            "src/hive_mind_os/whole_os_codex_host.py",
            "src/hive_mind_os/whole_os_composition.py",
            "src/hive_mind_os/whole_os_service.py",
            "tests/test_whole_os_bootstrap.py",
            "tests/test_whole_os_codex_host.py",
            "tests/test_whole_os_powershell_pipeline.py",
        ):
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"owned fixture for {relative}\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=repository, check=True, capture_output=True)
        return repository

    def _deployment_bundle(
        self, root: Path, repository: Path, state: Path
    ) -> DeploymentBundle:
        executable = root / (
            "codex-test.exe" if sys.platform == "win32" else "codex-test"
        )
        shutil.copy2(sys.executable, executable)
        # Match the production boundary, which canonicalizes the executable
        # before comparing it with the independently retained probe. Windows
        # hosted runners can otherwise expose two spellings of the same path.
        executable = executable.resolve(strict=True)
        probe = {
            "schema_version": 1,
            "kind": "whole-os-codex-tool-probe",
            "adapter_id": "codex-cli",
            "version": "v1.0.0",
            "executable_path": str(executable),
            "binary_digest": raw_sha256(executable.read_bytes()),
            "version_output": "codex-cli 1.0.0",
            "version_output_digest": raw_sha256(b"codex-cli 1.0.0"),
            "exit_code": 0,
            "platform": sys.platform,
        }
        return build_deployment_bundle(
            repository=repository,
            state_root=state,
            codex_executable=executable,
            tenant_id="tenant-test",
            repository_id="repository-test",
            observed_codex=("v1.0.0", probe),
        )

    def test_sealed_config_is_inert_and_factory_runs_whole_os_service(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            state = root.joinpath(*(("external-state-segment",) * 8))
            bundle = self._deployment_bundle(root, repository, state)
            config = json.loads(bundle.config_path.read_text(encoding="utf-8"))
            serialized = json.dumps(config).casefold()
            for forbidden in ("import", "callback", "command", "credential", "secret", "token"):
                self.assertNotIn(forbidden, serialized)
            self.assertEqual(config["graph"]["packages"][0]["acceptance_ids"], [ACCEPTANCE_ID])

            focused_directory = filesystem_path(state / "focused")
            focused_directory.mkdir(parents=True)
            focused = {
                "status": "PASSED",
                "receipt_digest": "sha256:" + "a" * 64,
            }
            focused_path = focused_directory / "receipt.json"
            focused_path.write_bytes(canonical_json_bytes(focused) + b"\n")
            curator_directory = filesystem_path(state / "curator")
            curator = _FakeWorker().run(
                evidence_directory=curator_directory,
                workspace=repository,
            )
            curator_path = curator_directory / "receipt.json"
            worker = _FakeWorker()
            builder_paths = []
            factory = compose_factory(
                bundle=bundle,
                worker=worker,
                admission_receipt=curator,
                admission_receipt_path=curator_path,
                focused_receipt=focused,
                focused_receipt_path=focused_path,
                timeout_seconds=60,
                builder_receipts=builder_paths,
            )
            registration = WholeOSHostFactoryRegistration(
                PROVIDER_ID,
                PROVIDER_VERSION,
                bundle.descriptor.configuration_digest,
                bundle.implementation_digest,
                AUTHORITY_REF,
                ("test:deterministic-curator",),
                True,
            )
            output = io.StringIO()
            with redirect_stdout(output):
                code = run_registered_whole_os(
                    ("start", "--config", str(bundle.config_path), "--json"),
                    registration=registration,
                    factory=factory,
                )
            observation = json.loads(output.getvalue())

            self.assertEqual(code, 0)
            self.assertEqual(observation["status"], "complete", observation)
            self.assertEqual(observation["completed_packages"], ["host-bootstrap-startup"])
            self.assertEqual(len(worker.calls), 1)
            self.assertFalse(worker.calls[0]["writable"])
            self.assertEqual(len(builder_paths), 1)
            self.assertTrue(filesystem_path(state / "learning").is_dir())
            shutil.rmtree(filesystem_path(root), ignore_errors=True)

    def test_launcher_creates_a_state_root_beyond_windows_max_path(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            state = root.joinpath(*(("external-state-segment",) * 12))
            self.assertGreater(len(str(state)), 260)

            with patch(
                "hive_mind_os.whole_os_codex_host.build_deployment_bundle",
                side_effect=CodexHostBootstrapError("stop after state-root creation"),
            ):
                code, receipt = execute_trusted_launcher(
                    repository=repository,
                    state_root=state,
                    executable=Path(sys.executable),
                )

            self.assertEqual(code, 20)
            self.assertIn("stop after state-root creation", receipt["blocker"])
            self.assertEqual(receipt["schema_version"], 2)
            self.assertEqual(
                receipt["claim_scope"], "full-autonomy-or-superiority"
            )
            self.assertIsNone(receipt["candidate_digest"])
            self.assertIsNone(receipt["service_candidate_digest"])
            self.assertTrue(filesystem_path(state).is_dir())
            self.assertTrue(filesystem_path(Path(receipt["receipt_path"])).is_file())
            shutil.rmtree(filesystem_path(root), ignore_errors=True)

    def test_launcher_rejects_unknown_claim_scope_before_writing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            state = root / "rejected-state"

            with self.assertRaisesRegex(CodexHostBootstrapError, "claim scope"):
                execute_trusted_launcher(
                    repository=repository,
                    state_root=state,
                    claim_scope="invented-scope",
                )

            self.assertFalse(state.exists())

    def test_blocked_receipt_retains_the_admitted_candidate(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            state = root / "external-state"
            bundle = self._deployment_bundle(root, repository, state)
            expected = _admitted_candidate_digest(bundle)

            with (
                patch(
                    "hive_mind_os.whole_os_codex_host.build_deployment_bundle",
                    return_value=bundle,
                ),
                patch(
                    "hive_mind_os.whole_os_codex_host._focused_verification",
                    side_effect=CodexHostBootstrapError(
                        "stop after candidate admission"
                    ),
                ),
            ):
                code, receipt = execute_trusted_launcher(
                    repository=repository,
                    state_root=state,
                    executable=bundle.codex_executable,
                    claim_scope="bounded-operational-production-pilot",
                )

            self.assertEqual(code, 20)
            self.assertEqual(receipt["candidate_digest"], expected)
            self.assertIsNone(receipt["service_candidate_digest"])
            self.assertEqual(
                receipt["claim_scope"], "bounded-operational-production-pilot"
            )
            shutil.rmtree(filesystem_path(root), ignore_errors=True)

    def test_terminal_candidate_must_match_the_admitted_checkout(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            bundle = self._deployment_bundle(root, repository, root / "state")
            expected = _admitted_candidate_digest(bundle)

            self.assertEqual(
                _validated_service_candidate_digest(
                    bundle, {"last_result": {"candidate_digest": expected}}
                ),
                expected,
            )
            invalid_outputs = (
                {},
                {"last_result": {}},
                {"last_result": {"candidate_digest": "bad"}},
                {
                    "last_result": {
                        "candidate_digest": "sha256:" + "0" * 64
                    }
                },
            )
            for output in invalid_outputs:
                with self.subTest(output=output), self.assertRaises(
                    CodexHostBootstrapError
                ):
                    _validated_service_candidate_digest(bundle, output)

            shutil.rmtree(filesystem_path(root), ignore_errors=True)

    def test_dirty_or_non_codex_branch_is_not_admitted(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            (repository / "untracked.txt").write_text("not admitted\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "clean"):
                build_deployment_bundle(
                    repository=repository,
                    state_root=root / "state",
                    codex_executable=Path(sys.executable),
                    tenant_id="tenant-test",
                    repository_id="repository-test",
                )

    def test_launcher_rejects_repository_state_before_writing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            rejected_state = repository / "state"

            with self.assertRaisesRegex(
                CodexHostBootstrapError, "no receipt was written"
            ):
                execute_trusted_launcher(
                    repository=repository,
                    state_root=rejected_state,
                    tenant_id="tenant-test",
                    repository_id="repository-test",
                    timeout_seconds=60,
                )

            self.assertFalse(rejected_state.exists())


if __name__ == "__main__":
    unittest.main()
