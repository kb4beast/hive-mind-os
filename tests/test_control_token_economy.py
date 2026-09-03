from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hive_mind_os.context_capsule import (
    ColdContextReference,
    ContextBody,
    ContextCapsuleError,
    NodeContextRoute,
    RoundCapsule,
    measure_context_savings,
)
from hive_mind_os.evidence_compaction import (
    EvidenceCompactionError,
    compact_evidence,
)
from hive_mind_os.test_result_cache import (
    CachedTestResult,
    CommandDescriptor,
    TestCacheError,
    TestCacheKey,
    TestOutcome,
    TestResultCache,
)
from hive_mind_os.wave_manifest import CandidateIdentity


def digest(character: str) -> str:
    return "sha256:" + character * 64


def make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt" or shutil.which("powershell") is None:
            raise unittest.SkipTest(
                f"directory links are unavailable: {symlink_error}"
            ) from symlink_error
    environment = os.environ.copy()
    environment["HIVE_CACHE_TEST_LINK"] = str(link)
    environment["HIVE_CACHE_TEST_TARGET"] = str(target)
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "New-Item -ItemType Junction -Path $env:HIVE_CACHE_TEST_LINK "
            "-Target $env:HIVE_CACHE_TEST_TARGET | Out-Null",
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise unittest.SkipTest(
            "directory links are unavailable: " + completed.stderr
        )


def remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
        return
    # The Windows fallback above creates a junction rather than a symbolic
    # link.  Junctions require directory removal on supported Python versions.
    os.rmdir(link)


def capsule() -> RoundCapsule:
    bodies = tuple(
        ContextBody(f"dep-{name}", "text/plain", name.encode() * 400)
        for name in ("a", "b", "c")
    )
    cold = ColdContextReference("history", digest("9"), 50_000, "objects/history.bin")
    return RoundCapsule(
        round_id="round-1",
        generation_id=digest("1"),
        plan_digest=digest("2"),
        manifest_digest=digest("3"),
        subject_id=digest("4"),
        subject_snapshot_digest=digest("5"),
        authority_digest=digest("6"),
        model_route_digest=digest("7"),
        budget_digest=digest("8"),
        shared_body=ContextBody("shared", "text/plain", b"shared-contract" * 100),
        direct_bodies=bodies,
        cold_references=(cold,),
        routes=tuple(
            NodeContextRoute(
                f"node-{name}",
                (f"dep-{name}",),
                ("history",),
                tuple(f"dep-{other}" for other in ("a", "b", "c") if other != name),
            )
            for name in ("a", "b", "c")
        ),
    )


def cache_key(**overrides) -> TestCacheKey:
    values = {
        "candidate": CandidateIdentity("a" * 40, "b" * 40, digest("4")),
        "command": CommandDescriptor(("python", "-m", "unittest"), "repo", None, 60),
        "test_set_digest": digest("1"),
        "semantic_locks": ("capability:test", "schema:result"),
        "configuration_digest": digest("2"),
        "toolchain_digest": digest("3"),
        "os_identity_digest": digest("5"),
        "safe_environment_digest": digest("6"),
    }
    values.update(overrides)
    return TestCacheKey(**values)


class ContextCapsuleTests(unittest.TestCase):
    def test_each_node_receives_only_direct_bodies_and_content_addressed_cold_refs(
        self,
    ) -> None:
        value = capsule()
        delta = value.node_delta(
            "node-a",
            node_contract_digest=digest("a"),
            objective_digest=digest("b"),
        )
        self.assertEqual([item.context_id for item in delta.direct_bodies], ["dep-a"])
        self.assertEqual(
            [item.context_id for item in delta.cold_references], ["history"]
        )
        self.assertEqual(set(delta.omitted_context_ids), {"dep-b", "dep-c"})
        self.assertNotIn("dep-b", [item.context_id for item in delta.direct_bodies])
        self.assertEqual(delta.capsule_digest, value.capsule_digest)

    def test_routes_must_disposition_every_item_exactly_once(self) -> None:
        value = capsule()
        with self.assertRaises(ContextCapsuleError):
            replace(
                value,
                routes=(
                    NodeContextRoute("node-a", ("dep-a",), ("history",), ("dep-b",)),
                ),
                capsule_digest="",
            )

    def test_measured_fixture_is_materially_smaller_than_naive_fanout(self) -> None:
        value = capsule()
        deltas = tuple(
            value.node_delta(
                f"node-{name}",
                node_contract_digest=digest(name),
                objective_digest=digest(str(index)),
            )
            for index, name in enumerate(("a", "b", "c"), start=1)
        )
        result = measure_context_savings(
            value,
            deltas,
            naive_envelopes=(b"n" * 20_000, b"n" * 20_000, b"n" * 20_000),
        )
        self.assertTrue(result.materially_lower)
        self.assertGreater(result.saved_bytes, 0)


class TestResultCacheTests(unittest.TestCase):
    def test_boolean_cache_schema_versions_are_rejected(self) -> None:
        key = cache_key()
        key_document = key.to_document()
        key_document["schema_version"] = True
        with self.assertRaisesRegex(TestCacheError, "unknown shape"):
            TestCacheKey.from_document(key_document)

        result = CachedTestResult(
            key,
            TestOutcome.PASSED,
            0,
            digest("7"),
            digest("8"),
        )
        result_document = result.to_document()
        result_document["schema_version"] = True
        with self.assertRaisesRegex(TestCacheError, "unknown shape"):
            CachedTestResult.from_document(result_document)

    def test_only_exact_passing_candidate_context_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = TestResultCache(directory)
            key = cache_key()
            result = CachedTestResult(
                key,
                TestOutcome.PASSED,
                0,
                digest("7"),
                digest("8"),
            )
            cache.publish(result)
            self.assertEqual(cache.lookup(key), result)
            changed_keys = (
                replace(
                    key, candidate=CandidateIdentity("a" * 40, "c" * 40, digest("4"))
                ),
                replace(
                    key,
                    command=CommandDescriptor(
                        ("python", "-m", "pytest"), "repo", None, 60
                    ),
                ),
                replace(key, test_set_digest=digest("9")),
                replace(key, semantic_locks=("capability:test",)),
                replace(key, configuration_digest=digest("9")),
                replace(key, toolchain_digest=digest("9")),
                replace(key, os_identity_digest=digest("9")),
                replace(key, safe_environment_digest=digest("9")),
            )
            for changed in changed_keys:
                with self.subTest(field=changed.digest):
                    self.assertIsNone(cache.lookup(changed))

    def test_failure_is_retained_but_not_reused_and_corruption_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = TestResultCache(directory)
            key = cache_key()
            failure = CachedTestResult(
                key,
                TestOutcome.FAILED,
                1,
                digest("7"),
                digest("8"),
            )
            failure_path = cache.publish(failure)
            self.assertTrue(failure_path.is_file())
            self.assertIsNone(cache.lookup(key))
            passing = CachedTestResult(
                key,
                TestOutcome.PASSED,
                0,
                digest("7"),
                digest("8"),
            )
            path = cache.publish(passing)
            self.assertEqual(cache.lookup(key), passing)
            path.write_bytes(b"{}")
            with self.assertRaises(TestCacheError):
                cache.lookup(key)

    def test_failure_publication_does_not_follow_a_failures_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cache"
            outside = Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            failures_link = root / "failures"
            make_directory_link(failures_link, outside)
            try:
                cache = TestResultCache(root)
                result = CachedTestResult(
                    cache_key(),
                    TestOutcome.FAILED,
                    1,
                    digest("7"),
                    digest("8"),
                )

                published = cache.publish(result)

                self.assertEqual(root.resolve(), published.parent)
                self.assertEqual([], list(outside.iterdir()))
            finally:
                remove_directory_link(failures_link)

    def test_cache_root_rejects_a_linked_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outside = base / "outside"
            linked = base / "linked"
            outside.mkdir()
            make_directory_link(linked, outside)
            try:
                with self.assertRaisesRegex(TestCacheError, "traverses"):
                    TestResultCache(linked / "cache")
            finally:
                remove_directory_link(linked)

    def test_cache_rejects_replacement_of_its_authenticated_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cache"
            displaced = Path(directory) / "displaced-cache"
            cache = TestResultCache(root)
            root.rename(displaced)
            root.mkdir()
            result = CachedTestResult(
                cache_key(),
                TestOutcome.PASSED,
                0,
                digest("7"),
                digest("8"),
            )

            with self.assertRaisesRegex(TestCacheError, "identity changed"):
                cache.publish(result)

    def test_semantic_locks_must_have_one_canonical_order(self) -> None:
        with self.assertRaises(ValueError):
            cache_key(semantic_locks=("z", "a"))

    def test_concurrent_publication_refuses_a_non_file_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = TestResultCache(directory)
            result = CachedTestResult(
                cache_key(),
                TestOutcome.PASSED,
                0,
                digest("7"),
                digest("8"),
            )

            def replace_with_directory(_source: str, destination: str) -> None:
                Path(destination).mkdir()
                raise FileExistsError(destination)

            with mock.patch(
                "hive_mind_os.test_result_cache.os.link",
                side_effect=replace_with_directory,
            ):
                with self.assertRaisesRegex(TestCacheError, "unsafe path"):
                    cache.publish(result)


class EvidenceCompactionTests(unittest.TestCase):
    def test_passing_logs_compact_with_full_raw_digest(self) -> None:
        raw = ("noise\n" * 100 + "Ran 4 tests\nOK\n").encode()
        result = compact_evidence(
            raw, outcome="passed", exit_code=0, passing_tail_lines=3
        )
        self.assertTrue(result.verify_raw(raw))
        self.assertLess(len(result.retained_lines), result.raw_line_count)
        self.assertIn("OK", result.retained_lines)
        self.assertIsNone(result.first_causal_error)

    def test_failure_retains_first_cause_and_every_distinct_material_error(
        self,
    ) -> None:
        raw = (
            "setup\nTraceback (most recent call last):\n"
            "ERROR alpha: missing receipt\nERROR alpha: missing receipt\n"
            "Caused by policy violation\nFAILED beta\n"
        ).encode()
        result = compact_evidence(raw, outcome="FAILED", exit_code=1)
        self.assertEqual(
            result.first_causal_error, "Traceback (most recent call last):"
        )
        self.assertIn("ERROR alpha: missing receipt", result.distinct_material_errors)
        self.assertIn("Caused by policy violation", result.distinct_material_errors)
        self.assertIn("FAILED beta", result.distinct_material_errors)
        self.assertEqual(
            result.distinct_material_errors.count("ERROR alpha: missing receipt"),
            1,
        )
        self.assertFalse(result.verify_raw(raw + b"tamper"))

    def test_unrecognized_failure_is_not_compacted_to_empty_and_bound_is_closed(
        self,
    ) -> None:
        result = compact_evidence(
            b"process disappeared\n", outcome="FAILED", exit_code=1
        )
        self.assertEqual(result.first_causal_error, "process disappeared")
        with self.assertRaises(EvidenceCompactionError):
            compact_evidence(
                b"1234", outcome="PASSED", exit_code=0, maximum_raw_bytes=3
            )
        with self.assertRaises(EvidenceCompactionError):
            compact_evidence(b"claimed pass", outcome="PASSED", exit_code=1)


if __name__ == "__main__":
    unittest.main()
