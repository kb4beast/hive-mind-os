from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION_REF = re.compile(r"^\s*uses:\s+[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$")


class RepositoryGovernanceTests(unittest.TestCase):
    def test_every_ci_action_is_pinned_to_a_commit(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        uses_lines = [line for line in workflow.splitlines() if "uses:" in line]
        self.assertTrue(uses_lines)
        for line in uses_lines:
            self.assertRegex(line, ACTION_REF)

    def test_ci_covers_required_constitutional_checks(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        for required in (
            "static-and-type-checks",
            "codeql-security",
            "secret-scan",
            "dependency-and-license-review",
            "sbom-and-build-provenance",
            "actions/attest@",
            "anchore/sbom-action@",
        ):
            self.assertIn(required, workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)

    def test_constitutional_files_have_code_owners(self) -> None:
        codeowners = (ROOT / ".github" / "CODEOWNERS").read_text()
        for protected in (
            "/AGENTS.md",
            "/docs/architecture/",
            "/src/hive_mind_os/courtroom.py",
            "/src/hive_mind_os/policy.py",
            "/src/hive_mind_os/source_docket.py",
            "/src/hive_mind_os/schemas/",
            "/evidence/",
            "/.github/",
        ):
            self.assertIn(protected, codeowners)

    def test_required_rules_fail_closed_and_admit_remote_verification_gap(self) -> None:
        rules = json.loads(
            (
                ROOT
                / ".github"
                / "governance"
                / "required-repository-rules.json"
            ).read_text()
        )
        self.assertEqual(rules["required_host_enforcement"], "active")
        self.assertEqual(rules["rules"]["deletion"], "blocked")
        self.assertEqual(rules["rules"]["force_push"], "blocked")
        pull_request = rules["rules"]["pull_request"]
        self.assertGreaterEqual(pull_request["required_approving_review_count"], 2)
        self.assertTrue(pull_request["require_code_owner_review"])
        self.assertTrue(pull_request["require_last_push_approval"])
        self.assertEqual(rules["verification_status"], "not_verified_on_remote")
        self.assertTrue(rules["blocking_obligation"])

    def test_build_backend_is_exactly_pinned(self) -> None:
        project = (ROOT / "pyproject.toml").read_text()
        self.assertIn('requires = ["setuptools==80.9.0"]', project)

    def test_secret_scan_allowlist_is_narrow_and_extends_defaults(self) -> None:
        config = tomllib.loads((ROOT / "gitleaks.toml").read_text())
        self.assertEqual(config["extend"], {"useDefault": True})
        self.assertEqual(len(config["allowlists"]), 1)
        allowlist = config["allowlists"][0]
        self.assertEqual(allowlist["regexTarget"], "line")
        self.assertEqual(
            allowlist["regexes"],
            ["IDEMPOTENCY" + "-P06-test"],
        )
        self.assertNotIn("commits", allowlist)
        self.assertNotIn("paths", allowlist)


if __name__ == "__main__":
    unittest.main()
