from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
# healing imports its siblings by name, exactly as the CLI does.
sys.path.insert(0, str(BIN))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("healing_controller", "controller.py")
learning = _load("healing_learning", "learning.py")
healing = _load("healing_module", "healing.py")
attended = _load("healing_attended_host", "attended_host.py")

NODE = "MISSION-400"
BRANCH = "autopilot/mission-400"
OWNER = "codex:mission-400-fixture"
PAST = "2020-01-01T00:00:00Z"
FUTURE = "2099-01-01T00:00:00Z"
OLD_COMMIT_DATE = "2020-01-01T00:00:00 +0000"

CLAIM_ENVIRONMENT = {
    "GIT_AUTHOR_NAME": "Hive Mind Autopilot Claim",
    "GIT_AUTHOR_EMAIL": controller.CLAIM_COMMIT_EMAIL,
    "GIT_COMMITTER_NAME": "Hive Mind Autopilot Claim",
    "GIT_COMMITTER_EMAIL": controller.CLAIM_COMMIT_EMAIL,
}


def git(root: Path, *arguments: str, environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root)) + arguments,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(environment or {})},
    )
    return completed.stdout.strip()


class HealingFixture(unittest.TestCase):
    """A work checkout plus a bare origin, exactly as the claim tests build it."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "work"
        self.origin = base / "origin.git"
        self.root.mkdir()
        subprocess.run(
            ("git", "init", "--bare", "--initial-branch=main", str(self.origin)),
            check=True,
            capture_output=True,
        )
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@hive-mind.invalid")
        source = Path(__file__).resolve().parents[1]
        copy_autopilot_fixture(source, self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "push", "-u", "origin", "main")
        self.target = git(self.root, "rev-parse", "HEAD")
        self.plane = controller.ControlPlane(self.root)
        self.policy = {
            **healing.DEFAULT_POLICY,
            "auto_reconcile": False,
            "auto_redispatch": False,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish_claim(
        self,
        *,
        expires_at: str,
        owner: str = OWNER,
        committer_date: str | None = None,
        plan_fingerprint: str | None = None,
    ) -> str:
        """Reproduce publish_remote_claim's exact commit shape and identity."""

        tree = git(self.root, "rev-parse", f"{self.target}^{{tree}}")
        message = json.dumps(
            {
                "kind": "hive-mind-autopilot-remote-claim-v1",
                "node_id": NODE,
                "owner": owner,
                "expires_at": expires_at,
                "plan_fingerprint": plan_fingerprint
                or self.plane.expected_plan_fingerprint,
                "target_sha": self.target,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        environment = dict(CLAIM_ENVIRONMENT)
        if committer_date is not None:
            environment["GIT_AUTHOR_DATE"] = committer_date
            environment["GIT_COMMITTER_DATE"] = committer_date
        commit = git(
            self.root,
            "commit-tree",
            tree,
            "-p",
            self.target,
            "-m",
            message,
            environment=environment,
        )
        git(self.root, "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
        return commit

    def publish_work(
        self,
        parent: str,
        *,
        committer_date: str | None = None,
        author_email: str = "fixture@hive-mind.invalid",
        content: str = "real work\n",
    ) -> str:
        """Push an unsealed work commit on top of ``parent``."""

        (self.root / "worker-output.txt").write_text(content, encoding="utf-8")
        git(self.root, "add", "worker-output.txt")
        environment = {
            "GIT_AUTHOR_NAME": "Worker",
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": "Worker",
            "GIT_COMMITTER_EMAIL": author_email,
        }
        if committer_date is not None:
            environment["GIT_AUTHOR_DATE"] = committer_date
            environment["GIT_COMMITTER_DATE"] = committer_date
        tree = git(self.root, "write-tree")
        commit = git(
            self.root,
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            "worker implementation",
            environment=environment,
        )
        git(self.root, "restore", "--staged", "worker-output.txt")
        git(self.root, "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
        return commit

    def remote_head(self) -> str | None:
        listed = git(self.root, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}")
        return listed.split()[0] if listed else None

    def quarantine_ref_sha(self, head: str) -> str | None:
        ref = f"refs/hive-mind-autopilot/quarantine/{NODE.lower()}/{head}"
        listed = git(self.root, "ls-remote", "origin", ref)
        return listed.split()[0] if listed else None


class ReapDefunctRemoteClaimTests(HealingFixture):
    """A claim mutex that provably protects nothing must be retirable."""

    def test_expired_claim_is_reaped_without_knowing_the_owner(self) -> None:
        claim = self.publish_claim(expires_at=PAST)
        released = self.plane.reap_defunct_remote_claim(
            NODE, actor="test:healer", reason="worker session ended"
        )
        self.assertEqual(released["outcome"], "retired-defunct")
        self.assertEqual(released["owner"], OWNER)
        self.assertEqual(released["proof"]["kind"], "expired")
        self.assertIsNone(self.remote_head())
        recorded = (self.root / ".autopilot" / "state" / "releases.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertIn(claim, recorded)
        self.assertIn("expired", recorded)

    def test_plan_superseded_claim_is_reaped_despite_a_live_ttl(self) -> None:
        self.publish_claim(
            expires_at=FUTURE, plan_fingerprint="sha256:some-retired-plan"
        )
        released = self.plane.reap_defunct_remote_claim(
            NODE, actor="test:healer", reason="claim binds a retired plan"
        )
        self.assertEqual(released["proof"]["kind"], "plan-superseded")
        self.assertIsNone(self.remote_head())

    def test_live_current_claim_is_refused_without_a_stall_bound(self) -> None:
        claim = self.publish_claim(expires_at=FUTURE)
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.reap_defunct_remote_claim(
                NODE, actor="test:healer", reason="impatient"
            )
        self.assertIn("may still protect", str(raised.exception))
        self.assertEqual(self.remote_head(), claim)

    def test_stalled_bare_claim_is_reaped_after_the_bound(self) -> None:
        self.publish_claim(expires_at=FUTURE, committer_date=OLD_COMMIT_DATE)
        released = self.plane.reap_defunct_remote_claim(
            NODE,
            actor="test:healer",
            reason="no work ever arrived",
            stall_minutes=30,
        )
        self.assertEqual(released["proof"]["kind"], "stalled-bare-claim")
        self.assertGreaterEqual(released["proof"]["idle_minutes"], 30)
        self.assertIsNone(self.remote_head())

    def test_young_bare_claim_survives_the_stall_bound(self) -> None:
        claim = self.publish_claim(expires_at=FUTURE)
        with self.assertRaises(controller.ClaimError):
            self.plane.reap_defunct_remote_claim(
                NODE, actor="test:healer", reason="impatient", stall_minutes=30
            )
        self.assertEqual(self.remote_head(), claim)

    def test_published_work_is_never_deleted(self) -> None:
        claim = self.publish_claim(expires_at=PAST)
        advanced = self.publish_work(claim)
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.reap_defunct_remote_claim(
                NODE, actor="test:healer", reason="cleanup"
            )
        self.assertIn("carries", str(raised.exception))
        self.assertEqual(self.remote_head(), advanced)

    def test_absent_branch_is_not_an_error(self) -> None:
        released = self.plane.reap_defunct_remote_claim(
            NODE, actor="test:healer", reason="nothing to retire"
        )
        self.assertEqual(released["outcome"], "absent")


class QuarantineDefunctBranchTests(HealingFixture):
    """Dead work is archived verbatim, never deleted, and never taken warm."""

    def test_dead_workers_work_is_archived_and_the_branch_freed(self) -> None:
        claim = self.publish_claim(expires_at=PAST, committer_date=OLD_COMMIT_DATE)
        head = self.publish_work(claim, committer_date=OLD_COMMIT_DATE)
        result = self.plane.quarantine_defunct_remote_branch(
            NODE, actor="test:healer", reason="worker died mid-implementation"
        )
        self.assertEqual(result["outcome"], "quarantined")
        self.assertEqual(result["claim_proof"]["kind"], "expired")
        self.assertEqual(self.quarantine_ref_sha(head), head)
        self.assertIsNone(self.remote_head())
        recorded = (self.root / ".autopilot" / "state" / "quarantines.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertIn(head, recorded)

    def test_unclaimed_work_is_archived_after_the_stall_bound(self) -> None:
        head = self.publish_work(self.target, committer_date=OLD_COMMIT_DATE)
        result = self.plane.quarantine_defunct_remote_branch(
            NODE, actor="test:healer", reason="no lawful claim ever governed this"
        )
        self.assertEqual(result["claim_proof"]["kind"], "no-governing-claim")
        self.assertEqual(self.quarantine_ref_sha(head), head)
        self.assertIsNone(self.remote_head())

    def test_sealed_heads_are_never_quarantined(self) -> None:
        claim = self.publish_claim(expires_at=PAST, committer_date=OLD_COMMIT_DATE)
        tree = git(self.root, "rev-parse", f"{claim}^{{tree}}")
        sealed = git(
            self.root,
            "commit-tree",
            tree,
            "-p",
            claim,
            "-m",
            "receipt",
            environment={
                "GIT_AUTHOR_NAME": "Receipt",
                "GIT_AUTHOR_EMAIL": controller.RECEIPT_COMMIT_EMAIL,
                "GIT_COMMITTER_NAME": "Receipt",
                "GIT_COMMITTER_EMAIL": controller.RECEIPT_COMMIT_EMAIL,
                "GIT_AUTHOR_DATE": OLD_COMMIT_DATE,
                "GIT_COMMITTER_DATE": OLD_COMMIT_DATE,
            },
        )
        git(self.root, "push", "--force", "origin", f"{sealed}:refs/heads/{BRANCH}")
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.quarantine_defunct_remote_branch(
                NODE, actor="test:healer", reason="tidy"
            )
        self.assertIn("sealed receipt", str(raised.exception))
        self.assertEqual(self.remote_head(), sealed)

    def test_recent_movement_is_respected(self) -> None:
        claim = self.publish_claim(expires_at=PAST, committer_date=OLD_COMMIT_DATE)
        head = self.publish_work(claim)  # committed now
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.quarantine_defunct_remote_branch(
                NODE, actor="test:healer", reason="tidy"
            )
        self.assertIn("moved", str(raised.exception))
        self.assertEqual(self.remote_head(), head)

    def test_live_governed_work_is_respected(self) -> None:
        claim = self.publish_claim(expires_at=FUTURE, committer_date=OLD_COMMIT_DATE)
        head = self.publish_work(claim, committer_date=OLD_COMMIT_DATE)
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.quarantine_defunct_remote_branch(
                NODE, actor="test:healer", reason="tidy"
            )
        self.assertIn("live claim", str(raised.exception))
        self.assertEqual(self.remote_head(), head)

    def test_bare_claims_are_routed_to_the_reap_verb(self) -> None:
        self.publish_claim(expires_at=PAST, committer_date=OLD_COMMIT_DATE)
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.quarantine_defunct_remote_branch(
                NODE, actor="test:healer", reason="tidy"
            )
        self.assertIn("reap_defunct_remote_claim", str(raised.exception))

    def test_integrated_foreign_claims_never_govern(self) -> None:
        """A completed sibling's expired claim rides along in target history;
        the branch's own live claim must govern, so quarantine must refuse."""

        tree = git(self.root, "rev-parse", f"{self.target}^{{tree}}")
        foreign_message = json.dumps(
            {
                "kind": "hive-mind-autopilot-remote-claim-v1",
                "node_id": "ARCH-100",
                "owner": "codex:arch-100-finished",
                "expires_at": PAST,
                "plan_fingerprint": self.plane.expected_plan_fingerprint,
                "target_sha": self.target,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        foreign = git(
            self.root,
            "commit-tree",
            tree,
            "-p",
            self.target,
            "-m",
            foreign_message,
            environment={**CLAIM_ENVIRONMENT, "GIT_COMMITTER_DATE": OLD_COMMIT_DATE},
        )
        git(self.root, "merge", "--no-ff", "--no-edit", foreign)
        git(self.root, "push", "origin", "main")
        self.target = git(self.root, "rev-parse", "HEAD")
        claim = self.publish_claim(
            expires_at=FUTURE, committer_date=OLD_COMMIT_DATE
        )
        head = self.publish_work(claim, committer_date=OLD_COMMIT_DATE)
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.quarantine_defunct_remote_branch(
                NODE, actor="test:healer", reason="tidy"
            )
        self.assertIn("live claim", str(raised.exception))
        self.assertEqual(self.remote_head(), head)


class RetryQuarantineLiftTests(HealingFixture):
    """A spent retry budget reopens only when every cause carries a fix."""

    def quarantine_node(self, *, resolved: bool) -> str:
        blocker_id = "sha256:fixture-blocker"
        blockers = Path(self.plane.blockers_dir)
        blockers.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(
                {
                    "blocker_id": blocker_id,
                    "node_id": NODE,
                    "status": "OPEN",
                    "category": "stale_remote_node_branch",
                    "cause": "stale claim wedged the branch",
                }
            )
        ]
        if resolved:
            lines.append(
                json.dumps(
                    {
                        "event": "BLOCKER_RESOLVED",
                        "blocker_id": blocker_id,
                        "node_id": NODE,
                        "status": "RESOLVED",
                    }
                )
            )
        (blockers / f"{NODE}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        failures = Path(self.plane.failures_dir)
        failures.mkdir(parents=True, exist_ok=True)
        (failures / f"{NODE}.jsonl").write_text(
            "\n".join(json.dumps({"node_id": NODE, "error": f"attempt {i}"}) for i in range(3))
            + "\n",
            encoding="utf-8",
        )
        quarantine = Path(self.plane.quarantine_dir)
        quarantine.mkdir(parents=True, exist_ok=True)
        (quarantine / f"{NODE}.json").write_text(
            json.dumps({"node_id": NODE, "reason": "configured retry budget exhausted"})
            + "\n",
            encoding="utf-8",
        )
        escalations = Path(self.plane.escalations_dir)
        escalations.mkdir(parents=True, exist_ok=True)
        (escalations / f"{NODE}.json").write_text(
            json.dumps({"node_id": NODE, "kind": "escalation"}) + "\n", encoding="utf-8"
        )
        return blocker_id

    def test_unresolved_blockers_keep_the_quarantine(self) -> None:
        self.quarantine_node(resolved=False)
        with self.assertRaises(controller.AutopilotError) as raised:
            self.plane.lift_retry_quarantine(NODE, actor="test:healer")
        self.assertIn("unresolved", str(raised.exception))
        self.assertTrue((Path(self.plane.quarantine_dir) / f"{NODE}.json").is_file())

    def test_an_empty_ledger_never_lifts_the_quarantine(self) -> None:
        quarantine = Path(self.plane.quarantine_dir)
        quarantine.mkdir(parents=True, exist_ok=True)
        (quarantine / f"{NODE}.json").write_text(
            json.dumps({"node_id": NODE, "reason": "configured retry budget exhausted"})
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(controller.AutopilotError) as raised:
            self.plane.lift_retry_quarantine(NODE, actor="test:healer")
        self.assertIn("names no resolvable causes", str(raised.exception))
        self.assertTrue((quarantine / f"{NODE}.json").is_file())

    def test_unresolved_quarantine_reports_resolve_blockers(self) -> None:
        self.quarantine_node(resolved=False)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={
                **healing.DEFAULT_POLICY,
                "auto_reconcile": False,
                "auto_redispatch": False,
            },
            status={
                "reconciliation_required": False,
                "nodes": [],
                "dispatch_release": {"valid": False, "verdicts": {}},
            },
        )
        self.assertEqual(report["disposition"], "RESOLVE_BLOCKERS")
        self.assertTrue(report["stuck"][0]["resolvable"])
        self.assertIn("blocker-resolve", report["stuck"][0]["instructions"])

    def test_resolved_blockers_lift_and_archive_everything(self) -> None:
        self.quarantine_node(resolved=True)
        recovery = self.plane.lift_retry_quarantine(NODE, actor="test:healer")
        self.assertEqual(recovery["kind"], "hive-mind-autopilot-retry-quarantine-lift-v1")
        self.assertEqual(len(recovery["failures"]), 3)
        self.assertFalse((Path(self.plane.quarantine_dir) / f"{NODE}.json").is_file())
        self.assertFalse((Path(self.plane.escalations_dir) / f"{NODE}.json").is_file())
        self.assertFalse((Path(self.plane.failures_dir) / f"{NODE}.jsonl").is_file())
        archives = list((self.root / ".autopilot" / "state" / "recoveries").glob("*.json"))
        self.assertEqual(len(archives), 1)
        self.assertIsNone(self.plane.lift_retry_quarantine(NODE, actor="test:healer"))

    def test_fully_resolved_ledger_is_recognized(self) -> None:
        self.quarantine_node(resolved=True)
        self.assertTrue(self.plane.blockers_fully_resolved(NODE))
        self.assertEqual(self.plane.unresolved_blockers(NODE), ())

    def test_unparseable_ledger_is_never_fully_resolved(self) -> None:
        blockers = Path(self.plane.blockers_dir)
        blockers.mkdir(parents=True, exist_ok=True)
        (blockers / f"{NODE}.jsonl").write_text(
            json.dumps({"error": "no blocker_id or status here"}) + "\n",
            encoding="utf-8",
        )
        self.assertFalse(self.plane.blockers_fully_resolved(NODE))

    def test_heal_round_lifts_a_liftable_quarantine(self) -> None:
        self.quarantine_node(resolved=True)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={
                **healing.DEFAULT_POLICY,
                "auto_reconcile": False,
                "auto_redispatch": False,
            },
            status={
                "reconciliation_required": False,
                "nodes": [],
                "dispatch_release": {"valid": False, "verdicts": {}},
            },
        )
        self.assertEqual(report["disposition"], "HEALED")
        lifted = [a for a in report["actions"] if a["kind"] == "lift-quarantine"]
        self.assertEqual(lifted[0]["outcome"], "APPLIED")
        self.assertFalse((Path(self.plane.quarantine_dir) / f"{NODE}.json").is_file())


class EscalationResolutionTests(HealingFixture):
    """An escalation that never spent a retry budget still needs a way back.

    ``lift_retry_quarantine`` is the only other verb that clears an escalation
    packet, and it refuses unless a quarantine file exists.  A node that
    escalates inside its retry budget therefore writes a packet no verb could
    ever retire, so it reports ESCALATION_REQUIRED forever.  These tests pin the
    lawful exit and, just as importantly, pin that it stays shut until the
    blocker ledger proves every named cause was fixed.
    """

    def escalate(self) -> str:
        """Escalate through the real verb, inside the budget, and return the blocker id."""

        record = self.plane.fail(
            NODE,
            OWNER,
            error="host adapter refused the dispatch",
            kind="escalation",
            blocker_cause="host adapter refused the dispatch",
            blocker_fix="Install the missing host adapter and re-run the round.",
            retry_when="Retry once the adapter answers a probe.",
        )
        # The gap under test: one failure against max_retries=2 escalates
        # without ever earning the quarantine that lift_retry_quarantine needs.
        self.assertFalse(self.plane.is_quarantined(NODE))
        self.assertTrue(self.plane.is_escalated(NODE))
        self.assertIsNone(self.plane.lift_retry_quarantine(NODE, actor="test:healer"))
        return str(record["blocker"]["blocker_id"])

    def resolve_blocker(self, blocker_id: str) -> None:
        self.plane.resolve_blocker(
            NODE,
            blocker_id,
            actor="test:healer",
            fix="Installed the host adapter and verified it answers a probe.",
            retry_command=["python", ".autopilot/bin/autopilot.py", "status"],
        )

    def archives(self) -> list[Path]:
        return sorted((self.root / ".autopilot" / "state" / "recoveries").glob("*.json"))

    def test_no_escalation_packet_returns_none_and_changes_nothing(self) -> None:
        state = self.root / ".autopilot" / "state"
        before = sorted(str(p.relative_to(state)) for p in state.rglob("*"))
        self.assertIsNone(self.plane.resolve_escalation(NODE, actor="test:healer"))
        after = sorted(str(p.relative_to(state)) for p in state.rglob("*"))
        self.assertEqual(before, after)
        self.assertFalse((state / "recoveries.jsonl").exists())

    def test_an_open_blocker_refuses_and_the_packet_survives(self) -> None:
        blocker_id = self.escalate()
        with self.assertRaises(controller.AutopilotError) as raised:
            self.plane.resolve_escalation(NODE, actor="test:healer")
        self.assertIn("unresolved", str(raised.exception))
        self.assertIn(blocker_id, str(raised.exception))
        self.assertTrue((Path(self.plane.escalations_dir) / f"{NODE}.json").is_file())
        self.assertTrue(self.plane.is_escalated(NODE))
        self.assertEqual(self.plane.node_view(NODE).state, "ESCALATION_REQUIRED")
        self.assertEqual(self.archives(), [])

    def test_the_escalating_identity_may_not_clear_its_own_escalation(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        # Every other gate is satisfied: only the identity is wrong.
        self.assertTrue(self.plane.blockers_fully_resolved(NODE))
        with self.assertRaises(controller.AutopilotError) as raised:
            self.plane.resolve_escalation(NODE, actor=OWNER)
        message = str(raised.exception)
        self.assertIn("may not clear", message)
        self.assertIn(OWNER, message)
        self.assertIn(NODE, message)
        self.assertTrue((Path(self.plane.escalations_dir) / f"{NODE}.json").is_file())
        self.assertTrue(self.plane.is_escalated(NODE))
        self.assertEqual(self.plane.node_view(NODE).state, "ESCALATION_REQUIRED")
        self.assertEqual(self.archives(), [])

    def test_padding_the_owner_does_not_manufacture_a_second_identity(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        for actor in (f"  {OWNER}", f"{OWNER}\t", f"\n {OWNER} \n"):
            with self.assertRaises(controller.AutopilotError) as raised:
                self.plane.resolve_escalation(NODE, actor=actor)
            self.assertIn("may not clear", str(raised.exception))
        self.assertTrue((Path(self.plane.escalations_dir) / f"{NODE}.json").is_file())

    def test_an_independent_identity_clears_the_escalation(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        packet = json.loads(
            (Path(self.plane.escalations_dir) / f"{NODE}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(packet["owner"], OWNER)
        recovery = self.plane.resolve_escalation(NODE, actor="codex:orchestrator")
        self.assertEqual(recovery["actor"], "codex:orchestrator")
        self.assertNotEqual(recovery["actor"], recovery["escalation"]["owner"])
        # The archive keeps both halves of the independence claim checkable.
        self.assertEqual(recovery["escalation"]["owner"], OWNER)
        self.assertFalse(self.plane.is_escalated(NODE))
        self.assertNotEqual(self.plane.node_view(NODE).state, "ESCALATION_REQUIRED")

    def test_an_empty_ledger_never_retires_an_escalation(self) -> None:
        escalations = Path(self.plane.escalations_dir)
        escalations.mkdir(parents=True, exist_ok=True)
        (escalations / f"{NODE}.json").write_text(
            json.dumps({"node_id": NODE, "kind": "escalation"}) + "\n", encoding="utf-8"
        )
        with self.assertRaises(controller.AutopilotError) as raised:
            self.plane.resolve_escalation(NODE, actor="test:healer")
        self.assertIn("names no resolvable causes", str(raised.exception))
        self.assertTrue((escalations / f"{NODE}.json").is_file())

    def test_resolved_blockers_retire_the_escalation(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        recovery = self.plane.resolve_escalation(NODE, actor="test:healer")
        self.assertEqual(recovery["kind"], "hive-mind-autopilot-escalation-resolution-v1")
        self.assertFalse((Path(self.plane.escalations_dir) / f"{NODE}.json").is_file())
        self.assertFalse(self.plane.is_escalated(NODE))
        self.assertNotEqual(self.plane.node_view(NODE).state, "ESCALATION_REQUIRED")
        # Idempotent: a second run finds no packet and reports so without error.
        self.assertIsNone(self.plane.resolve_escalation(NODE, actor="test:healer"))

    def test_the_archive_holds_the_escalation_record_and_failure_ledger(self) -> None:
        blocker_id = self.escalate()
        ledger = list(self.plane.failures(NODE))
        self.resolve_blocker(blocker_id)
        recovery = self.plane.resolve_escalation(NODE, actor="test:healer")
        archives = self.archives()
        self.assertEqual(len(archives), 1)
        archived = json.loads(archives[0].read_text(encoding="utf-8"))
        self.assertEqual(archived, dict(recovery))
        self.assertEqual(archived["node_id"], NODE)
        self.assertEqual(archived["escalation"]["kind"], "escalation")
        self.assertEqual(
            archived["escalation"]["error"], "host adapter refused the dispatch"
        )
        self.assertEqual(archived["escalation"]["owner"], OWNER)
        self.assertEqual(archived["failures"], [dict(item) for item in ledger])
        self.assertEqual(len(archived["failures"]), 1)
        self.assertEqual(
            archived["failures"][0]["error"], "host adapter refused the dispatch"
        )
        # Nothing is lost: the live ledger and any quarantine are untouched.
        self.assertEqual(len(self.plane.failures(NODE)), 1)

    def test_a_blank_actor_is_refused(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        for actor in ("", "   ", "\t\n"):
            with self.assertRaises(controller.AutopilotError) as raised:
                self.plane.resolve_escalation(NODE, actor=actor)
            self.assertIn("acting identity", str(raised.exception))
        self.assertTrue((Path(self.plane.escalations_dir) / f"{NODE}.json").is_file())

    def test_the_audit_record_names_the_actor(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        recovery = self.plane.resolve_escalation(NODE, actor="human:brian")
        audit = self.root / ".autopilot" / "state" / "recoveries.jsonl"
        rows = [
            json.loads(line)
            for line in audit.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actor"], "human:brian")
        self.assertEqual(rows[0]["node_id"], NODE)
        self.assertEqual(rows[0]["recovery_id"], recovery["recovery_id"])
        self.assertEqual(recovery["actor"], "human:brian")
        # The audit row points at an archive that really exists.
        archive = self.root / ".autopilot" / "state" / rows[0]["archive"]
        self.assertTrue(archive.is_file())

    def test_a_retry_quarantine_outlives_the_escalation_resolution(self) -> None:
        """Clearing an escalation must not smuggle a spent budget back open."""

        blocker_id = self.escalate()
        quarantine = Path(self.plane.quarantine_dir)
        quarantine.mkdir(parents=True, exist_ok=True)
        (quarantine / f"{NODE}.json").write_text(
            json.dumps({"node_id": NODE, "reason": "configured retry budget exhausted"})
            + "\n",
            encoding="utf-8",
        )
        self.resolve_blocker(blocker_id)
        recovery = self.plane.resolve_escalation(NODE, actor="test:healer")
        self.assertTrue((quarantine / f"{NODE}.json").is_file())
        self.assertTrue(self.plane.is_quarantined(NODE))
        self.assertEqual(self.plane.node_view(NODE).state, "QUARANTINED")
        self.assertEqual(recovery["quarantine"]["reason"], "configured retry budget exhausted")

    def test_the_cli_verb_prints_the_recovery_document(self) -> None:
        blocker_id = self.escalate()
        self.resolve_blocker(blocker_id)
        completed = subprocess.run(
            (
                sys.executable,
                str(BIN / "autopilot.py"),
                "escalation-resolve",
                NODE,
                "--actor",
                "human:brian",
            ),
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["kind"], "hive-mind-autopilot-escalation-resolution-v1")
        self.assertEqual(payload["actor"], "human:brian")
        self.assertFalse(self.plane.is_escalated(NODE))
        again = subprocess.run(
            (
                sys.executable,
                str(BIN / "autopilot.py"),
                "escalation-resolve",
                NODE,
                "--actor",
                "human:brian",
            ),
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(again.stdout), {"node_id": NODE, "outcome": "not-escalated"}
        )


class ValidationLeaseBreakTests(HealingFixture):
    """An expired lease left by a dead session must stop wedging rounds."""

    def write_lease(self, *, expires_at: str) -> None:
        path = self.plane.validation_lease_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "node_id": NODE,
                    "owner": "codex:departed-session",
                    "expires_at": expires_at,
                    "lease_id": "sha256:fixture-lease",
                    "status": "ACTIVE",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_expired_lease_is_broken_and_archived(self) -> None:
        self.write_lease(expires_at=PAST)
        broken = self.plane.break_expired_validation_lease(actor="test:healer")
        self.assertEqual(broken["status"], "EXPIRED_BROKEN")
        self.assertEqual(broken["broken_by"], "test:healer")
        self.assertFalse(self.plane.validation_lease_path.is_file())
        archive = (
            self.root / ".autopilot" / "state" / "validation-leases" /
            "sha256-fixture-lease.json"
        )
        self.assertTrue(archive.is_file())
        self.assertIsNone(
            self.plane.break_expired_validation_lease(actor="test:healer")
        )

    def test_live_lease_is_never_broken(self) -> None:
        self.write_lease(expires_at=FUTURE)
        with self.assertRaises(controller.AutopilotError) as raised:
            self.plane.break_expired_validation_lease(actor="test:healer")
        self.assertIn("live", str(raised.exception))
        self.assertTrue(self.plane.validation_lease_path.is_file())


class HealRoundTests(HealingFixture):
    """The healer's report must be a disposition a loop can act on mechanically."""

    RECONCILED_STATUS = {
        "reconciliation_required": False,
        "nodes": [],
        "dispatch_release": {"valid": False, "verdicts": {}},
    }

    def test_a_defunct_claim_wedge_heals_end_to_end(self) -> None:
        self.publish_claim(expires_at=PAST)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(report["disposition"], "HEALED")
        applied = [
            action for action in report["actions"] if action["outcome"] == "APPLIED"
        ]
        self.assertEqual(applied[0]["kind"], "reap")
        self.assertIsNone(self.remote_head())

    def test_a_live_claim_waits_with_an_exact_wake_time(self) -> None:
        self.publish_claim(expires_at=FUTURE)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(report["disposition"], "WAITING")
        self.assertIsNotNone(report["wake_at"])
        self.assertEqual(report["waiting"][0]["node_id"], NODE)
        self.assertIsNotNone(self.remote_head())

    def test_dry_run_withholds_every_action(self) -> None:
        claim = self.publish_claim(expires_at=PAST)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=self.RECONCILED_STATUS,
            apply=False,
        )
        self.assertEqual(report["disposition"], "ACTIONABLE")
        self.assertEqual(report["actions"][0]["outcome"], "WITHHELD")
        self.assertEqual(self.remote_head(), claim)

    def test_released_but_unstarted_nodes_ask_for_sessions(self) -> None:
        status = {
            "reconciliation_required": False,
            "nodes": [],
            "dispatch_release": {"valid": True, "verdicts": {NODE: "START NOW"}},
        }
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=status,
        )
        self.assertEqual(report["disposition"], "OPEN_SESSIONS")
        self.assertEqual(report["open_sessions"], [NODE])

    def test_sealed_blockers_are_reported_as_stuck(self) -> None:
        blockers = Path(self.plane.blockers_dir)
        blockers.mkdir(parents=True, exist_ok=True)
        (blockers / f"{NODE}.jsonl").write_text(
            json.dumps(
                {
                    "category": "external-authority",
                    "cause": "requires production credential",
                    "fix": "a human must supply the deploy token",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(report["disposition"], "STUCK_HUMAN")
        self.assertIn("deploy token", report["stuck"][0]["instructions"])

    def test_disabled_policy_does_nothing(self) -> None:
        claim = self.publish_claim(expires_at=PAST)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "enabled": False},
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(report["disposition"], "DISABLED")
        self.assertEqual(report["actions"], [])
        self.assertEqual(self.remote_head(), claim)

    def test_frozen_evidence_is_measured_across_observations(self) -> None:
        self.publish_claim(expires_at=FUTURE)
        base_time = controller.utc_now()
        early = controller.ControlPlane(self.root, clock=lambda: base_time)
        late = controller.ControlPlane(
            self.root, clock=lambda: base_time + timedelta(minutes=10)
        )
        first = healing.heal_round(
            early,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=self.RECONCILED_STATUS,
        )
        second = healing.heal_round(
            late,
            actor="test:healer",
            nodes=[NODE],
            policy=self.policy,
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(
            first["evidence_fingerprint"], second["evidence_fingerprint"]
        )
        self.assertEqual(second["evidence_frozen_minutes"], 10)

    def test_repeated_stall_retirements_suspend_the_bound(self) -> None:
        for _ in range(3):
            controller.append_jsonl(
                Path(self.plane.state_dir) / "releases.jsonl",
                {
                    "node_id": NODE,
                    "outcome": "retired-defunct",
                    "proof": {"kind": "stalled-bare-claim"},
                },
            )
        self.publish_claim(expires_at=FUTURE, committer_date=OLD_COMMIT_DATE)
        diagnosis = healing.diagnose_node(
            self.plane, NODE, policy=healing.DEFAULT_POLICY
        )
        self.assertEqual(diagnosis.verdict, "CLAIM_LIVE")
        self.assertIn("suspended", diagnosis.detail)
        self.assertEqual(diagnosis.wake_at, FUTURE)  # lease expiry bounds the wait


class LearningTests(HealingFixture):
    """A lesson must be earned by outcomes, survive the session, and bite."""

    RECONCILED_STATUS = {
        "reconciliation_required": False,
        "nodes": [],
        "dispatch_release": {"valid": False, "verdicts": {}},
    }

    def setUp(self) -> None:
        super().setUp()
        # The fixture inherits this repository's committed lessons, which is the
        # point of committing them (see test_committed_lessons_reach_a_fresh_checkout).
        # Every other test here measures its own subject, so start from a clean slate.
        self.inherited = dict(learning.load_lessons(self.plane.ap_root))
        for path in learning.lessons_dir(self.plane.ap_root).glob("*.jsonl"):
            path.unlink()

    def use_release_branch(self) -> None:
        """Lesson commits are refused on main; work where the DAG works."""

        git(self.root, "checkout", "-q", "-B", "release/lessons-fixture")

    def test_committed_lessons_reach_a_fresh_checkout(self) -> None:
        """The whole reason lessons are committed: a new clone starts informed."""

        self.assertTrue(
            self.inherited,
            "a fresh fixture inherited no lessons; committed lessons are not travelling",
        )
        for lesson in self.inherited.values():
            self.assertNotIn("sha256:", lesson.signature)
            for part in (NODE, BRANCH, "MISSION"):
                self.assertNotIn(part, lesson.signature)

    KEY = "CLAIM_STALLED|stalled-bare-claim|reap"

    def observe(self, outcome: str, *, action: str = "reap", node: str = NODE) -> None:
        learning.record_outcome(
            self.plane.ap_root,
            verdict="CLAIM_STALLED",
            proof_kind="stalled-bare-claim",
            action=action,
            outcome=outcome,
            node_id=node,
            actor="test:healer",
            observed_at=controller.format_time(controller.utc_now()),
            guidance="inspect the claim commit by hand",
        )

    def test_signature_is_mechanism_not_instance(self) -> None:
        self.assertEqual(
            learning.signature("CLAIM_STALLED", "stalled-bare-claim", "reap"), self.KEY
        )
        self.observe("UNBLOCKED", node="MISSION-400")
        self.observe("UNBLOCKED", node="ARCH-100")
        lessons = learning.load_lessons(self.plane.ap_root)
        # Two different nodes, one mechanism: the lesson is about the mechanism.
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[self.KEY].counts["UNBLOCKED"], 2)

    def test_confidence_is_derived_from_settled_outcomes(self) -> None:
        self.assertIsNone(
            learning.consult(self.plane.ap_root, "CLAIM_STALLED", "stalled-bare-claim", "reap")
        )
        self.observe("UNBLOCKED")
        self.assertEqual(
            learning.load_lessons(self.plane.ap_root)[self.KEY].confidence, "PROVISIONAL"
        )
        self.observe("UNBLOCKED")
        self.assertEqual(
            learning.load_lessons(self.plane.ap_root)[self.KEY].confidence, "PROVEN"
        )

    def test_refusals_never_become_evidence_that_a_repair_fails(self) -> None:
        for _ in range(5):
            self.observe("REFUSED")
        lesson = learning.load_lessons(self.plane.ap_root)[self.KEY]
        # Refusals prove nothing about whether the repair holds...
        self.assertEqual(lesson.confidence, "UNTRIED")
        self.assertEqual(lesson.counts["NO_EFFECT"], 0)
        # ...but a run of them against an unmoving head still stops the retry
        # loop, under the separate refusal-stall rule.
        self.assertTrue(lesson.refusal_stalled())

    def test_three_failures_withdraw_the_repair(self) -> None:
        for _ in range(3):
            self.observe("NO_EFFECT")
        lesson = learning.load_lessons(self.plane.ap_root)[self.KEY]
        self.assertEqual(lesson.confidence, "DISPROVEN")
        self.assertTrue(lesson.withdrawn(controller.utc_now(), cooldown_minutes=720))

    def test_withdrawal_is_a_cooldown_not_a_life_sentence(self) -> None:
        for _ in range(3):
            self.observe("NO_EFFECT")
        lesson = learning.load_lessons(self.plane.ap_root)[self.KEY]
        later = controller.utc_now() + timedelta(minutes=721)
        self.assertTrue(lesson.withdrawn(controller.utc_now(), cooldown_minutes=720))
        self.assertFalse(lesson.withdrawn(later, cooldown_minutes=720))

    def test_one_success_keeps_a_repair_alive(self) -> None:
        self.observe("UNBLOCKED")
        for _ in range(5):
            self.observe("NO_EFFECT")
        lesson = learning.load_lessons(self.plane.ap_root)[self.KEY]
        self.assertEqual(lesson.confidence, "PROVISIONAL")
        self.assertFalse(lesson.withdrawn(controller.utc_now(), cooldown_minutes=720))

    def test_duplicate_records_from_a_union_merge_are_counted_once(self) -> None:
        self.observe("NO_EFFECT")
        path = next(learning.lessons_dir(self.plane.ap_root).glob("*.jsonl"))
        line = path.read_text(encoding="utf-8").strip()
        # A union merge can replay an identical record; it must not invent evidence.
        path.write_text(line + "\n" + line + "\n", encoding="utf-8")
        lesson = learning.load_lessons(self.plane.ap_root)[self.KEY]
        self.assertEqual(lesson.counts["NO_EFFECT"], 1)

    def test_lessons_live_outside_gitignored_state(self) -> None:
        self.observe("UNBLOCKED")
        directory = learning.lessons_dir(self.plane.ap_root)
        self.assertTrue(directory.is_dir())
        self.assertNotIn("state", directory.relative_to(self.plane.ap_root).parts)
        self.assertTrue(list(directory.glob("*.jsonl")))
        # The record survives a brand-new plane object (a fresh session).
        reloaded = controller.ControlPlane(self.root)
        self.assertEqual(len(learning.load_lessons(reloaded.ap_root)), 1)

    def test_a_repair_is_settled_by_a_later_pass_not_by_itself(self) -> None:
        """The heart of it: running is not holding."""

        self.publish_claim(expires_at=PAST)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "commit_lessons": False},
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(report["disposition"], "HEALED")
        # The repair is recorded as an attempt, deliberately unjudged.
        self.assertEqual(len(learning.unsettled_attempts(self.plane.ap_root)), 1)
        self.assertEqual(learning.load_lessons(self.plane.ap_root), {})

        # A later pass sees the wedge is gone and settles it as having held.
        later = controller.ControlPlane(
            self.root, clock=lambda: controller.utc_now() + timedelta(minutes=5)
        )
        healing.heal_round(
            later,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "commit_lessons": False},
            status=self.RECONCILED_STATUS,
        )
        lesson = learning.consult(self.plane.ap_root, "CLAIM_DEFUNCT", "expired", "reap")
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.counts["UNBLOCKED"], 1)
        self.assertEqual(learning.unsettled_attempts(self.plane.ap_root), ())

    def test_a_wedge_that_returns_settles_as_did_not_hold(self) -> None:
        """A repair that must be re-applied every round is not working."""

        self.publish_claim(expires_at=PAST)
        healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "commit_lessons": False},
            status=self.RECONCILED_STATUS,
        )
        # The same mechanism wedges the node again before the next pass.
        self.publish_claim(expires_at=PAST)
        later = controller.ControlPlane(
            self.root, clock=lambda: controller.utc_now() + timedelta(minutes=5)
        )
        healing.heal_round(
            later,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "commit_lessons": False},
            status=self.RECONCILED_STATUS,
        )
        lesson = learning.consult(self.plane.ap_root, "CLAIM_DEFUNCT", "expired", "reap")
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.counts["NO_EFFECT"], 1)
        self.assertEqual(lesson.counts["UNBLOCKED"], 0)

    def test_healer_withdraws_a_disproven_repair_instead_of_retrying(self) -> None:
        for _ in range(3):
            learning.record_outcome(
                self.plane.ap_root,
                verdict="CLAIM_DEFUNCT",
                proof_kind="expired",
                action="reap",
                outcome="NO_EFFECT",
                node_id=NODE,
                actor="test:healer",
                observed_at=controller.format_time(controller.utc_now()),
                guidance="retire this claim by hand; the automatic reap never holds here",
            )
        claim = self.publish_claim(expires_at=PAST)
        report = healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "commit_lessons": False},
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(report["disposition"], "RESOLVE_BLOCKERS")
        withdrawn = [a for a in report["actions"] if a["outcome"] == "WITHDRAWN"]
        self.assertEqual(len(withdrawn), 1)
        self.assertIn("by hand", report["stuck"][0]["instructions"])
        # The claim it refused to reap is untouched.
        self.assertEqual(self.remote_head(), claim)

    def refuse(self, head: str | None) -> None:
        learning.record_outcome(
            self.plane.ap_root,
            verdict="BRANCH_DEFUNCT",
            proof_kind="expired",
            action="quarantine",
            outcome="REFUSED",
            node_id=NODE,
            actor="test:healer",
            observed_at=controller.format_time(controller.utc_now()),
            head=head,
            guidance="the remote forbids deleting this ref; ask an admin",
        )

    def test_a_refused_repair_that_never_moves_the_head_is_withdrawn(self) -> None:
        """Branch protection must not become an infinite retry loop."""

        for _ in range(3):
            self.refuse("a" * 40)
        lesson = learning.load_lessons(self.plane.ap_root)[
            "BRANCH_DEFUNCT|expired|quarantine"
        ]
        self.assertEqual(lesson.confidence, "UNTRIED")  # refusals prove nothing
        self.assertTrue(lesson.refusal_stalled())
        self.assertTrue(lesson.withdrawn(controller.utc_now(), cooldown_minutes=720))

    def test_a_lost_race_keeps_its_retry(self) -> None:
        """A refusal whose head moved is a worker winning; retry is correct."""

        for head in ("a" * 40, "b" * 40, "c" * 40):
            self.refuse(head)
        lesson = learning.load_lessons(self.plane.ap_root)[
            "BRANCH_DEFUNCT|expired|quarantine"
        ]
        self.assertEqual(lesson.stuck_refusals, 1)
        self.assertFalse(lesson.refusal_stalled())
        self.assertFalse(lesson.withdrawn(controller.utc_now(), cooldown_minutes=720))

    def test_a_stall_reap_is_keyed_by_its_real_proof(self) -> None:
        """The recorded key must be the documented one, not an empty proof."""

        self.publish_claim(expires_at=FUTURE, committer_date=OLD_COMMIT_DATE)
        diagnosis = healing.diagnose_node(
            self.plane, NODE, policy=healing.DEFAULT_POLICY
        )
        self.assertEqual(diagnosis.verdict, "CLAIM_STALLED")
        self.assertEqual(healing.proof_kind_of(diagnosis), "stalled-bare-claim")

    def test_learning_disabled_records_nothing(self) -> None:
        self.publish_claim(expires_at=PAST)
        healing.heal_round(
            self.plane,
            actor="test:healer",
            nodes=[NODE],
            policy={**self.policy, "learn": False, "commit_lessons": False},
            status=self.RECONCILED_STATUS,
        )
        self.assertEqual(learning.load_lessons(self.plane.ap_root), {})

    def test_lessons_are_committed_to_the_branch(self) -> None:
        self.use_release_branch()
        self.observe("UNBLOCKED")
        self.assertTrue(learning.uncommitted_lessons(self.plane))
        result = learning.commit_lessons(self.plane, actor="test:healer")
        self.assertEqual(result["outcome"], "committed")
        self.assertEqual(learning.uncommitted_lessons(self.plane), ())
        author = git(self.root, "show", "-s", "--format=%ae", "HEAD")
        self.assertEqual(author, learning.LESSON_COMMIT_EMAIL)
        self.assertNotEqual(author, controller.RECEIPT_COMMIT_EMAIL)
        self.assertEqual(
            learning.commit_lessons(self.plane, actor="test:healer")["outcome"],
            "nothing-to-commit",
        )

    def test_a_lesson_commit_never_sweeps_unrelated_work(self) -> None:
        self.use_release_branch()
        self.observe("UNBLOCKED")
        (self.root / "unrelated.txt").write_text("not a lesson\n", encoding="utf-8")
        git(self.root, "add", "unrelated.txt")
        learning.commit_lessons(self.plane, actor="test:healer")
        committed = git(self.root, "show", "--name-only", "--format=", "HEAD")
        self.assertIn("lessons", committed)
        self.assertNotIn("unrelated.txt", committed)

    def test_lessons_are_never_committed_to_main(self) -> None:
        self.observe("UNBLOCKED")
        git(self.root, "checkout", "-q", "-B", "main")
        result = learning.commit_lessons(self.plane, actor="test:healer")
        self.assertEqual(result["outcome"], "refused")
        self.assertIn("main", result["reason"])


class AttendedHostSurfaceTests(HealingFixture):
    """The attended host's evidence probes must respect healed history."""

    def test_inspect_runtime_authority_reports_plane_state(self) -> None:
        host = attended.AttendedCodexHost(self.plane)
        result = host.inspect_runtime_authority(repo_root=self.root)
        self.assertEqual(result["target_branch"], self.plane.target_branch)
        self.assertEqual(result["active_claims"], [])
        self.assertIsNone(result["active_validation_lease"])
        self.assertTrue(result["quiescent"])

    def test_resolved_ledger_is_not_failure_evidence(self) -> None:
        blockers = Path(self.plane.blockers_dir)
        blockers.mkdir(parents=True, exist_ok=True)
        (blockers / f"{NODE}.jsonl").write_text(
            json.dumps(
                {"blocker_id": "sha256:b1", "node_id": NODE, "status": "OPEN"}
            )
            + "\n"
            + json.dumps(
                {
                    "event": "BLOCKER_RESOLVED",
                    "blocker_id": "sha256:b1",
                    "node_id": NODE,
                    "status": "RESOLVED",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        host = attended.AttendedCodexHost(self.plane)
        self.assertIsNone(host._recorded_failure(NODE))
        (blockers / f"{NODE}.jsonl").write_text(
            json.dumps(
                {"blocker_id": "sha256:b2", "node_id": NODE, "status": "OPEN"}
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertIsNotNone(host._recorded_failure(NODE))

    def test_pending_cards_deduplicate_by_node(self) -> None:
        host = attended.AttendedCodexHost(self.plane)
        host.bind_tasks(
            [
                {"launch_instruction_id": "sha256:attempt-1", "node_id": NODE},
                {"launch_instruction_id": "sha256:attempt-2", "node_id": NODE},
            ]
        )
        host.create_thread(
            title="Hive Mind MISSION-400 attempt 1",
            prompt="do the work",
            idempotency_key="sha256:attempt-1",
        )
        host.create_thread(
            title="Hive Mind MISSION-400 attempt 2",
            prompt="do the work again",
            idempotency_key="sha256:attempt-2",
        )
        self.assertEqual(len(host.pending_cards()), 1)


if __name__ == "__main__":
    unittest.main()
