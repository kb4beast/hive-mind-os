"""Adversarial checks for the inert Generic Hive Mind V3 execution overlay."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
PLAN_AUTHORING_BASE = "42b4aeef17f816430a7d8a435102635afea8761a"
PAYLOAD_A = "4e2b81b932e5145f24c4b52ceeee664bff91df2e"
CORRECTION_PARENT = "f06e52c43a1e2d1d53523378c0d6f5564fb984bf"
TARGET_BRANCH = "release/hive-mind-autopilot"
PAYLOAD_PATHS = (
    "docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md",
    "docs/architecture/ADR_INDEX.md",
    "docs/execution/dags/generic-hive-mind-product-v3/README.md",
    "docs/execution/dags/generic-hive-mind-product-v3/manifest.json",
    "docs/execution/dags/generic-hive-mind-product-v3/materialize_plan.py",
    "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json",
    "docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json",
    "docs/execution/dags/generic-hive-mind-product-v3/plan.json",
    "docs/execution/dags/generic-hive-mind-product-v3/traceability.json",
    "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py",
    "tests/test_generic_dag_v3_overlay.py",
)
CORRECTION_PATHS = (
    "docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md",
    "docs/execution/dags/generic-hive-mind-product-v3/README.md",
    "docs/execution/dags/generic-hive-mind-product-v3/manifest.json",
    "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py",
    "tests/test_generic_dag_v3_overlay.py",
)


def canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shell_command(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


class GenericDagV3OverlayTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        discovered_git = shutil.which("git")
        if discovered_git is None:
            raise unittest.SkipTest("Git executable is unavailable")
        git_executable = Path(discovered_git).resolve()
        if os.name == "nt":
            direct_git = git_executable.parents[1] / "mingw64" / "bin" / "git.exe"
            if direct_git.is_file():
                git_executable = direct_git.resolve()
        cls.git_executable = git_executable
        cls.git_executable_sha256 = "sha256:" + hashlib.sha256(git_executable.read_bytes()).hexdigest()
        cls.git_environment = dict(os.environ)
        for key in list(cls.git_environment):
            if key.casefold().startswith("git_"):
                cls.git_environment.pop(key)
        cls.git_environment.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_OPTIONAL_LOCKS": "0",
            }
        )
        cls._authoring_directory = tempfile.TemporaryDirectory()
        cls.authoring_root = Path(cls._authoring_directory.name) / "authoring"
        subprocess.run(
            [
                str(cls.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(ROOT),
                str(cls.authoring_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            env=cls.git_environment,
        )
        cls.run_git(cls.authoring_root, "switch", "--quiet", "-C", TARGET_BRANCH, CORRECTION_PARENT)
        for relative in PAYLOAD_PATHS:
            destination = cls.authoring_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._authoring_directory.cleanup()
        super().tearDownClass()

    def copy_overlay(self, target: Path) -> Path:
        copied = target / "overlay"
        shutil.copytree(
            self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3",
            copied,
        )
        return copied

    def run_verifier(
        self,
        overlay: Path,
        *,
        repo_root: Path | None = None,
        authoring_check: bool = True,
        include_expected_manifest: bool = True,
        environment_updates: dict[str, str] | None = None,
        git_executable: Path | None = None,
        git_executable_sha256: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if repo_root is None:
            repo_root = self.authoring_root if authoring_check else ROOT
        command = [
            sys.executable,
            str(overlay / "verify_plan.py"),
            "--overlay-dir",
            str(overlay),
            "--repo-root",
            str(repo_root),
            "--git-executable",
            str(git_executable or self.git_executable),
            "--expected-git-executable-sha256",
            git_executable_sha256 or self.git_executable_sha256,
        ]
        if include_expected_manifest:
            command.extend(
                [
                    "--expected-manifest-digest",
                    "sha256:" + hashlib.sha256((overlay / "manifest.json").read_bytes()).hexdigest(),
                ]
            )
        if authoring_check:
            command.append("--authoring-check")
        environment = dict(os.environ)
        for key in list(environment):
            if key.casefold().startswith("git_"):
                environment.pop(key)
        if environment_updates:
            environment.update(environment_updates)
        return subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

    @classmethod
    def run_git(cls, repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(cls.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "-C",
                str(repository),
                *args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            env=cls.git_environment,
        )

    def make_committed_checkout(
        self,
        parent: Path,
        *,
        base: str = CORRECTION_PARENT,
        extra_path: bool = False,
        executable_path: str | None = None,
    ) -> Path:
        checkout = parent / "committed"
        subprocess.run(
            [
                str(self.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(ROOT),
                str(checkout),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            env=self.git_environment,
        )
        self.run_git(checkout, "switch", "--quiet", "-C", TARGET_BRANCH, base)
        self.run_git(checkout, "config", "user.name", "V3 Fixture")
        self.run_git(checkout, "config", "user.email", "v3-fixture@example.invalid")
        for relative in PAYLOAD_PATHS:
            destination = checkout / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.authoring_root / relative, destination)
        paths = list(CORRECTION_PATHS)
        if extra_path:
            unexpected = checkout / "unexpected-v3-payload.txt"
            unexpected.write_text("not allowlisted\n", encoding="utf-8")
            paths.append("unexpected-v3-payload.txt")
        self.run_git(checkout, "add", "--", *paths)
        if executable_path is not None:
            self.run_git(checkout, "update-index", "--chmod=+x", "--", executable_path)
        if base == CORRECTION_PARENT:
            staged = tuple(
                sorted(
                    line
                    for line in self.run_git(
                        checkout,
                        "diff",
                        "--cached",
                        "--name-only",
                        "--no-renames",
                    ).stdout.splitlines()
                    if line
                )
            )
            self.assertEqual(staged, tuple(sorted(paths)))
        self.run_git(checkout, "commit", "--quiet", "-m", "fixture: exact V3 payload")
        return checkout

    def assert_rejected(
        self,
        result: subprocess.CompletedProcess[str],
        expected_error: str | None = None,
    ) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertIs(payload["verified"], False)
        self.assertTrue(payload["error"])
        if expected_error is not None:
            self.assertIn(expected_error, payload["error"])

    def rewrite_manifest(self, overlay: Path, mutate) -> None:
        path = overlay / "manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        mutate(value)
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_valid_overlay_verifies_without_mutating_historical_plan(self) -> None:
        sealed_legacy_plan = self.authoring_root / ".autopilot" / "plan.json"
        before = sealed_legacy_plan.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_verifier(self.copy_overlay(Path(directory)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["verified"])
        self.assertEqual(payload["integrity"], "verified-sealed")
        self.assertEqual(payload["durability_semantics"], "typed-v2")
        self.assertEqual(payload["topology"], {"nodes": 20, "raw_edges": 28, "levels": 17, "rounds": 20})
        self.assertFalse(payload["materializer_imported_or_executed"])
        self.assertEqual(payload["verification_mode"], "authoring-correction-check-non-executing")
        self.assertFalse(payload["committed_payload_qualification"])
        self.assertFalse(payload["execution_qualification"])
        self.assertEqual(sealed_legacy_plan.read_bytes(), before)

    def test_default_mode_requires_exact_committed_payload_and_caller_manifest_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            result = self.run_verifier(overlay, repo_root=checkout, authoring_check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verification_mode"], "committed-git-boundary-correction-v3")
            self.assertTrue(payload["committed_payload_qualification"])
            self.assertFalse(payload["execution_qualification"])
            self.assertEqual(payload["committed_payload"]["authoring_base_parent"], PLAN_AUTHORING_BASE)
            self.assertEqual(payload["committed_payload"]["correction_parent"], CORRECTION_PARENT)
            self.assertEqual(
                payload["committed_payload"]["head"],
                self.run_git(checkout, "rev-parse", "HEAD").stdout.strip(),
            )
            missing = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=False,
                include_expected_manifest=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("--expected-manifest-digest", missing.stderr)

    def test_default_mode_refuses_precommit_extra_commit_wrong_parent_and_path_change(self) -> None:
        overlay = self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
        self.assert_rejected(
            self.run_verifier(
                overlay,
                repo_root=self.authoring_root,
                authoring_check=False,
            ),
            "committed payload must be one non-merge direct child of the correction parent",
        )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            self.run_git(checkout, "commit", "--quiet", "--allow-empty", "-m", "unexpected second commit")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload must be one non-merge direct child of the correction parent",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory), base=CORRECTION_PARENT + "^")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload must be one non-merge direct child of the correction parent",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory), extra_path=True)
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload changed-path allowlist mismatch",
            )

    def test_default_mode_refuses_dirty_staged_and_other_untracked_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            readme = overlay / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "dirty\n", encoding="utf-8")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "tracked worktree bytes differ from HEAD: docs/execution/dags/generic-hive-mind-product-v3/README.md",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            readme = overlay / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "staged\n", encoding="utf-8")
            self.run_git(checkout, "add", "--", "docs/execution/dags/generic-hive-mind-product-v3/README.md")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "Git index differs from the exact HEAD tree",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            (checkout / "unapproved.txt").write_text("untracked\n", encoding="utf-8")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed checkout contains an unapproved untracked or ignored path",
            )

    def test_git_boundary_rejects_case_insensitive_ambient_overrides(self) -> None:
        overlay = self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
        poison_path = str(self.authoring_root / ".git" / "poison")
        overrides = (
            ("GIT_WORK_TREE", poison_path),
            ("GIT_DIR", poison_path),
            ("gIt_CoMmOn_DiR", poison_path),
            ("GIT_INDEX_FILE", poison_path),
            ("GIT_OBJECT_DIRECTORY", poison_path),
            ("GIT_ALTERNATE_OBJECT_DIRECTORIES", poison_path),
            ("GIT_CONFIG_GLOBAL", poison_path),
            ("GIT_CONFIG_SYSTEM", poison_path),
            ("GIT_CONFIG_COUNT", "1"),
            ("GIT_CONFIG_KEY_0", "core.fsmonitor"),
            ("GIT_CONFIG_VALUE_0", "hostile"),
            ("gIt_CoNfIg_PaRaMeTeRs", "'core.fsmonitor=hostile'"),
            ("GIT_EXEC_PATH", poison_path),
            ("GIT_PAGER", "hostile"),
            ("GIT_EXTERNAL_DIFF", "hostile"),
            ("GIT_REPLACE_REF_BASE", "refs/replace/hostile"),
        )
        for key, value in overrides:
            with self.subTest(key=key):
                result = self.run_verifier(
                    overlay,
                    environment_updates={key: value},
                )
                self.assert_rejected(result, "inherited Git environment is forbidden")
                error = json.loads(result.stdout.strip().splitlines()[-1])["error"]
                self.assertIn(key.casefold(), error.casefold())

    def test_git_boundary_binds_absolute_executable_digest_and_ignores_path(self) -> None:
        overlay = self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"

        relative = self.run_verifier(overlay, git_executable=Path("git"))
        self.assert_rejected(relative, "Git executable path must be absolute")

        wrong_digest = self.run_verifier(
            overlay,
            git_executable_sha256="sha256:" + "0" * 64,
        )
        self.assert_rejected(wrong_digest, "caller-authenticated Git executable digest mismatch")

        with tempfile.TemporaryDirectory() as directory:
            fake_directory = Path(directory) / "fake-path"
            fake_directory.mkdir()
            fake_git = fake_directory / ("git.exe" if os.name == "nt" else "git")
            if os.name == "nt":
                fake_git.write_bytes(b"not a Git executable\n")
            else:
                fake_git.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
                fake_git.chmod(0o755)
            result = self.run_verifier(
                overlay,
                environment_updates={"PATH": str(fake_directory)},
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["git_boundary"]["executable"], str(self.git_executable))
        self.assertEqual(payload["git_boundary"]["executable_sha256"], self.git_executable_sha256)
        self.assertFalse(payload["git_boundary"]["path_lookup"])

    def test_git_boundary_blocks_hostile_configs_and_local_worktree_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = self.make_committed_checkout(root / "fixture")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            hook = root / "fsmonitor_hook.py"
            hook.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[1]).write_text('executed', encoding='utf-8')\n"
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )

            local_marker = root / "local.marker"
            home_marker = root / "home.marker"
            xdg_marker = root / "xdg.marker"

            def marker_command(marker: Path) -> str:
                return shell_command([sys.executable, str(hook), str(marker)])

            empty_home = root / "empty-home"
            empty_xdg = root / "empty-xdg"
            hostile_home = root / "hostile-home"
            hostile_xdg = root / "hostile-xdg"
            for path in (empty_home, empty_xdg, hostile_home, hostile_xdg / "git"):
                path.mkdir(parents=True, exist_ok=True)

            self.run_git(checkout, "config", "core.fsmonitor", marker_command(local_marker))
            self.run_git(
                checkout,
                "config",
                "--file",
                str(hostile_home / ".gitconfig"),
                "core.fsmonitor",
                marker_command(home_marker),
            )
            self.run_git(
                checkout,
                "config",
                "--file",
                str(hostile_xdg / "git" / "config"),
                "core.fsmonitor",
                marker_command(xdg_marker),
            )

            config_cases = (
                (
                    "local",
                    {"HOME": str(empty_home), "XDG_CONFIG_HOME": str(empty_xdg)},
                ),
                (
                    "home",
                    {"HOME": str(hostile_home), "XDG_CONFIG_HOME": str(empty_xdg)},
                ),
                (
                    "xdg",
                    {"HOME": str(empty_home), "XDG_CONFIG_HOME": str(hostile_xdg)},
                ),
            )
            for label, environment in config_cases:
                with self.subTest(config=label):
                    for marker in (local_marker, home_marker, xdg_marker):
                        marker.unlink(missing_ok=True)
                    result = self.run_verifier(
                        overlay,
                        repo_root=checkout,
                        authoring_check=False,
                        environment_updates=environment,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse(local_marker.exists())
                    self.assertFalse(home_marker.exists())
                    self.assertFalse(xdg_marker.exists())

            self.run_git(checkout, "config", "--unset", "core.fsmonitor")
            shadow = root / "shadow"
            subprocess.run(
                [
                    str(self.git_executable),
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "clone",
                    "--quiet",
                    "--no-hardlinks",
                    str(checkout),
                    str(shadow),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
                env=self.git_environment,
            )
            self.run_git(checkout, "config", "core.worktree", str(shadow))
            contributing = checkout / "CONTRIBUTING.md"
            contributing.write_bytes(contributing.read_bytes() + b"hidden by hostile core.worktree\n")
            redirected = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=False,
            )
            self.assert_rejected(
                redirected,
                "tracked worktree bytes differ from HEAD: CONTRIBUTING.md",
            )

    def test_git_boundary_rejects_on_disk_object_alternates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = self.make_committed_checkout(root / "fixture")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            git_dir = Path(
                self.run_git(checkout, "rev-parse", "--absolute-git-dir").stdout.strip()
            )
            alternate_objects = root / "alternate-objects"
            alternate_objects.mkdir()
            alternates = git_dir / "objects" / "info" / "alternates"
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(str(alternate_objects.resolve()) + "\n", encoding="utf-8")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "Git object alternates are forbidden",
            )

    def test_git_replace_hidden_worktree_and_mode_substitution_fail_closed(self) -> None:
        readme_relative = "docs/execution/dags/generic-hive-mind-product-v3/README.md"
        unrelated_relative = "CONTRIBUTING.md"

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.run_git(checkout, "replace", CORRECTION_PARENT, PLAN_AUTHORING_BASE)
            result = self.run_verifier(overlay, repo_root=checkout, authoring_check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for flag in ("--skip-worktree", "--assume-unchanged"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                checkout = self.make_committed_checkout(Path(directory))
                overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
                unrelated = checkout / unrelated_relative
                self.run_git(checkout, "update-index", flag, "--", unrelated_relative)
                unrelated.write_bytes(unrelated.read_bytes() + b"hidden substitution\n")
                self.assert_rejected(
                    self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                    "tracked index visibility flag is not pristine",
                )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(
                Path(directory),
                executable_path=readme_relative,
            )
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload is not one regular file",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            (checkout / "ignored.tmp").write_text("ignored\n", encoding="utf-8")
            self.run_git(checkout, "check-ignore", "--quiet", "--", "ignored.tmp")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed checkout contains an unapproved untracked or ignored path",
            )

    def test_source_substitution_is_rejected_before_materializer_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            marker = overlay / "MATERIALIZER_EXECUTED"
            (overlay / "materialize_plan.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
                encoding="utf-8",
            )
            result = self.run_verifier(overlay)
            self.assert_rejected(result, "materialize_plan.py")
            self.assertFalse(marker.exists())

    def test_manifest_identity_snapshot_and_tool_substitution_fail_closed(self) -> None:
        mutations = {
            "request": lambda m: m["request_binding"].__setitem__("request_id", "sha256:stale"),
            "objective": lambda m: m["request_binding"].__setitem__("objective_digest", "sha256:stale"),
            "repository": lambda m: m["request_binding"].__setitem__("repository_id", "sha256:stale"),
            "branch": lambda m: m["request_binding"].__setitem__("target_branch", "main"),
            "head": lambda m: m["snapshot_lineage"]["authoring_base_parent"].__setitem__("commit", "0" * 40),
            "tree": lambda m: m["snapshot_lineage"]["authoring_base_parent"].__setitem__("tree", "0" * 40),
            "correction_head": lambda m: m["snapshot_lineage"]["correction_parent"].__setitem__("commit", "0" * 40),
            "correction_tree": lambda m: m["snapshot_lineage"]["correction_parent"].__setitem__("tree", "0" * 40),
            "predecessor_manifest": lambda m: m["committed_payload_contract"]["predecessor_payload"].__setitem__("manifest_raw_sha256", "sha256:stale"),
            "predecessor_aggregate": lambda m: m["committed_payload_contract"]["predecessor_payload"]["full_payload_aggregate"].__setitem__("sha256", "sha256:stale"),
            "payload_inventory": lambda m: m["committed_payload_contract"]["payload_inventory"].pop(),
            "anti_downgrade": lambda m: m["committed_payload_contract"]["activation_anti_downgrade"].__setitem__("predecessor_activation", "ALLOWED"),
            "request_snapshot": lambda m: m["snapshot_lineage"]["request_observation"].__setitem__("commit", "0" * 40),
            "compiler": lambda m: next(
                row for row in m["source_bindings"]["repository"] if row["path"] == ".autopilot/bin/dag_standard.py"
            ).__setitem__("sha256", "sha256:substituted"),
            "standard": lambda m: next(
                row for row in m["source_bindings"]["repository"] if row["path"] == "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
            ).__setitem__("sha256", "sha256:substituted"),
            "execution_authority": lambda m: m["authorship"].__setitem__("execution_authority", "SELF_GRANTED"),
            "extra_authority_field": lambda m: m["authorship"].__setitem__("delegated_authority", "SELF_GRANTED"),
            "extra_top_level_authority": lambda m: m.__setitem__("execution_authority", "GRANTED"),
            "extra_execution_command": lambda m: m["execution_contract"].__setitem__("command", "powershell hostile.ps1"),
            "extra_evidence_authority": lambda m: m["evidence_partition"].__setitem__("external_execution_authority", "GRANTED"),
            "removed_nonclaims": lambda m: m.__setitem__("nonclaims", []),
            "self_review": lambda m: m["authorship"].__setitem__("judge", "/root/generation_architect"),
        }
        expected_errors = {
            "request": "manifest request/repository/objective binding mismatch",
            "objective": "manifest request/repository/objective binding mismatch",
            "repository": "manifest request/repository/objective binding mismatch",
            "branch": "manifest request/repository/objective binding mismatch",
            "head": "authoring-base parent commit/tree mismatch",
            "tree": "authoring-base parent commit/tree mismatch",
            "correction_head": "correction parent commit/tree mismatch",
            "correction_tree": "correction parent commit/tree mismatch",
            "predecessor_manifest": "predecessor correction identity/status mismatch",
            "predecessor_aggregate": "predecessor correction identity/status mismatch",
            "payload_inventory": "committed payload inventory mismatch",
            "anti_downgrade": "activation anti-downgrade contract mismatch",
            "request_snapshot": "request snapshot mismatch",
            "compiler": "manifest repository source binding mismatch",
            "standard": "manifest repository source binding mismatch",
            "execution_authority": "author manifest cannot grant execution authority",
            "extra_authority_field": "manifest authorship field inventory mismatch",
            "extra_top_level_authority": "manifest top-level field inventory mismatch",
            "extra_execution_command": "manifest execution contract mismatch",
            "extra_evidence_authority": "evidence partition contract mismatch",
            "removed_nonclaims": "manifest nonclaims mismatch",
            "self_review": "author manifest cannot self-assign a judge",
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                overlay = self.copy_overlay(Path(directory))
                self.rewrite_manifest(overlay, mutation)
                self.assert_rejected(self.run_verifier(overlay), expected_errors[label])

    def test_strict_json_rejects_duplicate_nonfinite_oversize_and_deep_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            manifest = overlay / "manifest.json"
            text = manifest.read_text(encoding="utf-8")
            manifest.write_text(text.replace('"schema_version": 3,', '"schema_version": 3,\n  "schema_version": 3,', 1), encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            manifest = overlay / "manifest.json"
            text = manifest.read_text(encoding="utf-8")
            manifest.write_text(text.replace("{", '{"poison":NaN,', 1), encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            manifest = overlay / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" " * 262_144)
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            self.rewrite_manifest(overlay, lambda m: m.__setitem__("too_deep", [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]))
            self.assert_rejected(self.run_verifier(overlay))

    def test_plan_and_node_reseal_substitution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            plan_path = overlay / "plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["nodes"][0]["objective"] += " substituted"
            for node in plan["nodes"]:
                node.pop("contract_digest", None)
                node["contract_digest"] = canonical_digest(node)
            plan.pop("plan_digest", None)
            plan["plan_digest"] = canonical_digest(plan)
            rendered = json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            plan_path.write_text(rendered, encoding="utf-8")
            new_plan_digest = plan["plan_digest"]
            new_raw_digest = "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
            self.rewrite_manifest(
                overlay,
                lambda m: m["plan_binding"].update(
                    expected_plan_digest=new_plan_digest,
                    expected_raw_bytes_digest=new_raw_digest,
                ),
            )
            self.assert_rejected(self.run_verifier(overlay))

    def test_contract_topology_durability_ownership_effect_trace_and_quarantine_corruption(self) -> None:
        corruptions = {
            "topology": ("node-contracts.json", lambda d: d["nodes"][1].__setitem__("dependencies", [])),
            "durability": ("node-contracts.json", lambda d: d["nodes"][0].__setitem__("durability", "ephemeral")),
            "ownership": ("node-contracts.json", lambda d: d["nodes"][1]["write_scope"].append(d["nodes"][0]["write_scope"][0])),
            "effects": ("ownership-effects.json", lambda d: d["node_effect_expectations"]["BASELINE-000"].__setitem__("candidate_build_effects", ["concealed-effect"])),
            "missing_v1_mapping": ("traceability.json", lambda d: d["rows"].pop(next(iter(d["rows"])))),
            "source_quarantine": ("plan.json", lambda d: d["source_governance"].__setitem__("SRC-024", "ADOPT")),
        }
        for label, (name, mutate) in corruptions.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                overlay = self.copy_overlay(Path(directory))
                path = overlay / name
                data = json.loads(path.read_text(encoding="utf-8"))
                mutate(data)
                path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                self.assert_rejected(self.run_verifier(overlay))

    def test_source_path_swap_collision_and_detached_binding_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            left = overlay / "node-contracts.json"
            right = overlay / "traceability.json"
            left_bytes, right_bytes = left.read_bytes(), right.read_bytes()
            left.write_bytes(right_bytes)
            right.write_bytes(left_bytes)
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            self.rewrite_manifest(
                overlay,
                lambda m: m["source_bindings"]["overlay"].append(dict(m["source_bindings"]["overlay"][0])),
            )
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            self.rewrite_manifest(
                overlay,
                lambda m: m["plan_binding"].__setitem__("external_path", "detached/plan.json"),
            )
            self.assert_rejected(self.run_verifier(overlay))

    def test_invalid_v3_has_no_legacy_fallback_and_activation_attacks_are_explicit(self) -> None:
        plan = json.loads((OVERLAY / "plan.json").read_text(encoding="utf-8"))
        activation = plan["activation_contract"]
        self.assertEqual(activation["invalid_v3_legacy_fallback"], "PROHIBITED")
        self.assertEqual(activation["concurrent_activation"], "single_winner_compare_and_swap_ledger")
        self.assertEqual(activation["repeat_resume"], "idempotent_only_for_exact_generation_and_resume_identity")
        self.assertEqual(activation["same_request_fast_path"], "exact_request_on_persisted_target_before_new_target_protection_check")
        expected_attacks = {
            "duplicate_json_key",
            "non_finite_number",
            "oversize_document",
            "excessive_nesting_depth",
            "path_swap",
            "detached_signature_or_digest_substitution",
            "request_repository_objective_or_generation_collision",
            "replay_or_expired_lease",
            "repeat_resume_identity_mismatch",
            "concurrent_activation_loser",
        }
        self.assertEqual(set(activation["strict_rejections"]), expected_attacks)
        self.assertFalse(activation["path_reference_sufficient"])
        self.assertFalse(activation["detached_digest_sufficient"])

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            plan_path = overlay / "plan.json"
            invalid = json.loads(plan_path.read_text(encoding="utf-8"))
            invalid["execution"]["legacy_fallback"] = "ALLOW_V1"
            plan_path.write_text(json.dumps(invalid, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))

    def test_exact_host_evidence_lineage_and_manual_parent_boundaries(self) -> None:
        contracts = json.loads((OVERLAY / "node-contracts.json").read_text(encoding="utf-8"))
        ownership = json.loads((OVERLAY / "ownership-effects.json").read_text(encoding="utf-8"))
        plan = json.loads((OVERLAY / "plan.json").read_text(encoding="utf-8"))
        host = contracts["frozen_host_contract"]
        self.assertEqual(host["extraction_commit"], "ca43709591313c1c166a2e655b8982ccff16daf3")
        self.assertEqual(host["file_count"], 16)
        self.assertEqual(len(host["files"]), 16)
        self.assertTrue(all(set(row) >= {"path", "bytes", "sha256", "git_blob"} for row in host["files"]))
        self.assertEqual(host["bundle_digest"], "sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255")
        lineage = ownership["phase_boundaries"]["candidate_and_evidence_lineage"]
        self.assertIn("Envelope B", json.dumps(lineage))
        self.assertEqual(plan["execution"]["mode"], "manual-parent-v1")
        self.assertEqual(plan["execution"]["expected_round_count"], 20)
        self.assertEqual(plan["execution"]["expected_nodes_per_round"], 1)
        self.assertEqual(plan["execution"]["round_command_policy"], "all_null")
        self.assertNotIn('"command"', json.dumps(plan, sort_keys=True))
        self.assertFalse(plan["execution"]["executable_dispatch_command_available"])

    def test_frozen_standard_v2_compiles_exact_null_command_rounds(self) -> None:
        digest = "sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1"
        compiler = ROOT / ".autopilot" / "bin" / "dag_standard.py"
        plan = OVERLAY / "plan.json"
        lint = subprocess.run(
            [sys.executable, str(compiler), "dag-lint", "--json", "--strict", "--plan", str(plan), "--expected-plan-digest", digest],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        lint_result = json.loads(lint.stdout)
        self.assertEqual(lint_result["counts"], {"error": 0, "warning": 0, "info": 0})
        self.assertEqual(lint_result["integrity"]["status"], "verified-sealed")
        self.assertEqual(lint_result["durability_semantics"]["mode"], "typed-v2")
        self.assertTrue(lint_result["expected_plan_binding"]["matched"])

        rounds = subprocess.run(
            [sys.executable, str(compiler), "dag-rounds", "--json", "--plan", str(plan), "--expected-plan-digest", digest],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(rounds.returncode, 0, rounds.stdout + rounds.stderr)
        result = json.loads(rounds.stdout)
        self.assertEqual(result["execution"]["mode"], "manual-parent-v1")
        self.assertFalse(result["execution"]["executable_dispatch_command_available"])
        self.assertEqual(len(result["rounds"]), 20)
        self.assertEqual([round_["round_id"] for round_ in result["rounds"]], [f"R{number}" for number in range(1, 21)])
        self.assertTrue(all(round_["command"] is None for round_ in result["rounds"]))
        self.assertTrue(all(len(round_["nodes"]) == 1 for round_ in result["rounds"]))

    def test_materialization_is_repeatable_and_refuses_autopilot_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            plan_path = overlay / "plan.json"
            plan_path.unlink()
            command = [sys.executable, str(overlay / "materialize_plan.py")]
            first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            first_bytes = plan_path.read_bytes()
            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(plan_path.read_bytes(), first_bytes)

            forbidden = ROOT / ".autopilot" / "v3-test-plan.json"
            self.assertFalse(forbidden.exists())
            refused = subprocess.run(
                command + ["--output", str(forbidden)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
