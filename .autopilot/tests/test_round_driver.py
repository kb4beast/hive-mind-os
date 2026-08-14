from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

BIN = Path(__file__).resolve().parents[1] / "bin"
# round_driver imports its siblings by name, exactly as the CLI does.
sys.path.insert(0, str(BIN))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("driver_controller", "controller.py")
attended = _load("driver_attended_host", "attended_host.py")
driver = _load("driver_module", "round_driver.py")

NODE = "MISSION-400"
BRANCH = "autopilot/mission-400"
RELEASE_ID = "sha256:" + "a" * 64


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root)) + arguments,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(arguments)} failed ({completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


class RoundDriverTests(unittest.TestCase):
    """Integration order, gate discipline, and triage authority, as tested code."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "work"
        self.origin = base / "origin.git"
        self.root.mkdir()
        copy_autopilot_fixture(
            Path(__file__).resolve().parents[1], self.root / ".autopilot"
        )
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_bytes(
            (
                json.dumps(
                    control,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        )
        self.target = control["target"]["branch"]
        subprocess.run(
            (
                "git",
                "init",
                "--bare",
                f"--initial-branch={self.target}",
                str(self.origin),
            ),
            check=True,
            capture_output=True,
        )
        git(self.root, "init", f"--initial-branch={self.target}")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@hive-mind.invalid")
        (self.root / "shared.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "remote", "set-url", "origin", str(self.origin))
        git(self.root, "push", "-u", "origin", self.target)
        self.base = git(self.root, "rev-parse", "HEAD")
        self.plane = controller.ControlPlane(self.root)
        ready_runtime(controller, self.root)
        # These integration-order fixtures exercise the receipt-commit boundary. The
        # controller's exhaustive receipt/claim tests construct the full production
        # payload; keep that independent verifier callable here while supplying a
        # minimal canonical payload for Git transaction tests.
        self.plane.validate_receipt = lambda *_a, **_k: ()  # type: ignore[method-assign]
        self.plane._claim_provenance_issues = lambda *_a, **_k: ()  # type: ignore[method-assign]
        self.report = driver.RoundReport()
        self.round = driver.Round(
            round_id="R-TEST",
            level=6,
            nodes=(NODE,),
            parallel_safe=False,
            reason="fixture round",
            command="dispatch",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def authority_snapshot(
        self,
        *,
        release: dict[str, object] | None = None,
        status: dict[str, object] | None = None,
        **overrides: object,
    ) -> dict[str, object]:
        sealed_release: dict[str, object] = {
            "release_id": RELEASE_ID,
            "admission_epoch": 1,
            "execution_id": self.plane.execution_id,
            "execution_namespace": self.plane.execution_namespace,
            "released_wave": [NODE],
            "session_cap": driver.DEFAULT_MAX_SESSIONS,
            "host_id": "host:test",
            "capacity_generation": "sha256:" + "6" * 64,
            "capacity_epoch": 1,
            "capacity_record_id": "sha256:" + "7" * 64,
            "capacity_max_total_sessions": driver.DEFAULT_MAX_SESSIONS,
            "capacity_validation_slots": 1,
            "target_branch": self.target,
            "target_sha": self.base,
        }
        if release:
            sealed_release.update(release)
        sealed_status: dict[str, object] = {
            "nodes": [],
            "complete": False,
            "reconciliation_required": False,
        }
        if status:
            sealed_status.update(status)
        snapshot: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-round-authority-snapshot-v1",
            "execution_id": self.plane.execution_id,
            "execution_namespace": self.plane.execution_namespace,
            "release_id": RELEASE_ID,
            "admission_epoch": sealed_release["admission_epoch"],
            "release": sealed_release,
            "active_write_launch_reservations": [],
            "active_host_reservations": [],
            "execution_global_host_reservations": [],
            "active_claims": [],
            "active_validation_lease": None,
            "publication_transaction_fence": None,
            "active_publication_count": 0,
            "terminal_launch_bindings": [],
            "terminal_sidecar_bindings": [],
            "conflicting_global_reservations": [],
            "reconciliation_obligations": [],
            "host_capacity_generations": {
                str(sealed_release["host_id"]): {
                    "capacity_generation": sealed_release["capacity_generation"],
                    "capacity_epoch": sealed_release["capacity_epoch"],
                    "record_id": sealed_release["capacity_record_id"],
                    "max_total_sessions": sealed_release["capacity_max_total_sessions"],
                    "validation_slots": sealed_release["capacity_validation_slots"],
                }
            },
            "release_capacity_issuance_record": {
                "host_id": sealed_release["host_id"],
                "capacity_generation": sealed_release["capacity_generation"],
                "capacity_epoch": sealed_release["capacity_epoch"],
                "record_id": sealed_release["capacity_record_id"],
                "max_total_sessions": sealed_release["capacity_max_total_sessions"],
                "validation_slots": sealed_release["capacity_validation_slots"],
            },
            "status": sealed_status,
            "authority_digest": "sha256:" + "b" * 64,
            "observed_at": "2030-01-01T00:00:00Z",
        }
        snapshot.update(overrides)
        return snapshot

    def install_round_snapshot(self, snapshot: dict[str, object]) -> None:
        @contextmanager
        def round_guard(*, release_id: str):
            self.assertEqual(release_id, RELEASE_ID)
            yield snapshot

        self.plane.round_admission_guard = round_guard  # type: ignore[attr-defined]

    @staticmethod
    def publication_token() -> dict[str, object]:
        return {
            "transaction_id": "sha256:" + "c" * 64,
            "transaction_lease_id": "sha256:" + "d" * 64,
            "expected_target_sha": "0" * 40,
            "transaction_ref": "refs/hive-mind/test/transaction",
            "status": "PREPARED",
            "pinned_sha": None,
        }

    @contextmanager
    def public_pipeline(
        self,
        *,
        validation_passes: bool = True,
        publication_outcome: str = "PUBLISHED",
    ):
        token = self.publication_token()
        pinned = "f" * 40
        workspace = mock.Mock(path=self.root)

        completion_id = "sha256:" + "8" * 64
        broker_result = {"completion_id": completion_id}
        broker_side_effect = (
            None
            if validation_passes
            else driver.RoundValidationError(
                [RuntimeError("fixed repository validation failed")]
            )
        )

        def terminal(_transaction, **kwargs):
            return {**token, **kwargs, "outcome": kwargs["outcome"]}

        published = {
            **token,
            "status": "PUBLISHED",
            "pinned_sha": pinned,
            "outcome": publication_outcome,
            "detail": f"publication {publication_outcome.lower()}",
        }
        with (
            mock.patch.object(
                driver,
                "select_round",
                side_effect=AssertionError(
                    "public round must not recompile a local plan"
                ),
            ),
            mock.patch.object(driver, "receipt_head", return_value="e" * 40),
            mock.patch.object(driver, "triage_round"),
            mock.patch.object(
                self.plane,
                "begin_publication_transaction",
                create=True,
                return_value=token,
            ) as begin,
            mock.patch.object(
                self.plane,
                "renew_publication_transaction",
                create=True,
                side_effect=lambda transaction, **_kwargs: transaction,
            ),
            mock.patch.object(
                self.plane,
                "pin_publication_transaction",
                create=True,
                side_effect=lambda transaction, **kwargs: {
                    **transaction,
                    "status": "PINNED",
                    "pinned_sha": kwargs["pinned_sha"],
                },
            ) as pin,
            mock.patch.object(
                self.plane,
                "seal_validated_publication_transaction",
                create=True,
                side_effect=lambda transaction, **kwargs: (
                    {
                        **transaction,
                        "status": "VALIDATED",
                    }
                    if kwargs.get("validation_evidence")
                    == {"broker_completion_id": completion_id}
                    else (_ for _ in ()).throw(
                        AssertionError("seal did not receive exact broker evidence")
                    )
                ),
            ) as seal,
            mock.patch.object(
                self.plane,
                "run_publication_validation_broker",
                create=True,
                return_value=broker_result,
                side_effect=broker_side_effect,
            ) as gate,
            mock.patch.object(
                self.plane,
                "finish_publication_transaction",
                create=True,
                side_effect=terminal,
            ) as finish,
            mock.patch.object(
                self.plane,
                "publish_pinned_transaction",
                create=True,
                return_value=published,
            ) as publish,
            mock.patch.object(driver, "PrivateRoundWorkspace") as private,
            mock.patch.object(
                driver,
                "integrate_private_round",
                return_value=pinned,
            ),
            mock.patch.object(driver, "assert_private_validation_state"),
        ):
            private.return_value.__enter__.return_value = workspace
            yield {
                "begin": begin,
                "pin": pin,
                "seal": seal,
                "finish": finish,
                "publish": publish,
                "gate": gate,
                "private": private,
                "pinned": pinned,
            }

    def seal_candidate(self, candidate: str) -> str:
        tree = git(self.root, "rev-parse", f"{candidate}^{{tree}}")
        receipt = {
            "base_commit": self.base,
            "branch": BRANCH,
            "final_commit": candidate,
            "final_tree": tree,
            "node_id": NODE,
        }
        message = (
            driver.RECEIPT_COMMIT_MARKER
            + "\n"
            + json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        )
        return subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "commit-tree",
                tree,
                "-p",
                candidate,
                "-F",
                "-",
            ),
            check=True,
            capture_output=True,
            text=True,
            input=message,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Receipt",
                "GIT_AUTHOR_EMAIL": attended.RECEIPT_IDENTITY,
                "GIT_COMMITTER_NAME": "Receipt",
                "GIT_COMMITTER_EMAIL": attended.RECEIPT_IDENTITY,
            },
        ).stdout.strip()

    def publish_node_branch(self, *, sealed: bool, content: str = "node work\n") -> str:
        """Build a node branch, optionally sealed by a receipt-authored head."""

        git(self.root, "checkout", "-q", "-b", "tmp-node", self.base)
        (self.root / "node.txt").write_text(content, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "node candidate")
        head = git(self.root, "rev-parse", "HEAD")
        if sealed:
            head = self.seal_candidate(head)
        git(self.root, "push", "--force", "origin", f"{head}:refs/heads/{BRANCH}")
        git(self.root, "checkout", "-q", self.target)
        return head

    def test_private_sealed_integration_is_idempotent(self) -> None:
        head = self.publish_node_branch(sealed=True)
        transaction = self.private_transaction()
        with driver.PrivateRoundWorkspace(self.plane, transaction) as workspace:
            first = driver.integrate_private_round(
                self.plane,
                workspace,
                self.round,
                self.report,
                sealed_heads={NODE: head},
            )
        self.assertEqual(self.report.steps[-1].outcome, "INTEGRATED")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.base)
        transaction["status"] = "PINNED"
        transaction["pinned_sha"] = first
        again = driver.RoundReport()
        with driver.PrivateRoundWorkspace(self.plane, transaction) as workspace:
            second = driver.integrate_private_round(
                self.plane,
                workspace,
                self.round,
                again,
                sealed_heads={NODE: head},
            )
        self.assertEqual(second, first)
        self.assertEqual(again.steps[-1].outcome, "ALREADY")

    def test_private_workspace_rejects_an_unsealed_descendant_ref(self) -> None:
        transaction = self.private_transaction()
        tree = git(self.root, "rev-parse", f"{self.base}^{{tree}}")
        unauthorized = git(
            self.root,
            "commit-tree",
            tree,
            "-p",
            self.base,
            "-m",
            "unauthorized private-ref descendant",
        )
        git(
            self.root,
            "update-ref",
            str(transaction["transaction_ref"]),
            unauthorized,
        )

        with self.assertRaisesRegex(
            driver.RoundDriverError, "differs from its exact sealed state"
        ):
            with driver.PrivateRoundWorkspace(self.plane, transaction):
                self.fail("poisoned transaction ref must not create a workspace")

    def test_unsealed_branch_is_not_receipt_authority(self) -> None:
        self.publish_node_branch(sealed=False)
        self.assertIsNone(driver.receipt_head(self.plane, NODE))

    def test_receipt_identity_without_canonical_payload_is_not_authority(self) -> None:
        git(self.root, "checkout", "-q", "-b", "tmp-node", self.base)
        git(self.root, "commit", "--allow-empty", "-m", "candidate")
        candidate = git(self.root, "rev-parse", "HEAD")
        tree = git(self.root, "rev-parse", "HEAD^{tree}")
        forged = subprocess.run(
            (
                "git",
                "-C",
                str(self.root),
                "commit-tree",
                tree,
                "-p",
                candidate,
                "-m",
                "receipt",
            ),
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Receipt",
                "GIT_AUTHOR_EMAIL": attended.RECEIPT_IDENTITY,
                "GIT_COMMITTER_NAME": "Receipt",
                "GIT_COMMITTER_EMAIL": attended.RECEIPT_IDENTITY,
            },
        ).stdout.strip()
        git(self.root, "push", "--force", "origin", f"{forged}:refs/heads/{BRANCH}")
        git(self.root, "checkout", "-q", self.target)
        self.assertIsNone(driver.receipt_head(self.plane, NODE))

    def test_receipt_rejected_when_controller_or_claim_provenance_rejects_it(
        self,
    ) -> None:
        self.publish_node_branch(sealed=True)
        self.plane.validate_receipt = lambda *_a, **_k: ("receipt invalid",)  # type: ignore[method-assign]
        self.assertIsNone(driver.receipt_head(self.plane, NODE))
        self.plane.validate_receipt = lambda *_a, **_k: ()  # type: ignore[method-assign]
        self.plane._claim_provenance_issues = lambda *_a, **_k: ("claim invalid",)  # type: ignore[method-assign]
        self.assertIsNone(driver.receipt_head(self.plane, NODE))

    def test_noncanonical_or_duplicate_receipt_json_is_rejected(self) -> None:
        self.assertIsNone(
            driver._parse_canonical_receipt_message(
                driver.RECEIPT_COMMIT_MARKER + '\n{"node_id":"A", "node_id":"A"}'
            )
        )
        self.assertIsNone(
            driver._parse_canonical_receipt_message(
                driver.RECEIPT_COMMIT_MARKER + '\n{"node_id":NaN}'
            )
        )

    def test_private_conflict_preserves_the_ambient_target(self) -> None:
        git(self.root, "checkout", "-q", "-b", "tmp-node", self.base)
        (self.root / "shared.txt").write_text("node side\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "node candidate")
        head = self.seal_candidate(git(self.root, "rev-parse", "HEAD"))
        git(self.root, "push", "--force", "origin", f"{head}:refs/heads/{BRANCH}")
        git(self.root, "checkout", "-q", self.target)
        (self.root / "shared.txt").write_text("target side\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "target advance")
        transaction = self.private_transaction()
        transaction["expected_target_sha"] = git(self.root, "rev-parse", "HEAD")
        with self.assertRaisesRegex(driver.RoundDriverError, "integration conflict"):
            with driver.PrivateRoundWorkspace(self.plane, transaction) as workspace:
                driver.integrate_private_round(
                    self.plane,
                    workspace,
                    self.round,
                    self.report,
                    sealed_heads={NODE: head},
                )
        self.assertEqual(self.report.steps[-1].outcome, "CONFLICT")
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def private_transaction(self) -> dict[str, object]:
        transaction_id = "sha256:" + "b" * 64
        transaction_ref = "refs/hive-mind-autopilot/transactions/fixture/" + "b" * 64
        self.plane.execution_transaction_ref = (  # type: ignore[attr-defined]
            lambda value: transaction_ref if value == transaction_id else None
        )
        return {
            "transaction_id": transaction_id,
            "transaction_ref": transaction_ref,
            "expected_target_sha": self.base,
            "status": "PREPARED",
            "pinned_sha": None,
        }

    def test_private_round_integration_never_advances_ambient_target_checkout(
        self,
    ) -> None:
        head = self.publish_node_branch(sealed=True)
        transaction = self.private_transaction()
        with driver.PrivateRoundWorkspace(self.plane, transaction) as workspace:
            pinned = driver.integrate_private_round(
                self.plane,
                workspace,
                self.round,
                self.report,
                sealed_heads={NODE: head},
            )
            driver.assert_private_validation_state(
                self.plane,
                workspace,
                pinned_sha=pinned,
                sealed_heads={NODE: head},
            )
            private_path = workspace.path
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.base)
        self.assertEqual(self.plane.remote_branch_sha(self.target), self.base)
        self.assertEqual(
            git(self.root, "rev-parse", str(transaction["transaction_ref"])),
            pinned,
        )
        self.assertIsNotNone(private_path)
        self.assertFalse(private_path.exists())

    def test_fixed_validation_rejects_checkout_or_untracked_mutation(self) -> None:
        head = self.publish_node_branch(sealed=True)
        transaction = self.private_transaction()
        with driver.PrivateRoundWorkspace(self.plane, transaction) as workspace:
            pinned = driver.integrate_private_round(
                self.plane,
                workspace,
                self.round,
                self.report,
                sealed_heads={NODE: head},
            )
            assert workspace.path is not None
            (workspace.path / "validation-created.txt").write_text(
                "unexpected\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                driver.RoundDriverError, "changed the pinned transaction"
            ):
                driver.assert_private_validation_state(
                    self.plane,
                    workspace,
                    pinned_sha=pinned,
                    sealed_heads={NODE: head},
                )
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.base)

    def test_validation_releases_its_lease_even_when_tests_fail(self) -> None:
        def failing() -> tuple[bool, str]:
            return False, "FAILED (failures=1)"

        driver.validate_round(
            self.plane, self.round, self.report, owner="test:owner", runner=failing
        )
        self.assertEqual(self.report.steps[-1].outcome, "FAILED")
        self.assertIsNone(self.plane.status().get("active_validation_lease"))

    def test_validation_releases_its_lease_when_the_runner_raises(self) -> None:
        def exploding() -> tuple[bool, str]:
            raise RuntimeError("runner died")

        with self.assertRaises(driver.RoundValidationError) as caught:
            driver.validate_round(
                self.plane,
                self.round,
                self.report,
                owner="test:owner",
                runner=exploding,
            )
        self.assertTrue(
            any(isinstance(error, RuntimeError) for error in caught.exception.failures)
        )
        self.assertIsNone(self.plane.status().get("active_validation_lease"))

    def test_validation_preserves_runner_and_release_failures_together(self) -> None:
        original_release = self.plane.release_global_validation_lease_internal

        def failed_release(*args, **kwargs):
            original_release(*args, **kwargs)
            raise OSError("release receipt write failed")

        self.plane.release_global_validation_lease_internal = failed_release  # type: ignore[method-assign]

        def exploding() -> tuple[bool, str]:
            raise RuntimeError("runner died")

        with self.assertRaises(driver.RoundValidationError) as caught:
            driver.validate_round(
                self.plane,
                self.round,
                self.report,
                owner="test:owner",
                runner=exploding,
            )
        self.assertEqual(
            {type(error) for error in caught.exception.failures},
            {RuntimeError, OSError},
        )

    def test_long_validation_renews_exact_lease_before_original_expiry(self) -> None:
        now = [controller.parse_time("2030-01-01T00:00:00Z")]
        self.plane.clock = lambda: now[0]
        renewed = threading.Event()
        receipts: list[dict[str, object]] = []
        original = self.plane.renew_global_validation_lease_internal

        def observe_renewal(*args, **kwargs):
            result = dict(original(*args, **kwargs))
            receipts.append(result)
            renewed.set()
            return result

        self.plane.renew_global_validation_lease_internal = observe_renewal  # type: ignore[method-assign]

        def long_runner() -> tuple[bool, str]:
            now[0] += timedelta(seconds=30)
            self.assertTrue(renewed.wait(2), "validation lease was not renewed")
            now[0] += timedelta(seconds=45)
            return True, "passed after original lease expiry"

        driver.validate_round(
            self.plane,
            self.round,
            self.report,
            owner="test:owner",
            runner=long_runner,
            lease_minutes=1,
            renew_interval_seconds=0.01,
        )
        self.assertGreaterEqual(int(receipts[-1]["renewal_count"]), 1)
        self.assertGreater(
            controller.parse_time(receipts[-1]["expires_at"]),
            controller.parse_time("2030-01-01T00:01:00Z"),
        )
        self.assertEqual(self.report.steps[-1].outcome, "PASSED")

    def test_keyed_validation_binds_release_host_and_transaction_sha(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []

        class KeyedPlane:
            def acquire_keyed_validation_lease_internal(self, *_args, **kwargs):
                calls.append(("acquire", dict(kwargs)))
                return {"lease_id": "sha256:" + "1" * 64}

            def renew_keyed_validation_lease_internal(self, *_args, **kwargs):
                calls.append(("renew", dict(kwargs)))

            def release_keyed_validation_lease_internal(self, *_args, **kwargs):
                calls.append(("release", dict(kwargs)))

        authority = {
            "host_id": "host:test",
            "release_id": RELEASE_ID,
            "transaction_sha": "f" * 40,
        }
        report = driver.RoundReport()
        driver.validate_round(
            KeyedPlane(),
            self.round,
            report,
            owner="test:keyed",
            runner=lambda: (True, "passed"),
            keyed_validation_authority=authority,
            renew_interval_seconds=10,
        )
        self.assertEqual([name for name, _ in calls], ["acquire", "release"])
        self.assertEqual(
            {key: calls[0][1][key] for key in authority},
            authority,
        )
        self.assertEqual(
            {key: calls[-1][1][key] for key in authority},
            authority,
        )

    def test_publication_lease_renewer_adopts_the_latest_exact_token(self) -> None:
        renewed = threading.Event()
        calls: list[dict[str, object]] = []

        class PublicationPlane:
            def renew_publication_transaction(self, transaction, **kwargs):
                calls.append(dict(kwargs))
                renewed.set()
                return {**transaction, "record_id": "sha256:" + "9" * 64}

        token = self.publication_token()
        renewer = driver.PublicationLeaseRenewer(
            PublicationPlane(),
            token,
            coordinator_id="test:coordinator",
            interval_seconds=0.01,
        ).start()
        self.assertTrue(renewed.wait(1))
        latest = renewer.settle()
        self.assertEqual(latest["record_id"], "sha256:" + "9" * 64)
        self.assertEqual(calls[0]["coordinator_id"], "test:coordinator")
        self.assertEqual(
            calls[0]["transaction_lease_id"], token["transaction_lease_id"]
        )

    def test_publication_transition_serializes_with_inflight_renewal(self) -> None:
        renewal_entered = threading.Event()
        allow_renewal = threading.Event()
        transition_entered = threading.Event()

        class PublicationPlane:
            def renew_publication_transaction(self, transaction, **_kwargs):
                renewal_entered.set()
                if not allow_renewal.wait(2):
                    raise AssertionError("test did not release publication renewal")
                return {**transaction, "record_id": "sha256:" + "9" * 64}

        token = {**self.publication_token(), "record_id": "sha256:" + "8" * 64}
        renewer = driver.PublicationLeaseRenewer(
            PublicationPlane(),
            token,
            coordinator_id="test:coordinator",
            interval_seconds=0.01,
        ).start()
        self.assertTrue(renewal_entered.wait(1))
        transitioned: list[dict[str, object]] = []

        def transition() -> None:
            result = renewer.transition(
                lambda current: (
                    transition_entered.set() or {**current, "status": "VALIDATED"}
                )
            )
            transitioned.append(dict(result))

        thread = threading.Thread(target=transition, daemon=True)
        thread.start()
        self.assertFalse(
            transition_entered.wait(0.05),
            "state transition entered while renewal still owned the token",
        )
        allow_renewal.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        latest = renewer.settle()
        self.assertEqual(transitioned[0]["record_id"], "sha256:" + "9" * 64)
        self.assertEqual(latest["status"], "VALIDATED")

    def test_stale_round_authority_causes_zero_mutation_before_integration(
        self,
    ) -> None:
        effects: list[str] = []

        class FencedPlane:
            @contextmanager
            def round_admission_guard(self, *, release_id: str):
                effects.append(f"guard:{release_id}")
                raise controller.ClaimError("round admission release fence mismatch")
                yield {}  # pragma: no cover - required by contextmanager protocol

            def status(self) -> dict[str, object]:
                effects.append("status")
                return {}

        with self.assertRaisesRegex(controller.ClaimError, "fence mismatch"):
            driver.drive_round(
                FencedPlane(),
                actor="test:stale-round",
                push=False,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(effects, [f"guard:{RELEASE_ID}"])

    def test_missing_round_authority_causes_zero_observation_or_git_effects(
        self,
    ) -> None:
        effects: list[str] = []

        class UnfencedPlane:
            def status(self) -> dict[str, object]:
                effects.append("status")
                return {}

            def _git(self, *_args, **_kwargs):
                effects.append("git")
                raise AssertionError("Git must not be reached")

        with self.assertRaisesRegex(driver.RoundDriverError, "requires exact shared"):
            driver.drive_round(UnfencedPlane(), actor="test:unfenced-round")
        self.assertEqual(effects, [])

    def test_public_validation_bypass_is_rejected_before_authority_or_effects(
        self,
    ) -> None:
        effects: list[str] = []

        class FencedPlane:
            @contextmanager
            def round_admission_guard(self, *, release_id: str):
                effects.append("guard")
                raise controller.ClaimError("round admission release is stale")
                yield {}  # pragma: no cover - required by contextmanager protocol

            def status(self) -> dict[str, object]:
                effects.append("status")
                return {}

        with self.assertRaises(TypeError):
            driver.drive_round(
                FencedPlane(),
                actor="test:skip-validation",
                push=False,
                validate=False,  # type: ignore[call-arg]
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(effects, [])

    def test_public_round_api_does_not_accept_a_validation_runner(self) -> None:
        effects: list[str] = []

        class Plane:
            def round_admission_guard(self, **_kwargs):
                effects.append("guard")
                raise AssertionError("authority must not be reached")

        with self.assertRaises(TypeError):
            driver.drive_round(
                Plane(),
                actor="test:runner-injection",
                runner=lambda: (True, "forged gate"),  # type: ignore[call-arg]
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(effects, [])

    def test_public_round_api_does_not_accept_a_session_cap(self) -> None:
        effects: list[str] = []

        class Plane:
            def round_admission_guard(self, **_kwargs):
                effects.append("guard")
                raise AssertionError("authority must not be reached")

        with self.assertRaises(TypeError):
            driver.drive_round(
                Plane(),
                actor="test:session-cap-injection",
                max_sessions=99,  # type: ignore[call-arg]
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(effects, [])

    def test_public_round_never_recompiles_an_ambient_worktree_plan(self) -> None:
        effects: list[str] = []
        self.install_round_snapshot(self.authority_snapshot())
        with (
            mock.patch.object(
                driver,
                "select_round",
                side_effect=AssertionError("ambient plan selector must not run"),
            ),
            mock.patch.object(driver, "receipt_head", return_value=None),
            mock.patch.object(
                driver,
                "triage_round",
                side_effect=lambda *_a, **_k: effects.append("triage"),
            ),
            mock.patch.object(
                driver,
                "integrate_private_round",
                side_effect=lambda *_a, **_k: effects.append("integrate"),
            ),
            mock.patch.object(
                driver.healing,
                "heal_round",
                side_effect=lambda *_a, **_k: effects.append("heal"),
            ),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:canonical-release-wave",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PENDING")
        self.assertEqual(effects, [])

    def test_nonpositive_round_cap_is_rejected_before_status_or_effects(self) -> None:
        effects: list[str] = []
        self.install_round_snapshot(self.authority_snapshot(release={"session_cap": 0}))
        with mock.patch.object(
            driver,
            "select_round",
            side_effect=lambda *_a, **_k: effects.append("select"),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:noncanonical-cap",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")
        self.assertEqual(effects, [])

    def test_round_uses_dynamic_authenticated_remaining_capacity(self) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(
                release={"session_cap": 3, "host_id": "host:shared-capacity"},
            )
        )
        with (
            mock.patch.object(
                driver,
                "select_round",
                side_effect=AssertionError("release is the only round selector"),
            ),
            mock.patch.object(driver, "receipt_head", return_value=None),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:dynamic-cap",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PENDING")

    def test_round_accepts_same_generation_capacity_expiry_renewal(self) -> None:
        snapshot = self.authority_snapshot()
        capacities = snapshot["host_capacity_generations"]
        assert isinstance(capacities, dict)
        current = capacities["host:test"]
        assert isinstance(current, dict)
        current["record_id"] = "sha256:" + "8" * 64
        self.install_round_snapshot(snapshot)
        with (
            mock.patch.object(
                driver,
                "select_round",
                side_effect=AssertionError("release is the only round selector"),
            ),
            mock.patch.object(driver, "receipt_head", return_value=None),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:capacity-expiry-renewal",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PENDING")

    def test_round_rejects_capacity_record_outside_authenticated_lineage(self) -> None:
        snapshot = self.authority_snapshot()
        issuance = snapshot["release_capacity_issuance_record"]
        assert isinstance(issuance, dict)
        issuance["record_id"] = "sha256:" + "9" * 64
        self.install_round_snapshot(snapshot)
        result = driver.drive_round(
            self.plane,
            actor="test:capacity-lineage-mismatch",
            round_authority={"release_id": RELEASE_ID},
        )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")

    def test_round_rejects_wave_or_cap_beyond_authenticated_host_capacity(self) -> None:
        cases = (
            {
                "released_wave": [NODE, "EXTRA-200"],
                "session_cap": 1,
            },
            {
                "session_cap": 3,
                "capacity_max_total_sessions": 2,
            },
        )
        for release in cases:
            with self.subTest(release=release):
                self.install_round_snapshot(self.authority_snapshot(release=release))
                result = driver.drive_round(
                    self.plane,
                    actor="test:over-cap-release",
                    round_authority={"release_id": RELEASE_ID},
                )
                self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")

    def test_round_rejects_malformed_capacity_authority_fields(self) -> None:
        cases = (
            {"capacity_generation": "not-a-digest"},
            {"capacity_record_id": "not-a-digest"},
            {"capacity_epoch": 0},
            {"capacity_validation_slots": -1},
            {
                "capacity_max_total_sessions": 1,
                "capacity_validation_slots": 2,
            },
        )
        for release in cases:
            with self.subTest(release=release):
                self.install_round_snapshot(self.authority_snapshot(release=release))
                result = driver.drive_round(
                    self.plane,
                    actor="test:malformed-capacity",
                    round_authority={"release_id": RELEASE_ID},
                )
                self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")

    def test_reconciliation_change_refuses_round_without_healing(self) -> None:
        effects: list[str] = []
        self.install_round_snapshot(
            self.authority_snapshot(status={"reconciliation_required": True})
        )
        with mock.patch.object(
            driver.healing,
            "reconcile_with_snapshot",
            side_effect=lambda *_a, **_k: effects.append("reconcile"),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:advanced-target",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")
        self.assertEqual(effects, [])

    def test_public_partial_wave_returns_before_heal_merge_or_child_reconcile(
        self,
    ) -> None:
        effects: list[str] = []
        self.install_round_snapshot(self.authority_snapshot())
        with (
            mock.patch.object(driver, "select_round", return_value=self.round),
            mock.patch.object(
                driver,
                "receipt_head",
                side_effect=lambda *_a, **_k: effects.append("receipt") or None,
            ),
            mock.patch.object(
                driver,
                "triage_round",
                side_effect=lambda *_a, **_k: effects.append("triage"),
            ),
            mock.patch.object(
                driver,
                "integrate_private_round",
                side_effect=lambda *_a, **_k: effects.append("integrate"),
            ),
            mock.patch.object(
                driver.healing,
                "heal_round",
                side_effect=lambda *_a, **_k: effects.append("heal"),
            ),
            mock.patch.object(
                driver.healing,
                "reconcile_with_snapshot",
                side_effect=lambda *_a, **_k: effects.append("reconcile"),
            ),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:partial-round",
                push=False,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PENDING")
        self.assertEqual(effects, ["receipt"])

    def test_public_round_never_uses_an_ambient_advanced_checkout(self) -> None:
        git(self.root, "commit", "--allow-empty", "-m", "unreleased local advance")
        self.plane.observe_status = mock.Mock(  # type: ignore[method-assign]
            side_effect=AssertionError("status must not be observed")
        )
        self.install_round_snapshot(self.authority_snapshot())
        with (
            mock.patch.object(driver, "select_round", return_value=self.round),
            mock.patch.object(driver, "receipt_head", return_value=None),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:local-ahead",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PENDING")
        self.plane.observe_status.assert_not_called()

    def test_public_round_never_uses_ambient_untracked_files(self) -> None:
        (self.root / "untracked.txt").write_text("not admitted\n", encoding="utf-8")
        self.plane.observe_status = mock.Mock(  # type: ignore[method-assign]
            side_effect=AssertionError("status must not be observed")
        )
        self.install_round_snapshot(self.authority_snapshot())
        with (
            mock.patch.object(driver, "select_round", return_value=self.round),
            mock.patch.object(driver, "receipt_head", return_value=None),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:dirty-round",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PENDING")
        self.plane.observe_status.assert_not_called()

    def test_live_validation_lease_prevents_false_quiescence(self) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(
                status={"complete": True},
                active_validation_lease={
                    "node_id": NODE,
                    "expires_at": "2030-01-01T00:10:00Z",
                },
            )
        )
        result = driver.drive_round(
            self.plane,
            actor="test:lease",
            round_authority={"release_id": RELEASE_ID},
        )
        self.assertEqual(result["disposition"], "ACTIVE")
        self.assertEqual(result["wake_at"], "2030-01-01T00:10:00Z")

    def test_expired_validation_lease_requires_recovery_not_quiescence(self) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(
                status={"complete": True},
                reconciliation_obligations=[
                    {"kind": "EXPIRED_VALIDATION_LEASE", "node_id": NODE}
                ],
            )
        )
        result = driver.drive_round(
            self.plane,
            actor="test:expired-lease",
            round_authority={"release_id": RELEASE_ID},
        )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")
        self.assertTrue(result["blocked"])

    def test_host_reservation_prevents_false_quiescence(self) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(
                status={"complete": True},
                active_host_reservations=[
                    {"host_reservation_id": "sha256:" + "e" * 64}
                ],
            )
        )
        with mock.patch.object(driver, "select_round", return_value=None):
            result = driver.drive_round(
                self.plane,
                actor="test:reservation",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "ACTIVE")
        self.assertIn("active_host_reservations", result["authority"])

    def test_public_authority_inventory_is_mandatory_and_typed(self) -> None:
        with self.assertRaisesRegex(
            driver.RoundDriverError, "missing a typed active_write_launch_reservations"
        ):
            driver._strict_public_authority_inventory({})
        malformed = {key: [] for key in driver._PUBLIC_AUTHORITY_INVENTORIES}
        malformed["active_host_reservations"] = ["not an authority object"]
        with self.assertRaisesRegex(
            driver.RoundDriverError, "missing a typed active_host_reservations"
        ):
            driver._strict_public_authority_inventory(malformed)

    def test_live_sidecar_blocks_a_selected_round_not_only_quiescence(self) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(
                active_host_reservations=[
                    {
                        "sidecar_id": "sha256:" + "c" * 64,
                        "host_reservation_id": "sha256:" + "e" * 64,
                    }
                ]
            )
        )
        with mock.patch.object(
            driver,
            "select_round",
            side_effect=AssertionError("round selection must remain fenced"),
        ):
            result = driver.drive_round(
                self.plane,
                actor="test:selected-reservation",
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "ACTIVE")
        self.assertIn("active_host_reservations", result["authority"])

    def test_incomplete_controller_state_prevents_false_quiescence(self) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(release={"released_wave": []})
        )
        result = driver.drive_round(
            self.plane,
            actor="test:incomplete",
            round_authority={"release_id": RELEASE_ID},
        )
        self.assertEqual(result["disposition"], "ACTIVE")

    def test_empty_release_and_complete_atomic_snapshot_is_controller_quiescent_candidate(
        self,
    ) -> None:
        self.install_round_snapshot(
            self.authority_snapshot(
                release={"released_wave": []},
                status={"complete": True},
            )
        )
        result = driver.drive_round(
            self.plane,
            actor="test:quiescent",
            round_authority={"release_id": RELEASE_ID},
        )
        self.assertEqual(result["disposition"], "CONTROLLER_QUIESCENT_CANDIDATE")
        self.assertEqual(result["controller_authority_digest"], "sha256:" + "b" * 64)

    def test_completed_worker_round_validates_without_a_live_worker_claim(self) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        self.assertFalse(self.plane.claim_path(NODE).exists())
        with self.public_pipeline() as calls:
            result = driver.drive_round(
                self.plane,
                actor="test:round-coordinator",
                push=False,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "ROUND_VALIDATED_LOCAL")
        self.assertFalse(self.plane.claim_path(NODE).exists())
        calls["gate"].assert_called_once()
        calls["publish"].assert_not_called()
        self.assertEqual(calls["finish"].call_args.kwargs["outcome"], "NO_PUSH")

    def test_failed_public_validation_retains_private_adverse_evidence(self) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        with self.public_pipeline(validation_passes=False) as calls:
            result = driver.drive_round(
                self.plane,
                actor="test:failed-validation",
                push=True,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "VALIDATION_FAILED")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.base)
        self.assertEqual(self.plane.remote_branch_sha(self.target), self.base)
        self.assertEqual(
            calls["finish"].call_args.kwargs["outcome"], "VALIDATION_FAILED"
        )
        calls["pin"].assert_called_once()
        calls["seal"].assert_not_called()
        calls["publish"].assert_not_called()

    def test_whole_validated_round_publishes_target_once(self) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        with self.public_pipeline() as calls:
            result = driver.drive_round(
                self.plane,
                actor="test:publish-round",
                push=True,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "ROUND_COMPLETE")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.base)
        calls["pin"].assert_called_once()
        calls["seal"].assert_called_once()
        calls["publish"].assert_called_once()
        self.assertEqual(calls["publish"].call_args.args[0]["status"], "VALIDATED")
        self.assertEqual(
            calls["publish"].call_args.kwargs["pinned_sha"], calls["pinned"]
        )
        self.assertEqual(result["steps"][-1]["outcome"], "PUBLISHED")

    def test_remote_publication_rejection_is_not_reported_as_rollback(self) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        with self.public_pipeline(publication_outcome="REJECTED"):
            result = driver.drive_round(
                self.plane,
                actor="test:remote-advance",
                push=True,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "PUBLISH_REJECTED")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.base)
        self.assertEqual(self.plane.remote_branch_sha(self.target), self.base)

    def test_publication_exception_is_retained_as_recovery_required(self) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        with self.public_pipeline() as calls:
            calls["publish"].side_effect = RuntimeError("response lost after push")
            result = driver.drive_round(
                self.plane,
                actor="test:publication-exception",
                push=True,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")
        self.assertEqual(
            calls["finish"].call_args.kwargs["outcome"], "RECOVERY_REQUIRED"
        )
        self.assertIn("response lost after push", "; ".join(result["failures"]))

    def test_malformed_publication_result_is_retained_as_recovery_required(
        self,
    ) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        with self.public_pipeline() as calls:
            calls["publish"].return_value = {"outcome": "impossible"}
            result = driver.drive_round(
                self.plane,
                actor="test:malformed-publication-result",
                push=True,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")
        self.assertEqual(
            calls["finish"].call_args.kwargs["outcome"], "RECOVERY_REQUIRED"
        )
        self.assertIn("malformed terminal evidence", "; ".join(result["failures"]))

    def test_validation_and_workspace_cleanup_failures_are_both_retained(self) -> None:
        self.install_round_snapshot(self.authority_snapshot())
        with self.public_pipeline() as calls:
            calls["gate"].side_effect = driver.RoundValidationError(
                [RuntimeError("fixed repository validation failed")]
            )
            calls[
                "private"
            ].return_value.__exit__.side_effect = driver.RoundDriverError(
                "workspace cleanup uncertain"
            )
            result = driver.drive_round(
                self.plane,
                actor="test:validation-and-cleanup-failure",
                push=True,
                round_authority={"release_id": RELEASE_ID},
            )
        self.assertEqual(result["disposition"], "RECOVERY_REQUIRED")
        joined = "; ".join(result["failures"])
        self.assertIn("fixed repository validation failed", joined)
        self.assertIn("workspace cleanup uncertain", joined)
        self.assertEqual(
            calls["finish"].call_args.kwargs["outcome"], "RECOVERY_REQUIRED"
        )

    def test_completion_reads_node_rows_not_the_plan_wide_boolean(self) -> None:
        status = {
            "complete": False,
            "nodes": [
                {"node_id": "BOOT-000", "state": "COMPLETE"},
                {"node_id": NODE, "state": "RECONCILIATION_REQUIRED"},
            ],
        }
        self.assertEqual(driver.completed_nodes(status), {"BOOT-000"})

    def test_validation_runs_against_this_checkouts_sources(self) -> None:
        """An editable install elsewhere must not win the gate's imports."""

        source = self.root / "src" / "probe_pkg"
        source.mkdir(parents=True)
        (source / "__init__.py").write_text(
            "ORIGIN = 'this-checkout'\n", encoding="utf-8"
        )
        tests = self.root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_probe.py").write_text(
            "import unittest, probe_pkg\n"
            "class T(unittest.TestCase):\n"
            "    def test_origin(self):\n"
            "        self.assertEqual(probe_pkg.ORIGIN, 'this-checkout')\n",
            encoding="utf-8",
        )
        passed, summary = driver.default_validation_runner(self.root)()
        self.assertTrue(passed, summary)

    def test_fixed_validation_runner_seals_exact_gate_evidence(self) -> None:
        tests = self.root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_probe_fixed_gate.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_gate(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        runner = driver.default_validation_runner(self.root)
        passed, summary = runner()
        self.assertTrue(passed, summary)
        evidence = dict(runner.validation_evidence or {})
        self.assertEqual(
            set(evidence),
            {
                "schema_version",
                "kind",
                "argv",
                "interpreter_path",
                "interpreter_digest_before",
                "interpreter_digest_after",
                "round_driver_path",
                "round_driver_digest_before",
                "round_driver_digest_after",
                "git_executable_path",
                "git_executable_digest_before",
                "git_executable_digest_after",
                "worktree_tree",
                "worktree_head_after",
                "transaction_ref_after",
                "worktree_status_porcelain",
                "environment_policy_digest",
                "started_at",
                "completed_at",
                "exit_code",
                "output_digest",
                "summary",
            },
        )
        self.assertEqual(evidence["kind"], "hive-mind-fixed-publication-gate-result-v1")
        self.assertEqual(evidence["exit_code"], 0)
        self.assertEqual(evidence["argv"][1:4], ["-I", "-S", "-B"])
        self.assertEqual(evidence["argv"][-1], str(self.root.resolve()))
        self.assertEqual(
            evidence["interpreter_digest_before"],
            evidence["interpreter_digest_after"],
        )
        self.assertEqual(
            evidence["round_driver_digest_before"],
            evidence["round_driver_digest_after"],
        )
        self.assertEqual(
            evidence["git_executable_digest_before"],
            evidence["git_executable_digest_after"],
        )

    def test_fixed_validation_rejects_interpreter_startup_shadows(self) -> None:
        source = self.root / "src"
        source.mkdir(exist_ok=True)
        poison = source / "sitecustomize.py"
        poison.write_text("import os; os._exit(0)\n", encoding="utf-8")
        with self.assertRaisesRegex(
            driver.RoundDriverError, "interpreter-startup shadows"
        ):
            driver.default_validation_runner(self.root)()

    def test_fixed_validation_rejects_git_replacement_authority(self) -> None:
        """A clone-local replacement must never stand in for pushed object truth."""

        original = git(self.root, "rev-parse", "HEAD")
        git(self.root, "commit", "--allow-empty", "-m", "replacement poison")
        replacement = git(self.root, "rev-parse", "HEAD")
        git(self.root, "reset", "--hard", original)
        git(self.root, "replace", original, replacement)
        try:
            with self.assertRaisesRegex(
                driver.RoundDriverError, "Git replacement refs"
            ):
                driver.default_validation_runner(self.root)()
        finally:
            git(self.root, "replace", "-d", original)

    def test_fixed_validation_rejects_legacy_git_grafts(self) -> None:
        common_dir = Path(git(self.root, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = self.root / common_dir
        grafts = common_dir / "info" / "grafts"
        grafts.parent.mkdir(parents=True, exist_ok=True)
        grafts.write_text(git(self.root, "rev-parse", "HEAD") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(driver.RoundDriverError, "legacy Git grafts"):
            driver.default_validation_runner(self.root)()

    def test_validation_does_not_inherit_git_environment_variables(self) -> None:
        """An exported GIT_* must not make the gate fail for environmental reasons."""

        tests = self.root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_probe_env.py").write_text(
            "import os, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_no_inherited_git_vars(self):\n"
            "        self.assertEqual(\n"
            "            {k: v for k, v in os.environ.items() if k.upper().startswith('GIT_')},\n"
            "            {'GIT_NO_REPLACE_OBJECTS': '1'},\n"
            "        )\n",
            encoding="utf-8",
        )
        previous = os.environ.get("GIT_EDITOR")
        os.environ["GIT_EDITOR"] = "true"
        try:
            passed, summary = driver.default_validation_runner(self.root)()
        finally:
            if previous is None:
                os.environ.pop("GIT_EDITOR", None)
            else:
                os.environ["GIT_EDITOR"] = previous
        self.assertTrue(passed, summary)

    def test_blocker_classification_follows_required_authority(self) -> None:
        self.assertEqual(
            driver.classify_blocker("remote branch already exists; reconcile it"),
            "CLASS_B",
        )
        self.assertEqual(
            driver.classify_blocker("node requires owner credential for delivery"),
            "CLASS_C",
        )
        self.assertEqual(
            driver.classify_blocker(
                "runbook demands a digest equality the store cannot produce"
            ),
            "CLASS_A",
        )

    def test_triage_reports_without_repairing_a_sealed_blocker(self) -> None:
        self.plane.record_blocker(
            NODE,
            cause="requires production authority",
            fix="obtain the separately governed production authority",
            retry_when="the external authority is explicitly available",
            category="external-authority",
        )
        driver.triage_round(self.plane, (NODE,), self.report)
        self.assertEqual(self.report.steps[-1].outcome, "CLASS_C")
        self.assertTrue(self.report.blocked)


if __name__ == "__main__":
    unittest.main()
