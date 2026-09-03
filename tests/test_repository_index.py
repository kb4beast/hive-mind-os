from __future__ import annotations

import unittest

from hive_mind_os.repository_index import (
    AnalyzerIdentity,
    RepositoryIndexer,
    RepositoryIndexError,
)
from hive_mind_os.resource_adapter import (
    ConservativeResourceAdapter,
    ResourceDescriptor,
    ResourceKind,
)
from hive_mind_os.subject_adapter import SubjectDescriptor, SubjectKind, SubjectSnapshot

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
NOW = "2026-09-02T00:00:00Z"


def _subject(snapshot_id: str, content_digest: str) -> SubjectSnapshot:
    subject = SubjectDescriptor(
        "repo-one",
        SubjectKind.REPOSITORY,
        "repo:one",
        ("analyze",),
        DIGEST_A,
        ("source:repo",),
    )
    return SubjectSnapshot(subject, snapshot_id, content_digest, NOW, ("receipt:tree",))


def _resource(resource_id: str, path: str, body: bytes):
    descriptor = ResourceDescriptor(
        "repo-one",
        resource_id,
        ResourceKind.REPOSITORY_PATH,
        path,
        "text/plain",
        False,
        None,
        ("source:repo",),
    )
    return ConservativeResourceAdapter().observe(
        descriptor, body, observed_at=NOW, evidence_refs=("receipt:blob",)
    )


def _analyzer(version: str = "1") -> AnalyzerIdentity:
    return AnalyzerIdentity("builtin.metadata", version, DIGEST_A, DIGEST_B)


class RepositoryIndexTests(unittest.TestCase):
    def test_exact_snapshot_index_reuses_changes_and_deletes_by_digest(self) -> None:
        indexer = RepositoryIndexer()
        first = indexer.build(
            _subject("tree:one", DIGEST_A),
            (
                _resource("a", "src/a.py", b"a=1\n"),
                _resource("b", "src/b.ts", b"b=1\n"),
            ),
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index-one",),
        )
        second = indexer.build(
            _subject("tree:two", DIGEST_B),
            (
                _resource("a", "src/a.py", b"a=1\n"),
                _resource("c", "src/c.go", b"package c\n"),
            ),
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index-two",),
            previous=first,
        )
        self.assertEqual(("a",), second.reused_resource_ids)
        self.assertEqual(("c",), second.changed_resource_ids)
        self.assertEqual(("b",), second.deleted_resource_ids)
        self.assertNotEqual(first.index_digest, second.index_digest)
        self.assertEqual("python", second.by_resource_id["a"].language)
        self.assertEqual("go", second.by_resource_id["c"].language)

    def test_identity_binds_analyzer_environment_snapshot_and_content(self) -> None:
        indexer = RepositoryIndexer()
        resources = (_resource("a", "src/a.py", b"a=1\n"),)
        baseline = indexer.build(
            _subject("tree:one", DIGEST_A),
            resources,
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index",),
        )
        changed_analyzer = indexer.build(
            _subject("tree:one", DIGEST_A),
            resources,
            _analyzer("2"),
            DIGEST_A,
            evidence_refs=("receipt:index",),
        )
        changed_environment = indexer.build(
            _subject("tree:one", DIGEST_A),
            resources,
            _analyzer(),
            DIGEST_B,
            evidence_refs=("receipt:index",),
        )
        self.assertEqual(
            3,
            len(
                {
                    baseline.index_digest,
                    changed_analyzer.index_digest,
                    changed_environment.index_digest,
                }
            ),
        )

    def test_index_contains_no_source_body_and_rejects_secret_like_paths(self) -> None:
        indexer = RepositoryIndexer()
        safe = indexer.build(
            _subject("tree:one", DIGEST_A),
            (_resource("a", "src/a.py", b"safe body"),),
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index",),
        )
        self.assertFalse(hasattr(safe.entries[0], "body"))
        with self.assertRaises(RepositoryIndexError):
            indexer.build(
                _subject("tree:two", DIGEST_B),
                (_resource("secret", ".env", b"ordinary-looking"),),
                _analyzer(),
                DIGEST_A,
                evidence_refs=("receipt:index",),
            )
        for locator in (".env?x", "dir/id_rsa#x"):
            with self.subTest(locator=locator), self.assertRaises(RepositoryIndexError):
                indexer._reject_sensitive_locator(locator)

    def test_cross_subject_prior_index_is_rejected(self) -> None:
        indexer = RepositoryIndexer()
        first = indexer.build(
            _subject("tree:one", DIGEST_A),
            (),
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index",),
        )
        foreign_descriptor = SubjectDescriptor(
            "repo-two",
            SubjectKind.REPOSITORY,
            "repo:two",
            ("analyze",),
            DIGEST_A,
            ("source:repo",),
        )
        foreign = SubjectSnapshot(
            foreign_descriptor, "tree:two", DIGEST_B, NOW, ("receipt:tree",)
        )
        with self.assertRaises(RepositoryIndexError):
            indexer.build(
                foreign,
                (),
                _analyzer(),
                DIGEST_A,
                evidence_refs=("receipt:index",),
                previous=first,
            )

    def test_same_bytes_under_changed_resource_identity_are_reanalyzed(self) -> None:
        indexer = RepositoryIndexer()
        first = indexer.build(
            _subject("tree:one", DIGEST_A),
            (_resource("a", "src/a.py", b"same bytes\n"),),
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index-one",),
        )
        moved = indexer.build(
            _subject("tree:two", DIGEST_B),
            (_resource("a", "src/a.js", b"same bytes\n"),),
            _analyzer(),
            DIGEST_A,
            evidence_refs=("receipt:index-two",),
            previous=first,
        )
        self.assertEqual((), moved.reused_resource_ids)
        self.assertEqual(("a",), moved.changed_resource_ids)
        self.assertEqual("javascript", moved.entries[0].language)
        self.assertNotEqual(
            first.entries[0].analysis_digest, moved.entries[0].analysis_digest
        )


if __name__ == "__main__":
    unittest.main()
