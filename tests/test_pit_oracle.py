from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.pit_oracle import (
    LeakageError,
    PointInTimeOracle,
    SealViolation,
    build_self_curriculum,
)
from hive_mind_os.receipts import FileReceiptValidator, ReceiptReference
from hive_mind_os.repository_learning import RepositoryLearningCurriculum
from tests.fixtures.fixture_history import EXPECTED_SHAS, build_fixture_history


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        env={
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace"))
    return completed


class PointInTimeOracleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.fixture = build_fixture_history(self.base / "fixture")
        self.ledger = EvidenceLedger()
        self.addCleanup(self.ledger.close)
        self.oracle = PointInTimeOracle(
            self.fixture.root,
            self.base / "state",
            ledger=self.ledger,
        )

    def environment(self, position: int = 6):
        return self.oracle.build_environment(self.fixture.commits[position])

    def test_ancestor_set_equals_exact_fixture_dag_closure(self) -> None:
        environment = self.environment(6)
        expected = tuple(
            _git(
                self.fixture.root,
                "rev-list",
                "--topo-order",
                "--reverse",
                f"{environment.target_sha}^",
            ).stdout.decode("ascii").splitlines()
        )
        observed = tuple(
            _git(
                environment.root,
                "rev-list",
                "--topo-order",
                "--reverse",
                "--all",
            ).stdout.decode("ascii").splitlines()
        )
        self.assertEqual(set(environment.ancestor_shas), set(expected))
        self.assertEqual(set(observed), set(expected))

    def test_target_tree_future_objects_absent_and_ancestor_blob_present(self) -> None:
        environment = self.environment(6)
        forbidden = (
            environment.target_sha,
            environment.target_tree_sha,
            *environment.hidden_shas,
        )
        for object_id in forbidden:
            with self.subTest(object_id=object_id):
                self.assertNotEqual(
                    _git(
                        environment.root,
                        "cat-file",
                        "-e",
                        object_id,
                        check=False,
                    ).returncode,
                    0,
                )
        pre_target_blob = (
            _git(
                self.fixture.root,
                "rev-parse",
                f"{environment.ancestor_shas[0]}:README.md",
            )
            .stdout.decode("ascii")
            .strip()
        )
        self.assertEqual(
            _git(
                environment.root,
                "cat-file",
                "-e",
                pre_target_blob,
                check=False,
            ).returncode,
            0,
        )

    def test_post_merge_environment_contains_both_parent_lines(self) -> None:
        environment = self.environment(8)
        merge_parents = (
            _git(self.fixture.root, "rev-list", "--parents", "-n", "1", self.fixture.merge_sha)
            .stdout.decode("ascii")
            .strip()
            .split()[1:]
        )
        observed = set(
            _git(environment.root, "rev-list", "--all")
            .stdout.decode("ascii")
            .splitlines()
        )
        self.assertEqual(len(merge_parents), 2)
        self.assertTrue(set(merge_parents).issubset(observed))

    def test_self_verification_refuses_injected_future_object(self) -> None:
        environment = self.environment(6)
        _git(
            environment.root,
            "fetch",
            str(self.fixture.root),
            environment.target_sha,
        )
        with self.assertRaisesRegex(LeakageError, "forbidden object"):
            self.oracle.verify_environment(environment)

    def test_seal_is_required_before_reveal_and_orders_ledger_events(self) -> None:
        environment = self.environment(6)
        with self.assertRaises(SealViolation):
            self.oracle.reveal(environment)
        sealed = self.oracle.seal_prediction(
            environment,
            target_position=6,
            learner_identity="test-learner",
            prediction_content={"changed_paths": ["tests/core.txt"]},
        )
        reveal = self.oracle.reveal(environment, sealed)
        grade = self.oracle.grade(environment, sealed, reveal)
        event_types = [
            event["event_type"] for event in self.ledger.events(environment.episode_id)
        ]
        self.assertIn("pit.violation", event_types)
        self.assertLess(
            event_types.index("pit.prediction.sealed"),
            event_types.index("pit.target.revealed"),
        )
        self.assertGreaterEqual(grade.score, 0.0)

    def test_prediction_mutation_after_reveal_is_detected_at_grading(self) -> None:
        environment = self.environment(6)
        content = {"changed_paths": ["tests/core.txt"]}
        sealed = self.oracle.seal_prediction(
            environment,
            target_position=6,
            learner_identity="mutable-learner",
            prediction_content=content,
        )
        reveal = self.oracle.reveal(environment, sealed)
        altered = replace(
            sealed,
            prediction_content={"changed_paths": ["src/core.txt"]},
        )
        with self.assertRaisesRegex(SealViolation, "altered"):
            self.oracle.grade(environment, altered, reveal)

    def test_forged_reveal_is_rejected_before_grading(self) -> None:
        environment = self.environment(6)
        sealed = self.oracle.seal_prediction(
            environment,
            target_position=6,
            learner_identity="reveal-integrity-learner",
            prediction_content={"changed_paths": ["forged.txt"]},
        )
        reveal = self.oracle.reveal(environment, sealed)
        forged_reveal = {**reveal, "changed_paths": ["forged.txt"]}

        with self.assertRaisesRegex(
            SealViolation,
            "altered, foreign, or not recorded",
        ):
            self.oracle.grade(environment, sealed, forged_reveal)

        event_types = [
            event["event_type"] for event in self.ledger.events(environment.episode_id)
        ]
        self.assertEqual(event_types[-1], "pit.violation")
        self.assertNotIn("pit.episode.graded", event_types)

    def test_seal_rejects_mutated_target_environment(self) -> None:
        environment = self.environment(6)
        sealed = self.oracle.seal_prediction(
            environment,
            target_position=6,
            learner_identity="target-binding-learner",
            prediction_content={"changed_paths": ["tests/core.txt"]},
        )
        environment.target_sha = self.fixture.commits[7]

        with self.assertRaisesRegex(SealViolation, "altered"):
            self.oracle.reveal(environment, sealed)

        event_types = [
            event["event_type"] for event in self.ledger.events(environment.episode_id)
        ]
        self.assertEqual(event_types[-1], "pit.violation")
        self.assertNotIn("pit.target.revealed", event_types)

    def test_cheating_probes_fail_and_every_attempt_has_a_receipt(self) -> None:
        environment = self.environment(6)
        probes = self.oracle.run_adversarial_probes(environment)
        self.assertEqual(
            {probe["name"] for probe in probes},
            {"target-cat-file", "all-refs-log", "reflog", "packed-refs"},
        )
        target_probe = next(
            probe for probe in probes if probe["name"] == "target-cat-file"
        )
        self.assertEqual(target_probe["result"], "failed")
        validator = FileReceiptValidator(self.oracle.receipt_root)
        for probe in probes:
            matching = [
                record
                for record in environment.receipt_records
                if record["digest"] == probe["receipt_digest"]
            ]
            self.assertEqual(len(matching), 1)
            result = validator.validate(
                ReceiptReference(matching[0]["path"], matching[0]["digest"]),
                mission_id=matching[0]["mission_id"],
                state_ref=matching[0]["state_ref"],
                actor_id=matching[0]["actor_id"],
                action_id=matching[0]["action_id"],
                action_kind=matching[0]["action_kind"],
                action_digest=matching[0]["action_digest"],
            )
            self.assertTrue(result.valid, result.issues)

    def test_bookkeeping_physics_discrepancy_fails_closed(self) -> None:
        environment = self.environment(6)
        states = tuple(
            self.oracle_state(sha_value) for sha_value in self.fixture.commits
        )
        episode = RepositoryLearningCurriculum(states).episodes()[6]
        with self.assertRaisesRegex(LeakageError, "defense-in-depth discrepancy"):
            self.oracle.validate_curriculum_access(
                environment,
                episode,
                [environment.target_sha],
            )

    def oracle_state(self, sha_value: str):
        from hive_mind_os.repository_learning import CommitState

        line = (
            _git(self.fixture.root, "rev-list", "--parents", "-n", "1", sha_value)
            .stdout.decode("ascii")
            .strip()
            .split()
        )
        tree = (
            _git(self.fixture.root, "rev-parse", f"{sha_value}^{{tree}}")
            .stdout.decode("ascii")
            .strip()
        )
        return CommitState(line[0], tree, tuple(line[1:]))

    def test_episode_record_is_complete_and_receipts_resolve(self) -> None:
        record_path = self.oracle.run_scripted_episode(self.fixture.commits[6])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertTrue(record["environment"]["digest"].startswith("sha256:"))
        self.assertTrue(record["prediction"]["digest"].startswith("sha256:"))
        self.assertIn("score", record["grade"])
        self.assertEqual(len(record["adversarial_probes"]), 4)
        self.assertGreater(len(record["receipts"]), 0)
        self.assertTrue(record["contamination_caveats"])
        validator = FileReceiptValidator(Path(record["receipt_root"]))
        for receipt in record["receipts"]:
            validation = validator.validate(
                ReceiptReference(receipt["path"], receipt["digest"]),
                mission_id=receipt["mission_id"],
                state_ref=receipt["state_ref"],
                actor_id=receipt["actor_id"],
                action_id=receipt["action_id"],
                action_kind=receipt["action_kind"],
                action_digest=receipt["action_digest"],
            )
            self.assertTrue(validation.valid, validation.issues)

    def test_self_history_pins_and_scripted_episode_complete_offline(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        pins = json.loads(
            (repository / "tests" / "fixtures" / "self_history_pins.json").read_text(
                encoding="utf-8"
            )
        )["shas"]
        curriculum = build_self_curriculum(repository, len(pins))
        self.assertEqual(
            tuple(episode.target.sha for episode in curriculum.episodes()),
            tuple(pins),
        )
        self_oracle = PointInTimeOracle(
            repository,
            self.base / "self-state",
        )
        self.addCleanup(self_oracle.close)
        record_path = self_oracle.run_scripted_episode(
            pins[-1],
            self_history=True,
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["target_sha"], pins[-1])
        self.assertIn("model-training-data cutoffs", " ".join(record["contamination_caveats"]))
        event_types = [event["event_type"] for event in record["ledger_events"]]
        self.assertIn("pit.prediction.sealed", event_types)
        self.assertIn("pit.episode.graded", event_types)

    def test_fixture_sha_table_and_tag_are_stable(self) -> None:
        self.assertEqual(self.fixture.commits, EXPECTED_SHAS)
        tag_target = (
            _git(self.fixture.root, "rev-parse", self.fixture.tag_name)
            .stdout.decode("ascii")
            .strip()
        )
        self.assertEqual(tag_target, self.fixture.merge_sha)


if __name__ == "__main__":
    unittest.main()
