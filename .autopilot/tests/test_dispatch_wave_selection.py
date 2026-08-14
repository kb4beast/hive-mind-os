"""The CLI's own dispatcher must never write a release its validator rejects.

``autopilot.ControlPlane`` overrides ``dispatch``, so the release-barrier suite
never exercised the wave selection the CLI actually runs. That override chose a
wave on lock-disjointness alone and ignored ``parallel_safe``, which seats a
serial node beside parallel siblings — precisely the pairing
``_release_issues`` rejects. The release was therefore invalid the moment it
was written: ``ready`` stayed empty, no node could ever be claimed, and an
auto-dispatching healer rewrote the same invalid wave on every pass.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


autopilot = _load("dispatch_autopilot", "autopilot.py")
github_snapshot = _load("dispatch_github_snapshot", "github_snapshot.py")
controller = sys.modules["controller"]

SERIAL = "MIGRATION-460"          # parallel_safe: false in the sealed plan
PARALLEL = ("SELFHEAL-450", "CHALLENGER-510", "POISON-540")
TEST_HOST_MAX_TOTAL_SESSIONS = 8


def _begin_observation_process(
    root: str,
    host_runtime: str,
    host_base: str,
    barrier: object,
    results: object,
) -> None:
    with mock.patch.object(
        controller, "_host_runtime_base_dir", return_value=Path(host_base)
    ):
        barrier.wait()
        plane = autopilot.ControlPlane(
            Path(root), host_runtime_dir=Path(host_runtime)
        )
        record = plane.begin_github_snapshot_observation(
            actor="test:parallel-process"
        )
        results.put(
            (
                record["observation_id"],
                record["observation_epoch"],
                record["record_id"],
            )
        )


class DispatchWaveSelectionTests(unittest.TestCase):
    """A release the dispatcher writes must satisfy its own validator."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "work"
        self.root.mkdir()
        self.host_base = Path(self.temporary.name) / "host-authority-base"
        self.host_base_patch = mock.patch.object(
            controller,
            "_host_runtime_base_dir",
            return_value=self.host_base,
        )
        self.host_base_patch.start()
        self.addCleanup(self.host_base_patch.stop)
        self.host_runtime = Path(self.temporary.name) / "host-runtime"
        controller.initialize_host_runtime(self.host_runtime)
        subprocess.run(
            ("git", "init", "--quiet", "--initial-branch=main", str(self.root)),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "-C", str(self.root), "remote", "add", "origin", str(self.root)),
            check=True,
            capture_output=True,
        )
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        subprocess.run(
            (
                "git", "-C", str(self.root), "symbolic-ref", "HEAD",
                f"refs/heads/{control['target']['branch']}",
            ),
            check=True,
            capture_output=True,
        )
        ready_runtime(controller, self.root)
        self.plane = autopilot.ControlPlane(
            self.root, host_runtime_dir=self.host_runtime
        )
        self.host_id = autopilot._canonical_app_server_host_id(self.plane)
        self.provider_identity_digest = autopilot.digest_json(
            {"fixture": "authenticated-test-host-provider"}
        )
        with self.plane.host_lock():
            controller.bind_host_repository_runtime(
                self.plane.host_runtime_dir,
                repository=str(self.plane.control["target"]["repository"]),
                coordination_dir=self.plane.coordination_dir,
                repo_root=self.plane.repo_root,
                transport_digest=str(
                    self.plane.repository_identity["transport_digest"]
                ),
                bound_at=controller.format_time(self.plane.clock()),
            )
            now = self.plane.clock()
            controller.publish_host_capacity(
                self.plane.host_runtime_dir,
                host_id=self.host_id,
                capacity_generation=autopilot.digest_json(
                    {"fixture": "dispatch-host-capacity", "epoch": 1}
                ),
                capacity_epoch=1,
                max_total_sessions=TEST_HOST_MAX_TOTAL_SESSIONS,
                validation_slots=1,
                issued_at=controller.format_time(now),
                expires_at=controller.format_time(now + timedelta(days=1)),
                capability_source="test fixture",
                capability_digest=autopilot.digest_json(
                    {"fixture": "dispatch-host-capability"}
                ),
                provider_identity_source=(
                    autopilot.APP_SERVER_PROVIDER_IDENTITY_SOURCE
                ),
                provider_identity_digest=self.provider_identity_digest,
                declarative=False,
                now=now,
                expected_generation=None,
            )
            with self.plane.arbiter_lock():
                controller.initialize_execution_namespace(
                    self.plane.coordination_dir, self.plane.execution_identity
                )
                self.plane.bind_canonical_remote_transport_identity()
                initial_target = self.plane.current_target_sha()
                initial_observation = {
                    "schema_version": 1,
                    "kind": "hive-mind-initial-remote-target-observation-v1",
                    "repository": str(
                        self.plane.control["target"]["repository"]
                    ),
                    "repository_transport_digest": str(
                        self.plane.repository_identity["transport_digest"]
                    ),
                    "target_ref": f"refs/heads/{self.plane.target_branch}",
                    "target_sha": initial_target,
                    "transport_record_id": self.plane.bind_canonical_remote_transport_identity()[
                        "record_id"
                    ],
                    "execution_id": self.plane.execution_id,
                    "execution_namespace": self.plane.execution_namespace,
                    "observed_at": controller.format_time(self.plane.clock()),
                }
                initial_observation["record_id"] = autopilot.digest_json(
                    initial_observation
                )
                self.plane.initialize_repository_target_watermark(
                    target_sha=initial_target,
                    source_observation=initial_observation,
                    actor="test:runtime-initializer",
                )
        self._make_eligible([SERIAL])

    def _seed_installed_observation(
        self,
        plane: object,
        *,
        force: bool = False,
    ) -> dict[str, object]:
        existing = plane._snapshot_observation()
        if isinstance(existing, dict) and not force:
            return dict(existing)
        canonical = plane._canonical_dispatch_identity()
        previous_epoch = (
            existing.get("observation_epoch", 0)
            if isinstance(existing, dict)
            else 0
        )
        epoch = int(previous_epoch) + 1
        observation_id = autopilot.digest_json(
            {
                "fixture": "installed-observation",
                "epoch": epoch,
                "target_sha": canonical["target_sha"],
            }
        )
        branch_fetches = plane._snapshot_branch_fetches(epoch, observation_id)
        now = plane.clock()
        record: dict[str, object] = {
            "schema_version": 2,
            "kind": autopilot.SNAPSHOT_OBSERVATION_KIND,
            "status": "PENDING",
            "execution_namespace": plane.execution_namespace,
            "execution_id": plane.execution_id,
            "observation_epoch": epoch,
            "observation_id": observation_id,
            "fetch_ref": plane._snapshot_fetch_ref(
                plane.execution_id, epoch, observation_id
            ),
            "branch_fetches": branch_fetches,
            "repository": canonical["repository"],
            "target_branch": canonical["target_branch"],
            "base_target_sha": canonical["target_sha"],
            "target_sha": canonical["target_sha"],
            "plan_fingerprint": canonical["plan_fingerprint"],
            "snapshot_digest": None,
            "candidate_artifact": None,
            "supersedes_observation_id": (
                existing.get("observation_id")
                if isinstance(existing, dict)
                else None
            ),
            "actor": "test:evidence-seed",
            "began_at": controller.format_time(now),
            "expires_at": controller.format_time(now + timedelta(minutes=30)),
            "installed_at": None,
        }
        candidate = self._candidate(record)
        snapshot_digest = autopilot.digest_json(candidate)
        artifact = plane._snapshot_candidate_artifact(
            observation_id, snapshot_digest
        )
        plane._write_immutable_json(plane.execution_dir / artifact, candidate)
        record.update(
            {
                "status": "INSTALLED",
                "snapshot_digest": snapshot_digest,
                "candidate_artifact": artifact,
                "installed_at": controller.format_time(now),
            }
        )
        record = plane._seal_snapshot_observation(record)
        autopilot.atomic_write_json(plane.snapshot_observation_path, record)
        return record

    def _candidate(
        self,
        observation: object,
        *,
        target_sha: str | None = None,
        source: str = "reserved observation fixture",
        branch_heads: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        assert isinstance(observation, dict)
        selected_branch_heads = dict(branch_heads or {})
        branch_observations = [
            {
                "node_id": item["node_id"],
                "branch": item["branch"],
                "fetch_ref": item["fetch_ref"],
                "present": item["branch"] in selected_branch_heads,
                "sha": selected_branch_heads.get(str(item["branch"])),
            }
            for item in observation["branch_fetches"]
        ]
        selected_target = target_sha or str(observation["target_sha"])
        ls_remote_argv = [
            "git",
            "--no-replace-objects",
            "-c",
            f"core.hooksPath={os.devnull}",
            "ls-remote",
            "--heads",
            "origin",
        ]
        remote_lines = [
            (
                f"{selected_target}\t"
                f"refs/heads/{observation['target_branch']}"
            ),
            *[
                f"{sha}\trefs/heads/{branch}"
                for branch, sha in selected_branch_heads.items()
            ],
        ]
        raw_stdout = (
            "\n".join(
                sorted(remote_lines, key=lambda line: line.split("\t", 1)[1])
            )
            + "\n"
        )
        source_material = {
            "schema_version": 1,
            "kind": autopilot.SNAPSHOT_SOURCE_REF_OBSERVATION_KIND,
            "execution_namespace": observation["execution_namespace"],
            "execution_id": observation["execution_id"],
            "observation_id": observation["observation_id"],
            "repository": observation["repository"],
            "repository_transport_digest": self.plane.repository_identity[
                "transport_digest"
            ],
            "target_ref": f"refs/heads/{observation['target_branch']}",
            "target_sha": selected_target,
            "branch_refs": [
                {
                    "node_id": item["node_id"],
                    "branch": item["branch"],
                    "ref": f"refs/heads/{item['branch']}",
                    "present": item["branch"] in selected_branch_heads,
                    "sha": selected_branch_heads.get(str(item["branch"])),
                }
                for item in observation["branch_fetches"]
            ],
            "ls_remote_argv": ls_remote_argv,
            "raw_stdout": raw_stdout,
            "raw_stdout_digest": "sha256:"
            + autopilot.sha256(raw_stdout.encode("utf-8")).hexdigest(),
            "observed_at": "2026-08-14T00:00:00+00:00",
        }
        source_ref_observation = {
            **source_material,
            "record_id": autopilot.digest_json(source_material),
        }
        candidate = {
            "schema_version": 1,
            "kind": autopilot.SNAPSHOT_CANDIDATE_KIND,
            "execution_namespace": observation["execution_namespace"],
            "execution_id": observation["execution_id"],
            "observation_id": observation["observation_id"],
            "observation_epoch": observation["observation_epoch"],
            "fetch_ref": observation["fetch_ref"],
            "repository": observation["repository"],
            "target_branch": observation["target_branch"],
            "target_sha": selected_target,
            "branch_observations": branch_observations,
            "pull_requests": [],
            "raw_pull_requests": [],
            "branches": [
                {
                    "name": item["branch"],
                    "sha": selected_branch_heads[str(item["branch"])],
                    "node_id": item["node_id"],
                }
                for item in observation["branch_fetches"]
                if item["branch"] in selected_branch_heads
            ],
            "github_query": {
                "offline": False,
                "evidence_available": True,
                "complete": True,
                "node_queries": [
                    {
                        "node_id": item["node_id"],
                        "branch": item["branch"],
                        "argv": [
                            "gh",
                            "pr",
                            "list",
                            "--repo",
                            observation["repository"],
                            "--head",
                            item["branch"],
                            "--state",
                            "all",
                            "--limit",
                            str(autopilot.GITHUB_NODE_PR_LIMIT),
                            "--json",
                            "number,state,headRefName,statusCheckRollup",
                        ],
                        "exit_code": 0,
                        "result_count": 0,
                        "result_digest": autopilot.digest_json([]),
                    }
                    for item in observation["branch_fetches"]
                ],
                "exit_code": 0,
            },
            "git_query": {
                "target_refspec": (
                    f"+refs/heads/{observation['target_branch']}:"
                    f"{observation['fetch_ref']}"
                ),
                "branch_refspecs": [
                    (
                        f"+refs/heads/{item['branch']}:"
                        f"{item['fetch_ref']}"
                    )
                    for item in observation["branch_fetches"]
                    if item["branch"] in selected_branch_heads
                ],
                "ls_remote_argv": ls_remote_argv,
            },
            "source_ref_observation": source_ref_observation,
        }
        candidate["candidate_id"] = autopilot.digest_json(candidate)
        return candidate

    def _make_eligible(
        self,
        eligible: list[str],
        *,
        plane: object | None = None,
    ) -> None:
        """Report exactly these nodes as ready, leaving the real plan intact."""

        selected = plane or self.plane
        if not hasattr(selected, "_fixture_dispatch"):
            real_dispatch = selected.dispatch

            def fixture_dispatch(**kwargs: object) -> object:
                kwargs.setdefault("host_id", self.host_id)
                return real_dispatch(**kwargs)

            selected._fixture_dispatch = real_dispatch  # type: ignore[attr-defined]
            selected.dispatch = fixture_dispatch  # type: ignore[method-assign]
        rows = [{"node_id": node_id, "state": "READY"} for node_id in eligible]
        rows += [
            {"node_id": node_id, "state": "COMPLETE"}
            for node_id in selected._nodes
            if node_id not in eligible
        ]
        status = {"ready": list(eligible), "nodes": rows}
        selected._base_status = lambda: dict(status)  # type: ignore[method-assign]
        selected._compiled_frontier = (  # type: ignore[method-assign]
            lambda _status, max_sessions: list(eligible[:max_sessions])
        )
        selected.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        selected._reconciliation_digest = lambda: "sha256:" + "1" * 64  # type: ignore[method-assign]
        selected._recovery_issues = lambda: ()  # type: ignore[method-assign]
        observation = self._seed_installed_observation(selected)
        snapshot_digest = str(observation["snapshot_digest"])
        selected._snapshot_digest = lambda: snapshot_digest  # type: ignore[method-assign]
        if selected._dispatcher_generation() is None:
            with selected.execution_lock("dispatcher-admission.lock"):
                selected._invalidate_dispatcher_admission_unlocked(
                    actor="test:evidence-seed",
                    reason="install deterministic shared fixture evidence",
                    github_snapshot_digest=snapshot_digest,
                    reconciliation_digest="sha256:" + "1" * 64,
                )

    def _linked_divergent_plane(self) -> object:
        subprocess.run(
            ("git", "-C", str(self.root), "config", "user.name", "Dispatch Fixture"),
            check=True,
        )
        subprocess.run(
            (
                "git", "-C", str(self.root), "config", "user.email",
                "dispatch@hive-mind.invalid",
            ),
            check=True,
        )
        subprocess.run(("git", "-C", str(self.root), "add", "-A"), check=True)
        subprocess.run(
            ("git", "-C", str(self.root), "commit", "-m", "dispatch fixture"),
            check=True,
            capture_output=True,
        )
        observation = self._seed_installed_observation(self.plane, force=True)
        # The linked-worktree fixture commit advances the live target after setUp
        # seeded its lightweight evidence generation. Publish that deterministic
        # advance before constructing a consumer in the sibling worktree.
        with self.plane.execution_lock("dispatcher-admission.lock"):
            self.plane._invalidate_dispatcher_admission_unlocked(
                actor="test:linked-worktree-fixture",
                reason="seal the linked-worktree fixture target",
                github_snapshot_digest=str(observation["snapshot_digest"]),
                reconciliation_digest="sha256:" + "1" * 64,
            )
        sibling = self.root.parent / "sibling"
        subprocess.run(
            (
                "git", "-C", str(self.root), "worktree", "add", "--detach",
                str(sibling), "HEAD",
            ),
            check=True,
            capture_output=True,
        )

        def remove_sibling() -> None:
            subprocess.run(
                (
                    "git", "-C", str(self.root), "worktree", "remove", "--force",
                    str(sibling),
                ),
                check=False,
                capture_output=True,
            )

        self.addCleanup(remove_sibling)
        control_path = sibling / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["plan_fingerprint"] = "sha256:" + "b" * 64
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        sibling_plane = autopilot.ControlPlane(sibling)
        self.assertEqual(sibling_plane.coordination_dir, self.plane.coordination_dir)
        return sibling_plane

    def _commit_fixture(self, message: str, *, marker: str | None = None) -> str:
        subprocess.run(
            ("git", "-C", str(self.root), "config", "user.name", "Snapshot Fixture"),
            check=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "config",
                "user.email",
                "snapshot@hive-mind.invalid",
            ),
            check=True,
        )
        if marker is not None:
            (self.root / f"{marker}.txt").write_text(
                f"{marker}\n", encoding="utf-8"
            )
        subprocess.run(("git", "-C", str(self.root), "add", "-A"), check=True)
        subprocess.run(
            ("git", "-C", str(self.root), "commit", "-m", message),
            check=True,
            capture_output=True,
        )
        return subprocess.run(
            ("git", "-C", str(self.root), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _reserve_advanced_candidate(
        self,
    ) -> tuple[str, str, dict[str, object], Path]:
        base = self._commit_fixture("snapshot base")
        target_ref = f"refs/remotes/origin/{self.plane.target_branch}"
        subprocess.run(
            ("git", "-C", str(self.root), "update-ref", target_ref, base),
            check=True,
        )
        self.plane.control["verify_git_objects"] = True
        observation = dict(
            self.plane.begin_github_snapshot_observation(actor="test:remote-reader")
        )
        candidate_sha = self._commit_fixture(
            "compatible target advance", marker="compatible-advance"
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "update-ref",
                str(observation["fetch_ref"]),
                candidate_sha,
            ),
            check=True,
        )
        self.plane._publish_remote_evidence_ref(
            str(observation["fetch_ref"]),
            candidate_sha,
            label="test snapshot target evidence",
        )
        source = self.root / "advanced-snapshot.json"
        source.write_text(
            json.dumps(self._candidate(observation, target_sha=candidate_sha)),
            encoding="utf-8",
        )
        return base, candidate_sha, observation, source

    def _seed_unknown_publication(
        self,
        *,
        finish_unknown: bool = True,
        prepared_only: bool = False,
        validated_only: bool = False,
        expected_sha: str | None = None,
        pinned_sha: str | None = None,
        receipt_sha: str | None = None,
        plane: object | None = None,
    ) -> tuple[dict[str, object], str, str, dict[str, str]]:
        selected = plane or self.plane
        expected = expected_sha or "1" * 40
        pinned = pinned_sha or "2" * 40
        release_id = autopilot.digest_json({"fixture": "publication-release"})
        authority_digest = autopilot.digest_json(
            {"fixture": "publication-authority"}
        )
        heads = [
            {
                "node_id": SERIAL,
                "branch": str(selected.node(SERIAL)["branch"]),
                "sha": receipt_sha or "3" * 40,
            }
        ]
        transaction_key = autopilot.digest_json(
            {
                "kind": "hive-mind-publication-transaction-key-v1",
                "execution_id": selected.execution_id,
                "release_id": release_id,
                "round_id": "R1",
                "expected_target_sha": expected,
                "authority_digest": authority_digest,
                "authority_baseline_digest": authority_digest,
                "receipt_heads": heads,
            }
        )
        nonce = "4" * 64
        lease_nonce = "5" * 64
        transaction_id = autopilot.digest_json(
            {
                "kind": "hive-mind-publication-attempt-key-v1",
                "transaction_key": transaction_key,
                "attempt_epoch": 1,
                "nonce": nonce,
            }
        )
        lease_id = autopilot.digest_json(
            {
                "kind": "hive-mind-publication-coordinator-lease-v1",
                "transaction_id": transaction_id,
                "nonce": lease_nonce,
            }
        )
        reserved_at = "2026-08-14T00:00:00+00:00"
        prepared = selected._seal_publication_record(
            {
                "schema_version": 1,
                "kind": autopilot.PUBLICATION_TRANSACTION_KIND,
                "status": "PREPARED",
                "transaction_key": transaction_key,
                "attempt_epoch": 1,
                "nonce": nonce,
                "transaction_id": transaction_id,
                "execution_namespace": selected.execution_namespace,
                "execution_id": selected.execution_id,
                "release_id": release_id,
                "round_id": "R1",
                "repository": str(selected.control["target"]["repository"]),
                "target_branch": selected.target_branch,
                "expected_target_sha": expected,
                "authority_digest": authority_digest,
                "authority_baseline_digest": authority_digest,
                "receipt_heads": heads,
                "receipt_heads_digest": autopilot.digest_json(heads),
                "transaction_ref": selected.execution_transaction_ref(
                    transaction_id
                ),
                "coordinator_id": "test:publication-coordinator",
                "transaction_lease_nonce": lease_nonce,
                "transaction_lease_id": lease_id,
                "lease_expires_at": "2099-08-14T01:00:00+00:00",
                "publishing_lease_nonce": None,
                "publishing_lease_id": None,
                "publishing_lease_expires_at": None,
                "pinned_sha": None,
                "validation_evidence": None,
                "outcome": None,
                "detail": "fixture publication reserved",
                "actor": "test:publication-coordinator",
                "reserved_at": reserved_at,
                "updated_at": reserved_at,
                "completed_at": None,
            }
        )
        selected._write_publication_pair(
            prepared, detail="fixture publication reserved"
        )
        target_watermark = selected.repository_target_watermark()
        selected.current_release = lambda: {  # type: ignore[method-assign]
            "release_id": release_id,
            "target_sha": expected,
            "target_generation": target_watermark["target_generation"],
            "target_watermark_record_id": target_watermark["record_id"],
            "admission_epoch": 1,
            "host_id": "test:publication-host",
            "capacity_generation": autopilot.digest_json(
                {"fixture": "publication-capacity"}
            ),
        }
        if prepared_only:
            return (
                prepared,
                expected,
                pinned,
                {str(item["node_id"]): str(item["sha"]) for item in heads},
            )
        pinned_record = dict(prepared)
        pinned_record.update(
            {
                "status": "PINNED",
                "pinned_sha": pinned,
                "detail": "fixture portable transaction pin",
                "updated_at": "2026-08-14T00:00:00.500000+00:00",
            }
        )
        pinned_record = selected._seal_publication_record(pinned_record)
        selected._write_publication_pair(
            pinned_record, detail="fixture portable transaction pin"
        )
        capacity_generation = autopilot.digest_json(
            {"fixture": "publication-capacity"}
        )
        provider_generation = autopilot.digest_json(
            {"fixture": "publication-provider", "epoch": 1}
        )
        local_reservation_id = autopilot.digest_json(
            {"fixture": "publication-validation-reservation"}
        )
        host_reservation_id = autopilot.digest_json(
            {
                "kind": "hive-mind-host-reservation-key-v1",
                "repository": str(selected.control["target"]["repository"]),
                "execution_id": selected.execution_id,
                "host_id": "test:publication-host",
                "provider_generation": provider_generation,
                "capacity_generation": capacity_generation,
                "local_reservation_id": local_reservation_id,
                "reservation_kind": "VALIDATION",
            }
        )
        lease_material = {
            "schema_version": 1,
            "node_id": SERIAL,
            "owner": "test:publication-coordinator",
            "target_sha": expected,
            "acquired_at": "2026-08-14T00:00:00.600000+00:00",
            "expires_at": "2099-08-14T01:00:00+00:00",
            "renewal_count": 0,
            "status": "ACTIVE",
            "execution_id": selected.execution_id,
            "validation_resource_key": autopilot.digest_json(
                {"fixture": "validation-resource"}
            ),
            "authority_nonce": "7" * 64,
            "claim_id": None,
            "claim_authority_class": "CONTROLLER_INTERNAL",
            "launch_instruction_id": None,
            "resource_key": None,
            "authority_epoch": None,
            "release_id": release_id,
            "transaction_sha": pinned,
            "host_reservation_id": host_reservation_id,
            "capacity_host_id": "test:publication-host",
            "capacity_generation": capacity_generation,
        }
        validation_lease = {
            **lease_material,
            "lease_id": autopilot.digest_json(lease_material),
            "global_host_reservation_id": host_reservation_id,
            "global_capacity_generation": capacity_generation,
        }
        released_lease = {
            **lease_material,
            "status": "RELEASED",
            "lease_id": validation_lease["lease_id"],
            "released_at": "2026-08-14T00:00:00.900000+00:00",
        }
        reservation_material = {
            "schema_version": 1,
            "kind": "hive-mind-host-reservation-event-v1",
            "state": "RELEASED",
            "reservation_id": host_reservation_id,
            "reservation_kind": "VALIDATION",
            "repository": str(selected.control["target"]["repository"]),
            "execution_id": selected.execution_id,
            "host_id": "test:publication-host",
            "provider_generation": provider_generation,
            "provider_epoch": 1,
            "capacity_generation": capacity_generation,
            "capacity_epoch": 1,
            "local_reservation_id": local_reservation_id,
            "resource_key": lease_material["validation_resource_key"],
            "write_scopes": [],
            "reserved_at": "2026-08-14T00:00:00.500000+00:00",
            "expires_at": "2099-08-14T01:00:00+00:00",
            "released_at": "2026-08-14T00:00:00.900000+00:00",
            "release_actor": "test:publication-coordinator",
            "release_reason": "fixture validation settled",
            "external_cancellation": "NOT_CLAIMED",
            "previous_event_id": None,
        }
        host_reservation = {
            **reservation_material,
            "event_id": autopilot.digest_json(reservation_material),
        }
        cleanup_material = {
            "schema_version": 1,
            "kind": "hive-mind-keyed-validation-cleanup-v1",
            "execution_id": selected.execution_id,
            "release_id": release_id,
            "transaction_sha": pinned,
            "lease_id": validation_lease["lease_id"],
            "lease_released": True,
            "host_reservation": host_reservation,
            "errors": [],
            "recorded_at": "2026-08-14T00:00:00.900000+00:00",
        }
        cleanup = {
            **cleanup_material,
            "record_id": autopilot.digest_json(cleanup_material),
        }
        gate_identity = selected.publication_validation_gate_identity()
        pinned_tree = "8" * 40
        gate = {
            "schema_version": 1,
            "kind": "hive-mind-fixed-publication-gate-result-v1",
            "argv": [
                *list(gate_identity["argv"][:-1]),
                str(selected.repo_root.resolve()),
            ],
            "interpreter_path": gate_identity["interpreter_path"],
            "interpreter_digest_before": gate_identity["interpreter_digest"],
            "interpreter_digest_after": gate_identity["interpreter_digest"],
            "git_executable_path": gate_identity["git_executable_path"],
            "git_executable_digest_before": gate_identity[
                "git_executable_digest"
            ],
            "git_executable_digest_after": gate_identity[
                "git_executable_digest"
            ],
            "round_driver_path": gate_identity["round_driver_path"],
            "round_driver_digest_before": gate_identity["round_driver_digest"],
            "round_driver_digest_after": gate_identity["round_driver_digest"],
            "worktree_tree": pinned_tree,
            "worktree_head_after": pinned,
            "transaction_ref_after": pinned,
            "worktree_status_porcelain": "",
            "environment_policy_digest": gate_identity[
                "environment_policy_digest"
            ],
            "started_at": "2026-08-14T00:00:00.700000+00:00",
            "completed_at": "2026-08-14T00:00:00.800000+00:00",
            "exit_code": 0,
            "output_digest": autopilot.digest_json({"fixture": "gate-output"}),
            "summary": "fixture fixed gate passed",
            "test_manifest_digest": autopilot.digest_json(
                {"fixture": "test-id-manifest"}
            ),
            "test_source_manifest_digest": autopilot.digest_json(
                {"fixture": "test-source-manifest"}
            ),
            "test_counts": {
                "discovered": 1,
                "executed": 1,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "expected_failures": 0,
                "unexpected_successes": 0,
                "successful": True,
            },
            "sandbox_broker_identity_id": gate_identity[
                "sandbox_broker_identity_id"
            ],
            "stdlib_bundle_digest": gate_identity["stdlib_bundle_digest"],
        }
        evidence_material = {
            "schema_version": 1,
            "kind": "hive-mind-fixed-publication-validation-v1",
            "execution_namespace": selected.execution_namespace,
            "execution_id": selected.execution_id,
            "transaction_id": transaction_id,
            "transaction_record_id": pinned_record["record_id"],
            "release_id": release_id,
            "dispatcher_admission_epoch": 1,
            "authority_digest": authority_digest,
            "authority_baseline_digest": authority_digest,
            "receipt_heads_digest": autopilot.digest_json(heads),
            "pinned_sha": pinned,
            "pinned_tree": pinned_tree,
            "protected_test_manifest_digest": autopilot.digest_json(
                {"fixture": "protected-test-source-manifest"}
            ),
            "candidate_test_manifest_digest": gate[
                "test_source_manifest_digest"
            ],
            "test_diff_policy": "TARGET_TEST_BLOBS_IMMUTABLE_ADDITIONS_ALLOWED",
            "governed_kernel_manifest_digest": autopilot.digest_json(
                {"fixture": "governed-autopilot-kernel-manifest"}
            ),
            "kernel_diff_policy": (
                "GOVERNED_AUTOPILOT_KERNEL_EXACTLY_IMMUTABLE"
            ),
            "host_id": "test:publication-host",
            "capacity_generation": capacity_generation,
            "lease": validation_lease,
            "released_lease": released_lease,
            "cleanup": cleanup,
            "gate": gate,
            "broker_completion_id": autopilot.digest_json(
                {"fixture": "publication-validation-broker-completion"}
            ),
        }
        validation_evidence = {
            **evidence_material,
            "evidence_id": autopilot.digest_json(evidence_material),
        }
        validated = dict(pinned_record)
        validated.update(
            {
                "status": "VALIDATED",
                "validation_evidence": validation_evidence,
                "detail": "fixture fixed gate capability",
                "updated_at": "2026-08-14T00:00:00.950000+00:00",
            }
        )
        validated = selected._seal_publication_record(validated)
        selected._write_publication_pair(
            validated, detail="fixture fixed gate capability"
        )
        if validated_only:
            return (
                validated,
                expected,
                pinned,
                {str(item["node_id"]): str(item["sha"]) for item in heads},
            )
        publishing_nonce = "6" * 64
        publishing = dict(validated)
        publishing.update(
            {
                "status": "PUBLISHING",
                "publishing_lease_nonce": publishing_nonce,
                "publishing_lease_id": autopilot.digest_json(
                    {
                        "kind": "hive-mind-publication-operation-lease-v1",
                        "transaction_id": transaction_id,
                        "transaction_lease_id": lease_id,
                        "pinned_sha": pinned,
                        "nonce": publishing_nonce,
                    }
                ),
                "publishing_lease_expires_at": "2099-08-14T01:00:00+00:00",
                "pinned_sha": pinned,
                "detail": "fixture publication in progress",
                "updated_at": "2026-08-14T00:00:01+00:00",
            }
        )
        publishing = selected._seal_publication_record(publishing)
        selected._write_publication_pair(
            publishing, detail="fixture publication in progress"
        )
        if not finish_unknown:
            return (
                publishing,
                expected,
                pinned,
                {str(item["node_id"]): str(item["sha"]) for item in heads},
            )
        unknown = dict(publishing)
        unknown.update(
            {
                "status": "PUBLISH_UNKNOWN",
                "outcome": "PUBLISH_UNKNOWN",
                "detail": "fixture push response was lost",
                "updated_at": "2026-08-14T00:00:02+00:00",
                "completed_at": "2026-08-14T00:00:02+00:00",
            }
        )
        unknown = selected._seal_publication_record(unknown)
        selected._write_publication_pair(
            unknown, detail="fixture push response was lost"
        )
        return (
            unknown,
            expected,
            pinned,
            {str(item["node_id"]): str(item["sha"]) for item in heads},
        )

    def _capacity_policy_inputs(
        self,
        capability: Mapping[str, object] | None = None,
    ) -> tuple[object, str, Mapping[str, object], Mapping[str, object]]:
        module_digest = autopilot.digest_json({"fixture": "adapter-module"})
        provider_identity = {
            "adapter_module_digest": module_digest,
            "provider_identity_digest": self.provider_identity_digest,
        }
        lifecycle_material = {
            "schema_version": 1,
            "kind": "hive-mind-host-lifecycle-capability-v1",
            "host_id": self.host_id,
            "create": True,
            "query": True,
            "resume": True,
            "interrupt": True,
            "archive": True,
            "autonomous_launch": True,
            "source": "test:authenticated-lifecycle",
        }
        lifecycle = {
            **lifecycle_material,
            "record_id": autopilot.digest_json(lifecycle_material),
        }

        class Adapter:
            pass

        adapter = Adapter()
        if capability is not None:
            adapter.host_capacity_capability = (  # type: ignore[attr-defined]
                lambda *, repo_root: dict(capability)
            )
        return adapter, module_digest, provider_identity, lifecycle

    def _capacity_capability(
        self,
        *,
        maximum: int,
        issued_delta: timedelta = timedelta(minutes=-1),
        expiry_delta: timedelta = timedelta(hours=1),
    ) -> dict[str, object]:
        now = self.plane.clock()
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-host-capacity-capability-v1",
            "host_id": self.host_id,
            "provider_identity_digest": self.provider_identity_digest,
            "max_total_sessions": maximum,
            "validation_slots": 1,
            "issued_at": controller.format_time(now + issued_delta),
            "expires_at": controller.format_time(now + expiry_delta),
            "source": "test:sealed-product-capacity",
        }
        return {**material, "record_id": autopilot.digest_json(material)}

    def test_a_serial_node_is_never_seated_beside_parallel_siblings(self) -> None:
        release = self.plane.dispatch(actor="test:dispatcher", host_id=self.host_id)
        wave = list(release["released_wave"])
        serial = [n for n in wave if not self.plane.node(n).get("parallel_safe")]
        if serial:
            self.assertEqual(
                wave, serial[:1],
                "a serial node must be released alone, never with siblings",
            )

    def test_the_written_release_satisfies_its_own_validator(self) -> None:
        """The invariant that actually matters, whatever the wave turns out to be."""

        release = self.plane.dispatch(actor="test:dispatcher", host_id=self.host_id)
        issues = self.plane._release_issues(release)
        self.assertEqual(
            tuple(issues), (),
            f"dispatch wrote a self-invalidating release for wave {release['released_wave']}",
        )

    def test_priority_wins_so_a_serial_node_is_not_starved(self) -> None:
        release = self.plane.dispatch(actor="test:dispatcher", host_id=self.host_id)
        # MIGRATION-460 carries the highest critical_path_importance of this set,
        # so it must take the round rather than being skipped forever.
        self.assertEqual(list(release["released_wave"]), [SERIAL])

    def test_parallel_only_eligibility_still_waves_together(self) -> None:
        self._make_eligible(list(PARALLEL))
        release = self.plane.dispatch(actor="test:dispatcher", host_id=self.host_id)
        self.assertEqual(sorted(release["released_wave"]), sorted(PARALLEL))
        self.assertEqual(tuple(self.plane._release_issues(release)), ())

    def test_requesting_a_serial_node_with_a_sibling_is_refused(self) -> None:
        with self.assertRaises(autopilot.AutopilotError) as raised:
            self.plane.dispatch(
                actor="test:dispatcher",
                host_id=self.host_id,
                requested_nodes=[SERIAL, PARALLEL[0]],
            )
        self.assertIn("compiled frontier", str(raised.exception))

    def test_run_round_cli_accepts_only_the_shared_release_fence(self) -> None:
        release_id = "sha256:" + "a" * 64
        parsed = autopilot.parser().parse_args(
            ["run-round", "--release-id", release_id]
        )
        self.assertEqual(parsed.release_id, release_id)
        self.assertFalse(hasattr(parsed, "claim_id"))
        self.assertFalse(hasattr(parsed, "max_sessions"))
        self.assertFalse(hasattr(parsed, "skip_validation"))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                autopilot.parser().parse_args(
                    [
                        "run-round",
                        "--release-id",
                        release_id,
                        "--claim-authority-class",
                        "PRIVILEGED_INTERNAL",
                    ]
                )
            with self.assertRaises(SystemExit):
                autopilot.parser().parse_args(
                    ["run-round", "--release-id", release_id, "--skip-validation"]
                )

    def test_snapshot_install_cli_requires_a_reserved_observation_id(self) -> None:
        observation_id = "sha256:" + "b" * 64
        parsed = autopilot.parser().parse_args(
            [
                "install-github-snapshot",
                "snapshot.json",
                "--observation-id",
                observation_id,
            ]
        )
        self.assertEqual(parsed.observation_id, observation_id)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                autopilot.parser().parse_args(
                    ["install-github-snapshot", "snapshot.json"]
                )

    def test_render_prompt_requires_and_propagates_authenticated_host_id(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                autopilot.parser().parse_args(["render-prompt", SERIAL])
        parsed = autopilot.parser().parse_args(
            ["render-prompt", SERIAL, "--host-id", self.host_id]
        )
        self.assertEqual(parsed.host_id, self.host_id)

        with mock.patch.object(
            self.plane,
            "render_worker_prompt",
            return_value="authenticated worker prompt",
        ) as render:
            with mock.patch.object(autopilot, "ControlPlane", return_value=self.plane):
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = autopilot.main(
                        [
                            "--repo-root",
                            str(self.root),
                            "render-prompt",
                            SERIAL,
                            "--host-id",
                            self.host_id,
                        ]
                    )
        self.assertEqual(exit_code, 0)
        render.assert_called_once_with(SERIAL, host_id=self.host_id)

    def test_dispatch_enforces_the_canonical_repository_session_cap(self) -> None:
        eligible = list(self.plane._nodes)[
            : TEST_HOST_MAX_TOTAL_SESSIONS + 3
        ]
        self._make_eligible(eligible)
        self.plane._compiled_frontier = (  # type: ignore[method-assign]
            lambda _status, max_sessions: eligible[:max_sessions]
        )
        self.plane.node = lambda _node_id: {  # type: ignore[method-assign]
            "parallel_safe": True,
            "critical_path_importance": 1,
            "downstream_unlock_value": 1,
        }
        self.plane._nodes_conflict = lambda _first, _second: False  # type: ignore[method-assign]
        release = self.plane.dispatch(actor="test:dispatcher", host_id=self.host_id)
        self.assertEqual(
            len(release["released_wave"]),
            TEST_HOST_MAX_TOTAL_SESSIONS,
        )
        self.assertEqual(
            release["session_cap"], TEST_HOST_MAX_TOTAL_SESSIONS
        )
        with self.assertRaisesRegex(autopilot.AutopilotError, "session cap"):
            self.plane.dispatch(
                actor="test:dispatcher",
                host_id=self.host_id,
                requested_nodes=eligible,
            )

    def test_app_server_without_capacity_evidence_is_limited_to_one(self) -> None:
        adapter, module_digest, provider, lifecycle = self._capacity_policy_inputs()
        capacity = autopilot._ensure_app_server_capacity(
            self.plane,
            adapter,
            host_id=self.host_id,
            module_digest=module_digest,
            provider_identity=provider,
            lifecycle=lifecycle,
        )
        self.assertEqual(capacity["max_total_sessions"], 1)
        self.assertEqual(capacity["validation_slots"], 1)
        self.assertIs(capacity["declarative"], True)

    def test_unchanged_capacity_policy_renews_live_permit_without_rotation(
        self,
    ) -> None:
        adapter, module_digest, provider, lifecycle = self._capacity_policy_inputs()
        started_at = self.plane.clock()
        observation = dict(self.plane._snapshot_observation())
        observation["expires_at"] = controller.format_time(
            started_at + timedelta(hours=2)
        )
        observation = self.plane._seal_snapshot_observation(observation)
        autopilot.atomic_write_json(self.plane.snapshot_observation_path, observation)
        with self.plane.execution_lock("dispatcher-admission.lock"):
            self.plane._invalidate_dispatcher_admission_unlocked(
                actor="test:capacity-renewal-fixture",
                reason="extend immutable snapshot freshness past capacity renewal",
                github_snapshot_digest=str(observation["snapshot_digest"]),
                reconciliation_digest="sha256:" + "1" * 64,
            )
        first = autopilot._ensure_app_server_capacity(
            self.plane,
            adapter,
            host_id=self.host_id,
            module_digest=module_digest,
            provider_identity=provider,
            lifecycle=lifecycle,
        )
        release = self.plane.dispatch(
            actor="test:capacity-renewal-live-release",
            host_id=self.host_id,
        )
        reservation_id = release["primary_host_reservations"][0]["reservation_id"]

        renewal_time = started_at + timedelta(minutes=50)
        self.plane.clock = lambda: renewal_time  # type: ignore[method-assign]
        with mock.patch.object(
            controller,
            "_append_host_reservation_unlocked",
            side_effect=RuntimeError(
                "fixture crash after capacity replace before permit renewal"
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "before permit renewal"):
                autopilot._ensure_app_server_capacity(
                    self.plane,
                    adapter,
                    host_id=self.host_id,
                    module_digest=module_digest,
                    provider_identity=provider,
                    lifecycle=lifecycle,
                )
        crashed_capacity = self.plane._strict_json_file(
            controller.host_capacity_path(self.host_runtime, self.host_id),
            label="crash-installed host capacity successor",
        )
        self.assertNotEqual(crashed_capacity["record_id"], first["record_id"])
        with self.plane.host_lock():
            stale_cut = controller.active_global_host_reservations(
                self.plane.host_runtime_dir
            )
        self.assertEqual(stale_cut[0]["state"], "RESERVED")
        self.assertNotEqual(
            stale_cut[0]["expires_at"], crashed_capacity["expires_at"]
        )

        restarted = autopilot.ControlPlane(
            self.root,
            host_runtime_dir=self.host_runtime,
            execution_namespace=self.plane.execution_namespace,
        )
        restarted.clock = lambda: renewal_time  # type: ignore[method-assign]
        renewed_capacity = autopilot._ensure_app_server_capacity(
            restarted,
            adapter,
            host_id=self.host_id,
            module_digest=module_digest,
            provider_identity=provider,
            lifecycle=lifecycle,
        )
        self.assertEqual(
            renewed_capacity["capacity_generation"],
            first["capacity_generation"],
        )
        self.assertEqual(renewed_capacity["capacity_epoch"], first["capacity_epoch"])
        self.assertEqual(renewed_capacity["provider_generation"], first["provider_generation"])
        self.assertNotEqual(renewed_capacity["record_id"], first["record_id"])
        self.assertGreater(
            controller.parse_time(renewed_capacity["expires_at"]),
            controller.parse_time(first["expires_at"]),
        )
        with self.plane.host_lock():
            active = controller.active_global_host_reservations(
                self.plane.host_runtime_dir
            )
            issuance = controller.host_capacity_record_in_current_lineage(
                self.plane.host_runtime_dir,
                self.host_id,
                capacity_generation=str(first["capacity_generation"]),
                record_id=str(first["record_id"]),
            )
            with self.assertRaisesRegex(
                controller.ConfigurationError, "outside the current lineage"
            ):
                controller.host_capacity_record_in_current_lineage(
                    self.plane.host_runtime_dir,
                    self.host_id,
                    capacity_generation=str(first["capacity_generation"]),
                    record_id=autopilot.digest_json(
                        {"fixture": "forged-capacity-issuance"}
                    ),
                )
        self.assertEqual(len(active), 1)
        self.assertEqual(issuance, first)
        renewed_permit = active[0]
        self.assertEqual(renewed_permit["reservation_id"], reservation_id)
        self.assertEqual(renewed_permit["state"], "RENEWED")
        self.assertEqual(
            renewed_permit["capacity_generation"],
            first["capacity_generation"],
        )
        self.assertEqual(
            renewed_permit["expires_at"], renewed_capacity["expires_at"]
        )
        self.assertEqual(tuple(self.plane._release_issues(release)), ())
        with self.plane.dispatcher_launch_authority_guard(
            str(release["released_wave"][0]),
            host_id=self.host_id,
            release_id=str(release["release_id"]),
        ) as guarded:
            self.assertEqual(guarded["release_id"], release["release_id"])

    def test_sealed_live_capacity_evidence_can_raise_the_aggregate_ceiling(self) -> None:
        evidence = self._capacity_capability(maximum=4)
        adapter, module_digest, provider, lifecycle = self._capacity_policy_inputs(
            evidence
        )
        capacity = autopilot._ensure_app_server_capacity(
            self.plane,
            adapter,
            host_id=self.host_id,
            module_digest=module_digest,
            provider_identity=provider,
            lifecycle=lifecycle,
        )
        self.assertEqual(capacity["max_total_sessions"], 4)
        self.assertIs(capacity["declarative"], False)
        self.assertEqual(capacity["capability_source"], evidence["source"])

    def test_tampered_capacity_evidence_fails_without_rotating_generation(self) -> None:
        evidence = self._capacity_capability(maximum=4)
        evidence["max_total_sessions"] = 5
        adapter, module_digest, provider, lifecycle = self._capacity_policy_inputs(
            evidence
        )
        before = controller.read_host_capacity(
            self.host_runtime, self.host_id, now=self.plane.clock()
        )
        with self.assertRaisesRegex(autopilot.AutopilotError, "capability is invalid"):
            autopilot._ensure_app_server_capacity(
                self.plane,
                adapter,
                host_id=self.host_id,
                module_digest=module_digest,
                provider_identity=provider,
                lifecycle=lifecycle,
            )
        after = controller.read_host_capacity(
            self.host_runtime, self.host_id, now=self.plane.clock()
        )
        self.assertEqual(after, before)

    def test_expired_capacity_evidence_falls_back_to_one(self) -> None:
        evidence = self._capacity_capability(
            maximum=4,
            issued_delta=timedelta(hours=-2),
            expiry_delta=timedelta(hours=-1),
        )
        adapter, module_digest, provider, lifecycle = self._capacity_policy_inputs(
            evidence
        )
        capacity = autopilot._ensure_app_server_capacity(
            self.plane,
            adapter,
            host_id=self.host_id,
            module_digest=module_digest,
            provider_identity=provider,
            lifecycle=lifecycle,
        )
        self.assertEqual(capacity["max_total_sessions"], 1)
        self.assertIs(capacity["declarative"], True)

    def test_dispatch_compiles_against_the_aggregate_host_kernel_budget(self) -> None:
        foreign = [
            {
                "reservation_id": autopilot.digest_json(
                    {"fixture": "foreign-host-reservation", "index": index}
                ),
                "execution_id": autopilot.digest_json(
                    {"fixture": "foreign-execution", "index": index}
                ),
                # Provider labels are provenance only and must not create a
                # second capacity partition.
                "host_id": f"legacy-provider-alias-{index}",
            }
            for index in range(TEST_HOST_MAX_TOTAL_SESSIONS - 1)
        ]
        observed_caps: list[int] = []

        def stop_before_effects(**kwargs: object) -> Mapping[str, object]:
            observed_caps.append(int(kwargs["session_cap"]))
            raise RuntimeError("stop after aggregate capacity compilation")

        with mock.patch.object(
            autopilot,
            "active_global_host_reservations",
            return_value=tuple(foreign),
        ):
            with mock.patch.object(
                self.plane,
                "_build_dispatch_release_unlocked",
                side_effect=stop_before_effects,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "aggregate capacity compilation"
                ):
                    self.plane.dispatch(
                        actor="test:aggregate-host-capacity",
                        host_id=self.host_id,
                    )
        self.assertEqual(observed_caps, [1])

    def test_app_server_provider_digest_matches_the_adapter_contract(self) -> None:
        adapter_path = Path(autopilot.__file__).resolve().with_name(
            "app_server_host.py"
        )
        module_digest = "sha256:" + autopilot.sha256(
            adapter_path.read_bytes()
        ).hexdigest()
        launcher = self.root / "sealed-launcher.bin"
        launcher.write_bytes(b"sealed launcher")
        launcher_digest = "sha256:" + autopilot.sha256(
            launcher.read_bytes()
        ).hexdigest()
        runtime_identity = self.plane._strict_json_file(
            self.plane.host_runtime_dir / "host-runtime-identity.json",
            label="test host runtime identity",
        )
        provider_material = {
            "kind": "hive-mind-codex-app-server-provider-identity-v1",
            "machine_user_id": runtime_identity["machine_user_id"],
            "launcher_path": str(launcher.resolve()),
            "launcher_digest": launcher_digest,
            "cli_module_path": None,
            "cli_module_digest": None,
            "executable_path": str(launcher.resolve()),
            "executable_digest": launcher_digest,
            "executable_version": "fixture-1",
            "schema_bundle_digest": autopilot.digest_json({"fixture": "schema"}),
            "thread_start_schema_digest": autopilot.digest_json(
                {"fixture": "thread-start"}
            ),
            "turn_start_schema_digest": autopilot.digest_json(
                {"fixture": "turn-start"}
            ),
            "environment_root_digest": autopilot.digest_json(
                {"fixture": "environment"}
            ),
            "behavior_environment_digest": autopilot.digest_json(
                {"fixture": "behavior-environment"}
            ),
            "provider_config_digest": autopilot.digest_json(
                {"fixture": "provider-config"}
            ),
            "account_identity_digest": autopilot.digest_json(
                {"fixture": "account-identity"}
            ),
            "transport": "stdio://",
            "initialize_result_digest": autopilot.digest_json(
                {"fixture": "initialize"}
            ),
        }
        identity_material = {
            "schema_version": 1,
            "kind": "hive-mind-codex-app-server-provider-identity-v1",
            "execution_namespace": self.plane.execution_namespace,
            "execution_id": self.plane.execution_id,
            "host_id": self.host_id,
            "machine_user_id": runtime_identity["machine_user_id"],
            "provider_identity_digest": autopilot.digest_json(provider_material),
            "adapter_module_path": str(adapter_path),
            "adapter_module_digest": module_digest,
            "launcher_path": str(launcher.resolve()),
            "launcher_digest": launcher_digest,
            "cli_module_path": None,
            "cli_module_digest": None,
            "executable_path": str(launcher.resolve()),
            "executable_digest": launcher_digest,
            "executable_version": "fixture-1",
            "schema_bundle_digest": provider_material["schema_bundle_digest"],
            "thread_start_schema_digest": provider_material[
                "thread_start_schema_digest"
            ],
            "turn_start_schema_digest": provider_material[
                "turn_start_schema_digest"
            ],
            "environment_root_digest": provider_material[
                "environment_root_digest"
            ],
            "behavior_environment_digest": provider_material[
                "behavior_environment_digest"
            ],
            "provider_config_digest": provider_material[
                "provider_config_digest"
            ],
            "execution_config_digest": autopilot.digest_json(
                {"fixture": "execution-config"}
            ),
            "account_identity_digest": provider_material[
                "account_identity_digest"
            ],
            "effective_model": "fixture-model",
            "effective_model_provider": None,
            "transport": "stdio://",
            "initialize_result_digest": provider_material[
                "initialize_result_digest"
            ],
            "created_at": controller.format_time(self.plane.clock()),
        }
        identity = {
            **identity_material,
            "record_id": autopilot.digest_json(identity_material),
        }

        class Adapter:
            def host_provider_identity(
                self, *, repo_root: Path
            ) -> Mapping[str, object]:
                self_root = repo_root
                if self_root != self.plane_root:
                    raise AssertionError("unexpected repository")
                return identity

        adapter = Adapter()
        adapter.plane_root = self.plane.repo_root  # type: ignore[attr-defined]
        self.assertEqual(
            autopilot._app_server_provider_identity(
                self.plane,
                adapter,
                host_id=self.host_id,
                module_digest=module_digest,
            ),
            identity,
        )
        execution_variant_material = dict(identity)
        execution_variant_material.pop("record_id")
        execution_variant_material["execution_config_digest"] = autopilot.digest_json(
            {"fixture": "another-execution-config"}
        )
        execution_variant_material["effective_model"] = "fixture-model-variant"
        identity = {
            **execution_variant_material,
            "record_id": autopilot.digest_json(execution_variant_material),
        }
        accepted_variant = autopilot._app_server_provider_identity(
            self.plane,
            adapter,
            host_id=self.host_id,
            module_digest=module_digest,
        )
        self.assertEqual(
            accepted_variant["provider_identity_digest"],
            autopilot.digest_json(provider_material),
        )

        provider_tamper_material = dict(identity)
        provider_tamper_material.pop("record_id")
        provider_tamper_material["provider_config_digest"] = autopilot.digest_json(
            {"fixture": "tampered-provider-config"}
        )
        identity = {
            **provider_tamper_material,
            "record_id": autopilot.digest_json(provider_tamper_material),
        }
        with self.assertRaisesRegex(
            autopilot.AutopilotError, "provider identity is invalid"
        ):
            autopilot._app_server_provider_identity(
                self.plane,
                adapter,
                host_id=self.host_id,
                module_digest=module_digest,
            )

    def test_host_startup_reaper_resolves_only_authenticated_canonical_checkouts(
        self,
    ) -> None:
        other = Path(self.temporary.name) / "other-repository"
        other.mkdir()
        subprocess.run(
            ("git", "init", "--quiet", "--initial-branch=main", str(other)),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "-C", str(other), "remote", "add", "origin", str(other)),
            check=True,
            capture_output=True,
        )
        copy_autopilot_fixture(
            Path(__file__).resolve().parents[1], other / ".autopilot"
        )
        control_path = other / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["target"]["repository"] = "fixture/other-repository"
        control_path.write_text(
            json.dumps(control, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        identity = controller.runtime_repository_identity(other)
        self.assertIsInstance(identity, Mapping)
        binding = {
            "repository": identity["repository"],
            "transport_digest": identity["transport_digest"],
            "coordination_dir": str((other / ".autopilot" / "state").resolve()),
            "checkout_roots": [str(other.resolve())],
        }
        seen: list[Path | None] = []

        def global_reaper(
            _host_runtime: Path,
            *,
            adapter_resolver: object,
            repository_root_resolver: object,
            actor: str,
            reason: str,
        ) -> tuple[Mapping[str, object], ...]:
            del adapter_resolver, actor, reason
            seen.append(repository_root_resolver(binding))
            return ()

        with mock.patch.object(
            autopilot,
            "reconcile_global_expired_host_reservations",
            side_effect=global_reaper,
        ):
            autopilot._recover_expired_app_server_reservations(
                self.plane, object(), host_id=self.host_id
            )
        self.assertEqual(seen, [other.resolve()])

        unresolved = ({
            "state": "WAITING_FOR_REPOSITORY",
            "reservation_id": "sha256:" + "8" * 64,
        },)
        with mock.patch.object(
            autopilot,
            "reconcile_global_expired_host_reservations",
            return_value=unresolved,
        ):
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "remain charged"
            ):
                autopilot._recover_expired_app_server_reservations(
                    self.plane, object(), host_id=self.host_id
                )

    def test_global_reaper_reuses_and_closes_foreign_adapter_exactly_once(self) -> None:
        foreign_root = Path(self.temporary.name) / "foreign-checkout"
        foreign_root.mkdir()
        foreign_execution_dir = Path(self.temporary.name) / "foreign-execution"
        foreign_execution_dir.mkdir()
        execution_id = autopilot.digest_json({"fixture": "foreign-execution"})
        execution_identity = {
            "namespace": "foreign",
            "execution_id": execution_id,
            "repository": "fixture/foreign-repository",
        }
        repository_binding = {
            "repository": "fixture/foreign-repository",
            "coordination_dir": str(Path(self.temporary.name) / "foreign-state"),
        }
        reservation = {
            "execution_id": execution_id,
            "host_id": self.host_id,
        }

        class ForeignPlane:
            pass

        foreign_plane = ForeignPlane()
        foreign_plane.repo_root = foreign_root
        foreign_plane.execution_dir = foreign_execution_dir
        foreign_plane.execution_namespace = "foreign"
        foreign_plane.execution_identity = execution_identity
        foreign_plane.execution_id = execution_id

        class ForeignAdapter:
            def __init__(self) -> None:
                self.close_count = 0

            def close(self) -> None:
                self.close_count += 1

        foreign_adapter = ForeignAdapter()
        returned: list[object] = []

        def global_reaper(
            _host_runtime: Path,
            *,
            adapter_resolver: object,
            repository_root_resolver: object,
            actor: str,
            reason: str,
        ) -> tuple[Mapping[str, object], ...]:
            del repository_root_resolver, actor, reason
            for _ in range(2):
                returned.append(
                    adapter_resolver(
                        reservation=reservation,
                        repository_binding=repository_binding,
                        execution_identity=execution_identity,
                        repo_root=foreign_root,
                        execution_dir=foreign_execution_dir,
                    )
                )
            return ()

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(autopilot, "ControlPlane", return_value=foreign_plane)
            )
            stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "_canonical_app_server_host_id",
                    return_value=self.host_id,
                )
            )
            instantiate = stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "_instantiate_app_server_adapter",
                    return_value=(foreign_adapter, "digest", {}, {}),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "reconcile_global_expired_host_reservations",
                    side_effect=global_reaper,
                )
            )
            autopilot._recover_expired_app_server_reservations(
                self.plane, object(), host_id=self.host_id
            )
        self.assertEqual(returned, [foreign_adapter, foreign_adapter])
        self.assertEqual(instantiate.call_count, 1)
        self.assertEqual(foreign_adapter.close_count, 1)

    def test_global_reaper_closes_foreign_adapter_when_reconciliation_raises(self) -> None:
        foreign_root = Path(self.temporary.name) / "foreign-error-checkout"
        foreign_root.mkdir()
        foreign_execution_dir = Path(self.temporary.name) / "foreign-error-execution"
        foreign_execution_dir.mkdir()
        execution_id = autopilot.digest_json({"fixture": "foreign-error"})
        execution_identity = {
            "namespace": "foreign-error",
            "execution_id": execution_id,
            "repository": "fixture/foreign-error-repository",
        }
        repository_binding = {
            "repository": "fixture/foreign-error-repository",
            "coordination_dir": str(Path(self.temporary.name) / "foreign-error-state"),
        }
        reservation = {"execution_id": execution_id, "host_id": self.host_id}

        class ForeignPlane:
            pass

        foreign_plane = ForeignPlane()
        foreign_plane.repo_root = foreign_root
        foreign_plane.execution_dir = foreign_execution_dir
        foreign_plane.execution_namespace = "foreign-error"
        foreign_plane.execution_identity = execution_identity
        foreign_plane.execution_id = execution_id

        class ForeignAdapter:
            close_count = 0

            def close(self) -> None:
                self.close_count += 1

        foreign_adapter = ForeignAdapter()

        def global_reaper(
            _host_runtime: Path,
            *,
            adapter_resolver: object,
            repository_root_resolver: object,
            actor: str,
            reason: str,
        ) -> tuple[Mapping[str, object], ...]:
            del repository_root_resolver, actor, reason
            self.assertIs(
                adapter_resolver(
                    reservation=reservation,
                    repository_binding=repository_binding,
                    execution_identity=execution_identity,
                    repo_root=foreign_root,
                    execution_dir=foreign_execution_dir,
                ),
                foreign_adapter,
            )
            raise RuntimeError("simulated global recovery failure")

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(autopilot, "ControlPlane", return_value=foreign_plane)
            )
            stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "_canonical_app_server_host_id",
                    return_value=self.host_id,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "_instantiate_app_server_adapter",
                    return_value=(foreign_adapter, "digest", {}, {}),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "reconcile_global_expired_host_reservations",
                    side_effect=global_reaper,
                )
            )
            with self.assertRaisesRegex(RuntimeError, "global recovery failure"):
                autopilot._recover_expired_app_server_reservations(
                    self.plane, object(), host_id=self.host_id
                )
        self.assertEqual(foreign_adapter.close_count, 1)

    def test_authenticated_observer_cannot_admit_incomplete_work(self) -> None:
        release = self.plane.dispatch(
            actor="test:observer-release", host_id=self.host_id
        )
        context = autopilot.ObserverContext(
            execution_dir=self.plane.execution_dir,
            execution_id=self.plane.execution_id,
            execution_namespace=self.plane.execution_namespace,
            plan_fingerprint=self.plane.expected_plan_fingerprint,
            initial_frontier_id=self.plane.expected_plan_fingerprint,
            frontier_id=self.plane.expected_plan_fingerprint,
            completed_frontiers=(),
        )
        incomplete = {"complete": False, "ready": list(release["released_wave"])}
        with mock.patch.object(
            self.plane, "observe_status", return_value=incomplete
        ):
            with mock.patch.object(self.plane, "_release_issues", return_value=()):
                with mock.patch.object(self.plane, "dispatch") as dispatch:
                    with mock.patch.object(
                        autopilot, "build_orchestration_contract"
                    ) as build:
                        with mock.patch.object(autopilot, "bind_launch") as bind:
                            with mock.patch.object(
                                autopilot, "reserve_global_host_session"
                            ) as reserve:
                                with mock.patch.object(
                                    autopilot, "execute_contract"
                                ) as execute:
                                    with mock.patch.object(
                                        self.plane, "round_authority_snapshot"
                                    ) as round_authority:
                                        result = autopilot._supervisor_terminal_observer(
                                            self.plane,
                                            object(),
                                            context=context,
                                            host_id=self.host_id,
                                        )
        self.assertEqual(
            result.disposition, autopilot.StepDisposition.WAITING_FOR_HOST
        )
        self.assertIn("no dispatch", result.detail)
        dispatch.assert_not_called()
        build.assert_not_called()
        bind.assert_not_called()
        reserve.assert_not_called()
        execute.assert_not_called()
        round_authority.assert_not_called()

    def test_supervisor_authenticator_binds_nondefault_execution_to_exact_plan(
        self,
    ) -> None:
        selected = autopilot.ControlPlane(
            self.root,
            execution_namespace="application-two",
            host_runtime_dir=self.host_runtime,
        )
        with selected.host_lock():
            with selected.arbiter_lock():
                controller.initialize_execution_namespace(
                    selected.coordination_dir, selected.execution_identity
                )
        journal = (
            selected.execution_dir / autopilot.execution_supervisor_runtime.JOURNAL_NAME
        )
        wrong_plan = autopilot.digest_json({"fixture": "another-plan"})
        def authenticate(
            directory: Path,
            execution_id: str,
            namespace: str,
            plan: str,
        ) -> Path:
            return autopilot._authenticate_supervisor_execution(
                selected, directory, execution_id, namespace, plan
            )

        with self.assertRaises(autopilot.SupervisorError):
            autopilot.run_to_fixed_point(
                execution_dir=selected.execution_dir,
                execution_id=selected.execution_id,
                execution_namespace=selected.execution_namespace,
                authenticate=authenticate,
                plan_fingerprint=wrong_plan,
                initial_frontier_id=wrong_plan,
                host_capability=autopilot.HostCapability.NO_LAUNCH,
                step=lambda _context: self.fail("NO_LAUNCH invoked the step callback"),
                verify_fixed_point=lambda _request: self.fail(
                    "NO_LAUNCH invoked the fixed-point verifier"
                ),
                clock=selected.clock,
            )
        self.assertFalse(journal.exists())

        result = autopilot.run_to_fixed_point(
            execution_dir=selected.execution_dir,
            execution_id=selected.execution_id,
            execution_namespace=selected.execution_namespace,
            authenticate=authenticate,
            plan_fingerprint=selected.expected_plan_fingerprint,
            initial_frontier_id=selected.expected_plan_fingerprint,
            host_capability=autopilot.HostCapability.NO_LAUNCH,
            step=lambda _context: self.fail("NO_LAUNCH invoked the step callback"),
            verify_fixed_point=lambda _request: self.fail(
                "NO_LAUNCH invoked the fixed-point verifier"
            ),
            clock=selected.clock,
        )
        self.assertEqual(
            result.disposition, autopilot.StepDisposition.WAITING_FOR_HOST
        )
        self.assertTrue(journal.is_file())

    def test_plain_run_can_reobserve_and_wake_a_controller_wait(self) -> None:
        stored = autopilot.digest_json({"fixture": "stored-wait-observation"})
        current = autopilot.digest_json({"fixture": "changed-wait-observation"})
        token = autopilot.digest_json(
            {
                "kind": "hive-mind-supervisor-wait-resume-v1",
                "execution_id": self.plane.execution_id,
                "frontier_id": self.plane.expected_plan_fingerprint,
                "observation_fingerprint": stored,
            }
        )
        def authenticate(
            directory: Path,
            execution_id: str,
            namespace: str,
            plan: str,
        ) -> Path:
            return autopilot._authenticate_supervisor_execution(
                self.plane, directory, execution_id, namespace, plan
            )
        waiting = autopilot.run_to_fixed_point(
            execution_dir=self.plane.execution_dir,
            execution_id=self.plane.execution_id,
            execution_namespace=self.plane.execution_namespace,
            authenticate=authenticate,
            plan_fingerprint=self.plane.expected_plan_fingerprint,
            initial_frontier_id=self.plane.expected_plan_fingerprint,
            host_capability=autopilot.HostCapability.AUTHENTICATED_LIFECYCLE,
            step=lambda _context: autopilot.StepResult(
                disposition=autopilot.StepDisposition.WAITING,
                detail="fixture controller wait",
                wait_condition=autopilot.WaitCondition(
                    observation_fingerprint=stored,
                    resume_token=token,
                ),
            ),
            verify_fixed_point=lambda _request: self.fail(
                "WAITING invoked the fixed-point verifier"
            ),
            clock=self.plane.clock,
        )
        self.assertEqual(waiting.disposition, autopilot.StepDisposition.WAITING)

        with mock.patch.object(
            autopilot,
            "_supervisor_wait_observation_fingerprint",
            return_value=current,
        ) as observe:
            observed, resumed_with = autopilot._automatic_supervisor_wait_resume(
                self.plane,
                observation_fingerprint=None,
                resume_token=None,
            )
            resumed_step = mock.Mock(
                return_value=autopilot.StepResult(
                    disposition=autopilot.StepDisposition.BLOCKED,
                    detail="fixture changed observation was admitted exactly once",
                )
            )
            resumed = autopilot.run_to_fixed_point(
                execution_dir=self.plane.execution_dir,
                execution_id=self.plane.execution_id,
                execution_namespace=self.plane.execution_namespace,
                authenticate=authenticate,
                plan_fingerprint=self.plane.expected_plan_fingerprint,
                initial_frontier_id=self.plane.expected_plan_fingerprint,
                host_capability=autopilot.HostCapability.AUTHENTICATED_LIFECYCLE,
                step=resumed_step,
                verify_fixed_point=lambda _request: self.fail(
                    "BLOCKED invoked the fixed-point verifier"
                ),
                verify_wait_observation=lambda request: (
                    autopilot._supervisor_wait_observation_verifier(
                        self.plane, request=request
                    )
                ),
                observation_fingerprint=observed,
                resume_token=resumed_with,
                clock=self.plane.clock,
            )
        self.assertEqual((observed, resumed_with), (current, token))
        self.assertGreaterEqual(observe.call_count, 2)
        self.assertEqual(resumed.disposition, autopilot.StepDisposition.BLOCKED)
        resumed_step.assert_called_once()

    def test_terminal_observer_recovers_one_expired_validation_lease_before_quiescence(
        self,
    ) -> None:
        release_id = autopilot.digest_json({"fixture": "observer-terminal-release"})
        release = {"release_id": release_id}
        lease_id = autopilot.digest_json({"fixture": "expired-validation-lease"})
        before = {
            "complete": True,
            "expired_validation_lease": {"lease_id": lease_id},
        }
        after = {"complete": True, "expired_validation_lease": None}
        authority = {
            "status": {"complete": True},
            "active_write_launch_reservations": [],
            "active_host_reservations": [],
            "execution_global_host_reservations": [],
            "active_claims": [],
            "conflicting_global_reservations": [],
            "reconciliation_obligations": [],
            "host_effect_obligations": [],
            "active_validation_lease": None,
            "active_publication_count": 0,
            "active_host_effect_count": 0,
        }
        terminal_observation_id = autopilot.digest_json(
            {"fixture": "terminal-host-observation"}
        )
        context = autopilot.ObserverContext(
            execution_dir=self.plane.execution_dir,
            execution_id=self.plane.execution_id,
            execution_namespace=self.plane.execution_namespace,
            plan_fingerprint=self.plane.expected_plan_fingerprint,
            initial_frontier_id=self.plane.expected_plan_fingerprint,
            frontier_id=self.plane.expected_plan_fingerprint,
            completed_frontiers=(),
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.plane, "observe_status", side_effect=[before, after]
                )
            )
            broken = stack.enter_context(
                mock.patch.object(self.plane, "break_expired_validation_lease")
            )
            stack.enter_context(
                mock.patch.object(self.plane, "current_release", return_value=release)
            )
            stack.enter_context(
                mock.patch.object(self.plane, "_release_issues", return_value=())
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane, "round_authority_snapshot", return_value=authority
                )
            )
            stack.enter_context(
                mock.patch.object(
                    autopilot,
                    "_capture_terminal_lifecycle_observation",
                    return_value=terminal_observation_id,
                )
            )
            result = autopilot._supervisor_terminal_observer(
                self.plane,
                object(),
                context=context,
                host_id=self.host_id,
            )
        self.assertEqual(
            result.disposition, autopilot.StepDisposition.PLAN_QUIESCENT
        )
        self.assertEqual(result.terminal_observation_id, terminal_observation_id)
        broken.assert_called_once_with(
            actor="autopilot:observer-expired-validation-recovery",
            lease_id=lease_id,
        )

    def test_fixed_point_verifier_rejects_publication_racing_terminal_seal(self) -> None:
        release_id = autopilot.digest_json({"fixture": "terminal-release"})
        watermark = dict(self.plane.repository_target_watermark())
        release = {
            "release_id": release_id,
            "target_sha": watermark["target_sha"],
            "target_generation": watermark["target_generation"],
            "target_watermark_record_id": watermark["record_id"],
            "admission_epoch": 1,
        }
        observation_id = autopilot.digest_json({"fixture": "host-zero"})
        request = autopilot.FixedPointVerificationRequest(
            execution_dir=self.plane.execution_dir,
            execution_id=self.plane.execution_id,
            execution_namespace=self.plane.execution_namespace,
            plan_fingerprint=self.plane.expected_plan_fingerprint,
            initial_frontier_id=self.plane.expected_plan_fingerprint,
            current_frontier_id=self.plane.expected_plan_fingerprint,
            terminal_observation_id=observation_id,
        )
        publication = {
            "transaction_id": autopilot.digest_json({"fixture": "terminal-race"})
        }
        stable = {
            "schema_version": 1,
            "kind": "hive-mind-round-authority-snapshot-v1",
            "execution_id": self.plane.execution_id,
            "execution_namespace": self.plane.execution_namespace,
            "release_id": release_id,
            "admission_epoch": 1,
            "release": release,
            "repository_target_watermark": watermark,
            "active_write_launch_reservations": [],
            "active_host_reservations": [],
            "execution_global_host_reservations": [],
            "host_capacity_generations": {},
            "active_claims": [],
            "active_validation_lease": None,
            "publication_transaction_fence": publication,
            "active_publication_count": 1,
            "plan_terminal_fence": None,
            "terminal_launch_bindings": [],
            "terminal_sidecar_bindings": [],
            "active_host_effect_count": 0,
            "host_effect_obligations": [],
            "host_effect_obligation_digest": autopilot.digest_json([]),
            "conflicting_global_reservations": [],
            "reconciliation_obligations": [],
            "status": {
                "nodes": [],
                "complete": True,
                "ready": [],
                "reconciliation_required": False,
            },
        }
        cut_digest = autopilot.digest_json(stable)
        seal_material = {
            "schema_version": 1,
            "kind": controller.PLAN_TERMINAL_FENCE_KIND,
            "execution_id": self.plane.execution_id,
            "execution_namespace": self.plane.execution_namespace,
            "release_id": release_id,
            "admission_epoch": 1,
            "target_sha": release["target_sha"],
            "target_generation": release["target_generation"],
            "target_watermark_record_id": release[
                "target_watermark_record_id"
            ],
            "plan_fingerprint": self.plane.expected_plan_fingerprint,
            "authority_digest": cut_digest,
            "controller_observation_id": autopilot.digest_json(
                {"fixture": "controller-cut"}
            ),
            "sealed_by": "test:controller",
            "sealed_at": "2026-08-14T00:00:00+00:00",
            "state": "PLAN_QUIESCENT",
        }
        sealed = {
            **seal_material,
            "record_id": autopilot.digest_json(seal_material),
        }
        terminal_snapshot = {
            **stable,
            "plan_terminal_fence": sealed,
            "authority_digest": autopilot.digest_json(
                {**stable, "plan_terminal_fence": sealed}
            ),
            "publication_transaction_status": "PREPARED",
            "observed_at": "2026-08-14T00:00:01+00:00",
        }
        before = {
            "execution_id": self.plane.execution_id,
            "execution_namespace": self.plane.execution_namespace,
            "release_id": release_id,
            "authority_digest": cut_digest,
        }
        lifecycle = {
            "active_host_threads": 0,
            "active_host_turns": 0,
            "unobserved_host_lifecycle_items": 0,
        }
        with mock.patch.object(self.plane, "current_release", return_value=release):
            with mock.patch.object(self.plane, "plan_terminal_fence", return_value=None):
                with contextlib.ExitStack() as stack:
                    stack.enter_context(
                        mock.patch.object(
                            self.plane,
                            "round_authority_snapshot",
                            side_effect=[before, terminal_snapshot],
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            self.plane, "seal_plan_quiescent", return_value=sealed
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            self.plane, "_release_issues", return_value=()
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            self.plane,
                            "repository_target_watermark",
                            return_value=watermark,
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            self.plane,
                            "_remote_ref_sha",
                            return_value=release["target_sha"],
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            autopilot,
                            "_authenticated_host_lifecycle_observation",
                            return_value=lifecycle,
                        )
                    )
                    with self.assertRaisesRegex(
                        autopilot.AutopilotError,
                        "zero-activity fixed point",
                    ):
                        autopilot._supervisor_fixed_point_verifier(
                            self.plane,
                            object(),
                            host_id=self.host_id,
                            request=request,
                        )

    def test_two_worktrees_share_one_generation_and_stale_release_cannot_claim(self) -> None:
        sibling = self._linked_divergent_plane()
        self.plane.control["verify_git_objects"] = True
        sibling.control["verify_git_objects"] = True
        self._make_eligible([SERIAL], plane=self.plane)
        first = self.plane.dispatch(
            actor="test:primary",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )

        plan_path = sibling.ap_root / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for node in plan["nodes"]:
            if node.get("id") == PARALLEL[0]:
                node["objective"] = "stale but internally consistent divergent objective"
                break
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        control_path = sibling.ap_root / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        material = dict(plan)
        material.pop("plan_fingerprint", None)
        control["plan_fingerprint"] = autopilot.digest_json(material)
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        sibling = autopilot.ControlPlane(sibling.repo_root)
        sibling.control["verify_git_objects"] = True
        self._make_eligible([PARALLEL[0]], plane=sibling)
        with self.assertRaisesRegex(autopilot.AutopilotError, "stale relative"):
            sibling.dispatch(
                actor="test:stale-worktree",
                host_id=self.host_id,
                requested_nodes=[PARALLEL[0]],
            )

        self.assertEqual(self.plane.current_release()["release_id"], first["release_id"])
        local_release = sibling.state_dir / "dispatcher-release.json"
        local_release.parent.mkdir(parents=True, exist_ok=True)
        local_release.write_text(
            json.dumps({"release_id": "sha256:" + "f" * 64}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(sibling.current_release()["release_id"], first["release_id"])

        self.plane.node_view = lambda node_id: controller.NodeView(  # type: ignore[method-assign]
            node_id,
            "READY",
            (),
            (),
            branch=str(self.plane.node(node_id).get("branch", "fixture")),
        )
        sibling.node_view = self.plane.node_view  # type: ignore[method-assign]
        sibling.control["plan_fingerprint"] = self.plane.expected_plan_fingerprint
        sibling.plan = self.plane.plan
        sibling._nodes = self.plane._nodes
        sibling._snapshot_digest = lambda: None  # type: ignore[method-assign]
        sibling._reconciliation_digest = lambda: None  # type: ignore[method-assign]
        claim = sibling.claim_internal(SERIAL, "worker:secondary")
        self.assertEqual(claim["node_id"], SERIAL)

    def test_active_claim_prevents_divergent_worktree_from_replacing_wave(self) -> None:
        sibling = self._linked_divergent_plane()
        self.plane.control["verify_git_objects"] = True
        sibling.control["verify_git_objects"] = True
        self._make_eligible([SERIAL], plane=self.plane)
        release = self.plane.dispatch(
            actor="test:primary",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        self.plane.node_view = lambda node_id: controller.NodeView(  # type: ignore[method-assign]
            node_id,
            "READY",
            (),
            (),
            branch=str(self.plane.node(node_id).get("branch", "fixture")),
        )
        self.plane.claim_internal(SERIAL, "worker:primary")
        generation_before = dict(self.plane._dispatcher_generation())
        reconciliation_path = self.plane.state_dir / "target.json"
        self.assertFalse(reconciliation_path.exists())
        with self.assertRaisesRegex(autopilot.AutopilotError, "deferred"):
            self.plane.reconcile(
                self.plane.current_target_sha(),
                actor="test:reconciler",
                reason="new evidence arrived during the wave",
            )
        self.assertFalse(reconciliation_path.exists())
        self.assertEqual(dict(self.plane._dispatcher_generation()), generation_before)
        self._make_eligible([PARALLEL[0]], plane=sibling)
        with self.assertRaisesRegex(autopilot.AutopilotError, "active claims"):
            sibling.dispatch(
                actor="test:secondary",
                host_id=self.host_id,
                requested_nodes=[PARALLEL[0]],
            )
        self.assertEqual(self.plane.current_release()["release_id"], release["release_id"])

    def test_new_reconciliation_invalidates_shared_admission_after_wave_settles(self) -> None:
        self._make_eligible([SERIAL])
        release = self.plane.dispatch(
            actor="test:dispatcher",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        generation = dict(self.plane._dispatcher_generation())
        self.assertEqual(generation["status"], "ACTIVE")
        self.plane.reconcile(
            self.plane.current_target_sha(),
            actor="test:reconciler",
            reason="new shared evidence",
        )
        invalidated = dict(self.plane._dispatcher_generation())
        self.assertEqual(invalidated["status"], "INVALIDATED")
        self.assertGreater(invalidated["admission_epoch"], generation["admission_epoch"])
        self.assertEqual(self.plane.current_release()["release_id"], release["release_id"])
        with self.assertRaisesRegex(autopilot.ClaimError, "invalidated"):
            self.plane.assert_start_now(SERIAL)

    def test_external_target_advance_fences_shared_release_consumers(self) -> None:
        self._make_eligible([SERIAL])
        self.plane.dispatch(
            actor="test:dispatcher",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        self.plane.current_target_sha = lambda: "c" * 40  # type: ignore[method-assign]
        with self.assertRaisesRegex(autopilot.ClaimError, "target_sha"):
            self.plane.assert_start_now(SERIAL)

    def test_pre_generation_canonical_release_is_preserved_but_not_live(self) -> None:
        self._make_eligible([SERIAL])
        release = self.plane.dispatch(
            actor="test:dispatcher",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        self.plane.dispatcher_generation_path.unlink()
        self.assertEqual(self.plane.current_release()["release_id"], release["release_id"])
        with self.assertRaisesRegex(autopilot.ClaimError, "generation"):
            self.plane.assert_start_now(SERIAL)
        self.assertTrue(self.plane.current_release_path.is_file())

    def test_shared_generation_pins_repository_target_branch(self) -> None:
        self._make_eligible([SERIAL])
        release = self.plane.dispatch(
            actor="test:dispatcher",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        self.plane._canonical_dispatch_identity = lambda: {  # type: ignore[method-assign]
            "repository": release["repository"],
            "target_branch": "forged/alternate-target",
            "target_sha": release["target_sha"],
            "plan_fingerprint": release["plan_fingerprint"],
        }
        with self.assertRaisesRegex(autopilot.AutopilotError, "canonical identity"):
            self.plane.dispatch(
                actor="test:forged-target",
                host_id=self.host_id,
                requested_nodes=[SERIAL],
            )

    def test_newer_shared_evidence_blocks_stale_worktree_redispatch(self) -> None:
        sibling = self._linked_divergent_plane()
        sibling.control["plan_fingerprint"] = self.plane.expected_plan_fingerprint
        sibling.plan = self.plane.plan
        sibling._nodes = self.plane._nodes
        self._make_eligible([SERIAL], plane=sibling)
        first = self.plane.dispatch(
            actor="test:primary",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )

        newer_reconciliation = "sha256:" + "4" * 64
        newer_observation = self._seed_installed_observation(
            self.plane,
            force=True,
        )
        newer_snapshot = str(newer_observation["snapshot_digest"])
        self.plane._snapshot_digest = lambda: newer_snapshot  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: newer_reconciliation  # type: ignore[method-assign]
        with self.plane.execution_lock("dispatcher-admission.lock"):
            self.plane._invalidate_dispatcher_admission_unlocked(
                actor="test:newer-evidence",
                reason="another worktree installed and reconciled newer evidence",
                github_snapshot_digest=newer_snapshot,
                reconciliation_digest=newer_reconciliation,
            )

        self.assertEqual(self.plane.current_release()["release_id"], first["release_id"])
        with self.assertRaisesRegex(autopilot.AutopilotError, "stale relative"):
            sibling.dispatch(
                actor="test:stale-sibling",
                host_id=self.host_id,
                requested_nodes=[SERIAL],
            )
        replacement = self.plane.dispatch(
            actor="test:current-primary",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        self.assertGreater(replacement["admission_epoch"], first["admission_epoch"])

    def test_unexpired_snapshot_observation_is_single_flight_across_worktrees(self) -> None:
        sibling = self._linked_divergent_plane()
        sibling.control["plan_fingerprint"] = self.plane.expected_plan_fingerprint
        sibling.plan = self.plane.plan
        sibling._nodes = self.plane._nodes
        self._make_eligible([SERIAL], plane=sibling)

        older = self.plane.begin_github_snapshot_observation(actor="test:older")
        newer = sibling.begin_github_snapshot_observation(actor="test:newer")
        self.assertEqual(newer, older)
        source = self.root / "concurrent-snapshot.json"
        source.write_text(
            json.dumps(self._candidate(dict(newer))),
            encoding="utf-8",
        )
        installed = sibling.install_github_snapshot(
            source,
            observation_id=str(newer["observation_id"]),
        )
        self.assertTrue(installed.is_file())
        self.assertEqual(
            sibling._snapshot_observation()["status"],
            "INSTALLED",
        )

    def test_two_processes_join_one_snapshot_token_without_epoch_churn(self) -> None:
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        results = context.Queue()
        processes = [
            context.Process(
                target=_begin_observation_process,
                args=(
                    str(self.root),
                    str(self.host_runtime),
                    str(self.host_base),
                    barrier,
                    results,
                ),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(30)
            self.assertEqual(process.exitcode, 0)
        records = [results.get(timeout=5) for _ in range(2)]
        self.assertEqual(records[0], records[1])
        self.assertEqual(
            self.plane._snapshot_observation()["observation_epoch"],
            records[0][1],
        )

    def test_pending_observation_fences_release_if_invalidation_crashes(self) -> None:
        release = self.plane.dispatch(
            actor="test:before-observation",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        with mock.patch.object(
            self.plane,
            "_invalidate_dispatcher_admission_unlocked",
            side_effect=RuntimeError("simulated crash after observation publication"),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                self.plane.begin_github_snapshot_observation(actor="test:crash")

        observation = self.plane._snapshot_observation()
        self.assertEqual(observation["status"], "PENDING")
        self.assertEqual(
            self.plane._dispatcher_generation()["release_id"],
            release["release_id"],
        )
        with self.assertRaisesRegex(autopilot.ClaimError, "still in progress"):
            self.plane.assert_start_now(SERIAL)
        with self.assertRaisesRegex(autopilot.AutopilotError, "still in progress"):
            self.plane.dispatch(
                actor="test:must-not-republish",
                host_id=self.host_id,
                requested_nodes=[SERIAL],
            )

    def test_snapshot_installs_the_exact_bytes_validated_before_source_mutation(self) -> None:
        observation = self.plane.begin_github_snapshot_observation(actor="test:toctou")
        source = self.root / "mutable-snapshot.json"
        original = self._candidate(dict(observation), source="validated bytes")
        replacement = {
            **original,
            "source": "substituted after validation",
        }
        source.write_text(json.dumps(original), encoding="utf-8")
        atomic_write = autopilot.atomic_write_json

        def mutate_after_installing_marker(path: Path, value: object) -> None:
            atomic_write(path, value)
            if (
                Path(path) == self.plane.snapshot_observation_path
                and isinstance(value, dict)
                and value.get("status") == "INSTALLING"
            ):
                source.write_text(json.dumps(replacement), encoding="utf-8")

        with mock.patch.object(
            autopilot,
            "atomic_write_json",
            side_effect=mutate_after_installing_marker,
        ):
            installed = self.plane.install_github_snapshot(
                source,
                observation_id=str(observation["observation_id"]),
            )
        self.assertEqual(json.loads(installed.read_text(encoding="utf-8")), original)
        self.assertEqual(
            self.plane._dispatcher_generation()["github_snapshot_digest"],
            controller.digest_json(original),
        )

    def test_release_requires_the_exact_installed_observation_record(self) -> None:
        release = self.plane.dispatch(
            actor="test:dispatcher",
            host_id=self.host_id,
            requested_nodes=[SERIAL],
        )
        observation = dict(self.plane._snapshot_observation())
        self.plane.snapshot_observation_path.unlink()
        with self.assertRaisesRegex(autopilot.ClaimError, "observation"):
            self.plane.assert_start_now(SERIAL)

        autopilot.atomic_write_json(self.plane.snapshot_observation_path, observation)
        replacement = self._seed_installed_observation(self.plane, force=True)
        self.assertNotEqual(
            replacement["observation_id"], release["snapshot_observation_id"]
        )
        with self.assertRaisesRegex(autopilot.ClaimError, "observation"):
            self.plane.assert_start_now(SERIAL)

    def test_legacy_active_release_without_observation_binding_is_nonlive(self) -> None:
        release = dict(
            self.plane.dispatch(
                actor="test:dispatcher",
                host_id=self.host_id,
                requested_nodes=[SERIAL],
            )
        )
        for field in (
            "snapshot_observation_id",
            "snapshot_observation_epoch",
            "snapshot_observation_record_id",
        ):
            release.pop(field)
        release.pop("release_id")
        release["release_id"] = autopilot.digest_json(release)
        self.assertTrue(
            any(
                "observation" in issue
                for issue in self.plane._shared_release_shape_issues(release)
            )
        )

    def test_old_snapshot_file_cannot_be_replayed_under_a_new_token(self) -> None:
        older = dict(
            self.plane.begin_github_snapshot_observation(actor="test:older")
        )
        replay = self.root / "old-snapshot.json"
        replay.write_text(json.dumps(self._candidate(older)), encoding="utf-8")
        expired = dict(older)
        expired["expires_at"] = "2000-01-01T00:00:00+00:00"
        autopilot.atomic_write_json(
            self.plane.snapshot_observation_path,
            self.plane._seal_snapshot_observation(expired),
        )
        newer = dict(
            self.plane.begin_github_snapshot_observation(actor="test:newer")
        )
        self.assertNotEqual(older["fetch_ref"], newer["fetch_ref"])
        with self.assertRaisesRegex(autopilot.AutopilotError, "reservation"):
            self.plane.install_github_snapshot(
                replay,
                observation_id=str(newer["observation_id"]),
            )

    def test_compatible_target_advance_installs_through_tracking_ref_cas(self) -> None:
        _base, candidate_sha, observation, source = (
            self._reserve_advanced_candidate()
        )
        installed = self.plane.install_github_snapshot(
            source,
            observation_id=str(observation["observation_id"]),
        )
        self.assertEqual(self.plane._target_tracking_sha(), candidate_sha)
        self.assertEqual(
            json.loads(installed.read_text(encoding="utf-8"))["target_sha"],
            candidate_sha,
        )
        sealed = self.plane._snapshot_observation()
        self.assertEqual(sealed["status"], "INSTALLED")
        self.assertEqual(sealed["target_sha"], candidate_sha)

    def test_tracking_ref_cas_conflict_fails_without_installing_candidate(self) -> None:
        base, candidate_sha, observation, source = self._reserve_advanced_candidate()
        tree = subprocess.run(
            ("git", "-C", str(self.root), "rev-parse", f"{base}^{{tree}}"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        conflict = subprocess.run(
            ("git", "-C", str(self.root), "commit-tree", tree, "-p", base),
            input="compatible competing target\n",
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        target_ref = f"refs/remotes/origin/{self.plane.target_branch}"
        subprocess.run(
            ("git", "-C", str(self.root), "update-ref", target_ref, conflict, base),
            check=True,
        )
        with self.assertRaisesRegex(autopilot.AutopilotError, "compare-and-swap"):
            self.plane.install_github_snapshot(
                source,
                observation_id=str(observation["observation_id"]),
            )
        self.assertEqual(self.plane._target_tracking_sha(), conflict)
        self.assertNotEqual(self.plane._target_tracking_sha(), candidate_sha)
        self.assertFalse(self.plane.github_snapshot_path.is_file())

    def test_snapshot_source_target_advance_supersedes_observation(self) -> None:
        _base, _candidate, observation, source = self._reserve_advanced_candidate()
        self._commit_fixture("target advanced after snapshot source read", marker="drift")
        with self.assertRaisesRegex(
            autopilot.AutopilotError, "fresh token|source branch changed"
        ):
            self.plane.install_github_snapshot(
                source,
                observation_id=str(observation["observation_id"]),
            )
        stale = self.plane._snapshot_observation()
        self.assertEqual(stale["status"], "SUPERSEDED")
        refreshed = self.plane.begin_github_snapshot_observation(
            actor="test:source-drift-refresh"
        )
        self.assertNotEqual(
            refreshed["observation_id"], observation["observation_id"]
        )

    def test_snapshot_target_advance_between_collection_and_cas_is_fenced(self) -> None:
        _base, _candidate, observation, source = self._reserve_advanced_candidate()
        collect = self.plane._collect_snapshot_source_ref_observation
        calls = 0

        def collect_then_advance(value: Mapping[str, object]) -> Mapping[str, object]:
            nonlocal calls
            result = collect(value)
            calls += 1
            if calls == 1:
                self._commit_fixture(
                    "target advanced while snapshot waited for CAS authority",
                    marker="locked-cut-drift",
                )
            return result

        with mock.patch.object(
            self.plane,
            "_collect_snapshot_source_ref_observation",
            side_effect=collect_then_advance,
        ):
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "CAS cut|fresh token"
            ):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        self.assertEqual(calls, 2)
        self.assertEqual(
            self.plane._snapshot_observation()["status"], "SUPERSEDED"
        )

    def test_snapshot_absent_source_branch_creation_supersedes_observation(self) -> None:
        _base, candidate_sha, observation, source = (
            self._reserve_advanced_candidate()
        )
        branch = str(observation["branch_fetches"][0]["branch"])
        subprocess.run(
            ("git", "-C", str(self.root), "update-ref", f"refs/heads/{branch}", candidate_sha),
            check=True,
        )
        with self.assertRaisesRegex(autopilot.AutopilotError, "fresh token"):
            self.plane.install_github_snapshot(
                source,
                observation_id=str(observation["observation_id"]),
            )
        self.assertEqual(
            self.plane._snapshot_observation()["status"], "SUPERSEDED"
        )

    def test_absent_source_branch_created_while_waiting_for_cas_is_fenced(
        self,
    ) -> None:
        _base, candidate_sha, observation, source = (
            self._reserve_advanced_candidate()
        )
        branch = str(observation["branch_fetches"][0]["branch"])
        collect = self.plane._collect_snapshot_source_ref_observation
        calls = 0

        def collect_then_create(value: Mapping[str, object]) -> Mapping[str, object]:
            nonlocal calls
            result = collect(value)
            calls += 1
            if calls == 1:
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(self.root),
                        "update-ref",
                        f"refs/heads/{branch}",
                        candidate_sha,
                    ),
                    check=True,
                )
            return result

        with mock.patch.object(
            self.plane,
            "_collect_snapshot_source_ref_observation",
            side_effect=collect_then_create,
        ):
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "CAS cut|fresh token"
            ):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        self.assertEqual(calls, 2)
        self.assertEqual(
            self.plane._snapshot_observation()["status"], "SUPERSEDED"
        )

    def test_snapshot_present_source_branch_advance_supersedes_observation(self) -> None:
        base, candidate_sha, observation, source = self._reserve_advanced_candidate()
        branch_fetch = observation["branch_fetches"][0]
        branch = str(branch_fetch["branch"])
        subprocess.run(
            ("git", "-C", str(self.root), "update-ref", f"refs/heads/{branch}", base),
            check=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "update-ref",
                str(branch_fetch["fetch_ref"]),
                base,
            ),
            check=True,
        )
        self.plane._publish_remote_evidence_ref(
            str(branch_fetch["fetch_ref"]),
            base,
            label="test snapshot branch evidence",
        )
        source.write_text(
            json.dumps(
                self._candidate(
                    observation,
                    target_sha=candidate_sha,
                    branch_heads={branch: base},
                )
            ),
            encoding="utf-8",
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "update-ref",
                f"refs/heads/{branch}",
                candidate_sha,
                base,
            ),
            check=True,
        )
        with self.assertRaisesRegex(autopilot.AutopilotError, "fresh token"):
            self.plane.install_github_snapshot(
                source,
                observation_id=str(observation["observation_id"]),
            )
        self.assertEqual(
            self.plane._snapshot_observation()["status"], "SUPERSEDED"
        )

    def test_present_source_branch_advances_while_waiting_for_cas_is_fenced(
        self,
    ) -> None:
        base, candidate_sha, observation, source = self._reserve_advanced_candidate()
        branch_fetch = observation["branch_fetches"][0]
        branch = str(branch_fetch["branch"])
        subprocess.run(
            ("git", "-C", str(self.root), "update-ref", f"refs/heads/{branch}", base),
            check=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "update-ref",
                str(branch_fetch["fetch_ref"]),
                base,
            ),
            check=True,
        )
        self.plane._publish_remote_evidence_ref(
            str(branch_fetch["fetch_ref"]),
            base,
            label="test snapshot branch evidence",
        )
        source.write_text(
            json.dumps(
                self._candidate(
                    observation,
                    target_sha=candidate_sha,
                    branch_heads={branch: base},
                )
            ),
            encoding="utf-8",
        )
        collect = self.plane._collect_snapshot_source_ref_observation
        calls = 0

        def collect_then_advance(value: Mapping[str, object]) -> Mapping[str, object]:
            nonlocal calls
            result = collect(value)
            calls += 1
            if calls == 1:
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(self.root),
                        "update-ref",
                        f"refs/heads/{branch}",
                        candidate_sha,
                        base,
                    ),
                    check=True,
                )
            return result

        with mock.patch.object(
            self.plane,
            "_collect_snapshot_source_ref_observation",
            side_effect=collect_then_advance,
        ):
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "CAS cut|fresh token"
            ):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        self.assertEqual(calls, 2)
        self.assertEqual(
            self.plane._snapshot_observation()["status"], "SUPERSEDED"
        )

    def test_unknown_publication_adjudication_proves_lost_success_response(self) -> None:
        unknown, _expected, pinned, heads = self._seed_unknown_publication()
        self.plane._observe_publication_remote = (  # type: ignore[method-assign]
            lambda _sealed: (pinned, heads)
        )
        resolved = self.plane.adjudicate_unknown_publication(
            unknown, actor="test:remote-adjudicator"
        )
        self.assertEqual(resolved["status"], "PUBLISHED")
        self.assertEqual(
            [event["status"] for event in self.plane._publication_journal_events()][-2:],
            ["PUBLISH_UNKNOWN", "PUBLISHED"],
        )

    def test_prepared_publication_fences_claim_and_validation_admission(self) -> None:
        prepared, _expected, _pinned, _heads = self._seed_unknown_publication(
            prepared_only=True
        )
        with self.assertRaisesRegex(
            (autopilot.AutopilotError, autopilot.ClaimError),
            "publication transaction",
        ):
            self.plane.claim_internal(
                SERIAL,
                "test:publication-race-claim",
            )
        with self.assertRaisesRegex(
            (autopilot.AutopilotError, autopilot.ClaimError),
            "publication transaction",
        ):
            self.plane.acquire_global_validation_lease_internal(
                SERIAL,
                "test:publication-race-validation",
            )
        self.assertEqual(
            self.plane._current_publication_resource()[1]["record_id"],
            prepared["record_id"],
        )
        self.assertFalse(self.plane.validation_lease_path.exists())

    def test_unknown_publication_at_predecessor_preserves_historical_unknown(self) -> None:
        unknown, expected, _pinned, heads = self._seed_unknown_publication()
        self.plane._observe_publication_remote = (  # type: ignore[method-assign]
            lambda _sealed: (expected, heads)
        )
        resolved = self.plane.adjudicate_unknown_publication(
            unknown, actor="test:remote-adjudicator"
        )
        self.assertEqual(resolved["status"], "PUBLISH_UNKNOWN")
        self.assertIn("CURRENTLY_AT_PREDECESSOR", resolved["detail"])

    def test_unknown_publication_after_accept_then_revert_is_indistinguishable(self) -> None:
        unknown, expected, _pinned, heads = self._seed_unknown_publication()
        # A provider without an authenticated audit/reflog exposes the same
        # current state whether the push never landed or landed and was reverted.
        self.plane._observe_publication_remote = (  # type: ignore[method-assign]
            lambda _sealed: (expected, heads)
        )
        resolved = self.plane.adjudicate_unknown_publication(
            unknown, actor="test:remote-adjudicator-after-revert"
        )
        self.assertEqual(resolved["status"], "PUBLISH_UNKNOWN")
        self.assertIn("RETRYABLE_UNKNOWN", resolved["detail"])

    def test_unknown_publication_remains_fenced_when_remote_advanced_ambiguously(self) -> None:
        unknown, _expected, _pinned, heads = self._seed_unknown_publication()
        self.plane._observe_publication_remote = (  # type: ignore[method-assign]
            lambda _sealed: ("7" * 40, heads)
        )
        unresolved = self.plane.adjudicate_unknown_publication(
            unknown, actor="test:remote-adjudicator"
        )
        self.assertEqual(unresolved["status"], "PUBLISH_UNKNOWN")
        with self.assertRaisesRegex(
            autopilot.AutopilotError, "PUBLISH_UNKNOWN|publication transaction"
        ):
            self.plane._assert_no_publication_transaction("new dispatcher admission")
        self.assertEqual(
            [event["status"] for event in self.plane._publication_journal_events()][-2:],
            ["PUBLISH_UNKNOWN", "PUBLISH_UNKNOWN"],
        )

    def test_publication_push_uses_exact_remote_compare_and_swap(self) -> None:
        validated, expected, pinned, heads = self._seed_unknown_publication(
            validated_only=True
        )
        pushed: list[tuple[str, ...]] = []

        def git(arguments: object, *, check: bool = True, **_: object):
            del check
            argv = tuple(arguments)
            if argv[0] == "rev-parse":
                return subprocess.CompletedProcess(
                    argv, 0, stdout=pinned + "\n", stderr=""
                )
            if argv[0] == "push":
                pushed.append(argv)
                return subprocess.CompletedProcess(
                    argv,
                    1,
                    stdout="! [rejected] stale info\n",
                    stderr="",
                )
            raise AssertionError(f"unexpected Git command: {argv}")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.plane, "_git", side_effect=git))
            stack.enter_context(
                mock.patch.object(self.plane, "_materialize_remote_evidence_ref")
            )
            stack.enter_context(
                mock.patch.object(self.plane, "_assert_publication_source_policy")
            )
            stack.enter_context(
                mock.patch.object(self.plane, "is_ancestor", return_value=True)
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_observe_publication_remote",
                    return_value=(expected, heads),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane, "_remote_ref_sha", return_value=pinned
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane, "assert_canonical_remote_transport_identity"
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "round_authority_snapshot",
                    return_value={
                        "authority_digest": validated["authority_digest"]
                    },
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_round_authority_digests",
                    return_value=(
                        validated["authority_digest"],
                        validated["authority_baseline_digest"],
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(self.plane, "_release_issues", return_value=())
            )
            resolved = self.plane.publish_pinned_transaction(
                validated,
                pinned_sha=pinned,
                actor="test:publication-racer",
            )
        self.assertEqual(resolved["status"], "PUBLISH_UNKNOWN")
        self.assertEqual(len(pushed), 1)
        self.assertIn(
            (
                "--force-with-lease="
                f"refs/heads/{self.plane.target_branch}:{expected}"
            ),
            pushed[0],
        )
        self.assertIn("historical PUBLISHING intent", resolved["detail"])

    def test_expired_publishing_intent_becomes_unknown_without_new_attempt(self) -> None:
        publishing, expected, _pinned, heads = self._seed_unknown_publication(
            finish_unknown=False
        )
        expired = dict(publishing)
        expired["lease_expires_at"] = "2026-08-14T01:00:00+00:00"
        expired = self.plane._seal_publication_record(expired)
        self.plane._write_publication_pair(
            expired, detail="fixture publication coordinator expired"
        )
        self.plane.clock = lambda: autopilot.parse_time(  # type: ignore[method-assign]
            "2026-08-14T02:00:00+00:00"
        )
        authority_digest = str(expired["authority_digest"])

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "round_authority_snapshot",
                    return_value={"authority_digest": authority_digest},
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_round_authority_digests",
                    return_value=(authority_digest, authority_digest),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_validate_receipt_heads",
                    return_value=list(expired["receipt_heads"]),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_observe_publication_remote",
                    return_value=(expected, heads),
                )
            )
            stack.enter_context(
                mock.patch.object(self.plane, "_release_issues", return_value=())
            )
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "indeterminate remote outcome"
            ):
                self.plane.begin_publication_transaction(
                    release_id=str(expired["release_id"]),
                    round_id=str(expired["round_id"]),
                    expected_target_sha=expected,
                    authority_digest=authority_digest,
                    receipt_heads=heads,
                    coordinator_id=str(expired["coordinator_id"]),
                    actor="test:expired-publishing-recovery",
                )

        current = self.plane._current_publication_resource()[1]
        self.assertEqual(current["status"], "PUBLISH_UNKNOWN")
        self.assertEqual(current["transaction_id"], expired["transaction_id"])
        statuses = [event["status"] for event in self.plane._publication_journal_events()]
        self.assertEqual(statuses[-2:], ["PUBLISHING", "PUBLISH_UNKNOWN"])
        self.assertNotIn("EXPIRED_FENCED", statuses[-2:])

    def test_foreign_expired_publishing_intent_remains_the_global_fence(self) -> None:
        foreign = autopilot.ControlPlane(
            self.root,
            execution_namespace="publication-peer",
            host_runtime_dir=self.host_runtime,
        )
        with foreign.host_lock():
            with foreign.arbiter_lock():
                controller.initialize_execution_namespace(
                    foreign.coordination_dir, foreign.execution_identity
                )
        publishing, expected, _pinned, heads = self._seed_unknown_publication(
            finish_unknown=False,
            plane=foreign,
        )
        expired = dict(publishing)
        expired["lease_expires_at"] = "2026-08-14T01:00:00+00:00"
        expired = foreign._seal_publication_record(expired)
        foreign._write_publication_pair(
            expired, detail="fixture foreign publication coordinator expired"
        )
        self.plane.clock = lambda: autopilot.parse_time(  # type: ignore[method-assign]
            "2026-08-14T02:00:00+00:00"
        )
        foreign_release = foreign.current_release()
        self.plane.current_release = lambda: foreign_release  # type: ignore[method-assign]
        authority_digest = str(expired["authority_digest"])

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "round_authority_snapshot",
                    return_value={"authority_digest": authority_digest},
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_round_authority_digests",
                    return_value=(authority_digest, authority_digest),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_validate_receipt_heads",
                    return_value=list(expired["receipt_heads"]),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    self.plane,
                    "_observe_publication_remote",
                    return_value=(expected, heads),
                )
            )
            stack.enter_context(
                mock.patch.object(self.plane, "_release_issues", return_value=())
            )
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "indeterminate remote outcome"
            ):
                self.plane.begin_publication_transaction(
                    release_id=str(expired["release_id"]),
                    round_id=str(expired["round_id"]),
                    expected_target_sha=expected,
                    authority_digest=authority_digest,
                    receipt_heads=heads,
                    coordinator_id="test:replacement-coordinator",
                    actor="test:foreign-expiry-recovery",
                )

        resource = self.plane._strict_json_file(
            self.plane._publication_resource_path(),
            label="foreign publication target reservation",
        )
        _, fenced = self.plane._validated_publication_resource(
            resource,
            label="foreign publication target reservation",
            allow_foreign=True,
        )
        self.assertEqual(fenced["status"], "PUBLISH_UNKNOWN")
        self.assertEqual(fenced["transaction_id"], expired["transaction_id"])
        self.assertEqual(
            foreign._publication_journal_events()[-1]["status"], "PUBLISHING"
        )

    def test_prepared_publication_resumes_from_an_independent_clone(self) -> None:
        """Clone B publishes only after fetching clone A's immutable txn ref."""

        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["target"]["repository"] = "fixture/portable-publication-authority"
        control["verify_git_objects"] = True
        autopilot.atomic_write_json(control_path, control)
        shutil.copy2(
            BIN / "execution_supervisor.py",
            self.root / ".autopilot" / "bin" / "execution_supervisor.py",
        )
        self._commit_fixture("portable publication runtime")

        bare = self.root.parent / "publication-origin.git"
        clone_a = self.root.parent / "publication-clone-a"
        clone_b = self.root.parent / "publication-clone-b"
        subprocess.run(
            ("git", "init", "--bare", "--quiet", str(bare)),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "-C", str(self.root), "remote", "add", "publication", str(bare)),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "push",
                "--quiet",
                "publication",
                f"HEAD:refs/heads/{control['target']['branch']}",
            ),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "clone", "--quiet", str(bare), str(clone_a)),
            check=True,
            capture_output=True,
        )
        coordination = self.root.parent / "portable-publication-coordination"
        ready_runtime(controller, clone_a, state_dir=coordination)
        plane_a = autopilot.ControlPlane(
            clone_a,
            state_dir=coordination,
            host_runtime_dir=self.host_runtime,
        )
        with plane_a.host_lock():
            controller.bind_host_repository_runtime(
                plane_a.host_runtime_dir,
                repository=str(plane_a.control["target"]["repository"]),
                transport_digest=str(
                    plane_a.repository_identity["transport_digest"]
                ),
                coordination_dir=coordination,
                repo_root=clone_a,
                bound_at=controller.format_time(plane_a.clock()),
            )
            with plane_a.arbiter_lock():
                controller.initialize_execution_namespace(
                    coordination, plane_a.execution_identity
                )
                plane_a.bind_canonical_remote_transport_identity()

        expected = subprocess.run(
            ("git", "-C", str(clone_a), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ("git", "-C", str(clone_a), "config", "user.name", "Txn Fixture"),
            check=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(clone_a),
                "config",
                "user.email",
                "txn@hive-mind.invalid",
            ),
            check=True,
        )
        (clone_a / "validated-pinned.txt").write_text("pinned\n", encoding="utf-8")
        subprocess.run(
            ("git", "-C", str(clone_a), "add", "validated-pinned.txt"),
            check=True,
        )
        subprocess.run(
            ("git", "-C", str(clone_a), "commit", "-m", "validated pinned"),
            check=True,
            capture_output=True,
        )
        pinned = subprocess.run(
            ("git", "-C", str(clone_a), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        receipt_branch = str(plane_a.node(SERIAL)["branch"])
        subprocess.run(
            (
                "git",
                "-C",
                str(clone_a),
                "push",
                "--quiet",
                "origin",
                f"{pinned}:refs/heads/{receipt_branch}",
            ),
            check=True,
            capture_output=True,
        )
        prepared, _, _, _ = self._seed_unknown_publication(
            prepared_only=True,
            expected_sha=expected,
            pinned_sha=pinned,
            receipt_sha=pinned,
            plane=plane_a,
        )
        transaction_ref = str(prepared["transaction_ref"])
        subprocess.run(
            (
                "git",
                "-C",
                str(clone_a),
                "update-ref",
                transaction_ref,
                pinned,
            ),
            check=True,
        )
        source_round_calls = 0

        def crash_after_remote_evidence(_release_id: str) -> Mapping[str, object]:
            nonlocal source_round_calls
            source_round_calls += 1
            if source_round_calls == 2:
                raise RuntimeError("simulated clone A loss after transaction ref")
            return {}

        digest_pair = (
            str(prepared["authority_digest"]),
            str(prepared["authority_baseline_digest"]),
        )
        with mock.patch.object(
            plane_a,
            "round_authority_snapshot",
            side_effect=crash_after_remote_evidence,
        ):
            with mock.patch.object(
                plane_a, "_round_authority_digests", return_value=digest_pair
            ):
                with mock.patch.object(plane_a, "_release_issues", return_value=()):
                    with self.assertRaisesRegex(RuntimeError, "clone A loss"):
                        plane_a.publish_pinned_transaction(
                            prepared,
                            pinned_sha=pinned,
                            actor="test:clone-a-publisher",
                        )
        self.assertEqual(
            plane_a._current_publication_resource()[1]["status"], "PREPARED"
        )
        self.assertEqual(
            subprocess.run(
                ("git", "--git-dir", str(bare), "rev-parse", transaction_ref),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            pinned,
        )
        self.assertEqual(
            subprocess.run(
                (
                    "git",
                    "--git-dir",
                    str(bare),
                    "rev-parse",
                    f"refs/heads/{control['target']['branch']}",
                ),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            expected,
        )
        shutil.rmtree(clone_a)

        subprocess.run(
            ("git", "clone", "--quiet", str(bare), str(clone_b)),
            check=True,
            capture_output=True,
        )
        self.assertNotEqual(
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(clone_b),
                    "rev-parse",
                    "--verify",
                    transaction_ref,
                ),
                check=False,
                capture_output=True,
            ).returncode,
            0,
        )
        plane_b = autopilot.ControlPlane(
            clone_b,
            host_runtime_dir=self.host_runtime,
        )
        self.assertEqual(plane_b.coordination_dir, coordination)
        autopilot._register_current_checkout(plane_b)
        with plane_b.host_lock():
            binding = next(
                item
                for item in controller.host_repository_registry_bindings(
                    plane_b.host_runtime_dir
                )
                if item["repository"]
                == plane_b.control["target"]["repository"]
            )
        self.assertIn(str(clone_b.resolve()), binding["checkout_roots"])
        self.assertFalse(clone_a.exists())
        installed_prepared = plane_b._current_publication_resource()[1]
        plane_b.current_release = lambda: {  # type: ignore[method-assign]
            "release_id": installed_prepared["release_id"],
            "target_sha": expected,
        }
        with plane_b.publication_recovery_guard(
            installed_prepared,
            coordinator_id=str(installed_prepared["coordinator_id"]),
        ):
            self.assertEqual(
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(clone_b),
                        "rev-parse",
                        "--verify",
                        f"{transaction_ref}^{{commit}}",
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                pinned,
            )
        durable_pin = plane_b._current_publication_resource()[1]
        self.assertEqual(durable_pin["status"], "PINNED")
        self.assertEqual(durable_pin["pinned_sha"], pinned)
        with mock.patch.object(
            plane_b, "round_authority_snapshot", return_value={}
        ):
            with mock.patch.object(
                plane_b, "_round_authority_digests", return_value=digest_pair
            ):
                with mock.patch.object(plane_b, "_release_issues", return_value=()):
                    published = plane_b.publish_pinned_transaction(
                        installed_prepared,
                        pinned_sha=pinned,
                        actor="test:clone-b-publisher",
                    )
        self.assertEqual(published["status"], "PUBLISHED")
        self.assertEqual(
            subprocess.run(
                (
                    "git",
                    "--git-dir",
                    str(bare),
                    "rev-parse",
                    f"refs/heads/{control['target']['branch']}",
                ),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            pinned,
        )

    def test_terminal_execution_rejects_publication_before_any_authority_effect(self) -> None:
        def inventory(root: Path) -> dict[str, bytes]:
            if not root.exists():
                return {}
            return {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

        before_execution = inventory(self.plane.execution_dir)
        before_arbiter = inventory(self.plane.arbiter_dir)
        terminal = {"record_id": "sha256:" + "9" * 64}
        with mock.patch.object(
            self.plane, "plan_terminal_fence", return_value=terminal
        ):
            with mock.patch.object(
                self.plane, "round_authority_snapshot"
            ) as round_authority:
                with mock.patch.object(
                    self.plane, "_observe_publication_remote"
                ) as remote_observation:
                    with self.assertRaisesRegex(
                        autopilot.AutopilotError, "terminal fence"
                    ):
                        self.plane.begin_publication_transaction(
                            release_id="sha256:" + "1" * 64,
                            round_id="R1",
                            expected_target_sha="2" * 40,
                            authority_digest="sha256:" + "3" * 64,
                            receipt_heads={SERIAL: "4" * 40},
                            coordinator_id="test:terminal-publication",
                            actor="test:terminal-publication",
                        )
        round_authority.assert_not_called()
        remote_observation.assert_not_called()
        self.assertEqual(inventory(self.plane.execution_dir), before_execution)
        self.assertEqual(inventory(self.plane.arbiter_dir), before_arbiter)

    def test_install_retry_recovers_a_crash_after_tracking_ref_cas(self) -> None:
        _base, candidate_sha, observation, source = self._reserve_advanced_candidate()
        atomic_write = autopilot.atomic_write_json
        crashed = False

        def crash_before_snapshot(path: Path, value: object) -> None:
            nonlocal crashed
            if Path(path) == self.plane.github_snapshot_path and not crashed:
                crashed = True
                raise RuntimeError("simulated crash after target CAS")
            atomic_write(path, value)

        with mock.patch.object(
            autopilot, "atomic_write_json", side_effect=crash_before_snapshot
        ):
            with self.assertRaisesRegex(RuntimeError, "after target CAS"):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        self.assertEqual(self.plane._target_tracking_sha(), candidate_sha)
        self.assertEqual(self.plane._snapshot_observation()["status"], "INSTALLING")
        source.unlink()
        installed = self.plane.install_github_snapshot(
            None,
            observation_id=str(observation["observation_id"]),
        )
        self.assertTrue(installed.is_file())
        self.assertEqual(self.plane._snapshot_observation()["status"], "INSTALLED")

    def test_install_retry_adopts_private_ref_after_other_namespace_overtakes(self) -> None:
        _base, candidate_sha, observation, source = self._reserve_advanced_candidate()
        atomic_write = autopilot.atomic_write_json
        crashed = False

        def crash_before_snapshot(path: Path, value: object) -> None:
            nonlocal crashed
            if Path(path) == self.plane.github_snapshot_path and not crashed:
                crashed = True
                raise RuntimeError("simulated process loss after private target pin")
            atomic_write(path, value)

        with mock.patch.object(
            autopilot, "atomic_write_json", side_effect=crash_before_snapshot
        ):
            with self.assertRaisesRegex(RuntimeError, "private target pin"):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        self.assertEqual(self.plane._execution_target_sha(), candidate_sha)
        self.assertEqual(self.plane._snapshot_observation()["status"], "INSTALLING")

        other = autopilot.ControlPlane(
            self.root,
            execution_namespace="snapshot-overtaker",
            host_runtime_dir=self.host_runtime,
        )
        with other.host_lock():
            with other.arbiter_lock():
                controller.initialize_execution_namespace(
                    other.coordination_dir, other.execution_identity
                )
        other.control["verify_git_objects"] = True
        other_observation = dict(
            other.begin_github_snapshot_observation(actor="test:overtaker")
        )
        descendant = self._commit_fixture(
            "second namespace target advance", marker="namespace-overtake"
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "update-ref",
                str(other_observation["fetch_ref"]),
                descendant,
            ),
            check=True,
        )
        other._publish_remote_evidence_ref(
            str(other_observation["fetch_ref"]),
            descendant,
            label="test overtaking snapshot target evidence",
        )
        other_source = self.root / "overtaking-snapshot.json"
        other_source.write_text(
            json.dumps(self._candidate(other_observation, target_sha=descendant)),
            encoding="utf-8",
        )
        other.install_github_snapshot(
            other_source,
            observation_id=str(other_observation["observation_id"]),
        )
        self.assertEqual(self.plane._target_tracking_sha(), descendant)

        source.unlink()
        installed = self.plane.install_github_snapshot(
            None,
            observation_id=str(observation["observation_id"]),
        )
        self.assertTrue(installed.is_file())
        self.assertEqual(self.plane._snapshot_observation()["status"], "INSTALLED")
        self.assertEqual(self.plane._execution_target_sha(), candidate_sha)
        self.assertEqual(
            self.plane._target_tracking_sha(),
            descendant,
            "an older namespace must never regress the compatible shared target",
        )

    def test_install_retry_uses_immutable_candidate_after_installing_marker_crash(self) -> None:
        base, _candidate_sha, observation, source = self._reserve_advanced_candidate()
        original_target_lookup = self.plane._target_tracking_sha
        crashed = False

        def crash_before_cas() -> str:
            nonlocal crashed
            if not crashed and self.plane._snapshot_observation()["status"] == "INSTALLING":
                crashed = True
                raise RuntimeError("simulated crash after INSTALLING marker")
            return original_target_lookup()

        with mock.patch.object(
            self.plane, "_target_tracking_sha", side_effect=crash_before_cas
        ):
            with self.assertRaisesRegex(RuntimeError, "INSTALLING marker"):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        self.assertEqual(original_target_lookup(), base)
        sealed = self.plane._snapshot_observation()
        artifact = self.plane.execution_dir / str(sealed["candidate_artifact"])
        self.assertTrue(artifact.is_file())
        source.unlink()
        installed = self.plane.install_github_snapshot(
            None,
            observation_id=str(observation["observation_id"]),
        )
        self.assertTrue(installed.is_file())

    def test_install_retry_repairs_crash_after_installed_observation_publication(self) -> None:
        _base, _candidate_sha, observation, source = self._reserve_advanced_candidate()
        with mock.patch.object(
            self.plane,
            "_invalidate_dispatcher_admission_unlocked",
            side_effect=RuntimeError("simulated watermark crash"),
        ):
            with self.assertRaisesRegex(RuntimeError, "watermark crash"):
                self.plane.install_github_snapshot(
                    source,
                    observation_id=str(observation["observation_id"]),
                )
        installed_observation = dict(self.plane._snapshot_observation())
        self.assertEqual(installed_observation["status"], "INSTALLED")
        self.plane.install_github_snapshot(
            source,
            observation_id=str(observation["observation_id"]),
        )
        generation = self.plane._dispatcher_generation()
        self.assertEqual(
            generation["snapshot_observation_record_id"],
            installed_observation["record_id"],
        )

    def test_expired_snapshot_observation_cannot_install(self) -> None:
        observation = dict(
            self.plane.begin_github_snapshot_observation(actor="test:expired")
        )
        observation["expires_at"] = "2000-01-01T00:00:00+00:00"
        observation = self.plane._seal_snapshot_observation(observation)
        autopilot.atomic_write_json(self.plane.snapshot_observation_path, observation)
        source = self.root / "expired-snapshot.json"
        source.write_text(json.dumps(self._candidate(observation)), encoding="utf-8")
        with self.assertRaisesRegex(autopilot.AutopilotError, "expired"):
            self.plane.install_github_snapshot(
                source,
                observation_id=str(observation["observation_id"]),
            )

    def test_expired_observation_archive_is_immutable_and_crash_retryable(self) -> None:
        expired = dict(
            self.plane.begin_github_snapshot_observation(actor="test:will-expire")
        )
        expired["expires_at"] = "2000-01-01T00:00:00+00:00"
        expired = self.plane._seal_snapshot_observation(expired)
        autopilot.atomic_write_json(self.plane.snapshot_observation_path, expired)
        atomic_write = autopilot.atomic_write_json
        crashed = False

        def crash_after_archive(path: Path, value: object) -> None:
            nonlocal crashed
            if Path(path) == self.plane.snapshot_observation_path and not crashed:
                crashed = True
                raise RuntimeError("simulated crash after immutable expiry archive")
            atomic_write(path, value)

        with mock.patch.object(
            autopilot, "atomic_write_json", side_effect=crash_after_archive
        ):
            with self.assertRaisesRegex(RuntimeError, "expiry archive"):
                self.plane.begin_github_snapshot_observation(actor="test:replacer")
        archives = list(self.plane.snapshot_observation_archive_dir.glob("*.json"))
        self.assertEqual(len(archives), 1)
        first_bytes = archives[0].read_bytes()
        replacement = self.plane.begin_github_snapshot_observation(
            actor="test:retry-replacer"
        )
        self.assertEqual(archives[0].read_bytes(), first_bytes)
        self.assertEqual(
            replacement["supersedes_observation_id"], expired["observation_id"]
        )

    def test_tampered_expired_observation_archive_blocks_retry(self) -> None:
        expired = dict(
            self.plane.begin_github_snapshot_observation(actor="test:will-expire")
        )
        expired["expires_at"] = "2000-01-01T00:00:00+00:00"
        expired = self.plane._seal_snapshot_observation(expired)
        autopilot.atomic_write_json(self.plane.snapshot_observation_path, expired)
        with mock.patch.object(
            autopilot,
            "atomic_write_json",
            side_effect=RuntimeError("stop after archive"),
        ):
            with self.assertRaises(RuntimeError):
                self.plane.begin_github_snapshot_observation(actor="test:first")
        archive = next(self.plane.snapshot_observation_archive_dir.glob("*.json"))
        archive.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(autopilot.AutopilotError, "collision differs"):
            self.plane.begin_github_snapshot_observation(actor="test:retry")

    def test_snapshot_candidate_rejects_duplicate_nonfinite_and_unknown_fields(self) -> None:
        for defect in ("duplicate", "nonfinite", "unknown"):
            with self.subTest(defect=defect):
                observation = dict(
                    self.plane.begin_github_snapshot_observation(
                        actor=f"test:strict-{defect}"
                    )
                )
                candidate = self._candidate(observation)
                source = self.root / f"strict-{defect}.json"
                if defect == "duplicate":
                    rendered = json.dumps(candidate)
                    rendered = rendered.replace(
                        '"target_sha":',
                        f'"target_sha":"{candidate["target_sha"]}","target_sha":',
                        1,
                    )
                elif defect == "nonfinite":
                    rendered = json.dumps(candidate).replace(
                        '"observation_epoch":', '"observation_epoch":NaN,"ignored":', 1
                    )
                else:
                    candidate["unknown_authority"] = "forged"
                    candidate.pop("candidate_id")
                    candidate["candidate_id"] = autopilot.digest_json(candidate)
                    rendered = json.dumps(candidate)
                source.write_text(rendered, encoding="utf-8")
                with self.assertRaises(autopilot.AutopilotError):
                    self.plane.install_github_snapshot(
                        source,
                        observation_id=str(observation["observation_id"]),
                    )
                expired = dict(self.plane._snapshot_observation())
                expired["expires_at"] = "2000-01-01T00:00:00+00:00"
                autopilot.atomic_write_json(
                    self.plane.snapshot_observation_path,
                    self.plane._seal_snapshot_observation(expired),
                )

    def test_forged_branch_and_pr_summaries_are_rejected(self) -> None:
        observation = dict(
            self.plane.begin_github_snapshot_observation(actor="test:forged-branch")
        )
        branch_candidate = self._candidate(observation)
        branch_candidate["branch_observations"][0]["present"] = True
        branch_candidate["branch_observations"][0]["sha"] = "f" * 40
        branch_candidate.pop("candidate_id")
        branch_candidate["candidate_id"] = autopilot.digest_json(branch_candidate)
        branch_source = self.root / "forged-branch.json"
        branch_source.write_text(json.dumps(branch_candidate), encoding="utf-8")
        with self.assertRaisesRegex(autopilot.AutopilotError, "branches"):
            self.plane.install_github_snapshot(
                branch_source,
                observation_id=str(observation["observation_id"]),
            )

        expired = dict(self.plane._snapshot_observation())
        expired["expires_at"] = "2000-01-01T00:00:00+00:00"
        autopilot.atomic_write_json(
            self.plane.snapshot_observation_path,
            self.plane._seal_snapshot_observation(expired),
        )
        observation = dict(
            self.plane.begin_github_snapshot_observation(actor="test:forged-pr")
        )
        pr_candidate = self._candidate(observation)
        branch = str(observation["branch_fetches"][0]["branch"])
        raw = {
            "number": 123,
            "state": "OPEN",
            "headRefName": branch,
            "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        }
        pr_candidate["raw_pull_requests"] = [raw]
        pr_candidate["pull_requests"] = [
            {
                "node_id": observation["branch_fetches"][0]["node_id"],
                "number": 123,
                "state": "open",
                "merged": False,
                "ci": "failure",
            }
        ]
        pr_candidate["github_query"] = {
            "offline": False,
            "argv": [
                "gh", "pr", "list", "--repo", observation["repository"],
                "--state", "all", "--limit", "200", "--json",
                "number,state,headRefName,statusCheckRollup",
            ],
            "exit_code": 0,
        }
        pr_candidate.pop("candidate_id")
        pr_candidate["candidate_id"] = autopilot.digest_json(pr_candidate)
        pr_source = self.root / "forged-pr.json"
        pr_source.write_text(json.dumps(pr_candidate), encoding="utf-8")
        with self.assertRaisesRegex(autopilot.AutopilotError, "normalized pull requests"):
            self.plane.install_github_snapshot(
                pr_source,
                observation_id=str(observation["observation_id"]),
            )

    def test_snapshot_script_fetches_only_to_the_reserved_private_ref(self) -> None:
        namespace = "snapshot-handoff"
        snapshot_plane = autopilot.ControlPlane(
            self.root,
            execution_namespace=namespace,
            host_runtime_dir=self.host_runtime,
        )
        with snapshot_plane.host_lock():
            with snapshot_plane.arbiter_lock():
                controller.initialize_execution_namespace(
                    snapshot_plane.coordination_dir,
                    snapshot_plane.execution_identity,
                )
        observation = dict(
            snapshot_plane.begin_github_snapshot_observation(actor="test:script")
        )
        target_sha = str(observation["target_sha"])
        commands: list[tuple[str, ...]] = []
        installed_candidate: dict[str, object] = {}

        def scripted_run(
            args: list[str], *, cwd: Path, check: bool = True
        ) -> subprocess.CompletedProcess[str]:
            command = tuple(str(item) for item in args)
            commands.append(command)
            if "snapshot-observation-begin" in command:
                return subprocess.CompletedProcess(command, 0, json.dumps(observation), "")
            if command[:2] == ("git", "fetch"):
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[:3] == ("git", "rev-parse", "--verify"):
                return subprocess.CompletedProcess(command, 0, target_sha + "\n", "")
            if command[:2] == ("git", "show"):
                return subprocess.CompletedProcess(
                    command,
                    0,
                    (self.root / ".autopilot" / "plan.json").read_text(
                        encoding="utf-8"
                    ),
                    "",
                )
            if command[:3] == ("git", "ls-remote", "--heads"):
                return subprocess.CompletedProcess(
                    command,
                    0,
                    f"{target_sha}\trefs/heads/{snapshot_plane.target_branch}\n",
                    "",
                )
            if "install-github-snapshot" in command:
                snapshot_index = command.index("install-github-snapshot") + 1
                installed_candidate.update(
                    json.loads(Path(command[snapshot_index]).read_text(encoding="utf-8"))
                )
                return subprocess.CompletedProcess(command, 0, "", "")
            self.fail(f"unexpected snapshot command: {command}")

        published: list[tuple[str, str, str]] = []

        def publish_evidence(
            _plane: object,
            reference: str,
            sha: str,
            *,
            label: str,
        ) -> None:
            published.append((reference, sha, label))

        output = io.StringIO()
        with mock.patch.object(github_snapshot, "run", side_effect=scripted_run):
            with mock.patch.object(
                autopilot.ControlPlane,
                "_publish_remote_evidence_ref",
                autospec=True,
                side_effect=publish_evidence,
            ):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "github_snapshot.py",
                        "--repo-root",
                        str(self.root),
                        "--state-dir",
                        str(self.plane.coordination_dir),
                        "--execution-namespace",
                        namespace,
                        "--host-runtime-dir",
                        str(self.host_runtime),
                        "--host-id",
                        self.host_id,
                        "--offline",
                    ],
                ):
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(github_snapshot.main(), 0)
        fetch = next(command for command in commands if command[:2] == ("git", "fetch"))
        self.assertIn("--no-write-fetch-head", fetch)
        self.assertIn(
            f"+refs/heads/{snapshot_plane.target_branch}:{observation['fetch_ref']}",
            fetch,
        )
        self.assertFalse(
            any(
                f"refs/remotes/origin/{snapshot_plane.target_branch}" in part
                for part in fetch
            )
        )
        self.assertEqual(installed_candidate["observation_id"], observation["observation_id"])
        self.assertEqual(installed_candidate["observation_epoch"], observation["observation_epoch"])
        self.assertEqual(installed_candidate["fetch_ref"], observation["fetch_ref"])
        self.assertEqual(
            published,
            [
                (
                    str(observation["fetch_ref"]),
                    target_sha,
                    "snapshot target evidence",
                )
            ],
        )
        handoff = output.getvalue()
        self.assertGreaterEqual(handoff.count(f"--execution-namespace {namespace}"), 2)
        self.assertGreaterEqual(
            handoff.count(f"--state-dir {self.plane.coordination_dir}"), 2
        )
        self.assertGreaterEqual(
            handoff.count(f"--host-runtime-dir {self.host_runtime}"), 2
        )
        self.assertIn(f"--host-id {self.host_id}", handoff)
        self.assertNotIn("HOST_ID", handoff)

    def test_snapshot_script_crash_resumes_from_an_independent_clone(self) -> None:
        """The remote evidence ref, not clone A's object store, owns recovery."""

        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["target"]["repository"] = "fixture/portable-snapshot-authority"
        control["verify_git_objects"] = True
        autopilot.atomic_write_json(control_path, control)
        # execution_supervisor is a new runtime module in this remediation tree
        # and is not yet in the fixture's tracked-file inventory.
        shutil.copy2(
            BIN / "execution_supervisor.py",
            self.root / ".autopilot" / "bin" / "execution_supervisor.py",
        )
        self._commit_fixture("portable snapshot runtime")

        bare = self.root.parent / "portable-origin.git"
        clone_a = self.root.parent / "portable-clone-a"
        clone_b = self.root.parent / "portable-clone-b"
        subprocess.run(
            ("git", "init", "--bare", "--quiet", str(bare)),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "-C", str(self.root), "remote", "add", "portable", str(bare)),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "push",
                "--quiet",
                "portable",
                f"HEAD:refs/heads/{control['target']['branch']}",
            ),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ("git", "clone", "--quiet", str(bare), str(clone_a)),
            check=True,
            capture_output=True,
        )

        coordination = self.root.parent / "portable-snapshot-coordination"
        ready_runtime(controller, clone_a, state_dir=coordination)
        plane_a = autopilot.ControlPlane(
            clone_a,
            state_dir=coordination,
            host_runtime_dir=self.host_runtime,
        )
        with plane_a.host_lock():
            controller.bind_host_repository_runtime(
                plane_a.host_runtime_dir,
                repository=str(plane_a.control["target"]["repository"]),
                transport_digest=str(
                    plane_a.repository_identity["transport_digest"]
                ),
                coordination_dir=coordination,
                repo_root=clone_a,
                bound_at=controller.format_time(plane_a.clock()),
            )
            with plane_a.arbiter_lock():
                controller.initialize_execution_namespace(
                    coordination, plane_a.execution_identity
                )
                plane_a.bind_canonical_remote_transport_identity()

        real_run = github_snapshot.run
        crashed = False

        def crash_install(
            arguments: list[str], *, cwd: Path, check: bool = True
        ) -> subprocess.CompletedProcess[str]:
            nonlocal crashed
            command = tuple(str(item) for item in arguments)
            if "install-github-snapshot" not in command:
                return real_run(list(command), cwd=cwd, check=check)
            source_index = command.index("install-github-snapshot") + 1
            observation_index = command.index("--observation-id") + 1
            real_target = plane_a._target_tracking_sha

            def fail_after_installing_marker() -> str:
                nonlocal crashed
                if (
                    not crashed
                    and plane_a._snapshot_observation().get("status")
                    == "INSTALLING"
                ):
                    crashed = True
                    raise RuntimeError("simulated clone A loss after INSTALLING")
                return real_target()

            with mock.patch.object(
                plane_a,
                "_target_tracking_sha",
                side_effect=fail_after_installing_marker,
            ):
                plane_a.install_github_snapshot(
                    Path(command[source_index]),
                    observation_id=command[observation_index],
                )
            raise AssertionError("snapshot crash point did not fire")

        with mock.patch.object(github_snapshot, "run", side_effect=crash_install):
            with mock.patch.object(
                sys,
                "argv",
                [
                    "github_snapshot.py",
                    "--repo-root",
                    str(clone_a),
                    "--state-dir",
                    str(coordination),
                    "--host-runtime-dir",
                    str(self.host_runtime),
                    "--offline",
                ],
            ):
                with self.assertRaisesRegex(RuntimeError, "clone A loss"):
                    github_snapshot.main()
        observation = dict(plane_a._snapshot_observation())
        self.assertEqual(observation["status"], "INSTALLING")
        target_sha = str(observation["target_sha"])
        remote_ref = str(observation["fetch_ref"])
        self.assertEqual(
            subprocess.run(
                ("git", "--git-dir", str(bare), "rev-parse", remote_ref),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            target_sha,
        )
        shutil.rmtree(clone_a)

        subprocess.run(
            ("git", "clone", "--quiet", str(bare), str(clone_b)),
            check=True,
            capture_output=True,
        )
        absent = subprocess.run(
            ("git", "-C", str(clone_b), "rev-parse", "--verify", remote_ref),
            check=False,
            capture_output=True,
        )
        self.assertNotEqual(absent.returncode, 0)
        plane_b = autopilot.ControlPlane(
            clone_b,
            host_runtime_dir=self.host_runtime,
        )
        self.assertEqual(plane_b.coordination_dir, coordination)
        autopilot._register_current_checkout(plane_b)
        with plane_b.host_lock():
            binding = next(
                item
                for item in controller.host_repository_registry_bindings(
                    plane_b.host_runtime_dir
                )
                if item["repository"]
                == plane_b.control["target"]["repository"]
            )
        self.assertIn(str(clone_b.resolve()), binding["checkout_roots"])
        self.assertFalse(clone_a.exists())
        installed = plane_b.install_github_snapshot(
            None,
            observation_id=str(observation["observation_id"]),
        )
        self.assertTrue(installed.is_file())
        self.assertEqual(plane_b._snapshot_observation()["status"], "INSTALLED")
        self.assertEqual(
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(clone_b),
                    "rev-parse",
                    "--verify",
                    f"{remote_ref}^{{commit}}",
                ),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            target_sha,
        )

    def test_dispatch_frontier_is_the_round_driver_frontier_and_rejects_subsets(self) -> None:
        initial_status = {"nodes": []}
        expected = autopilot.select_round(
            self.plane,
            initial_status,
            max_sessions=TEST_HOST_MAX_TOTAL_SESSIONS,
            plan_path=self.plane.ap_root / "plan.json",
        )
        self.assertIsNotNone(expected)
        frontier = list(expected.nodes)
        self._make_eligible(frontier)
        self.plane._compiled_frontier = (  # type: ignore[method-assign]
            autopilot.ControlPlane._compiled_frontier.__get__(
                self.plane, autopilot.ControlPlane
            )
        )
        release = self.plane.dispatch(
            actor="test:canonical-frontier", host_id=self.host_id
        )
        self.assertEqual(release["released_wave"], frontier)
        if len(frontier) > 1:
            with self.assertRaisesRegex(
                autopilot.AutopilotError, "exact authenticated compiled frontier"
            ):
                self.plane.dispatch(
                    actor="test:subset",
                    host_id=self.host_id,
                    requested_nodes=frontier[:-1],
                )

    def test_capacity_change_keeps_only_pending_members_of_compiled_barrier(
        self,
    ) -> None:
        completed = list(PARALLEL[:2])
        pending = PARALLEL[2]
        status = {
            "nodes": [
                {"node_id": node_id, "state": "COMPLETE"}
                for node_id in completed
            ]
            + [{"node_id": pending, "state": "READY"}]
        }
        compiled_at_two = mock.Mock(nodes=(pending,))
        compiled_at_three = mock.Mock(nodes=tuple([*completed, pending]))

        def compile_for_capacity(
            _plane: object,
            _status: Mapping[str, object],
            *,
            max_sessions: int,
            plan_path: Path,
        ) -> object:
            self.assertEqual(plan_path, self.plane.ap_root / "plan.json")
            return compiled_at_two if max_sessions == 2 else compiled_at_three

        with mock.patch.object(
            autopilot, "select_round", side_effect=compile_for_capacity
        ) as select:
            before_growth = self.plane._compiled_frontier(status, max_sessions=2)
            after_growth = self.plane._compiled_frontier(status, max_sessions=3)
        self.assertEqual(before_growth, [pending])
        self.assertEqual(after_growth, [pending])
        self.assertEqual(select.call_count, 2)
        self.assertEqual(
            [call.kwargs["max_sessions"] for call in select.call_args_list],
            [2, 3],
        )

    def test_malformed_dag_fails_before_release_or_host_reservation_effects(self) -> None:
        original_plan = json.loads(
            (self.root / ".autopilot" / "plan.json").read_text(encoding="utf-8")
        )

        def inventory(root: Path) -> dict[str, bytes]:
            if not root.exists():
                return {}
            return {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

        for case in ("missing-dependency", "duplicate-node"):
            with self.subTest(case=case):
                plan = json.loads(json.dumps(original_plan))
                if case == "missing-dependency":
                    node = next(item for item in plan["nodes"] if item["id"] == SERIAL)
                    node["dependencies"] = [*node["dependencies"], "MISSING-NODE"]
                    expected_error = "unknown dependencies|MISSING-NODE"
                else:
                    plan["nodes"].append(dict(plan["nodes"][0]))
                    expected_error = "duplicate"
                material = dict(plan)
                material.pop("plan_fingerprint", None)
                fingerprint = autopilot.digest_json(material)
                plan["plan_fingerprint"] = fingerprint
                autopilot.atomic_write_json(
                    self.root / ".autopilot" / "plan.json", plan
                )
                control = json.loads(
                    (self.root / ".autopilot" / "control-plane.json").read_text(
                        encoding="utf-8"
                    )
                )
                control["plan_fingerprint"] = fingerprint
                autopilot.atomic_write_json(
                    self.root / ".autopilot" / "control-plane.json", control
                )
                plane = autopilot.ControlPlane(
                    self.root,
                    execution_namespace=f"malformed-{case}",
                    host_runtime_dir=self.host_runtime,
                )
                with plane.host_lock():
                    with plane.arbiter_lock():
                        controller.initialize_execution_namespace(
                            plane.coordination_dir, plane.execution_identity
                        )
                self._make_eligible([SERIAL], plane=plane)
                plane._compiled_frontier = (  # type: ignore[method-assign]
                    autopilot.ControlPlane._compiled_frontier.__get__(
                        plane, autopilot.ControlPlane
                    )
                )
                before_execution = inventory(plane.execution_dir)
                before_host = inventory(plane.host_runtime_dir)
                with self.assertRaisesRegex(Exception, expected_error):
                    plane.dispatch(
                        actor=f"test:{case}",
                        host_id=self.host_id,
                    )
                self.assertEqual(inventory(plane.execution_dir), before_execution)
                self.assertEqual(inventory(plane.host_runtime_dir), before_host)

        autopilot.atomic_write_json(
            self.root / ".autopilot" / "plan.json", original_plan
        )
        original_control = json.loads(
            (self.root / ".autopilot" / "control-plane.json").read_text(
                encoding="utf-8"
            )
        )
        original_control["plan_fingerprint"] = original_plan["plan_fingerprint"]
        autopilot.atomic_write_json(
            self.root / ".autopilot" / "control-plane.json", original_control
        )
    def test_dispatch_plan_is_only_an_equivalent_canonical_assertion(self) -> None:
        alternate = self.root / "alternate-plan.json"
        alternate.write_text(
            (self.plane.ap_root / "plan.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.plane.authenticate_dispatch_plan_assertion(alternate)
        changed = json.loads(alternate.read_text(encoding="utf-8"))
        changed["nodes"][0]["objective"] = "ungoverned alternate objective"
        alternate.write_text(json.dumps(changed), encoding="utf-8")
        with mock.patch.object(self.plane, "dispatch") as dispatch:
            with mock.patch.object(autopilot, "ControlPlane", return_value=self.plane):
                with contextlib.redirect_stderr(io.StringIO()):
                    exit_code = autopilot.main(
                        [
                            "--repo-root",
                            str(self.root),
                            "dispatch",
                            "--actor",
                            "test:custom-plan",
                            "--host-id",
                            self.host_id,
                            "--plan",
                            str(alternate),
                        ]
                    )
        self.assertEqual(exit_code, 2)
        dispatch.assert_not_called()

    def test_target_dispatch_identity_rejects_ambiguous_authority_corpus(self) -> None:
        control = json.loads(
            (self.plane.ap_root / "control-plane.json").read_text(encoding="utf-8")
        )
        plan = json.loads(
            (self.plane.ap_root / "plan.json").read_text(encoding="utf-8")
        )

        def canonical(value: object) -> str:
            return json.dumps(value, ensure_ascii=False, indent=2) + "\n"

        valid_control = canonical(control)
        valid_plan = canonical(plan)
        unknown_control = dict(control)
        unknown_control["caller_authority"] = "injected"
        mismatched_plan = dict(plan)
        mismatched_plan["plan_fingerprint"] = "sha256:" + "f" * 64
        corpus = {
            "duplicate-key": (
                valid_control.replace(
                    "{\n", '{\n  "schema_version": 1,\n', 1
                ),
                valid_plan,
            ),
            "nonfinite-number": (
                valid_control.replace(
                    '"default_claim_lease_minutes": 90',
                    '"default_claim_lease_minutes": NaN',
                    1,
                ),
                valid_plan,
            ),
            "unknown-authority-field": (canonical(unknown_control), valid_plan),
            "noncanonical-encoding": (
                json.dumps(control, ensure_ascii=False) + "\n",
                valid_plan,
            ),
            "embedded-fingerprint-mismatch": (
                valid_control,
                canonical(mismatched_plan),
            ),
        }
        target_sha = "a" * 40

        for defect, (control_text, plan_text) in corpus.items():
            with self.subTest(defect=defect):
                documents = {
                    "control-plane.json": control_text,
                    "plan.json": plan_text,
                }

                def fake_git(arguments: object, *, check: bool = True, **_: object):
                    del check
                    name = str(tuple(arguments)[1]).rsplit("/", 1)[-1]
                    return subprocess.CompletedProcess(
                        arguments,
                        0,
                        stdout=documents[name],
                        stderr="",
                    )

                with mock.patch.object(
                    type(self.plane),
                    "verify_git_objects",
                    new_callable=mock.PropertyMock,
                    return_value=True,
                ):
                    with mock.patch.object(
                        self.plane, "git_object_exists", return_value=True
                    ):
                        with mock.patch.object(
                            self.plane, "_git", side_effect=fake_git
                        ):
                            with self.assertRaises(autopilot.AutopilotError):
                                self.plane._dispatch_identity_at(target_sha)

    def test_run_round_cli_returns_nonzero_for_non_success_dispositions(self) -> None:
        release_id = "sha256:" + "e" * 64
        for disposition, expected_exit in (
            ("ROUND_COMPLETE", 0),
            ("PLAN_QUIESCENT", 1),
            ("ROUND_VALIDATED_LOCAL", 0),
            ("CONTROLLER_QUIESCENT_CANDIDATE", 1),
            ("VALIDATION_FAILED", 1),
            ("RECOVERY_REQUIRED", 1),
            ("PENDING", 1),
            ("ACTIVE", 1),
        ):
            with self.subTest(disposition=disposition):
                with mock.patch.object(
                    autopilot, "ControlPlane", return_value=self.plane
                ):
                    with mock.patch.object(
                        autopilot,
                        "drive_round",
                        return_value={"disposition": disposition},
                    ):
                        with contextlib.redirect_stdout(io.StringIO()):
                            exit_code = autopilot.main(
                                [
                                    "--repo-root",
                                    str(self.root),
                                    "run-round",
                                    "--release-id",
                                    release_id,
                                ]
                            )
                self.assertEqual(exit_code, expected_exit)


if __name__ == "__main__":
    unittest.main()
