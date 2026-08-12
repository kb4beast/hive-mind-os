from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
import sealed_recovery  # noqa: E402
from durable_controller import ControlPlane as DurableControlPlane  # noqa: E402
from sealed_recovery import (  # noqa: E402
    BUILDER_APPEALS_PATH,
    BUILDER_COURT_PATH,
    BUILDER_REPLAN_PATH,
    SealedRecoveryMixin,
)


class SealedRecoveryBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        self.original_capability = sealed_recovery.SEALED_CAPABILITY_COMMIT
        if self.original_capability == "0" * 40:
            sealed_recovery.SEALED_CAPABILITY_COMMIT = "f" * 40
            authority_path = self.root / ".autopilot" / "sealed-repair-authorities.json"
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            for record in authority["repair_authorities"]:
                record["capability_commit"] = "f" * 40
            authority_path.write_text(json.dumps(authority), encoding="utf-8")
            builder_path = self.root / ".autopilot" / "builder-330-recovery-bootstrap.json"
            builder = json.loads(builder_path.read_text(encoding="utf-8"))
            builder["capability_commit"] = "f" * 40
            builder_path.write_text(json.dumps(builder), encoding="utf-8")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control), encoding="utf-8")
        self.plane = autopilot.ControlPlane(self.root)
        self.plane._live_release_issues = lambda _record, _expected=None: ()  # type: ignore[method-assign]
        self.plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]

    def tearDown(self) -> None:
        sealed_recovery.SEALED_CAPABILITY_COMMIT = self.original_capability
        self.temporary.cleanup()

    @property
    def authority_path(self) -> Path:
        return self.root / ".autopilot" / "sealed-repair-authorities.json"

    def _record(self, node_id: str) -> dict:
        document = json.loads(self.authority_path.read_text(encoding="utf-8"))
        return next(record for record in document["repair_authorities"] if record["node_id"] == node_id)

    def _rewrite_record(self, node_id: str, key: str, value: object) -> None:
        document = json.loads(self.authority_path.read_text(encoding="utf-8"))
        record = next(record for record in document["repair_authorities"] if record["node_id"] == node_id)
        record[key] = value
        self.authority_path.write_text(json.dumps(document), encoding="utf-8")

    def _live_snapshot(self, node_id: str) -> dict:
        record = self._record(node_id)
        return {
            "target_sha": "d" * 40,
            "pull_requests": [
                {
                    "node_id": node_id,
                    "number": record["pr"],
                    "state": "open",
                    "merged": False,
                    "ci": "failure" if node_id == "ORCH-300" else "success",
                    "base": self.plane.target_branch,
                    "head": record["branch"],
                    "head_sha": record["old_receipt_commit"],
                    "draft": True,
                    "created_at": record["pr_created_at"],
                }
            ],
            "branches": [{"name": record["branch"], "sha": record["old_receipt_commit"]}],
        }

    def _ready_repair(self, node_id: str) -> dict:
        record = self._record(node_id)
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        self.plane.github_snapshot = lambda: self._live_snapshot(node_id)  # type: ignore[method-assign]
        self.plane._repair_live_issues = lambda _record: ()  # type: ignore[method-assign]
        self.plane.assert_start_now = lambda _node: {"release_id": "release"}  # type: ignore[method-assign]
        self.plane.current_release = lambda: {"release_id": "release"}  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        self.plane._fetch_exact_repair_head = lambda _record: "refs/test/fetch"  # type: ignore[method-assign]
        self.plane._old_repair_history_issues = lambda _record: ()  # type: ignore[method-assign]
        self.plane.is_ancestor = lambda _ancestor, _descendant: True  # type: ignore[method-assign]
        return record

    def test_exact_repair_records_and_builder_court_chain_validate(self) -> None:
        self.assertEqual(self.plane.sealed_recovery_issues(), ())
        records = self.plane._repair_records()
        self.assertEqual(set(records), {"OPTIMIZER-370", "ORCH-300"})
        for record in records.values():
            identities = {
                record["advocate_identity"],
                record["cross_examiner_identity"],
                record["expert_witness_identity"],
                record["judge_identity"],
            }
            self.assertEqual(len(identities), 4)
            self.assertTrue(record["court_id"])
            self.assertTrue(record["owner_identity"])
            self.assertTrue(record["outcome_metric"])
            self.assertTrue(record["evidence_refs"])
            self.assertTrue(record["acceptance_test_mapping"])
            self.assertTrue(record["authenticated_snapshot_retrieval_digest"].startswith("sha256:"))

    def test_each_wrong_optimizer_identity_and_scope_fails_closed(self) -> None:
        mutations = {
            "node_id": "optimizer-370",
            "branch": "Autopilot/optimizer-370",
            "pr": 136,
            "incident_target_sha": "a" * 40,
            "candidate_commit": "b" * 40,
            "old_receipt_commit": "c" * 40,
            "plan_fingerprint": "sha256:" + "0" * 64,
            "allowed_paths": ["src/hive_mind_os/brain_kernel/planner.py"],
        }
        original = self.authority_path.read_text(encoding="utf-8")
        for key, value in mutations.items():
            with self.subTest(key=key):
                self.authority_path.write_text(original, encoding="utf-8")
                self._rewrite_record("OPTIMIZER-370", key, value)
                self.assertTrue(self.plane.sealed_recovery_issues())
        self.authority_path.write_text(original, encoding="utf-8")

    def test_capability_retarget_fails_closed(self) -> None:
        self._rewrite_record("OPTIMIZER-370", "capability_commit", "e" * 40)
        self.assertIn("compiled pin", "; ".join(self.plane.sealed_recovery_issues()))

    def test_literal_origin_release_divergence_fails_live_authentication(self) -> None:
        record = self._record("OPTIMIZER-370")
        self.plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._remote_ref_sha = lambda _ref: "e" * 40  # type: ignore[method-assign]
        issues = SealedRecoveryMixin._live_release_issues(self.plane, record)
        self.assertIn("differs", "; ".join(issues))

    def test_each_wrong_orch_identity_pr_tree_and_case_fails_closed(self) -> None:
        mutations = {
            "node_id": "Orch-300",
            "branch": "autopilot/ORCH-300",
            "replacement_pr": 132,
            "expected_old_pr": 131,
            "claim_target_sha": "a" * 40,
            "candidate_tree": "b" * 40,
            "old_receipt_tree": "c" * 40,
            "claim_topology": "direct_zero_path_child",
        }
        original = self.authority_path.read_text(encoding="utf-8")
        for key, value in mutations.items():
            with self.subTest(key=key):
                self.authority_path.write_text(original, encoding="utf-8")
                self._rewrite_record("ORCH-300", key, value)
                self.assertTrue(self.plane.sealed_recovery_issues())
        self.authority_path.write_text(original, encoding="utf-8")

    def test_builder_exact_records_reject_tamper_and_explorer_substitution(self) -> None:
        for relative in (BUILDER_COURT_PATH, BUILDER_APPEALS_PATH, BUILDER_REPLAN_PATH):
            path = self.root / relative
            original = path.read_text(encoding="utf-8")
            value = json.loads(original)
            value["node_id"] = "EXPLORER-310"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertTrue(self.plane._builder_record_issues())
            path.write_text(original, encoding="utf-8")

    def test_wrong_pr_snapshot_fields_and_moved_head_block_repair(self) -> None:
        for node_id in ("OPTIMIZER-370", "ORCH-300"):
            record = self._ready_repair(node_id)
            for key, value in (
                ("number", 999),
                ("state", "closed"),
                ("merged", True),
                ("base", "main"),
                ("head", str(record["branch"]).upper()),
                ("head_sha", "f" * 40),
                ("draft", False),
            ):
                snapshot = self._live_snapshot(node_id)
                snapshot["pull_requests"][0][key] = value
                self.plane.github_snapshot = lambda snapshot=snapshot: snapshot  # type: ignore[method-assign]
                with self.subTest(node_id=node_id, key=key):
                    self.assertTrue(SealedRecoveryMixin._repair_live_issues(self.plane, record))

    def test_repair_claim_requires_remote_publication_and_literal_origin(self) -> None:
        for node_id in ("OPTIMIZER-370", "ORCH-300"):
            self._ready_repair(node_id)
            with self.assertRaises(autopilot.ClaimError):
                self.plane.claim(node_id, "test:owner", publish_remote=False)
            with self.assertRaises(autopilot.ClaimError):
                self.plane.claim(node_id, "test:owner", publish_remote=True, remote="Origin")

    def test_exact_claim_cas_is_single_use_and_rollback_restores_old_head(self) -> None:
        record = self._ready_repair("OPTIMIZER-370")
        state = {"head": record["old_receipt_commit"]}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane._create_repair_claim_commits = lambda _record, _local: ("c" * 40, "d" * 40)  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        claim = self.plane.claim("OPTIMIZER-370", "test:owner", publish_remote=True)
        self.assertEqual(claim["remote_claim_commit"], "c" * 40)
        self.assertEqual(claim["remote_head_commit"], "d" * 40)
        with self.assertRaises(autopilot.ClaimError):
            self.plane.claim("OPTIMIZER-370", "test:other", publish_remote=True)
        self.plane.release("OPTIMIZER-370", "test:owner", reason="bounded rollback")
        self.assertEqual(state["head"], record["old_receipt_commit"])

    def test_claim_compensation_restores_old_receipt_after_local_failure(self) -> None:
        record = self._ready_repair("OPTIMIZER-370")
        state = {"head": record["old_receipt_commit"]}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane._create_repair_claim_commits = lambda _record, _local: ("c" * 40, "d" * 40)  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        original_write = sealed_recovery.atomic_write_json
        try:
            calls = 0

            def fail_after_preparation(*_args, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("disk full")
                return original_write(*_args, **_kwargs)

            sealed_recovery.atomic_write_json = fail_after_preparation
            with self.assertRaises(OSError):
                self.plane.claim("OPTIMIZER-370", "test:owner", publish_remote=True)
        finally:
            sealed_recovery.atomic_write_json = original_write
        self.assertEqual(state["head"], record["old_receipt_commit"])

    def test_failed_claim_compensation_preserves_adverse_lease_evidence(self) -> None:
        record = self._ready_repair("OPTIMIZER-370")
        state = {"head": record["old_receipt_commit"]}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane._create_repair_claim_commits = lambda _record, _local: ("c" * 40, "d" * 40)  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            if expected == record["old_receipt_commit"]:
                state["head"] = new
                return
            raise autopilot.ClaimError("rollback rejected")

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        original_write = sealed_recovery.atomic_write_json
        calls = 0

        def fail_claimed(path, value):
            nonlocal calls
            if path == self.plane.claim_path("OPTIMIZER-370"):
                calls += 1
                if calls == 2:
                    raise OSError("disk full")
            return original_write(path, value)

        try:
            sealed_recovery.atomic_write_json = fail_claimed
            with self.assertRaises(OSError):
                self.plane.claim("OPTIMIZER-370", "test:owner", publish_remote=True)
        finally:
            sealed_recovery.atomic_write_json = original_write
        retained = json.loads(self.plane.claim_path("OPTIMIZER-370").read_text(encoding="utf-8"))
        self.assertEqual(retained["status"], "ADVERSE")
        self.assertEqual(state["head"], "d" * 40)

    def test_release_race_after_claim_cas_restores_old_head(self) -> None:
        record = self._ready_repair("OPTIMIZER-370")
        state = {"head": record["old_receipt_commit"]}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane._create_repair_claim_commits = lambda _record, _local: ("c" * 40, "d" * 40)  # type: ignore[method-assign]
        calls = 0

        def binding(_claim=None):
            nonlocal calls
            calls += 1
            return () if calls == 1 else ("release moved",)

        self.plane._release_binding_issues = binding  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "release changed"):
            self.plane.claim("OPTIMIZER-370", "test:owner", publish_remote=True)
        self.assertEqual(state["head"], record["old_receipt_commit"])
        self.assertFalse(self.plane.claim_path("OPTIMIZER-370").exists())

    def test_live_origin_release_race_after_claim_cas_restores_old_head(self) -> None:
        record = self._ready_repair("OPTIMIZER-370")
        state = {"head": record["old_receipt_commit"]}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane._create_repair_claim_commits = lambda _record, _local: ("c" * 40, "d" * 40)  # type: ignore[method-assign]
        live_checks = 0

        def live_release(_record, _expected=None):
            nonlocal live_checks
            live_checks += 1
            return () if live_checks == 1 else ("literal origin release moved",)

        self.plane._live_release_issues = live_release  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "literal origin release moved"):
            self.plane.claim("OPTIMIZER-370", "test:owner", publish_remote=True)
        self.assertEqual(state["head"], record["old_receipt_commit"])
        self.assertFalse(self.plane.claim_path("OPTIMIZER-370").exists())

    def test_preparing_prepared_and_expired_claim_restart_states_recover_exact_head(self) -> None:
        record = self._record("OPTIMIZER-370")
        path = self.plane.claim_path("OPTIMIZER-370")
        state = {"head": record["old_receipt_commit"]}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        base = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND,
            "node_id": "OPTIMIZER-370", "owner": "test:owner",
            "authority_digest": autopilot.digest_json(record),
            "expires_at": "2030-01-01T00:00:00Z",
        }
        autopilot.atomic_write_json(path, {**base, "status": "PREPARING", "remote_claim_commit": None})
        self.plane._recover_interrupted_repair_claim(record)
        self.assertFalse(path.exists())
        state["head"] = "d" * 40
        autopilot.atomic_write_json(path, {
            **base, "status": "PREPARED", "remote_claim_commit": "c" * 40,
            "remote_head_commit": "d" * 40,
        })
        self.plane._recover_interrupted_repair_claim(record)
        self.assertEqual(state["head"], record["old_receipt_commit"])
        self.assertFalse(path.exists())
        state["head"] = "d" * 40
        autopilot.atomic_write_json(path, {
            **base, "status": "CLAIMED", "expires_at": "2020-01-01T00:00:00Z",
            "remote_claim_commit": "c" * 40, "remote_head_commit": "d" * 40,
        })
        self.plane._recover_interrupted_repair_claim(record)
        self.assertEqual(state["head"], record["old_receipt_commit"])
        self.assertFalse(path.exists())

    def test_optimizer_and_orch_claim_topologies_are_distinct_and_exact(self) -> None:
        optimizer = self.plane._repair_records()["OPTIMIZER-370"]
        tree, parents = self.plane._repair_claim_tree_and_parents(
            optimizer,
            "cfe17ff7d6b06bdaa42e9ba6ec2a75a9c66c6a58",
        )
        self.assertEqual(tree, optimizer["old_receipt_tree"])
        self.assertEqual(parents, (optimizer["old_receipt_commit"],))
        orch = self.plane._repair_records()["ORCH-300"]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "f" * 40 + "\n", "")  # type: ignore[method-assign]
        self.plane._diff_paths = lambda _base, _final: tuple(orch["allowed_paths"])  # type: ignore[method-assign]
        tree, parents = self.plane._repair_claim_tree_and_parents(
            orch,
            "cfe17ff7d6b06bdaa42e9ba6ec2a75a9c66c6a58",
        )
        self.assertEqual(
            parents,
            (
                "dbb8cb736eb98e77ef35eb141b2e55e492fbcf88",
                "cfe17ff7d6b06bdaa42e9ba6ec2a75a9c66c6a58",
            ),
        )
        self.assertEqual(
            set(self.plane._diff_paths("cfe17ff7d6b06bdaa42e9ba6ec2a75a9c66c6a58", tree)),
            set(orch["allowed_paths"]),
        )

    def test_clean_single_branch_clone_fetches_pinned_old_head_before_tree_work(self) -> None:
        seed = self.root / "seed"
        remote = self.root / "origin.git"
        clone = self.root / "release-only"

        def run(*args: str, cwd: Path | None = None) -> str:
            return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

        run("git", "init", str(seed))
        run("git", "config", "user.name", "Fixture", cwd=seed)
        run("git", "config", "user.email", "fixture@example.invalid", cwd=seed)
        (seed / "base.txt").write_text("base\n", encoding="utf-8")
        run("git", "add", "base.txt", cwd=seed)
        run("git", "commit", "-m", "release", cwd=seed)
        release = run("git", "rev-parse", "HEAD", cwd=seed)
        run("git", "branch", "release/hive-mind-os-singleton-20260810-r2", release, cwd=seed)
        (seed / "old.txt").write_text("old\n", encoding="utf-8")
        run("git", "add", "old.txt", cwd=seed)
        run("git", "commit", "-m", "old head", cwd=seed)
        old = run("git", "rev-parse", "HEAD", cwd=seed)
        old_tree = run("git", "rev-parse", "HEAD^{tree}", cwd=seed)
        run("git", "branch", "autopilot/optimizer-370", old, cwd=seed)
        run("git", "init", "--bare", str(remote))
        run("git", "push", str(remote), "--all", cwd=seed)
        run("git", "clone", "--no-local", "--single-branch", "--branch", "release/hive-mind-os-singleton-20260810-r2", str(remote), str(clone))
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], clone / ".autopilot")
        plane = autopilot.ControlPlane(clone)
        self.assertFalse(plane.git_object_exists(old))
        local_ref = plane._fetch_exact_repair_head({
            "node_id": "OPTIMIZER-370",
            "branch": "autopilot/optimizer-370",
            "old_receipt_commit": old,
            "old_receipt_tree": old_tree,
        })
        self.assertEqual(run("git", "rev-parse", local_ref, cwd=clone), old)

    def _receipt(self, node_id: str) -> dict:
        record = self._record(node_id)
        node = self.plane.node(node_id)
        return {
            "schema_version": 1,
            "plan_fingerprint": self.plane.expected_plan_fingerprint,
            "node_id": node_id,
            "contract_version": 1,
            "base_commit": record["incident_target_sha"] if node_id == "OPTIMIZER-370" else "d" * 40,
            "base_tree": "a" * 40,
            "final_commit": "e" * 40,
            "final_tree": "b" * 40,
            "branch": record["branch"],
            "pr": record["replacement_pr"],
            "changed_paths": list(record["allowed_paths"]),
            "tests": [
                {"name": name, "status": "passed", "command": ["python", "-m", "unittest"]}
                for name in node["required_tests"]
            ],
            "evidence_refs": ["evidence:repair"],
            "model_runtime": {"provider": "fixture", "model": "fixture"},
            "role_identities": [
                {"role": role, "identity": f"role:{role}", "identity_kind": "model_role"}
                for role in node["roles"]
            ],
            "authority": {
                "node_id": node_id,
                "autonomy_level": "A3",
                "grants": [record["grant_id"]],
                "execution_merge_commit": "c" * 40,
                "grant_id": record["grant_id"],
                "supersedes_receipt_commit": record["old_receipt_commit"],
                "repair_authority_digest": autopilot.digest_json(record),
                "repair_claim_commit": "c" * 40,
                "execution_target_sha": "d" * 40,
                "repair_claim_payload_digest": "sha256:" + "0" * 64,
            },
            "consultations": [],
            "acceptance_decision": "ADAPT",
            "timestamp": "2030-01-01T00:00:00Z",
            "rollback_ref": "revert:repair",
        }

    def _install_terminal_optimizer_cut(
        self,
        *,
        claim_present: bool,
        continuation_status: str = "CONSUMED",
    ) -> tuple[dict, dict, str, Path]:
        node_id = "OPTIMIZER-370"
        owner = "test:continuation"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        receipt_commit = "f" * 40
        claimed = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND,
            "node_id": node_id,
            "owner": owner,
            "status": "CLAIMED",
            "grant_id": record["grant_id"],
            "expires_at": "2026-08-11T21:13:07.231123Z",
            "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        claim = {**claimed, "status": "COMPLETING"}
        if claim_present:
            autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        consuming = {
            "kind": sealed_recovery.OPTIMIZER_CONTINUATION_KIND,
            "status": "CONSUMING",
            "target_sha": "9" * 40,
            "grant_id": record["grant_id"],
            "claim_digest": autopilot.digest_json(claimed),
        }
        continuation = dict(consuming)
        continuation["status"] = continuation_status
        if continuation_status == "CONSUMED":
            continuation.update({
                "previous_digest": autopilot.digest_json(consuming),
                "receipt_commit": receipt_commit,
            })
        autopilot.atomic_write_json(self.plane.optimizer_continuation_path, continuation)
        intent_path = (
            self.plane.state_dir / "sealed-repair-completion-optimizer-370.json"
        )
        autopilot.atomic_write_json(intent_path, {
            "schema_version": 1,
            "kind": "hive-mind-autopilot-sealed-repair-completion-v1",
            "status": "PREPARED",
            "node_id": node_id,
            "owner": owner,
            "target_sha": claimed["target_sha"],
            "remote_expected_final": receipt["final_commit"],
            "receipt_digest": autopilot.digest_json(receipt),
            "receipt_commit": receipt_commit,
            "active_claim_digest": autopilot.digest_json(claimed),
            "prepared_at": "2026-08-11T20:00:00Z",
            "continuation_digest": autopilot.digest_json(consuming),
            "continuation_target_sha": consuming["target_sha"],
            "continuation_grant_id": consuming["grant_id"],
        })
        autopilot.atomic_write_json(self.plane.receipt_path(node_id), receipt)
        autopilot.append_jsonl(self.plane.state_dir / "receipt-index.jsonl", {
            "node_id": node_id,
            "receipt_commit": receipt_commit,
            "receipt_digest": autopilot.digest_json(receipt),
            "final_commit": receipt["final_commit"],
            "supersedes_receipt_commit": record["old_receipt_commit"],
            "timestamp": receipt["timestamp"],
        })
        self.plane.remote_branch_sha = lambda _branch: receipt_commit  # type: ignore[method-assign]
        self.plane._commit_parents = lambda _sha: (receipt["final_commit"],)  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: receipt["final_tree"]  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(  # type: ignore[method-assign]
            args,
            0,
            self.plane._receipt_message(receipt)
            if tuple(args[:3]) == ("show", "-s", "--format=%B")
            else "",
            "",
        )
        return record, receipt, receipt_commit, intent_path

    @staticmethod
    def _consultation() -> dict:
        return {
            "request_id": "CONSULT-sealed", "mission_id": "MISSION-sealed",
            "question": "Is this recovery evidence sufficient?", "reason_code": "AMBIGUITY",
            "requesting_role": "builder", "consulted_roles": ["architect", "curator"],
            "round": 1, "suspected_cheating": False, "evidence_refs": ["evidence:sealed"],
            "decision": "RESOLVED", "answer": "Resolved from exact evidence", "dissent": [],
            "human_escalation": False, "authority_class": None, "role_first_exhausted": True,
            "cheating_disposition": "NOT_APPLICABLE",
            "identity_records": [
                {"role": "architect", "identity": "role:architect", "identity_kind": "model_role"},
                {"role": "curator", "identity": "role:curator", "identity_kind": "model_role"},
            ],
        }

    def test_replacement_requires_supersedes_grant_exact_pr_and_scope(self) -> None:
        for node_id in ("OPTIMIZER-370", "ORCH-300"):
            self.assertEqual(self.plane._replacement_receipt_issues(node_id, self._receipt(node_id)), ())
            for mutation in ("missing_supersedes", "wrong_grant", "wrong_pr", "scope"):
                receipt = self._receipt(node_id)
                if mutation == "missing_supersedes":
                    receipt["authority"].pop("supersedes_receipt_commit")
                elif mutation == "wrong_grant":
                    receipt["authority"]["grant_id"] = "other"
                elif mutation == "wrong_pr":
                    receipt["pr"] = 999
                else:
                    receipt["changed_paths"] = ["src/outside.py"]
                with self.subTest(node_id=node_id, mutation=mutation):
                    self.assertTrue(self.plane._replacement_receipt_issues(node_id, receipt))

    def test_replacement_receipt_rejects_schema_expansion_and_weak_types(self) -> None:
        def consultation_mutation(receipt: dict, mutation: str) -> None:
            consultation = self._consultation()
            receipt["consultations"] = [consultation]
            if mutation == "extra_consultation_key":
                consultation["unexpected_nested_key"] = True
            elif mutation == "extra_identity_key":
                consultation["identity_records"][0]["unexpected_nested_key"] = True
            elif mutation == "duplicate_identity":
                consultation["identity_records"].append(copy.deepcopy(consultation["identity_records"][0]))
            elif mutation == "blank_consultation_identity":
                consultation["identity_records"][0]["identity"] = "  "
            elif mutation == "typed_consultation_identity":
                consultation["identity_records"][0]["identity"] = 1
            elif mutation == "reused_consultation_identity":
                consultation["identity_records"][1]["identity"] = consultation["identity_records"][0]["identity"]
            elif mutation == "wrong_consultation_identity_kind":
                consultation["identity_records"][0]["identity_kind"] = "fixture"
            elif mutation == "requester_self_consultation":
                consultation["consulted_roles"][0] = "builder"
                consultation["identity_records"][0]["role"] = "builder"
            else:
                consultation["consulted_roles"].append("architect")

        valid = self._receipt("OPTIMIZER-370")
        valid["consultations"] = [self._consultation()]
        self.assertEqual(self.plane._replacement_receipt_issues("OPTIMIZER-370", valid), ())

        mutations = {
            "extra_top_level": lambda receipt: receipt.__setitem__("unexpected", True),
            "blank_identity": lambda receipt: receipt["role_identities"][0].__setitem__("identity", "  "),
            "missing_runtime": lambda receipt: receipt.__setitem__("model_runtime", None),
            "non_string_evidence": lambda receipt: receipt.__setitem__("evidence_refs", [1]),
            "extra_test_key": lambda receipt: receipt["tests"][0].__setitem__("unexpected", True),
            "extra_runtime_key": lambda receipt: receipt["model_runtime"].__setitem__("unexpected", True),
            "duplicate_role": lambda receipt: receipt["role_identities"].append(
                copy.deepcopy(receipt["role_identities"][0])
            ),
            "non_hex_claim_digest": lambda receipt: receipt["authority"].__setitem__(
                "repair_claim_payload_digest", "sha256:" + "g" * 64
            ),
            "extra_consultation_key": lambda receipt: consultation_mutation(receipt, "extra_consultation_key"),
            "extra_identity_key": lambda receipt: consultation_mutation(receipt, "extra_identity_key"),
            "duplicate_identity": lambda receipt: consultation_mutation(receipt, "duplicate_identity"),
            "duplicate_consulted_role": lambda receipt: consultation_mutation(receipt, "duplicate_consulted_role"),
            "blank_consultation_identity": lambda receipt: consultation_mutation(receipt, "blank_consultation_identity"),
            "typed_consultation_identity": lambda receipt: consultation_mutation(receipt, "typed_consultation_identity"),
            "reused_consultation_identity": lambda receipt: consultation_mutation(receipt, "reused_consultation_identity"),
            "wrong_consultation_identity_kind": lambda receipt: consultation_mutation(receipt, "wrong_consultation_identity_kind"),
            "requester_self_consultation": lambda receipt: consultation_mutation(receipt, "requester_self_consultation"),
        }
        for name, mutate in mutations.items():
            receipt = self._receipt("OPTIMIZER-370")
            mutate(receipt)
            with self.subTest(name=name):
                self.assertTrue(self.plane._replacement_receipt_issues("OPTIMIZER-370", receipt))

    def test_canonical_receipt_schema_mutation_matrix_fails_closed(self) -> None:
        node_id = "OPTIMIZER-370"

        def baseline() -> dict:
            receipt = self._receipt(node_id)
            receipt["consultations"] = [self._consultation()]
            return receipt

        self.assertEqual(self.plane._sealed_receipt_shape_issues(node_id, baseline()), ())

        mutations: list[tuple[str, Callable[[dict], object]]] = []
        for key in baseline():
            mutations.append((f"missing_top_level_{key}", lambda value, key=key: value.pop(key)))
        for key in (
            "plan_fingerprint", "node_id", "base_commit", "base_tree", "final_commit",
            "final_tree", "branch", "timestamp", "rollback_ref", "acceptance_decision",
        ):
            mutations.append((f"blank_top_level_{key}", lambda value, key=key: value.__setitem__(key, " ")))
        for key in ("provider", "model"):
            mutations.append((f"blank_runtime_{key}", lambda value, key=key: value["model_runtime"].__setitem__(key, " ")))
        for key in ("role", "identity", "identity_kind"):
            mutations.append((f"blank_role_{key}", lambda value, key=key: value["role_identities"][0].__setitem__(key, " ")))
        for key in ("node_id", "autonomy_level", "grant_id"):
            mutations.append((f"blank_authority_{key}", lambda value, key=key: value["authority"].__setitem__(key, " ")))
        for key in (
            "supersedes_receipt_commit", "repair_authority_digest", "repair_claim_commit",
            "execution_merge_commit", "execution_target_sha", "repair_claim_payload_digest",
        ):
            mutations.append((f"blank_authority_binding_{key}", lambda value, key=key: value["authority"].__setitem__(key, " ")))
        for key in (
            "request_id", "mission_id", "question", "reason_code", "requesting_role",
            "decision", "cheating_disposition",
        ):
            mutations.append((f"blank_consultation_{key}", lambda value, key=key: value["consultations"][0].__setitem__(key, " ")))
        for key in ("role", "identity", "identity_kind"):
            mutations.append((f"blank_consultation_identity_{key}", lambda value, key=key: value["consultations"][0]["identity_records"][0].__setitem__(key, " ")))
        mutations.extend([
            ("unknown_top_level", lambda value: value.__setitem__("unknown", True)),
            ("schema_bool", lambda value: value.__setitem__("schema_version", True)),
            ("contract_wrong", lambda value: value.__setitem__("contract_version", 2)),
            ("fingerprint_nonhex", lambda value: value.__setitem__("plan_fingerprint", "sha256:" + "g" * 64)),
            ("node_blank", lambda value: value.__setitem__("node_id", " ")),
            ("branch_typed", lambda value: value.__setitem__("branch", 1)),
            ("commit_short", lambda value: value.__setitem__("final_commit", "abc")),
            ("tree_upper", lambda value: value.__setitem__("final_tree", "A" * 40)),
            ("pr_bool", lambda value: value.__setitem__("pr", True)),
            ("timestamp_invalid", lambda value: value.__setitem__("timestamp", "not-a-time")),
            ("timestamp_naive", lambda value: value.__setitem__("timestamp", "2030-01-01T00:00:00")),
            ("timestamp_offset", lambda value: value.__setitem__("timestamp", "2029-12-31T18:00:00-06:00")),
            ("timestamp_space", lambda value: value.__setitem__("timestamp", "2030-01-01 00:00:00Z")),
            ("timestamp_fraction", lambda value: value.__setitem__("timestamp", "2030-01-01T00:00:00.000Z")),
            ("rollback_blank", lambda value: value.__setitem__("rollback_ref", " ")),
            ("decision_unknown", lambda value: value.__setitem__("acceptance_decision", "ADOPT")),
            ("paths_typed", lambda value: value.__setitem__("changed_paths", None)),
            ("paths_blank", lambda value: value.__setitem__("changed_paths", [" "])),
            ("paths_duplicate", lambda value: value["changed_paths"].append(value["changed_paths"][0])),
            ("paths_unsorted", lambda value: value["changed_paths"].reverse()),
            ("evidence_blank", lambda value: value.__setitem__("evidence_refs", [" "])),
            ("evidence_duplicate", lambda value: value.__setitem__("evidence_refs", ["e", "e"])),
            ("runtime_extra", lambda value: value["model_runtime"].__setitem__("extra", True)),
            ("runtime_missing", lambda value: value["model_runtime"].pop("model")),
            ("runtime_blank", lambda value: value["model_runtime"].__setitem__("provider", " ")),
            ("test_extra", lambda value: value["tests"][0].__setitem__("extra", True)),
            ("test_missing", lambda value: value["tests"][0].pop("command")),
            ("test_blank", lambda value: value["tests"][0].__setitem__("name", " ")),
            ("test_status", lambda value: value["tests"][0].__setitem__("status", "failed")),
            ("test_status_blank", lambda value: value["tests"][0].__setitem__("status", " ")),
            ("test_command_type", lambda value: value["tests"][0].__setitem__("command", [1])),
            ("test_command_blank", lambda value: value["tests"][0].__setitem__("command", [" "])),
            ("test_order", lambda value: value["tests"].reverse()),
            ("role_extra", lambda value: value["role_identities"][0].__setitem__("extra", True)),
            ("role_missing", lambda value: value["role_identities"][0].pop("identity")),
            ("role_blank", lambda value: value["role_identities"][0].__setitem__("identity", " ")),
            ("role_kind", lambda value: value["role_identities"][0].__setitem__("identity_kind", "other")),
            ("role_reused_identity", lambda value: value["role_identities"][1].__setitem__(
                "identity", value["role_identities"][0]["identity"]
            )),
            ("role_order", lambda value: value["role_identities"].reverse()),
            ("authority_extra", lambda value: value["authority"].__setitem__("extra", True)),
            ("authority_missing", lambda value: value["authority"].pop("grant_id")),
            ("authority_grants_type", lambda value: value["authority"].__setitem__("grants", "grant")),
            ("authority_grants_duplicate", lambda value: value["authority"].__setitem__("grants", ["g", "g"])),
            ("authority_grants_blank", lambda value: value["authority"].__setitem__("grants", [" "])),
            ("authority_blank", lambda value: value["authority"].__setitem__("grant_id", " ")),
            ("authority_sha", lambda value: value["authority"].__setitem__("repair_claim_commit", "A" * 40)),
            ("authority_digest", lambda value: value["authority"].__setitem__(
                "repair_authority_digest", "sha256:" + "G" * 64
            )),
            ("consultation_extra", lambda value: value["consultations"][0].__setitem__("extra", True)),
            ("consultation_missing", lambda value: value["consultations"][0].pop("reason_code")),
            ("consultation_blank", lambda value: value["consultations"][0].__setitem__("question", " ")),
            ("consultation_round_bool", lambda value: value["consultations"][0].__setitem__("round", True)),
            ("consultation_bool_type", lambda value: value["consultations"][0].__setitem__(
                "suspected_cheating", 0
            )),
            ("consultation_array_type", lambda value: value["consultations"][0].__setitem__(
                "evidence_refs", "evidence"
            )),
            ("consultation_array_duplicate", lambda value: value["consultations"][0].__setitem__(
                "dissent", ["same", "same"]
            )),
            ("consultation_evidence_blank", lambda value: value["consultations"][0].__setitem__(
                "evidence_refs", [" "]
            )),
            ("consultation_dissent_blank", lambda value: value["consultations"][0].__setitem__(
                "dissent", [" "]
            )),
            ("consultation_decision", lambda value: value["consultations"][0].__setitem__(
                "decision", "UNKNOWN"
            )),
            ("consultation_answer_type", lambda value: value["consultations"][0].__setitem__("answer", 1)),
            ("consultation_answer_blank", lambda value: value["consultations"][0].__setitem__("answer", " ")),
            ("consultation_authority_blank", lambda value: value["consultations"][0].__setitem__(
                "authority_class", " "
            )),
            ("consultation_role_blank", lambda value: value["consultations"][0]["consulted_roles"].__setitem__(
                0, " "
            )),
            ("consultation_self", lambda value: value["consultations"][0]["consulted_roles"].__setitem__(
                0, "builder"
            )),
            ("consultation_duplicate_role", lambda value: value["consultations"][0].__setitem__(
                "consulted_roles", ["architect", "architect"]
            )),
            ("identity_extra", lambda value: value["consultations"][0]["identity_records"][0].__setitem__(
                "extra", True
            )),
            ("identity_missing", lambda value: value["consultations"][0]["identity_records"][0].pop(
                "identity_kind"
            )),
            ("identity_typed", lambda value: value["consultations"][0]["identity_records"][0].__setitem__(
                "identity", 1
            )),
            ("identity_kind", lambda value: value["consultations"][0]["identity_records"][0].__setitem__(
                "identity_kind", "other"
            )),
            ("identity_reuse", lambda value: value["consultations"][0]["identity_records"][1].__setitem__(
                "identity", value["consultations"][0]["identity_records"][0]["identity"]
            )),
            ("identity_order", lambda value: value["consultations"][0]["identity_records"].reverse()),
            ("duplicate_request", lambda value: value["consultations"].append(
                copy.deepcopy(value["consultations"][0])
            )),
        ])
        for label, mutate in mutations:
            receipt = baseline()
            mutate(receipt)
            with self.subTest(label=label):
                self.assertTrue(self.plane._sealed_receipt_shape_issues(node_id, receipt))

    def test_only_exact_old_new_pair_resolves_and_extra_receipt_fails_closed(self) -> None:
        node_id = "ORCH-300"
        record = copy.deepcopy(self._record(node_id))
        old_receipt = {"node_id": node_id, "pr": None}
        record["old_receipt_payload_digest"] = autopilot.digest_json(old_receipt)
        self.plane._repair_records = lambda: {node_id: record}  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        old = {"commit": record["old_receipt_commit"], "receipt": old_receipt}
        new = {"commit": "f" * 40, "receipt": {"pr": 131}}
        records = [old, new]
        self.assertEqual(self.plane.resolve_sealed_repair_records(node_id, records), [new])
        extra = [old, new, {"commit": "a" * 40}]
        self.assertIs(self.plane.resolve_sealed_repair_records(node_id, extra), extra)
        wrong_old = copy.deepcopy(old)
        wrong_old["receipt"]["pr"] = 131
        wrong_pair = [wrong_old, new]
        self.assertIs(self.plane.resolve_sealed_repair_records(node_id, wrong_pair), wrong_pair)

    def test_integrated_exact_old_new_durable_pair_projects_complete_without_validator_stub(self) -> None:
        node_id = "OPTIMIZER-370"
        record = copy.deepcopy(self._record(node_id))
        old_receipt = {"node_id": node_id, "pr": record["expected_old_pr"]}
        record["old_receipt_payload_digest"] = autopilot.digest_json(old_receipt)
        replacement = self._receipt(node_id)
        replacement["authority"]["repair_authority_digest"] = autopilot.digest_json(record)
        durable_records = {
            node_id: [
                {"commit": record["old_receipt_commit"], "parents": (record["candidate_commit"],), "tree": record["old_receipt_tree"], "receipt": old_receipt},
                {"commit": "f" * 40, "parents": (replacement["final_commit"],), "tree": replacement["final_tree"], "receipt": replacement},
            ]
        }
        self.plane._repair_records = lambda: {node_id: record}  # type: ignore[method-assign]
        self.plane.sealed_recovery_issues = lambda: ()  # type: ignore[method-assign]
        with mock.patch.object(DurableControlPlane, "_durable_receipt_records", return_value=durable_records):
            view = self.plane.node_view(node_id)
        self.assertEqual(view.state, "COMPLETE", view.reasons)

    def test_live_cfe_not_g_optimizer_receipt_exact_topology_and_negatives(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        plane = autopilot.ControlPlane(repository)
        receipt = json.loads(
            (repository / ".autopilot" / "optimizer-370-intended-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotEqual(receipt["base_commit"], receipt["authority"]["execution_target_sha"])
        self.assertEqual(
            plane._diff_paths(
                receipt["authority"]["execution_target_sha"], receipt["final_commit"]
            ),
            tuple(receipt["changed_paths"]),
        )
        self.assertEqual(plane._replacement_receipt_issues("OPTIMIZER-370", receipt), ())

        mutations = {
            "one_path_omission": lambda value: value.__setitem__(
                "changed_paths", value["changed_paths"][:1]
            ),
            "g_as_base": lambda value: value.update({
                "base_commit": value["authority"]["execution_target_sha"],
                "base_tree": "2a5b94489c368c0e3798c2d38d85f7631adb8604",
            }),
            "incident_wide_paths": lambda value: value.__setitem__(
                "changed_paths", list(plane._diff_paths(value["base_commit"], value["final_commit"]))
            ),
            "wrong_candidate": lambda value: value.__setitem__(
                "final_commit", value["authority"]["execution_merge_commit"]
            ),
            "wrong_grant": lambda value: value["authority"].__setitem__("grant_id", "other"),
        }
        for label, mutate in mutations.items():
            changed = copy.deepcopy(receipt)
            mutate(changed)
            with self.subTest(label=label):
                self.assertTrue(plane._replacement_receipt_issues("OPTIMIZER-370", changed))

        plane.control["verify_git_objects"] = False
        self.assertIn(
            "Git object verification",
            "; ".join(plane._replacement_receipt_issues("OPTIMIZER-370", receipt)),
        )

    def test_real_bare_live_cfe_not_g_prearmed_h_crash_receipt_and_integration(self) -> None:
        source = Path(__file__).resolve().parents[2]
        remote = self.root / "optimizer-live-post-h.git"
        repository = self.root / "optimizer-live-post-h"
        integrated_repository = self.root / "optimizer-live-integrated"
        g = "9ea57b8ee1bb630b4fe3a8350e1629c4fb4a4379"
        claim_commit = "8fa51243327ae928e46df180bfd81fbf90062cf5"
        execution_merge = "88f2962b64f7cc9f88284c5dd30106de5313da7b"
        candidate = "948368b77ba8de920369f416970e83b909bd50ba"
        main = "8bcecb7f6a182f86d30f9b9696c9720b6e06a0c8"
        capability_commit = sealed_recovery.OPTIMIZER_COMPLETION_CAPABILITY_COMMIT
        checkout = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=source, text=True,
            capture_output=True, check=True,
        ).stdout.strip()
        checkout_parents = subprocess.run(
            ("git", "show", "-s", "--format=%P", checkout), cwd=source,
            text=True, capture_output=True, check=True,
        ).stdout.strip().split()
        candidates = [checkout, *checkout_parents]
        h_matches = []
        for candidate_head in candidates:
            parents = subprocess.run(
                ("git", "show", "-s", "--format=%P", candidate_head), cwd=source,
                text=True, capture_output=True, check=True,
            ).stdout.strip().split()
            if parents == [capability_commit]:
                h_matches.append(candidate_head)
        self.assertEqual(len(set(h_matches)), 1, h_matches)
        h = h_matches[0]
        self.assertEqual(
            subprocess.run(
                ("git", "rev-parse", f"{h}^"), cwd=source, text=True,
                capture_output=True, check=True,
            ).stdout.strip(),
            capability_commit,
        )

        def run(*args: str, cwd: Path = repository) -> str:
            completed = subprocess.run(
                args, cwd=cwd, text=True, capture_output=True, check=False
            )
            if completed.returncode != 0:
                self.fail(f"{' '.join(args)} failed: {completed.stderr}")
            return completed.stdout.strip()

        subprocess.run(("git", "init", "--bare", str(remote)), check=True, capture_output=True)
        run(
            "git", "push", str(remote),
            f"{g}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
            f"{candidate}:refs/heads/autopilot/optimizer-370",
            f"{main}:refs/heads/main", f"{h}:refs/heads/overlay-h", cwd=source,
        )
        run("git", "clone", str(remote), str(repository), cwd=self.root)
        run("git", "config", "user.name", "Optimizer Live Fixture")
        run("git", "config", "user.email", "optimizer-live@example.invalid")
        run("git", "checkout", "-B", "autopilot/optimizer-370", candidate)
        shutil.rmtree(repository / ".autopilot")
        copy_autopilot_fixture(source / ".autopilot", repository / ".autopilot")
        plane = autopilot.ControlPlane(
            repository,
            clock=lambda: sealed_recovery.parse_time("2026-08-11T20:00:00Z"),
        )
        record = plane._repair_record("OPTIMIZER-370")
        receipt = json.loads(
            (repository / ".autopilot/optimizer-370-intended-receipt.json").read_text()
        )
        message = plane._repair_claim_message(claim_commit)
        assert isinstance(message, dict)
        claim = {
            "schema_version": 1,
            "kind": sealed_recovery.REPAIR_CLAIM_KIND,
            "node_id": "OPTIMIZER-370",
            "owner": "codex:optimizer-370-repair",
            "status": "CLAIMED",
            "claimed_at": "2026-08-11T18:13:07.231123Z",
            "heartbeat_at": "2026-08-11T18:13:07.231123Z",
            "expires_at": message["expires_at"],
            "plan_fingerprint": message["plan_fingerprint"],
            "remote": "origin",
            "remote_claim_commit": claim_commit,
            "execution_merge_commit": execution_merge,
            "remote_head_commit": execution_merge,
            "target_sha": g,
            "branch": "autopilot/optimizer-370",
            "old_receipt_commit": record["old_receipt_commit"],
            "repair_id": record["repair_id"],
            "grant_id": record["grant_id"],
            "authority_digest": autopilot.digest_json(record),
            "release_id": message["release_id"],
            "github_snapshot_digest": message["github_snapshot_digest"],
            "reconciliation_digest": message["reconciliation_digest"],
            "doctor_evidence_digest": message["doctor_evidence_digest"],
        }
        autopilot.atomic_write_json(plane.claim_path("OPTIMIZER-370"), claim)
        target_release = {
            "target_sha": h,
            "release_id": "sha256:" + "1" * 64,
            "github_snapshot_digest": "sha256:" + "2" * 64,
            "reconciliation_digest": "sha256:" + "3" * 64,
            "doctor_evidence_digest": "sha256:" + "4" * 64,
        }

        def configure(value) -> None:
            value._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
            value.github_snapshot = lambda: {  # type: ignore[method-assign]
                "target_sha": value.current_target_sha(),
                "pull_requests": [{
                    "node_id": "OPTIMIZER-370", "number": 135, "state": "open",
                    "merged": False, "ci": "success", "base": value.target_branch,
                    "head": "autopilot/optimizer-370", "head_sha": candidate,
                    "draft": True,
                }],
            }
            value.current_release = lambda: dict(target_release)  # type: ignore[method-assign]
            value._release_issues = lambda _release: ()  # type: ignore[method-assign]
            value._doctor_evidence_digest = lambda: target_release["doctor_evidence_digest"]  # type: ignore[method-assign]
            value.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "fixture"}  # type: ignore[method-assign]
            value.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

        configure(plane)
        armed = plane.arm_optimizer_completion_continuation(
            "codex:optimizer-370-repair", h
        )
        self.assertEqual(armed["target_sha"], h)
        self.assertEqual(armed["status"], "ARMED")

        h_tree = run("git", "rev-parse", f"{h}^{{tree}}")
        wrong_h = run(
            "git", "commit-tree", h_tree, "-p", capability_commit,
            "-m", "wrong sibling H",
        )
        run(
            "git", "push", "--force", "origin",
            f"{wrong_h}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
        )
        run("git", "fetch", "origin", "release/hive-mind-os-singleton-20260810-r2")
        with self.assertRaisesRegex(autopilot.ClaimError, "pin current H exactly"):
            plane.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt)
        run(
            "git", "push", "--force", "origin",
            f"{g}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
        )
        run("git", "fetch", "origin", "release/hive-mind-os-singleton-20260810-r2")
        run(
            "git", "push", "origin",
            f"{h}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
        )
        run("git", "fetch", "origin", "release/hive-mind-os-singleton-20260810-r2")

        original_write = sealed_recovery.atomic_write_json

        def crash_after_remote_receipt(path, value):
            if path == plane.receipt_path("OPTIMIZER-370"):
                raise SystemExit("restart after exact remote receipt CAS")
            return original_write(path, value)

        try:
            sealed_recovery.atomic_write_json = crash_after_remote_receipt
            with self.assertRaises(SystemExit):
                plane.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt)
        finally:
            sealed_recovery.atomic_write_json = original_write
        receipt_commit = plane.remote_branch_sha("autopilot/optimizer-370")
        assert isinstance(receipt_commit, str)
        restarted = autopilot.ControlPlane(
            repository,
            clock=lambda: sealed_recovery.parse_time("2026-08-11T20:05:00Z"),
        )
        configure(restarted)
        self.assertEqual(
            restarted.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt),
            receipt_commit,
        )
        with self.assertRaisesRegex(autopilot.ClaimError, "binding differs"):
            restarted.complete("OPTIMIZER-370", "codex:unrelated", receipt)
        run(
            "git", "push", "--force", "origin",
            f"{candidate}:refs/heads/autopilot/optimizer-370",
        )
        with self.assertRaisesRegex(autopilot.ClaimError, "binding differs"):
            restarted.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt)
        run(
            "git", "push", "--force", "origin",
            f"{receipt_commit}:refs/heads/autopilot/optimizer-370",
        )
        index_path = restarted.state_dir / "receipt-index.jsonl"
        exact_index = index_path.read_text(encoding="utf-8")
        with index_path.open("a", encoding="utf-8") as stream:
            stream.write(exact_index)
        with self.assertRaisesRegex(autopilot.ClaimError, "evidence differs"):
            restarted.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt)
        index_path.write_text(exact_index, encoding="utf-8")
        self.assertEqual(
            restarted.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt),
            receipt_commit,
        )

        merge_tree = run("git", "merge-tree", "--write-tree", h, receipt_commit)
        integration = run(
            "git", "commit-tree", merge_tree, "-p", h, "-p", receipt_commit,
            "-m", "integrate exact Optimizer receipt after H",
        )
        run(
            "git", "push", "origin",
            f"{integration}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
        )
        run("git", "fetch", "origin", "release/hive-mind-os-singleton-20260810-r2")
        self.assertEqual(
            restarted.complete("OPTIMIZER-370", "codex:optimizer-370-repair", receipt),
            receipt_commit,
        )
        run(
            "git", "clone", "--branch",
            "release/hive-mind-os-singleton-20260810-r2",
            str(remote), str(integrated_repository), cwd=self.root,
        )
        source_authority = source / ".autopilot/optimizer-370-completion-overlay-authority.json"
        integrated_authority = (
            integrated_repository
            / ".autopilot/optimizer-370-completion-overlay-authority.json"
        )
        if integrated_authority.read_bytes() != source_authority.read_bytes():
            # Before the final reseal commit exists, exercise the prospective H
            # control-plane bytes.  On the sealed H path this branch is not taken.
            shutil.rmtree(integrated_repository / ".autopilot")
            copy_autopilot_fixture(source / ".autopilot", integrated_repository / ".autopilot")
        integrated = autopilot.ControlPlane(integrated_repository)
        durable_records = integrated._durable_receipt_records().get("OPTIMIZER-370", [])
        self.assertEqual(len(durable_records), 1, durable_records)
        self.assertEqual(durable_records[0]["receipt"], receipt)
        view = integrated.node_view("OPTIMIZER-370")
        self.assertEqual(view.state, "COMPLETE", view.reasons)

    def test_real_bare_optimizer_claim_restart_receipt_and_integrated_complete(self) -> None:
        repository = self.root / "sealed-real-flow"
        remote = self.root / "sealed-real-flow.git"
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], repository / ".autopilot")

        def run(*args: str, check: bool = True) -> str:
            completed = subprocess.run(
                args, cwd=repository, text=True, capture_output=True, check=False
            )
            if check and completed.returncode != 0:
                self.fail(f"{' '.join(args)} failed: {completed.stderr}")
            return completed.stdout.strip()

        subprocess.run(("git", "init", "--bare", str(remote)), check=True, capture_output=True)
        run("git", "init")
        run("git", "config", "user.name", "Sealed Flow Fixture")
        run("git", "config", "user.email", "sealed-flow@example.invalid")
        run("git", "remote", "add", "origin", str(remote))
        record = copy.deepcopy(self._record("OPTIMIZER-370"))
        other_record = copy.deepcopy(self._record("ORCH-300"))
        for relative in record["allowed_paths"]:
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("baseline\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-m", "synthetic current release")
        target = run("git", "rev-parse", "HEAD")
        target_tree = run("git", "rev-parse", f"{target}^{{tree}}")
        run("git", "branch", "release/hive-mind-os-singleton-20260810-r2", target)

        original_claim_payload = {
            "kind": "hive-mind-autopilot-remote-claim-v1",
            "node_id": "OPTIMIZER-370",
            "target_sha": target,
            "branch": record["branch"],
            "plan_fingerprint": record["plan_fingerprint"],
        }
        original_claim = run(
            "git", "commit-tree", target_tree, "-p", target,
            "-m", json.dumps(original_claim_payload, sort_keys=True, separators=(",", ":")),
        )
        run("git", "checkout", "-B", "synthetic-candidate", original_claim)
        for index, relative in enumerate(record["allowed_paths"], start=1):
            (repository / relative).write_text(f"rejected candidate {index}\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-m", "synthetic rejected candidate")
        candidate = run("git", "rev-parse", "HEAD")
        candidate_tree = run("git", "rev-parse", f"{candidate}^{{tree}}")
        old_receipt_payload = {
            "node_id": "OPTIMIZER-370", "branch": record["branch"],
            "plan_fingerprint": record["plan_fingerprint"], "contract_version": 1,
            "base_commit": target, "final_commit": candidate, "final_tree": candidate_tree,
            "pr": record["expected_old_pr"],
        }
        old_receipt = run(
            "git", "commit-tree", candidate_tree, "-p", candidate, "-m",
            "HIVE-MIND-AUTOPILOT-COMPLETION-V1\n" + json.dumps(
                old_receipt_payload, sort_keys=True, separators=(",", ":")
            ),
        )
        run("git", "branch", "-f", record["branch"], old_receipt)
        run(
            "git", "push", "origin",
            f"{target}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
            f"{old_receipt}:refs/heads/{record['branch']}",
        )
        record.update({
            "incident_target_sha": target,
            "original_claim_commit": original_claim,
            "candidate_commit": candidate,
            "candidate_tree": candidate_tree,
            "old_receipt_commit": old_receipt,
            "old_receipt_tree": candidate_tree,
            "old_receipt_payload_digest": autopilot.digest_json(old_receipt_payload),
        })

        def configure(plane) -> None:
            plane._repair_records = lambda: {  # type: ignore[method-assign]
                "OPTIMIZER-370": record, "ORCH-300": other_record,
            }
            plane.sealed_recovery_issues = lambda: ()  # type: ignore[method-assign]
            plane._repair_live_issues = lambda _record: ()  # type: ignore[method-assign]
            plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
            plane._live_release_issues = lambda _record, _expected=None: ()  # type: ignore[method-assign]
            plane.assert_start_now = lambda _node: {"release_id": "sealed-real-release"}  # type: ignore[method-assign]
            plane.current_release = lambda: {  # type: ignore[method-assign]
                "release_id": "sealed-real-release", "target_sha": target,
            }
            plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
            plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
            plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
            plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
            # This legacy synthetic flow predates the immutable live Optimizer tuple.
            plane._exact_optimizer_completion_issues = lambda _receipt: ()  # type: ignore[method-assign]

        plane = autopilot.ControlPlane(repository)
        configure(plane)
        claim = plane.claim("OPTIMIZER-370", "test:real-flow", publish_remote=True)
        execution_merge = str(claim["execution_merge_commit"])
        self.assertEqual(plane.remote_branch_sha(record["branch"]), execution_merge)
        run("git", "checkout", "-B", record["branch"], execution_merge)
        for index, relative in enumerate(record["allowed_paths"], start=1):
            (repository / relative).write_text(f"repaired candidate {index}\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-m", "synthetic repaired candidate")
        final = run("git", "rev-parse", "HEAD")
        final_tree = run("git", "rev-parse", f"{final}^{{tree}}")
        run("git", "push", "origin", f"{final}:refs/heads/{record['branch']}")
        receipt = self._receipt("OPTIMIZER-370")
        receipt.update({
            "base_commit": target, "base_tree": target_tree,
            "final_commit": final, "final_tree": final_tree,
            "changed_paths": sorted(record["allowed_paths"]),
        })
        receipt["authority"].update({
            "supersedes_receipt_commit": old_receipt,
            "repair_authority_digest": autopilot.digest_json(record),
            "repair_claim_commit": claim["remote_claim_commit"],
            "execution_merge_commit": execution_merge,
            "execution_target_sha": target,
            "repair_claim_payload_digest": autopilot.digest_json(
                plane._repair_claim_message(str(claim["remote_claim_commit"]))
            ),
        })
        original_write = sealed_recovery.atomic_write_json

        def crash_after_receipt_cas(path, value):
            if path == plane.receipt_path("OPTIMIZER-370"):
                raise SystemExit("synthetic hard restart")
            return original_write(path, value)

        try:
            sealed_recovery.atomic_write_json = crash_after_receipt_cas
            with self.assertRaises(SystemExit):
                plane.complete("OPTIMIZER-370", "test:real-flow", receipt)
        finally:
            sealed_recovery.atomic_write_json = original_write
        published_receipt = plane.remote_branch_sha(record["branch"])
        self.assertNotEqual(published_receipt, final)
        restarted = autopilot.ControlPlane(repository)
        configure(restarted)
        self.assertEqual(
            restarted.complete("OPTIMIZER-370", "test:real-flow", receipt),
            published_receipt,
        )
        run(
            "git", "push", "origin",
            f"{published_receipt}:refs/heads/release/hive-mind-os-singleton-20260810-r2",
        )
        run("git", "fetch", "origin", "release/hive-mind-os-singleton-20260810-r2")
        integrated = autopilot.ControlPlane(repository)
        configure(integrated)
        integrated.current_release = lambda: {  # type: ignore[method-assign]
            "release_id": "integrated", "target_sha": published_receipt,
        }
        view = integrated.node_view("OPTIMIZER-370")
        self.assertEqual(view.state, "COMPLETE", view.reasons)

    def test_orch_exact_inherited_claim_provenance_can_validate_integrated_successor(self) -> None:
        node_id = "ORCH-300"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        receipt["authority"]["grant_id"] = record["grant_id"]
        original = record["original_claim_commit"]
        final = receipt["final_commit"]
        durable = {
            "commit": "f" * 40,
            "parents": (final,),
            "tree": receipt["final_tree"],
            "receipt": receipt,
        }
        self.plane.validate_receipt = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane._has_git_repository = lambda: True  # type: ignore[method-assign]
        self.plane.git_object_exists = lambda _sha: True  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "9" * 40  # type: ignore[method-assign]
        self.plane.is_ancestor = lambda ancestor, descendant: (  # type: ignore[method-assign]
            (ancestor, descendant) in {(final, "f" * 40), ("f" * 40, "9" * 40), (original, final)}
        )
        self.plane._commit_tree = lambda sha: (  # type: ignore[method-assign]
            record["claim_target_tree"] if sha == original else receipt["final_tree"]
        )
        self.plane._commit_parents = lambda sha: (  # type: ignore[method-assign]
            (record["claim_target_sha"],) if sha == original else (final,)
        )
        original_payload = {
            "kind": "hive-mind-autopilot-remote-claim-v1",
            "node_id": node_id,
            "target_sha": record["claim_target_sha"],
            "branch": record["branch"],
            "plan_fingerprint": record["plan_fingerprint"],
        }
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(  # type: ignore[method-assign]
            args, 0, json.dumps(original_payload), ""
        )
        self.assertEqual(self.plane._validate_receipt_commit_record(node_id, durable), ())

    def test_receipt_publication_uses_final_head_cas_and_keeps_claim_until_verified(self) -> None:
        node_id = "OPTIMIZER-370"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        final = receipt["final_commit"]
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND,
            "owner": "test:owner",
            "status": "CLAIMED",
            "expires_at": "2030-01-01T00:00:00Z",
            "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        state = {"head": final}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "lease"}  # type: ignore[method-assign]
        self.plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        self.plane._create_receipt_commit = lambda *_args: "f" * 40  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", "")  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        committed = self.plane.complete(node_id, "test:owner", receipt)
        self.assertEqual(committed, "f" * 40)
        self.assertEqual(state["head"], committed)
        self.assertFalse(self.plane.claim_path(node_id).exists())
        self.assertTrue(self.plane.receipt_path(node_id).is_file())

    def test_prepared_intent_with_claimed_claim_recovers_before_active_rejection(self) -> None:
        node_id = "OPTIMIZER-370"
        owner = "test:prepared-cut"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND,
            "node_id": node_id,
            "owner": owner,
            "status": "CLAIMED",
            "expires_at": "2030-01-01T00:00:00Z",
            "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        claim_path = self.plane.claim_path(node_id)
        autopilot.atomic_write_json(claim_path, claim)
        intent_path = self.plane.state_dir / "sealed-repair-completion-optimizer-370.json"
        autopilot.atomic_write_json(intent_path, {
            "schema_version": 1,
            "kind": "hive-mind-autopilot-sealed-repair-completion-v1",
            "status": "PREPARED",
            "node_id": node_id,
            "owner": owner,
            "target_sha": claim["target_sha"],
            "remote_expected_final": receipt["final_commit"],
            "receipt_digest": autopilot.digest_json(receipt),
            "receipt_commit": None,
            "active_claim_digest": autopilot.digest_json(claim),
            "prepared_at": "2026-08-11T20:00:00Z",
        })
        self.plane.remote_branch_sha = lambda _branch: receipt["final_commit"]  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(  # type: ignore[method-assign]
            args, 0, receipt["final_commit"] + "\n", ""
        )
        self.assertIsNone(
            self.plane._recover_interrupted_repair_completion(
                node_id, owner, receipt, claim, record
            )
        )
        self.assertEqual(json.loads(claim_path.read_text())["status"], "CLAIMED")
        self.assertFalse(intent_path.exists())

    def test_consumed_cut_finishes_cleanup_after_expiry_and_h_advance(self) -> None:
        record, receipt, receipt_commit, intent_path = self._install_terminal_optimizer_cut(
            claim_present=True
        )
        self.plane.clock = lambda: autopilot.parse_time("2031-01-01T00:00:00Z")  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "a" * 40  # type: ignore[method-assign]
        claim = json.loads(self.plane.claim_path("OPTIMIZER-370").read_text())
        self.assertEqual(
            self.plane._recover_interrupted_repair_completion(
                "OPTIMIZER-370", "test:continuation", receipt, claim, record
            ),
            receipt_commit,
        )
        self.assertFalse(self.plane.claim_path("OPTIMIZER-370").exists())
        self.assertFalse(intent_path.exists())
        self.assertEqual(
            json.loads(self.plane.optimizer_continuation_path.read_text())["status"],
            "CONSUMED",
        )

    def test_terminal_missing_claim_reconciles_consumed_continuation(self) -> None:
        _record, receipt, receipt_commit, intent_path = self._install_terminal_optimizer_cut(
            claim_present=False
        )
        self.plane.clock = lambda: autopilot.parse_time("2031-01-01T00:00:00Z")  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "a" * 40  # type: ignore[method-assign]
        self.assertEqual(
            self.plane.complete("OPTIMIZER-370", "test:continuation", receipt),
            receipt_commit,
        )
        self.assertFalse(intent_path.exists())

    def test_durable_continuation_transition_marker_recovers_after_process_death(self) -> None:
        path = self.plane.optimizer_continuation_path
        current = {
            "kind": sealed_recovery.OPTIMIZER_CONTINUATION_KIND,
            "status": "ACTIVE",
            "target_sha": "9" * 40,
        }
        autopilot.atomic_write_json(path, current)
        marker = path.with_suffix(path.suffix + ".transition")
        autopilot.atomic_write_json(marker, {
            "schema_version": 1,
            "kind": sealed_recovery.OPTIMIZER_CONTINUATION_KIND + "-transition",
            "expected_status": "ACTIVE",
            "next_status": "CONSUMING",
            "expected_digest": autopilot.digest_json(current),
            "receipt_commit": None,
            "bindings": None,
        })
        transitioned = self.plane._transition_optimizer_continuation(
            "ACTIVE", "CONSUMING"
        )
        self.assertEqual(transitioned["status"], "CONSUMING")
        self.assertFalse(marker.exists())
        self.assertEqual(
            self.plane._transition_optimizer_continuation("ACTIVE", "CONSUMING")["status"],
            "CONSUMING",
        )
        autopilot.atomic_write_json(marker, {
            "schema_version": 1,
            "kind": sealed_recovery.OPTIMIZER_CONTINUATION_KIND + "-transition",
            "expected_status": "ACTIVE",
            "next_status": "CONSUMING",
            "expected_digest": transitioned["previous_digest"],
            "receipt_commit": None,
            "bindings": None,
        })
        consumed = self.plane._transition_optimizer_continuation(
            "CONSUMING", "CONSUMED", receipt_commit="f" * 40
        )
        self.assertEqual(consumed["status"], "CONSUMED")
        self.assertFalse(marker.exists())

    def test_post_consumed_claim_and_intent_unlink_failures_never_compensate(self) -> None:
        for cut in ("claim", "intent"):
            with self.subTest(cut=cut):
                repository = self.root / f"post-consumed-{cut}"
                copy_autopilot_fixture(
                    Path(__file__).resolve().parents[1], repository / ".autopilot"
                )
                control_path = repository / ".autopilot/control-plane.json"
                control = json.loads(control_path.read_text())
                control["verify_git_objects"] = False
                control_path.write_text(json.dumps(control))
                plane = autopilot.ControlPlane(repository)
                node_id = "OPTIMIZER-370"
                owner = "test:consumed-cut"
                record = plane._repair_record(node_id)
                receipt = self._receipt(node_id)
                claim = {
                    "kind": sealed_recovery.REPAIR_CLAIM_KIND,
                    "node_id": node_id, "owner": owner, "status": "CLAIMED",
                    "expires_at": "2030-01-01T00:00:00Z",
                    "authority_digest": autopilot.digest_json(record),
                    "target_sha": "d" * 40, "grant_id": record["grant_id"],
                }
                claim_path = plane.claim_path(node_id)
                autopilot.atomic_write_json(claim_path, claim)
                continuation = {
                    "kind": sealed_recovery.OPTIMIZER_CONTINUATION_KIND,
                    "status": "ACTIVE", "node_id": node_id, "owner": owner,
                    "target_sha": "9" * 40, "grant_id": record["grant_id"],
                    "claim_digest": autopilot.digest_json(claim),
                    "receipt_digest": autopilot.digest_json(receipt),
                }
                autopilot.atomic_write_json(plane.optimizer_continuation_path, continuation)
                state = {"remote": receipt["final_commit"], "local": receipt["final_commit"]}
                plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
                plane.remote_branch_sha = lambda _branch: state["remote"]  # type: ignore[method-assign]
                plane._arm_optimizer_continuation = lambda *_args: json.loads(plane.optimizer_continuation_path.read_text())  # type: ignore[method-assign]
                plane._optimizer_continuation_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
                plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
                plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "fixture"}  # type: ignore[method-assign]
                plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
                plane._create_receipt_commit = lambda *_args: "f" * 40  # type: ignore[method-assign]
                plane._commit_parents = lambda _sha: (receipt["final_commit"],)  # type: ignore[method-assign]
                plane._commit_tree = lambda _sha: receipt["final_tree"]  # type: ignore[method-assign]

                def cas(_branch: str, expected: str, new: str) -> None:
                    self.assertEqual(state["remote"], expected)
                    state["remote"] = new

                plane._cas_update_branch = cas  # type: ignore[method-assign]
                plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(  # type: ignore[method-assign]
                    args, 0,
                    plane._receipt_message(receipt)
                    if tuple(args[:3]) == ("show", "-s", "--format=%B")
                    else state["local"] + "\n",
                    "",
                )
                intent_path = plane.state_dir / "sealed-repair-completion-optimizer-370.json"
                original_unlink = Path.unlink
                failed = False

                def fail_terminal_unlink(path: Path, *args, **kwargs):
                    nonlocal failed
                    target = claim_path if cut == "claim" else intent_path
                    if path == target and not failed:
                        failed = True
                        raise OSError(f"process death at {cut} unlink")
                    return original_unlink(path, *args, **kwargs)

                with mock.patch.object(Path, "unlink", fail_terminal_unlink):
                    with self.assertRaises(OSError):
                        plane.complete(node_id, owner, receipt)
                self.assertEqual(state["remote"], "f" * 40)
                self.assertTrue(plane.receipt_path(node_id).is_file())
                self.assertTrue(plane._receipt_index_contains(node_id, "f" * 40))
                self.assertEqual(
                    json.loads(plane.optimizer_continuation_path.read_text())["status"],
                    "CONSUMED",
                )
                self.assertEqual(plane.complete(node_id, owner, receipt), "f" * 40)

    def test_receipt_cas_failure_restores_claimed_state_without_completion_evidence(self) -> None:
        node_id = "OPTIMIZER-370"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        final = receipt["final_commit"]
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND, "owner": "test:owner",
            "status": "CLAIMED",
            "expires_at": "2030-01-01T00:00:00Z", "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        state = {"remote": final, "local": final, "cas_attempts": 0}
        self.plane.remote_branch_sha = lambda _branch: state["remote"]  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "lease"}  # type: ignore[method-assign]
        self.plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        def create_receipt(*_args):
            state["local"] = "f" * 40
            return state["local"]

        self.plane._create_receipt_commit = create_receipt  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            state["cas_attempts"] += 1
            if state["cas_attempts"] == 1:
                raise autopilot.ClaimError("CAS rejected")
            self.assertEqual(state["remote"], expected)
            state["remote"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]

        def git(args, **_kwargs):
            command = tuple(args)
            if command[0] == "update-ref":
                self.assertEqual(state["local"], command[3])
                state["local"] = command[2]
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:2] == ("rev-parse", "--verify"):
                return subprocess.CompletedProcess(command, 0, state["local"] + "\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        self.plane._git = git  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "CAS rejected"):
            self.plane.complete(node_id, "test:owner", receipt)
        retained = json.loads(self.plane.claim_path(node_id).read_text(encoding="utf-8"))
        self.assertEqual(retained["status"], "CLAIMED")
        self.assertFalse(self.plane.receipt_path(node_id).exists())
        self.assertFalse((self.plane.state_dir / "sealed-repair-completion-optimizer-370.json").exists())
        self.assertEqual(state["local"], final)
        self.assertEqual(self.plane.complete(node_id, "test:owner", receipt), "f" * 40)
        self.assertEqual(state["remote"], "f" * 40)

    def test_restart_after_local_receipt_creation_rolls_back_and_retries(self) -> None:
        node_id = "OPTIMIZER-370"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        final = receipt["final_commit"]
        receipt_commit = "f" * 40
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND, "owner": "test:owner", "status": "CLAIMED",
            "expires_at": "2030-01-01T00:00:00Z", "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        state = {"remote": final, "local": final}
        self.plane.remote_branch_sha = lambda _branch: state["remote"]  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "lease"}  # type: ignore[method-assign]
        self.plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

        def create_receipt(*_args):
            state["local"] = receipt_commit
            return receipt_commit

        self.plane._create_receipt_commit = create_receipt  # type: ignore[method-assign]
        self.plane._commit_parents = lambda _sha: (final,)  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: receipt["final_tree"]  # type: ignore[method-assign]

        def git(args, **_kwargs):
            command = tuple(args)
            if command[:2] == ("rev-parse", "--verify"):
                return subprocess.CompletedProcess(command, 0, state["local"] + "\n", "")
            if command[0] == "update-ref":
                self.assertEqual(state["local"], command[3])
                state["local"] = command[2]
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ("show", "-s", "--format=%B"):
                return subprocess.CompletedProcess(command, 0, self.plane._receipt_message(receipt), "")
            return subprocess.CompletedProcess(command, 0, "", "")

        self.plane._git = git  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["remote"], expected)
            state["remote"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        original_write = sealed_recovery.atomic_write_json
        intent_writes = 0

        def crash_before_receipt_identity(path, value):
            nonlocal intent_writes
            if path.name == "sealed-repair-completion-optimizer-370.json":
                intent_writes += 1
                if intent_writes == 2:
                    raise SystemExit("crash after local receipt creation")
            return original_write(path, value)

        try:
            sealed_recovery.atomic_write_json = crash_before_receipt_identity
            with self.assertRaises(SystemExit):
                self.plane.complete(node_id, "test:owner", receipt)
        finally:
            sealed_recovery.atomic_write_json = original_write
        self.assertEqual(state, {"remote": final, "local": receipt_commit})
        self.assertEqual(self.plane.complete(node_id, "test:owner", receipt), receipt_commit)
        self.assertEqual(state, {"remote": receipt_commit, "local": receipt_commit})

    def test_hard_restart_after_receipt_remote_cas_resumes_local_evidence_cleanup(self) -> None:
        node_id = "OPTIMIZER-370"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        final = receipt["final_commit"]
        receipt_commit = "f" * 40
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND, "owner": "test:owner", "status": "CLAIMED",
            "expires_at": "2030-01-01T00:00:00Z", "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        state = {"head": final}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "lease"}  # type: ignore[method-assign]
        self.plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        self.plane._create_receipt_commit = lambda *_args: receipt_commit  # type: ignore[method-assign]
        self.plane._commit_parents = lambda _sha: (final,)  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: receipt["final_tree"]  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(  # type: ignore[method-assign]
            args, 0, self.plane._receipt_message(receipt) if args[:3] == ("show", "-s", "--format=%B") else "", ""
        )

        def cas(_branch: str, expected: str, new: str) -> None:
            self.assertEqual(state["head"], expected)
            state["head"] = new

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        original_write = sealed_recovery.atomic_write_json

        def crash_after_remote_cas(path, value):
            if path == self.plane.receipt_path(node_id):
                raise SystemExit("simulated process death")
            return original_write(path, value)

        try:
            sealed_recovery.atomic_write_json = crash_after_remote_cas
            with self.assertRaises(SystemExit):
                self.plane.complete(node_id, "test:owner", receipt)
        finally:
            sealed_recovery.atomic_write_json = original_write
        self.assertEqual(state["head"], receipt_commit)
        self.assertTrue(self.plane.claim_path(node_id).is_file())
        self.plane.current_target_sha = lambda: "9" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ("release advanced",)  # type: ignore[method-assign]
        self.plane._live_release_issues = lambda _record, _expected=None: ("literal origin release advanced",)  # type: ignore[method-assign]
        self.plane.clock = lambda: autopilot.parse_time("2031-01-01T00:00:00Z")  # type: ignore[method-assign]
        recovered = self.plane.complete(node_id, "test:owner", receipt)
        self.assertEqual(recovered, receipt_commit)
        self.assertFalse(self.plane.claim_path(node_id).exists())
        self.assertTrue(self.plane.receipt_path(node_id).is_file())
        self.assertTrue(self.plane._receipt_index_contains(node_id, receipt_commit))

    def test_receipt_post_cas_rollback_failure_preserves_adverse_claim_and_intent(self) -> None:
        node_id = "OPTIMIZER-370"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        final = receipt["final_commit"]
        receipt_commit = "f" * 40
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND, "owner": "test:owner", "status": "CLAIMED",
            "expires_at": "2030-01-01T00:00:00Z", "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        state = {"head": final}
        self.plane.remote_branch_sha = lambda _branch: state["head"]  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "lease"}  # type: ignore[method-assign]
        self.plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        self.plane._create_receipt_commit = lambda *_args: receipt_commit  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", "")  # type: ignore[method-assign]

        def cas(_branch: str, expected: str, new: str) -> None:
            if expected == final:
                state["head"] = new
                return
            raise autopilot.ClaimError("receipt rollback rejected")

        self.plane._cas_update_branch = cas  # type: ignore[method-assign]
        original_write = sealed_recovery.atomic_write_json

        def fail_local_receipt(path, value):
            if path == self.plane.receipt_path(node_id):
                raise OSError("disk unavailable")
            return original_write(path, value)

        try:
            sealed_recovery.atomic_write_json = fail_local_receipt
            with self.assertRaises(OSError):
                self.plane.complete(node_id, "test:owner", receipt)
        finally:
            sealed_recovery.atomic_write_json = original_write
        retained = json.loads(self.plane.claim_path(node_id).read_text(encoding="utf-8"))
        self.assertEqual(retained["status"], "ADVERSE")
        self.assertEqual(state["head"], receipt_commit)
        self.assertTrue((self.plane.state_dir / f"sealed-repair-completion-{node_id.lower()}.json").is_file())

    def test_builder_atomic_cas_archive_delete_and_reuse_denial(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        self.plane.github_snapshot = lambda: {  # type: ignore[method-assign]
            "target_sha": "d" * 40,
            "pull_requests": [],
            "branches": [{"name": replan["branch"], "sha": replan["candidate_commit"], "stale": True}],
        }
        self.plane._builder_history_issues = lambda _replan: ()  # type: ignore[method-assign]
        self.plane._builder_release_preflight = lambda: {"release_id": "release", "target_sha": "d" * 40}  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane.is_ancestor = lambda ancestor, descendant: True  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _commit: replan["candidate_tree"]  # type: ignore[method-assign]
        state = {"source": replan["candidate_commit"], "archive": None}
        self.plane._remote_ref_sha = lambda ref: state["source"] if ref.startswith("refs/heads/") else state["archive"]  # type: ignore[method-assign]
        pushes: list[tuple[str, ...]] = []

        def git(args, *, check=False, environment=None):
            command = tuple(args)
            if command[0] == "push":
                pushes.append(command)
                self.assertIn("--atomic", command)
                self.assertIn(
                    f"--force-with-lease=refs/heads/{replan['branch']}:{replan['candidate_commit']}",
                    command,
                )
                self.assertIn(f"--force-with-lease={replan['archive_ref']}:", command)
                state["source"], state["archive"] = None, replan["candidate_commit"]
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "fetch":
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "rev-parse":
                return subprocess.CompletedProcess(command, 0, replan["candidate_commit"] + "\n", "")
            if command[0] == "update-ref":
                return subprocess.CompletedProcess(command, 0, "", "")
            self.fail(f"unexpected command: {command}")

        self.plane._git = git  # type: ignore[method-assign]
        result = self.plane.retire_builder_branch(actor="test:builder-retirement")
        self.assertEqual(result["status"], "RETIRED")
        self.assertEqual(len(pushes), 1)
        with self.assertRaisesRegex(autopilot.ClaimError, "reuse"):
            self.plane.retire_builder_branch(actor="test:reuse")

    def test_builder_post_push_failure_atomically_restores_source_and_removes_archive(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        self.plane._builder_release_preflight = lambda: {"release_id": "release"}  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._builder_history_issues = lambda _replan: ()  # type: ignore[method-assign]
        self.plane.github_snapshot = lambda: {  # type: ignore[method-assign]
            "target_sha": "d" * 40, "pull_requests": [],
            "branches": [{"name": replan["branch"], "sha": replan["candidate_commit"], "stale": True}],
        }
        state = {"source": replan["candidate_commit"], "archive": None}
        self.plane._remote_ref_sha = lambda ref: state["source"] if ref.startswith("refs/heads/") else state["archive"]  # type: ignore[method-assign]
        pushes: list[tuple[str, ...]] = []

        def git(args, **_kwargs):
            command = tuple(args)
            if command[0] == "push":
                pushes.append(command)
                if state["source"] is not None:
                    state["source"], state["archive"] = None, replan["candidate_commit"]
                else:
                    state["source"], state["archive"] = replan["candidate_commit"], None
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "rev-parse":
                return subprocess.CompletedProcess(command, 0, replan["candidate_commit"] + "\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        self.plane._git = git  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: (_ for _ in ()).throw(RuntimeError("post-push verification failed"))  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "post-push"):
            self.plane.retire_builder_branch(actor="test:builder-retirement")
        self.assertEqual(state, {"source": replan["candidate_commit"], "archive": None})
        self.assertEqual(len(pushes), 2)
        compensation = pushes[1]
        self.assertIn(f"--force-with-lease=refs/heads/{replan['branch']}:", compensation)
        self.assertIn(f"--force-with-lease={replan['archive_ref']}:{replan['candidate_commit']}", compensation)
        self.assertFalse(self.plane.builder_execution_path.exists())
        self.assertFalse(self.plane.builder_intent_path.exists())

    def test_builder_prepared_intent_recovers_verified_post_push_state(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane.current_target_sha = lambda: "e" * 40  # type: ignore[method-assign]
        self.plane.current_release = lambda: {"release_id": "new-release"}  # type: ignore[method-assign]
        self.plane._live_release_issues = lambda _record, _expected=None: ("literal origin release advanced",)  # type: ignore[method-assign]
        self.plane._builder_history_issues = lambda _replan: ()  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: replan["candidate_tree"]  # type: ignore[method-assign]
        self.plane._remote_ref_sha = lambda ref: None if ref.startswith("refs/heads/") else replan["candidate_commit"]  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", "")  # type: ignore[method-assign]
        lease = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "recovery_id": "builder-330-stale-candidate-recovery-v1", "node_id": "BUILDER-330", "actor": "test:builder",
            "source_head": replan["candidate_commit"], "archive_ref": replan["archive_ref"],
            "target_sha": "d" * 40, "release_id": "release",
            "expires_at": "2030-01-01T00:00:00Z", "status": "ACTIVE",
        }
        intent = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "status": "PREPARED", "recovery_id": lease["recovery_id"],
            "source_head": replan["candidate_commit"], "archive_ref": replan["archive_ref"],
            "target_sha": "d" * 40, "release_id": "release", "snapshot_digest": "snapshot",
            "reconciliation_digest": "reconciliation", "doctor_evidence_digest": "doctor",
            "actor": "test:builder", "lease_digest": autopilot.digest_json(lease),
            "prepared_at": "2026-08-11T00:00:00Z",
        }
        autopilot.atomic_write_json(self.plane.builder_intent_path, intent)
        autopilot.atomic_write_json(self.plane.builder_lease_path, lease)
        recovered = self.plane._recover_interrupted_builder_retirement(replan)
        assert recovered is not None
        self.assertEqual(recovered["status"], "RETIRED")
        self.assertFalse(self.plane.builder_intent_path.exists())
        self.assertFalse(self.plane.builder_lease_path.exists())

    def test_builder_restart_after_execution_record_finishes_only_intent_cleanup(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        lease = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "recovery_id": "builder-330-stale-candidate-recovery-v1", "node_id": "BUILDER-330",
            "actor": "test:builder", "source_head": replan["candidate_commit"],
            "archive_ref": replan["archive_ref"], "target_sha": "d" * 40,
            "release_id": "release", "expires_at": "2030-01-01T00:00:00Z", "status": "ACTIVE",
        }
        intent = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND, "status": "PREPARED",
            "recovery_id": lease["recovery_id"], "source_head": replan["candidate_commit"],
            "archive_ref": replan["archive_ref"], "target_sha": "d" * 40, "release_id": "release",
            "snapshot_digest": "snapshot", "reconciliation_digest": "reconciliation",
            "doctor_evidence_digest": "doctor", "actor": "test:builder",
            "lease_digest": autopilot.digest_json(lease), "prepared_at": "2026-08-11T00:00:00Z",
        }
        execution = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND, "status": "RETIRED",
            "recovery_id": lease["recovery_id"], "source_head": replan["candidate_commit"],
            "archive_ref": replan["archive_ref"], "snapshot_digest": "snapshot",
            "reconciliation_digest": "reconciliation", "doctor_evidence_digest": "doctor",
            "target_sha": "d" * 40, "release_id": "release", "actor": "test:builder",
            "completed_at": "2026-08-11T00:01:00Z",
        }
        autopilot.atomic_write_json(self.plane.builder_lease_path, lease)
        autopilot.atomic_write_json(self.plane.builder_intent_path, intent)
        autopilot.atomic_write_json(self.plane.builder_execution_path, execution)
        self.plane._remote_ref_sha = lambda ref: (  # type: ignore[method-assign]
            None if ref.startswith("refs/heads/") else replan["candidate_commit"]
        )
        recovered = self.plane.retire_builder_branch(actor="test:restart")
        self.assertEqual(recovered, execution)
        self.assertFalse(self.plane.builder_intent_path.exists())
        self.assertFalse(self.plane.builder_lease_path.exists())

    def test_builder_recovery_snapshot_binds_absent_source_and_exact_archive(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        execution = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND, "status": "RETIRED",
            "recovery_id": "builder-330-stale-candidate-recovery-v1", "source_head": replan["candidate_commit"],
            "archive_ref": replan["archive_ref"], "snapshot_digest": "old-snapshot",
            "reconciliation_digest": "old-reconciliation", "doctor_evidence_digest": "old-doctor",
            "target_sha": "d" * 40, "release_id": "release", "actor": "test:builder",
            "completed_at": "2026-08-11T00:00:00Z",
        }
        recovery = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "recovery_id": execution["recovery_id"], "snapshot_digest": "snapshot",
            "reconciliation_digest": "reconciliation", "doctor_evidence_digest": "doctor",
            "target_sha": "d" * 40, "recorded_at": "2026-08-11T00:01:00Z",
        }
        autopilot.atomic_write_json(self.plane.builder_execution_path, execution)
        autopilot.atomic_write_json(self.plane.builder_recovery_path, recovery)
        self.plane.github_snapshot = lambda: {"branches": [], "refs": []}  # type: ignore[method-assign]
        self.assertIn("archive ref", "; ".join(self.plane._builder_recovery_issues()))
        self.plane.github_snapshot = lambda: {  # type: ignore[method-assign]
            "branches": [], "refs": [{"name": replan["archive_ref"], "sha": replan["candidate_commit"]}],
        }
        self.assertEqual(self.plane._builder_recovery_issues(), ())

    def test_builder_source_archive_pr_and_lease_mismatches_never_push(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane._origin_is_configured_repository = lambda _record: True  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        self.plane._builder_history_issues = lambda _replan: ()  # type: ignore[method-assign]
        self.plane._builder_release_preflight = lambda: {"release_id": "release", "target_sha": "d" * 40}  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane.is_ancestor = lambda *_args: True  # type: ignore[method-assign]
        pushes: list[tuple[str, ...]] = []
        self.plane._git = lambda args, **_kwargs: pushes.append(tuple(args))  # type: ignore[method-assign]
        cases = (
            ({"pull_requests": [], "branches": []}, "source"),
            ({"pull_requests": [{"node_id": "BUILDER-330"}], "branches": [{"name": replan["branch"], "sha": replan["candidate_commit"], "stale": True}]}, "PR"),
            ({"pull_requests": [], "branches": [{"name": str(replan["branch"]).upper(), "sha": replan["candidate_commit"], "stale": True}]}, "snapshot"),
        )
        for snapshot, _label in cases:
            self.plane.github_snapshot = lambda snapshot=snapshot: {"target_sha": "d" * 40, **snapshot}  # type: ignore[method-assign]
            with self.subTest(label=_label), self.assertRaises(autopilot.ClaimError):
                self.plane.retire_builder_branch(actor="test:block")
        self.assertFalse(any(command and command[0] == "push" for command in pushes))

    def test_builder_active_claim_validation_lease_archive_and_foreign_lease_fail_closed(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        self.plane._builder_release_preflight = lambda: {"release_id": "release"}  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._builder_history_issues = lambda _replan: ()  # type: ignore[method-assign]
        self.plane.github_snapshot = lambda: {  # type: ignore[method-assign]
            "target_sha": "d" * 40, "pull_requests": [],
            "branches": [{"name": replan["branch"], "sha": replan["candidate_commit"], "stale": True}],
        }
        self.plane._remote_ref_sha = lambda ref: (  # type: ignore[method-assign]
            replan["candidate_commit"] if ref.startswith("refs/heads/") else None
        )
        claim_path = self.plane.claim_path("BUILDER-330")
        autopilot.atomic_write_json(claim_path, {"owner": "foreign"})
        with self.assertRaisesRegex(autopilot.ClaimError, "active claim"):
            self.plane.retire_builder_branch(actor="test:builder")
        claim_path.unlink()
        autopilot.atomic_write_json(self.plane.validation_lease_path, {"owner": "foreign"})
        with self.assertRaisesRegex(autopilot.ClaimError, "validation lease"):
            self.plane.retire_builder_branch(actor="test:builder")
        self.plane.validation_lease_path.unlink()
        self.plane._remote_ref_sha = lambda ref: replan["candidate_commit"]  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "archive already exists"):
            self.plane.retire_builder_branch(actor="test:builder")
        foreign_lease = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "recovery_id": "foreign", "node_id": "EXPLORER-310", "actor": "foreign",
            "source_head": replan["candidate_commit"], "archive_ref": replan["archive_ref"],
            "target_sha": "d" * 40, "release_id": "foreign",
            "expires_at": "2030-01-01T00:00:00Z", "status": "ACTIVE",
        }
        autopilot.atomic_write_json(self.plane.builder_lease_path, foreign_lease)
        self.plane._remote_ref_sha = lambda ref: (  # type: ignore[method-assign]
            replan["candidate_commit"] if ref.startswith("refs/heads/") else None
        )
        with self.assertRaisesRegex(autopilot.ClaimError, "lease already exists"):
            self.plane.retire_builder_branch(actor="test:builder")


if __name__ == "__main__":
    unittest.main()
