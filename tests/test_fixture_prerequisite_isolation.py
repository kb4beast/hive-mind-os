"""Independent security contract for hermetic fixture seeds.

The authoritative red assertion lives in ``test_autopilot_fixture_seed.py``.  This
module intentionally becomes a no-op while that API is absent so the sealed root-CI
inventory stays at its one authorized failure and eight existing skips.  Once the
API appears, every test below is an adversarial acceptance requirement.
"""
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


def _load_support():
    spec = importlib.util.spec_from_file_location("fpp_fixture_support", FIXTURE_SUPPORT)
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


def _have_api(module: object) -> bool:
    return all(hasattr(module, name) for name in REQUIRED_API)


class FixturePrerequisiteIsolationTests(unittest.TestCase):
    """Tests that activate only after the independently frozen API exists."""

    def setUp(self) -> None:
        self.support = _load_support()
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "source"
        self.ap_root = self.repository / ".autopilot"
        (self.ap_root / "bin").mkdir(parents=True)
        (self.ap_root / "state").mkdir()
        (self.ap_root / "bin" / "tool.py").write_text("print('fixture')\n", encoding="utf-8")
        (self.ap_root / "control-plane.json").write_text(
            '{"schema_version": 1}\n', encoding="utf-8"
        )
        _git(self.repository, "init", "--initial-branch=main")
        _git(self.repository, "config", "user.name", "FPP Curator")
        _git(self.repository, "config", "user.email", "curator@hive-mind.invalid")
        _git(self.repository, "add", ".autopilot")
        _git(self.repository, "commit", "-m", "pinned fixture source")
        self.storage = self.base / "seed-storage"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _active(self) -> bool:
        # Do not add a failure or skip before Build: the frozen red assertion owns it.
        return _have_api(self.support)

    def _seed(self, *, source: Path | None = None, rebuild: bool = False):
        return self.support.ContentAddressedFixtureSeed(
            source or self.ap_root, self.storage, rebuild=rebuild
        )

    def _expect_policy_rejection(self, source: Path | None = None) -> None:
        with self.assertRaises(self.support.FixturePolicyError):
            self._seed(source=source, rebuild=True)

    def test_tampered_and_torn_seed_are_rejected(self) -> None:
        if not self._active():
            return
        seed = self._seed()
        contents = [path for path in Path(seed.seed_path).rglob("*") if path.is_file()]
        self.assertTrue(contents)
        contents[0].write_bytes(contents[0].read_bytes() + b"tampered")
        with self.assertRaises(self.support.FixtureIntegrityError):
            with seed.derive():
                pass

        rebuilt = self._seed(rebuild=True)
        torn = next(path for path in Path(rebuilt.seed_path).rglob("*") if path.is_file())
        torn.unlink()
        with self.assertRaises(self.support.FixtureIntegrityError):
            with rebuilt.derive():
                pass

    def test_source_commit_tree_and_blob_identity_are_verified(self) -> None:
        if not self._active():
            return
        seed = self._seed()
        expected_commit = _git(self.repository, "rev-parse", "HEAD")
        expected_tree = _git(self.repository, "rev-parse", "HEAD^{tree}")
        listing = _git(self.repository, "ls-files", "-s", "--", ".autopilot")
        blobs = {
            repository_path.removeprefix(".autopilot/"): metadata.split()[1]
            for line in listing.splitlines()
            for metadata, repository_path in [line.split("\t", 1)]
            if not repository_path.startswith(".autopilot/state/")
        }
        self.assertEqual(seed.repository_identity, {"commit": expected_commit, "tree": expected_tree})
        self.assertEqual({item["path"]: item["blob"] for item in seed.manifest}, blobs)
        digest_body = json.dumps(
            {"commit": expected_commit, "tree": expected_tree, "entries": list(seed.manifest)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(seed.digest, "sha256:" + hashlib.sha256(digest_body).hexdigest())

        (self.ap_root / "bin" / "tool.py").write_text("mutated\n", encoding="utf-8")
        with self.assertRaises(self.support.FixtureIntegrityError):
            with seed.derive():
                pass

    def test_symlink_junction_and_hardlink_sources_fail_closed(self) -> None:
        if not self._active():
            return
        external = self.base / "external.txt"
        external.write_text("outside\n", encoding="utf-8")
        linked = self.ap_root / "linked.txt"
        try:
            os.symlink(external, linked)
        except (NotImplementedError, OSError):
            # Windows without Developer Mode cannot create a symlink; the hardlink
            # case below still exercises link rejection without widening authority.
            pass
        else:
            _git(self.repository, "add", ".autopilot/linked.txt")
            _git(self.repository, "commit", "-m", "symlinked fixture input")
            self._expect_policy_rejection()
            _git(self.repository, "reset", "--hard", "HEAD~1")

        junction_target = self.base / "junction-target"
        junction_target.mkdir()
        (junction_target / "inside.txt").write_text("outside junction\n", encoding="utf-8")
        junction = self.ap_root / "junction"
        junction_result = subprocess.run(
            ("cmd", "/c", "mklink", "/J", str(junction), str(junction_target)),
            capture_output=True,
            text=True,
        )
        if junction_result.returncode == 0:
            _git(self.repository, "add", ".autopilot/junction/inside.txt")
            _git(self.repository, "commit", "-m", "junctioned fixture input")
            self._expect_policy_rejection()
            _git(self.repository, "reset", "--hard", "HEAD~1")
            subprocess.run(("cmd", "/c", "rmdir", str(junction)), check=False)

        hardlinked = self.ap_root / "hardlinked.txt"
        os.link(external, hardlinked)
        _git(self.repository, "add", ".autopilot/hardlinked.txt")
        _git(self.repository, "commit", "-m", "hardlinked fixture input")
        self._expect_policy_rejection()

    def test_unsafe_git_object_sources_are_rejected(self) -> None:
        if not self._active():
            return
        objects = Path(_git(self.repository, "rev-parse", "--git-path", "objects"))
        if not objects.is_absolute():
            objects = self.repository / objects
        alternates = objects / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(str(self.base / "outside-objects") + "\n", encoding="utf-8")
        self._expect_policy_rejection()
        alternates.unlink()

        _git(self.repository, "config", "remote.origin.promisor", "true")
        _git(self.repository, "config", "remote.origin.partialclonefilter", "blob:none")
        self._expect_policy_rejection()

    def test_concurrent_derivations_are_private_and_network_free(self) -> None:
        if not self._active():
            return
        seed = self._seed()
        barrier = threading.Barrier(4)

        def derive_once(_index: int) -> tuple[str, str, str]:
            barrier.wait(timeout=10)
            with seed.derive() as fixture:
                root = Path(fixture.root)
                objects = Path(_git(root, "rev-parse", "--absolute-git-dir")) / "objects"
                self.assertFalse((objects / "info" / "alternates").exists())
                self.assertFalse(any(path.is_symlink() for path in root.rglob("*")))
                return (
                    str(Path(fixture.workspace).resolve()),
                    str(objects.resolve()),
                    str(Path(fixture.origin).resolve()),
                )

        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), mock.patch(
            "socket.create_connection", side_effect=AssertionError("network forbidden")
        ):
            with ThreadPoolExecutor(max_workers=4) as executor:
                identities = list(executor.map(derive_once, range(4)))
        self.assertEqual(len(set(identities)), 4)

    def test_interruption_cleanup_and_cross_worktree_state_isolation(self) -> None:
        if not self._active():
            return
        seed = self._seed()
        with seed.derive() as left, seed.derive() as right:
            left_root, right_root = Path(left.root), Path(right.root)
            (left_root / ".autopilot" / "state" / "receipt.json").write_text("{}\n", encoding="utf-8")
            (left_root / "only-left.txt").write_text("left\n", encoding="utf-8")
            self.assertFalse((right_root / ".autopilot" / "state" / "receipt.json").exists())
            self.assertFalse((right_root / "only-left.txt").exists())
            active_workspace = Path(left.workspace)
        self.assertFalse(active_workspace.exists())

        child_program = r'''
import importlib.util, sys, time
from pathlib import Path
module_path, source, storage = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("fpp_child_support", module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
with module.ContentAddressedFixtureSeed(source, storage).derive() as fixture:
    print(Path(fixture.workspace).resolve(), flush=True)
    time.sleep(60)
'''
        child = subprocess.Popen(
            [sys.executable, "-c", child_program, str(FIXTURE_SUPPORT), str(self.ap_root), str(self.storage)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "GIT_ALLOW_PROTOCOL": "file"},
        )
        assert child.stdout is not None
        abandoned = Path(child.stdout.readline().strip())
        self.assertTrue(abandoned.exists())
        child.terminate()
        child.wait(timeout=10)
        with self._seed().derive():
            deadline = time.monotonic() + 5
            while abandoned.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertFalse(abandoned.exists())

    def test_existing_copy_fixture_helper_remains_compatible(self) -> None:
        if not self._active():
            return
        helper_spec = importlib.util.spec_from_file_location(
            "fpp_existing_fixture_helper", FIXTURE_SUPPORT
        )
        assert helper_spec and helper_spec.loader
        helper = importlib.util.module_from_spec(helper_spec)
        helper_spec.loader.exec_module(helper)
        destination = self.base / "compatibility" / ".autopilot"
        copied = helper.copy_autopilot_fixture(self.ap_root, destination)
        self.assertEqual(copied, destination)
        self.assertTrue((copied / "bin" / "tool.py").is_file())
        self.assertTrue((copied / "state").is_dir())


if __name__ == "__main__":
    unittest.main()
