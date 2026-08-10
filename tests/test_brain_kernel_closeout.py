from __future__ import annotations

import argparse
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.closeout import (
    declare_closeout_obligations,
    derive_technical_closeout,
    integrate_verified_work,
    record_evaluation_bundle,
)
from hive_mind_os.brain_kernel.contracts import (
    HistoricalEvidenceReference,
    RoleResult,
    TechnicalCloseoutState,
)
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.roles import (
    KERNEL_IMPLEMENTED_ROLES,
    append_role_result,
    result_digest,
)
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.brain_kernel.verification import (
    accept_verified_work,
    create_evaluation_plan,
    seal_evaluation_plan,
    verify_exact_candidate,
)
from hive_mind_os.cli import _run_kernel_closeout, build_kernel_parser

TIME = "2026-08-07T12:00:00Z"
DIGEST = "sha256:" + "0" * 64


class LocalTechnicalCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.base = self.root / "base"
        self.base.mkdir()
        (self.base / "app.txt").write_text("before\n", encoding="utf-8")
        (self.root / "state").mkdir()
        self.store = KernelStore(self.root / "state" / "brain-kernel.sqlite3")
        self.store.append(KernelEvent("mission", "MISSION-closeout", "mission.created", "fixture", TIME, {}))
        self._append("work", "work.created", {}, work_id="WORK-closeout")
        for status in ("READY", "LEASED", "RUNNING"):
            self._append(f"work:{status}", "work.transition", {"status": status}, work_id="WORK-closeout")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _append(self, event_id: str, event_type: str, payload: dict[str, object], *, work_id: str) -> None:
        self.store.append(KernelEvent(event_id, "MISSION-closeout", event_type, "fixture", TIME, payload, work_id=work_id, previous_digest=self.store.events()[-1]["digest"]))

    def _role_result(self, role: str, executor_id: str) -> RoleResult:
        provisional = RoleResult("MISSION-closeout", "WORK-closeout", "ATTEMPT-one", role, executor_id, DIGEST, DIGEST, (), (), (f"artifact:{role}",), (f"claim:{role}",), (), (), None, "bounded local output", DIGEST)
        return replace(provisional, result_digest=result_digest(provisional))

    def _completed_closeout(self, *, shared_identity: bool = False) -> tuple[Path, str]:
        receipt = self.root / "historical-receipt.json"
        receipt.write_text('{"historical":true}\n', encoding="utf-8")
        reference = HistoricalEvidenceReference("receipt:legacy", canonical_digest({"bytes": receipt.read_bytes().hex()}), "legacy-fixture", "retain unchanged")
        declare_closeout_obligations(self.store, "MISSION-closeout", historical_evidence=(reference,))
        for role in KERNEL_IMPLEMENTED_ROLES:
            executor = "executor:shared" if shared_identity and role in {"builder", "curator"} else f"executor:{role}"
            append_role_result(self.store, self._role_result(role, executor), occurred_at=TIME)
        plan = create_evaluation_plan("EVAL-closeout", self.base, acceptance_commands=("content-is-after",), allowed_paths=("app.txt",))
        seal_evaluation_plan(self.store, "WORK-closeout", plan, base_root=self.base, actor_id="architect")
        self._append("work:awaiting", "work.transition", {"status": "AWAITING_VERIFICATION"}, work_id="WORK-closeout")
        candidate = self.root / "candidate"
        shutil.copytree(self.base, candidate)
        (candidate / "app.txt").write_text("after\n", encoding="utf-8")
        outcome = verify_exact_candidate(self.store, "WORK-closeout", plan, candidate, builder_id="builder:one", evaluator_id="curator:two", check_runner=lambda _command, root: (root / "app.txt").read_text(encoding="utf-8") == "after\n", bundle_directory=self.root / "bundle")
        record_evaluation_bundle(self.store, "WORK-closeout", outcome.result, outcome.bundle_path, bundle_ref="fixture")
        accept_verified_work(self.store, "WORK-closeout", outcome.result, actor_id="integrator")
        integrate_verified_work(self.store, "WORK-closeout", outcome.result)
        self.assertEqual('{"historical":true}\n', receipt.read_text(encoding="utf-8"))
        return outcome.bundle_path, "fixture"

    def test_replayed_closeout_requires_roles_integrated_work_and_intact_bundle(self) -> None:
        bundle, reference = self._completed_closeout()
        report = derive_technical_closeout(self.store, "MISSION-closeout", bundle_directories={reference: bundle})
        self.assertEqual(TechnicalCloseoutState.TECHNICALLY_VERIFIED, report.state)
        self.assertEqual(KERNEL_IMPLEMENTED_ROLES, report.fulfilled_roles)
        self.assertTrue(report.validate().valid, report.validate().issues)
        self.assertEqual(report, derive_technical_closeout(self.store, "MISSION-closeout", bundle_directories={reference: bundle}))

        unavailable = derive_technical_closeout(self.store, "MISSION-closeout")
        self.assertEqual(TechnicalCloseoutState.BLOCKED, unavailable.state)
        (bundle / "verification.json").write_text("{}", encoding="utf-8")
        tampered = derive_technical_closeout(self.store, "MISSION-closeout", bundle_directories={reference: bundle})
        self.assertEqual(TechnicalCloseoutState.BLOCKED, tampered.state)

    def test_shared_required_identity_blocks_closeout(self) -> None:
        bundle, reference = self._completed_closeout(shared_identity=True)
        report = derive_technical_closeout(self.store, "MISSION-closeout", bundle_directories={reference: bundle})
        self.assertEqual(TechnicalCloseoutState.BLOCKED, report.state)
        self.assertIn("distinct required role identities", report.missing_obligations)

    def test_unintegrated_but_valid_local_work_is_partial(self) -> None:
        declare_closeout_obligations(self.store, "MISSION-closeout")
        for role in KERNEL_IMPLEMENTED_ROLES:
            append_role_result(self.store, self._role_result(role, f"executor:{role}"), occurred_at=TIME)
        report = derive_technical_closeout(self.store, "MISSION-closeout")
        self.assertEqual(TechnicalCloseoutState.PARTIAL, report.state)
        self.assertIn("integrated:WORK-closeout", report.missing_obligations)

    def test_closeout_cli_is_read_only_and_requires_existing_state(self) -> None:
        bundle, reference = self._completed_closeout()
        events_before = self.store.events()
        self.store.close()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(0, _run_kernel_closeout(argparse.Namespace(mission_id="MISSION-closeout", state_dir=str(self.root / "state"), bundle_ref=[f"{reference}={bundle}"], json_output=True)))
        self.assertIn("TECHNICALLY_VERIFIED", stdout.getvalue())
        reader = KernelStore(self.root / "state" / "brain-kernel.sqlite3", read_only=True)
        self.assertEqual(events_before, reader.events())
        reader.close()
        parsed = build_kernel_parser().parse_args(["closeout", "MISSION-closeout", "--bundle-ref", f"{reference}={bundle}"])
        self.assertEqual("closeout", parsed.kernel_command)
