from __future__ import annotations

import json
import os
import subprocess
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import phase3_obsidian_refresh_fixture as fixture
from scripts.phase3_obsidian_vault_refresh_inventory import (
    FAILED_RUNS,
    PASSING_RUN,
    RUN_ROOT,
    SUPERSEDED_RUNS,
    TARGET_PATHS,
    _bounded_file,
    _validate_passing_run,
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

    def test_prior_pass_is_preserved_as_superseded(self) -> None:
        for run_id in SUPERSEDED_RUNS:
            with self.subTest(run_id=run_id):
                run = json.loads(
                    (
                        self.repository / RUN_ROOT / run_id / "run.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(run["verdict"], "pass")
                self.assertNotEqual(
                    run["subject_commit"],
                    json.loads(
                        (
                            self.repository
                            / RUN_ROOT
                            / PASSING_RUN
                            / "run.json"
                        ).read_text(encoding="utf-8")
                    )["subject_commit"],
                )

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

    def test_validator_rejects_semantic_and_privacy_forgery(self) -> None:
        original = json.loads(
            (
                self.repository / RUN_ROOT / PASSING_RUN / "run.json"
            ).read_text(encoding="utf-8")
        )
        mutations = {
            "wrong target": lambda run: run["cases"][0].__setitem__(
                "target", "private/secret.md"
            ),
            "blank Canvas disclosure": lambda run: run["cases"][3].__setitem__(
                "visible_disclosure", ""
            ),
            "unsafe fixture": lambda run: run["fixture"].__setitem__(
                "safe_public_synthetic_records_only", False
            ),
            "false duration": lambda run: run["cases"][4].__setitem__(
                "actual_stability_seconds", 999
            ),
            "local registration path": lambda run: run["fixture"][
                "fixture_registration"
            ].__setitem__("repository", "C:\\private"),
            "invalid process": lambda run: run["runtime"].__setitem__(
                "process_id", 0
            ),
            "cross-case chronology": lambda run: run["cases"][1].__setitem__(
                "before_observed_at", "2026-07-29T21:00:00Z"
            ),
            "private root field": lambda run: run.__setitem__(
                "debug_path", "C:\\private"
            ),
            "false tree role": lambda run: run["cases"][4].__setitem__(
                "tree_digest_role", "observed-byte proof"
            ),
            "manifest mismatch": lambda run: run["cases"][4].__setitem__(
                "manifest_digest", "sha256:" + ("0" * 64)
            ),
            "weakened claim limits": lambda run: run.__setitem__(
                "claim_limits", []
            ),
            "target metadata extension": lambda run: run[
                "final_target_metadata"
            ]["hive-mind/generated/README.md"].__setitem__(
                "local_path", "relative-but-undisclosed"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = deepcopy(original)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    _validate_passing_run(self.repository, candidate)

    def test_bounded_evidence_reader_rejects_unsafe_files(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            root.mkdir()
            safe = root / "safe.bin"
            safe.write_bytes(b"bounded")
            self.assertEqual(_bounded_file(root, safe, 7), b"bounded")

            with self.assertRaisesRegex(ValueError, "bounded evidence"):
                _bounded_file(root, safe, 6)

            hardlink = root / "hardlink.bin"
            os.link(safe, hardlink)
            with self.assertRaisesRegex(ValueError, "bounded evidence"):
                _bounded_file(root, hardlink, 7)

            outside = root.parent / "outside.bin"
            outside.write_bytes(b"outside")
            with self.assertRaisesRegex(ValueError, "escapes run directory"):
                _bounded_file(root, outside, 7)

            symlink = root / "symlink.bin"
            try:
                symlink.symlink_to(outside)
            except OSError:
                pass
            else:
                with self.assertRaisesRegex(ValueError, "linked evidence"):
                    _bounded_file(root, symlink, 7)


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
        self.assertEqual(
            registration["no_hardlink_file_count"],
            registration["tracked_file_count"],
        )
        self.assertGreater(registration["git_object_file_count"], 0)
        self.assertEqual(
            registration["no_hardlink_git_object_count"],
            registration["git_object_file_count"],
        )

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

    def test_fixture_rejects_shared_objects_and_alternates(self) -> None:
        shared = self.root / "shared"
        subprocess.run(
            ("git", "clone", str(self.source), str(shared)),
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(SystemExit, "Git object"):
            fixture._validate_fixture(
                shared,
                self.source,
                self.state,
                command="initialize",
                claimed_subject_commit=self.subject,
            )

        alternates = self.clone / ".git" / "objects" / "info" / "alternates"
        alternates.write_text(
            str(self.source / ".git" / "objects") + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SystemExit, "shared Git object alternate"):
            fixture._validate_fixture(
                self.clone,
                self.source,
                self.state,
                command="initialize",
                claimed_subject_commit=self.subject,
            )


if __name__ == "__main__":
    unittest.main()
