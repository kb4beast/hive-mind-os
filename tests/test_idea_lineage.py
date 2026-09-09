"""Portable idea revisions, fair challenges, and durable human-readable history."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path

from hive_mind_os.idea_lineage import IdeaLineageError, IdeaLineageStore, idea_note_name


class IdeaLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "ideas.sqlite3"
        self.store = IdeaLineageStore(self.path)
        self.addCleanup(self.store.close)

    def propose(self, **changes):
        values = dict(
            subject_id="FOO BAR", idea_id="cache-requests", title="Reduce repeated reads",
            hypothesis="A bounded cache may reduce repeated repository reads.",
            source="owner-request:2026-09-08", actor_id="explorer-1",
        )
        return self.store.propose(**(values | changes))

    def append(self, event_type, actor_id, expected_sequence, **changes):
        values = dict(
            subject_id="FOO BAR", idea_id="cache-requests", event_type=event_type,
            actor_id=actor_id, expected_sequence=expected_sequence,
            reason="The recorded example supports this next step.",
        )
        return self.store.append(**(values | changes))

    def test_append_accepts_proposal_padding_without_weakening_write_checks(self):
        padded = dict(subject_id=" \tFOO BAR\n", idea_id=" \tcache-requests\n")
        initial = self.propose(**padded)
        canonical = (initial.subject_id, initial.idea_id)
        self.assertEqual(canonical, ("FOO BAR", "cache-requests"))
        with self.assertRaisesRegex(IdeaLineageError, "challenger must"):
            self.append("challenged", "explorer-1", 1, **padded)
        self.assertEqual(self.store.history(*canonical), (initial,))
        challenge = self.append("challenged", "curator-1", 1, **padded)
        history = self.store.history(*canonical)
        self.assertEqual(history, (initial, challenge))
        self.assertEqual((challenge.subject_id, challenge.idea_id), canonical)
        self.assertEqual((challenge.sequence, challenge.revision), (2, 1))
        self.assertEqual(challenge.previous_digest, initial.digest)
        self.assertEqual(self.store.history(padded["subject_id"], canonical[1]), ())
        self.assertEqual(self.store.history(canonical[0], padded["idea_id"]), ())
        with self.assertRaisesRegex(IdeaLineageError, "stale expected_sequence"):
            self.append("challenged", "curator-2", 1, **padded)
        self.assertEqual(self.store.history(*canonical), history)
        for field in ("subject_id", "idea_id"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(IdeaLineageError, field + " must be non-empty text"):
                    self.append("challenged", "curator-2", 2, **(padded | {field: " \t\n"}))
                self.assertEqual(self.store.history(*canonical), history)
        with IdeaLineageStore(self.path) as reopened:
            self.assertEqual(reopened.history(*canonical), history)

    def test_append_preserves_case_and_internal_spaces_in_both_identities(self):
        identities = (
            ("FOO BAR", "cache requests"),
            ("FOOBAR", "cache requests"),
            ("foo bar", "cache requests"),
            ("FOO BAR", "cacherequests"),
            ("FOO BAR", "Cache requests"),
        )
        originals = {
            identity: self.propose(subject_id=identity[0], idea_id=identity[1])
            for identity in identities
        }
        expected = {identity: (event,) for identity, event in originals.items()}
        for subject_id, idea_id in identities:
            with self.subTest(subject_id=subject_id, idea_id=idea_id):
                event = self.append(
                    "challenged", "curator-1", 1,
                    subject_id=" " + subject_id + " ", idea_id=" " + idea_id + " ",
                )
                identity = (subject_id, idea_id)
                self.assertEqual((event.subject_id, event.idea_id), identity)
                self.assertEqual(event.previous_digest, originals[identity].digest)
                expected[identity] = (originals[identity], event)
                for key, history in expected.items():
                    self.assertEqual(self.store.history(*key), history)

    def test_proposal_needs_hypothesis_and_source_but_no_benchmark(self):
        initial = self.propose()
        self.assertEqual((initial.revision, initial.sequence), (1, 1))
        self.assertEqual(initial.event_type, "proposed")
        with self.assertRaises(FrozenInstanceError):
            initial.reason = "rewritten"
        for field in ("hypothesis", "source"):
            with self.subTest(field=field), self.assertRaises(IdeaLineageError):
                self.propose(idea_id=field, **{field: " "})

    def test_rejected_idea_is_revised_and_adopted_under_same_id(self):
        initial = self.propose()
        self.append("challenged", "curator-1", 1,
                    reason="A cache can return stale repository contents.")
        rejection = self.append(
            "reject", "judge-1", 2,
            reason="The current proposal does not invalidate changed files.",
            return_to_agent="explorer-1", next_action="Add digest-based invalidation.",
        )
        revision = self.append(
            "revised", "explorer-1", 3,
            hypothesis="Key cached reads by the file content digest.",
            reason="Address the stale-content counterexample.",
            source="local-experiment:invalidation-01",
        )
        with self.assertRaisesRegex(IdeaLineageError, "current revision"):
            self.append("adopt", "judge-1", 4)
        self.append("challenged", "curator-1", 4,
                    reason="Check that changed content always produces a new key.")
        adoption = self.append("adopt", "judge-1", 5,
                               reason="Adopt for design; implementation gates still apply.")
        history = self.store.history("FOO BAR", initial.idea_id)
        self.assertEqual(len(history), 6)
        self.assertEqual({event.idea_id for event in history}, {initial.idea_id})
        self.assertEqual(revision.revision, 2)
        self.assertEqual(adoption.revision, 2)
        self.assertEqual(history[0], initial)
        self.assertEqual(history[2], rejection)
        self.assertEqual(history[3].previous_digest, rejection.digest)
        with IdeaLineageStore(self.path) as reopened:
            self.assertEqual(reopened.history("FOO BAR", initial.idea_id), history)

    def test_foreign_subjects_have_independent_ids_and_local_parent_links(self):
        self.propose()
        self.propose(subject_id="ANOTHER REPO")
        child = self.propose(idea_id="cache / child", parent_idea_id="cache-requests")
        self.assertEqual(child.parent_idea_id, "cache-requests")
        self.propose(idea_id="only-foo")
        with self.assertRaisesRegex(IdeaLineageError, "same subject"):
            self.propose(subject_id="ANOTHER REPO", idea_id="orphan", parent_idea_id="only-foo")
        with self.assertRaisesRegex(IdeaLineageError, "same subject"):
            self.propose(idea_id="self-parent", parent_idea_id="self-parent")
        self.assertEqual(self.store.history("MISSING", "cache-requests"), ())

    def test_roles_cannot_challenge_or_judge_their_own_idea(self):
        self.propose()
        with self.assertRaisesRegex(IdeaLineageError, "challenger must"):
            self.append("challenged", "explorer-1", 1)
        self.append("challenged", "curator-1", 1)
        for actor_id in ("explorer-1", "curator-1"):
            with self.subTest(actor_id=actor_id), self.assertRaisesRegex(IdeaLineageError, "judge must"):
                self.append("adopt", actor_id, 2)
        self.append("adapt", "judge-1", 2)
        for actor_id in ("curator-1", "judge-1"):
            with self.subTest(actor_id=actor_id), self.assertRaisesRegex(IdeaLineageError, "reviser must"):
                self.append("revised", actor_id, 3, hypothesis="A revised design.")

    def test_nonadoption_requires_reason_recipient_and_next_action(self):
        self.propose()
        self.append("challenged", "curator-1", 1)
        for disposition in ("defer", "reject", "quarantine"):
            for changes in ({}, {"return_to_agent": "explorer-1"},
                            {"return_to_agent": "explorer-1", "next_action": " "},
                            {"return_to_agent": "explorer-1", "next_action": "Review failure", "reason": " "}):
                with self.subTest(disposition=disposition, changes=changes), self.assertRaises(IdeaLineageError):
                    self.append(disposition, "judge-1", 2, **changes)
        self.assertEqual(len(self.store.history("FOO BAR", "cache-requests")), 2)

    def test_all_dispositions_are_recordable_after_independent_challenge(self):
        for disposition in ("adopt", "adapt", "defer", "reject", "quarantine"):
            with self.subTest(disposition=disposition):
                self.propose(idea_id=disposition)
                self.append("challenged", "curator-1", 1, idea_id=disposition)
                event = self.append(disposition, "judge-1", 2, idea_id=disposition,
                                    return_to_agent="builder-1", next_action="Evaluate a bounded experiment.")
                self.assertEqual(event.event_type, disposition)
                with self.assertRaisesRegex(IdeaLineageError, "reopening"):
                    self.append("challenged", "curator-1", 3, idea_id=disposition)

    def test_revision_budget_is_persisted_and_failed_append_is_atomic(self):
        self.propose(max_revisions=2)
        self.append("revised", "explorer-1", 1, hypothesis="Cache by content digest.")
        with IdeaLineageStore(self.path) as reopened:
            with self.assertRaisesRegex(IdeaLineageError, "budget exhausted"):
                reopened.append(subject_id="FOO BAR", idea_id="cache-requests",
                                event_type="revised", actor_id="explorer-1", reason="Try again.",
                                expected_sequence=2, hypothesis="Another variant.")
        self.append("challenged", "curator-1", 2)
        self.assertEqual(self.store.history("FOO BAR", "cache-requests")[-1].sequence, 3)

    def test_stale_concurrent_writers_cannot_both_append(self):
        self.propose()
        second = IdeaLineageStore(self.path)
        self.addCleanup(second.close)

        def challenge(store, actor):
            try:
                return store.append(subject_id="FOO BAR", idea_id="cache-requests",
                                    event_type="challenged", actor_id=actor, reason="Test invalidation.",
                                    expected_sequence=1)
            except IdeaLineageError as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(challenge, store, actor) for store, actor in
                       ((self.store, "curator-1"), (second, "curator-2"))]
            results = [future.result() for future in futures]
        self.assertEqual(sum(isinstance(result, IdeaLineageError) for result in results), 1)
        self.assertEqual(len(self.store.history("FOO BAR", "cache-requests")), 2)

    def test_sql_update_delete_and_replace_cannot_mutate_history(self):
        initial = self.propose()
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT * FROM idea_lineage_events").fetchone()
            commands = [
                ("UPDATE idea_lineage_events SET digest='changed'", ()),
                ("DELETE FROM idea_lineage_events", ()),
                ("INSERT OR REPLACE INTO idea_lineage_events VALUES (?, ?, ?, ?, ?)", row),
            ]
            for command, parameters in commands:
                with self.subTest(command=command), self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                    connection.execute(command, parameters)
        self.assertEqual(self.store.history("FOO BAR", "cache-requests"), (initial,))

    def test_hash_verification_detects_history_changed_outside_store(self):
        self.propose()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as connection:
            # A database owner can remove triggers; the digest still detects damage.
            connection.execute("DROP TRIGGER idea_lineage_no_update")
            connection.execute("UPDATE idea_lineage_events SET digest='corrupted'")
        with self.assertRaisesRegex(IdeaLineageError, "digest or sequence"):
            self.store.history("FOO BAR", "cache-requests")
        with self.assertRaisesRegex(IdeaLineageError, "digest or sequence"):
            self.append("challenged", "curator-1", 1)

    def test_markdown_quotes_embedded_html_and_encodes_parent_paths(self):
        self.propose(idea_id="parent / variant", title="<script>unsafe()</script>\n# Forged status")
        markdown = self.store.render_markdown("FOO BAR", "parent / variant")
        self.assertNotIn("<script>", markdown)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("> # Forged status", markdown)
        self.propose(idea_id="child", parent_idea_id="parent / variant")
        self.assertIn(f"[Parent history]({idea_note_name('parent / variant')})",
                      self.store.render_markdown("FOO BAR", "child"))

    def test_markdown_retains_rejection_and_return_history_without_writing_notes(self):
        self.propose()
        self.append("challenged", "curator-1", 1, reason="Changed files invalidate a cache entry.")
        self.append("defer", "judge-1", 2, reason="The invalidation experiment is missing.",
                    return_to_agent="builder-1", next_action="Run an invalidation experiment.")
        self.append("revised", "explorer-1", 3, hypothesis="Invalidate entries using file digests.")
        existing_note = Path(self.directory.name) / "cache-requests.md"
        existing_note.write_text("User annotations must survive.", encoding="utf-8")
        markdown = self.store.render_markdown("FOO BAR", "cache-requests")
        for text in ("FOO BAR", "Event 1", "Event 4", "Revision 2", "defer", "builder-1",
                     "Run an invalidation experiment.", "The invalidation experiment is missing.",
                     "owner-request:2026-09-08", "local assertions", "no execution or promotion authority"):
            self.assertIn(text, markdown)
        self.assertEqual(markdown, self.store.render_markdown("FOO BAR", "cache-requests"))
        self.assertEqual(existing_note.read_text(encoding="utf-8"), "User annotations must survive.")
        self.propose(idea_id="child", parent_idea_id="cache-requests")
        self.assertIn(f"[Parent history]({idea_note_name('cache-requests')})", self.store.render_markdown("FOO BAR", "child"))


if __name__ == "__main__":
    unittest.main()
