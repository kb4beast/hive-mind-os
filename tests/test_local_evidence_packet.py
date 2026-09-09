from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hive_mind_os import local_evidence_packet
from hive_mind_os.local_evidence_packet import (
    MAX_CONTENT_BYTES,
    LocalEvidenceError,
    apply_proposed_patch,
    build_source_packet,
    inspect_brain_publication,
    run_focused_checks,
)


class LocalEvidencePacketTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "isolated subject with spaces"
        self.workspace.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("src/example.py", "def answer():\n    return 1\n")
        self.write("tests/test_example.py", "import unittest\nfrom example import answer\n\n"
                   "class AnswerTests(unittest.TestCase):\n"
                   "    def test_answer(self):\n        self.assertEqual(answer(), 1)\n"
                   "    def test_type(self):\n        self.assertIsInstance(answer(), int)\n")
        self.commit()
        self.git("checkout", "--detach", "--quiet")

    def git(self, *args, data=None):
        result = subprocess.run(["git", "-C", str(self.workspace), *args], input=data,
                                capture_output=True, check=True)
        return result.stdout

    def write(self, name, content):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "fixture")

    @staticmethod
    def patch(name, before, after):
        return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                            fromfile=f"a/{name}", tofile=f"b/{name}"))

    def test_packet_reads_pinned_head_without_exposing_worktree_or_untracked_text(self):
        original = (self.workspace / "src/example.py").read_text()
        self.write("src/example.py", "UNCOMMITTED_DO_NOT_INCLUDE\n")
        self.write("untracked.py", "UNTRACKED_DO_NOT_INCLUDE\n")
        before = self.git("status", "--porcelain=v1")
        packet = build_source_packet(self.workspace, "BASELINE-001", [{"node_id": "earlier", "status": "blocked"}])
        self.assertEqual(before, self.git("status", "--porcelain=v1"))
        selected = {item["path"]: item for item in packet["selected_files"]}
        self.assertEqual(selected["src/example.py"]["content"], original)
        self.assertEqual(selected["src/example.py"]["sha256"], hashlib.sha256(original.encode()).hexdigest())
        self.assertNotIn("UNCOMMITTED_DO_NOT_INCLUDE", json.dumps(packet))
        self.assertNotIn("UNTRACKED_DO_NOT_INCLUDE", json.dumps(packet))
        self.assertEqual(packet["head"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(len(packet["inventory"]), 2)
        self.assertEqual(packet["predecessor_reports"][0]["node_id"], "earlier")

    def test_budget_binary_secrets_and_symlinks_are_explicit_omissions(self):
        self.write("src/oversized.py", "x" * (MAX_CONTENT_BYTES + 1))
        self.write("src/binary.py", b"\xff\x00\xff")
        self.write(".env", "SAMPLE_CONFIGURATION=placeholder\n")
        benign_source = "# Benign tracked source fixture.\n"
        self.write("src/credentials_example.py", benign_source)
        self.commit()
        blob = self.git("hash-object", "-w", "--stdin", data=b"../../outside").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{blob},src/link.py")
        self.git("commit", "--quiet", "-m", "tracked symlink")
        source_blob = self.git("rev-parse", "HEAD:src/credentials_example.py").decode().strip()
        original_git = local_evidence_packet._git
        secret = "ghp_" + "a" * 36

        def read_blob(workspace, *arguments, data=None):
            # Keep synthetic credential-shaped content in memory, never in Git or a file.
            if arguments == ("cat-file", "blob", source_blob):
                return f"TOKEN = '{secret}'\n".encode()
            return original_git(workspace, *arguments, data=data)

        with mock.patch.object(local_evidence_packet, "_git", side_effect=read_blob):
            packet = build_source_packet(self.workspace, "PROPOSE-042", [])
        self.assertEqual(self.git("show", "HEAD:src/credentials_example.py").decode(), benign_source)
        self.assertEqual((self.workspace / "src/credentials_example.py").read_text(), benign_source)
        omissions = {item["path"]: item["reason"] for item in packet["omitted_files"]}
        self.assertIn("budget", omissions["src/oversized.py"])
        self.assertIn("non-UTF-8", omissions["src/binary.py"])
        self.assertIn("secret", omissions[".env"])
        self.assertIn("secret", omissions["src/credentials_example.py"])
        self.assertIn("symlink", omissions["src/link.py"])
        self.assertNotIn(secret, json.dumps(packet))
        self.assertLessEqual(packet["selected_content_bytes"], MAX_CONTENT_BYTES)
        self.assertEqual(packet["truncated_files"], [])
        self.assertTrue(packet["evidence_obligations"])

    def test_real_patch_application_returns_exact_changed_paths_and_digests(self):
        before = (self.workspace / "src/example.py").read_text()
        after = before.replace("return 1", "return 2")
        receipt = apply_proposed_patch(self.workspace, self.patch("src/example.py", before, after), ["src/example.py"])
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(receipt["changed_paths"], ["src/example.py"])
        self.assertEqual(receipt["before_sha256"]["src/example.py"], hashlib.sha256(before.encode()).hexdigest())
        self.assertEqual(receipt["after_sha256"]["src/example.py"], hashlib.sha256(after.encode()).hexdigest())
        self.assertEqual((self.workspace / "src/example.py").read_text(), after)

    def test_multiple_plain_unified_file_sections_are_supported(self):
        source = (self.workspace / "src/example.py").read_text()
        test = (self.workspace / "tests/test_example.py").read_text()
        patch = self.patch("src/example.py", source, source.replace("return 1", "return 2"))
        patch += self.patch("tests/test_example.py", test, test.replace("answer(), 1", "answer(), 2"))
        receipt = apply_proposed_patch(self.workspace, patch, ["tests/test_example.py", "src/example.py"])
        self.assertEqual(receipt["changed_paths"], ["src/example.py", "tests/test_example.py"])
        checks = run_focused_checks(self.workspace, receipt["changed_paths"], self.root / "multi-checks", 15)
        self.assertTrue(checks["all_passed"])
        self.assertEqual(checks["total_tests"], 2)

    def test_incorrect_hunk_counts_are_recounted_without_changing_patch_bytes(self):
        source = (self.workspace / "src/example.py").read_text()
        tests = (self.workspace / "tests/test_example.py").read_text()
        patch = "diff --git a/src/example.py b/src/example.py\n"
        patch += self.patch("src/example.py", source, source.replace("return 1", "return 2"))
        patch += "diff --git a/tests/test_example.py b/tests/test_example.py\n"
        patch += self.patch("tests/test_example.py", tests, tests.replace("answer(), 1", "answer(), 2"))
        patch = re.sub(r"(@@ -\d+),\d+( \+\d+),\d+( @@)", r"\1,99\2,1\3", patch)
        original_bytes = patch.encode("utf-8")
        with self.assertRaises(subprocess.CalledProcessError):
            self.git("apply", "--check", "-", data=original_bytes)
        receipt = apply_proposed_patch(self.workspace, patch, ["src/example.py", "tests/test_example.py"])
        self.assertEqual(receipt["patch_sha256"], hashlib.sha256(original_bytes).hexdigest())
        self.assertIn("--recount", receipt["hunk_count_handling"])
        self.assertEqual((self.workspace / "src/example.py").read_text(), source.replace("return 1", "return 2"))
        self.assertEqual((self.workspace / "tests/test_example.py").read_text(), tests.replace("answer(), 1", "answer(), 2"))
        checks = run_focused_checks(self.workspace, receipt["changed_paths"], self.root / "recount-checks", 15)
        self.assertTrue(checks["all_passed"])
        self.assertEqual(checks["total_tests"], 2)

    def test_recount_keeps_context_and_declared_path_validation(self):
        before = (self.workspace / "src/example.py").read_text()
        patch = self.patch("src/example.py", before, before.replace("return 1", "return 2"))
        patch = patch.replace("@@ -1,2 +1,2 @@", "@@ -1,99 +1,1 @@")
        with self.assertRaisesRegex(LocalEvidenceError, "exactly match"):
            apply_proposed_patch(self.workspace, patch, ["src/unapproved.py"])
        invalid_context = patch.replace(" def answer():", " def no_such_function():")
        with self.assertRaisesRegex(LocalEvidenceError, "patch does not apply"):
            apply_proposed_patch(self.workspace, invalid_context, ["src/example.py"])
        self.assertEqual((self.workspace / "src/example.py").read_text(), before)
        self.assertEqual(self.git("status", "--porcelain=v1"), b"")

    def test_head_patch_applies_to_windows_autocrlf_checkout(self):
        self.git("config", "core.autocrlf", "true")
        (self.workspace / "src/example.py").unlink()
        self.git("checkout-index", "--force", "--all")
        before = self.git("show", "HEAD:src/example.py").decode("utf-8")
        self.assertIn(b"\r\n", (self.workspace / "src/example.py").read_bytes())
        receipt = apply_proposed_patch(self.workspace,
                                      self.patch("src/example.py", before, before.replace("return 1", "return 2")),
                                      ["src/example.py"])
        self.assertEqual(receipt["status"], "applied")
        self.assertIn("return 2", (self.workspace / "src/example.py").read_text())

    def test_node_priorities_keep_cited_module_counterpart_and_recent_adr_first(self):
        self.write("src/hive_mind_os/local_codex_worker.py", "# Runtime worker\n")
        self.write("tests/test_local_codex_worker.py", "# Worker test\n")
        self.write("docs/architecture/ADR-001-OLD.md", "Old decision\n")
        self.write("docs/architecture/ADR-078-NEW.md", "Current decision\n")
        self.commit()
        packet = build_source_packet(self.workspace, "RUNTIME-030", [])
        paths = [item["path"] for item in packet["selected_files"]]
        self.assertEqual(paths[:2], ["src/hive_mind_os/local_codex_worker.py", "tests/test_local_codex_worker.py"])
        self.assertLess(paths.index("docs/architecture/ADR-078-NEW.md"), paths.index("docs/architecture/ADR-001-OLD.md"))
        packet = build_source_packet(self.workspace, "CHALLENGER-060",
                                     [{"ideas": [{"source": "src/example.py:1; unrelated/untracked.py:2"}]}])
        self.assertEqual([item["path"] for item in packet["selected_files"]][:2],
                         ["src/example.py", "tests/test_example.py"])

    def test_selected_idea_and_test_survive_large_cited_documents(self):
        bodies = {
            "src/z_selected.py": "# Selected implementation\n" * 1600,
            "tests/test_z_selected.py": "# Selected regression\n" * 1600,
            "src/alpha.py": "# Another idea\n" * 1000,
            "tests/test_alpha.py": "# Another regression\n" * 1000,
        }
        for name, body in bodies.items():
            self.write(name, body)
        documents = [f"docs/architecture/ADR-{number:03d}-CONTEXT.md" for number in range(77, 81)]
        for name in documents:
            self.write(name, "Background consideration.\n" * 2200)
        self.commit()
        ideas = [{"idea_id": "chosen", "source": "src/z_selected.py:1"},
                 {"idea_id": "other", "source": "src/alpha.py:1"}]
        proposal = {"node_id": "PROPOSE-042", "workers": [
            {"report": {"ideas": ideas, "selected_idea_ids": ["chosen"], "findings": documents}},
            {"report": {"ideas": ideas, "selected_idea_ids": ["other"]}},
        ]}
        for node_id in ("CROSS-045", "REVISE-048"):
            with self.subTest(node_id=node_id):
                packet = build_source_packet(self.workspace, node_id, [proposal])
                selected = packet["selected_files"]
                self.assertEqual([item["path"] for item in selected][:4],
                                 ["src/z_selected.py", "tests/test_z_selected.py",
                                  "src/alpha.py", "tests/test_alpha.py"])
                for item in selected[:4]:
                    self.assertEqual(item["content"], bodies[item["path"]])
                self.assertTrue(any(item["path"] in documents and "budget" in item["reason"]
                                    for item in packet["omitted_files"]))
                represented = {item["path"] for item in selected + packet["omitted_files"]}
                self.assertEqual(represented, {item["path"] for item in packet["inventory"]})
                self.assertLessEqual(packet["selected_content_bytes"], MAX_CONTENT_BYTES)
                self.assertEqual(packet["truncated_files"], [])

        court = {"node_id": "COURT-050", "workers": [
            {"report": {"selected_idea_ids": ["other"], "ideas": []}},
        ]}
        packet = build_source_packet(self.workspace, "CHALLENGER-060", [proposal, court])
        # The court choice resolves its source from the original proposal.
        self.assertEqual([item["path"] for item in packet["selected_files"]][:4],
                         ["src/alpha.py", "tests/test_alpha.py", "src/z_selected.py", "tests/test_z_selected.py"])

    def test_cited_code_and_tests_are_grouped_by_stem_before_cited_docs(self):
        self.write("src/zeta.py", "# Zeta implementation\n")
        self.write("tests/test_zeta.py", "# Zeta regression\n")
        self.write("docs/context.md", "Cited context\n")
        self.commit()
        packet = build_source_packet(self.workspace, "VERIFY-070", [{
            "findings": ["docs/context.md", "src/zeta.py:1", "src/example.py:1"],
        }])
        self.assertEqual([item["path"] for item in packet["selected_files"]][:5],
                         ["src/example.py", "tests/test_example.py", "src/zeta.py",
                          "tests/test_zeta.py", "docs/context.md"])

    def test_path_escape_metadata_renames_and_path_mismatch_are_rejected_before_effects(self):
        before = (self.workspace / "src/example.py").read_text()
        good = self.patch("src/example.py", before, before.replace("return 1", "return 2"))
        variants = [
            (good, ["src/other.py"]),
            (good.replace("src/example.py", "../outside.py"), ["../outside.py"]),
            (good.replace("src/example.py", "/absolute.py"), ["/absolute.py"]),
            (good.replace("src/example.py", ".git/config"), [".git/config"]),
            (good.replace("src/example.py", "C:/outside.py"), ["C:/outside.py"]),
            (good.replace("+++ b/src/example.py", "+++ b/src/renamed.py"), ["src/renamed.py"]),
            ("diff --git a/src/example.py b/src/example.py\nnew file mode 120000\n" + good, ["src/example.py"]),
            ("GIT binary patch\n" + good, ["src/example.py"]),
        ]
        for patch, names in variants:
            with self.subTest(names=names), self.assertRaises(LocalEvidenceError):
                apply_proposed_patch(self.workspace, patch, names)
        self.assertEqual((self.workspace / "src/example.py").read_text(), before)
        self.assertEqual(self.git("status", "--porcelain=v1"), b"")

    def test_mutations_require_clean_isolated_clone(self):
        before = (self.workspace / "src/example.py").read_text()
        patch = self.patch("src/example.py", before, before.replace("return 1", "return 2"))
        self.git("remote", "add", "origin", "https://example.invalid/subject")
        with self.assertRaisesRegex(LocalEvidenceError, "no remotes"):
            apply_proposed_patch(self.workspace, patch, ["src/example.py"])
        self.git("remote", "remove", "origin")
        self.git("switch", "-c", "owner-checkout")
        with self.assertRaisesRegex(LocalEvidenceError, "detached"):
            apply_proposed_patch(self.workspace, patch, ["src/example.py"])
        self.git("checkout", "--detach", "--quiet")
        self.write("owner-note.txt", "Keep this note.\n")
        with self.assertRaisesRegex(LocalEvidenceError, "clean"):
            apply_proposed_patch(self.workspace, patch, ["src/example.py"])

    def test_git_symlink_mode_is_rejected_even_when_windows_materializes_regular_file(self):
        blob = self.git("hash-object", "-w", "--stdin", data=b"outside\n").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{blob},src/link.py")
        self.git("commit", "--quiet", "-m", "tracked symlink")
        self.git("config", "core.symlinks", "false")
        self.git("checkout-index", "--force", "--all")
        self.assertFalse((self.workspace / "src/link.py").is_symlink())
        with self.assertRaisesRegex(LocalEvidenceError, "tracked symlink"):
            apply_proposed_patch(self.workspace, self.patch("src/link.py", "outside\n", "inside\n"), ["src/link.py"])

    def test_fixed_checks_execute_real_tests_and_capture_hashes(self):
        tests = (self.workspace / "tests/test_example.py").read_text()
        self.write("tests/test_example.py", tests + "\nimport os\n"
                   "print('CHECK_CWD=' + os.getcwd())\n"
                   "print('CHECK_PYTHONPATH=' + os.environ['PYTHONPATH'])\n")
        receipt = run_focused_checks(self.workspace, ["src/example.py"], self.root / "checks", 15)
        self.assertEqual(receipt["status"], "passed")
        self.assertTrue(receipt["all_passed"])
        self.assertEqual(receipt["total_tests"], 2)
        check = receipt["checks"][0]
        self.assertTrue(Path(check["command"][0]).samefile(sys.executable))
        self.assertEqual(check["command"][1:3], ["-m", "unittest"])
        self.assertIn("tests/test_example.py", check["command"])
        self.assertEqual(check["exit_code"], 0)
        self.assertEqual(
            check["cwd"], receipt["verification_receipt"]["execution_workspace"]
        )
        self.assertIn("PYTHONPATH", check["environment"]["names"])
        self.assertTrue(check["environment"]["digest"].startswith("sha256:"))
        actual_output = Path(check["stdout_path"]).read_text()
        self.assertIn("CHECK_CWD=" + check["cwd"], actual_output)
        self.assertIn("CHECK_PYTHONPATH=src", actual_output)
        self.assertIn(b"Ran 2 tests", Path(check["stderr_path"]).read_bytes())
        self.assertEqual(check["stderr_sha256"], hashlib.sha256(Path(check["stderr_path"]).read_bytes()).hexdigest())

    def test_failed_and_zero_test_runs_cannot_report_success(self):
        self.write("src/example.py", "def answer():\n    return 999\n")
        failure = run_focused_checks(self.workspace, ["src/example.py"], self.root / "failed", 15)
        self.assertFalse(failure["all_passed"])
        self.assertEqual(failure["total_tests"], 2)
        self.assertNotEqual(failure["checks"][0]["exit_code"], 0)
        self.write("tests/test_empty.py", "# There are no tests in this file.\n")
        empty = run_focused_checks(self.workspace, ["tests/test_empty.py"], self.root / "empty", 15)
        self.assertFalse(empty["all_passed"])
        self.assertEqual(empty["total_tests"], 0)
        none = run_focused_checks(self.workspace, [], self.root / "none", 15)
        self.assertEqual(none["status"], "no_tests_selected")
        self.assertFalse(none["all_passed"])

    def test_timeout_terminates_child_process_tree_and_preserves_real_output(self):
        pid_path = self.root / "descendant.pid"
        child_code = "import time; time.sleep(60)"
        self.write("tests/test_slow.py", "import pathlib, subprocess, sys, time, unittest\n"
                   "class Slow(unittest.TestCase):\n    def test_slow(self):\n"
                   f"        child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
                   f"        pathlib.Path({str(pid_path)!r}).write_text(str(child.pid))\n"
                   "        time.sleep(60)\n")
        receipt = run_focused_checks(self.workspace, ["tests/test_slow.py"], self.root / "timeout", 1)
        self.assertEqual(receipt["status"], "timed_out")
        self.assertFalse(receipt["all_passed"])
        self.assertTrue(receipt["checks"][0]["timed_out"])
        self.assertTrue(pid_path.is_file())
        pid = int(pid_path.read_text())
        if os.name == "nt":
            tasklist = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
            result = subprocess.run([str(tasklist), "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, check=True)
            self.assertNotIn(f'"{pid}"'.encode(), result.stdout)
        else:
            # Linux may briefly retain a killed descendant as a zombie.
            stat = Path(f"/proc/{pid}/stat")
            try:
                process_state = stat.read_text().split()[2]
            except FileNotFoundError:
                # Reaping can remove /proc between an existence check and read.
                pass
            else:
                self.assertEqual(process_state, "Z")


class BrainPublicationInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.brain = self.root / "existing brain"
        self.brain.mkdir()

    def write(self, name, content):
        path = self.brain / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def test_index_and_all_four_histories_are_captured_with_real_hashes_without_writes(self):
        idea_ids = ["LEARNING-040-I01", "ORCHESTRATION-020-IDEA-001", "AGENTS-010-IDEA-001", "RUNTIME-030-IDEA-001"]
        self.write("INDEX.md", "# Existing brain\n\n" + "".join(
            f"- [{idea_id}](idea-{number}.md)\n" for number, idea_id in enumerate(idea_ids)))
        for number, idea_id in enumerate(idea_ids):
            self.write(f"idea-{number}.md", f"# {idea_id}\n\nDisposition: defer\nReason: Reproduce the counterexample.\n"
                       "Return to: builder\nNext action: Add a regression.\n\n[Node evidence](NODE-001.md)\n")
        self.write("NODE-001.md", "# Node receipt\n\n[Brain index](INDEX.md)\n")
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.brain.iterdir()}
        snapshot = inspect_brain_publication(self.brain)
        self.assertEqual(snapshot["canonical_idea_ids"], idea_ids)
        self.assertEqual(len(snapshot["selected_files"]), 5)
        self.assertEqual(len(snapshot["inventory"]), 6)
        self.assertEqual(snapshot["selected_files"][0]["path"], "INDEX.md")
        self.assertTrue(snapshot["snapshot_consistent"])
        self.assertTrue(snapshot["index_and_idea_links_valid"])
        self.assertEqual(snapshot["invalid_links"], [])
        self.assertEqual(len(snapshot["links"]), 9)
        self.assertTrue(all(link["status"] == "verified" for link in snapshot["links"]))
        for item in snapshot["inventory"]:
            self.assertEqual(item["sha256"], hashlib.sha256(before[item["path"]][0]).hexdigest())
        for item in snapshot["selected_files"]:
            self.assertEqual(item["content"].encode(), before[item["path"]][0])
        self.assertEqual(snapshot["snapshot_sha256"], inspect_brain_publication(self.brain)["snapshot_sha256"])
        self.assertEqual(before, {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.brain.iterdir()})

    def test_missing_escaping_encoded_and_external_links_have_truthful_statuses(self):
        (self.root / "outside.md").write_text("External content must not enter the snapshot.")
        self.write("INDEX.md", "[Missing](idea-missing.md)\n[Escape](../outside.md)\n"
                   "[Encoded escape](%2e%2e/outside.md)\n[Web](https://example.invalid/page)\n"
                   "[Fragment](INDEX.md#heading)\n[Local](<note with spaces.md>)\n[[note with spaces|Wiki]]\n")
        self.write("note with spaces.md", "# Local note\n")
        self.write("invalid.md", b"\xff\x00")
        snapshot = inspect_brain_publication(self.brain)
        statuses = {link["label"]: link["status"] for link in snapshot["links"]}
        self.assertEqual(statuses, {"Missing": "missing", "Escape": "outside_brain",
                                   "Encoded escape": "outside_brain", "Web": "external_unchecked",
                                   "Fragment": "verified", "Local": "verified", "Wiki": "verified"})
        self.assertFalse(snapshot["index_and_idea_links_valid"])
        self.assertEqual(len(snapshot["invalid_links"]), 3)
        self.assertNotIn("External content must not enter", json.dumps(snapshot))
        self.assertTrue(any("fragments" in item for item in snapshot["evidence_obligations"]))
        self.assertTrue(any(item["path"] == "invalid.md" for item in snapshot["omitted_files"]))

    def test_content_limit_keeps_whole_notes_and_all_inventory_with_explicit_obligations(self):
        self.write("INDEX.md", "[A](idea-a.md)\n[B](idea-b.md)\n[Huge](idea-huge.md)\n")
        body = "# Complete history\n" + "Revision evidence.\n" * 4000
        self.write("idea-a.md", body)
        self.write("idea-b.md", body)
        oversized = b"x" * (MAX_CONTENT_BYTES + 1)
        self.write("idea-huge.md", oversized)
        snapshot = inspect_brain_publication(self.brain)
        self.assertEqual([item["path"] for item in snapshot["selected_files"]], ["INDEX.md", "idea-a.md"])
        self.assertEqual(snapshot["selected_files"][1]["content"], body)
        self.assertLessEqual(snapshot["selected_content_bytes"], MAX_CONTENT_BYTES)
        self.assertEqual(snapshot["truncated_files"], [])
        self.assertEqual(len(snapshot["inventory"]), 4)
        omitted = {item["path"]: item for item in snapshot["omitted_files"]}
        self.assertIn("not truncated", omitted["idea-b.md"]["reason"])
        self.assertEqual(omitted["idea-huge.md"]["sha256"], hashlib.sha256(oversized).hexdigest())
        self.assertFalse(snapshot["index_and_idea_links_valid"])
        self.assertTrue(any("oversized" in item for item in snapshot["evidence_obligations"]))


if __name__ == "__main__":
    unittest.main()
