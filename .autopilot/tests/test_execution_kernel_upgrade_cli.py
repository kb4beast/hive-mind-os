from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))


def _load_autopilot():
    spec = importlib.util.spec_from_file_location(
        "execution_kernel_upgrade_autopilot", BIN / "autopilot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


autopilot = _load_autopilot()


class ExecutionKernelUpgradeCliTests(unittest.TestCase):
    def test_host_torn_tail_recovery_is_available_without_a_repository_plane(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            host_runtime = Path(temp).resolve() / "host-runtime"
            receipt = {
                "kind": "hive-mind-host-authority-torn-tail-complete-v1",
                "record_id": "sha256:" + "7" * 64,
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "recover_host_authority_jsonl_torn_tail",
                    return_value=receipt,
                ) as recover,
                mock.patch.object(
                    autopilot,
                    "resolve_host_runtime_dir",
                    return_value=host_runtime,
                ),
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--host-runtime-dir",
                        str(host_runtime),
                        "host-runtime-recover-torn-tail",
                        "--ledger-kind",
                        "repository-registry",
                        "--actor",
                        "recovery-test",
                        "--reason",
                        "power-loss tail repair",
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            recover.assert_called_once_with(
                str(host_runtime),
                ledger_kind="repository-registry",
                actor="recovery-test",
                reason="power-loss tail repair",
                host_id=None,
            )
            document = json.loads(output.getvalue())
            self.assertEqual(document["outcome"], "RECOVERED")
            self.assertEqual(document["receipt"], receipt)

    def test_host_upgrade_bypasses_execution_plane(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            host_runtime = root / "host-runtime"
            generation = "sha256:" + "4" * 64
            successor = {
                "schema_version": 1,
                "kind": "hive-mind-host-runtime-identity-v1",
                "host_kernel_generation": "sha256:" + "5" * 64,
                "record_id": "sha256:" + "6" * 64,
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "upgrade_host_runtime_kernel",
                    return_value=successor,
                ) as upgrade,
                mock.patch.object(
                    autopilot,
                    "resolve_host_runtime_dir",
                    return_value=host_runtime,
                ) as resolve_host,
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--host-runtime-dir",
                        str(host_runtime),
                        "host-runtime-upgrade",
                        "--actor",
                        "upgrade-test",
                        "--reason",
                        "install canonical host writer",
                        "--expected-host-kernel-generation",
                        generation,
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            upgrade.assert_called_once_with(
                str(host_runtime),
                actor="upgrade-test",
                reason="install canonical host writer",
                expected_host_kernel_generation=generation,
            )
            resolve_host.assert_called_once_with(str(host_runtime))
            document = json.loads(output.getvalue())
            self.assertEqual(
                document["kind"], "hive-mind-host-kernel-upgrade-result-v1"
            )
            self.assertEqual(document["identity"], successor)

    def test_upgrade_bypasses_stale_plane_and_preserves_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            coordination = root / "coordination"
            host_runtime = root / "host-runtime"
            execution_id = "sha256:" + "1" * 64
            expected_record_id = "sha256:" + "2" * 64
            successor = {
                "schema_version": 1,
                "kind": "hive-mind-execution-identity-v1",
                "execution_id": execution_id,
                "namespace": "candidate-two",
                "record_id": "sha256:" + "3" * 64,
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    autopilot,
                    "resolve_repository_state_dir",
                    return_value=coordination,
                ) as resolve_repository,
                mock.patch.object(
                    autopilot,
                    "resolve_host_runtime_dir",
                    return_value=host_runtime,
                ) as resolve_host,
                mock.patch.object(
                    autopilot,
                    "upgrade_execution_namespace_kernel",
                    return_value=successor,
                ) as upgrade,
                mock.patch.object(autopilot, "ControlPlane") as control_plane,
                contextlib.redirect_stdout(output),
            ):
                code = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "--state-dir",
                        str(coordination),
                        "--host-runtime-dir",
                        str(host_runtime),
                        "--execution-namespace",
                        "candidate-two",
                        "execution-kernel-upgrade",
                        "--execution-id",
                        execution_id,
                        "--expected-identity-record-id",
                        expected_record_id,
                        "--actor",
                        "upgrade-test",
                        "--reason",
                        "install frozen candidate",
                    ]
                )

            self.assertEqual(code, 0)
            control_plane.assert_not_called()
            resolve_repository.assert_called_once_with(root, str(coordination))
            resolve_host.assert_called_once_with(str(host_runtime))
            upgrade.assert_called_once_with(
                root,
                coordination,
                host_runtime_dir=host_runtime,
                execution_namespace="candidate-two",
                execution_id=execution_id,
                actor="upgrade-test",
                reason="install frozen candidate",
                expected_identity_record_id=expected_record_id,
            )
            document = json.loads(output.getvalue())
            self.assertEqual(
                document["kind"],
                "hive-mind-execution-kernel-upgrade-result-v1",
            )
            self.assertEqual(document["identity"], successor)
            self.assertEqual(document["execution_namespace"], "candidate-two")


if __name__ == "__main__":
    unittest.main()
