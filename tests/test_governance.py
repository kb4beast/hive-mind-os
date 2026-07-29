from __future__ import annotations

import ast
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
            "syft/releases/download/v1.50.0/",
            "bf7b29ff57f06da30918266a0e1c2885a8f99784798d1bdb1628886aa015d788",
            "sha256sum --check --strict",
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
                ROOT / ".github" / "governance" / "required-repository-rules.json"
            ).read_text()
        )
        self.assertEqual(rules["required_host_enforcement"], "active")
        self.assertEqual(rules["rules"]["deletion"], "blocked")
        self.assertEqual(rules["rules"]["force_push"], "blocked")
        self.assertTrue(rules["rules"]["enforce_admins"])
        pull_request = rules["rules"]["pull_request"]
        self.assertGreaterEqual(pull_request["required_approving_review_count"], 2)
        self.assertTrue(pull_request["require_code_owner_review"])
        self.assertTrue(pull_request["require_last_push_approval"])
        self.assertEqual(
            rules["verification_status"],
            "blocked_on_remote_admin_enforcement",
        )
        evidence = ROOT / rules["verification_evidence"]
        self.assertTrue(evidence.is_file())
        self.assertEqual(
            rules["verification_evidence_digest"],
            "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest(),
        )
        self.assertIn("administrator", rules["blocking_obligation"])
        self.assertIn("enforcement", rules["blocking_obligation"])
        self.assertIn("one-maintainer", rules["verification_residual"])

    def test_build_backend_is_exactly_pinned(self) -> None:
        project = (ROOT / "pyproject.toml").read_text()
        self.assertIn('requires = ["setuptools==80.9.0"]', project)

    def test_unittest_contract_has_no_pytest_only_modules_or_silent_cases(
        self,
    ) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn(
            "python -m pip install --disable-pip-version-check --no-deps -e .",
            workflow,
        )

        violations: list[str] = []
        test_paths = sorted((ROOT / "tests").rglob("test_*.py"))
        for path in test_paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ) and node.name.startswith("test_"):
                    violations.append(
                        f"{path.name}:{node.lineno}: top-level test is not "
                        "discoverable by unittest"
                    )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(
                    alias.name == "pytest" or alias.name.startswith("pytest.")
                    for alias in node.names
                ):
                    violations.append(
                        f"{path.name}:{node.lineno}: pytest import violates "
                        "the zero-extra-dependency CI contract"
                    )
                if isinstance(node, ast.ImportFrom) and (
                    node.module == "pytest"
                    or (node.module is not None and node.module.startswith("pytest."))
                ):
                    violations.append(
                        f"{path.name}:{node.lineno}: pytest import violates "
                        "the zero-extra-dependency CI contract"
                    )
        self.assertEqual(violations, [])
        for path in test_paths:
            loader = unittest.TestLoader()
            suite = loader.discover(
                start_dir=str(ROOT / "tests"),
                pattern=path.name,
            )
            relative_path = path.relative_to(ROOT).as_posix()
            self.assertEqual(loader.errors, [], relative_path)
            self.assertGreater(
                suite.countTestCases(),
                0,
                f"{relative_path} exposes no unittest cases",
            )

    def test_build_job_verifies_the_installed_wheel_resource_contract(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("python scripts/verify_installed_wheel.py", workflow)
        self.assertIn("--source-root src/hive_mind_os", workflow)
        self.assertIn("--installed-root .wheel-install", workflow)
        self.assertIn("scan dir:.wheel-install", workflow)
        self.assertIn("SBOM contains no packages", workflow)
        self.assertIn("SBOM does not identify installed distribution", workflow)
        self.assertEqual(workflow.count("dist/hive-mind-os.spdx.json"), 4)
        self.assertIn("dist/*.whl", workflow)
        self.assertIn("Attest wheel and SBOM provenance", workflow)

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
