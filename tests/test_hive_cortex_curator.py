from __future__ import annotations

import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.brain_kernel.curator_runtime import (
    CandidateIdentity,
    CuratorRuntime,
    CuratorVerdict,
    CuratorVerificationError,
    IsolatedCandidateWorkspace,
)


class CuratorRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.builder_scratchpad = self.root / "builder"
        self.builder_scratchpad.mkdir()
        self.candidate = self.root / "curator-candidate"
        self.candidate.mkdir()
        (self.candidate / "candidate.txt").write_text("immutable\n", encoding="utf-8")
        self._git("init", "-q")
        self._git("config", "user.email", "curator@example.invalid")
        self._git("config", "user.name", "Curator fixture")
        self._git("add", "candidate.txt")
        self._git("commit", "-qm", "candidate fixture")
        self.runtime = CuratorRuntime()
        self.identity = CandidateIdentity(*self._git("rev-parse", "HEAD^{commit}", "HEAD^{tree}").splitlines())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _workspace(self, *, identity: CandidateIdentity | None = None) -> IsolatedCandidateWorkspace:
        return IsolatedCandidateWorkspace(
            "curator-workspace", self.candidate, identity or self.identity, "builder-workspace", self.builder_scratchpad
        )

    def _git(self, *arguments: str) -> str:
        return subprocess.run(
            ("git", "-C", str(self.candidate), *arguments),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_acceptance_seals_before_candidate_access_and_binds_exact_identity(self) -> None:
        seal = self.runtime.seal_acceptance(
            mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("content",)
        )
        report = self.runtime.verify(
            seal, self._workspace(), candidate=self.identity,
            check_runner=lambda _name, root: (root / "candidate.txt").read_text(encoding="utf-8") == "immutable\n",
        )
        self.assertEqual(CuratorVerdict.ADOPT, report.verdict)
        self.assertEqual(self.identity, report.candidate)
        self.assertEqual(report.pre_check_snapshot, report.post_check_snapshot)
        self.assertTrue(report.report_digest.startswith("sha256:"))

    def test_curator_rejects_builder_scratchpad_and_identity_mismatch(self) -> None:
        with self.assertRaises(CuratorVerificationError):
            IsolatedCandidateWorkspace("builder-workspace", self.candidate, self.identity, "builder-workspace", self.builder_scratchpad)
        with self.assertRaises(CuratorVerificationError):
            IsolatedCandidateWorkspace("curator-workspace", self.builder_scratchpad, self.identity, "builder-workspace", self.builder_scratchpad)
        seal = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("content",))
        mismatch = CandidateIdentity("a" * 40, "b" * 40)
        report = self.runtime.verify(seal, self._workspace(), candidate=mismatch, check_runner=lambda _name, _root: True)
        self.assertEqual(CuratorVerdict.BLOCKED, report.verdict)

    def test_failed_sealed_checks_remand_or_reject_without_test_weakening(self) -> None:
        remand = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("must-pass",))
        remand_report = self.runtime.verify(remand, self._workspace(), candidate=self.identity, check_runner=lambda _name, _root: False)
        self.assertEqual(CuratorVerdict.REMAND, remand_report.verdict)
        reject = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("must-pass",), failure_verdict=CuratorVerdict.REJECT)
        reject_report = self.runtime.verify(reject, self._workspace(), candidate=self.identity, check_runner=lambda _name, _root: False)
        self.assertEqual(CuratorVerdict.REJECT, reject_report.verdict)
        with self.assertRaises(CuratorVerificationError):
            self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=())
        with self.assertRaises(CuratorVerificationError):
            replace(remand, checks=("weakened",))

    def test_candidate_mutation_is_quarantined(self) -> None:
        seal = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("hostile",))

        def mutate_candidate(_name: str, root: Path) -> bool:
            (root / "candidate.txt").write_text("mutated\n", encoding="utf-8")
            return True

        report = self.runtime.verify(
            seal, self._workspace(), candidate=self.identity,
            check_runner=mutate_candidate,
        )
        self.assertEqual(CuratorVerdict.QUARANTINE, report.verdict)

    def test_empty_commit_metadata_mutation_is_quarantined(self) -> None:
        seal = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("metadata",))

        def mutate_metadata(_name: str, _root: Path) -> bool:
            self._git("commit", "--allow-empty", "-qm", "hostile metadata mutation")
            return True

        report = self.runtime.verify(
            seal, self._workspace(), candidate=self.identity, check_runner=mutate_metadata
        )
        self.assertEqual(CuratorVerdict.QUARANTINE, report.verdict)
        self.assertEqual(report.pre_check_snapshot, report.post_check_snapshot)

    def test_index_mutation_is_quarantined(self) -> None:
        seal = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("metadata",))

        def mutate_index(_name: str, _root: Path) -> bool:
            self._git("update-index", "--skip-worktree", "candidate.txt")
            return True

        index_report = self.runtime.verify(
            seal, self._workspace(), candidate=self.identity, check_runner=mutate_index
        )
        self.assertEqual(CuratorVerdict.QUARANTINE, index_report.verdict)

    def test_ref_mutation_is_quarantined(self) -> None:
        seal = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("metadata",))

        def mutate_ref(_name: str, _root: Path) -> bool:
            self._git("branch", "hostile-ref")
            return True

        ref_report = self.runtime.verify(
            seal, self._workspace(), candidate=self.identity, check_runner=mutate_ref
        )
        self.assertEqual(CuratorVerdict.QUARANTINE, ref_report.verdict)

    def test_fake_inherited_path_cannot_replace_trusted_git(self) -> None:
        seal = self.runtime.seal_acceptance(mission_id="MISSION-1", work_id="WORK-1", curator_id="curator:independent", checks=("content",))
        attacker_bin = self.root / "attacker-bin"
        attacker_bin.mkdir()
        (attacker_bin / "git.cmd").write_text("@echo forged-git-output\r\n", encoding="utf-8")
        with patch.dict("os.environ", {"PATH": str(attacker_bin)}, clear=False):
            report = self.runtime.verify(
                seal,
                self._workspace(),
                candidate=self.identity,
                check_runner=lambda _name, root: (root / "candidate.txt").read_text(encoding="utf-8") == "immutable\n",
            )
        self.assertEqual(CuratorVerdict.ADOPT, report.verdict)


if __name__ == "__main__":
    unittest.main()
