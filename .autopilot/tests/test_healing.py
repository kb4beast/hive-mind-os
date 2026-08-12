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
