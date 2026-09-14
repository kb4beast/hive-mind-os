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

from hive_mind_os.runtime_contracts import canonical_json_bytes
from hive_mind_os.runtime_contracts import raw_sha256
from hive_mind_os.receipts import filesystem_path
from hive_mind_os.whole_os_bootstrap import (
    WholeOSHostFactoryRegistration,
    run_registered_whole_os,
)
from hive_mind_os.whole_os_codex_host import (
    ACCEPTANCE_ID,
    AUTHORITY_REF,
    PROVIDER_ID,
    PROVIDER_VERSION,
    build_deployment_bundle,
    compose_factory,
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
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=repository, check=True, capture_output=True)
        return repository

    def test_sealed_config_is_inert_and_factory_runs_whole_os_service(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary)
            repository = self._repository(root)
            state = root / "external-state"
            executable = root / ("codex-test.exe" if sys.platform == "win32" else "codex-test")
            shutil.copy2(sys.executable, executable)
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
            bundle = build_deployment_bundle(
                repository=repository,
                state_root=state,
                codex_executable=executable,
                tenant_id="tenant-test",
                repository_id="repository-test",
                observed_codex=("v1.0.0", probe),
            )
            config = json.loads(bundle.config_path.read_text(encoding="utf-8"))
            serialized = json.dumps(config).casefold()
            for forbidden in ("import", "callback", "command", "credential", "secret", "token"):
                self.assertNotIn(forbidden, serialized)
            self.assertEqual(config["graph"]["packages"][0]["acceptance_ids"], [ACCEPTANCE_ID])

            focused_directory = state / "focused"
            focused_directory.mkdir(parents=True)
            focused = {
                "status": "PASSED",
                "receipt_digest": "sha256:" + "a" * 64,
            }
            focused_path = focused_directory / "receipt.json"
            focused_path.write_bytes(canonical_json_bytes(focused) + b"\n")
            curator_directory = state / "curator"
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
            self.assertEqual(observation["status"], "complete")
            self.assertEqual(observation["completed_packages"], ["host-bootstrap-startup"])
            self.assertEqual(len(worker.calls), 1)
            self.assertFalse(worker.calls[0]["writable"])
            self.assertEqual(len(builder_paths), 1)
            self.assertTrue((state / "learning").is_dir())
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


if __name__ == "__main__":
    unittest.main()
