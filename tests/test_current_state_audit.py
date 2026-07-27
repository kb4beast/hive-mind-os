from __future__ import annotations

import copy
import json
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hive_mind_os.current_state_audit import (
    AuditVerificationContext,
    CommandObservation,
    _artifact_docket_projection_digest,
    _broken_references,
    _parse_test_result,
    build_audit_verification_context,
    collect_current_state_audit,
    create_audit_artifact,
    execute_command,
    write_audit_artifact,
)
from hive_mind_os.current_state_audit import (
    verify_audit_artifact as _verify_audit_artifact,
)

_TEST_SOURCE_COVERAGE = {
    "source_id": "SRC-001",
    "kind": "paper",
    "status": "verified",
    "version_ref": "v1",
    "object_type": "paper_version",
    "retrieved_at": "2026-07-27T00:00:00Z",
    "license_spdx": "MIT",
    "content_digest": None,
    "unverified_digest_label": None,
    "provenance_complete": True,
    "requires_complete_ingestion": False,
    "snapshot_ref": None,
    "claim_ids": ["CLM-001"],
    "blocking_issues": [],
}
_TEST_CLAIMS_BY_MATURITY = {
    "specified": ["CLM-001"],
    "structurally_prototyped": [],
    "executed_in_isolation": [],
    "independently_verified_e2e": [],
    "production_proven": [],
}
_TEST_DOCKET_INVENTORY_DIGEST = f"sha256:{'d' * 64}"
_TEST_VERIFICATION_CONTEXT = AuditVerificationContext(
    repository_head="a" * 40,
    tracked_tree_digest=f"sha256:{'b' * 64}",
    docket_inventory_digest=_TEST_DOCKET_INVENTORY_DIGEST,
    docket_projection_digest=_artifact_docket_projection_digest(
        {
            "source_coverage": [_TEST_SOURCE_COVERAGE],
            "implementation_state_audit": {
                "claims_by_maturity": _TEST_CLAIMS_BY_MATURITY
            },
        }
    ),
    source_count=1,
    claim_count=1,
    working_tree_clean=True,
)


def verify_audit_artifact(
    artifact: object,
    *,
    signing_key: bytes | None = None,
) -> tuple[bool, tuple[str, ...]]:
    return _verify_audit_artifact(
        artifact,  # type: ignore[arg-type]
        signing_key=signing_key,
        verification_context=_TEST_VERIFICATION_CONTEXT,
    )


class CurrentStateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[1]

    def valid_audit(self, **overrides) -> dict[str, object]:
        head = "a" * 40
        audit: dict[str, object] = {
            "schema_version": 6,
            "artifact_type": "CurrentStateAudit",
            "repository": {
                "root": str(self.repository),
                "head": head,
                "working_tree_clean": True,
                "working_tree_entries": [],
                "post_test_head": head,
                "post_test_working_tree_clean": True,
                "post_test_working_tree_entries": [],
                "final_head": head,
                "final_working_tree_clean": True,
                "final_working_tree_entries": [],
                "tracked_tree_digest": f"sha256:{'b' * 64}",
            },
            "docket": {
                "source_count": 1,
                "claim_count": 1,
                "inventory_digest": _TEST_DOCKET_INVENTORY_DIGEST,
                "source_status_counts": {"verified": 1},
                "capability_maturity_counts": {"specified": 1},
                "inventory_complete": True,
                "release_ready": True,
                "source_blockers": [],
                "issues": [],
                "machine_blocked_claim_ids": [],
                "source_coverage": [copy.deepcopy(_TEST_SOURCE_COVERAGE)],
                "implementation_state_audit": {
                    "maturity_scale": [
                        "specified",
                        "structurally_prototyped",
                        "executed_in_isolation",
                        "independently_verified_e2e",
                        "production_proven",
                    ],
                    "maturity_counts": {"specified": 1},
                    "claims_by_maturity": copy.deepcopy(
                        _TEST_CLAIMS_BY_MATURITY
                    ),
                    "evidence_classes": {
                        "typed_domain_prototype": [],
                        "production_proof": [],
                    },
                },
                "broken_references": [],
                "receipts_valid": True,
                "reference_receipts": [
                    {
                        "claim_id": "CLM-1",
                        "kind": "test",
                        "reference": "tests/test_example.py",
                        "path_valid": True,
                        "digest": f"sha256:{'c' * 64}",
                        "execution": {"status": "passed"},
                        "valid": True,
                        "issues": [],
                    }
                ],
            },
            "tests": {"status": "passed", "passed": 1, "failed": 0, "errors": 0},
            "commands": [
                {
                    "command": ["python", "-m", "pytest", "-q"],
                    "cwd": str(self.repository),
                    "return_code": 0,
                    "stdout": "1 passed",
                    "stderr": "",
                    "timed_out": False,
                    "output_truncated": False,
                    "drain_incomplete": False,
                }
            ],
            "failures": [],
            "complete": True,
        }
        audit.update(overrides)
        return audit

    def test_collects_repository_docket_without_broken_receipts_or_running_tests(self) -> None:
        audit = collect_current_state_audit(
            self.repository,
            run_tests=False,
            generated_at=datetime(2026, 7, 27, tzinfo=UTC),
            invocation=("hive-mind", "audit", "--skip-tests"),
        )

        self.assertEqual(audit["artifact_type"], "CurrentStateAudit")
        self.assertGreaterEqual(audit["repository"]["full_ref_commit_count"], 79)
        self.assertEqual(audit["schema_version"], 6)
        self.assertEqual(audit["docket"]["source_count"], 23)
        self.assertEqual(audit["docket"]["claim_count"], 84)
        self.assertTrue(audit["docket"]["inventory_complete"])
        self.assertFalse(audit["docket"]["release_ready"])
        self.assertEqual(
            audit["docket"]["source_blockers"],
            [
                "SRC-001",
                "SRC-002",
                "SRC-005",
                "SRC-006",
                "SRC-007",
                "SRC-008",
                "SRC-009",
                "SRC-010",
                "SRC-011",
                "SRC-012",
                "SRC-013",
                "SRC-014",
                "SRC-015",
                "SRC-016",
                "SRC-017",
                "SRC-018",
                "SRC-019",
                "SRC-020",
                "SRC-022",
                "SRC-023",
            ],
        )
        self.assertEqual(len(audit["docket"]["source_coverage"]), 23)
        self.assertTrue(audit["docket"]["machine_blocked_claim_ids"])
        self.assertEqual(
            audit["docket"]["implementation_state_audit"]["claims_by_maturity"][
                "production_proven"
            ],
            [],
        )
        self.assertEqual(audit["docket"]["broken_references"], [])
        self.assertFalse(audit["docket"]["receipts_valid"])
        policy_receipts = [
            item
            for item in audit["docket"]["reference_receipts"]
            if item["reference"] == "tests/test_policy_invariants.py"
        ]
        self.assertTrue(policy_receipts)
        self.assertTrue(all(item["path_valid"] and item["digest"] for item in policy_receipts))
        self.assertTrue(
            all(item["execution"]["status"] == "not_run" for item in policy_receipts)
        )
        self.assertEqual(audit["tests"]["status"], "not_run")
        self.assertFalse(audit["complete"])
        context = build_audit_verification_context(self.repository)
        valid, issues = _verify_audit_artifact(
            create_audit_artifact(audit),
            verification_context=context,
        )
        if context.working_tree_clean:
            self.assertTrue(valid, issues)
        else:
            self.assertFalse(valid)
            self.assertIn("trusted repository worktree is not clean", issues)

    def test_broken_reference_detector_rejects_missing_and_escaping_paths(self) -> None:
        claim = SimpleNamespace(
            id="CLM-TEST",
            architecture_refs=(),
            code_refs=("missing.py", "../outside.py"),
            test_refs=(),
            benchmark_refs=(),
        )
        docket = SimpleNamespace(claims=(claim,))
        broken = _broken_references(docket, self.repository)
        reasons = {item["reason"] for item in broken}
        self.assertIn("referenced file does not exist", reasons)
        self.assertIn("path must not contain empty, current, or parent segments", reasons)

    def test_free_form_success_text_is_not_a_test_receipt(self) -> None:
        command = ("python", "-c", "print('999 passed')")
        observation = CommandObservation(
            command=command,
            cwd=str(self.repository),
            return_code=0,
            stdout="999 passed\n",
            stderr="",
        )
        result = _parse_test_result(observation)
        self.assertEqual(result["status"], "unverified")

    def test_zero_exit_failed_or_mixed_pytest_summary_is_not_passing(self) -> None:
        command = (sys.executable, "-m", "pytest", "-q")
        for summary in ("1 failed\n", "1 passed, 2 failed\n", "1 error\n"):
            with self.subTest(summary=summary):
                observation = CommandObservation(
                    command=command,
                    cwd=str(self.repository),
                    return_code=0,
                    stdout=summary,
                    stderr="",
                )
                result = _parse_test_result(observation, expected_command=command)
                self.assertEqual(result["status"], "failed")

    def test_test_time_worktree_mutation_is_reported(self) -> None:
        status_calls = 0

        def executor(command, cwd):
            nonlocal status_calls
            command_tuple = tuple(command)
            if command_tuple[:4] == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
                status_calls += 1
                return CommandObservation(
                    command_tuple,
                    str(cwd),
                    0,
                    " M README.md\0" if status_calls == 2 else "",
                    "",
                )
            if len(command_tuple) >= 4 and command_tuple[1:4] == ("-m", "pytest", "-q"):
                return CommandObservation(command_tuple, str(cwd), 0, "1 passed\n", "")
            return execute_command(command_tuple, cwd)

        audit = collect_current_state_audit(
            self.repository,
            run_tests=True,
            generated_at=datetime(2026, 7, 27, tzinfo=UTC),
            executor=executor,
        )
        self.assertFalse(audit["complete"])
        self.assertFalse(audit["repository"]["post_test_working_tree_clean"])
        self.assertTrue(audit["repository"]["final_working_tree_clean"])
        self.assertIn(
            "worktree_changed_during_audit",
            {failure.get("kind") for failure in audit["failures"]},
        )

    def test_command_timeout_is_a_visible_failed_observation(self) -> None:
        with patch("hive_mind_os.current_state_audit.COMMAND_TIMEOUT_SECONDS", 0.01):
            observation = execute_command(
                (
                    sys.executable,
                    "-c",
                    "import time; time.sleep(1)",
                ),
                self.repository,
            )
        self.assertFalse(observation.succeeded)
        self.assertTrue(observation.timed_out)
        self.assertEqual(observation.return_code, 124)

    def test_command_output_limit_stops_and_rejects_verbose_process(self) -> None:
        with patch("hive_mind_os.current_state_audit.MAX_COMMAND_OUTPUT_BYTES", 32):
            observation = execute_command(
                (sys.executable, "-c", "print('x' * 10000)"),
                self.repository,
            )
        self.assertFalse(observation.succeeded)
        self.assertTrue(observation.output_truncated)
        self.assertLessEqual(
            len(observation.stdout.encode("utf-8"))
            + len(observation.stderr.encode("utf-8")),
            32,
        )

    def test_command_output_limit_is_shared_across_both_streams(self) -> None:
        with patch("hive_mind_os.current_state_audit.MAX_COMMAND_OUTPUT_BYTES", 32):
            observation = execute_command(
                (
                    sys.executable,
                    "-c",
                    "import sys; print('o' * 1000); print('e' * 1000, file=sys.stderr)",
                ),
                self.repository,
            )
        self.assertFalse(observation.succeeded)
        self.assertTrue(observation.output_truncated)
        self.assertLessEqual(
            len(observation.stdout.encode("utf-8"))
            + len(observation.stderr.encode("utf-8")),
            32,
        )

    def test_command_output_limit_applies_to_serialized_invalid_utf8(self) -> None:
        with patch("hive_mind_os.current_state_audit.MAX_COMMAND_OUTPUT_BYTES", 32):
            observation = execute_command(
                (
                    sys.executable,
                    "-c",
                    "import sys;sys.stdout.buffer.write(bytes([255])*32)",
                ),
                self.repository,
            )
        self.assertFalse(observation.succeeded)
        self.assertTrue(observation.output_truncated)
        self.assertLessEqual(
            len(json.dumps(observation.stdout, ensure_ascii=False)[1:-1].encode("utf-8"))
            + len(json.dumps(observation.stderr, ensure_ascii=False)[1:-1].encode("utf-8")),
            32,
        )

    def test_command_output_limit_counts_json_escape_expansion(self) -> None:
        for byte_value in (0, 1, 8, 9, 10, 13, 34, 92):
            with self.subTest(byte_value=byte_value), patch(
                "hive_mind_os.current_state_audit.MAX_COMMAND_OUTPUT_BYTES",
                32,
            ):
                observation = execute_command(
                    (
                        sys.executable,
                        "-c",
                        (
                            "import sys;"
                            f"data=bytes([{byte_value}])*16;"
                            "sys.stdout.buffer.write(data);sys.stdout.flush();"
                            "sys.stderr.buffer.write(data)"
                        ),
                    ),
                    self.repository,
                )
            serialized_size = len(
                json.dumps(observation.stdout, ensure_ascii=False)[1:-1].encode("utf-8")
            ) + len(
                json.dumps(observation.stderr, ensure_ascii=False)[1:-1].encode("utf-8")
            )
            self.assertFalse(observation.succeeded)
            self.assertTrue(observation.output_truncated)
            self.assertLessEqual(serialized_size, 32)

    def test_timeout_terminates_descendants_that_inherit_output_pipes(self) -> None:
        command = (
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                "time.sleep(30)"
            ),
        )
        started = time.perf_counter()
        with patch("hive_mind_os.current_state_audit.COMMAND_TIMEOUT_SECONDS", 0.05):
            observation = execute_command(command, self.repository)
        self.assertLess(time.perf_counter() - started, 3)
        self.assertTrue(observation.timed_out)
        self.assertFalse(observation.succeeded)

    def test_output_cap_terminates_descendants_that_inherit_output_pipes(self) -> None:
        command = (
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                "print('x'*10000,flush=True);time.sleep(30)"
            ),
        )
        started = time.perf_counter()
        with patch("hive_mind_os.current_state_audit.MAX_COMMAND_OUTPUT_BYTES", 32):
            observation = execute_command(command, self.repository)
        self.assertLess(time.perf_counter() - started, 3)
        self.assertTrue(observation.output_truncated)
        self.assertFalse(observation.succeeded)

    def test_successful_parent_exit_still_terminates_pipe_retaining_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "descendant-survived.txt"
            child_code = (
                "import pathlib,time;"
                "time.sleep(2);"
                f"pathlib.Path({str(sentinel)!r}).write_text('survived')"
            )
            parent_code = (
                "import subprocess,sys;"
                f"subprocess.Popen([sys.executable,'-c',{child_code!r}])"
            )
            started = time.perf_counter()
            observation = execute_command(
                (sys.executable, "-c", parent_code),
                self.repository,
            )
            self.assertLess(time.perf_counter() - started, 3)
            self.assertTrue(observation.succeeded)
            self.assertFalse(observation.drain_incomplete)
            time.sleep(2.2)
            self.assertFalse(sentinel.exists())

    def test_unrecognized_overall_pytest_result_cannot_complete(self) -> None:
        status_calls = 0

        def executor(command, cwd):
            nonlocal status_calls
            command_tuple = tuple(command)
            if command_tuple[:4] == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
                status_calls += 1
                return CommandObservation(command_tuple, str(cwd), 0, "", "")
            if command_tuple == (sys.executable, "-m", "pytest", "-q"):
                return CommandObservation(command_tuple, str(cwd), 0, "done\n", "")
            if len(command_tuple) >= 4 and command_tuple[1:4] == ("-m", "pytest", "-q"):
                return CommandObservation(command_tuple, str(cwd), 0, "1 passed\n", "")
            return execute_command(command_tuple, cwd)

        audit = collect_current_state_audit(
            self.repository,
            run_tests=True,
            generated_at=datetime(2026, 7, 27, tzinfo=UTC),
            executor=executor,
        )
        self.assertEqual(status_calls, 3)
        self.assertEqual(audit["tests"]["status"], "failed")
        self.assertFalse(audit["complete"])
        self.assertIn(
            "unrecognized_test_result",
            {failure.get("kind") for failure in audit["failures"]},
        )

    def test_digest_detects_mutation(self) -> None:
        artifact = create_audit_artifact(self.valid_audit(value="original"))
        valid, issues = verify_audit_artifact(artifact)
        self.assertTrue(valid, issues)

        mutated = copy.deepcopy(artifact)
        mutated["audit"]["value"] = "substituted"
        valid, issues = verify_audit_artifact(mutated)
        self.assertFalse(valid)
        self.assertIn("audit digest mismatch", issues)

    def test_lone_surrogate_in_untrusted_artifact_fails_closed(self) -> None:
        audit = self.valid_audit()
        audit["commands"][0]["stdout"] = "\ud800"
        artifact = {
            "audit": audit,
            "integrity": {
                "canonicalization": "json-sort-keys-utf8-v1",
                "digest": f"sha256:{'0' * 64}",
                "signature": None,
            },
        }
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertEqual(
            issues,
            ("artifact contains an invalid Unicode scalar value",),
        )

    def test_noncanonical_json_values_fail_closed(self) -> None:
        for invalid_artifact in (None, [], "not-an-object", 3):
            with self.subTest(invalid_artifact=invalid_artifact):
                valid, issues = verify_audit_artifact(invalid_artifact)
                self.assertFalse(valid)
                self.assertEqual(issues, ("artifact must be an object",))

        for invalid_value in (float("nan"), b"not-json"):
            with self.subTest(invalid_value=invalid_value):
                audit = self.valid_audit(invalid_value=invalid_value)
                artifact = {
                    "audit": audit,
                    "integrity": {
                        "canonicalization": "json-sort-keys-utf8-v1",
                        "digest": f"sha256:{'0' * 64}",
                        "signature": None,
                    },
                }
                valid, issues = verify_audit_artifact(artifact)
                self.assertFalse(valid)
                self.assertIn("artifact is not canonical JSON", issues)

                for location in ("envelope", "integrity"):
                    valid_artifact = create_audit_artifact(self.valid_audit())
                    if location == "envelope":
                        valid_artifact["extra"] = invalid_value
                    else:
                        valid_artifact["integrity"]["extra"] = invalid_value
                    valid, issues = verify_audit_artifact(valid_artifact)
                    self.assertFalse(valid)
                    self.assertIn("artifact is not canonical JSON", issues)

        cyclic_audit = self.valid_audit()
        cyclic_audit["cycle"] = cyclic_audit
        cyclic_artifact = {
            "audit": cyclic_audit,
            "integrity": {
                "canonicalization": "json-sort-keys-utf8-v1",
                "digest": f"sha256:{'0' * 64}",
                "signature": None,
            },
        }
        valid, issues = verify_audit_artifact(cyclic_artifact)
        self.assertFalse(valid)
        self.assertTrue(issues)

        for location in ("envelope", "integrity"):
            cyclic_envelope = create_audit_artifact(self.valid_audit())
            if location == "envelope":
                cyclic_envelope["cycle"] = cyclic_envelope
            else:
                cyclic_envelope["integrity"]["cycle"] = cyclic_envelope["integrity"]
            valid, issues = verify_audit_artifact(cyclic_envelope)
            self.assertFalse(valid)
            self.assertTrue(issues)

        deeply_nested: object = "leaf"
        for _ in range(256):
            deeply_nested = [deeply_nested]
        deep_audit = self.valid_audit(deeply_nested=deeply_nested)
        deep_artifact = create_audit_artifact(deep_audit)
        valid, issues = verify_audit_artifact(deep_artifact)
        self.assertFalse(valid)
        self.assertEqual(issues, ("artifact exceeds maximum nesting depth",))

        shared_tail: object = "leaf"
        for _ in range(100):
            shared_tail = [shared_tail]
        deep_wrapper: object = shared_tail
        for _ in range(30):
            deep_wrapper = [deep_wrapper]
        shared_audit = self.valid_audit(
            shallow_path=shared_tail,
            deep_path=deep_wrapper,
        )
        shared_artifact = create_audit_artifact(shared_audit)
        valid, issues = verify_audit_artifact(shared_artifact)
        self.assertFalse(valid)
        self.assertEqual(issues, ("artifact exceeds maximum nesting depth",))

    def test_optional_signature_requires_matching_key(self) -> None:
        artifact = create_audit_artifact(
            self.valid_audit(),
            signing_key=b"test-only-key",
            signing_key_id="test-key-1",
        )
        valid, issues = verify_audit_artifact(artifact, signing_key=b"test-only-key")
        self.assertTrue(valid, issues)

        valid, issues = verify_audit_artifact(artifact, signing_key=b"wrong-key")
        self.assertFalse(valid)
        self.assertIn("audit signature mismatch", issues)

    def test_unknown_schema_is_not_verified(self) -> None:
        artifact = create_audit_artifact(self.valid_audit(schema_version=7))
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

    def test_minimal_self_digested_payload_is_not_a_verified_audit(self) -> None:
        artifact = create_audit_artifact({"schema_version": 6})
        valid, issues = verify_audit_artifact(artifact)
        self.assertFalse(valid)
        self.assertIn("artifact type must be CurrentStateAudit", issues)

        underspecified = {
            "schema_version": 6,
            "artifact_type": "CurrentStateAudit",
            "repository": {},
            "docket": {},
            "tests": {},
            "commands": [],
            "failures": [],
            "complete": True,
        }
        valid, issues = verify_audit_artifact(create_audit_artifact(underspecified))
        self.assertFalse(valid)
        self.assertIn("audit repository head is invalid", issues)
        self.assertIn("audit contains no command observations", issues)
        self.assertIn("complete audit requires passing tests", issues)

    def test_version_two_shape_is_preserved_but_not_currently_verified(self) -> None:
        fixture = self.repository / "tests" / "fixtures" / "current_state_audit_v2_payload.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        valid, issues = verify_audit_artifact(create_audit_artifact(payload))
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

    def test_version_three_shape_is_preserved_but_not_currently_verified(self) -> None:
        fixture = self.repository / "tests" / "fixtures" / "current_state_audit_v3_payload.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        valid, issues = verify_audit_artifact(create_audit_artifact(payload))
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

    def test_boolean_schema_and_contradictory_complete_audit_are_rejected(self) -> None:
        boolean_schema = create_audit_artifact(self.valid_audit(schema_version=True))
        valid, issues = verify_audit_artifact(boolean_schema)
        self.assertFalse(valid)
        self.assertIn("unsupported CurrentStateAudit schema version", issues)

        contradictory = self.valid_audit()
        contradictory["repository"]["working_tree_clean"] = False
        contradictory["repository"]["working_tree_entries"] = [" M file.py"]
        contradictory["tests"]["status"] = "failed"
        contradictory["docket"]["receipts_valid"] = False
        contradictory["failures"] = [{"kind": "test_failure"}]
        valid, issues = verify_audit_artifact(create_audit_artifact(contradictory))
        self.assertFalse(valid)
        self.assertIn("complete audit requires a clean repository", issues)
        self.assertIn("complete audit requires passing tests", issues)
        self.assertIn("complete audit requires valid reference receipts", issues)
        self.assertIn("complete audit cannot contain failures", issues)

        contradictory_counts = self.valid_audit()
        contradictory_counts["tests"].update(
            {"status": "passed", "passed": 1, "failed": 2, "errors": 0}
        )
        valid, issues = verify_audit_artifact(
            create_audit_artifact(contradictory_counts)
        )
        self.assertFalse(valid)
        self.assertIn(
            "audit passing test result contains failures or errors",
            issues,
        )

        oversized_output = self.valid_audit()
        oversized_output["commands"][0]["stdout"] = "\0" * 166_667
        valid, issues = verify_audit_artifact(
            create_audit_artifact(oversized_output)
        )
        self.assertFalse(valid)
        self.assertIn(
            "audit command observation 0 exceeds the output budget",
            issues,
        )

        deep_contradiction = self.valid_audit()
        receipt = deep_contradiction["docket"]["reference_receipts"][0]
        receipt["path_valid"] = False
        receipt["execution"] = {"status": "failed"}
        receipt["issues"] = ["missing"]
        receipt["valid"] = True
        valid, issues = verify_audit_artifact(create_audit_artifact(deep_contradiction))
        self.assertFalse(valid)
        self.assertIn("audit reference receipt 0 validity is contradictory", issues)

    def test_schema6_rejects_fabricated_coverage_blockers_and_maturity(self) -> None:
        duplicate_coverage = self.valid_audit()
        duplicate_coverage["docket"]["source_count"] = 2
        duplicate_coverage["docket"]["source_status_counts"] = {"verified": 2}
        duplicate_coverage["docket"]["source_coverage"].append(
            copy.deepcopy(duplicate_coverage["docket"]["source_coverage"][0])
        )
        valid, issues = verify_audit_artifact(
            create_audit_artifact(duplicate_coverage)
        )
        self.assertFalse(valid)
        self.assertIn("audit source coverage contains duplicate sources", issues)

        missing_block = self.valid_audit()
        missing_block["docket"]["release_ready"] = True
        missing_block["docket"]["source_blockers"] = ["SRC-001"]
        missing_block["docket"]["source_coverage"][0]["blocking_issues"] = [
            "source license or reuse grant is unresolved",
            "dependent claim is machine-blocked by incomplete source evidence",
        ]
        missing_block["docket"]["issues"] = [
            {
                "severity": "blocking",
                "message": "source license or reuse grant is unresolved",
                "source_id": "SRC-001",
                "claim_id": None,
            },
            {
                "severity": "blocking",
                "message": (
                    "dependent claim is machine-blocked by incomplete source evidence"
                ),
                "source_id": "SRC-001",
                "claim_id": "CLM-001",
            },
        ]
        valid, issues = verify_audit_artifact(create_audit_artifact(missing_block))
        self.assertFalse(valid)
        self.assertIn(
            "audit machine-blocked claims contradict source evidence",
            issues,
        )
        self.assertIn(
            "audit release readiness contradicts blocking docket issues",
            issues,
        )

        fabricated_maturity = self.valid_audit()
        implementation = fabricated_maturity["docket"][
            "implementation_state_audit"
        ]
        implementation["claims_by_maturity"]["specified"] = []
        implementation["claims_by_maturity"]["production_proven"] = ["CLM-001"]
        implementation["maturity_counts"] = {"production_proven": 1}
        fabricated_maturity["docket"]["capability_maturity_counts"] = {
            "production_proven": 1
        }
        implementation["evidence_classes"]["production_proof"] = ["CLM-FAKE"]
        valid, issues = verify_audit_artifact(
            create_audit_artifact(fabricated_maturity)
        )
        self.assertFalse(valid)
        self.assertIn(
            "audit production proof contradicts production maturity",
            issues,
        )

        coordinated_removal = self.valid_audit()
        source = coordinated_removal["docket"]["source_coverage"][0]
        source.update(
            {
                "kind": "research_and_repository",
                "status": "partial",
                "version_ref": "arXiv:2407.16741",
                "object_type": "paper_version",
                "license_spdx": None,
                "provenance_complete": False,
                "requires_complete_ingestion": True,
            }
        )
        coordinated_removal["docket"]["issues"] = []
        coordinated_removal["docket"]["source_blockers"] = []
        coordinated_removal["docket"]["machine_blocked_claim_ids"] = []
        coordinated_removal["docket"]["release_ready"] = True
        source["blocking_issues"] = []
        valid, issues = verify_audit_artifact(
            create_audit_artifact(coordinated_removal)
        )
        self.assertFalse(valid)
        self.assertIn(
            "audit source coverage omits metadata-derived blockers: SRC-001",
            issues,
        )
        self.assertIn(
            "audit release readiness contradicts blocking docket issues",
            issues,
        )

        erased_inventory = self.valid_audit()
        erased_inventory["docket"].update(
            {
                "source_count": 0,
                "claim_count": 0,
                "source_status_counts": {},
                "capability_maturity_counts": {},
                "source_coverage": [],
                "issues": [],
                "source_blockers": [],
                "machine_blocked_claim_ids": [],
                "release_ready": True,
                "inventory_complete": True,
            }
        )
        erased_implementation = erased_inventory["docket"][
            "implementation_state_audit"
        ]
        erased_implementation["maturity_counts"] = {}
        erased_implementation["claims_by_maturity"] = {
            maturity: [] for maturity in _TEST_CLAIMS_BY_MATURITY
        }
        erased_implementation["evidence_classes"] = {
            "typed_domain_prototype": [],
            "production_proof": [],
        }
        valid, issues = verify_audit_artifact(
            create_audit_artifact(erased_inventory)
        )
        self.assertFalse(valid)
        self.assertIn("audit source count contradicts trusted context", issues)
        self.assertIn(
            "audit docket projection contradicts trusted context",
            issues,
        )

        fabricated_identity = self.valid_audit()
        fabricated_source = fabricated_identity["docket"]["source_coverage"][0]
        fabricated_source["source_id"] = "SRC-999"
        fabricated_source["claim_ids"] = ["CLM-999"]
        fabricated_identity["docket"]["implementation_state_audit"][
            "claims_by_maturity"
        ]["specified"] = ["CLM-999"]
        valid, issues = verify_audit_artifact(
            create_audit_artifact(fabricated_identity)
        )
        self.assertFalse(valid)
        self.assertIn(
            "audit docket projection contradicts trusted context",
            issues,
        )

        changed_repository = self.valid_audit()
        changed_repository["repository"]["head"] = "f" * 40
        changed_repository["repository"]["post_test_head"] = "f" * 40
        changed_repository["repository"]["final_head"] = "f" * 40
        valid, issues = verify_audit_artifact(
            create_audit_artifact(changed_repository)
        )
        self.assertFalse(valid)
        self.assertIn(
            "audit repository head contradicts trusted context",
            issues,
        )

        valid, issues = _verify_audit_artifact(
            create_audit_artifact(self.valid_audit())
        )
        self.assertFalse(valid)
        self.assertIn(
            "schema 6 audit verification requires a trusted context",
            issues,
        )

    def test_written_artifact_is_newline_terminated(self) -> None:
        artifact = create_audit_artifact(self.valid_audit())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            write_audit_artifact(artifact, output)
            self.assertTrue(output.read_bytes().endswith(b"\n"))
            with self.assertRaises(FileExistsError):
                write_audit_artifact(artifact, output)

    def test_interrupted_atomic_publish_leaves_destination_retryable(self) -> None:
        artifact = create_audit_artifact(self.valid_audit())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            with patch(
                "hive_mind_os.current_state_audit.os.link",
                side_effect=OSError("simulated publish interruption"),
            ):
                with self.assertRaises(OSError):
                    write_audit_artifact(artifact, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
            write_audit_artifact(artifact, output)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
