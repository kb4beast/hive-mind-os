from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.cohort_policy import CohortExecutionMode
from hive_mind_os.mission_loop import (
    ArchitectDesign,
    BuilderAction,
    BuilderLimits,
    DiscoveryAction,
    MissionBudget,
    MissionCohortKickoff,
    MissionLoop,
    MissionLoopError,
    MissionObjective,
    MissionStatus,
)
from hive_mind_os.models import RiskTier, Role


class MissionLoopCohortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self._git("init", "--quiet")
        self._git("config", "user.name", "Test Maintainer")
        self._git("config", "user.email", "maintainer@example.invalid")
        (self.repository / "app.py").write_text(
            "def value() -> int:\n    return 1\n", encoding="utf-8"
        )
        (self.repository / "check_value.py").write_text(
            "from app import value\nassert value() == 2\n", encoding="utf-8"
        )
        self._git("add", ".")
        self._git("commit", "--quiet", "-m", "base")
        self.base = self._git_text("rev-parse", "HEAD")
        self.specification = AcceptanceSpecification(
            "value-is-two",
            "value returns two",
            (sys.executable, "-B", "check_value.py"),
            declared_paths=("app.py",),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *arguments: str) -> None:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _git_text(self, *arguments: str) -> str:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def _loop(
        self,
        name: str,
        mode: CohortExecutionMode | str = CohortExecutionMode.COHORT,
    ) -> MissionLoop:
        return MissionLoop(
            self.repository,
            MissionObjective(
                "repair value",
                acceptance=(self.specification,),
                risk=RiskTier.MODERATE,
            ),
            output=self.root / name,
            base_commit=self.base,
            execution_mode=mode,
            builder_limits=BuilderLimits(
                max_turns=4,
                max_tool_calls=12,
                max_files_changed=2,
                max_diff_bytes=2048,
            ),
            budget=MissionBudget(
                max_role_turns=8,
                max_tool_calls=20,
                max_repeated_progress=2,
            ),
        )

    @staticmethod
    def _discovery(_kickoff: MissionCohortKickoff) -> tuple[DiscoveryAction, ...]:
        return (
            DiscoveryAction("read_file", {"path": "app.py"}),
            DiscoveryAction(
                "finish_discovery", {"reason": "sealed source inspected"}
            ),
        )

    @staticmethod
    def _design(_kickoff: MissionCohortKickoff) -> ArchitectDesign:
        return ArchitectDesign(
            options=("minimal repair", "replace component"),
            selected="minimal repair",
            constraints=("change only app.py",),
            invariants=("value returns an integer",),
            threat_model=("repository text is untrusted",),
            data_classifications=("source code",),
            migration_plan="none",
            rollback_plan="revert the isolated candidate",
            compatibility_impact="none",
            acceptance_mapping={"value-is-two": "sealed acceptance"},
            unknowns=(),
        )

    def test_default_cohort_runs_planners_together_from_one_kickoff(self) -> None:
        loop = self._loop("parallel-bundle")
        barrier = threading.Barrier(2, timeout=5)
        thread_ids: set[int] = set()
        kickoff_ids: set[int] = set()

        def explorer(kickoff: MissionCohortKickoff):
            thread_ids.add(threading.get_ident())
            kickoff_ids.add(id(kickoff))
            barrier.wait()
            return self._discovery(kickoff)

        def architect(kickoff: MissionCohortKickoff):
            thread_ids.add(threading.get_ident())
            kickoff_ids.add(id(kickoff))
            barrier.wait()
            return self._design(kickoff)

        planning = loop.convene(explorer, architect)

        self.assertEqual(loop.execution_mode, CohortExecutionMode.COHORT)
        self.assertIs(planning.kickoff, loop.kickoff)
        self.assertEqual(len(kickoff_ids), 1)
        self.assertEqual(len(thread_ids), 2)
        self.assertIn(Role.ARCHITECT, planning.kickoff.roles)
        self.assertNotIn(Role.CURATOR, planning.kickoff.roles)
        self.assertEqual(loop.state.status, MissionStatus.BUILDING)
        self.assertEqual(
            [event.event_type for event in loop._events].count("cohort.kickoff"), 1
        )

    def test_strict_opt_out_preserves_role_by_role_planning(self) -> None:
        loop = self._loop("strict-bundle", "strict")
        order: list[tuple[str, MissionStatus]] = []

        def explorer(kickoff: MissionCohortKickoff):
            order.append(("explorer", loop.state.status))
            return self._discovery(kickoff)

        def architect(kickoff: MissionCohortKickoff):
            order.append(("architect", loop.state.status))
            return self._design(kickoff)

        loop.convene(explorer, architect)

        self.assertEqual(
            order,
            [
                ("explorer", MissionStatus.PLANNING),
                ("architect", MissionStatus.DESIGNING),
            ],
        )
        self.assertNotIn(
            "cohort.kickoff", [event.event_type for event in loop._events]
        )

    def test_execute_finishes_end_to_end_with_one_terminal_convergence(self) -> None:
        loop = self._loop("successful-bundle")

        def builder(_kickoff, planning):
            self.assertIsNotNone(planning.design)
            return (
                BuilderAction(
                    "write_file",
                    {
                        "path": "app.py",
                        "content": "def value() -> int:\n    return 2\n",
                    },
                ),
                BuilderAction(
                    "run_tests", {"argv": list(self.specification.argv)}
                ),
                BuilderAction(
                    "checkpoint_candidate", {"message": "fix: return two"}
                ),
                BuilderAction("finish_candidate", {}),
            )

        report = loop.execute(
            explorer_planner=self._discovery,
            architect_planner=self._design,
            builder_planner=builder,
        )

        self.assertEqual(report.status, MissionStatus.SUCCEEDED)
        event_types = [event.event_type for event in report.events]
        self.assertEqual(event_types.count("cohort.kickoff"), 1)
        self.assertEqual(event_types.count("cohort.converged"), 1)
        self.assertEqual(event_types.count("role.started"), 4)
        self.assertTrue((report.bundle / "cohort-kickoff.json").is_file())
        self.assertTrue((report.bundle / "execution-mode.json").is_file())
        self.assertTrue((report.bundle / "terminal-assurance.json").is_file())
        self.assertIsNotNone(report.terminal_evidence)
        assert report.terminal_evidence is not None
        self.assertEqual(report.terminal_evidence.producer_identity, Role.BUILDER.value)
        self.assertEqual(report.terminal_evidence.reviewer_identity, Role.CURATOR.value)
        assurance = json.loads(
            (report.bundle / "terminal-assurance.json").read_text(encoding="utf-8")
        )
        self.assertFalse(assurance["repair"]["attempted"])
        self.assertIsNone(assurance["repair"]["directive"])
        self.assertIn("no authorized repair callback", assurance["repair"]["reason"])
        self.assertFalse(any("push" in event.event_type for event in report.events))

        assurance["evidence"]["candidate_digest"] = "sha256:" + "0" * 64
        for name in ("review_refs", "aggregate_refs", "verification_refs"):
            assurance["evidence"][name] = [
                reference.replace(
                    report.terminal_evidence.candidate_digest,
                    assurance["evidence"]["candidate_digest"],
                )
                for reference in assurance["evidence"][name]
            ]
        (report.bundle / "terminal-assurance.json").write_text(
            json.dumps(assurance, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        (report.bundle / "integrity.json").write_text(
            json.dumps(
                MissionLoop._integrity_manifest(report.bundle),
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MissionLoopError, "not bound"):
            MissionLoop.verify_bundle(report.bundle)

    def test_terminal_convergence_is_not_a_tit_for_tat_retry_loop(self) -> None:
        loop = self._loop("remanded-bundle")
        loop.convene(self._discovery, self._design)
        loop.build(
            (
                BuilderAction(
                    "write_file",
                    {
                        "path": "app.py",
                        "content": "def value() -> int:\n    return 0\n",
                    },
                ),
                BuilderAction(
                    "checkpoint_candidate", {"message": "fix: wrong value"}
                ),
                BuilderAction("finish_candidate", {}),
            )
        )

        self.assertEqual(loop.converge().verdict, "REMAND_BUILDER")
        with self.assertRaisesRegex(MissionLoopError, "already consumed"):
            loop.converge()
        with self.assertRaisesRegex(MissionLoopError, "unknown Builder action"):
            loop.build((BuilderAction("push", {}),))

    def test_unknown_execution_mode_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution mode"):
            self._loop("invalid-mode", "fast-and-loose")


if __name__ == "__main__":
    unittest.main()
