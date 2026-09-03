from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
TESTS = ROOT / "tests"
SPDX_NORMALIZER = ROOT / "scripts" / "normalize_spdx_json.py"
SPDX_VALIDATOR_LOCK = ROOT / "requirements" / "spdx-validator-linux-py312.txt"


class CIContractTests(unittest.TestCase):
    def _normalizer(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location(
            "hive_test_spdx_normalizer", SPDX_NORMALIZER
        )
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertIsNotNone(spec.loader)
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _syft_spdx_document() -> dict[str, object]:
        return {
            "SPDXID": "SPDXRef-DOCUMENT",
            "spdxVersion": "SPDX-2.2",
            "creationInfo": {
                "created": "2026-09-03T11:25:40.785436227Z",
                "creators": ["Tool: syft-0.42.2"],
            },
            "packages": [
                {"SPDXID": "SPDXRef-one", "name": "one"},
                {
                    "SPDXID": "SPDXRef-two",
                    "name": "two",
                    "copyrightText": "Copyright Example",
                },
            ],
        }

    def _workflow_test_command(self) -> str:
        lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
        step_name = "- name: Run deterministic test suite"
        for index, line in enumerate(lines):
            if line.strip() != step_name:
                continue
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip()
                if stripped.startswith("- name:"):
                    break
                if stripped.startswith("run:"):
                    return stripped.partition(":")[2].strip()
        self.fail("workflow test-suite command is missing")

    def test_documented_gate_matches_workflow(self) -> None:
        command = self._workflow_test_command()
        for document in ("README.md", "AGENTS.md", "docs/plan/00_OVERVIEW.md"):
            with self.subTest(document=document):
                self.assertIn(command, (ROOT / document).read_text(encoding="utf-8"))

    def test_readme_starts_with_status_and_a_runnable_entry_point(self) -> None:
        opening = "\n".join(
            (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:40]
        ).lower()
        self.assertIn("## status: early. here is exactly what works.", opening)
        self.assertIn("hive-mind demo", opening)
        for forbidden in ("docket", "atomic claim", "burden", "stage 0", "courtroom"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, opening)

    def test_no_test_module_imports_third_party(self) -> None:
        local_roots = {"hive_mind_os", "tests"}
        local_roots.update(
            path.stem if path.is_file() else path.name
            for path in TESTS.iterdir()
            if not path.name.startswith("__")
        )
        allowed_roots = set(sys.stdlib_module_names) | local_roots
        for path in sorted(TESTS.glob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_roots = {
                alias.name.partition(".")[0]
                for node in ast.walk(module)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imported_roots.update(
                node.module.partition(".")[0]
                for node in ast.walk(module)
                if isinstance(node, ast.ImportFrom) and node.module
            )
            with self.subTest(path=path.name):
                self.assertTrue(
                    imported_roots <= allowed_roots,
                    f"third-party test imports: {sorted(imported_roots - allowed_roots)}",
                )

    def test_workflow_installs_no_extras(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "python -m pip install --disable-pip-version-check --no-deps -e .",
            workflow,
        )

    def test_pull_request_jobs_checkout_the_immutable_candidate_head(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        checkout_ref = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
        self.assertEqual(1, workflow.count(checkout_ref))
        self.assertIn(
            "# Keep the tested object identical to the one direct-child review candidate.",
            workflow,
        )
        linux_job = workflow.partition("  unit-tests:\n")[2].partition(
            "\n  unit-tests-windows:\n"
        )[0]
        self.assertNotIn(checkout_ref, linux_job)
        windows_job = workflow.partition("  unit-tests-windows:\n")[2].partition(
            "\n  quality:\n"
        )[0]
        self.assertIn(checkout_ref, windows_job)

    def test_workflow_exercises_windows_with_python_3_12(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        windows_job = workflow.partition("  unit-tests-windows:\n")[2].partition(
            "\n  quality:\n"
        )[0]
        self.assertTrue(windows_job, "Windows unit-test job is missing")
        self.assertIn("runs-on: windows-latest", windows_job)
        self.assertIn('python-version: ["3.12"]', windows_job)
        self.assertIn(self._workflow_test_command(), windows_job)

    def test_sbom_is_materialized_validated_uploaded_and_attested(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        build_job = workflow.partition("  build-evidence:\n")[2]
        self.assertTrue(build_job, "build-evidence job is missing")
        self.assertIn("anchore/sbom-action/download-syft@", build_job)
        self.assertIn("syft-version: v0.42.2", build_job)
        self.assertIn("packages . \\", build_job)
        self.assertIn(
            "--output spdx-json=dist/hive-mind-os.spdx.json", build_job
        )
        self.assertIn("python scripts/normalize_spdx_json.py", build_job)
        self.assertIn("--require-hashes", build_job)
        self.assertIn("spdx-validator-linux-py312.txt", build_job)
        self.assertIn("pyspdxtools -i dist/hive-mind-os.spdx.json", build_job)
        self.assertIn('Path("dist/hive-mind-os.spdx.json")', build_job)
        self.assertIn('sorted(Path("dist").glob("*.whl"))', build_job)
        self.assertIn('not document["packages"]', build_job)
        self.assertEqual(6, build_job.count("dist/hive-mind-os.spdx.json"))
        for unsupported in (
            "output-file:",
            "upload-artifact:",
            "upload-release-assets:",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, build_job)

    def test_spdx_normalizer_repairs_only_the_proven_syft_gaps(self) -> None:
        module = self._normalizer()
        document = self._syft_spdx_document()
        normalized = module.normalize_spdx_22(document)
        self.assertIs(document, normalized)
        self.assertEqual(
            "2026-09-03T11:25:40Z", normalized["creationInfo"]["created"]
        )
        self.assertEqual("NOASSERTION", normalized["packages"][0]["copyrightText"])
        self.assertEqual(
            "Copyright Example", normalized["packages"][1]["copyrightText"]
        )

    def test_spdx_normalizer_is_deterministic_and_idempotent(self) -> None:
        module = self._normalizer()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sbom.json"
            path.write_text(json.dumps(self._syft_spdx_document()), encoding="utf-8")
            module.normalize_file(path)
            first = path.read_bytes()
            module.normalize_file(path)
            self.assertEqual(first, path.read_bytes())
            self.assertTrue(first.endswith(b"\n"))

    def test_spdx_normalizer_fails_closed_on_unproven_inputs(self) -> None:
        module = self._normalizer()
        invalid_documents = []
        wrong_version = self._syft_spdx_document()
        wrong_version["spdxVersion"] = "SPDX-2.3"
        invalid_documents.append(wrong_version)
        wrong_timezone = self._syft_spdx_document()
        wrong_timezone["creationInfo"]["created"] = "2026-09-03T11:25:40+00:00"
        invalid_documents.append(wrong_timezone)
        impossible_time = self._syft_spdx_document()
        impossible_time["creationInfo"]["created"] = "2026-02-30T11:25:40Z"
        invalid_documents.append(impossible_time)
        empty_packages = self._syft_spdx_document()
        empty_packages["packages"] = []
        invalid_documents.append(empty_packages)
        invalid_copyright = self._syft_spdx_document()
        invalid_copyright["packages"][0]["copyrightText"] = " "
        invalid_documents.append(invalid_copyright)
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(module.SpdxNormalizationError):
                    module.normalize_spdx_22(document)

    def test_spdx_validator_lock_pins_every_distribution_hash(self) -> None:
        lock = SPDX_VALIDATOR_LOCK.read_text(encoding="utf-8")
        requirements = [
            line for line in lock.splitlines() if line and not line.startswith(("#", "--"))
        ]
        self.assertEqual(12, len(requirements))
        self.assertIn("--only-binary=:all:", lock)
        self.assertIn(
            "spdx-tools==0.8.5 --hash=sha256:"
            "7c2d5865941be9d2e898f5b084e8d5422dd298dc5a29320ddb198fec304f59c4",
            lock,
        )
        for requirement in requirements:
            with self.subTest(requirement=requirement):
                self.assertRegex(
                    requirement,
                    r"^[A-Za-z0-9_.-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}$",
                )
