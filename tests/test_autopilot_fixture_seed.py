from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SUPPORT = REPO_ROOT / ".autopilot" / "tests" / "fixture_support.py"
REQUIRED_API = (
    "ContentAddressedFixtureSeed",
    "FixtureIntegrityError",
    "FixturePolicyError",
)


def _load_fixture_support():
    spec = importlib.util.spec_from_file_location(
        "doctor_performance_fixture_support", FIXTURE_SUPPORT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=check,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_ALLOW_PROTOCOL": "file"},
    )
    return completed.stdout.strip()


def _all_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


class FixtureSeedAPISurfaceTests(unittest.TestCase):
    def test_future_fixture_api_is_available(self) -> None:
        module = _load_fixture_support()
        missing = [name for name in REQUIRED_API if not hasattr(module, name)]
        self.assertEqual(
            missing,
            [],
            "expected pre-implementation failure: DP-FIXTURE-030 has not supplied "
            "the independently authored fixture API",
        )


class ContentAddressedFixtureSeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.support = _load_fixture_support()
        missing = [name for name in REQUIRED_API if not hasattr(cls.support, name)]
        if missing:
            raise unittest.SkipTest(
                "adversarial fixture tests activate after DP-FIXTURE-030 supplies: "
                + ", ".join(missing)
            )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "source"
        self.ap_root = self.repository / ".autopilot"
        (self.ap_root / "bin").mkdir(parents=True)
        (self.ap_root / "state").mkdir()
        (self.ap_root / "tests" / "__pycache__").mkdir(parents=True)
        (self.ap_root / "control-plane.json").write_text(
            '{"schema_version": 1}\n', encoding="utf-8"
        )
        (self.ap_root / "bin" / "tool.py").write_text(
            "print('tracked')\n", encoding="utf-8"
        )
        (self.ap_root / "mode-tool.sh").write_text(
            "#!/bin/sh\nexit 0\n", encoding="utf-8"
        )
        (self.ap_root / "state" / "tracked-must-not-seed.json").write_text(
            '{"verdict": "cached"}\n', encoding="utf-8"
        )
        (self.ap_root / "tests" / "__pycache__" / "tracked.pyc").write_bytes(
            b"bytecode must not seed"
        )
        (self.ap_root / ".gitignore").write_text(
            "*.ignored\n__pycache__/\n", encoding="utf-8"
        )
        _git(self.repository, "init", "--initial-branch=main")
        _git(self.repository, "config", "user.name", "Fixture Contract")
        _git(self.repository, "config", "user.email", "fixture@hive-mind.invalid")
        _git(self.repository, "add", "-f", ".autopilot")
        _git(
            self.repository,
            "update-index",
            "--chmod=+x",
            ".autopilot/mode-tool.sh",
        )
        _git(self.repository, "commit", "-m", "pinned fixture snapshot")
        _git(
            self.repository,
            "remote",
            "add",
            "untrusted-network",
            "https://invalid.example/hive-mind.git",
        )
        (self.ap_root / "bin" / "untracked.py").write_text(
            "raise AssertionError('untracked')\n", encoding="utf-8"
        )
        (self.ap_root / "cache.ignored").write_text("ignored\n", encoding="utf-8")
        (self.repository / "outside.txt").write_text("outside snapshot\n", encoding="utf-8")
        self.storage = self.base / "seed-storage"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _seed(self, *, rebuild: bool = False):
        return self.support.ContentAddressedFixtureSeed(
            self.ap_root, self.storage, rebuild=rebuild
        )

    def _expected_manifest(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        listing = _git(self.repository, "ls-files", "-s", "--", ".autopilot")
        for line in listing.splitlines():
            metadata, repository_path = line.split("\t", 1)
            mode, blob, _stage = metadata.split()
            relative = repository_path.removeprefix(".autopilot/")
            parts = Path(relative).parts
            if (
                parts[:1] == ("state",)
                or "__pycache__" in parts
                or relative.endswith((".pyc", ".pyo"))
            ):
                continue
            entries.append({"path": relative, "mode": mode, "blob": blob})
        return sorted(entries, key=lambda item: item["path"])

    def _expected_digest(self, manifest: list[dict[str, str]]) -> str:
        payload = {
            "commit": _git(self.repository, "rev-parse", "HEAD"),
            "tree": _git(self.repository, "rev-parse", "HEAD^{tree}"),
            "entries": manifest,
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(body).hexdigest()

    def test_seed_binds_commit_tree_modes_blobs_and_excludes_unsafe_material(self) -> None:
        seed = self._seed()
        manifest = self._expected_manifest()
        self.assertEqual(list(seed.manifest), manifest)
        self.assertEqual(
            seed.repository_identity,
            {
                "commit": _git(self.repository, "rev-parse", "HEAD"),
                "tree": _git(self.repository, "rev-parse", "HEAD^{tree}"),
            },
        )
        self.assertEqual(seed.digest, self._expected_digest(manifest))
        self.assertEqual(Path(seed.seed_path).name, seed.digest.removeprefix("sha256:"))

        recorded = {item["path"] for item in seed.manifest}
        self.assertIn("mode-tool.sh", recorded)
        self.assertNotIn("state/tracked-must-not-seed.json", recorded)
        self.assertNotIn("tests/__pycache__/tracked.pyc", recorded)
        for forbidden in ("bin/untracked.py", "cache.ignored", "outside.txt"):
            self.assertNotIn(forbidden, recorded)

    def test_source_mutation_fails_closed_and_rebuild_changes_the_address(self) -> None:
        seed = self._seed()
        original_digest = seed.digest
        (self.ap_root / "bin" / "tool.py").write_text(
            "print('dirty mutation')\n", encoding="utf-8"
        )
        with self.assertRaises(self.support.FixtureIntegrityError):
            with seed.derive():
                pass

        _git(self.repository, "add", ".autopilot/bin/tool.py")
        _git(self.repository, "commit", "-m", "new explicit snapshot")
        with self.assertRaises(self.support.FixtureIntegrityError):
            with seed.derive():
                pass
        rebuilt = self._seed(rebuild=True)
        self.assertNotEqual(rebuilt.digest, original_digest)
        with rebuilt.derive() as fixture:
            self.assertTrue(Path(fixture.root).is_dir())

    def test_credential_shaped_tracked_content_is_rejected(self) -> None:
        secret = self.ap_root / "tracked-secret.txt"
        secret.write_text("github_pat_" + "a" * 82 + "\n", encoding="utf-8")
        _git(self.repository, "add", ".autopilot/tracked-secret.txt")
        _git(self.repository, "commit", "-m", "adversarial credential")
        with self.assertRaises(self.support.FixturePolicyError):
            self._seed(rebuild=True)

    def test_derivations_isolate_worktree_index_refs_branches_receipts_and_state(self) -> None:
        seed = self._seed()
        with seed.derive() as left, seed.derive() as right:
            left_root = Path(left.root)
            right_root = Path(right.root)
            self.assertNotEqual(left_root.resolve(), right_root.resolve())
            self.assertNotEqual(Path(left.origin).resolve(), Path(right.origin).resolve())
            (left_root / "worktree-only.txt").write_text("left\n", encoding="utf-8")
            _git(left_root, "add", "worktree-only.txt")
            _git(left_root, "checkout", "-b", "left-only")
            state = left_root / ".autopilot" / "state"
            state.mkdir(parents=True, exist_ok=True)
            (state / "prior-result.json").write_text('{"passed": true}\n', encoding="utf-8")
            receipts = state / "receipts"
            receipts.mkdir()
            (receipts / "cached.json").write_text("{}\n", encoding="utf-8")

            self.assertFalse((right_root / "worktree-only.txt").exists())
            self.assertNotIn("left-only", _git(right_root, "branch", "--list"))
            self.assertEqual(_git(right_root, "diff", "--cached", "--name-only"), "")
            self.assertFalse((right_root / ".autopilot" / "state" / "prior-result.json").exists())
            self.assertFalse((right_root / ".autopilot" / "state" / "receipts").exists())

    def test_derivations_have_independent_objects_and_no_forbidden_coupling(self) -> None:
        seed = self._seed()
        with seed.derive() as first, seed.derive() as second:
            roots = (Path(first.root), Path(second.root))
            object_dirs = [
                Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "objects"))
                for root in roots
            ]
            self.assertNotEqual(object_dirs[0].resolve(), object_dirs[1].resolve())
            for object_dir in object_dirs:
                self.assertFalse((object_dir / "info" / "alternates").exists())
            for root in roots:
                for path in root.rglob("*"):
                    self.assertFalse(path.is_symlink(), f"symlinked fixture path: {path}")

            common = Path(".autopilot/control-plane.json")
            copies = [root / common for root in roots]
            self.assertFalse(os.path.samefile(copies[0], copies[1]))
            self.assertFalse(os.path.samefile(copies[0], self.ap_root / "control-plane.json"))
            first_inodes = {(path.stat().st_dev, path.stat().st_ino) for path in _all_files(roots[0])}
            second_inodes = {(path.stat().st_dev, path.stat().st_ino) for path in _all_files(roots[1])}
            self.assertTrue(first_inodes.isdisjoint(second_inodes))

    def test_concurrent_derivations_are_unique_and_network_free(self) -> None:
        seed = self._seed()
        barrier = threading.Barrier(4)

        def derive_once(_index: int) -> tuple[str, str, str]:
            barrier.wait()
            with seed.derive() as fixture:
                root = Path(fixture.root)
                origin = Path(fixture.origin)
                self.assertTrue(origin.is_dir())
                return (
                    str(Path(fixture.workspace).resolve()),
                    str(Path(_git(root, "rev-parse", "--absolute-git-dir")).resolve()),
                    str(origin.resolve()),
                )

        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ), mock.patch(
            "socket.create_connection", side_effect=AssertionError("network forbidden")
        ):
            with ThreadPoolExecutor(max_workers=4) as executor:
                identities = list(executor.map(derive_once, range(4)))
        self.assertEqual(len(set(identities)), 4)

    def test_derivation_does_not_reuse_cached_verdicts_or_prior_results(self) -> None:
        seed = self._seed()
        with seed.derive() as first:
            first_root = Path(first.root)
            state = first_root / ".autopilot" / "state"
            state.mkdir(parents=True, exist_ok=True)
            (state / "cached-verdict.json").write_text(
                '{"verdict": "PASS"}\n', encoding="utf-8"
            )
            (state / "prior-test-result.json").write_text(
                '{"passed": true}\n', encoding="utf-8"
            )
        with seed.derive() as second:
            second_root = Path(second.root)
            self.assertFalse(
                (second_root / ".autopilot" / "state" / "cached-verdict.json").exists()
            )
            self.assertFalse(
                (second_root / ".autopilot" / "state" / "prior-test-result.json").exists()
            )

    def test_seed_tampering_is_prevented_or_rejected_before_derivation(self) -> None:
        seed = self._seed()
        candidates = _all_files(Path(seed.seed_path))
        self.assertTrue(candidates)
        target = candidates[0]
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"tamper")
        except PermissionError:
            with seed.derive() as fixture:
                self.assertTrue(Path(fixture.root).is_dir())
        else:
            with self.assertRaises(self.support.FixtureIntegrityError):
                with seed.derive():
                    pass

    def test_cleanup_runs_after_success_failure_and_forced_child_termination(self) -> None:
        seed = self._seed()
        with seed.derive() as fixture:
            successful = Path(fixture.workspace)
            self.assertTrue(successful.exists())
        self.assertFalse(successful.exists())

        class TestBodyFailure(RuntimeError):
            pass

        failed: Path | None = None
        with self.assertRaises(TestBodyFailure):
            with seed.derive() as fixture:
                failed = Path(fixture.workspace)
                raise TestBodyFailure("intentional test-body failure")
        assert failed is not None
        self.assertFalse(failed.exists())

        child_program = r"""
import importlib.util
import sys
import time
from pathlib import Path

module_path, source, storage = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("child_fixture_support", module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
seed = module.ContentAddressedFixtureSeed(source, storage)
with seed.derive() as fixture:
    print(Path(fixture.workspace).resolve(), flush=True)
    time.sleep(60)
"""
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                child_program,
                str(FIXTURE_SUPPORT),
                str(self.ap_root),
                str(self.storage),
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "GIT_ALLOW_PROTOCOL": "file"},
        )
        assert child.stdout is not None
        interrupted = Path(child.stdout.readline().strip())
        self.assertTrue(interrupted.exists())
        child.terminate()
        child.wait(timeout=10)

        reopened = self._seed()
        with reopened.derive():
            deadline = time.monotonic() + 5
            while interrupted.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertFalse(
            interrupted.exists(),
            "a derivation abandoned by a terminated child was not reclaimed",
        )


if __name__ == "__main__":
    unittest.main()
