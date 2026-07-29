from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import phase3_obsidian_refresh_fixture as fixture
from scripts.phase3_obsidian_vault_refresh_inventory import (
    FAILED_RUNS,
    PASSING_RUN,
    RUN_ROOT,
    TARGET_PATHS,
    build_phase3_item5_inventory,
)


class ObsidianVaultRefreshEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).parents[1]

    def test_both_failed_integrity_runs_are_preserved(self) -> None:
        expected = (
            "item4-generated-byte-integrity",
            "item4-delayed-generated-byte-integrity",
        )
        for run_id, failed_case in zip(FAILED_RUNS, expected, strict=True):
            with self.subTest(run_id=run_id):
                run = json.loads(
                    (
                        self.repository / RUN_ROOT / run_id / "run.json"
                    ).read_text(encoding="utf-8")
                )
                failed = [
                    case for case in run["cases"] if case["verdict"] == "fail"
                ]
                self.assertEqual(run["verdict"], "fail")
                self.assertEqual(
                    [case["case_id"] for case in failed],
                    [failed_case],
                )
                self.assertNotEqual(
                    failed[0]["projector_sha256"],
                    failed[0]["after_obsidian_sha256"],
                )

    def test_passing_run_is_bounded_and_preserves_bytes(self) -> None:
        run = json.loads(
            (
                self.repository / RUN_ROOT / PASSING_RUN / "run.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(run["verdict"], "pass")
        self.assertEqual(run["test_window_seconds"], 15)
        self.assertTrue(
            all(
                case.get("latency_seconds", 0) <= 15
                for case in run["cases"]
            )
        )
        integrity = next(
            case
            for case in run["cases"]
            if case["case_id"] == "item4-generated-byte-integrity"
        )
        self.assertEqual(integrity["item4_check_status"], "unchanged")
        self.assertEqual(integrity["conflict_paths"], [])
        self.assertEqual(integrity["stability_interval_seconds"], 300)
        self.assertEqual(integrity["baseline_targets"], run["final_targets"])
        self.assertEqual(tuple(run["final_targets"]), TARGET_PATHS)
        self.assertFalse(any(run["prohibited_actions"].values()))

    def test_inventory_matches_current_evidence(self) -> None:
        committed = json.loads(
            (
                self.repository
                / "evidence"
                / "phase3"
                / "phase3_obsidian_vault_refresh_inventory.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            build_phase3_item5_inventory(self.repository),
            committed,
        )


class ObsidianRefreshFixtureBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.clone = self.root / "clone"
        self.state = self.root / "state"
        subprocess.run(("git", "init", str(self.source)), check=True, capture_output=True)
        subprocess.run(
            ("git", "-C", str(self.source), "config", "user.email", "test@example.test"),
            check=True,
        )
        subprocess.run(
            ("git", "-C", str(self.source), "config", "user.name", "Test"),
            check=True,
        )
        (self.source / ".gitignore").write_text(".obsidian/\n", encoding="utf-8")
        (self.source / "tracked.txt").write_text("fixture\n", encoding="utf-8")
        subprocess.run(
            ("git", "-C", str(self.source), "add", ".gitignore", "tracked.txt"),
            check=True,
        )
        subprocess.run(
            ("git", "-C", str(self.source), "commit", "-m", "fixture"),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "clone", "--no-hardlinks", str(self.source), str(self.clone)),
            check=True,
            capture_output=True,
        )
        self.subject = subprocess.run(
            ("git", "-C", str(self.clone), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_fixture_derives_and_persists_exact_clone_identity(self) -> None:
        registration = fixture._validate_fixture(
            self.clone,
            self.source,
            self.state,
            command="initialize",
            claimed_subject_commit=self.subject,
        )
        self.state.mkdir()
        (self.state / fixture.FIXTURE_REGISTRATION).write_text(
            json.dumps(registration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        repeated = fixture._validate_fixture(
            self.clone,
            self.source,
            self.state,
            command="append",
            claimed_subject_commit=None,
        )
        self.assertEqual(repeated, registration)
        self.assertEqual(registration["subject_commit"], self.subject)
        self.assertGreater(registration["no_hardlink_file_count"], 0)

    def test_fixture_rejects_source_worktree_and_hardlinks(self) -> None:
        with self.assertRaisesRegex(SystemExit, "separate clone"):
            fixture._validate_fixture(
                self.source,
                self.source,
                self.state,
                command="initialize",
                claimed_subject_commit=self.subject,
            )
        clone_file = self.clone / "tracked.txt"
        clone_file.unlink()
        os.link(self.source / "tracked.txt", clone_file)
        with self.assertRaisesRegex(SystemExit, "hardlinked"):
            fixture._validate_fixture(
                self.clone,
                self.source,
                self.state,
                command="initialize",
                claimed_subject_commit=self.subject,
            )


if __name__ == "__main__":
    unittest.main()
