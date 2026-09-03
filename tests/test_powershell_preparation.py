import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from hive_mind_os.powershell_preparation import (
    PowerShellPreparationError,
    prepare_read_only_powershell,
)


class PowerShellPreparationTests(unittest.TestCase):
    def test_preparation_is_inert_bounded_and_quotes_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            client = root / "hive-mind.exe"
            client.write_bytes(b"pinned inert fixture client")
            client_digest = "sha256:" + sha256(client.read_bytes()).hexdigest()
            prepared = prepare_read_only_powershell(
                subject="O'Brien docs",
                plan_path=root / "plan with spaces.json",
                expected_plan_digest="sha256:" + "a" * 64,
                state_directory=root / "state with spaces",
                execution_client_path=client,
                expected_execution_client_digest=client_digest,
            )
            document = prepared.to_document()
            self.assertFalse(document["execution_authorized"])
            self.assertIn("O''Brien docs", prepared.text)
            self.assertIn("'dag' 'validate'", prepared.text)
            self.assertIn("'dag' 'rounds'", prepared.text)
            self.assertIn("'dag' 'status'", prepared.text)
            self.assertEqual(str(client.resolve()), document["execution_client_path"])
            self.assertEqual(client_digest, document["execution_client_digest"])
            self.assertIn("Get-FileHash", prepared.text)
            self.assertIn("& $client", prepared.text)
            self.assertNotIn("hive-mind dag", prepared.text)
            for forbidden in ("dag execute", "git push", "gh pr", "Invoke-Expression"):
                self.assertNotIn(forbidden, prepared.text)

    def test_injection_and_bad_digest_are_rejected(self) -> None:
        client = Path(__file__).resolve()
        client_digest = "sha256:" + sha256(client.read_bytes()).hexdigest()
        with self.assertRaises(PowerShellPreparationError):
            prepare_read_only_powershell(
                subject="line1\nline2", plan_path="plan.json",
                expected_plan_digest="sha256:" + "a" * 64, state_directory="state",
                execution_client_path=client,
                expected_execution_client_digest=client_digest,
            )
        with self.assertRaises(PowerShellPreparationError):
            prepare_read_only_powershell(
                subject="ok", plan_path="plan.json", expected_plan_digest="bad",
                state_directory="state",
                execution_client_path=client,
                expected_execution_client_digest=client_digest,
            )

    def test_relative_paths_are_rejected_instead_of_resolved_from_ambient_cwd(self) -> None:
        digest = "sha256:" + "a" * 64
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            client = root / "hive-mind.exe"
            client.write_bytes(b"fixture client")
            client_digest = "sha256:" + sha256(client.read_bytes()).hexdigest()
            cases = (
                ({"plan_path": "plan.json", "state_directory": root}, "plan_path"),
                (
                    {
                        "plan_path": root / "plan.json",
                        "standard_path": "standard.md",
                        "state_directory": root,
                    },
                    "standard_path",
                ),
                (
                    {"plan_path": root / "plan.json", "state_directory": "state"},
                    "state_directory",
                ),
            )
            for paths, label in cases:
                with self.subTest(label=label):
                    with self.assertRaisesRegex(PowerShellPreparationError, label):
                        prepare_read_only_powershell(
                            subject="bounded fixture",
                            expected_plan_digest=digest,
                            execution_client_path=client,
                            expected_execution_client_digest=client_digest,
                            **paths,
                        )

    def test_execution_client_must_be_absolute_readable_and_digest_bound(self) -> None:
        digest = "sha256:" + "a" * 64
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            plan = root / "plan.json"
            state = root / "state"
            client = root / "hive-mind.exe"
            client.write_bytes(b"fixture client")
            client_digest = "sha256:" + sha256(client.read_bytes()).hexdigest()
            common = {
                "subject": "bounded fixture",
                "plan_path": plan,
                "expected_plan_digest": digest,
                "state_directory": state,
            }
            with self.assertRaisesRegex(PowerShellPreparationError, "absolute"):
                prepare_read_only_powershell(
                    **common,
                    execution_client_path="hive-mind.exe",
                    expected_execution_client_digest=client_digest,
                )
            with self.assertRaisesRegex(PowerShellPreparationError, "readable file"):
                prepare_read_only_powershell(
                    **common,
                    execution_client_path=root / "missing.exe",
                    expected_execution_client_digest=client_digest,
                )
            with self.assertRaisesRegex(PowerShellPreparationError, "do not match"):
                prepare_read_only_powershell(
                    **common,
                    execution_client_path=client,
                    expected_execution_client_digest="sha256:" + "f" * 64,
                )


if __name__ == "__main__":
    unittest.main()
