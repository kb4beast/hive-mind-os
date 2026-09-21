from __future__ import annotations

import base64
import copy
import errno
import json
import os
import pickle
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from hive_mind_os.autonomy import EpisodeAllowance
from hive_mind_os.contracts import (
    tool_intent_digest,
    validate_contract,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import AutonomyLevel, Role
from hive_mind_os.policy import PolicyEngine
from hive_mind_os.receipts import (
    FileReceiptValidator,
    ReceiptReference,
    sha256_digest,
)
from hive_mind_os.sandbox import (
    _INCOMPLETE_CREDENTIALED_STREAM,
    ConfinementViolation,
    SandboxDenied,
    SandboxError,
    SandboxRunner,
    SandboxSpec,
    SandboxTimeout,
    _canonical_receipt,
    _interpreter_flags,
    _TrustedChildContext,
)

_MOUNT_POINT_TAG = 0xA0000003
_SECRET_ENV = "HIVE_MIND_TRUSTED_SECRET"
_SYNTHETIC_TOKEN = "synthetic-sandbox-token-3b7e91c4"
_SYNTHETIC_REMOTE = "https://github.com/example/synthetic-repo.git"
_OTHER_REMOTE = "https://github.com/example/other-repo.git"
# A controlled child that derives every supported secret form from its own
# environment and echoes it in the mode named by ``sys.argv[1]``.  No backslashes:
# the sandbox would treat the argument as a path.
_ECHO_CHILD = """
import base64, os, sys, time
token = os.environ['HIVE_MIND_TRUSTED_SECRET']
encoded = base64.b64encode(('x-access-token:' + token).encode()).decode()
header = 'Authorization: Basic ' + encoded
forms = [token, 'x-access-token:' + token, encoded, 'Basic ' + encoded, header]
mode = sys.argv[1]
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


class SandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "workspace"
        self.trusted = self.base / "evidence"
        self.root.mkdir()
        self.python_name = Path(sys.executable).name

    def spec(self, **overrides: Any) -> SandboxSpec:
        values: dict[str, Any] = {
            "root": self.root,
            "argv_allowlist": (self.python_name,),
            "allow_interpreter_flags": True,
            "timeout_s": 5.0,
            "max_output_bytes": 4096,
        }
        values.update(overrides)
        return SandboxSpec(**values)

    def runner(
        self,
        *,
        spec: SandboxSpec | None = None,
        allowance: EpisodeAllowance | None = None,
        role: Role = Role.BUILDER,
        trusted: Path | None = None,
        ledger: EvidenceLedger | None = None,
        policy: PolicyEngine | None = None,
    ) -> SandboxRunner:
        return SandboxRunner(
            spec or self.spec(),
            trusted or self.trusted,
            allowance or EpisodeAllowance(20, 100.0),
            role=role,
            ledger=ledger,
            policy=policy,
        )

    def intent(
        self,
        argv: list[str],
        *,
        path_args: list[int] | None = None,
        action_id: str = "ACT-sandbox-1",
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": 1,
            "action_id": action_id,
            "mission_id": "mission-sandbox",
            "state_ref": "MISSION_STATE:mission-sandbox:1",
            "actor_id": "builder-pass-1",
            "kind": "command",
            "description": "execute a bounded sandbox command",
            "action_digest": f"sha256:{'0' * 64}",
            "policy_decision_ref": "POLICY-sandbox-1",
            "lease_id": "LEASE-sandbox-1",
            "idempotency_key": action_id,
            "rollback_ref": None,
            "command": {
                "argv": argv,
                "path_args": path_args or [],
            },
            "status": "proposed",
        }
        document["action_digest"] = tool_intent_digest(document)
        return document

    def stdout(self, receipt: dict[str, Any], trusted: Path | None = None) -> bytes:
        root = trusted or self.trusted
        artifact = receipt["artifacts"][0]
        return (root / artifact["path"]).read_bytes()

    def junction(self, link: Path, target: Path) -> None:
        """Create an NTFS junction at ``link``, or skip with the observed failure."""

        try:
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            self.skipTest(f"mklink /J could not run: {type(error).__name__}: {error}")
        if created.returncode != 0:
            self.skipTest(
                f"mklink /J exited {created.returncode}: "
                f"{(created.stderr or created.stdout).strip()}"
            )
        self.addCleanup(self.remove_junction, link)
        try:
            tag = getattr(os.lstat(link), "st_reparse_tag", 0)
        except OSError as error:
            self.skipTest(f"mklink /J reported success but {link.name} is unreadable: {error}")
        if tag != _MOUNT_POINT_TAG:
            self.skipTest(
                f"mklink /J reported success but {link.name} carries reparse tag "
                f"{tag:#x}, not a junction ({_MOUNT_POINT_TAG:#x})"
            )

    @staticmethod
    def remove_junction(link: Path) -> None:
        """Detach a junction without descending into whatever it points at."""

        try:
            os.rmdir(link)
        except FileNotFoundError:
            pass

    def test_happy_path_receipt_round_trips_through_validator(self) -> None:
        runner = self.runner()
        intent = self.intent([sys.executable, "-c", "print('hi')"])
        receipt = runner.run(intent)
        self.assertTrue(validate_contract("tool-receipt", receipt).valid)
        self.assertEqual(
            receipt["enforced"],
            {
                "filesystem": "none",
                "network": "none",
                "resources": "posix-rlimit-only",
                "executable_identity": "name-allowlist-only",
            },
        )
        self.assertEqual(self.stdout(receipt).splitlines(), [b"hi"])
        self.assertIsNotNone(runner.last_reference)
        assert runner.last_reference is not None
        validation = FileReceiptValidator(self.trusted).validate(
            runner.last_reference,
            mission_id=intent["mission_id"],
            state_ref=intent["state_ref"],
            actor_id=intent["actor_id"],
            action_id=intent["action_id"],
            action_kind=intent["kind"],
            action_digest=intent["action_digest"],
        )
        self.assertTrue(validation.valid, validation.issues)
        self.assertTrue(validation.succeeded)

    def test_default_rejects_inline_python_execution(self) -> None:
        runner = self.runner(spec=SandboxSpec(root=self.root))
        with self.assertRaisesRegex(SandboxDenied, "inline interpreter"):
            runner.run(self.intent([sys.executable, "-c", "print('no spawn')"]))
        self.assertEqual(runner.spawn_count, 0)

    def test_versioned_python_names_reject_inline_execution(self) -> None:
        self.assertEqual(_interpreter_flags("python3.11"), frozenset({"-c", "-m"}))
        self.assertEqual(_interpreter_flags("pypy3.10"), frozenset({"-c", "-m"}))

    def test_undeclared_path_like_argument_is_confined(self) -> None:
        runner = self.runner()
        with self.assertRaises(ConfinementViolation):
            runner.run(
                self.intent([sys.executable, "-c", "print('no spawn')", "../outside.txt"])
            )
        self.assertEqual(runner.spawn_count, 0)

    def test_intent_digest_binds_every_declared_field(self) -> None:
        runner = self.runner()
        intent = self.intent([sys.executable, "-c", "print('bound')"])
        intent["description"] = "mutated after digest"
        with self.assertRaisesRegex(SandboxDenied, "digest"):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)

        missing_command = dict(intent)
        missing_command["action_digest"] = f"sha256:{'0' * 64}"
        missing_command.pop("command")
        missing_command["action_digest"] = tool_intent_digest(missing_command)
        self.assertFalse(validate_contract("tool-intent", missing_command).valid)

    def test_non_allowlisted_executable_is_denied_before_spawn(self) -> None:
        runner = self.runner()
        intent = self.intent(["definitely-not-a-hive-executable", "--version"])
        with self.assertRaisesRegex(SandboxDenied, "allowlisted"):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)
        self.assertFalse((self.trusted / "receipts").exists())

    def test_parent_path_escape_is_rejected(self) -> None:
        runner = self.runner()
        intent = self.intent(
            [sys.executable, "-c", "print('no spawn')", "../outside.txt"],
            path_args=[3],
        )
        with self.assertRaises(ConfinementViolation):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)

    def test_https_remote_url_is_not_auto_detected_as_a_workspace_path(self) -> None:
        url = "https://github.com/patencyhealth-lab/hive-mind-a4-pilot.git"
        runner = self.runner()
        receipt = runner.run(self.intent([sys.executable, "-c", "print('pushed')", url]))
        self.assertEqual(receipt["result"], "succeeded")
        self.assertEqual(runner.spawn_count, 1)
        self.assertEqual(receipt["execution"]["argv"][3], url)

    def test_https_url_at_a_declared_path_index_is_still_validated(self) -> None:
        url = "https://github.com/patencyhealth-lab/hive-mind-a4-pilot.git"
        runner = self.runner()
        with self.assertRaises(ConfinementViolation):
            runner.run(self.intent([sys.executable, "-c", "print('no spawn')", url], path_args=[3]))
        self.assertEqual(runner.spawn_count, 0)

    def test_https_url_carrying_credentials_is_never_exempted(self) -> None:
        runner = self.runner()
        for url in (
            "https://user:pass@github.com/o/r.git",
            "https://token@github.com/o/r.git",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ConfinementViolation):
                    runner.run(self.intent([sys.executable, "-c", "print('no spawn')", url]))
        self.assertEqual(runner.spawn_count, 0)

    def test_non_https_remote_forms_keep_their_confinement_treatment(self) -> None:
        runner = self.runner()
        for argument in (
            "http://github.com/o/r.git",
            "file:///c/tmp/repo.git",
            "file://server/share/repo.git",
            "ssh://git@github.com/o/r.git",
            "git://github.com/o/r.git",
            "git@github.com:o/r.git",
            "//server/share/repo.git",
            "\\\\server\\share\\repo.git",
            "https://github.com/o/../r.git",
            "https://github.com/o//r.git",
        ):
            with self.subTest(argument=argument):
                with self.assertRaises(ConfinementViolation):
                    runner.run(self.intent([sys.executable, "-c", "print('no spawn')", argument]))
        self.assertEqual(runner.spawn_count, 0)

    def test_embedded_https_substring_does_not_exempt_a_path_argument(self) -> None:
        runner = self.runner()
        for argument in ("./notes/https://weird.txt", "docs/https://x.md"):
            with self.subTest(argument=argument):
                with self.assertRaises(ConfinementViolation):
                    runner.run(self.intent([sys.executable, "-c", "print('no spawn')", argument]))
        self.assertEqual(runner.spawn_count, 0)

    def test_nested_parent_traversal_argument_is_still_rejected(self) -> None:
        runner = self.runner()
        for path_args in ([], [3]):
            with self.subTest(path_args=path_args):
                with self.assertRaises(ConfinementViolation):
                    runner.run(
                        self.intent(
                            [sys.executable, "-c", "print('no spawn')", "nested/../../outside.txt"],
                            path_args=path_args,
                        )
                    )
        self.assertEqual(runner.spawn_count, 0)

    def test_absolute_path_outside_root_is_still_rejected(self) -> None:
        outside = (self.base / "outside.txt").resolve()
        runner = self.runner()
        for path_args in ([], [3]):
            with self.subTest(path_args=path_args):
                with self.assertRaises(ConfinementViolation):
                    runner.run(
                        self.intent(
                            [sys.executable, "-c", "print('no spawn')", str(outside)],
                            path_args=path_args,
                        )
                    )
        self.assertEqual(runner.spawn_count, 0)

    def test_relative_path_argument_is_still_resolved_inside_the_root(self) -> None:
        runner = self.runner()
        receipt = runner.run(
            self.intent([sys.executable, "-c", "print('resolved')", "nested/file.txt"])
        )
        self.assertEqual(receipt["result"], "succeeded")
        rewritten = Path(receipt["execution"]["argv"][3])
        self.assertTrue(rewritten.is_absolute())
        self.assertEqual(rewritten, (runner.spec.root / "nested" / "file.txt").resolve())
        self.assertEqual(receipt["execution"]["requested_argv"][3], "nested/file.txt")

    @unittest.skipIf(os.name == "nt", "POSIX-only symlink confinement case")
    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (self.root / "link.txt").symlink_to(outside)
        runner = self.runner()
        intent = self.intent(
            [sys.executable, "-c", "print('no spawn')", "link.txt"],
            path_args=[3],
        )
        with self.assertRaises(ConfinementViolation):
            runner.run(intent)
        self.assertEqual(runner.spawn_count, 0)

    @unittest.skipUnless(os.name == "nt", "NTFS junction confinement case")
    def test_windows_junction_escape_is_rejected(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("outside-secret", encoding="utf-8")
        link = self.root / "escape"
        self.junction(link, outside)
        self.assertEqual(
            (link / "secret.txt").read_text(encoding="utf-8"),
            "outside-secret",
        )
        runner = self.runner()
        for argument, path_args in (("escape", [3]), ("escape/secret.txt", None)):
            with self.subTest(argument=argument):
                with self.assertRaisesRegex(ConfinementViolation, "escapes sandbox root"):
                    runner.run(
                        self.intent(
                            [sys.executable, "-c", "print('no spawn')", argument],
                            path_args=path_args,
                        )
                    )
        self.assertEqual(runner.spawn_count, 0)

    def test_environment_is_scrubbed_unless_allowlisted(self) -> None:
        name = "HIVE_MIND_SANDBOX_SENTINEL"
        code = f"import os;print(os.environ.get({name!r}, 'absent'))"
        with patch.dict(os.environ, {name: "present"}):
            absent_runner = self.runner(trusted=self.base / "absent-evidence")
            absent = absent_runner.run(
                self.intent([sys.executable, "-c", code], action_id="ACT-env-absent")
            )
            allowed_runner = self.runner(
                spec=self.spec(env_allowlist=(name,)),
                trusted=self.base / "allowed-evidence",
            )
            allowed = allowed_runner.run(
                self.intent([sys.executable, "-c", code], action_id="ACT-env-allowed")
            )
        self.assertEqual(
            self.stdout(absent, self.base / "absent-evidence").splitlines(),
            [b"absent"],
        )
        self.assertEqual(
            self.stdout(allowed, self.base / "allowed-evidence").splitlines(),
            [b"present"],
        )

    def test_fixed_environment_is_digest_bound_without_inheriting_host_values(self) -> None:
        name = "HIVE_MIND_SANDBOX_FIXED"
        code = f"import os;print(os.environ.get({name!r}, 'absent'))"
        with patch.dict(os.environ, {name: "host-value"}):
            runner = self.runner(
                spec=self.spec(fixed_environment=((name, "sealed-value"),)),
                trusted=self.base / "fixed-evidence",
            )
            receipt = runner.run(
                self.intent([sys.executable, "-c", code], action_id="ACT-env-fixed")
            )
        self.assertEqual(
            self.stdout(receipt, self.base / "fixed-evidence").splitlines(),
            [b"sealed-value"],
        )
        self.assertNotEqual(
            self.spec().spec_digest(),
            runner.spec.spec_digest(),
        )

    def test_timeout_kills_process_tree_and_leaves_failed_receipt(self) -> None:
        marker = self.root / "survived.txt"
        child = (
            "import pathlib,time;"
            "time.sleep(0.8);"
            "pathlib.Path('survived.txt').write_text('not killed')"
        )
        parent = (
            "import subprocess,sys,time;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
            "time.sleep(5)"
        )
        runner = self.runner(spec=self.spec(timeout_s=0.2))
        started = time.monotonic()
        with self.assertRaises(SandboxTimeout) as captured:
            runner.run(self.intent([sys.executable, "-c", parent]))
        self.assertLess(time.monotonic() - started, 2.0)
        receipt = captured.exception.receipt
        self.assertEqual(receipt["execution"]["outcome"], "timeout")
        self.assertEqual(receipt["result"], "failed")
        self.assertIsNotNone(runner.last_reference)
        time.sleep(1.0)
        self.assertFalse(marker.exists())

    def test_timeout_covers_early_parent_exit_and_background_child(self) -> None:
        marker = self.root / "background-survived.txt"
        child = (
            "import pathlib,time;"
            "time.sleep(0.8);"
            "pathlib.Path('background-survived.txt').write_text('not killed')"
        )
        parent = (
            "import subprocess,sys;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}],"
            "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
        )
        runner = self.runner(spec=self.spec(timeout_s=0.2))
        started = time.monotonic()
        with self.assertRaises(SandboxTimeout) as captured:
            runner.run(self.intent([sys.executable, "-c", parent]))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(captured.exception.receipt["execution"]["outcome"], "timeout")
        time.sleep(1.0)
        self.assertFalse(marker.exists())

    def test_windows_descendants_exclude_stale_parent_pid_records(self) -> None:
        table = {
            200: 100,
            201: 200,
            300: 100,
            301: 300,
        }
        creation_times = {
            200: 900,
            201: 1100,
            300: 1001,
            301: 1002,
        }
        self.assertEqual(
            SandboxRunner._descendants_from_table(
                100,
                1000,
                table,
                creation_times,
            ),
            {300, 301},
        )

    def test_windows_timeout_kill_never_uses_unfiltered_taskkill_tree(self) -> None:
        class FinishedProcess:
            pid = 100

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                raise AssertionError("finished root process must not be killed")

        process = FinishedProcess()
        with (
            patch("hive_mind_os.sandbox.os.name", "nt"),
            patch.object(
                SandboxRunner,
                "_windows_descendant_identities",
                return_value={},
            ),
            patch("hive_mind_os.sandbox.subprocess.run") as run,
        ):
            SandboxRunner._kill_tree(process)  # type: ignore[arg-type]
        run.assert_not_called()

    def test_windows_timeout_termination_rechecks_opened_process_identity(self) -> None:
        kernel32 = Mock()
        kernel32.OpenProcess.side_effect = [2000, 3000]
        with patch.object(
            SandboxRunner,
            "_windows_process_creation_time_from_handle",
            side_effect=[1100, 901],
        ):
            SandboxRunner._terminate_windows_descendant_identities(
                {200: 1100, 201: 900},
                1000,
                kernel32=kernel32,
            )
        self.assertEqual(kernel32.TerminateProcess.call_args_list, [((2000, 1),)])
        self.assertEqual(kernel32.CloseHandle.call_args_list, [((2000,),), ((3000,),)])

    def test_windows_timeout_termination_keeps_unknown_metadata_conservative(self) -> None:
        kernel32 = Mock()
        kernel32.OpenProcess.return_value = 2000
        with patch.object(
            SandboxRunner,
            "_windows_process_creation_time_from_handle",
            return_value=None,
        ):
            SandboxRunner._terminate_windows_descendant_identities(
                {200: None},
                1000,
                kernel32=kernel32,
            )
        kernel32.TerminateProcess.assert_called_once_with(2000, 1)

    def test_windows_timeout_rescans_after_root_termination(self) -> None:
        class RunningProcess:
            pid = 100

            def __init__(self) -> None:
                self.killed = False

            def poll(self) -> int | None:
                return None if not self.killed else 0

            def kill(self) -> None:
                self.killed = True

        process = RunningProcess()
        with (
            patch("hive_mind_os.sandbox.os.name", "nt"),
            patch.object(
                SandboxRunner,
                "_windows_descendant_identities",
                side_effect=[{200: 1100}, {201: 1101}],
            ),
            patch.object(SandboxRunner, "_terminate_windows_descendant_identities") as terminate,
        ):
            SandboxRunner._kill_tree(process)  # type: ignore[arg-type]
        self.assertTrue(process.killed)
        self.assertEqual(terminate.call_count, 2)

    @unittest.skipUnless(os.name == "nt", "Windows-specific PID-reuse regression")
    def test_short_lived_windows_commands_do_not_false_timeout(self) -> None:
        runner = self.runner(spec=self.spec(timeout_s=1.0))
        for index in range(10):
            with self.subTest(index=index):
                receipt = runner.run(
                    self.intent(
                        [sys.executable, "-c", "pass"],
                        action_id=f"ACT-short-lived-{index}",
                    )
                )
                self.assertEqual(receipt["execution"]["outcome"], "succeeded")

    @unittest.skipUnless(os.name == "nt", "Windows-specific Job Object regression")
    def test_windows_job_assignment_failure_denies_before_suspended_root_runs(self) -> None:
        class FailingJob:
            def __init__(self) -> None:
                self.closed = False

            def assign(self, process: subprocess.Popen[bytes]) -> bool:
                return False

            def resume(self, process: subprocess.Popen[bytes]) -> bool:
                raise AssertionError("a process must not resume before Job Object assignment")

            def close(self) -> None:
                self.closed = True

        marker = self.root / "assignment-escape.txt"
        job = FailingJob()
        runner = self.runner()
        with patch("hive_mind_os.sandbox._WindowsJob.create", return_value=job):
            with self.assertRaisesRegex(SandboxDenied, "process creation failed: SubprocessError"):
                runner.run(
                    self.intent(
                        [
                            sys.executable,
                            "-c",
                            "import pathlib; pathlib.Path('assignment-escape.txt').write_text('escaped')",
                        ]
                    )
                )
        self.assertTrue(job.closed)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "nt", "Windows-specific Job Object regression")
    def test_windows_job_unavailable_denies_before_root_spawns(self) -> None:
        marker = self.root / "unavailable-escape.txt"
        runner = self.runner(spec=self.spec(timeout_s=0.2))
        with patch("hive_mind_os.sandbox._WindowsJob.create", return_value=None):
            with self.assertRaisesRegex(SandboxDenied, "process creation failed: SubprocessError"):
                runner.run(
                    self.intent(
                        [
                            sys.executable,
                            "-c",
                            "import pathlib; pathlib.Path('unavailable-escape.txt').write_text('escaped')",
                        ]
                    )
                )
        self.assertEqual(runner.spawn_count, 0)
        self.assertFalse(marker.exists())

    def test_output_cap_is_explicit_and_digest_bound(self) -> None:
        runner = self.runner(spec=self.spec(max_output_bytes=100))
        receipt = runner.run(
            self.intent(
                [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*4096)"]
            )
        )
        stdout = self.stdout(receipt)
        stream = receipt["execution"]["stdout"]
        self.assertEqual(stdout, b"x" * 100)
        self.assertEqual(stream["bytes"], 100)
        self.assertTrue(stream["truncated"])
        self.assertEqual(stream["digest"], sha256_digest(stdout))

    def test_policy_denial_occurs_before_spawn(self) -> None:
        runner = self.runner(policy=PolicyEngine(AutonomyLevel.ADVISE))
        with self.assertRaisesRegex(SandboxDenied, "requires autonomy level"):
            runner.run(self.intent([sys.executable, "-c", "print('denied')"]))
        self.assertEqual(runner.spawn_count, 0)

    def test_exhausted_allowance_occurs_before_spawn(self) -> None:
        runner = self.runner(allowance=EpisodeAllowance(0, 0.0))
        with self.assertRaisesRegex(SandboxDenied, "allowance exhausted"):
            runner.run(self.intent([sys.executable, "-c", "print('denied')"]))
        self.assertEqual(runner.spawn_count, 0)

    def test_concurrent_calls_cannot_overbook_one_call_allowance(self) -> None:
        barrier = threading.Barrier(2)

        class SynchronizedRunner(SandboxRunner):
            def _validate_intent(self, intent: dict[str, Any]) -> None:
                super()._validate_intent(intent)
                barrier.wait(timeout=2)

        runner = SynchronizedRunner(
            self.spec(),
            self.trusted,
            EpisodeAllowance(1, 1.0),
        )
        intents = [
            self.intent(
                [sys.executable, "-c", "print('one')"],
                action_id=f"ACT-concurrent-{index}",
            )
            for index in range(2)
        ]

        def invoke(intent: dict[str, Any]) -> str:
            try:
                runner.run(intent)
            except SandboxDenied:
                return "denied"
            return "succeeded"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(invoke, intents))
        self.assertEqual(sorted(outcomes), ["denied", "succeeded"])
        self.assertEqual(runner.tool_calls_used, 1)
        self.assertEqual(runner.spawn_count, 1)

    def test_all_pre_spawn_denials_append_ledger_evidence(self) -> None:
        cases: list[tuple[str, dict[str, Any], type[SandboxDenied]]] = []
        invalid_digest = self.intent([sys.executable, "-c", "print('no')"])
        invalid_digest["description"] = "mutated"
        cases.append(("digest", invalid_digest, SandboxDenied))
        escape = self.intent(
            [sys.executable, "-c", "print('no')", "../outside.txt"],
            path_args=[3],
        )
        cases.append(("escape", escape, ConfinementViolation))
        embedded_nul = self.intent([sys.executable, "-c", "print('no')\x00"])
        cases.append(("nul", embedded_nul, SandboxDenied))

        for label, intent, error_type in cases:
            with self.subTest(case=label):
                ledger = EvidenceLedger()
                runner = self.runner(
                    trusted=self.base / f"{label}-evidence",
                    ledger=ledger,
                )
                with self.assertRaises(error_type):
                    runner.run(intent)
                denials = [
                    event
                    for event in ledger.events()
                    if event["event_type"] == "sandbox.denied"
                ]
                self.assertEqual(len(denials), 1)
                self.assertEqual(runner.spawn_count, 0)

    def test_subprocess_creation_error_is_a_receipted_denial(self) -> None:
        class FailingRunner(SandboxRunner):
            def _spawn(self, argv: list[str]) -> subprocess.Popen[bytes]:
                raise subprocess.SubprocessError("simulated child setup failure")

        ledger = EvidenceLedger()
        runner = FailingRunner(
            self.spec(),
            self.trusted,
            EpisodeAllowance(1, 1.0),
            ledger=ledger,
        )
        with self.assertRaisesRegex(SandboxDenied, "SubprocessError"):
            runner.run(self.intent([sys.executable, "-c", "print('no')"]))
        self.assertEqual(runner.spawn_count, 0)
        self.assertEqual(
            [event["event_type"] for event in ledger.events()],
            ["sandbox.denied"],
        )

    def test_non_object_intent_is_a_receipted_schema_denial(self) -> None:
        ledger = EvidenceLedger()
        runner = self.runner(ledger=ledger)
        with self.assertRaises(SandboxDenied):
            runner.run([])  # type: ignore[arg-type]
        self.assertEqual(runner.spawn_count, 0)
        events = ledger.events()
        self.assertEqual([event["event_type"] for event in events], ["sandbox.denied"])
        self.assertEqual(events[0]["payload"]["action_id"], None)

    def test_interrupted_publish_leaves_no_receipt_claim(self) -> None:
        class InterruptedRunner(SandboxRunner):
            def _atomic_write(self, relative: str, content: bytes) -> None:
                if relative.startswith("r/"):
                    raise OSError("simulated receipt publish interruption")
                super()._atomic_write(relative, content)

        runner = InterruptedRunner(
            self.spec(),
            self.trusted,
            EpisodeAllowance(20, 100.0),
        )
        with self.assertRaisesRegex(OSError, "simulated"):
            runner.run(self.intent([sys.executable, "-c", "print('orphan')"]))
        self.assertIsNone(runner.last_reference)
        receipts = self.trusted / "receipts"
        self.assertFalse(receipts.exists() and any(receipts.iterdir()))
        absent = ReceiptReference(
            f"r/{'0' * 64}.json",
            f"sha256:{'0' * 64}",
        )
        validation = FileReceiptValidator(self.trusted).validate(
            absent,
            mission_id="mission-sandbox",
            state_ref="MISSION_STATE:mission-sandbox:1",
            actor_id="builder-pass-1",
            action_id="ACT-sandbox-1",
            action_kind="command",
            action_digest=f"sha256:{'0' * 64}",
        )
        self.assertFalse(validation.valid)

    def test_repeat_execution_differs_only_in_volatile_receipt_fields(self) -> None:
        runner = self.runner()
        intent = self.intent([sys.executable, "-c", "print('stable')"])
        first = runner.run(intent)
        second = runner.run(intent)
        self.assertEqual(tool_intent_digest(intent), intent["action_digest"])

        def normalize(receipt: dict[str, Any]) -> dict[str, Any]:
            normalized = deepcopy(receipt)
            normalized["receipt_id"] = "<receipt-id>"
            normalized["execution_id"] = "<execution-id>"
            normalized["observed_at"] = "<timestamp>"
            normalized["execution"]["duration_ms"] = 0
            for artifact in normalized["artifacts"]:
                artifact["created_at"] = "<timestamp>"
            return normalized

        self.assertEqual(normalize(first), normalize(second))

    def test_golden_intent_and_receipt_conform_to_extended_contracts(self) -> None:
        fixture_root = Path(__file__).parent / "fixtures" / "sandbox"
        intent = json.loads((fixture_root / "intent.json").read_text(encoding="utf-8"))
        receipt = json.loads(
            (fixture_root / "receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(intent["action_digest"], tool_intent_digest(intent))
        self.assertTrue(validate_contract("tool-intent", intent).valid)
        self.assertTrue(validate_contract("tool-receipt", receipt).valid)

    def test_trusted_receipt_store_cannot_be_inside_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            self.runner(trusted=self.root / "untrusted-receipts")

    # -- private one-use trusted child context -------------------------------------

    @staticmethod
    def secret_forms(token: str = _SYNTHETIC_TOKEN) -> tuple[bytes, ...]:
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

    def echo_runner(self, name: str, **spec_overrides: Any) -> SandboxRunner:
        return self.runner(
            spec=self.spec(env_allowlist=(_SECRET_ENV,), **spec_overrides),
            trusted=self.base / f"{name}-evidence",
        )

    def echo_argv(self, mode: str) -> list[str]:
        return [sys.executable, "-c", _ECHO_CHILD, mode, _SYNTHETIC_REMOTE]

    def echo_context(
        self,
        runner: SandboxRunner,
        mode: str,
        token: str = _SYNTHETIC_TOKEN,
    ) -> _TrustedChildContext:
        return _TrustedChildContext(
            runner,
            self.echo_argv(mode),
            overrides=((_SECRET_ENV, token),),
            secrets=self.secret_forms(token),
            remote=_SYNTHETIC_REMOTE,
        )

    def run_echo(
        self,
        runner: SandboxRunner,
        mode: str,
        *,
        action_id: str = "ACT-echo-1",
    ) -> dict[str, Any]:
        return runner.run(
            self.intent(self.echo_argv(mode), action_id=action_id),
            _trusted=self.echo_context(runner, mode),
        )

    def assert_no_forms(self, root: Path, forms: tuple[bytes, ...] | None = None) -> None:
        """Scan every persisted byte (receipts and artifacts) for a supported form."""

        forms = forms or self.secret_forms()
        scanned = 0
        for path in sorted(root.rglob("*")):
            if path.is_file():
                scanned += 1
                content = path.read_bytes()
                for form in forms:
                    self.assertNotIn(form, content, path.name)
        self.assertGreater(scanned, 0)

    @staticmethod
    def stream(receipt: dict[str, Any], root: Path, index: int) -> bytes:
        return (root / receipt["artifacts"][index]["path"]).read_bytes()

    def test_trusted_environment_is_child_only_and_ordered_drop_fixed_override(self) -> None:
        dropped = "HIVE_MIND_TRUSTED_DROPPED"
        kept = "HIVE_MIND_TRUSTED_KEPT"
        fixed_dropped = "HIVE_MIND_TRUSTED_FIXED_DROPPED"
        overridden = "HIVE_MIND_TRUSTED_OVERRIDDEN"
        child_only = "HIVE_MIND_TRUSTED_CHILD_ONLY"
        names = [dropped, kept, fixed_dropped, overridden, child_only]
        code = (
            "import json,os;"
            f"print(json.dumps({{n: os.environ.get(n) for n in {names!r}}}, sort_keys=True))"
        )
        runner = self.runner(
            spec=self.spec(
                env_allowlist=tuple(names),
                fixed_environment=((fixed_dropped, "fixed-nonsecret"), (overridden, "fixed-old")),
            )
        )
        argv = [sys.executable, "-c", code]
        context = _TrustedChildContext(
            runner,
            argv,
            overrides=((overridden, "override-value"), (child_only, "child-only-value")),
            drop=(dropped, fixed_dropped),
        )
        ambient = {
            dropped: "ambient-dropped",
            kept: "ambient-kept",
            fixed_dropped: "ambient-secret-not-fixed",
            overridden: "ambient-overridden",
        }
        with patch.dict(os.environ, ambient):
            before = dict(os.environ)
            receipt = runner.run(self.intent(argv), _trusted=context)
            after = dict(os.environ)
        self.assertEqual(before, after)
        self.assertNotIn(child_only, os.environ)
        self.assertEqual(
            json.loads(self.stdout(receipt)),
            {
                dropped: None,
                kept: "ambient-kept",
                fixed_dropped: "fixed-nonsecret",
                overridden: "override-value",
                child_only: "child-only-value",
            },
        )

    def test_trusted_secret_is_absent_from_parent_and_unrelated_children_during_popen(self) -> None:
        code = f"import os;print(os.environ.get({_SECRET_ENV!r}, 'absent'))"
        argv = [sys.executable, "-c", code]
        trusted_runner = self.echo_runner("blocked-trusted")
        unrelated_runner = self.echo_runner("blocked-unrelated")
        # The remote must be part of the bound argv for a credentialed context.
        argv_with_remote = [*argv, _SYNTHETIC_REMOTE]
        context = _TrustedChildContext(
            trusted_runner,
            argv_with_remote,
            overrides=((_SECRET_ENV, _SYNTHETIC_TOKEN),),
            secrets=self.secret_forms(),
            remote=_SYNTHETIC_REMOTE,
        )
        real_popen = subprocess.Popen
        entered = threading.Event()
        release = threading.Event()
        environments: list[dict[str, str]] = []

        def blocked_popen(command: list[str], **kwargs: Any) -> Any:
            environment = dict(kwargs["env"])
            environments.append(environment)
            if _SECRET_ENV in environment:
                entered.set()
                if not release.wait(timeout=30):
                    raise RuntimeError("probe was never released")
            return real_popen(command, **kwargs)

        before = dict(os.environ)
        with patch.object(subprocess, "Popen", side_effect=blocked_popen):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    trusted_runner.run,
                    self.intent(argv_with_remote, action_id="ACT-blocked-trusted"),
                    _trusted=context,
                )
                try:
                    self.assertTrue(entered.wait(timeout=30))
                    # Observe the leak window while the credentialed Popen is blocked.
                    during = dict(os.environ)
                    unrelated = unrelated_runner.run(
                        self.intent(argv, action_id="ACT-blocked-unrelated")
                    )
                finally:
                    release.set()
                trusted = future.result(timeout=60)
        after = dict(os.environ)
        self.assertEqual(before, during)
        self.assertEqual(before, after)
        self.assertNotIn(_SECRET_ENV, during)
        for value in during.values():
            self.assertNotIn(_SYNTHETIC_TOKEN, value)
        self.assertEqual(
            self.stdout(unrelated, self.base / "blocked-unrelated-evidence").splitlines(),
            [b"absent"],
        )
        # The header-bearing mapping reached exactly one child: the credentialed one.
        self.assertEqual(sum(_SECRET_ENV in env for env in environments), 1)
        self.assertEqual(
            self.stdout(trusted, self.base / "blocked-trusted-evidence").splitlines(),
            [b"[REDACTED]"],
        )

    def test_concurrent_trusted_children_each_receive_only_their_own_environment(self) -> None:
        names = ["HIVE_MIND_TRUSTED_ONE", "HIVE_MIND_TRUSTED_TWO"]
        code = (
            "import json,os,time;time.sleep(0.6);"
            f"print(json.dumps({{n: os.environ.get(n) for n in {names!r}}}, sort_keys=True))"
        )
        argv = [sys.executable, "-c", code]
        runners = [
            self.runner(
                spec=self.spec(env_allowlist=tuple(names)),
                trusted=self.base / f"concurrent-{index}-evidence",
            )
            for index in range(3)
        ]
        contexts = [
            _TrustedChildContext(runners[0], argv, overrides=((names[0], "value-one"),)),
            _TrustedChildContext(runners[1], argv, overrides=((names[1], "value-two"),)),
            None,
        ]

        def invoke(index: int) -> dict[str, Any]:
            intent = self.intent(argv, action_id=f"ACT-concurrent-env-{index}")
            context = contexts[index]
            if context is None:
                return runners[index].run(intent)
            return runners[index].run(intent, _trusted=context)

        before = dict(os.environ)
        with ThreadPoolExecutor(max_workers=3) as pool:
            receipts = list(pool.map(invoke, range(3)))
        self.assertEqual(before, dict(os.environ))
        observed = [
            json.loads(self.stdout(receipt, self.base / f"concurrent-{index}-evidence"))
            for index, receipt in enumerate(receipts)
        ]
        self.assertEqual(observed[0], {names[0]: "value-one", names[1]: None})
        self.assertEqual(observed[1], {names[0]: None, names[1]: "value-two"})
        self.assertEqual(observed[2], {names[0]: None, names[1]: None})

    def test_trusted_context_denials_are_pre_spawn_and_leak_nothing(self) -> None:
        forms = self.secret_forms()
        overrides = ((_SECRET_ENV, _SYNTHETIC_TOKEN),)
        code = "print('bound')"
        bound = [sys.executable, "-c", code, _SYNTHETIC_REMOTE]

        def context_for(
            runner: SandboxRunner,
            argv: list[str],
            *,
            remote: str | None = _SYNTHETIC_REMOTE,
            secrets: tuple[bytes, ...] = forms,
        ) -> _TrustedChildContext:
            return _TrustedChildContext(
                runner, argv, overrides=overrides, secrets=secrets, remote=remote
            )

        # (label, denial reason, spec overrides); the branches below build the mismatch.
        other_argv = [sys.executable, "-c", "print('other')", _SYNTHETIC_REMOTE]
        wrong_remote_argv = [sys.executable, "-c", code, _OTHER_REMOTE]
        two_urls_argv = [sys.executable, "-c", code, _SYNTHETIC_REMOTE, _OTHER_REMOTE]
        cases: list[tuple[str, str, dict[str, Any]]] = [
            ("runner", "another runner", {}),
            ("identity", "another runner", {}),
            ("executable", "another executable", {}),
            ("arguments", "other arguments", {}),
            ("remote", "another remote", {}),
            ("second-url", "another remote", {}),
            ("allowlist", "not allowlisted", {"env_allowlist": ()}),
            ("invalid", "invalid", {}),
            ("reuse", "already used", {}),
        ]
        for label, reason, spec_overrides in cases:
            with self.subTest(case=label):
                ledger = EvidenceLedger()
                trusted_root = self.base / f"denial-{label}-evidence"
                spec_values = {"env_allowlist": (_SECRET_ENV,), **spec_overrides}
                runner = self.runner(
                    spec=self.spec(**spec_values),
                    trusted=trusted_root,
                    ledger=ledger,
                )
                other = self.runner(
                    spec=self.spec(**spec_values),
                    trusted=self.base / f"denial-{label}-other-evidence",
                )
                intent_argv = bound
                subject: Any = context_for(runner, bound)
                target = runner
                if label == "runner":
                    subject = context_for(other, bound)
                elif label == "identity":
                    runner.runner_identity = "renamed-sandbox-runner"
                elif label == "executable":
                    subject = context_for(
                        runner, ["definitely-not-a-hive-executable", *bound[1:]]
                    )
                elif label == "arguments":
                    subject = context_for(runner, other_argv)
                elif label == "remote":
                    intent_argv = wrong_remote_argv
                    subject = context_for(runner, wrong_remote_argv)
                elif label == "second-url":
                    intent_argv = two_urls_argv
                    subject = context_for(runner, two_urls_argv)
                elif label == "invalid":
                    subject = object()
                elif label == "reuse":
                    first = runner.run(
                        self.intent(bound, action_id="ACT-denial-first"),
                        _trusted=subject,
                    )
                    self.assertEqual(first["result"], "succeeded")
                spawned = target.spawn_count
                with self.assertRaisesRegex(SandboxDenied, reason) as captured:
                    target.run(
                        self.intent(intent_argv, action_id="ACT-denial-second"),
                        _trusted=subject,
                    )
                self.assertEqual(target.spawn_count, spawned)
                for form in forms:
                    self.assertNotIn(form.decode(), str(captured.exception))
                    self.assertNotIn(form.decode(), json.dumps(ledger.events(), default=str))
                denials = [
                    event
                    for event in ledger.events()
                    if event["event_type"] == "sandbox.denied"
                ]
                self.assertEqual(len(denials), 1)
                self.assertEqual(denials[0]["payload"]["reason"], str(captured.exception))
                if label != "reuse":
                    self.assertFalse((trusted_root / "r").exists())

    def test_trusted_context_is_private_redacted_and_not_copyable_or_serializable(self) -> None:
        runner = self.echo_runner("private-context")
        context = self.echo_context(runner, "echo")
        for rendered in (repr(context), str(context), f"{context}", format(context, "")):
            self.assertEqual(rendered, "<_TrustedChildContext redacted>")
            self.assertNotIn(_SYNTHETIC_TOKEN, rendered)
        self.assertFalse(hasattr(context, "__dict__"))
        with self.assertRaises(TypeError):
            copy.copy(context)
        with self.assertRaises(TypeError):
            copy.deepcopy(context)
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol), self.assertRaises(TypeError):
                pickle.dumps(context, protocol=protocol)
        with self.assertRaises(TypeError):
            json.dumps(context)

    def test_trusted_context_constructor_errors_do_not_stringify_values(self) -> None:
        runner = self.echo_runner("constructor-errors")
        argv = self.echo_argv("echo")
        bad_cases: list[dict[str, Any]] = [
            {"overrides": (("BAD=NAME", _SYNTHETIC_TOKEN),)},
            {"overrides": ((_SECRET_ENV, _SYNTHETIC_TOKEN + "\x00"),)},
            {"overrides": ((_SECRET_ENV, _SYNTHETIC_TOKEN), (_SECRET_ENV, "again"))},
            {"drop": (None,)},
            {"secrets": self.secret_forms(), "remote": None},
            {"remote": "https://user:" + _SYNTHETIC_TOKEN + "@github.com/o/r.git"},
        ]
        for keywords in bad_cases:
            with self.subTest(keywords=sorted(keywords)):
                with self.assertRaises(ValueError) as captured:
                    _TrustedChildContext(runner, argv, **keywords)
                self.assertNotIn(_SYNTHETIC_TOKEN, str(captured.exception))
                self.assertNotIn(_SYNTHETIC_TOKEN, repr(captured.exception))

    def test_credentialed_streams_are_redacted_before_persistence(self) -> None:
        for mode in ("echo", "fail"):
            with self.subTest(mode=mode):
                runner = self.echo_runner(f"redact-{mode}")
                receipt = self.run_echo(runner, mode)
                root = self.base / f"redact-{mode}-evidence"
                expected = b"[REDACTED]" + bytes([10])
                self.assertEqual(self.stream(receipt, root, 0), expected * 5)
                self.assertEqual(self.stream(receipt, root, 1), expected * 5)
                self.assertEqual(receipt["result"], "failed" if mode == "fail" else "succeeded")
                for label, index in (("stdout", 0), ("stderr", 1)):
                    stored = self.stream(receipt, root, index)
                    stream = receipt["execution"][label]
                    self.assertEqual(stream["bytes"], len(stored))
                    self.assertEqual(stream["digest"], sha256_digest(stored))
                    self.assertFalse(stream["truncated"])
                self.assert_no_forms(root)
                self.assertEqual(
                    (runner.tool_calls_used, runner.compute_units_used, runner.spawn_count),
                    (1, 1.0, 1),
                )

    def test_secret_split_across_pipe_reads_is_redacted(self) -> None:
        runner = self.echo_runner("boundary", max_output_bytes=200_000)
        receipt = self.run_echo(runner, "boundary")
        root = self.base / "boundary-evidence"
        stored = self.stream(receipt, root, 0)
        self.assertEqual(stored, b"a" * (65536 - 10) + b"[REDACTED]" + b"b" * 100)
        self.assertFalse(receipt["execution"]["stdout"]["truncated"])
        self.assertEqual(receipt["execution"]["stdout"]["bytes"], len(stored))
        self.assert_no_forms(root)

    def test_truncated_credentialed_streams_store_a_fixed_marker_with_raw_truth(self) -> None:
        marker = _INCOMPLETE_CREDENTIALED_STREAM
        for mode, index, other in (("cap-stdout", 0, 1), ("cap-stderr", 1, 0)):
            with self.subTest(mode=mode):
                runner = self.echo_runner(f"cap-{mode}", max_output_bytes=128)
                receipt = self.run_echo(runner, mode)
                root = self.base / f"cap-{mode}-evidence"
                label = ("stdout", "stderr")[index]
                self.assertEqual(self.stream(receipt, root, index), marker)
                stream = receipt["execution"][label]
                self.assertTrue(stream["truncated"])
                self.assertEqual(stream["bytes"], len(marker))
                self.assertEqual(stream["digest"], sha256_digest(marker))
                self.assertFalse(receipt["execution"][("stdout", "stderr")[other]]["truncated"])
                self.assert_no_forms(root)
                self.assertEqual(
                    (runner.tool_calls_used, runner.compute_units_used, runner.spawn_count),
                    (1, 1.0, 1),
                )

    def test_timed_out_credentialed_streams_store_a_fixed_marker(self) -> None:
        runner = self.echo_runner("timeout", timeout_s=4.0)
        with self.assertRaises(SandboxTimeout) as captured:
            self.run_echo(runner, "sleep")
        root = self.base / "timeout-evidence"
        receipt = captured.exception.receipt
        self.assertEqual(receipt["execution"]["outcome"], "timeout")
        self.assertEqual(self.stream(receipt, root, 0), _INCOMPLETE_CREDENTIALED_STREAM)
        self.assertEqual(self.stream(receipt, root, 1), _INCOMPLETE_CREDENTIALED_STREAM)
        self.assertEqual(
            receipt["execution"]["stdout"]["digest"],
            sha256_digest(_INCOMPLETE_CREDENTIALED_STREAM),
        )
        self.assert_no_forms(root)
        for form in self.secret_forms():
            self.assertNotIn(form.decode(), str(captured.exception))

    def test_context_without_secrets_leaves_output_and_truncation_untouched(self) -> None:
        runner = self.runner(spec=self.spec(max_output_bytes=100))
        argv = [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*4096)"]
        receipt = runner.run(
            self.intent(argv),
            _trusted=_TrustedChildContext(runner, argv),
        )
        self.assertEqual(self.stdout(receipt), b"x" * 100)
        self.assertTrue(receipt["execution"]["stdout"]["truncated"])
        self.assertEqual(receipt["execution"]["stdout"]["bytes"], 100)

    def test_trusted_context_does_not_change_intent_spec_or_receipt_digests(self) -> None:
        runner = self.runner()
        argv = [sys.executable, "-c", "print('stable')"]
        intent = self.intent(argv)
        spec_digest = runner.spec.spec_digest()
        plain = runner.run(intent)
        trusted = runner.run(intent, _trusted=_TrustedChildContext(runner, argv))
        self.assertEqual(runner.spec.spec_digest(), spec_digest)
        self.assertEqual(trusted["action_digest"], intent["action_digest"])
        self.assertEqual(
            trusted["execution"]["sandbox_spec_digest"],
            plain["execution"]["sandbox_spec_digest"],
        )

        def normalize(receipt: dict[str, Any]) -> dict[str, Any]:
            normalized = deepcopy(receipt)
            normalized["receipt_id"] = "<receipt-id>"
            normalized["execution_id"] = "<execution-id>"
            normalized["observed_at"] = "<timestamp>"
            normalized["execution"]["duration_ms"] = 0
            for artifact in normalized["artifacts"]:
                artifact["created_at"] = "<timestamp>"
            return normalized

        self.assertEqual(normalize(plain), normalize(trusted))

    def test_credentialed_receipt_digests_bind_only_sanitized_stored_bytes(self) -> None:
        runner = self.echo_runner("credentialed-receipt")
        receipt = self.run_echo(runner, "echo")
        assert runner.last_reference is not None
        intent = self.intent(self.echo_argv("echo"), action_id="ACT-echo-1")
        validation = FileReceiptValidator(self.base / "credentialed-receipt-evidence").validate(
            runner.last_reference,
            mission_id=intent["mission_id"],
            state_ref=intent["state_ref"],
            actor_id=intent["actor_id"],
            action_id=intent["action_id"],
            action_kind=intent["kind"],
            action_digest=receipt["action_digest"],
        )
        self.assertTrue(validation.valid, validation.issues)
        self.assertEqual(receipt["execution"]["argv"][-1], _SYNTHETIC_REMOTE)
        self.assertEqual(receipt["execution"]["requested_argv"][-1], _SYNTHETIC_REMOTE)

    def test_returned_receipt_derives_the_exact_published_reference(self) -> None:
        runner = self.runner()
        first = runner.run(self.intent([sys.executable, "-c", "print('one')"], action_id="ACT-ref-1"))
        first_reference = runner.last_reference
        second = runner.run(self.intent([sys.executable, "-c", "print('two')"], action_id="ACT-ref-2"))
        # The shared legacy reference now names the second invocation, but each returned
        # receipt still derives its own content address and retained bytes.
        self.assertNotEqual(first_reference, runner.last_reference)
        raw, reference = _canonical_receipt(first)
        self.assertEqual(reference, first_reference)
        self.assertEqual((self.trusted / reference.path).read_bytes(), raw)
        self.assertEqual(reference.digest, sha256_digest(raw))
        raw, reference = _canonical_receipt(second)
        self.assertEqual(reference, runner.last_reference)
        self.assertEqual((self.trusted / reference.path).read_bytes(), raw)

    # -- concurrent immutable content-addressed publication ------------------------------
    # These use the real filesystem and the real publication primitive (``os.link``).
    # The barrier wraps the primitive and passes through, so a change of primitive makes
    # ``ready`` never fire and the test fails instead of passing vacuously.

    def publication_target(self, name: str, content: bytes) -> tuple[SandboxRunner, str, Path]:
        trusted = self.base / f"{name}-evidence"
        runner = self.runner(trusted=trusted)
        relative = f"artifacts/{sha256_digest(content).removeprefix('sha256:')}.stderr"
        return runner, relative, trusted / relative

    @staticmethod
    def park_first_link(name: str) -> tuple[Any, threading.Event, threading.Event]:
        """Park the named thread inside the real ``os.link``, after its temp file is complete."""

        real_link = os.link
        ready = threading.Event()
        release = threading.Event()

        def link(source: Any, target: Any, *args: Any, **kwargs: Any) -> Any:
            if threading.current_thread().name == name and not ready.is_set():
                ready.set()
                if not release.wait(timeout=30):
                    raise RuntimeError("publication barrier was never released")
            return real_link(source, target, *args, **kwargs)

        return patch.object(os, "link", side_effect=link), ready, release

    def race_publishers(
        self,
        runner: SandboxRunner,
        relative: str,
        destination: Path,
        first_content: bytes,
        second_content: bytes,
        *,
        held_reader: bool,
    ) -> tuple[dict[str, str], os.stat_result]:
        """A checks the destination absent and parks; B publishes; a reader holds the
        winner open; then A resumes. Returns A's outcome and the winner's identity."""

        patcher, ready, release = self.park_first_link("publisher-A")
        outcome: dict[str, str] = {}

        def first() -> None:
            try:
                runner._atomic_write(relative, first_content)
                outcome["A"] = "success"
            except BaseException as error:  # recorded and asserted by the caller
                outcome["A"] = f"{type(error).__name__}: {error}"

        with patcher:
            thread = threading.Thread(target=first, name="publisher-A")
            thread.start()
            try:
                self.assertTrue(ready.wait(timeout=30))
                runner._atomic_write(relative, second_content)
                winner = os.stat(destination)
                if held_reader:
                    with destination.open("rb") as reader:
                        self.assertEqual(reader.read(), second_content)
                        release.set()
                        thread.join(timeout=30)
                else:
                    release.set()
                    thread.join(timeout=30)
            finally:
                release.set()
                thread.join(timeout=30)
        self.assertFalse(thread.is_alive())
        return outcome, winner

    def test_concurrent_same_bytes_publication_adopts_the_winner_with_a_held_reader(self) -> None:
        for content in (b"", b"exact matching complete artifact bytes\n"):
            for held_reader in (False, True):
                with self.subTest(content=len(content), held_reader=held_reader):
                    runner, relative, destination = self.publication_target(
                        f"same-{len(content)}-{held_reader}", content
                    )
                    outcome, winner = self.race_publishers(
                        runner, relative, destination, content, content, held_reader=held_reader
                    )
                    self.assertEqual(outcome, {"A": "success"})
                    after = os.stat(destination)
                    # The winner's file was adopted, not replaced.
                    self.assertEqual((after.st_dev, after.st_ino), (winner.st_dev, winner.st_ino))
                    self.assertEqual(destination.read_bytes(), content)
                    # Both owned temporary files are gone; nothing else was created.
                    self.assertEqual(
                        [entry.name for entry in destination.parent.iterdir()],
                        [destination.name],
                    )

    def test_concurrent_conflicting_bytes_fail_closed_without_overwrite(self) -> None:
        for held_reader in (False, True):
            with self.subTest(held_reader=held_reader):
                runner, relative, destination = self.publication_target(
                    f"conflict-{held_reader}", b"winner"
                )
                outcome, winner = self.race_publishers(
                    runner, relative, destination, b"loser", b"winner", held_reader=held_reader
                )
                self.assertEqual(
                    outcome, {"A": "SandboxError: content-addressed artifact collision"}
                )
                after = os.stat(destination)
                self.assertEqual((after.st_dev, after.st_ino), (winner.st_dev, winner.st_ino))
                self.assertEqual(destination.read_bytes(), b"winner")
                self.assertEqual(
                    [entry.name for entry in destination.parent.iterdir()],
                    [destination.name],
                )

    def test_existing_different_or_partial_bytes_are_never_accepted_or_overwritten(self) -> None:
        full = b"complete artifact bytes"
        for label, existing in (("different", b"other artifact bytes"), ("partial", full[:8])):
            with self.subTest(existing=label):
                runner, relative, destination = self.publication_target(f"existing-{label}", full)
                destination.parent.mkdir(parents=True)
                destination.write_bytes(existing)
                before = os.stat(destination)
                with self.assertRaisesRegex(SandboxError, "collision"):
                    runner._atomic_write(relative, full)
                after = os.stat(destination)
                self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
                self.assertEqual(destination.read_bytes(), existing)
                self.assertEqual(
                    [entry.name for entry in destination.parent.iterdir()],
                    [destination.name],
                )

    def test_publication_cleans_only_its_owned_temporary_file(self) -> None:
        content = b"owned temporary cleanup"
        runner, relative, destination = self.publication_target("cleanup", content)
        sibling = destination.parent / "unrelated-evidence.txt"
        destination.parent.mkdir(parents=True)
        sibling.write_bytes(b"must survive every publication attempt")

        def entries() -> list[str]:
            return sorted(entry.name for entry in destination.parent.iterdir())

        # Failure before publication (fsync) never exposes the destination.
        with patch.object(os, "fsync", side_effect=OSError(errno.EIO, "simulated fsync failure")):
            with self.assertRaises(OSError):
                runner._atomic_write(relative, content)
        self.assertEqual(entries(), [sibling.name])
        # A data error from the link propagates as itself, and its temporary file is removed.
        with patch.object(os, "link", side_effect=OSError(errno.ENOSPC, "simulated disk full")):
            with self.assertRaises(OSError) as captured:
                runner._atomic_write(relative, content)
        self.assertNotIsInstance(captured.exception, SandboxError)
        self.assertEqual(entries(), [sibling.name])
        # A cleanup failure never masks the primary error.
        with (
            patch.object(os, "link", side_effect=OSError(errno.ENOSPC, "simulated disk full")),
            patch.object(Path, "unlink", side_effect=PermissionError("temporary is locked")),
        ):
            with self.assertRaises(OSError) as masked:
                runner._atomic_write(relative, content)
        self.assertEqual(masked.exception.errno, errno.ENOSPC)
        for leftover in [entry for entry in destination.parent.iterdir() if entry != sibling]:
            leftover.unlink()  # the test's own leftover from the simulated locked file
        # Success leaves exactly the destination and the untouched sibling.
        runner._atomic_write(relative, content)
        self.assertEqual(entries(), sorted([destination.name, sibling.name]))
        self.assertEqual(destination.read_bytes(), content)
        self.assertEqual(sibling.read_bytes(), b"must survive every publication attempt")
        # A cleanup failure after a completed publication does not fail it, and the
        # leftover name holds the same complete bytes.
        other = b"published while its temporary file cannot be removed"
        _, other_relative, other_destination = self.publication_target("cleanup", other)
        with patch.object(Path, "unlink", side_effect=PermissionError("temporary is locked")):
            runner._atomic_write(other_relative, other)
        self.assertEqual(other_destination.read_bytes(), other)
        for entry in destination.parent.iterdir():
            if entry.name not in {destination.name, sibling.name}:
                self.assertIn(entry.read_bytes(), {other, content})

    def test_unsupported_hard_links_fail_with_a_typed_error_and_no_weaker_fallback(self) -> None:
        content = b"needs an atomic create-if-absent primitive"
        for label, error in (
            ("not implemented", NotImplementedError()),
            ("not permitted", OSError(errno.EPERM, "links are not permitted here")),
            ("cross-device", OSError(errno.EXDEV, "invalid cross-device link")),
        ):
            with self.subTest(host=label):
                runner, relative, destination = self.publication_target(
                    f"unsupported-{label.replace(' ', '-')}", content
                )
                with patch.object(os, "link", side_effect=error):
                    with self.assertRaisesRegex(SandboxError, "hard-link support"):
                        runner._atomic_write(relative, content)
                self.assertFalse(destination.exists())
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_many_concurrent_writers_and_readers_publish_identical_bytes(self) -> None:
        content = b"identical artifact bytes published by many writers"
        runner, relative, destination = self.publication_target("many-writers", content)
        writers = 8
        start = threading.Barrier(writers + 1)
        finished = threading.Event()
        errors: list[BaseException] = []

        def write() -> None:
            try:
                start.wait(timeout=30)
                runner._atomic_write(relative, content)
            except BaseException as error:  # collected and asserted below
                errors.append(error)

        def read() -> None:
            try:
                start.wait(timeout=30)
                while not finished.is_set():
                    try:
                        with destination.open("rb") as handle:
                            # Visible means complete: never a partial destination.
                            assert handle.read() == content
                    except FileNotFoundError:
                        pass
            except BaseException as error:  # collected and asserted below
                errors.append(error)

        reader = threading.Thread(target=read)
        pool = [threading.Thread(target=write) for _ in range(writers)]
        reader.start()
        for thread in pool:
            thread.start()
        for thread in pool:
            thread.join(timeout=60)
        finished.set()
        reader.join(timeout=30)
        self.assertEqual(errors, [])
        self.assertEqual(destination.read_bytes(), content)
        # A temporary name may survive only when a concurrent open reader blocked its
        # removal; it must then hold the same complete bytes.
        for entry in destination.parent.iterdir():
            self.assertEqual(entry.read_bytes(), content)

    def test_concurrent_runs_with_identical_artifacts_both_persist_their_receipts(self) -> None:
        runner = self.runner()
        argv = [sys.executable, "-c", "print('identical output')"]
        patcher, ready, release = self.park_first_link("run-A")
        results: dict[str, Any] = {}

        def first() -> None:
            try:
                results["A"] = runner.run(self.intent(argv, action_id="ACT-publication-A"))
            except BaseException as error:  # asserted below
                results["A"] = error

        with patcher:
            thread = threading.Thread(target=first, name="run-A")
            thread.start()
            try:
                self.assertTrue(ready.wait(timeout=30))
                results["B"] = runner.run(self.intent(argv, action_id="ACT-publication-B"))
                shared = self.trusted / results["B"]["artifacts"][0]["path"]
                with shared.open("rb") as reader:
                    reader.read()
                    release.set()
                    thread.join(timeout=60)
            finally:
                release.set()
                thread.join(timeout=60)
        self.assertFalse(thread.is_alive())
        for label in ("A", "B"):
            receipt = results[label]
            self.assertIsInstance(receipt, dict, repr(receipt))
            raw, reference = _canonical_receipt(receipt)
            self.assertEqual((self.trusted / reference.path).read_bytes(), raw)
            self.assertTrue(validate_contract("tool-receipt", receipt).valid)
        self.assertEqual(
            results["A"]["artifacts"][0]["digest"], results["B"]["artifacts"][0]["digest"]
        )
        self.assertEqual(runner.spawn_count, 2)

    def test_old_signature_spawn_override_serves_only_context_free_calls(self) -> None:
        class LegacyRunner(SandboxRunner):
            def _spawn(self, argv: list[str]) -> subprocess.Popen[bytes]:
                return super()._spawn(argv)

        ledger = EvidenceLedger()
        runner = LegacyRunner(
            self.spec(env_allowlist=(_SECRET_ENV,)),
            self.base / "legacy-evidence",
            EpisodeAllowance(5, 5.0),
            ledger=ledger,
        )
        plain = runner.run(self.intent([sys.executable, "-c", "print('legacy')"]))
        self.assertEqual(plain["result"], "succeeded")
        self.assertEqual(runner.spawn_count, 1)
        with self.assertRaises(TypeError) as captured:
            self.run_echo(runner, "echo")
        self.assertEqual(runner.spawn_count, 1)
        for form in self.secret_forms():
            self.assertNotIn(form.decode(), str(captured.exception))
        self.assertFalse(
            any(
                path.is_file() and b"REDACTED" in path.read_bytes()
                for path in (self.base / "legacy-evidence").rglob("*")
            )
        )


if __name__ == "__main__":
    unittest.main()
