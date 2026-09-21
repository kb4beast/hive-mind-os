from __future__ import annotations

import ast
import base64
import copy
import dataclasses
import hashlib
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from unittest.mock import patch
from uuid import uuid4

from hive_mind_os import git_adapter
from hive_mind_os.autonomy import EpisodeAllowance
from hive_mind_os.contracts import tool_intent_digest
from hive_mind_os.git_adapter import (
    GitOperationFailed,
    GitPolicyDenied,
    GitWorkspace,
    PinViolation,
    WorkspaceDirty,
    _git_child_context,
    verify_delivery,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import AutonomyLevel
from hive_mind_os.policy import Action, PolicyEngine
from hive_mind_os.receipts import (
    FileReceiptValidator,
    ReceiptReference,
    portable_path_parts,
    sha256_digest,
)
from hive_mind_os.sandbox import (
    _INCOMPLETE_CREDENTIALED_STREAM,
    ConfinementViolation,
    SandboxDenied,
    SandboxRunner,
    SandboxSpec,
    SandboxTimeout,
)
from tests.fixtures.fixture_repo import (
    COMMIT_ONE_SHA,
    COMMIT_TWO_SHA,
    build_fixture_repo,
)

FIXED_HEAD_SHA = "6c4a1f8d7036a1520260c004170c740bf41b89a5"
FIXED_TREE_SHA = "e2fed4976f15a32feb343b06e51e634bddcae76c"

# Synthetic values only: no real credential, remote host call or grant is involved.
SYNTHETIC_TOKEN = "synthetic-git-token-a91c6e4d02"
SYNTHETIC_REMOTE = "https://github.com/example/synthetic-repo.git"
OTHER_REMOTE = "https://github.com/example/other-repo.git"
CREDENTIAL_NAMES = (
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
    "GIT_CONFIG_KEY_1",
    "GIT_CONFIG_VALUE_1",
    "GIT_CONFIG_KEY_2",
    "GIT_CONFIG_VALUE_2",
)
PROBE_NAMES = (
    *CREDENTIAL_NAMES,
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_TERMINAL_PROMPT",
    "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_DATE",
)
AMBIENT_INJECTION = {
    "GIT_CONFIG_COUNT": "7",
    "GIT_CONFIG_KEY_0": "http.extraHeader",
    "GIT_CONFIG_VALUE_0": "Authorization: ambient-synthetic-header",
    "GIT_CONFIG_KEY_1": "credential.helper",
    "GIT_CONFIG_VALUE_1": "ambient-synthetic-helper",
    "GIT_CONFIG_KEY_2": "core.sshCommand",
    "GIT_CONFIG_VALUE_2": "ambient-synthetic-ssh",
    "GIT_CONFIG_GLOBAL": "ambient-synthetic-global",
    "GIT_TERMINAL_PROMPT": "1",
}
# Hashes only, so a probe never echoes a supported secret form. No backslashes: the
# sandbox would treat the code argument as a path.
PROBE_CODE = (
    "import hashlib,json,os;"
    f"names={list(PROBE_NAMES)!r};"
    "print(json.dumps({n: (hashlib.sha256(os.environ[n].encode()).hexdigest() "
    "if n in os.environ else None) for n in names}, sort_keys=True))"
)
# A controlled stand-in for Git that derives every supported secret form from the
# header it was given and echoes it as ``sys.argv[2]`` directs (argv[1] is the remote).
ECHO_CODE = """
import base64, os, sys, time
header = os.environ['GIT_CONFIG_VALUE_0']
encoded = header.split(' ')[-1]
token = base64.b64decode(encoded).decode().split(':', 1)[1]
forms = [token, 'x-access-token:' + token, encoded, 'Basic ' + encoded, header]
mode = sys.argv[2]
NL = bytes([10])
out = sys.stdout.buffer
err = sys.stderr.buffer
if mode in ('echo', 'fail'):
    for form in forms:
        out.write(form.encode() + NL)
        err.write(form.encode() + NL)
    out.flush()
    err.flush()
    sys.exit(3 if mode == 'fail' else 0)
if mode == 'boundary':
    out.write(b'a' * (65536 - 10) + header.encode() + b'b' * 100)
    out.flush()
if mode == 'cap-stdout':
    out.write(b'y' * 100 + header.encode())
    out.flush()
if mode == 'cap-stderr':
    out.write(b'ok')
    out.flush()
    err.write(b'z' * 100 + header.encode())
    err.flush()
if mode == 'sleep':
    out.write(header.encode())
    err.write(header.encode())
    out.flush()
    err.flush()
    time.sleep(60)
"""


def secret_forms(token: str = SYNTHETIC_TOKEN) -> tuple[bytes, ...]:
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    return tuple(
        form.encode()
        for form in (
            token,
            f"x-access-token:{token}",
            encoded,
            f"Basic {encoded}",
            f"Authorization: Basic {encoded}",
        )
    )


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class GitAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.fixture = build_fixture_repo(self.base / "source-parent")
        self.counter = 0

    def workspace(self, pin: str = COMMIT_TWO_SHA) -> GitWorkspace:
        self.counter += 1
        return GitWorkspace.materialize(
            self.fixture.root,
            pin,
            self.base / f"workspace-{self.counter}",
            self.base / f"evidence-{self.counter}",
        )

    @staticmethod
    def declared_test_argv() -> list[str]:
        return [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ]

    def fix_and_commit(self) -> GitWorkspace:
        workspace = self.workspace()
        workspace.create_branch("phase/fix-increment")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        head = workspace.commit("fix: restore increment")
        self.assertEqual(head, FIXED_HEAD_SHA)
        return workspace

    def validate_receipts(self, workspace: GitWorkspace) -> None:
        validator = FileReceiptValidator(workspace.trusted_root)
        for record in workspace.receipt_records:
            validation = validator.validate(
                ReceiptReference(record["path"], record["digest"]),
                mission_id=record["mission_id"],
                state_ref=record["state_ref"],
                actor_id=record["actor_id"],
                action_id=record["action_id"],
                action_kind=record["action_kind"],
                action_digest=record["action_digest"],
            )
            self.assertTrue(validation.valid, validation.issues)

    def test_fixture_repository_has_stable_pinned_history(self) -> None:
        second_parent = self.base / "second-parent"
        repeated = build_fixture_repo(second_parent)
        self.assertEqual(
            (self.fixture.commit_one, self.fixture.commit_two),
            (COMMIT_ONE_SHA, COMMIT_TWO_SHA),
        )
        self.assertEqual(
            (repeated.commit_one, repeated.commit_two),
            (COMMIT_ONE_SHA, COMMIT_TWO_SHA),
        )

    def test_materialize_exact_detached_pin_and_inert_hooks(self) -> None:
        workspace = self.workspace(COMMIT_ONE_SHA)
        head = workspace._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "test exact materialized head",
        )
        symbolic = workspace._run_git(
            ["symbolic-ref", "-q", "HEAD"],
            Action.READ_REPOSITORY,
            "test detached head",
            allow_failure=True,
        )[0]
        self.assertEqual(head, COMMIT_ONE_SHA)
        self.assertEqual(symbolic["result"], "failed")
        self.assertFalse((self.fixture.root.parent / "fixture-hook-ran.txt").exists())

    def test_materialize_excludes_local_codex_bookkeeping_refs(self) -> None:
        bookkeeping = (
            self.fixture.root
            / ".git"
            / "refs"
            / "codex"
            / "turn-diffs"
            / "checkpoints"
            / ("a" * 16)
            / ("b" * 16)
        )
        bookkeeping.mkdir(parents=True)
        (bookkeeping / "1785167248210").write_text(
            COMMIT_TWO_SHA + "\n",
            encoding="ascii",
        )
        workspace = self.workspace()
        self.assertFalse(
            (
                workspace.container_root
                / "source"
                / ".git"
                / "refs"
                / "codex"
            ).exists()
        )
        self.assertEqual(
            workspace._git_text(
                ["rev-parse", "HEAD"],
                Action.READ_REPOSITORY,
                "test materialized head without app refs",
            ),
            COMMIT_TWO_SHA,
        )
        if os.name == "nt":
            self.assertIn("SYSTEMROOT", workspace.runner.spec.env_allowlist)
            self.assertIn("GIT_CONFIG_KEY_1", workspace.runner.spec.env_allowlist)
            self.assertIn("GIT_CONFIG_VALUE_1", workspace.runner.spec.env_allowlist)
            self.assertIn("GIT_CONFIG_KEY_2", workspace.runner.spec.env_allowlist)
            self.assertIn("GIT_CONFIG_VALUE_2", workspace.runner.spec.env_allowlist)

    def test_materialize_ignores_host_global_git_configuration(self) -> None:
        global_config = self.base / "host-global.gitconfig"
        global_config.write_text(
            "[alias]\n\thive-forbidden = status\n",
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": str(global_config),
                "GIT_CONFIG_NOSYSTEM": "0",
            },
        ):
            workspace = self.workspace(COMMIT_ONE_SHA)
            receipt, output = workspace._run_git(
                ["config", "--global", "--get", "alias.hive-forbidden"],
                Action.READ_REPOSITORY,
                "verify isolated global Git configuration",
                allow_failure=True,
            )
        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(output, b"")

    def test_mutable_and_short_pins_are_rejected(self) -> None:
        for pin in ("main", "v1.0", COMMIT_ONE_SHA[:12]):
            with self.subTest(pin=pin):
                with self.assertRaises(PinViolation):
                    self.workspace(pin)

    def test_repository_urls_are_rejected(self) -> None:
        for source in (
            "https://example.invalid/repo.git",
            "file:///tmp/repo.git",
            "git@example.invalid:repo.git",
            r"\\example.invalid\share\repo.git",
        ):
            with self.subTest(source=source):
                with self.assertRaises(PinViolation):
                    GitWorkspace.materialize(
                        source,
                        COMMIT_ONE_SHA,
                        self.base / f"url-{self.counter}",
                        self.base / f"url-evidence-{self.counter}",
                    )
                self.counter += 1

    def test_branch_edit_commit_diff_tree_and_receipts(self) -> None:
        workspace = self.workspace()
        workspace.create_branch("phase/fix-increment")
        hook = workspace.root / ".git" / "hooks" / "pre-commit"
        hook.write_bytes(
            b"#!/bin/sh\nprintf hook-ran > hook-ran.txt\nexit 1\n"
        )
        try:
            hook.chmod(0o755)
        except OSError:
            pass
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        diff, digest = workspace.diff()
        self.assertIn(b"-    return value - 1", diff)
        self.assertIn(b"+    return value + 1", diff)
        self.assertTrue(digest.startswith("sha256:"))
        head = workspace.commit("fix: restore increment")
        self.assertEqual(head, FIXED_HEAD_SHA)
        self.assertFalse((workspace.root / "hook-ran.txt").exists())
        tree = workspace._git_text(
            ["rev-parse", "HEAD^{tree}"],
            Action.READ_REPOSITORY,
            "test committed tree",
        )
        self.assertEqual(tree, FIXED_TREE_SHA)
        self.validate_receipts(workspace)

    def test_write_file_rejects_nonportable_and_escaping_paths(self) -> None:
        workspace = self.workspace()
        for path in (
            "../outside.txt",
            "/absolute.txt",
            r"nested\windows.txt",
            ".git/HEAD",
            ".GIT/config",
        ):
            with self.subTest(path=path):
                with self.assertRaises((ValueError, ConfinementViolation)):
                    workspace.write_file(path, b"denied")

    def test_lower_authority_cannot_write_git_metadata(self) -> None:
        workspace = self.workspace()
        workspace.policy = PolicyEngine(AutonomyLevel.SANDBOX)
        with self.assertRaises(GitPolicyDenied):
            workspace.create_branch("phase/typed-denial")
        original_head = (workspace.root / ".git" / "HEAD").read_bytes()
        for path in (".git/HEAD", ".GIT/refs/heads/metadata-bypass"):
            with self.subTest(path=path):
                with self.assertRaises(ConfinementViolation):
                    workspace.write_file(path, b"ref: refs/heads/metadata-bypass\n")
        self.assertEqual((workspace.root / ".git" / "HEAD").read_bytes(), original_head)

    def test_declared_tests_fail_at_fixture_head_and_pass_after_fix(self) -> None:
        workspace = self.workspace()
        failed = workspace.run_tests(self.declared_test_argv())
        self.assertEqual(failed["result"], "failed")
        self.assertNotEqual(failed["execution"]["exit_code"], 0)
        self.assertIn(
            b"FAIL: test_increment_regression",
            workspace._artifact(failed, "stderr"),
        )
        workspace.create_branch("phase/fix-increment")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        workspace.commit("fix: restore increment")
        passed = workspace.run_tests(self.declared_test_argv())
        self.assertEqual(
            passed["result"],
            "succeeded",
            workspace._artifact(passed, "stderr").decode("utf-8", "replace"),
        )
        self.assertEqual(passed["execution"]["exit_code"], 0)

    def test_export_and_verify_delivery_with_resolvable_receipts(self) -> None:
        workspace = self.fix_and_commit()
        delivery = workspace.export_delivery(self.base / "delivery")
        self.assertTrue(verify_delivery(delivery.root, self.fixture.root))
        manifest = json.loads(delivery.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["head_sha"], FIXED_HEAD_SHA)
        self.assertEqual(manifest["head_tree"], FIXED_TREE_SHA)
        self.assertEqual(manifest["files"], ["tiny_pkg/maths.py"])
        self.validate_receipts(workspace)

        golden = json.loads(
            (
                Path(__file__).parent
                / "fixtures"
                / "git"
                / "delivery.json"
            ).read_text(encoding="utf-8")
        )
        normalized = deepcopy(manifest)
        normalized["bundle_digest"] = "<git-serialization-digest>"
        normalized["patch_digest"] = "<git-serialization-digest>"
        normalized["receipts"] = ["<content-addressed-receipts>"]
        self.assertEqual(normalized, golden)

        original_manifest = delivery.manifest_path.read_bytes()
        invalid_manifests = []
        for schema_version in (999, True):
            invalid = deepcopy(manifest)
            invalid["schema_version"] = schema_version
            invalid_manifests.append(invalid)
        empty_receipts = deepcopy(manifest)
        empty_receipts["receipts"] = []
        invalid_manifests.append(empty_receipts)
        truncated_receipts = deepcopy(manifest)
        truncated_receipts["receipts"] = truncated_receipts["receipts"][:1]
        invalid_manifests.append(truncated_receipts)
        escaping_file = deepcopy(manifest)
        escaping_file["files"] = ["../escape"]
        invalid_manifests.append(escaping_file)
        for invalid_manifest in invalid_manifests:
            delivery.manifest_path.write_text(
                json.dumps(invalid_manifest, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            self.assertFalse(verify_delivery(delivery.root, self.fixture.root))
            delivery.manifest_path.write_bytes(original_manifest)

        first_receipt = delivery.root / "evidence" / manifest["receipts"][0]["path"]
        original_receipt = first_receipt.read_bytes()
        first_receipt.write_bytes(b"{}")
        self.assertFalse(verify_delivery(delivery.root, self.fixture.root))
        first_receipt.write_bytes(original_receipt)

        tampered_patch = delivery.patch_path.read_bytes() + b"\n# coherent tamper\n"
        delivery.patch_path.write_bytes(tampered_patch)
        manifest["patch_digest"] = sha256_digest(tampered_patch)
        delivery.manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertFalse(verify_delivery(delivery.root, self.fixture.root))

    def test_export_rejects_a_new_hivemind_orchestration_dependency(self) -> None:
        workspace = self.workspace()
        workspace.create_branch("phase/no-orchestration-leak")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"from hive_mind_os.dag_executor import DagExecutor\n\n"
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        workspace.commit("test: inject orchestration dependency")

        with self.assertRaisesRegex(GitOperationFailed, "independent of HiveMind"):
            workspace.export_delivery(self.base / "orchestration-leak")

    def test_dirty_workspace_cannot_export_delivery(self) -> None:
        workspace = self.workspace()
        workspace.create_branch("phase/dirty")
        workspace.write_file("dirty.txt", b"uncommitted")
        with self.assertRaises(WorkspaceDirty):
            workspace.export_delivery(self.base / "dirty-delivery")

    def test_preexisting_delivery_root_is_rejected_before_any_write(self) -> None:
        workspace = self.fix_and_commit()
        delivery_root = self.base / "unsafe-delivery"
        outside = self.base / "outside-evidence"
        delivery_root.mkdir()
        outside.mkdir()
        evidence = delivery_root / "evidence"
        try:
            evidence.symlink_to(outside, target_is_directory=True)
        except OSError:
            evidence.mkdir()
        with self.assertRaises(WorkspaceDirty):
            workspace.export_delivery(delivery_root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_verifier_rejects_escaped_evidence_root(self) -> None:
        workspace = self.fix_and_commit()
        delivery = workspace.export_delivery(self.base / "delivery")
        evidence = delivery.root / "evidence"
        outside = self.base / "outside-evidence"
        evidence.rename(outside)
        try:
            evidence.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlinks are unavailable")
            linked = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(evidence), str(outside)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                check=False,
            )
            if linked.returncode != 0:
                self.skipTest("directory junctions are unavailable")
        self.assertFalse(verify_delivery(delivery.root, self.fixture.root))
        if evidence.is_symlink():
            evidence.unlink()
        else:
            evidence.rmdir()
        outside.rename(evidence)

    def test_truncated_git_output_fails_closed(self) -> None:
        workspace = self.workspace()
        workspace.write_file("tiny_pkg/maths.py", b"x" * 4096)
        git_name = Path(shutil.which("git") or "git").name
        workspace.runner = SandboxRunner(
            SandboxSpec(
                workspace.root,
                argv_allowlist=(git_name,),
                timeout_s=5.0,
                max_output_bytes=64,
            ),
            workspace.trusted_root,
            EpisodeAllowance(5, 5.0),
            policy=workspace.policy,
            role=workspace.role,
            runner_identity="git-sandbox-runner-v1",
        )
        with self.assertRaisesRegex(GitOperationFailed, "output limit"):
            workspace.diff()
        self.assertEqual(workspace.receipt_records[-1]["result"], "succeeded")

    def test_policy_denial_occurs_before_git_spawn(self) -> None:
        workspace = self.workspace()
        workspace.policy = PolicyEngine(AutonomyLevel.OBSERVE)
        before = workspace.runner.spawn_count
        with self.assertRaises(GitPolicyDenied):
            workspace.create_branch("phase/denied")
        self.assertEqual(workspace.runner.spawn_count, before)

    def test_run_tests_cannot_bypass_typed_git_authority(self) -> None:
        workspace = self.workspace()
        workspace.policy = PolicyEngine(AutonomyLevel.SANDBOX)
        with self.assertRaises(GitPolicyDenied):
            workspace.create_branch("phase/typed-denial")
        before = workspace.runner.spawn_count
        git = shutil.which("git") or "git"
        bypasses = (
            [git, "switch", "-c", "phase/bypass"],
            [git, "push", "origin", "HEAD:refs/heads/forbidden-push"],
        )
        for argv in bypasses:
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(GitPolicyDenied, "reserved"):
                    workspace.run_tests(argv)
        self.assertEqual(workspace.runner.spawn_count, before)
        self.assertFalse((workspace.root / ".git" / "refs" / "heads" / "bypass").exists())
        self.assertFalse(
            (
                workspace.container_root
                / "source"
                / ".git"
                / "refs"
                / "heads"
                / "forbidden-push"
            ).exists()
        )

    def test_api_has_no_merge_rebase_or_force_surface(self) -> None:
        forbidden = [
            name
            for name in dir(GitWorkspace)
            if any(
                keyword in name.lower()
                for keyword in ("merge", "rebase", "force")
            )
        ]
        self.assertEqual(forbidden, [])
        self.assertEqual(
            [name for name in dir(GitWorkspace) if "push" in name.lower()],
            ["push_branch"],
        )


class GitChildCredentialBoundaryTests(unittest.TestCase):
    """The credential and config-injection boundary of every Git child process.

    Git itself is replaced by a controlled Python child (``patch_git_argv``) wherever
    a test needs to observe or echo the child's environment, so nothing here touches
    the network. Observations are captured while the leak window would be open and
    asserted afterwards, so cleanup cannot hide a leak.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.fixture = build_fixture_repo(self.base / "source-parent")
        self.counter = 0

    def workspace(self, pin: str = COMMIT_TWO_SHA) -> GitWorkspace:
        self.counter += 1
        return GitWorkspace.materialize(
            self.fixture.root,
            pin,
            self.base / f"workspace-{self.counter}",
            self.base / f"evidence-{self.counter}",
        )

    @staticmethod
    def patch_git_argv(code: str) -> Any:
        def python_argv(hooks_root: Path, args: Sequence[str]) -> list[str]:
            return [sys.executable, "-c", code, *args]

        return patch.object(GitWorkspace, "_git_argv", staticmethod(python_argv))

    @contextmanager
    def observe_popen(
        self,
        *,
        block_when: Callable[[dict[str, str]], bool] | None = None,
    ) -> Iterator[tuple[list[dict[str, Any]], threading.Event, threading.Event]]:
        real_popen = subprocess.Popen
        calls: list[dict[str, Any]] = []
        entered = threading.Event()
        release = threading.Event()

        def observed(command: list[str], **kwargs: Any) -> Any:
            environment = dict(kwargs.get("env") or {})
            calls.append({"argv": list(command), "env": environment})
            if block_when is not None and block_when(environment):
                entered.set()
                if not release.wait(timeout=30):
                    raise RuntimeError("probe was never released")
            return real_popen(command, **kwargs)

        with patch.object(subprocess, "Popen", side_effect=observed):
            try:
                yield calls, entered, release
            finally:
                release.set()

    def tuned_runner(
        self,
        workspace: GitWorkspace,
        *,
        ledger: EvidenceLedger | None = None,
        **changes: Any,
    ) -> SandboxRunner:
        runner = SandboxRunner(
            dataclasses.replace(workspace.runner.spec, **changes),
            workspace.trusted_root,
            EpisodeAllowance(50, 50.0),
            policy=workspace.policy,
            role=workspace.role,
            runner_identity=workspace.runner.runner_identity,
            ledger=ledger,
        )
        workspace.runner = runner
        return runner

    def expected_environment(self, workspace: GitWorkspace) -> dict[str, str | None]:
        encoded = base64.b64encode(
            f"x-access-token:{SYNTHETIC_TOKEN}".encode()
        ).decode("ascii")
        values = {
            "GIT_CONFIG_COUNT": "3" if os.name == "nt" else "1",
            "GIT_CONFIG_KEY_0": f"http.{SYNTHETIC_REMOTE}/.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {encoded}",
            "GIT_CONFIG_GLOBAL": str(workspace.git_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
        if os.name == "nt":
            values.update(
                {
                    "GIT_CONFIG_KEY_1": "http.sslBackend",
                    "GIT_CONFIG_VALUE_1": "schannel",
                    "GIT_CONFIG_KEY_2": "http.schannelCheckRevoke",
                    "GIT_CONFIG_VALUE_2": "false",
                }
            )
        return {
            name: (sha_text(values[name]) if name in values else None)
            for name in PROBE_NAMES
        }

    def credentialed(
        self,
        workspace: GitWorkspace,
        mode: str,
        *,
        allow_failure: bool = False,
        token: str = SYNTHETIC_TOKEN,
    ) -> tuple[dict[str, Any], bytes]:
        return workspace._run_git(
            [SYNTHETIC_REMOTE, mode],
            Action.READ_REPOSITORY,
            f"controlled credentialed child ({mode})",
            allow_failure=allow_failure,
            credential=(SYNTHETIC_REMOTE, token),
        )

    def last_receipt(self, workspace: GitWorkspace) -> dict[str, Any]:
        record = workspace.receipt_records[-1]
        path = workspace.trusted_root / Path(*portable_path_parts(record["path"]))
        return json.loads(path.read_text(encoding="utf-8"))

    def assert_nothing_persisted_leaks(
        self,
        workspace: GitWorkspace,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        scanned = 0
        for path in sorted(workspace.trusted_root.rglob("*")):
            if path.is_file():
                scanned += 1
                content = path.read_bytes()
                for form in secret_forms():
                    self.assertNotIn(form, content, path.name)
        self.assertGreater(scanned, 0)
        surfaces = [json.dumps(workspace.receipt_records, sort_keys=True)]
        if ledger is not None:
            surfaces.append(json.dumps(ledger.events(), sort_keys=True, default=str))
        for surface in surfaces:
            for form in secret_forms():
                self.assertNotIn(form.decode(), surface)

    def test_credentialed_child_receives_exactly_the_supplied_header(self) -> None:
        workspace = self.workspace()
        with self.patch_git_argv(PROBE_CODE), patch.dict(os.environ, AMBIENT_INJECTION):
            before = dict(os.environ)
            _, output = workspace._run_git(
                [SYNTHETIC_REMOTE],
                Action.READ_REPOSITORY,
                "probe credentialed child environment",
                credential=(SYNTHETIC_REMOTE, SYNTHETIC_TOKEN),
            )
            after = dict(os.environ)
        self.assertEqual(before, after)
        for value in after.values():
            for form in secret_forms():
                self.assertNotIn(form.decode(), value)
        # Ambient count/key/value/global/prompt values were replaced or dropped; only
        # the supplied header, the isolated config and (on Windows) the fixed options
        # reached the child.
        self.assertEqual(json.loads(output), self.expected_environment(workspace))

    def test_parent_stays_clean_while_a_credentialed_popen_is_blocked(self) -> None:
        workspace = self.workspace()
        encoded = base64.b64encode(
            f"x-access-token:{SYNTHETIC_TOKEN}".encode()
        ).decode("ascii")
        with (
            self.patch_git_argv(PROBE_CODE),
            patch.dict(os.environ, AMBIENT_INJECTION),
            self.observe_popen(
                block_when=lambda env: encoded in env.get("GIT_CONFIG_VALUE_0", "")
            ) as (calls, entered, release),
        ):
            before = dict(os.environ)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    workspace._run_git,
                    [SYNTHETIC_REMOTE],
                    Action.READ_REPOSITORY,
                    "credentialed child blocked in Popen",
                    credential=(SYNTHETIC_REMOTE, SYNTHETIC_TOKEN),
                )
                try:
                    self.assertTrue(entered.wait(timeout=30))
                    # Observed while the credentialed spawn is blocked mid-Popen.
                    during = dict(os.environ)
                    unrelated = workspace.run_tests([sys.executable, "-c", PROBE_CODE])
                    unrelated_output = workspace._artifact(unrelated, "stdout")
                finally:
                    release.set()
                _, credentialed_output = future.result(timeout=60)
            after = dict(os.environ)
        self.assertEqual(before, during)
        self.assertEqual(before, after)
        for value in during.values():
            self.assertNotIn(encoded, value)
            self.assertNotIn(SYNTHETIC_TOKEN, value)
        # The unrelated run_tests child saw no Git config, credential or date value.
        self.assertEqual(
            json.loads(unrelated_output),
            {name: None for name in PROBE_NAMES},
        )
        self.assertEqual(
            json.loads(credentialed_output),
            self.expected_environment(workspace),
        )
        carriers = [
            call for call in calls if encoded in call["env"].get("GIT_CONFIG_VALUE_0", "")
        ]
        self.assertEqual(len(carriers), 1)

    def test_ambient_config_injection_is_dropped_for_clone_read_and_credentialed_children(
        self,
    ) -> None:
        with patch.dict(os.environ, AMBIENT_INJECTION):
            before = dict(os.environ)
            with self.observe_popen() as (calls, _entered, _release):
                workspace = self.workspace()
                workspace._git_text(
                    ["rev-parse", "HEAD"],
                    Action.READ_REPOSITORY,
                    "read under ambient injection",
                )
                git_calls = list(calls)
                with self.patch_git_argv(PROBE_CODE):
                    workspace._run_git(
                        [SYNTHETIC_REMOTE],
                        Action.READ_REPOSITORY,
                        "credentialed under ambient injection",
                        credential=(SYNTHETIC_REMOTE, SYNTHETIC_TOKEN),
                    )
            after = dict(os.environ)
        self.assertEqual(before, after)
        self.assertIn("clone", git_calls[0]["argv"])
        self.assertGreaterEqual(len(git_calls), 4)
        for call in git_calls:
            environment = call["env"]
            with self.subTest(argv=call["argv"][-3:]):
                for name in CREDENTIAL_NAMES:
                    self.assertNotIn(name, environment)
                self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
                self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
                self.assertNotEqual(
                    environment["GIT_CONFIG_GLOBAL"], "ambient-synthetic-global"
                )
        for call in calls:
            for value in call["env"].values():
                self.assertNotIn("ambient-synthetic", value)
        carrier = calls[-1]["env"]
        expected_names = {"GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"}
        if os.name == "nt":
            expected_names |= set(CREDENTIAL_NAMES)
        self.assertEqual(set(CREDENTIAL_NAMES) & set(carrier), expected_names)

    def test_ambient_injection_does_not_reach_real_git_reads(self) -> None:
        workspace = self.workspace()
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "alias.hive-injected",
                "GIT_CONFIG_VALUE_0": "status",
            },
        ):
            receipt, output = workspace._run_git(
                ["config", "--get", "alias.hive-injected"],
                Action.READ_REPOSITORY,
                "verify ambient config injection is dropped",
                allow_failure=True,
            )
        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(output, b"")

    def test_legacy_git_dates_still_reach_only_the_commit_child(self) -> None:
        workspace = self.workspace()
        workspace.create_branch("phase/legacy-dates")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        with patch.dict(os.environ):
            os.environ.pop("GIT_AUTHOR_DATE", None)
            os.environ.pop("GIT_COMMITTER_DATE", None)
            with self.observe_popen() as (calls, _entered, _release):
                workspace.commit("fix: restore increment")
        commits = [call for call in calls if "--no-gpg-sign" in call["argv"]]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["env"]["GIT_AUTHOR_DATE"], "2026-01-03T00:00:00Z")
        self.assertEqual(commits[0]["env"]["GIT_COMMITTER_DATE"], "2026-01-03T00:00:00Z")
        for call in calls:
            if call is not commits[0]:
                self.assertNotIn("GIT_AUTHOR_DATE", call["env"])

    def test_echoed_credential_forms_never_reach_artifacts_receipts_events_or_errors(
        self,
    ) -> None:
        workspace = self.workspace()
        ledger = EvidenceLedger()
        self.tuned_runner(workspace, ledger=ledger)
        redacted = (b"[REDACTED]" + bytes([10])) * 5
        with self.patch_git_argv(ECHO_CODE):
            receipt, stdout = self.credentialed(workspace, "echo")
            self.assertEqual(stdout, redacted)
            self.assertEqual(workspace._artifact(receipt, "stderr"), redacted)

            receipt, stdout = self.credentialed(workspace, "fail", allow_failure=True)
            self.assertEqual(receipt["result"], "failed")
            self.assertEqual(stdout, redacted)

            with self.assertRaises(GitOperationFailed) as captured:
                self.credentialed(workspace, "fail")
            self.assertIn("[REDACTED]", str(captured.exception))
            for form in secret_forms():
                self.assertNotIn(form.decode(), str(captured.exception))
                self.assertNotIn(form.decode(), repr(captured.exception))

            receipt, stdout = self.credentialed(workspace, "boundary")
            self.assertEqual(
                stdout, b"a" * (65536 - 10) + b"[REDACTED]" + b"b" * 100
            )
            stream = receipt["execution"]["stdout"]
            self.assertEqual(stream["bytes"], len(stdout))
            self.assertEqual(stream["digest"], sha256_digest(stdout))
            self.assertFalse(stream["truncated"])
        self.assert_nothing_persisted_leaks(workspace, ledger)
        self.assertEqual(ledger.events(), [])
        self.assertEqual(workspace.runner.spawn_count, 4)
        self.assertEqual(workspace.runner.tool_calls_used, 4)
        self.assertEqual(workspace.runner.compute_units_used, 4.0)

    def test_truncated_and_timed_out_credentialed_streams_store_a_fixed_marker(self) -> None:
        marker = _INCOMPLETE_CREDENTIALED_STREAM
        workspace = self.workspace()
        ledger = EvidenceLedger()
        with self.patch_git_argv(ECHO_CODE):
            self.tuned_runner(workspace, ledger=ledger, max_output_bytes=128)
            with self.assertRaisesRegex(GitOperationFailed, "output limit"):
                self.credentialed(workspace, "cap-stdout")
            receipt = self.last_receipt(workspace)
            self.assertEqual(workspace._artifact(receipt, "stdout"), marker)
            self.assertTrue(receipt["execution"]["stdout"]["truncated"])
            self.assertEqual(receipt["execution"]["stdout"]["bytes"], len(marker))
            self.assertEqual(receipt["execution"]["stdout"]["digest"], sha256_digest(marker))

            receipt, stdout = self.credentialed(workspace, "cap-stderr")
            self.assertEqual(stdout, b"ok")
            self.assertEqual(workspace._artifact(receipt, "stderr"), marker)
            self.assertTrue(receipt["execution"]["stderr"]["truncated"])
            self.assertFalse(receipt["execution"]["stdout"]["truncated"])

            self.tuned_runner(workspace, ledger=ledger, timeout_s=4.0)
            with self.assertRaises(SandboxTimeout) as captured:
                self.credentialed(workspace, "sleep")
            timed_out = captured.exception.receipt
            self.assertEqual(timed_out["execution"]["outcome"], "timeout")
            self.assertEqual(workspace._artifact(timed_out, "stdout"), marker)
            self.assertEqual(workspace._artifact(timed_out, "stderr"), marker)
            for form in secret_forms():
                self.assertNotIn(form.decode(), str(captured.exception))
        self.assert_nothing_persisted_leaks(workspace, ledger)

    def test_context_mismatch_and_bad_credentials_are_denied_before_spawn(self) -> None:
        workspace = self.workspace()
        ledger = EvidenceLedger()
        runner = self.tuned_runner(workspace, ledger=ledger)
        spawned = runner.spawn_count
        userinfo = f"https://x-access-token:{SYNTHETIC_TOKEN}@github.com/example/r.git"
        with self.patch_git_argv(ECHO_CODE), self.observe_popen() as (calls, _e, _r):
            with self.assertRaisesRegex(SandboxDenied, "another remote") as denied:
                workspace._run_git(
                    [OTHER_REMOTE, "echo"],
                    Action.READ_REPOSITORY,
                    "argv remote differs from the bound remote",
                    credential=(SYNTHETIC_REMOTE, SYNTHETIC_TOKEN),
                )
            with self.assertRaises(PinViolation) as userinfo_error:
                workspace._run_git(
                    [userinfo, "echo"],
                    Action.READ_REPOSITORY,
                    "remote carrying userinfo",
                    credential=(userinfo, SYNTHETIC_TOKEN),
                )
            with self.assertRaisesRegex(GitOperationFailed, "credential is required"):
                self.credentialed(workspace, "echo", token="")
            self.assertEqual(calls, [])
        self.assertEqual(runner.spawn_count, spawned)
        for error in (denied.exception, userinfo_error.exception):
            for form in secret_forms():
                self.assertNotIn(form.decode(), str(error))
        self.assert_nothing_persisted_leaks(workspace, ledger)

    def test_adapter_built_context_is_bound_to_runner_argv_executable_remote_and_one_use(
        self,
    ) -> None:
        workspace = self.workspace()
        ledger = EvidenceLedger()
        runner = self.tuned_runner(workspace, ledger=ledger)
        other = SandboxRunner(
            workspace.runner.spec,
            self.base / "other-evidence",
            EpisodeAllowance(10, 10.0),
            policy=workspace.policy,
            role=workspace.role,
            runner_identity=runner.runner_identity,
        )
        code = "print('bound')"
        argv = [sys.executable, "-c", code, SYNTHETIC_REMOTE]

        def intent(command: list[str]) -> dict[str, Any]:
            document: dict[str, Any] = {
                "schema_version": 1,
                "action_id": f"ACT-bound-{uuid4()}",
                "mission_id": "mission-bound",
                "state_ref": "MISSION_STATE:mission-bound:1",
                "actor_id": "builder-pass-1",
                "kind": "command",
                "description": "execute a context-bound command",
                "action_digest": f"sha256:{'0' * 64}",
                "policy_decision_ref": "POLICY-bound",
                "lease_id": "LEASE-bound",
                "idempotency_key": f"IDEMPOTENCY-bound-{uuid4()}",
                "rollback_ref": None,
                "command": {"argv": command, "path_args": []},
                "status": "proposed",
            }
            document["action_digest"] = tool_intent_digest(document)
            return document

        def build(command: list[str], *, bound: SandboxRunner = runner) -> Any:
            return _git_child_context(
                bound,
                command,
                workspace.git_config,
                remote=SYNTHETIC_REMOTE,
                token=SYNTHETIC_TOKEN,
            )

        cases: list[tuple[str, str, SandboxRunner, list[str], Any]] = [
            ("runner", "another runner", other, argv, build(argv)),
            (
                "arguments",
                "other arguments",
                runner,
                argv,
                build([sys.executable, "-c", "print('other')", SYNTHETIC_REMOTE]),
            ),
            (
                "executable",
                "another executable",
                runner,
                argv,
                build(["definitely-not-a-hive-executable", *argv[1:]]),
            ),
            (
                "remote",
                "another remote",
                runner,
                [sys.executable, "-c", code, OTHER_REMOTE],
                build([sys.executable, "-c", code, OTHER_REMOTE]),
            ),
        ]
        for label, reason, target, command, context in cases:
            with self.subTest(case=label):
                spawned = target.spawn_count
                with self.assertRaisesRegex(SandboxDenied, reason):
                    target.run(intent(command), _trusted=context)
                self.assertEqual(target.spawn_count, spawned)
        with self.subTest(case="reuse"):
            context = build(argv)
            first = runner.run(intent(argv), _trusted=context)
            self.assertEqual(first["result"], "succeeded")
            spawned = runner.spawn_count
            with self.assertRaisesRegex(SandboxDenied, "already used"):
                runner.run(intent([*argv]), _trusted=context)
            self.assertEqual(runner.spawn_count, spawned)
        with self.subTest(case="unallowlisted credential names"):
            bare = SandboxRunner(
                SandboxSpec(
                    workspace.root,
                    argv_allowlist=(Path(sys.executable).name,),
                    allow_interpreter_flags=True,
                ),
                self.base / "bare-evidence",
                EpisodeAllowance(10, 10.0),
                policy=workspace.policy,
                role=workspace.role,
                runner_identity="git-sandbox-runner-v1",
            )
            with self.assertRaisesRegex(SandboxDenied, "not allowlisted"):
                bare.run(intent(argv), _trusted=build(argv, bound=bare))
            self.assertEqual(bare.spawn_count, 0)
        self.assert_nothing_persisted_leaks(workspace, ledger)

    def test_git_child_context_is_private_redacted_and_not_serializable(self) -> None:
        workspace = self.workspace()
        argv = [sys.executable, "-c", "print('bound')", SYNTHETIC_REMOTE]
        context = _git_child_context(
            workspace.runner,
            argv,
            workspace.git_config,
            remote=SYNTHETIC_REMOTE,
            token=SYNTHETIC_TOKEN,
        )
        for rendered in (repr(context), str(context), f"{context}"):
            for form in secret_forms():
                self.assertNotIn(form.decode(), rendered)
        with self.assertRaises(TypeError):
            copy.copy(context)
        with self.assertRaises(TypeError):
            copy.deepcopy(context)
        with self.assertRaises(TypeError):
            pickle.dumps(context)
        self.assertFalse(hasattr(context, "__dict__"))

    def test_public_spec_intent_and_receipt_digests_do_not_depend_on_the_credential(self) -> None:
        workspace = self.workspace()
        spec_digest = workspace.runner.spec.spec_digest()
        allowlist = tuple(workspace.runner.spec.env_allowlist)
        for name in CREDENTIAL_NAMES:
            self.assertIn(name, allowlist)
        receipts = []
        with self.patch_git_argv(ECHO_CODE):
            for token in (SYNTHETIC_TOKEN, "another-synthetic-token-5d20b7f8c1"):
                receipt, _ = self.credentialed(workspace, "echo", token=token)
                receipts.append(receipt)
        self.assertEqual(workspace.runner.spec.spec_digest(), spec_digest)
        self.assertEqual(tuple(workspace.runner.spec.env_allowlist), allowlist)
        for receipt in receipts:
            self.assertEqual(receipt["execution"]["sandbox_spec_digest"], spec_digest)
            self.assertEqual(receipt["execution"]["argv"][3], SYNTHETIC_REMOTE)
            self.assertEqual(receipt["execution"]["requested_argv"][3], SYNTHETIC_REMOTE)
        # Different credentials, identical stored bytes: the artifact digests match too.
        self.assertEqual(receipts[0]["artifacts"][0]["digest"], receipts[1]["artifacts"][0]["digest"])
        validator = FileReceiptValidator(workspace.trusted_root)
        for record in workspace.receipt_records:
            validation = validator.validate(
                ReceiptReference(record["path"], record["digest"]),
                mission_id=record["mission_id"],
                state_ref=record["state_ref"],
                actor_id=record["actor_id"],
                action_id=record["action_id"],
                action_kind=record["action_kind"],
                action_digest=record["action_digest"],
            )
            self.assertTrue(validation.valid, validation.issues)

    def test_old_signature_spawn_subclass_serves_context_free_paths_and_fails_closed(self) -> None:
        class LegacyRunner(SandboxRunner):
            def _spawn(self, argv: list[str]) -> subprocess.Popen[bytes]:
                return super()._spawn(argv)

        workspace = self.workspace()
        source = workspace.runner
        workspace.runner = LegacyRunner(
            source.spec,
            workspace.trusted_root,
            EpisodeAllowance(20, 20.0),
            policy=workspace.policy,
            role=workspace.role,
            runner_identity=source.runner_identity,
        )
        receipt = workspace.run_tests([sys.executable, "-c", "print('legacy')"])
        self.assertEqual(receipt["result"], "succeeded")
        self.assertEqual(workspace.runner.spawn_count, 1)
        with self.assertRaises(TypeError):
            workspace._git_text(["rev-parse", "HEAD"], Action.READ_REPOSITORY, "needs a context")
        with self.patch_git_argv(ECHO_CODE), self.assertRaises(TypeError):
            self.credentialed(workspace, "echo")
        self.assertEqual(workspace.runner.spawn_count, 1)
        self.assert_nothing_persisted_leaks(workspace)

    def test_parent_mutating_helpers_are_gone_and_git_runner_calls_are_confined(self) -> None:
        self.assertFalse(hasattr(git_adapter, "_git_http_credentials"))
        self.assertFalse(hasattr(git_adapter, "_isolated_git_config"))
        source_root = Path(git_adapter.__file__).resolve().parent
        source = (source_root / "git_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("os.environ.update", source)
        module = ast.parse(source)
        owners: set[str] = set()
        for function in ast.walk(module):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "runner"
                ):
                    owners.add(function.name)
        # GitWorkspace._execute is the single funnel that builds the child context.
        self.assertEqual(owners, {"_execute"})
        # A trusted in-tree caller that drives a Git-allowlisted runner directly would
        # inherit the allowlisted ambient names; fail if a new one appears.
        offenders = sorted(
            path.relative_to(source_root).as_posix()
            for path in source_root.rglob("*.py")
            if path.name != "git_adapter.py"
            and re.search(r"\.runner\.run\(|workspace\.runner\b", path.read_text(encoding="utf-8"))
        )
        self.assertEqual(offenders, [])

    # -- remand 1: the context can never be silently omitted -------------------------

    def test_credential_remote_or_git_argv_without_the_context_is_refused_before_intent(
        self,
    ) -> None:
        workspace = self.workspace()
        runner = workspace.runner
        git = shutil.which("git") or "git"
        counters = (runner.tool_calls_used, runner.compute_units_used, runner.spawn_count)
        cases: list[tuple[str, dict[str, Any], list[str], type[Exception]]] = [
            (
                "token and remote",
                {"token": SYNTHETIC_TOKEN, "remote": SYNTHETIC_REMOTE},
                [git, "--version", SYNTHETIC_REMOTE],
                GitOperationFailed,
            ),
            (
                "remote only",
                {"remote": SYNTHETIC_REMOTE},
                [git, "--version", SYNTHETIC_REMOTE],
                GitOperationFailed,
            ),
            (
                "token only",
                {"token": SYNTHETIC_TOKEN},
                [git, "--version"],
                GitOperationFailed,
            ),
            ("bare git argv", {}, [git, "--version"], GitPolicyDenied),
        ]
        with (
            patch.object(runner, "_spawn", side_effect=AssertionError("REACHED_SPAWN")),
            self.observe_popen() as (calls, _entered, _release),
        ):
            for label, keywords, command, error_type in cases:
                with self.subTest(case=label):
                    with self.assertRaises(error_type) as captured:
                        GitWorkspace._execute(
                            runner,
                            command,
                            mission_id="synthetic-mission",
                            role=workspace.role,
                            description="Git command without the isolated context",
                            **keywords,
                        )
                    for form in secret_forms():
                        self.assertNotIn(form.decode(), str(captured.exception))
            self.assertEqual(calls, [])
        # Nothing was executed, and not even the episode allowance was consumed.
        self.assertEqual(
            (runner.tool_calls_used, runner.compute_units_used, runner.spawn_count),
            counters,
        )
        # The explicit legacy path for a non-Git command stays context-free.
        receipt = GitWorkspace._execute(
            runner,
            [sys.executable, "-c", "print('legacy')"],
            mission_id="synthetic-mission",
            role=workspace.role,
            description="non-Git command keeps the legacy path",
        )
        self.assertEqual(receipt["result"], "succeeded")

    def test_every_workspace_git_invocation_carries_the_isolated_context(self) -> None:
        with patch.dict(os.environ, AMBIENT_INJECTION):
            with self.observe_popen() as (calls, _entered, _release):
                workspace = self.workspace()
                workspace.create_branch("phase/every-path")
                workspace.write_file(
                    "tiny_pkg/maths.py",
                    b"def increment(value: int) -> int:\n    return value + 1\n",
                )
                workspace.commit("fix: restore increment")
                self.assertTrue(workspace.status_clean())
                workspace.diff()
                delivery = workspace.export_delivery(self.base / "every-path-delivery")
                self.assertTrue(verify_delivery(delivery.root, self.fixture.root))
        git_calls = [
            call
            for call in calls
            if Path(call["argv"][0]).name.casefold().removesuffix(".exe") == "git"
        ]
        # Clone, checkout, reads, branch, commit, export and both verification clones.
        self.assertGreaterEqual(len(git_calls), 20)
        for call in git_calls:
            environment = call["env"]
            with self.subTest(argv=call["argv"][-3:]):
                self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
                self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
                self.assertNotEqual(
                    environment["GIT_CONFIG_GLOBAL"], "ambient-synthetic-global"
                )
                for name in CREDENTIAL_NAMES:
                    self.assertNotIn(name, environment)

    # -- remand 2: the canonical credential-free URL is bound at creation ------------

    def test_non_canonical_remotes_are_denied_before_any_spawn(self) -> None:
        workspace = self.workspace()
        runner = workspace.runner
        git = shutil.which("git") or "git"
        cases = (
            ("host", "https://example.invalid/owner/repo.git"),
            ("query", SYNTHETIC_REMOTE + "?credential=benign"),
            ("path", "https://github.com/example/repo/extra.git"),
            ("port", "https://github.com:444/example/repo.git"),
            ("fragment", SYNTHETIC_REMOTE + "#fragment"),
            ("scheme", "http://github.com/example/repo.git"),
            ("userinfo", f"https://x-access-token:{SYNTHETIC_TOKEN}@github.com/example/repo.git"),
            ("missing suffix", "https://github.com/example/repo"),
            ("host case", "https://GitHub.com/example/repo.git"),
        )
        counters = (runner.tool_calls_used, runner.compute_units_used, runner.spawn_count)
        with (
            patch.object(runner, "_spawn", side_effect=AssertionError("NONCANONICAL_REACHED_SPAWN")),
            self.observe_popen() as (calls, _entered, _release),
        ):
            for label, remote in cases:
                command = [git, "--version", remote]
                surfaces: dict[str, Any] = {
                    "execute with credential": lambda: GitWorkspace._execute(
                        runner,
                        command,
                        mission_id="synthetic-mission",
                        role=workspace.role,
                        description="non-canonical credentialed remote",
                        git_config=workspace.git_config,
                        remote=remote,
                        token=SYNTHETIC_TOKEN,
                    ),
                    "execute without credential": lambda: GitWorkspace._execute(
                        runner,
                        command,
                        mission_id="synthetic-mission",
                        role=workspace.role,
                        description="non-canonical remote",
                        git_config=workspace.git_config,
                        remote=remote,
                    ),
                    "context helper": lambda: _git_child_context(
                        runner,
                        command,
                        workspace.git_config,
                        remote=remote,
                        token=SYNTHETIC_TOKEN,
                    ),
                    "credential helper": lambda: git_adapter._git_credential_environment(
                        remote, SYNTHETIC_TOKEN
                    ),
                }
                for surface, attempt in surfaces.items():
                    with self.subTest(remote=label, surface=surface):
                        with self.assertRaises(PinViolation) as captured:
                            attempt()
                        for form in secret_forms():
                            self.assertNotIn(form.decode(), str(captured.exception))
            self.assertEqual(calls, [])
        self.assertEqual(
            (runner.tool_calls_used, runner.compute_units_used, runner.spawn_count),
            counters,
        )
        self.assert_nothing_persisted_leaks(workspace)

    def test_canonical_remote_binding_keeps_the_accepted_host_scope(self) -> None:
        workspace = self.workspace()
        argv = [sys.executable, "-c", "print('bound')"]
        enterprise = "https://ghe.example.test/owner/repo.git"
        # The canonical public URL still binds.
        _git_child_context(
            workspace.runner,
            [*argv, SYNTHETIC_REMOTE],
            workspace.git_config,
            remote=SYNTHETIC_REMOTE,
            token=SYNTHETIC_TOKEN,
        )
        # A non-default host is only ever bound where materialization already allowed
        # it, and never for a credentialed context.
        _git_child_context(
            workspace.runner,
            [*argv, enterprise],
            workspace.git_config,
            remote=enterprise,
            allowed_hosts=("ghe.example.test",),
        )
        for keywords in (
            {},
            {"allowed_hosts": ("ghe.example.test",), "token": SYNTHETIC_TOKEN},
        ):
            with self.subTest(keywords=sorted(keywords)):
                with self.assertRaises(PinViolation):
                    _git_child_context(
                        workspace.runner,
                        [*argv, enterprise],
                        workspace.git_config,
                        remote=enterprise,
                        **keywords,
                    )

    # -- remand 3: each receipt index row binds to its own invocation ----------------

    def race_same_runner_receipts(
        self,
        workspace: GitWorkspace,
        first: Callable[[], object],
        second: Callable[[], object],
    ) -> list[dict[str, Any]]:
        """Park invocation A after its receipt exists, let B finish, then release A."""

        reached = threading.Event()
        release = threading.Event()
        original = GitWorkspace._append_receipt
        parked: list[str] = []
        errors: list[BaseException] = []
        before = len(workspace.receipt_records)

        def delayed(records: list[dict[str, Any]], runner: SandboxRunner, receipt: Any) -> None:
            if threading.current_thread().name == "receipt-race-first":
                parked.append(receipt["action_id"])
                reached.set()
                if not release.wait(timeout=30):
                    raise RuntimeError("receipt race was never released")
            return original(records, runner, receipt)

        def run_first() -> None:
            try:
                first()
            except BaseException as error:  # reported through ``errors`` below
                errors.append(error)

        with patch.object(GitWorkspace, "_append_receipt", new=staticmethod(delayed)):
            thread = threading.Thread(target=run_first, name="receipt-race-first")
            thread.start()
            try:
                self.assertTrue(reached.wait(timeout=30))
                second()
                # Observed while A is parked: the shared reference now names B.
                shared = workspace.runner.last_reference
            finally:
                release.set()
                thread.join(timeout=60)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        rows = workspace.receipt_records[before:]
        self.assertEqual(len(rows), 2)
        by_action = {row["action_id"]: row for row in rows}
        self.assertEqual(len(by_action), 2)
        assert shared is not None
        # The race really happened: the shared reference is not A's row.
        self.assertNotEqual(by_action[parked[0]]["path"], shared.path)
        self.assertIn(shared.path, {row["path"] for row in rows})
        return rows

    def assert_rows_bind_their_own_retained_receipts(
        self,
        workspace: GitWorkspace,
        rows: list[dict[str, Any]],
    ) -> None:
        validator = FileReceiptValidator(workspace.trusted_root)
        for row in rows:
            raw = (workspace.trusted_root / Path(*portable_path_parts(row["path"]))).read_bytes()
            retained = json.loads(raw)
            self.assertEqual(sha256_digest(raw), row["digest"])
            for field in (
                "mission_id",
                "state_ref",
                "actor_id",
                "action_id",
                "action_kind",
                "action_digest",
            ):
                self.assertEqual(retained[field], row[field], field)
            self.assertEqual(retained["result"], row["result"])
            validation = validator.validate(
                ReceiptReference(row["path"], row["digest"]),
                mission_id=row["mission_id"],
                state_ref=row["state_ref"],
                actor_id=row["actor_id"],
                action_id=row["action_id"],
                action_kind=row["action_kind"],
                action_digest=row["action_digest"],
            )
            self.assertTrue(validation.valid, validation.issues)

    def test_same_runner_local_git_receipts_index_their_own_invocation(self) -> None:
        workspace = self.workspace()

        def version(description: str) -> Callable[[], object]:
            return lambda: workspace._run_git(
                ["--version"], Action.READ_REPOSITORY, description
            )

        rows = self.race_same_runner_receipts(
            workspace, version("first local Git version"), version("second local Git version")
        )
        self.assert_rows_bind_their_own_retained_receipts(workspace, rows)

    def test_same_runner_credentialed_receipts_index_their_own_invocation(self) -> None:
        workspace = self.workspace()
        second_token = "another-synthetic-token-5d20b7f8c1"
        with self.patch_git_argv(ECHO_CODE):
            rows = self.race_same_runner_receipts(
                workspace,
                lambda: self.credentialed(workspace, "echo"),
                lambda: self.credentialed(workspace, "echo", token=second_token),
            )
        self.assert_rows_bind_their_own_retained_receipts(workspace, rows)
        for token in (SYNTHETIC_TOKEN, second_token):
            for path in workspace.trusted_root.rglob("*"):
                if path.is_file():
                    content = path.read_bytes()
                    for form in secret_forms(token):
                        self.assertNotIn(form, content, path.name)

    def test_receipt_index_never_reads_the_shared_reference_and_checks_retained_bytes(
        self,
    ) -> None:
        workspace = self.workspace()
        runner = workspace.runner
        first, _ = workspace._run_git(["--version"], Action.READ_REPOSITORY, "first")
        second, _ = workspace._run_git(["--version"], Action.READ_REPOSITORY, "second")
        assert runner.last_reference is not None
        latest = runner.last_reference
        rows: list[dict[str, Any]] = []
        GitWorkspace._append_receipt(rows, runner, first)
        self.assertNotEqual(rows[0]["path"], latest.path)
        self.assertEqual(rows[0]["action_id"], first["action_id"])
        # The public legacy reference is untouched and may even be cleared.
        self.assertEqual(runner.last_reference, latest)
        runner.last_reference = None
        GitWorkspace._append_receipt(rows, runner, second)
        self.assertEqual(rows[1]["path"], latest.path)
        self.assert_rows_bind_their_own_retained_receipts(workspace, rows)

        # A receipt that was never published under its content address is refused.
        forged = {**first, "result": "failed"}
        with self.assertRaisesRegex(GitOperationFailed, "did not publish"):
            GitWorkspace._append_receipt(rows, runner, forged)
        # Retained bytes that differ from the returned receipt are refused, not indexed.
        retained = workspace.trusted_root / Path(*portable_path_parts(rows[0]["path"]))
        retained.write_bytes(b"{}")
        with self.assertRaisesRegex(GitOperationFailed, "does not match"):
            GitWorkspace._append_receipt(rows, runner, first)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
