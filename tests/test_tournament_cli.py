from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hive_mind_os.dag_standard import compile_plan
from hive_mind_os.idea_lineage import IdeaLineageStore, idea_note_name
from hive_mind_os.tournament_cli import prepare_tournament, publish_brain


class TournamentCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "FOO BAR"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.repo / "app.js").write_text("console.log('FOO BAR');\n", encoding="utf-8")
        self.git("add", "app.js")
        self.git("commit", "-m", "fixture")
        self.request = self.root / "request.txt"
        self.request.write_text("Improve FOO BAR; retain challenged ideas and their revisions.\n", encoding="utf-8")
        self.standard = Path(__file__).resolve().parents[1] / "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
        self.output = self.root / "tournament"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
            capture_output=True, text=True).stdout.strip()

    def prepare(self):
        return prepare_tournament(repository=self.repo, request_file=self.request,
            standard_file=self.standard, output=self.output)

    def test_arbitrary_repository_prepares_compiles_and_stays_unchanged(self):
        before = self.git("rev-parse", "HEAD")
        manifest = self.prepare()
        self.assertEqual(before, manifest["commit"])
        self.assertEqual("", self.git("status", "--porcelain"))
        self.assertFalse((self.repo / ".autopilot").exists())
        self.assertFalse(manifest["execution_authorized"])
        self.assertEqual("AWAITING_AUTHENTICATED_EXECUTION", manifest["execution_status"])
        self.assertEqual(["operator-local-v1", "external-host"], manifest["available_execution_profiles"])
        receipt = compile_plan((self.output / "plan.json").read_bytes(),
            expected_plan_digest=manifest["plan_digest"], standard_bytes=self.standard.read_bytes(),
            expected_subject_id=manifest["subject_id"], expected_request_id=manifest["request_id"])
        self.assertGreater(receipt.metrics.node_count, 9)
        self.assertEqual(self.request.read_bytes(), (self.output / "request.txt").read_bytes())
        self.assertTrue((self.output / "brain.sqlite3").exists())

    def test_dirty_changes_are_disclosed_not_misrepresented_as_pinned(self):
        (self.repo / "app.js").write_text("console.log('draft');\n", encoding="utf-8")
        self.prepare()
        snapshot = json.loads((self.output / "snapshot.json").read_bytes())
        self.assertIn("app.js", snapshot["working_tree_status"])
        self.assertIn("not included", snapshot["scope"])

    def test_existing_bundle_cannot_be_overwritten(self):
        self.prepare()
        original = (self.output / "plan.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(original, (self.output / "plan.json").read_bytes())

    def test_output_equal_to_or_nested_in_target_is_rejected_before_writes(self):
        tracked = (self.repo / "app.js").read_bytes()
        for output in (self.repo, self.repo / "brain" / "run"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "outside"):
                prepare_tournament(repository=self.repo, request_file=self.request,
                    standard_file=self.standard, output=output)
            self.assertEqual(tracked, (self.repo / "app.js").read_bytes())
            self.assertEqual("", self.git("status", "--porcelain"))
        self.assertFalse((self.repo / "brain").exists())

    def test_similarly_prefixed_sibling_output_is_allowed(self):
        sibling = self.root / "FOO BAR-brain"
        manifest = prepare_tournament(repository=self.repo, request_file=self.request,
            standard_file=self.standard, output=sibling)
        self.assertEqual("PREPARED", manifest["status"])
        self.assertTrue((sibling / "brain.sqlite3").is_file())
        self.assertEqual("", self.git("status", "--porcelain"))

    def test_filesystem_alias_into_target_is_rejected_before_writes(self):
        alias = self.root / "target-alias"
        try:
            alias.symlink_to(self.repo, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory aliases unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "outside"):
            prepare_tournament(repository=self.repo, request_file=self.request,
                standard_file=self.standard, output=alias / "brain")
        self.assertFalse((self.repo / "brain").exists())
        self.assertEqual("", self.git("status", "--porcelain"))

    @unittest.skipUnless(os.name == "nt", "NTFS junction regression")
    def test_windows_junction_alias_into_target_is_rejected(self):
        alias = self.root / "target-junction"
        result = subprocess.run(
            [os.environ.get("ComSpec", "cmd.exe"), "/c", "mklink", "/J", str(alias), str(self.repo)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            self.skipTest(f"junctions unavailable: {result.stderr or result.stdout}")
        try:
            with self.assertRaisesRegex(ValueError, "outside"):
                prepare_tournament(repository=self.repo, request_file=self.request,
                    standard_file=self.standard, output=alias / "brain")
            self.assertFalse((self.repo / "brain").exists())
            self.assertEqual("", self.git("status", "--porcelain"))
        finally:
            alias.rmdir()

    def test_different_standard_cannot_be_relabelled_as_version_two(self):
        wrong = self.root / "standard.md"
        wrong.write_text("# DAG authoring standard V1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported standard"):
            prepare_tournament(repository=self.repo, request_file=self.request,
                standard_file=wrong, output=self.output)
        self.assertFalse(self.output.exists())

    def test_version_two_standard_accepts_git_checkout_line_endings(self):
        windows = self.root / "standard.md"
        windows.write_bytes(self.standard.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        manifest = prepare_tournament(repository=self.repo, request_file=self.request,
            standard_file=windows, output=self.output)
        self.assertEqual("PREPARED", manifest["status"])

    def test_brain_export_retains_return_and_revision_and_preserves_human_notes(self):
        manifest = self.prepare()
        database = self.output / "brain.sqlite3"
        store = IdeaLineageStore(database)
        subject = manifest["repository_id"]  # Stable across candidate commits.
        try:
            event = store.propose(subject_id=subject, idea_id="idea-1", title="Retry safely",
                hypothesis="Idempotency prevents duplicate retries", source="git:app.js", actor_id="scout")
            event = store.append(subject_id=subject, idea_id="idea-1", event_type="challenged",
                actor_id="cross", reason="Reproduce duplicate execution", expected_sequence=event.sequence)
            event = store.append(subject_id=subject, idea_id="idea-1", event_type="defer", actor_id="judge",
                reason="Need duplicate-run receipt", expected_sequence=event.sequence,
                return_to_agent="builder", next_action="Run twice and compare outputs")
            store.append(subject_id=subject, idea_id="idea-1", event_type="revised", actor_id="scout",
                reason="Added idempotency reproduction", expected_sequence=event.sequence,
                hypothesis="A deduplication key prevents duplicate writes", source="git:reproduction.js")
        finally:
            store.close()
        vault = self.root / "Obsidian Vault"
        vault.mkdir()
        human = vault / "Human.md"
        human.write_text("Keep this note", encoding="utf-8")
        export = vault / "tournament-001"
        publish_brain(database=database, subject_id=subject, idea_ids=["idea-1"], output=export)
        markdown = (export / idea_note_name("idea-1")).read_text(encoding="utf-8")
        for fragment in ("Need duplicate-run receipt", "builder", "Run twice", "Added idempotency"):
            self.assertIn(fragment, markdown)
        self.assertIn('same_idea_revision: 2', markdown)
        self.assertIn('latest_event: "revised"', markdown)
        index = (export / "INDEX.md").read_text(encoding="utf-8")
        for heading in ("Stable ID", "Relationships", "Latest event", "Rationale and next action"):
            self.assertIn(heading, index)
        with self.assertRaises(FileExistsError):
            publish_brain(database=database, subject_id=subject, idea_ids=["idea-1"], output=export)
        self.assertEqual("Keep this note", human.read_text(encoding="utf-8"))

    def test_missing_brain_does_not_create_a_database(self):
        database = self.root / "absent.sqlite3"
        with self.assertRaisesRegex(ValueError, "does not exist"):
            publish_brain(database=database, subject_id="foo", idea_ids=["idea-1"], output=self.output)
        self.assertFalse(database.exists())

    def test_read_export_never_modifies_an_unrelated_database(self):
        database = self.root / "unrelated.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE TABLE human_notes (note TEXT)")
        before = database.read_bytes()
        with self.assertRaisesRegex(ValueError, "not an idea history"):
            publish_brain(database=database, subject_id="foo", idea_ids=["idea-1"], output=self.output)
        self.assertEqual(before, database.read_bytes())
        self.assertFalse(self.output.exists())

    def test_export_includes_parents_and_handles_arbitrary_windows_names(self):
        manifest = self.prepare()
        database = self.output / "brain.sqlite3"
        identities = ["INDEX", "CON", "idea", "Idea", "cache / child"]
        with IdeaLineageStore(database) as store:
            for index, identity in enumerate(identities):
                store.propose(subject_id=manifest["repository_id"], idea_id=identity,
                    title=identity, hypothesis="Useful experiment", source="fixture", actor_id="scout",
                    parent_idea_id=identities[index-1] if index else None)
        export = self.root / "export"
        result = publish_brain(database=database, subject_id=manifest["repository_id"],
            idea_ids=[identities[-1]], output=export)
        self.assertEqual(set(identities), set(result["ideas"]))
        self.assertEqual(len(identities) + 1, len(list(export.glob("*.md"))))
        for index, identity in enumerate(identities):
            markdown = (export / idea_note_name(identity)).read_text(encoding="utf-8")
            if index:
                self.assertIn(f"({idea_note_name(identities[index-1])})", markdown)
            if index + 1 < len(identities):
                self.assertIn(f"({idea_note_name(identities[index+1])})", markdown)


if __name__ == "__main__":
    unittest.main()
