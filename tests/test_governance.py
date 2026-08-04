from __future__ import annotations

import hashlib
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

    def test_required_rules_bind_remote_verification_evidence(self) -> None:
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
        self.assertEqual(pull_request["required_approving_review_count"], 1)
        self.assertTrue(pull_request["require_code_owner_review"])
        self.assertTrue(pull_request["require_last_push_approval"])
        self.assertEqual(rules["verification_status"], "verified_on_remote")
        evidence = ROOT / rules["verification_evidence"]
        self.assertTrue(evidence.is_file())
        self.assertEqual(
            rules["verification_evidence_digest"],
            "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest(),
        )
        self.assertIsNone(rules["blocking_obligation"])
        self.assertIn("One approval", rules["verification_residual"])

    def test_contributor_material_and_lite_path_are_present(self) -> None:
        for path in (
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            "SECURITY.md",
            "CHANGELOG.md",
            ".github/ISSUE_TEMPLATE/bug_report.md",
            ".github/ISSUE_TEMPLATE/docs_improvement.md",
            ".github/pull_request_template.md",
        ):
            self.assertTrue((ROOT / path).is_file(), path)

        contributing = (ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn("Governance-lite", contributing)
        self.assertIn("one approving review", contributing)
        for heavyweight_area in (
            "kernel",
            "policy",
            "courtroom",
            "schemas",
        ):
            self.assertIn(heavyweight_area, contributing)

    def test_build_backend_is_exactly_pinned(self) -> None:
        project = (ROOT / "pyproject.toml").read_text()
        self.assertIn('requires = ["setuptools==80.9.0"]', project)

    def test_secret_scan_allowlist_is_narrow_and_extends_defaults(self) -> None:
        config = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
        self.assertEqual(config["extend"], {"useDefault": True})
        self.assertEqual(set(config), {"title", "extend", "allowlist"})
        allowlist = config["allowlist"]
        self.assertEqual(allowlist["regexTarget"], "line")
        self.assertEqual(
            allowlist["regexes"],
            ["IDEMPOTENCY" + "-P06-test"],
        )
        self.assertNotIn("commits", allowlist)
        self.assertNotIn("paths", allowlist)


if __name__ == "__main__":
    unittest.main()
