from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
import sealed_recovery  # noqa: E402
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

    def test_receipt_cas_failure_restores_claimed_state_without_completion_evidence(self) -> None:
        node_id = "OPTIMIZER-370"
        record = self._record(node_id)
        receipt = self._receipt(node_id)
        final = receipt["final_commit"]
        claim = {
            "kind": sealed_recovery.REPAIR_CLAIM_KIND, "owner": "test:owner",
            "expires_at": "2030-01-01T00:00:00Z", "authority_digest": autopilot.digest_json(record),
            "target_sha": "d" * 40,
        }
        autopilot.atomic_write_json(self.plane.claim_path(node_id), claim)
        self.plane.remote_branch_sha = lambda _branch: final  # type: ignore[method-assign]
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane._release_binding_issues = lambda _claim=None: ()  # type: ignore[method-assign]
        self.plane._replacement_receipt_issues = lambda *_args, **_kwargs: ()  # type: ignore[method-assign]
        self.plane.acquire_global_validation_lease = lambda *_args, **_kwargs: {"lease_id": "lease"}  # type: ignore[method-assign]
        self.plane.release_global_validation_lease = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        self.plane._create_receipt_commit = lambda *_args: "f" * 40  # type: ignore[method-assign]
        self.plane._cas_update_branch = lambda *_args: (_ for _ in ()).throw(autopilot.ClaimError("CAS rejected"))  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", "")  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "CAS rejected"):
            self.plane.complete(node_id, "test:owner", receipt)
        retained = json.loads(self.plane.claim_path(node_id).read_text(encoding="utf-8"))
        self.assertEqual(retained["status"], "CLAIMED")
        self.assertFalse(self.plane.receipt_path(node_id).exists())

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
        self.assertFalse(self.plane.builder_execution_path.exists())
        self.assertFalse(self.plane.builder_intent_path.exists())

    def test_builder_prepared_intent_recovers_verified_post_push_state(self) -> None:
        replan = self.plane._builder_document(BUILDER_REPLAN_PATH)
        assert isinstance(replan, dict)
        self.plane.current_target_sha = lambda: "d" * 40  # type: ignore[method-assign]
        self.plane.current_release = lambda: {"release_id": "release"}  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "snapshot"  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "reconciliation"  # type: ignore[method-assign]
        self.plane._doctor_evidence_digest = lambda: "doctor"  # type: ignore[method-assign]
        self.plane._builder_history_issues = lambda _replan: ()  # type: ignore[method-assign]
        self.plane._commit_tree = lambda _sha: replan["candidate_tree"]  # type: ignore[method-assign]
        self.plane._remote_ref_sha = lambda ref: None if ref.startswith("refs/heads/") else replan["candidate_commit"]  # type: ignore[method-assign]
        self.plane._git = lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", "")  # type: ignore[method-assign]
        intent = {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "status": "PREPARED", "recovery_id": "builder-330-stale-candidate-recovery-v1",
            "source_head": replan["candidate_commit"], "archive_ref": replan["archive_ref"],
            "target_sha": "d" * 40, "release_id": "release", "snapshot_digest": "snapshot",
            "reconciliation_digest": "reconciliation", "doctor_evidence_digest": "doctor",
            "actor": "test:builder", "lease_digest": "sha256:" + "0" * 64,
            "prepared_at": "2026-08-11T00:00:00Z",
        }
        autopilot.atomic_write_json(self.plane.builder_intent_path, intent)
        autopilot.atomic_write_json(self.plane.builder_lease_path, {
            "schema_version": 1, "kind": sealed_recovery.BUILDER_EXECUTION_KIND,
            "recovery_id": intent["recovery_id"], "node_id": "BUILDER-330", "actor": "test:builder",
            "source_head": replan["candidate_commit"], "archive_ref": replan["archive_ref"],
            "target_sha": "d" * 40, "release_id": "release",
            "expires_at": "2030-01-01T00:00:00Z", "status": "ACTIVE",
        })
        recovered = self.plane._recover_interrupted_builder_retirement(replan)
        assert recovered is not None
        self.assertEqual(recovered["status"], "RETIRED")
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


if __name__ == "__main__":
    unittest.main()
