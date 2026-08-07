from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.store import KernelIntegrityError, KernelStore
from hive_mind_os.brain_kernel.verification import (
    ExactCandidateVerificationError,
    accept_verified_work,
    create_evaluation_plan,
    seal_evaluation_plan,
    verify_bundle,
    verify_exact_candidate,
)


class ExactCandidateVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.base = self.root / "base"
        self.base.mkdir()
        (self.base / "app.txt").write_text("before\n", encoding="utf-8")
        self.store = KernelStore()
        self.store.append(KernelEvent("mission", "MISSION-verify", "mission.created", "fixture", "1970-01-01T00:00:00Z", {}))
        self._append("work", "work.created", {}, work_id="WORK-verify")
        for status in ("READY", "LEASED", "RUNNING"):
            self._append(f"work:{status}", "work.transition", {"status": status}, work_id="WORK-verify")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _append(self, event_id: str, event_type: str, payload: dict[str, object], *, work_id: str) -> None:
        self.store.append(
            KernelEvent(
                event_id,
                "MISSION-verify",
                event_type,
                "fixture",
                "1970-01-01T00:00:00Z",
                payload,
                work_id=work_id,
                previous_digest=self.store.events()[-1]["digest"],
            )
        )

    def _plan(self):
        return create_evaluation_plan(
            "EVAL-verify",
            self.base,
            acceptance_commands=("content-is-after",),
            allowed_paths=("app.txt",),
        )

    def _candidate(self) -> Path:
        candidate = self.root / "candidate"
        shutil.copytree(self.base, candidate)
        (candidate / "app.txt").write_text("after\n", encoding="utf-8")
        return candidate

    def test_passed_exact_candidate_can_be_accepted_only_with_its_verdict(self) -> None:
        plan = self._plan()
        seal_evaluation_plan(
            self.store, "WORK-verify", plan, base_root=self.base, actor_id="architect"
        )
        self._append("work:awaiting", "work.transition", {"status": "AWAITING_VERIFICATION"}, work_id="WORK-verify")
        outcome = verify_exact_candidate(
            self.store,
            "WORK-verify",
            plan,
            self._candidate(),
            builder_id="builder:one",
            evaluator_id="curator:two",
            check_runner=lambda command, root: (root / "app.txt").read_text() == "after\n",
            bundle_directory=self.root / "bundle",
        )
        self.assertEqual("PASSED", outcome.result.state)
        self.assertTrue(outcome.bundle_path.is_dir())
        verify_bundle(outcome.bundle_path)
        accept_verified_work(self.store, "WORK-verify", outcome.result, actor_id="integrator")
        self.assertEqual("ACCEPTED", self.store.projection()["work"]["WORK-verify"]["status"])

    def test_candidate_mutation_or_direct_acceptance_fails_closed(self) -> None:
        plan = self._plan()
        seal_evaluation_plan(
            self.store, "WORK-verify", plan, base_root=self.base, actor_id="architect"
        )
        self._append("work:awaiting", "work.transition", {"status": "AWAITING_VERIFICATION"}, work_id="WORK-verify")
        candidate = self._candidate()
        outcome = verify_exact_candidate(
            self.store,
            "WORK-verify",
            plan,
            candidate,
            builder_id="builder:one",
            evaluator_id="curator:two",
            check_runner=lambda _command, root: (root / "app.txt").write_text("mutated\n") or True,
            bundle_directory=self.root / "failed-bundle",
        )
        self.assertEqual("FAILED", outcome.result.state)
        with self.assertRaises(ExactCandidateVerificationError):
            accept_verified_work(self.store, "WORK-verify", outcome.result, actor_id="integrator")
        with self.assertRaises(KernelIntegrityError):
            self._append("forged-accept", "work.transition", {"status": "ACCEPTED"}, work_id="WORK-verify")
        (outcome.bundle_path / "verification.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ExactCandidateVerificationError):
            verify_bundle(outcome.bundle_path)

    def test_seal_rejects_a_base_that_changed_after_plan_creation(self) -> None:
        plan = self._plan()
        (self.base / "app.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaises(ExactCandidateVerificationError):
            seal_evaluation_plan(
                self.store, "WORK-verify", plan, base_root=self.base, actor_id="architect"
            )

    def test_same_identity_and_out_of_scope_candidate_fail_closed(self) -> None:
        plan = self._plan()
        seal_evaluation_plan(
            self.store, "WORK-verify", plan, base_root=self.base, actor_id="architect"
        )
        self._append(
            "work:awaiting", "work.transition", {"status": "AWAITING_VERIFICATION"}, work_id="WORK-verify"
        )
        candidate = self._candidate()
        with self.assertRaises(ExactCandidateVerificationError):
            verify_exact_candidate(
                self.store,
                "WORK-verify",
                plan,
                candidate,
                builder_id="same",
                evaluator_id="same",
                check_runner=lambda _command, _root: True,
                bundle_directory=self.root / "same-identity",
            )
        (candidate / "unexpected.txt").write_text("scope escape\n", encoding="utf-8")
        outcome = verify_exact_candidate(
            self.store,
            "WORK-verify",
            plan,
            candidate,
            builder_id="builder:one",
            evaluator_id="curator:two",
            check_runner=lambda _command, _root: True,
            bundle_directory=self.root / "scope-failure",
        )
        self.assertEqual("FAILED", outcome.result.state)
