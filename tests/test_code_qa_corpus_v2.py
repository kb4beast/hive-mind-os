from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from typing import Any

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.cortex.repository.code_qa_corpus import (
    PINNED_CORPUS_BUNDLE_DIGEST,
    QUALIFICATION,
    TRUST_MODEL,
    AttemptFeedback,
    BuilderTaskView,
    CandidateProposal,
    CorpusDefinitionError,
    DeterministicBuilderDouble,
    _assert_casefold_unique,
    run_code_qa_corpus,
    tree_digest,
)

FIXTURES = Path(__file__).parent / "fixtures" / "code_qa_v2"
WINNING_SHIPPING = (
    "def shipping_tier(weight: int) -> str:\n"
    "    return 'parcel' if 0 <= weight <= 10 else 'freight'\n"
)


def _run_pinned(
    fixture_root: Path,
    output_root: Path,
    **kwargs: Any,
):
    return run_code_qa_corpus(
        fixture_root,
        output_root,
        expected_bundle_digest=PINNED_CORPUS_BUNDLE_DIGEST,
        **kwargs,
    )


def _task_contract_digest(manifest: dict[str, Any]) -> str:
    fields = (
        "schema_version",
        "task_id",
        "shape",
        "objective",
        "allowed_write_paths",
        "public_test_paths",
        "baseline_tree_digest",
        "public_check_digest",
        "baseline_public_outcome_digest",
        "hidden_check_digest",
        "max_attempts",
        "qualification",
    )
    return canonical_digest({field: manifest[field] for field in fields})


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _reseal_root_manifest(root: Path) -> str:
    manifest_path = root / "corpus-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tasks"] = []
    for task_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        task = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["tasks"].append(
            {
                "task_id": task["task_id"],
                "task_contract_digest": task["task_contract_digest"],
            }
        )
    manifest["directories"] = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    )
    manifest["inventory"] = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": len(content),
            "sha256": f"sha256:{sha256(content).hexdigest()}",
        }
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path != manifest_path
        for content in (path.read_bytes(),)
    ]
    manifest.pop("bundle_digest", None)
    manifest["bundle_digest"] = canonical_digest(manifest)
    _write_json(manifest_path, manifest)
    return manifest["bundle_digest"]


class _OneProposalBuilder:
    identity = "test:one-proposal-code-qa-builder"
    qualification = QUALIFICATION

    def __init__(self, proposal: CandidateProposal) -> None:
        self.proposal = proposal
        self.views: list[BuilderTaskView] = []
        self.feedback: list[tuple[AttemptFeedback, ...]] = []

    def propose(
        self, task: BuilderTaskView, feedback: tuple[AttemptFeedback, ...]
    ) -> CandidateProposal:
        self.views.append(task)
        self.feedback.append(feedback)
        return self.proposal


class _InspectingBuilder:
    identity = "test:inspecting-delegating-code-qa-builder"
    qualification = QUALIFICATION

    def __init__(self) -> None:
        self.delegate = DeterministicBuilderDouble()
        self.views: list[BuilderTaskView] = []

    def propose(
        self, task: BuilderTaskView, feedback: tuple[AttemptFeedback, ...]
    ) -> CandidateProposal:
        self.views.append(task)
        return self.delegate.propose(task, feedback)


class CodeQACorpusV2Tests(unittest.TestCase):
    def test_three_varied_tasks_repair_through_effects_and_pass_both_checks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = _run_pinned(FIXTURES, output)

            self.assertEqual("succeeded", result.status)
            self.assertFalse(result.operationally_qualified)
            self.assertEqual(
                {
                    "flat-module-token-normalization",
                    "nested-package-whole-input-aggregation",
                    "single-module-boundary-classification",
                },
                {task.shape for task in result.task_runs},
            )
            self.assertEqual(3, len(result.task_runs))
            for task in result.task_runs:
                with self.subTest(task=task.task_id):
                    self.assertFalse(task.baseline.public_outcome.passed)
                    self.assertEqual(
                        task.baseline.tree_digest,
                        tree_digest(output / task.task_id / "baseline"),
                    )
                    self.assertEqual(2, len(task.attempts))
                    losing, winner = task.attempts
                    self.assertEqual("failed", losing.disposition)
                    self.assertTrue(losing.public_outcome.passed)
                    self.assertFalse(losing.hidden_outcome.passed)
                    self.assertEqual("succeeded", winner.disposition)
                    self.assertTrue(winner.public_outcome.passed)
                    self.assertTrue(winner.hidden_outcome.passed)
                    self.assertIsNotNone(winner.evidence)
                    assert winner.evidence is not None
                    self.assertEqual(
                        winner.evidence.candidate_digest,
                        winner.public_outcome.candidate_digest,
                    )
                    self.assertEqual(
                        winner.evidence.candidate_digest,
                        winner.hidden_outcome.candidate_digest,
                    )
                    self.assertTrue(winner.evidence.diff_digest.startswith("sha256:"))
                    self.assertTrue(winner.evidence.tree_digest.startswith("sha256:"))
                    self.assertGreater(len(winner.effects), 0)
                    self.assertTrue(
                        all(
                            effect.effect_status == "SUCCEEDED"
                            for effect in winner.effects
                        )
                    )
                    self.assertTrue(
                        all(
                            effect.adapter_outcome_status == "SUCCEEDED"
                            for effect in winner.effects
                        )
                    )
                    self.assertTrue(
                        all(
                            effect.receipt_digest.startswith("sha256:")
                            for effect in winner.effects
                        )
                    )
                    self.assertTrue(
                        (
                            output / task.task_id / "attempt-01" / "attempt-record.json"
                        ).is_file()
                    )
                    self.assertTrue(
                        (
                            output / task.task_id / "attempt-02" / "attempt-record.json"
                        ).is_file()
                    )

    def test_replay_is_deterministic_and_run_directory_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = _run_pinned(FIXTURES, root / "first")
            second = _run_pinned(FIXTURES, root / "second")
            self.assertEqual(first.corpus_digest, second.corpus_digest)
            self.assertEqual(
                [task.result_digest for task in first.task_runs],
                [task.result_digest for task in second.task_runs],
            )
            with self.assertRaises(FileExistsError):
                _run_pinned(FIXTURES, root / "first")

    def test_builder_view_discloses_only_public_files_and_hidden_digest(self) -> None:
        builder = _InspectingBuilder()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = _run_pinned(
                FIXTURES,
                output,
                builder=builder,
                task_ids=("shipping-boundary",),
                allow_custom_test_double=True,
            )
            self.assertEqual("partial-development", result.status)
            self.assertEqual(2, len(builder.views))
            for view in builder.views:
                self.assertNotIn("program", view.__dataclass_fields__)
                self.assertNotIn("checker_id", view.__dataclass_fields__)
                self.assertNotIn("sealed-check.json", view.visible_files)
                self.assertTrue(view.hidden_check_digest.startswith("sha256:"))
                self.assertEqual(QUALIFICATION, view.qualification)
            sealed = json.loads(
                (FIXTURES / "shipping-boundary" / "sealed-check.json").read_text(
                    encoding="utf-8"
                )
            )
            output_bytes = b"".join(
                path.read_bytes() for path in output.rglob("*") if path.is_file()
            )
            self.assertNotIn(sealed["program"].encode("utf-8"), output_bytes)

    def test_scope_guards_reject_test_evaluator_harness_and_other_writes(self) -> None:
        attacks = (
            (
                CandidateProposal(
                    "weaken-assertion",
                    {"tests/test_shipping.py": "def check() -> None:\n    pass\n"},
                    "Remove the public assertion.",
                ),
                "public-test-modification-or-assertion-weakening",
            ),
            (
                CandidateProposal(
                    "delete-public-test",
                    {"shipping.py": WINNING_SHIPPING},
                    "Delete the failing public test.",
                    deletions=("tests/test_shipping.py",),
                ),
                "public-test-deletion-or-assertion-weakening",
            ),
            (
                CandidateProposal(
                    "replace-evaluator",
                    {"evaluator/check.py": "passed = True\n"},
                    "Replace evaluator logic.",
                ),
                "evaluator-or-harness-path-is-protected",
            ),
            (
                CandidateProposal(
                    "replace-harness",
                    {"harness/run.py": "passed = True\n"},
                    "Replace harness logic.",
                ),
                "evaluator-or-harness-path-is-protected",
            ),
            (
                CandidateProposal(
                    "extra-write",
                    {
                        "shipping.py": WINNING_SHIPPING,
                        "outside.py": "surprise = True\n",
                    },
                    "Write beyond the sealed task scope.",
                ),
                "candidate-write-is-outside-sealed-scope",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (proposal, reason) in enumerate(attacks):
                with self.subTest(proposal=proposal.proposal_id):
                    result = _run_pinned(
                        FIXTURES,
                        root / f"attack-{index}",
                        builder=_OneProposalBuilder(proposal),
                        task_ids=("shipping-boundary",),
                        allow_custom_test_double=True,
                    )
                    task = result.task_runs[0]
                    self.assertEqual("failed", task.status)
                    self.assertTrue(
                        all(
                            attempt.disposition == "rejected"
                            for attempt in task.attempts
                        )
                    )
                    self.assertTrue(
                        all(attempt.reason == reason for attempt in task.attempts)
                    )
                    self.assertTrue(
                        all(
                            attempt.public_outcome.returncode is None
                            for attempt in task.attempts
                        )
                    )
                    self.assertTrue(
                        all(
                            attempt.hidden_outcome.returncode is None
                            for attempt in task.attempts
                        )
                    )

    def test_wrong_candidate_and_forged_receipt_claims_fail_before_evaluation(
        self,
    ) -> None:
        forged = (
            (
                CandidateProposal(
                    "wrong-candidate-claim",
                    {"shipping.py": WINNING_SHIPPING},
                    "Claim another candidate.",
                    claimed_candidate_digest="sha256:" + "a" * 64,
                ),
                "claimed-candidate-digest-does-not-bind-exact-candidate",
            ),
            (
                CandidateProposal(
                    "forged-effect-receipt",
                    {"shipping.py": WINNING_SHIPPING},
                    "Claim a receipt the effect gateway did not issue.",
                    claimed_effect_receipts=("sha256:" + "b" * 64,),
                ),
                "claimed-effect-receipts-are-forged-or-mismatched",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (proposal, reason) in enumerate(forged):
                with self.subTest(proposal=proposal.proposal_id):
                    result = _run_pinned(
                        FIXTURES,
                        root / f"forgery-{index}",
                        builder=_OneProposalBuilder(proposal),
                        task_ids=("shipping-boundary",),
                        allow_custom_test_double=True,
                    )
                    for attempt in result.task_runs[0].attempts:
                        self.assertEqual("rejected", attempt.disposition)
                        self.assertEqual(reason, attempt.reason)
                        self.assertGreater(len(attempt.effects), 0)
                        self.assertIsNone(attempt.public_outcome.returncode)
                        self.assertIsNone(attempt.hidden_outcome.returncode)

    def test_baseline_already_green_is_rejected_even_when_resealed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            shutil.copytree(FIXTURES, fixtures)
            task = fixtures / "shipping-boundary"
            (task / "repository" / "shipping.py").write_text(
                WINNING_SHIPPING, encoding="utf-8"
            )
            manifest_path = task / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["baseline_tree_digest"] = tree_digest(task / "repository")
            manifest["task_contract_digest"] = _task_contract_digest(manifest)
            _write_json(manifest_path, manifest)
            expected = _reseal_root_manifest(fixtures)
            with self.assertRaisesRegex(
                CorpusDefinitionError, "baseline-already-green"
            ):
                run_code_qa_corpus(
                    fixtures,
                    root / "run",
                    expected_bundle_digest=expected,
                )

    def test_fixture_and_hidden_checker_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hidden_fixtures = root / "hidden-fixtures"
            shutil.copytree(FIXTURES, hidden_fixtures)
            hidden_task = hidden_fixtures / "shipping-boundary"
            sealed_path = hidden_task / "sealed-check.json"
            sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
            sealed["program"] = "assert True"
            sealed_path.write_text(json.dumps(sealed, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(
                CorpusDefinitionError, "file inventory mismatch"
            ):
                _run_pinned(hidden_fixtures, root / "hidden-run")

            public_fixtures = root / "public-fixtures"
            shutil.copytree(FIXTURES, public_fixtures)
            public_task = public_fixtures / "shipping-boundary"
            public_test = public_task / "repository" / "tests" / "test_shipping.py"
            public_test.write_text("def check() -> None:\n    pass\n", encoding="utf-8")
            with self.assertRaisesRegex(
                CorpusDefinitionError, "file inventory mismatch"
            ):
                _run_pinned(public_fixtures, root / "public-run")

    def test_objective_inversion_changes_task_and_bundle_pins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            shutil.copytree(FIXTURES, fixtures)
            manifest_path = fixtures / "shipping-boundary" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            original_contract = manifest["task_contract_digest"]
            manifest["objective"] = (
                "Invert the contract: classify every non-negative weight through 10 "
                "as freight."
            )
            changed_contract = _task_contract_digest(manifest)
            self.assertNotEqual(original_contract, changed_contract)
            manifest["task_contract_digest"] = changed_contract
            _write_json(manifest_path, manifest)
            changed_bundle = _reseal_root_manifest(fixtures)
            self.assertNotEqual(PINNED_CORPUS_BUNDLE_DIGEST, changed_bundle)
            with self.assertRaisesRegex(
                CorpusDefinitionError, "expected.*digest mismatch"
            ):
                _run_pinned(fixtures, root / "run")

    def test_external_pin_is_required_and_unpinned_escape_stays_same_trust(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                CorpusDefinitionError, "expected.*digest is required"
            ):
                run_code_qa_corpus(FIXTURES, root / "missing-pin")
            self.assertFalse((root / "missing-pin").exists())
            with self.assertRaisesRegex(
                CorpusDefinitionError, "expected.*digest mismatch"
            ):
                run_code_qa_corpus(
                    FIXTURES,
                    root / "wrong-pin",
                    expected_bundle_digest="sha256:" + "f" * 64,
                    allow_unpinned_local_test_double=True,
                )
            unpinned = run_code_qa_corpus(
                FIXTURES,
                root / "explicit-local",
                allow_unpinned_local_test_double=True,
            )
            self.assertEqual("succeeded", unpinned.status)
            self.assertEqual(
                "explicit-unpinned-same-trust-local-development", unpinned.pin_mode
            )
            self.assertEqual(TRUST_MODEL, unpinned.trust_model)
            self.assertFalse(unpinned.independent_evaluator)
            self.assertFalse(unpinned.adaptive_intelligence)
            self.assertFalse(unpinned.operationally_qualified)
            self.assertTrue(any("unsandboxed" in item for item in unpinned.limitations))

    def test_custom_builder_requires_explicit_test_double_opt_in_and_is_capped(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                CorpusDefinitionError, "custom Builder.*opt-in"
            ):
                _run_pinned(
                    FIXTURES,
                    root / "denied",
                    builder=_InspectingBuilder(),
                    task_ids=("shipping-boundary",),
                )
            self.assertFalse((root / "denied").exists())
            allowed = _run_pinned(
                FIXTURES,
                root / "allowed",
                builder=_InspectingBuilder(),
                task_ids=("shipping-boundary",),
                allow_custom_test_double=True,
            )
            self.assertEqual("partial-development", allowed.status)
            self.assertEqual("partial-development", allowed.scope)
            self.assertFalse(allowed.operationally_qualified)
            self.assertEqual(QUALIFICATION, allowed.qualification)

    def test_root_manifest_rejects_task_omissions_extras_and_root_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            omitted = root / "omitted"
            shutil.copytree(FIXTURES, omitted)
            shutil.rmtree(omitted / "tag-parser")
            with self.assertRaisesRegex(
                CorpusDefinitionError, "directory inventory mismatch"
            ):
                _run_pinned(omitted, root / "omitted-run")

            extra = root / "extra"
            shutil.copytree(FIXTURES, extra)
            shutil.copytree(extra / "shipping-boundary", extra / "unlisted-extra-task")
            with self.assertRaisesRegex(
                CorpusDefinitionError, "directory inventory mismatch"
            ):
                _run_pinned(extra, root / "extra-run")

            root_file = root / "root-file"
            shutil.copytree(FIXTURES, root_file)
            (root_file / "notes.txt").write_text("not declared\n", encoding="utf-8")
            with self.assertRaisesRegex(CorpusDefinitionError, "unexpected root file"):
                _run_pinned(root_file, root / "root-file-run")

    def test_duplicate_json_keys_and_windows_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            shutil.copytree(FIXTURES, fixtures)
            manifest_path = fixtures / "corpus-manifest.json"
            text = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text(
                text.replace(
                    '"schema_version": 2,',
                    '"schema_version": 2,\n  "schema_version": 2,',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CorpusDefinitionError, "invalid corpus document"
            ):
                _run_pinned(fixtures, root / "run")
        with self.assertRaisesRegex(CorpusDefinitionError, "casefold alias collision"):
            _assert_casefold_unique(("Task/file.py", "task/file.py"))
        with self.assertRaisesRegex(CorpusDefinitionError, "unsafe Windows alias"):
            _assert_casefold_unique(("task/file.py.",))

    def test_symbolic_link_in_corpus_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            shutil.copytree(FIXTURES, fixtures)
            link = fixtures / "linked-task"
            try:
                os.symlink(
                    fixtures / "shipping-boundary", link, target_is_directory=True
                )
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with self.assertRaisesRegex(
                CorpusDefinitionError, "link, junction, or reparse"
            ):
                _run_pinned(fixtures, root / "run")

    @unittest.skipUnless(os.name == "nt", "NTFS junction regression")
    def test_windows_junction_in_corpus_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            target = root / "junction-target"
            shutil.copytree(FIXTURES, fixtures)
            target.mkdir()
            junction = fixtures / "junction-task"
            created = subprocess.run(
                ("cmd", "/c", "mklink", "/J", str(junction), str(target)),
                capture_output=True,
                check=False,
                text=True,
            )
            if created.returncode != 0:
                self.skipTest(f"directory junctions unavailable: {created.stderr}")
            try:
                with self.assertRaisesRegex(
                    CorpusDefinitionError, "link, junction, or reparse"
                ):
                    _run_pinned(fixtures, root / "run")
            finally:
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "NTFS junction regression")
    def test_windows_junction_ancestor_of_fixture_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target_parent = root / "target-parent"
            target_parent.mkdir()
            shutil.copytree(FIXTURES, target_parent / "fixtures")
            junction_parent = root / "junction-parent"
            created = subprocess.run(
                (
                    "cmd",
                    "/c",
                    "mklink",
                    "/J",
                    str(junction_parent),
                    str(target_parent),
                ),
                capture_output=True,
                check=False,
                text=True,
            )
            if created.returncode != 0:
                self.skipTest(f"directory junctions unavailable: {created.stderr}")
            try:
                with self.assertRaisesRegex(
                    CorpusDefinitionError, "traverses a link, junction, or reparse"
                ):
                    _run_pinned(junction_parent / "fixtures", root / "ancestor-run")
            finally:
                os.rmdir(junction_parent)

    def test_run_receipts_preserve_losing_outcomes_without_hidden_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = _run_pinned(FIXTURES, output, task_ids=("inventory-aggregation",))
            task = result.task_runs[0]
            losing = task.attempts[0]
            persisted = json.loads(
                (
                    output / task.task_id / "attempt-01" / "attempt-record.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(losing.record_digest, persisted["record_digest"])
            self.assertTrue(persisted["public_outcome"]["passed"])
            self.assertFalse(persisted["hidden_outcome"]["passed"])
            self.assertNotIn("program", persisted["hidden_outcome"])
            self.assertNotIn("expected", persisted["hidden_outcome"])
            self.assertEqual(
                "candidate-failed-one-or-more-independent-checks", persisted["reason"]
            )


if __name__ == "__main__":
    unittest.main()
