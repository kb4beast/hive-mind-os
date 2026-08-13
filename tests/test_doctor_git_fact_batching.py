"""Adversarial contract for one-shot immutable Git commit observations.

These tests intentionally precede the implementation.  They pin only the narrowly
authorized private observation boundary: commit bodies may be observed in one batch
for pure validation, while every mutable fact and every effect remains outside it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import os
import pickle
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / ".autopilot" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


controller = _load("controller", BIN / "controller.py")
durable = _load("gco_contract_durable", BIN / "durable_controller.py")


class Repo:
    def __init__(self, path: Path, *, object_format: str = "sha1") -> None:
        self.path = path
        self.path.mkdir(parents=True)
        args = ["init", "-q"]
        if object_format != "sha1":
            args.append(f"--object-format={object_format}")
        self.git(*args)
        self.git("config", "user.name", "GCO test")
        self.git("config", "user.email", "gco@example.invalid")

    def git(self, *args: str, input_bytes: bytes | None = None) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.path,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return completed.stdout.decode("ascii", "strict").strip()

    def commit(self, name: str, body: bytes | None = None) -> str:
        (self.path / name).write_bytes(body or name.encode("ascii"))
        self.git("add", name)
        self.git("commit", "-q", "-m", name)
        return self.git("rev-parse", "HEAD")

    def raw_commit(self, oid: str) -> bytes:
        return subprocess.run(
            ["git", "cat-file", "commit", oid],
            cwd=self.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout

    def git_dir(self) -> Path:
        value = self.git("rev-parse", "--absolute-git-dir")
        return Path(value)


def _packet(oid: str, body: bytes, *, kind: str = "commit") -> bytes:
    return f"{oid} {kind} {len(body)}\n".encode("ascii") + body + b"\n"


class GitCommitObservationContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = Repo(self.root / "repo")
        self.first = self.repo.commit("one.txt")
        self.second = self.repo.commit("two.txt")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def api(self):
        required = (
            "GitCommitObservation",
            "GitCommitObservationError",
            "_git_commit_observation",
            "_parse_git_commit_batch",
        )
        missing = [name for name in required if not hasattr(controller, name)]
        self.assertEqual(missing, [], "authorized GitCommitObservation API is not implemented")
        return (
            controller.GitCommitObservation,
            controller.GitCommitObservationError,
            controller._git_commit_observation,
            controller._parse_git_commit_batch,
        )

    def observe(self, repo: Path | None = None, oids: list[str] | None = None, **kwargs):
        _cls, _error, factory, _parser = self.api()
        return factory(repo or self.repo.path, oids or [self.first, self.second], **kwargs)

    def test_01_observation_is_frozen_finite_and_non_serializable(self) -> None:
        cls, _error, _factory, _parser = self.api()
        self.assertTrue(dataclasses.is_dataclass(cls))
        params = getattr(cls, "__dataclass_params__", None)
        self.assertTrue(params and params.frozen)
        with self.observe(oids=[self.first, self.first]) as observation:
            self.assertEqual(observation.oids, (self.first,))
            with self.assertRaises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                observation.oids = ()
            with self.assertRaises((pickle.PickleError, TypeError, AttributeError)):
                pickle.dumps(observation)

    def test_02_only_full_lowercase_deduplicated_commit_oids_are_accepted(self) -> None:
        _cls, error, factory, _parser = self.api()
        invalid = ["HEAD", self.first.upper(), self.first[:12], "g" * 40, "", " " + self.first]
        for oid in invalid:
            with self.subTest(oid=oid), self.assertRaises(error):
                with factory(self.repo.path, [oid]):
                    pass
        with factory(self.repo.path, [self.second, self.first, self.second]) as observation:
            self.assertEqual(observation.oids, (self.second, self.first))

    def test_03_commit_message_delimiters_cannot_forge_facts(self) -> None:
        tree = self.repo.git("rev-parse", "HEAD^{tree}")
        message = self.root / "message.bin"
        message.write_bytes(b"forge\x1e" + self.first.encode() + b"\x1f" + b"0" * 40 + b"\n")
        forged = self.repo.git("commit-tree", tree, "-p", self.second, "-F", str(message))
        with self.observe(oids=[forged]) as observation:
            self.assertEqual(observation.tree(forged), tree)
            self.assertEqual(observation.parents(forged), (self.second,))

    def test_04_duplicate_delimiter_records_cannot_overwrite_requested_commit(self) -> None:
        tree = self.repo.git("rev-parse", "HEAD^{tree}")
        message = self.root / "duplicate.bin"
        message.write_bytes(
            b"\x1e" + self.second.encode() + b"\x1f\x1f" + tree.encode() + b"\x1ffake\x1e"
        )
        commit = self.repo.git("commit-tree", tree, "-p", self.second, "-F", str(message))
        with self.observe(oids=[self.second, commit]) as observation:
            self.assertEqual(observation.parents(commit), (self.second,))
            self.assertEqual(observation.tree(commit), tree)

    def test_05_ref_move_create_delete_never_changes_frozen_facts(self) -> None:
        with self.observe(oids=[self.first, self.second]) as observation:
            old_tree = observation.tree(self.first)
            self.repo.git("update-ref", "refs/heads/mutable", self.first)
            self.repo.git("update-ref", "refs/heads/mutable", self.second, self.first)
            self.repo.git("update-ref", "-d", "refs/heads/mutable", self.second)
            self.assertEqual(observation.tree(self.first), old_tree)
            self.assertFalse(hasattr(observation, "refs"))

    def test_06_partial_false_negative_after_missing_object_is_not_reused_after_fetch(self) -> None:
        source = Repo(self.root / "source")
        source.commit("base.txt")
        subprocess.run(
            ["git", "clone", "-q", "--no-local", str(source.path), str(self.root / "clone")],
            check=True,
        )
        clone = self.root / "clone"
        unseen = source.commit("unseen.txt")
        _cls, error, factory, _parser = self.api()
        with self.assertRaises(error):
            with factory(clone, [unseen]):
                pass
        subprocess.run(["git", "fetch", "-q", "origin"], cwd=clone, check=True)
        with factory(clone, [unseen]) as observation:
            self.assertEqual(observation.oids, (unseen,))

    def test_07_replace_refs_are_rejected_even_when_replacements_are_disabled_for_batch(self) -> None:
        self.repo.git("replace", self.first, self.second)
        _cls, error, factory, _parser = self.api()
        with self.assertRaises(error):
            with factory(self.repo.path, [self.first]):
                pass

    def _assert_configuration_rejected(self, mutate) -> None:
        mutate()
        _cls, error, factory, _parser = self.api()
        with self.assertRaises(error):
            with factory(self.repo.path, [self.first]):
                pass

    def test_08_shallow_repository_is_rejected(self) -> None:
        self._assert_configuration_rejected(
            lambda: (self.repo.git_dir() / "shallow").write_text(self.first + "\n", encoding="ascii")
        )

    def test_09_grafts_are_rejected(self) -> None:
        def mutate() -> None:
            path = self.repo.git_dir() / "info" / "grafts"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.second + " " + self.first + "\n", encoding="ascii")
        self._assert_configuration_rejected(mutate)

    def test_10_alternate_object_store_is_rejected(self) -> None:
        other = Repo(self.root / "other")
        other.commit("other.txt")
        def mutate() -> None:
            path = self.repo.git_dir() / "objects" / "info" / "alternates"
            path.write_text(str(other.git_dir() / "objects") + "\n", encoding="utf-8")
        self._assert_configuration_rejected(mutate)

    def test_11_promisor_or_partial_clone_configuration_is_rejected(self) -> None:
        def mutate() -> None:
            self.repo.git("config", "remote.origin.promisor", "true")
            self.repo.git("config", "extensions.partialClone", "origin")
        self._assert_configuration_rejected(mutate)

    def test_12_ordinary_repository_and_linked_worktree_bind_distinct_git_dirs(self) -> None:
        worktree = self.root / "linked"
        self.repo.git("worktree", "add", "-q", "--detach", str(worktree), self.second)
        with self.observe() as main_observation, self.observe(worktree) as linked_observation:
            self.assertEqual(main_observation.common_dir, linked_observation.common_dir)
            self.assertNotEqual(main_observation.git_dir, linked_observation.git_dir)
            self.assertNotEqual(main_observation.repository_root, linked_observation.repository_root)

    def test_13_repository_identity_mismatch_fails_closed(self) -> None:
        other = Repo(self.root / "other")
        other.commit("other.txt")
        _cls, error, _factory, _parser = self.api()
        with self.observe(oids=[self.first]) as observation:
            with self.assertRaises(error):
                observation.assert_repository(other.path)

    def test_14_object_format_mismatch_fails_closed(self) -> None:
        try:
            sha256_repo = Repo(self.root / "sha256", object_format="sha256")
        except subprocess.CalledProcessError:
            self.skipTest("installed Git lacks SHA-256 repository support")
        sha256_repo.commit("sha256.txt")
        _cls, error, _factory, _parser = self.api()
        with self.observe(oids=[self.first]) as observation:
            with self.assertRaises(error):
                observation.assert_repository(sha256_repo.path)

    def parse(self, oids: list[str], payload: bytes, object_format: str = "sha1"):
        _cls, _error, _factory, parser = self.api()
        return parser(oids, payload, object_format=object_format)

    def test_15_parser_accepts_exact_framing_and_recomputes_hash(self) -> None:
        body = self.repo.raw_commit(self.first)
        facts = self.parse([self.first], _packet(self.first, body))
        self.assertEqual(tuple(facts), (self.first,))

    def test_16_missing_duplicate_extra_and_truncated_responses_are_fatal(self) -> None:
        body = self.repo.raw_commit(self.first)
        valid = _packet(self.first, body)
        cases = {
            "missing": b"",
            "duplicate": valid + valid,
            "extra": valid + b"extra commit 1\nx\n",
            "truncated-header": valid[:20],
            "truncated-body": valid[:-2],
        }
        _cls, error, _factory, _parser = self.api()
        for label, payload in cases.items():
            with self.subTest(label=label), self.assertRaises(error):
                self.parse([self.first], payload)

    def test_17_reordered_response_is_fatal(self) -> None:
        payload = _packet(self.second, self.repo.raw_commit(self.second)) + _packet(
            self.first, self.repo.raw_commit(self.first)
        )
        _cls, error, _factory, _parser = self.api()
        with self.assertRaises(error):
            self.parse([self.first, self.second], payload)

    def test_18_wrong_type_and_hash_mismatch_are_fatal(self) -> None:
        body = self.repo.raw_commit(self.first)
        changed = body.replace(b"one.txt", b"eno.txt", 1)
        _cls, error, _factory, _parser = self.api()
        for payload in (_packet(self.first, body, kind="blob"), _packet(self.first, changed)):
            with self.subTest(payload=payload[:80]), self.assertRaises(error):
                self.parse([self.first], payload)

    def test_19_commit_grammar_requires_one_tree_then_only_parents_before_blank_line(self) -> None:
        body = self.repo.raw_commit(self.first)
        tree_line = body.split(b"\n", 1)[0]
        bad_bodies = [
            body.replace(tree_line + b"\n", b"", 1),
            tree_line + b"\ntree " + b"0" * 40 + b"\n\nmessage\n",
            tree_line + b"\nauthor forged\nparent " + self.first.encode() + b"\n\nmessage\n",
        ]
        _cls, error, _factory, _parser = self.api()
        for bad in bad_bodies:
            oid = hashlib.sha1(b"commit " + str(len(bad)).encode() + b"\0" + bad).hexdigest()
            with self.subTest(body=bad[:80]), self.assertRaises(error):
                self.parse([oid], _packet(oid, bad))

    def test_20_nested_and_concurrent_observations_never_share_instances(self) -> None:
        with self.observe() as outer:
            with self.observe(oids=[self.first]) as inner:
                self.assertIsNot(outer, inner)
        barrier = threading.Barrier(2)
        def read() -> object:
            barrier.wait()
            with self.observe(oids=[self.first]) as observation:
                return observation
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _index: read(), range(2)))
        self.assertIsNot(first, second)

    def test_21_observation_is_invalidated_after_success_or_exception(self) -> None:
        _cls, error, _factory, _parser = self.api()
        with self.observe(oids=[self.first]) as success:
            self.assertEqual(success.tree(self.first), self.repo.git("rev-parse", f"{self.first}^{{tree}}"))
        with self.assertRaises(error):
            success.tree(self.first)
        captured = None
        with self.assertRaisesRegex(RuntimeError, "consumer"):
            with self.observe(oids=[self.first]) as captured:
                raise RuntimeError("consumer failure")
        assert captured is not None
        with self.assertRaises(error):
            captured.parents(self.first)

    def test_22_timeout_and_cancellation_kill_and_reap_batch_process(self) -> None:
        _cls, error, factory, _parser = self.api()
        self.assertTrue(hasattr(controller, "_start_git_commit_batch"), "private batch spawn seam is missing")
        for failure in (subprocess.TimeoutExpired("git", 0.01), KeyboardInterrupt()):
            class Process:
                def __init__(self) -> None:
                    self.killed = False
                    self.waited = False
                def communicate(self, *args, **kwargs):
                    raise failure
                def kill(self) -> None:
                    self.killed = True
                def wait(self, *args, **kwargs) -> int:
                    self.waited = True
                    return -9
            process = Process()
            with self.subTest(failure=type(failure).__name__), mock.patch.object(
                controller, "_start_git_commit_batch", return_value=process
            ):
                with self.assertRaises((error, KeyboardInterrupt)):
                    with factory(self.repo.path, [self.first], timeout_seconds=0.01):
                        pass
                self.assertTrue(process.killed)
                self.assertTrue(process.waited)

    def test_23_observation_cannot_capture_mutable_authority_or_effect_state(self) -> None:
        forbidden = {
            "authority", "claims", "releases", "leases", "snapshots", "receipts",
            "intents", "refs", "origin", "target", "cas", "force_with_lease",
        }
        state = self.repo.path / ".autopilot" / "state"
        state.mkdir(parents=True)
        mutable_files = {
            name: state / f"{name}.json"
            for name in ("authority", "claims", "releases", "leases", "snapshots", "receipts", "intents")
        }
        for path in mutable_files.values():
            path.write_text("before", encoding="utf-8")
        self.repo.git("config", "remote.origin.url", "before")
        self.repo.git("update-ref", "refs/heads/target", self.first)
        with self.observe(oids=[self.first]) as observation:
            for path in mutable_files.values():
                path.write_text("after", encoding="utf-8")
            self.repo.git("config", "remote.origin.url", "after")
            self.repo.git("update-ref", "refs/heads/target", self.second, self.first)
            field_names = {field.name.casefold() for field in dataclasses.fields(observation)}
            self.assertFalse(field_names & forbidden)
            for name in forbidden:
                self.assertFalse(hasattr(observation, name))
        self.assertTrue(all(path.read_text(encoding="utf-8") == "after" for path in mutable_files.values()))
        self.assertEqual(self.repo.git("config", "remote.origin.url"), "after")
        self.assertEqual(self.repo.git("rev-parse", "refs/heads/target"), self.second)

    def test_23b_one_replacement_disabled_binary_batch_process_is_used(self) -> None:
        _cls, _error, factory, _parser = self.api()
        self.assertTrue(hasattr(controller, "_start_git_commit_batch"), "private batch spawn seam is missing")
        body = self.repo.raw_commit(self.first)
        process = mock.Mock()
        process.communicate.return_value = (_packet(self.first, body), b"")
        process.returncode = 0
        process.wait.return_value = 0
        with mock.patch.object(controller, "_start_git_commit_batch", return_value=process) as start:
            with factory(self.repo.path, [self.first]) as observation:
                self.assertEqual(observation.oids, (self.first,))
        start.assert_called_once()
        self.assertIn("GIT_NO_REPLACE_OBJECTS", (BIN / "controller.py").read_text(encoding="utf-8"))

    def test_24_durable_consumption_is_explicit_pure_and_never_retained(self) -> None:
        self.api()
        signature = inspect.signature(durable.ControlPlane.validate_receipt)
        self.assertIn("commit_observation", signature.parameters)
        source = inspect.getsource(durable.ControlPlane)
        self.assertNotIn("self.commit_observation", source)
        self.assertNotIn("self._commit_observation", source)
        for effect in ("claim", "complete", "release", "reconcile", "publish_remote_claim"):
            method = getattr(durable.ControlPlane, effect)
            self.assertNotIn("commit_observation", inspect.signature(method).parameters)

    def test_25_effect_boundaries_keep_fresh_cas_and_force_with_lease_reads(self) -> None:
        self.api()
        controller_source = (BIN / "controller.py").read_text(encoding="utf-8")
        durable_source = (BIN / "durable_controller.py").read_text(encoding="utf-8")
        self.assertIn("--force-with-lease", controller_source)
        self.assertIn('"update-ref"', durable_source)
        for method_name in ("publish_remote_claim", "complete"):
            source = inspect.getsource(getattr(durable.ControlPlane, method_name))
            self.assertNotIn("snapshot_cache", source)
            self.assertNotIn("commit_observation", source)

    def test_26_sealed_recovery_and_release_barrier_cannot_consume_observation(self) -> None:
        self.api()
        for name in ("sealed_recovery.py", "release_barrier.py"):
            source = (BIN / name).read_text(encoding="utf-8")
            self.assertNotIn("GitCommitObservation", source)
            self.assertNotIn("git_commit_observation", source)

    def test_27_existing_autopilot_test_tree_is_frozen_by_scope(self) -> None:
        specs = _load(
            "gco_contract_specs",
            ROOT / "docs" / "execution" / "dags" / "git-commit-observation-v1" / "specs.py",
        )
        node = next(item for item in specs.SPECS if item["id"] == "GCO-TEST-020")
        self.assertEqual(node["write_scope"], ["tests/test_doctor_git_fact_batching.py"])
        self.assertNotIn(".autopilot/tests/", node["write_scope"])


if __name__ == "__main__":
    unittest.main()
