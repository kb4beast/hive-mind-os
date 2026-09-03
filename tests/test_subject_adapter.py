from __future__ import annotations

import unittest

from hive_mind_os.subject_adapter import (
    SubjectAdapterError,
    SubjectDescriptor,
    SubjectKind,
    SubjectSnapshot,
    require_snapshot_binding,
)

DIGEST = "sha256:" + "a" * 64


def _subject(kind: SubjectKind = SubjectKind.REPOSITORY) -> SubjectDescriptor:
    return SubjectDescriptor(
        "subject-one",
        kind,
        "subject://one",
        ("analyze", "snapshot"),
        DIGEST,
        ("evidence:subject",),
    )


class SubjectAdapterTests(unittest.TestCase):
    def test_every_supported_subject_kind_uses_the_same_contract(self) -> None:
        for kind in SubjectKind:
            subject = _subject(kind)
            self.assertEqual(kind, subject.kind)
            self.assertTrue(subject.identity_digest.startswith("sha256:"))

    def test_snapshot_binds_exact_subject_content_and_evidence(self) -> None:
        subject = _subject()
        first = SubjectSnapshot(
            subject,
            "tree:one",
            DIGEST,
            "2026-09-02T00:00:00Z",
            ("evidence:snapshot",),
        )
        repeated = SubjectSnapshot(
            subject,
            "tree:one",
            DIGEST,
            "2026-09-02T00:00:00Z",
            ("evidence:snapshot",),
        )
        self.assertEqual(first.snapshot_digest, repeated.snapshot_digest)
        self.assertIs(first, require_snapshot_binding(subject, first))

        replacement = _subject(SubjectKind.DATASET)
        with self.assertRaises(SubjectAdapterError):
            require_snapshot_binding(replacement, first)

    def test_mutable_or_unprovenanced_snapshots_fail_closed(self) -> None:
        with self.assertRaises(SubjectAdapterError):
            SubjectSnapshot(
                _subject(),
                "tree:one",
                DIGEST,
                "2026-09-02T00:00:00Z",
                ("evidence:snapshot",),
                immutable=False,
            )
        with self.assertRaises(SubjectAdapterError):
            SubjectDescriptor(
                "subject-one", SubjectKind.API, "https://example.test", (), DIGEST, ()
            )

    def test_snapshot_observation_requires_canonical_utc_rfc3339(self) -> None:
        for observed_at in (
            "not-a-time",
            "2026-09-02",
            "2026-09-02 00:00:00Z",
            "2026-09-02T00:00:00+00:00",
            "2026-13-02T00:00:00Z",
            " 2026-09-02T00:00:00Z",
        ):
            with self.subTest(observed_at=observed_at):
                with self.assertRaisesRegex(SubjectAdapterError, "UTC RFC 3339"):
                    SubjectSnapshot(
                        _subject(),
                        "tree:one",
                        DIGEST,
                        observed_at,
                        ("evidence:snapshot",),
                    )
        fractional = SubjectSnapshot(
            _subject(),
            "tree:fractional",
            DIGEST,
            "2026-09-02T00:00:00.123456Z",
            ("evidence:snapshot",),
        )
        self.assertEqual("2026-09-02T00:00:00.123456Z", fractional.observed_at)

    def test_capability_order_is_canonical(self) -> None:
        with self.assertRaises(SubjectAdapterError):
            SubjectDescriptor(
                "subject-one",
                SubjectKind.CUSTOM,
                "custom:one",
                ("snapshot", "analyze"),
                DIGEST,
                ("evidence:subject",),
            )

    def test_identity_collections_reject_mutable_lists(self) -> None:
        with self.assertRaisesRegex(SubjectAdapterError, "immutable tuple"):
            SubjectDescriptor(
                "subject-one",
                SubjectKind.CUSTOM,
                "custom:one",
                ["analyze"],  # type: ignore[arg-type]
                DIGEST,
                ("evidence:subject",),
            )
        with self.assertRaisesRegex(SubjectAdapterError, "immutable tuple"):
            SubjectDescriptor(
                "subject-one",
                SubjectKind.CUSTOM,
                "custom:one",
                ("analyze",),
                DIGEST,
                ["evidence:subject"],  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(SubjectAdapterError, "immutable tuple"):
            SubjectSnapshot(
                _subject(),
                "tree:one",
                DIGEST,
                "2026-09-02T00:00:00Z",
                ["evidence:snapshot"],  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
