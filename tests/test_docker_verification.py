"""Offline unit tests for the OCI Python verification adapter.

Nearly every test uses a synthetic Docker client (a fake executable file plus a fake
runner that models the daemon and a fake clock) or mocked ``subprocess.Popen``.  No
real container, network or Docker daemon is touched; real positive/negative container
probes are a separate obligation.  The only real processes are a few benign local
Python children in ``BoundedRunnerTests``.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence, cast
from unittest import mock

from hive_mind_os.docker_verification import (
    CONTAINER_ENVIRONMENT,
    LABEL_KEY,
    PYTHON_BINARY,
    CommandResult,
    DockerPythonSandbox,
    ImagePythonUnittestAdapter,
    SandboxCleanupError,
    SandboxOwnershipError,
    expected_mount_source,
    run_bounded,
    validate_image_reference,
)
from hive_mind_os.runtime_contracts import canonical_json_bytes, raw_sha256
from hive_mind_os.verification_adapters import (
    LocalProcessSandbox,
    SandboxRequirements,
    SandboxUnavailable,
    SealedCommand,
    VerificationBudget,
    VerificationError,
    VerificationRegistry,
    verify_repository,
)

IMAGE = "python@sha256:" + "ab" * 32
OTHER_IMAGE = "python@sha256:" + "cd" * 32
VERSION_ARGV = (PYTHON_BINARY, "--version")
TEST_ARGV = (PYTHON_BINARY, "-B", "-m", "unittest", "tests/test_ok.py", "-v")
OK_TEST = "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n"
GENUINE_CLIENT = b"synthetic docker client"


class _Crash(BaseException):
    """Simulates the controller dying mid-attach; not an Exception on purpose."""


SOCKET_MISSING = (
    b"failed to connect to the docker API at unix:///var/run/docker.sock: "
    b"dial unix /var/run/docker.sock: connect: no such file or directory"
)
PROXY_ENTRY = "HTTP_PROXY=http://synthetic-user:synthetic-password@proxy.invalid:3128"
FAILED_CREATE_MESSAGES = {
    "refuse": b"Cannot connect to the Docker daemon",
    "gateway": b"Error response from daemon: gateway timeout",
    "garbled": b"unexpected EOF",
}


def verb_index(command: Sequence[str]) -> int:
    """Index of the docker sub-command, after the global --config/--host options."""

    index = 1
    while command[index] in {"--config", "--host"}:
        index += 2
    return index


def verb_of(command: Sequence[str]) -> str:
    return command[verb_index(command)]


class FakeDocker:
    """Models just enough of a Docker daemon; records every client invocation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str]] = []
        self.timeouts: list[tuple[str, float]] = []
        self.containers: dict[str, dict[str, Any]] = {}
        self.pending: list[dict[str, Any]] = []
        self.now = 0.0                 # fake monotonic clock shared with the sandbox
        self.cost: dict[str, float] = {}
        self.test_run_cost = 0.0       # extra fake seconds consumed by a (non-version) attach
        self.create_mode = "ok"        # ok | unknown | late | refuse | gateway | garbled
        self.error_creates_late = False  # failed creates still complete inside the daemon later
        self.attach_mode = "exit"      # exit | hang | flood | crash
        self.exit_code = 0             # applies to test runs; the version probe always exits 0
        self.rm_fails = False
        self.control_fails = False     # kill/rm raise as if the client vanished
        self.image_env = ["PATH=/usr/local/bin"]  # variables baked into the pinned image
        self.inspect_error: bytes | None = None   # container inspect fails with this stderr ({ref} is substituted)
        self.mutate: Callable[[dict[str, Any]], None] | None = None
        self.before_create: Callable[[tuple[str, ...]], None] | None = None

    def verbs(self) -> list[str]:
        return [verb_of(call) for call in self.calls]

    def calls_for(self, verb: str) -> list[tuple[str, ...]]:
        return [call for call in self.calls if verb_of(call) == verb]

    def add_foreign(self, name: str, labels: dict[str, str] | None = None) -> str:
        options: dict[str, Any] = {
            "name": name, "image": IMAGE, "labels": labels or {"synthetic.owner": "someone-else"},
            "user": "0:0", "env": [], "entrypoint": "/bin/sh", "cmd": [], "workdir": "/", "network": "bridge",
            "cap-drop": "NONE", "security-opt": "x", "memory": "0", "memory-swap": "0", "pids-limit": "0",
            "cpus": "0", "ulimit": "", "log-driver": "json-file", "tmpfs": "/x:", "mount": "",
        }
        return self._new(options, status="running")

    def materialize(self) -> None:
        """A create the client gave up on completes late inside the daemon."""

        for options in self.pending:
            self._new(options)
        self.pending.clear()

    def _new(self, options: dict[str, Any], status: str = "created") -> str:
        identifier = hashlib.sha256(options["name"].encode()).hexdigest()
        self.containers[identifier] = {"id": identifier, "options": options, "status": status,
                                       "exit": 0, "started": status == "running"}
        return identifier

    @staticmethod
    def _parse(argv: Sequence[str]) -> dict[str, Any]:
        options: dict[str, Any] = {"env": [], "labels": {}}
        index = verb_index(argv) + 1
        while argv[index].startswith("--"):
            flag = argv[index]
            if flag == "--read-only":
                options["read_only"] = True
                index += 1
                continue
            value = argv[index + 1]
            if flag == "--env":
                options["env"].append(value)
            elif flag == "--label":
                key, _, label = value.partition("=")
                options["labels"][key] = label
            else:
                options[flag[2:]] = value
            index += 2
        options["image"], options["cmd"] = argv[index], list(argv[index + 1:])
        return options

    def _find(self, reference: str) -> dict[str, Any] | None:
        return next((c for c in self.containers.values() if reference in (c["id"], c["options"]["name"])), None)

    def _require(self, reference: str) -> dict[str, Any]:
        container = self._find(reference)
        if container is None:
            raise KeyError(reference)
        return container

    def _document(self, container: dict[str, Any]) -> dict[str, Any]:
        o, state = container["options"], container["status"]
        started = "2026-09-20T00:00:00Z" if container["started"] else "0001-01-01T00:00:00Z"
        mount = {k: v for k, _, v in (item.partition("=") for item in o["mount"].split(",") if item)}
        # Docker semantics: the image's baked variables, overridden by explicit --env values.
        merged = {k: v for k, _, v in (item.partition("=") for item in self.image_env)}
        merged.update({k: v for k, _, v in (item.partition("=") for item in o["env"])})
        ulimits = [
            {"Name": name, "Soft": int(soft), "Hard": int(hard)}
            for name, _, limit in (item.partition("=") for item in o["ulimit"].split(",") if item)
            for soft, _, hard in [limit.partition(":")]
        ]
        return {
            "Id": container["id"], "Name": "/" + o["name"], "Image": "sha256:" + "0" * 64,
            "Config": {
                "Image": o["image"], "Labels": dict(o["labels"]), "User": o["user"],
                "Env": [f"{k}={v}" for k, v in merged.items()], "Entrypoint": [o["entrypoint"]], "Cmd": o["cmd"],
                "WorkingDir": o["workdir"],
            },
            "HostConfig": {
                "NetworkMode": o["network"], "ReadonlyRootfs": o.get("read_only", False),
                "CapDrop": [o["cap-drop"]], "Privileged": False, "SecurityOpt": [o["security-opt"]],
                "Memory": int(o["memory"]), "MemorySwap": int(o["memory-swap"]), "PidsLimit": int(o["pids-limit"]),
                "NanoCpus": round(float(o["cpus"]) * 1e9), "Ulimits": ulimits,
                "LogConfig": {"Type": o["log-driver"]},
                "Tmpfs": {o["tmpfs"].partition(":")[0]: o["tmpfs"].partition(":")[2]},
                "Mounts": [{"Type": mount["type"], "Source": mount["source"], "Target": mount["target"],
                            "ReadOnly": "readonly" in mount}] if mount else [],
                "IpcMode": "private", "PidMode": "",
            },
            "Mounts": [{"Type": mount["type"], "Source": expected_mount_source(mount["source"]),
                        "Destination": mount["target"], "RW": "readonly" not in mount}] if mount else [],
            "State": {"Status": state, "Running": state == "running", "ExitCode": container["exit"],
                      "OOMKilled": False, "StartedAt": started, "FinishedAt": started, "Error": ""},
        }

    def __call__(
        self, argv: Sequence[str], *, environment: Mapping[str, str], timeout: float, limit: int,
        stdout_path: Path | None = None, stderr_path: Path | None = None,
    ) -> CommandResult:
        command = tuple(argv)
        verb = verb_of(command)
        self.calls.append(command)
        self.environments.append(dict(environment))
        self.timeouts.append((verb, timeout))
        self.now += self.cost.get(verb, 0.0)
        if self.control_fails and verb in {"kill", "rm"}:
            raise OSError("synthetic docker client vanished")
        if verb == "image":
            return self._image()
        if verb == "create":
            return self._create(command)
        if verb == "start":
            return self._start(command, limit, stdout_path)
        if verb == "inspect":
            return self._inspect(command)
        if verb == "kill":
            return self._kill(command)
        return self._rm(command)

    def _image(self) -> CommandResult:
        digest = IMAGE.rpartition("@")[2]
        return CommandResult(0, stdout=json.dumps([{
            "Id": digest, "RepoDigests": [IMAGE], "Config": {"Env": list(self.image_env)},
        }]).encode())

    def _create(self, argv: tuple[str, ...]) -> CommandResult:
        if self.before_create is not None:
            self.before_create(argv)
        options = self._parse(argv)
        if self.create_mode in FAILED_CREATE_MESSAGES:
            if self.error_creates_late:
                self.pending.append(options)  # the daemon received it and finishes after the client failed
            return CommandResult(1, stderr=FAILED_CREATE_MESSAGES[self.create_mode])
        if self._find(options["name"]) is not None:
            return CommandResult(125, stderr=b"Error response from daemon: Conflict. The container name is in use")
        if self.create_mode == "late":
            self.pending.append(options)
            return CommandResult(None, timed_out=True)
        identifier = self._new(options)
        if self.create_mode == "unknown":
            return CommandResult(None, timed_out=True)
        return CommandResult(0, stdout=identifier.encode() + b"\n")

    def _start(self, argv: tuple[str, ...], limit: int, stdout_path: Path | None) -> CommandResult:
        assert stdout_path is not None
        container = self._require(argv[-1])
        container["status"], container["started"] = "running", True
        if self.attach_mode == "crash":
            raise _Crash()
        if self.attach_mode == "hang":
            return CommandResult(None, timed_out=True)
        if self.attach_mode == "flood":
            stdout_path.write_bytes(b"x" * limit)
            return CommandResult(None, stdout_bytes=limit, truncated=True)
        version = container["options"]["cmd"] == ["--version"]
        if not version:
            self.now += self.test_run_cost
        out = b"Python 3.12.0\n" if version else b"OK\n"
        code = 0 if version else self.exit_code
        with stdout_path.open("ab") as handle:
            handle.write(out)
        container["status"], container["exit"] = "exited", code
        return CommandResult(code, stdout_bytes=len(out))

    def _inspect(self, argv: tuple[str, ...]) -> CommandResult:
        if self.inspect_error is not None:
            return CommandResult(1, stderr=self.inspect_error.replace(b"{ref}", argv[-1].encode()))
        container = self._find(argv[-1])
        if container is None:
            return CommandResult(1, stderr=b"Error: No such object: " + argv[-1].encode())
        document = self._document(container)
        if self.mutate is not None:
            self.mutate(document)
        return CommandResult(0, stdout=json.dumps([document]).encode())

    def _kill(self, argv: tuple[str, ...]) -> CommandResult:
        container = self._find(argv[-1])
        if container is None:
            return CommandResult(1, stderr=b"Error: No such container")
        if container["status"] != "running":
            return CommandResult(1, stderr=b"Container is not running")
        container["status"], container["exit"] = "exited", 137
        return CommandResult(0)

    def _rm(self, argv: tuple[str, ...]) -> CommandResult:
        container = self._find(argv[-1])
        if self.rm_fails or container is None or container["status"] == "running":
            return CommandResult(1, stderr=b"Error response from daemon: removal failed")
        del self.containers[container["id"]]
        return CommandResult(0)


def sha256_of(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class DockerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.evidence = self.make_evidence("evidence")
        self.workspace = self.evidence / "workspace"
        self.exe = self.root / "docker.exe"
        self.exe.write_bytes(GENUINE_CLIENT)
        self.docker = FakeDocker()
        self.counter = itertools.count(1)
        self.sandbox = self.make_sandbox()

    def make_evidence(self, name: str) -> Path:
        evidence = self.root / name
        (evidence / "workspace" / "tests").mkdir(parents=True)
        (evidence / "workspace" / "tests" / "test_ok.py").write_text(OK_TEST, encoding="utf-8")
        return evidence

    def make_sandbox(self, **overrides: Any) -> DockerPythonSandbox:
        options: dict[str, Any] = {
            "evidence_root": self.root, "docker_executable": self.exe, "client_environment": {},
            "runner": self.docker, "sleep": lambda _: None, "clock": lambda: self.docker.now,
            "allocation_id_factory": lambda: f"{next(self.counter):032x}",
        }
        options.update(overrides)
        return DockerPythonSandbox(IMAGE, **options)

    def run_phase(
        self, argv: tuple[str, ...] = TEST_ARGV, *, sandbox: DockerPythonSandbox | None = None,
        workspace: Path | None = None, environment: dict[str, str] | None = None,
        budget: VerificationBudget | None = None, evidence: Path | None = None, prefix: str = "",
        timeout: float = 30,
    ) -> tuple[int | None, bool]:
        evidence = evidence or self.evidence
        return (sandbox or self.sandbox).run(
            argv, workspace=workspace or evidence / "workspace",
            environment=dict(CONTAINER_ENVIRONMENT) if environment is None else environment,
            timeout=timeout, stdout_path=evidence / f"{prefix}stdout.bin", stderr_path=evidence / f"{prefix}stderr.bin",
            budget=budget or VerificationBudget(),
        )

    def journal_path(self, phase: str = "tests", evidence: Path | None = None) -> Path:
        return (evidence or self.evidence) / f"sandbox-{phase}.journal.jsonl"

    def journal(self, phase: str = "tests", evidence: Path | None = None) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.journal_path(phase, evidence).read_bytes().splitlines()]

    def last_receipt(self, sandbox: DockerPythonSandbox | None = None) -> dict[str, Any]:
        receipt = (sandbox or self.sandbox).last_execution_receipt()
        assert receipt is not None
        return receipt

    def record(self, phase: str, evidence: Path | None = None) -> dict[str, Any]:
        return next(r for r in self.journal(evidence=evidence) if r["phase"] == phase)

    def create_argv(self) -> tuple[str, ...]:
        return self.docker.calls_for("create")[0]

    def run_never_attempted(self, evidence: Path | None = None) -> None:
        """Fail a run before its create is attempted: the only separately provable no-create."""

        real_prepare = self.sandbox._prepare
        attempts: list[int] = []

        def fail_first_pre_effect_check(deadline: Any, ceiling: float) -> float:
            attempts.append(1)
            if len(attempts) == 1:
                raise SandboxUnavailable("synthetic pre-effect failure")
            return real_prepare(deadline, ceiling)

        with mock.patch.object(self.sandbox, "_prepare", fail_first_pre_effect_check), \
                self.assertRaises(SandboxUnavailable):
            self.run_phase(evidence=evidence)

    def assertPair(self, argv: tuple[str, ...], flag: str, value: str) -> None:
        self.assertIn(flag, argv)
        self.assertEqual(value, argv[argv.index(flag) + 1])


class ImageAndAdapterTests(DockerCase):
    def test_only_exact_sha256_image_references_are_accepted(self) -> None:
        self.assertEqual(IMAGE, validate_image_reference(IMAGE))
        bad_values: tuple[object, ...] = (
            "python:3.12", "python", "python:latest@sha256:" + "ab" * 32, "python@sha256:" + "ab" * 31,
            "python@sha256:" + "AB" * 32, "-python@sha256:" + "ab" * 32, IMAGE + "\n", IMAGE + " --privileged",
            "", None, "python@sha256:" + "ab" * 32 + "x",
        )
        for bad in bad_values:
            with self.subTest(bad=bad), self.assertRaises(VerificationError):
                validate_image_reference(bad)
            with self.subTest(constructor=bad), self.assertRaises(VerificationError):
                ImagePythonUnittestAdapter(cast(str, bad))
            with self.subTest(sandbox=bad), self.assertRaises(VerificationError):
                DockerPythonSandbox(cast(str, bad), evidence_root=self.root, docker_executable=self.exe)

    def test_adapter_seals_linux_python_argv_and_pinned_image(self) -> None:
        repo = self.root / "repo"
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "test_ok.py").write_text(OK_TEST, encoding="utf-8")
        command = ImagePythonUnittestAdapter(IMAGE).seal(repo, ())
        assert command is not None
        self.assertEqual((PYTHON_BINARY, "-B", "-m", "unittest", "tests/test_ok.py", "-v"), command.argv)
        self.assertEqual(VERSION_ARGV, command.version_argv)
        self.assertNotIn(sys.executable, command.argv)
        self.assertEqual(IMAGE, command.image_identity)
        self.assertEqual(CONTAINER_ENVIRONMENT, command.fixed_environment)
        other = ImagePythonUnittestAdapter(OTHER_IMAGE).seal(repo, ())
        assert other is not None
        self.assertNotEqual(command.digest, other.digest)
        self.assertIn(IMAGE, ImagePythonUnittestAdapter(IMAGE).adapter_version)

    def test_unimportable_test_paths_are_skipped_when_discovered_and_rejected_when_selected(self) -> None:
        repo = self.root / "repo"
        (repo / "tests").mkdir(parents=True)
        (repo / "my-tests").mkdir()
        (repo / "tests" / "test_ok.py").write_text(OK_TEST, encoding="utf-8")
        (repo / "my-tests" / "test_dash.py").write_text(OK_TEST, encoding="utf-8")
        adapter = ImagePythonUnittestAdapter(IMAGE)
        command = adapter.seal(repo, ())
        assert command is not None
        self.assertEqual(("tests/test_ok.py",), command.selected_tests)
        with self.assertRaises(VerificationError):
            adapter.seal(repo, ["my-tests/test_dash.py"])
        with self.assertRaises(VerificationError):
            adapter.seal(repo, ["../outside/test_x.py"])

    def test_legacy_defaults_and_digests_are_unchanged(self) -> None:
        self.assertEqual(["python-unittest", "node-typescript", "rustc-check", "go-test"],
                         [adapter.adapter_id for adapter in VerificationRegistry().adapters])
        command = SealedCommand("a", ("x",), ("x", "--version"), ("t",))
        expected = raw_sha256(canonical_json_bytes({
            "adapter_id": "a", "argv": ["x"], "version_argv": ["x", "--version"], "selected_tests": ["t"],
            "fixed_environment": [], "verification_kind": "test-execution",
        }))
        self.assertEqual(expected, command.digest)
        self.assertIsNone(LocalProcessSandbox().capabilities.document()["image_identity"])

    def test_invalid_budgets_are_rejected_without_changing_valid_ones(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), 0, -1, True):
            for field in ("wall_seconds", "cpu_seconds", "memory_bytes", "disk_bytes", "max_output_bytes"):
                arguments: dict[str, Any] = {field: value}
                with self.subTest(field=field, value=value), self.assertRaises(VerificationError):
                    VerificationBudget(**arguments)
        self.assertEqual(300.0, VerificationBudget().wall_seconds)


class SandboxContractTests(DockerCase):
    def test_capabilities_are_honest_about_the_shared_engine(self) -> None:
        capabilities = self.sandbox.capabilities
        self.assertTrue(capabilities.available)
        self.assertFalse(capabilities.hostile_code_isolation)
        self.assertTrue(capabilities.network_deny)
        self.assertEqual(IMAGE, capabilities.image_identity)
        self.assertEqual("trusted-local-oci-container", capabilities.document()["boundary_claim"])

    def test_missing_docker_is_typed_unavailable_not_a_fallback(self) -> None:
        with mock.patch("hive_mind_os.docker_verification.shutil.which", return_value=None):
            sandbox = DockerPythonSandbox(IMAGE, evidence_root=self.root, runner=self.docker)
        self.assertFalse(sandbox.capabilities.available)
        with self.assertRaises(SandboxUnavailable):
            self.run_phase(VERSION_ARGV, sandbox=sandbox)
        self.assertEqual([], self.docker.calls)
        with self.assertRaises(VerificationError):
            DockerPythonSandbox(IMAGE, evidence_root=self.root, docker_executable="docker")

    def test_create_argv_is_the_fixed_offline_readonly_profile(self) -> None:
        self.assertEqual((0, False), self.run_phase())
        argv = self.create_argv()
        self.assertEqual(str(self.exe), argv[0])
        self.assertTrue(all(isinstance(item, str) for item in argv))
        config = str(self.evidence / "docker-config")
        self.assertEqual(1, argv.count("--config"))
        self.assertNotIn("--host", argv)
        for call in self.docker.calls:  # every call uses the owned config, never the user's
            self.assertEqual(("--config", config), call[1:3])
        for flag, value in (("--network", "none"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges"),
                            ("--user", "65534:65534"), ("--pull", "never"), ("--log-driver", "none"),
                            ("--entrypoint", PYTHON_BINARY), ("--workdir", "/workspace")):
            self.assertPair(argv, flag, value)
        self.assertIn("--read-only", argv)
        self.assertEqual(IMAGE, argv[argv.index("--entrypoint") + 2])
        self.assertEqual(TEST_ARGV[1:], argv[argv.index(IMAGE) + 1:])
        mount = argv[argv.index("--mount") + 1]
        self.assertTrue(mount.startswith("type=bind,source=") and mount.endswith(",target=/workspace,readonly"))
        self.assertEqual(1, argv.count("--mount"))
        self.assertEqual({f"{k}={v}" for k, v in CONTAINER_ENVIRONMENT},
                         {argv[i + 1] for i, item in enumerate(argv) if item == "--env"})
        for forbidden in ("--privileged", "--rm", "--volume", "--network=host", "--pid", "--ipc", "--device"):
            self.assertNotIn(forbidden, argv)
        joined = " ".join(argv)
        self.assertNotIn("docker.sock", joined)
        self.assertRegex(joined, r"--memory \d+ --memory-swap \d+ --cpus 1 --pids-limit 128 --ulimit cpu=\d+:\d+")
        self.assertRegex(argv[argv.index("--tmpfs") + 1], r"^/tmp:rw,noexec,nosuid,nodev,mode=1777,size=\d+$")

    def test_host_environment_and_secrets_are_never_inherited(self) -> None:
        secrets = {"HIVE_ACCEPTANCE_SECRET": "must-not-leak", "GITHUB_TOKEN": "must-not-leak",
                   "OPENAI_API_KEY": "must-not-leak", "HOME": "/home/synthetic",
                   "DOCKER_CONFIG": "/home/synthetic/.docker", "DOCKER_HOST": "tcp://synthetic.invalid:2375",
                   "DOCKER_CONTEXT": "synthetic-context", "HTTP_PROXY": PROXY_ENTRY.partition("=")[2],
                   "HTTPS_PROXY": PROXY_ENTRY.partition("=")[2]}
        with mock.patch.dict(os.environ, secrets):
            sandbox = self.make_sandbox(client_environment=None)
        self.assertEqual((0, False), self.run_phase(sandbox=sandbox))
        for environment in self.docker.environments:
            self.assertEqual({"HOME": "/home/synthetic"}, {k: v for k, v in environment.items() if k in secrets})
        joined = "\0".join("\0".join(call) for call in self.docker.calls)
        self.assertNotIn("must-not-leak", joined)
        self.assertNotIn("/home/synthetic", joined)
        self.assertNotIn("synthetic-password", joined)
        for selector in ("DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT"):
            with self.subTest(selector=selector), self.assertRaises(VerificationError):
                self.make_sandbox(client_environment={selector: "x"})
        with self.assertRaises(VerificationError):
            self.make_sandbox(client_environment={"GITHUB_TOKEN": "x"})
        with self.assertRaises(VerificationError):
            self.run_phase(sandbox=self.make_sandbox(), environment={"PATH": "/host", "PYTHONPATH": "src"})

    def test_only_sealed_python_argv_is_approved(self) -> None:
        bad = (
            ("/bin/sh", "-c", "echo hi"), (sys.executable, "--version"), (PYTHON_BINARY, "-c", "print(1)"),
            (PYTHON_BINARY, "--version", "--help"), (PYTHON_BINARY, "-B", "-m", "unittest", "-v"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "../test_x.py", "-v"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "-x.py", "-v"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "/abs/test_x.py", "-v"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "tests\\test_x.py", "-v"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "tests/test_ok.py"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "tests/test_ok.py", "--privileged"),
            (PYTHON_BINARY, "-B", "-m", "unittest", "tests/test_missing.py", "-v"),
        )
        for argv in bad:
            with self.subTest(argv=argv), self.assertRaises(VerificationError):
                self.run_phase(argv)
        self.assertEqual([], self.docker.calls)

    def test_workspace_and_output_paths_are_validated_before_any_docker_effect(self) -> None:
        with self.subTest("workspace not beside outputs"), self.assertRaises(VerificationError):
            elsewhere = self.root / "elsewhere"
            (elsewhere / "workspace").mkdir(parents=True)
            self.run_phase(workspace=elsewhere / "workspace")
        with self.subTest("evidence outside root"), self.assertRaises(VerificationError):
            self.run_phase(sandbox=self.make_sandbox(evidence_root=self.root / "not-the-evidence-parent"))
        with self.subTest("unsafe mount character"), self.assertRaises(VerificationError):
            comma = self.root / "a,readonly=false"
            (comma / "workspace" / "tests").mkdir(parents=True)
            (comma / "workspace" / "tests" / "test_ok.py").write_text(OK_TEST, encoding="utf-8")
            self.run_phase(evidence=comma)
        with self.subTest("existing output is never overwritten"), self.assertRaises(VerificationError):
            (self.evidence / "stdout.bin").write_bytes(b"prior evidence")
            self.run_phase()
        self.assertEqual(b"prior evidence", (self.evidence / "stdout.bin").read_bytes())
        self.assertEqual([], self.docker.calls)

    def test_workspace_symlink_is_rejected(self) -> None:
        try:
            os.symlink(self.workspace / "tests" / "test_ok.py", self.workspace / "alias.py")
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(VerificationError, "symlink"):
            self.run_phase()
        self.assertEqual([], self.docker.calls)

    def test_mount_source_translation_is_narrow(self) -> None:
        self.assertEqual("/run/desktop/mnt/host/c/Users/beesp/a b/workspace",
                         expected_mount_source("C:\\Users\\beesp\\a b\\workspace", windows=True))
        self.assertEqual("/run/desktop/mnt/host/d/x", expected_mount_source("D:/x", windows=True))
        self.assertEqual("/srv/evidence/workspace", expected_mount_source("/srv/evidence/workspace", windows=False))
        for refused in ("\\\\server\\share\\workspace", "\\\\?\\C:\\workspace", "relative\\workspace", "C:"):
            with self.subTest(refused=refused), self.assertRaises(VerificationError):
                expected_mount_source(refused, windows=True)

    def test_non_finite_or_non_positive_timeouts_and_budgets_never_reach_docker(self) -> None:
        for timeout in (float("nan"), float("inf"), 0, -5, True):
            with self.subTest(timeout=timeout), self.assertRaises(VerificationError):
                self.run_phase(timeout=cast(float, timeout))
        forged = VerificationBudget()
        object.__setattr__(forged, "wall_seconds", float("nan"))
        with self.assertRaises(VerificationError):
            self.run_phase(budget=forged)
        self.assertEqual([], self.docker.calls)
        with self.assertRaises(VerificationError):
            self.make_sandbox(cpus=float("nan"))

    def test_docker_host_is_an_explicit_local_endpoint_bound_into_every_call(self) -> None:
        for bad in ("tcp://synthetic.invalid:2375", "ssh://synthetic@invalid", "npipe:////./pipe/a b", "",
                    "unix://relative.sock", "npipe:////./pipe/x --privileged"):
            with self.subTest(bad=bad), self.assertRaises(VerificationError):
                self.make_sandbox(docker_host=bad)
        host = "npipe:////./pipe/syntheticEngine"
        self.assertEqual((0, False), self.run_phase(sandbox=self.make_sandbox(docker_host=host)))
        config = str(self.evidence / "docker-config")
        for call in self.docker.calls:
            self.assertEqual(("--config", config, "--host", host), call[1:5])
        stored = json.loads((self.evidence / "sandbox-tests.receipt.json").read_bytes())
        self.assertEqual(host, stored["docker"]["host"])
        self.assertEqual(config, stored["docker"]["config_directory"])
        self.assertEqual(sha256_of(b"{}\n"), stored["docker"]["config_digest"])
        self.assertEqual(host, self.record("allocation_intent")["docker_host"])

    def test_docker_client_config_is_an_owned_inert_directory_and_never_the_users(self) -> None:
        with mock.patch.dict(os.environ, {"DOCKER_CONFIG": "C:\\Users\\synthetic\\.docker"}):
            sandbox = self.make_sandbox(client_environment=None)
        self.assertEqual((0, False), self.run_phase(sandbox=sandbox))
        directory = self.evidence / "docker-config"
        self.assertEqual(["config.json"], sorted(os.listdir(directory)))
        self.assertEqual(b"{}\n", (directory / "config.json").read_bytes())
        self.assertTrue(all("DOCKER_CONFIG" not in environment for environment in self.docker.environments))
        self.assertEqual(sha256_of(b"{}\n"), self.record("allocation_intent")["docker_config_digest"])

    def test_pre_existing_or_altered_config_is_refused_before_any_docker_effect(self) -> None:
        proxies = b'{"proxies":{"default":{"httpProxy":"' + PROXY_ENTRY.partition("=")[2].encode() + b'"}}}\n'
        for name, prepare in (
            ("proxy config", lambda d: (d / "config.json").write_bytes(proxies)),
            ("extra file", lambda d: (d / "extra").write_bytes(b"x")),
            ("extra directory", lambda d: (d / "contexts").mkdir()),
        ):
            with self.subTest(name):
                evidence = self.make_evidence("cfg-" + name.replace(" ", "-"))
                directory = evidence / "docker-config"
                directory.mkdir()
                (directory / "config.json").write_bytes(b"{}\n")
                prepare(directory)
                with self.assertRaises(SandboxUnavailable):
                    self.run_phase(evidence=evidence)
        self.assertEqual([], self.docker.calls)

    def test_config_changed_between_calls_stops_all_further_docker_use(self) -> None:
        proxies = b'{"proxies":{"default":{"httpProxy":"' + PROXY_ENTRY.partition("=")[2].encode() + b'"}}}\n'

        def inject_proxy_config(argv: tuple[str, ...]) -> None:
            (self.evidence / "docker-config" / "config.json").write_bytes(proxies)

        self.docker.before_create = inject_proxy_config
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        self.assertEqual(["image", "create"], self.docker.verbs())  # nothing ran after the change
        self.assertEqual(1, len(self.docker.containers))
        evidence_text = b"".join(p.read_bytes() for p in self.evidence.glob("sandbox-*"))
        self.assertNotIn(b"synthetic-password", evidence_text)
        self.assertFalse(self.last_receipt()["cleanup_verified"])


class ExecutionTests(DockerCase):
    def test_exact_native_bind_source_is_accepted_without_path_aliases(self) -> None:
        def native_source(info: dict[str, Any]) -> None:
            info["Mounts"][0]["Source"] = str(self.workspace)

        self.docker.mutate = native_source
        self.assertEqual((0, False), self.run_phase())
        self.assertTrue(self.last_receipt()["cleanup_verified"])

    def test_success_journals_intent_before_create_and_retains_exact_receipt(self) -> None:
        observed: list[list[str]] = []
        self.docker.before_create = lambda argv: observed.append([r["phase"] for r in self.journal()])
        self.assertEqual((0, False), self.run_phase())
        self.assertEqual([["allocation_intent", "image_verified"]], observed)
        self.assertEqual(
            ["allocation_intent", "image_verified", "create_result", "configuration_checked", "start_attach",
             "attach_result", "final_state", "cleanup", "outcome"], [r["phase"] for r in self.journal()])
        self.assertEqual({}, self.docker.containers)
        self.assertEqual(["image", "create", "inspect", "start", "inspect", "inspect", "rm", "inspect"],
                         self.docker.verbs())
        report = self.record("configuration_checked")["applied"]["environment_report"]
        self.assertEqual((True, [], [], []), (report["exact"], report["unexpected"], report["missing"],
                                              report["changed"]))
        self.assertEqual(report["expected_digest"], self.record("image_verified")["expected_environment_digest"])
        stored = json.loads((self.evidence / "sandbox-tests.receipt.json").read_bytes())
        digest = stored.pop("receipt_digest")
        self.assertEqual(digest, raw_sha256(canonical_json_bytes(stored)))
        self.assertEqual(list(TEST_ARGV), stored["command"])
        self.assertEqual(IMAGE, stored["image_identity"])
        self.assertEqual(dict(CONTAINER_ENVIRONMENT), stored["container_environment"])
        self.assertEqual(list(self.create_argv()), stored["create_argv"])
        self.assertEqual(sha256_of(GENUINE_CLIENT), stored["docker"]["executable_digest"])
        self.assertFalse(stored["hostile_code_isolation"])
        self.assertTrue(stored["cleanup_verified"])
        self.assertFalse(stored["create_unresolved"])
        self.assertEqual(self.journal()[-1]["digest"], stored["journal"]["head_digest"])
        stdout = (self.evidence / "stdout.bin").read_bytes()
        self.assertEqual(sha256_of(stdout), stored["outputs"]["stdout"]["digest"])
        self.assertEqual(digest, self.last_receipt()["receipt_digest"])
        self.assertEqual(f"hive-verify-tests-{1:032x}", stored["allocation"]["name"])
        self.assertEqual(f"{1:032x}", stored["allocation"]["label"][LABEL_KEY])
        self.assertEqual(20.0, stored["timing"]["cleanup_allowance_seconds"])
        self.assertEqual(30.0, stored["timing"]["execution_seconds_allowed"])
        applied = stored["applied_configuration"]
        self.assertEqual(1_073_741_824, applied["memory"])
        self.assertEqual(applied["memory"], applied["memory_swap"])
        self.assertEqual([{"Name": "cpu", "Soft": 240, "Hard": 240}], applied["ulimits"])
        self.assertEqual("none", applied["log_driver"])
        self.assertEqual(["no-new-privileges"], applied["security_opt"])
        self.assertEqual(expected_mount_source(str(self.workspace.resolve())), applied["mounts"][0]["source"])
        self.assertEqual([False], [m["rw"] for m in applied["mounts"]])

    def test_version_and_test_runs_are_retained_separately(self) -> None:
        self.assertEqual((0, False), self.run_phase(VERSION_ARGV, prefix="version."))
        self.assertEqual((0, False), self.run_phase(prefix=""))
        self.assertEqual(2, len(self.docker.calls_for("create")))
        for phase in ("version", "tests"):
            self.assertTrue((self.evidence / f"sandbox-{phase}.journal.jsonl").is_file())
            self.assertTrue((self.evidence / f"sandbox-{phase}.receipt.json").is_file())
        with self.assertRaises(VerificationError):
            self.run_phase()  # never overwrites retained evidence
        self.assertEqual(2, len(self.docker.calls_for("create")))

    def test_nonzero_test_exit_is_reported_truthfully(self) -> None:
        self.docker.exit_code = 3
        self.assertEqual((3, False), self.run_phase())
        self.assertEqual("EXITED", self.last_receipt()["status"])

    def test_timeout_stops_and_removes_only_the_owned_allocation(self) -> None:
        foreign = self.docker.add_foreign("synthetic-unrelated-container")
        self.docker.attach_mode = "hang"
        self.assertEqual((137, True), self.run_phase())
        owned = hashlib.sha256(f"hive-verify-tests-{1:032x}".encode()).hexdigest()
        self.assertEqual([owned], [call[-1] for call in self.docker.calls_for("kill")])
        self.assertEqual([owned], [call[-1] for call in self.docker.calls_for("rm")])
        self.assertEqual({foreign}, set(self.docker.containers))
        self.assertIn("stop", [r["phase"] for r in self.journal()])
        self.assertEqual("TIMED_OUT", self.last_receipt()["status"])

    def test_output_flood_is_bounded_while_streaming_and_stops_the_allocation(self) -> None:
        self.docker.attach_mode = "flood"
        exit_code, timed_out = self.run_phase(budget=VerificationBudget(max_output_bytes=100))
        self.assertEqual((137, False), (exit_code, timed_out))
        self.assertEqual(101, (self.evidence / "stdout.bin").stat().st_size)
        self.assertEqual(1, len(self.docker.calls_for("kill")))
        self.assertEqual("OUTPUT_CAPPED", self.last_receipt()["status"])
        self.assertEqual({}, self.docker.containers)

    def test_every_applied_configuration_drift_is_refused_before_start(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "mounts": lambda d: d["Mounts"][0].update(Source="/etc"),
            "memory swap": lambda d: d["HostConfig"].update(MemorySwap=-1),
            "cpu ulimit": lambda d: d["HostConfig"].update(Ulimits=[]),
            "tmpfs": lambda d: d["HostConfig"].update(Tmpfs={"/tmp": "rw,exec,suid,dev,size=1t"}),
            "no-new-privileges": lambda d: d["HostConfig"].update(SecurityOpt=["no-new-privileges=false"]),
            "log driver": lambda d: d["HostConfig"]["LogConfig"].update(Type="json-file"),
            "capabilities": lambda d: d["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
            "binds and devices": lambda d: d["HostConfig"].update(Binds=["/:/host"]),
            "host mounts": lambda d: d["HostConfig"]["Mounts"][0].update(Source="/etc"),
            "network": lambda d: d["HostConfig"].update(NetworkMode="bridge"),
            "memory": lambda d: d["HostConfig"].update(Memory=0),
        }
        extra_mount = {"Type": "volume", "Destination": "/data", "RW": True}
        cases["mounts (extra)"] = lambda d: d["Mounts"].append(extra_mount)
        for index, (name, mutate) in enumerate(cases.items()):
            with self.subTest(name):
                evidence = self.make_evidence(f"drift-{index}")
                self.docker.mutate = mutate
                with self.assertRaises(SandboxUnavailable):
                    self.run_phase(evidence=evidence)
                checked = next(r for r in self.journal(evidence=evidence) if r["phase"] == "configuration_checked")
                self.assertFalse(checked["ok"])
                self.assertIn(name.split(" (")[0], checked["problems"])
        self.docker.mutate = None
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertEqual({}, self.docker.containers)

    def test_every_failed_attempted_create_stays_unresolved_whatever_the_wording(self) -> None:
        for index, mode in enumerate(FAILED_CREATE_MESSAGES):
            with self.subTest(mode=mode):
                evidence = self.make_evidence(f"failed-{index}")
                self.docker.create_mode = mode
                with self.assertRaises(SandboxCleanupError):
                    self.run_phase(evidence=evidence)
                self.assertEqual([], self.docker.calls_for("start"))
                receipt = self.last_receipt()
                self.assertEqual(("ABORTED", False, True), (receipt["status"], receipt["cleanup_verified"],
                                                            receipt["create_unresolved"]))
                created = self.record("create_result", evidence)
                self.assertEqual(("unknown", 1), (created["outcome"], created["returncode"]))
                self.assertFalse(self.record("cleanup", evidence)["verified"])
                self.assertNotIn("create_resolved", [r["phase"] for r in self.journal(evidence=evidence)])

    def test_a_create_that_was_never_attempted_is_separately_provable_and_settled(self) -> None:
        self.run_never_attempted()
        receipt = self.last_receipt()
        self.assertEqual(("ABORTED", True, False), (receipt["status"], receipt["cleanup_verified"],
                                                    receipt["create_unresolved"]))
        self.assertEqual("not_attempted", self.record("create_result")["outcome"])
        self.assertEqual([], self.docker.calls_for("create"))

    def test_environment_must_equal_the_image_merge_exactly(self) -> None:
        def replace(key: str, value: str) -> Callable[[dict[str, Any]], None]:
            def mutate(d: dict[str, Any]) -> None:
                d["Config"]["Env"] = [f"{key}={value}" if e.startswith(key + "=") else e for e in d["Config"]["Env"]]
            return mutate

        cases: dict[str, tuple[Callable[[dict[str, Any]], None], str, list[str]]] = {
            "proxy injected by the docker client": (
                lambda d: d["Config"]["Env"].append(PROXY_ENTRY), "unexpected", ["HTTP_PROXY"]),
            "explicit value altered": (replace("PYTHONPATH", "elsewhere"), "changed", ["PYTHONPATH"]),
            "explicit value missing": (
                lambda d: d["Config"].update(Env=[e for e in d["Config"]["Env"] if not e.startswith("TMPDIR=")]),
                "missing", ["TMPDIR"]),
            "image variable altered": (replace("PATH", "/tmp/evil"), "changed", ["PATH"]),
            "duplicate key": (lambda d: d["Config"]["Env"].append("TMPDIR=/tmp"), "malformed", []),
        }
        for index, (name, (mutate, field, expected)) in enumerate(cases.items()):
            with self.subTest(name):
                evidence = self.make_evidence(f"env-{index}")
                self.docker.mutate = mutate
                with self.assertRaises(SandboxUnavailable):
                    self.run_phase(evidence=evidence)
                checked = self.record("configuration_checked", evidence)
                self.assertIn("environment", checked["problems"])
                report = checked["applied"]["environment_report"]
                self.assertFalse(report["exact"])
                self.assertEqual(True if field == "malformed" else expected, report[field])
                raw = b"".join(p.read_bytes() for p in evidence.glob("sandbox-*"))
                self.assertNotIn(b"synthetic-password", raw)  # values are digested, never recorded
        self.docker.mutate = None
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertEqual({}, self.docker.containers)

    def test_unexpected_credential_value_is_only_ever_recorded_as_a_digest(self) -> None:
        self.docker.mutate = lambda d: d["Config"]["Env"].append(PROXY_ENTRY)
        with self.assertRaises(SandboxUnavailable):
            self.run_phase()
        report = self.record("configuration_checked")["applied"]["environment_report"]
        self.assertEqual({"HTTP_PROXY": raw_sha256(PROXY_ENTRY.encode())}, report["value_digests"])
        self.assertIn("HTTP_PROXY", self.record("configuration_checked")["applied"]["environment_names"])

    def test_a_superset_of_image_environment_is_not_accepted(self) -> None:
        # The image gains a variable between the pinned-image read and the container inspect.
        def image_changes(argv: tuple[str, ...]) -> None:
            self.docker.image_env = ["PATH=/usr/local/bin", "LD_PRELOAD=/tmp/evil.so"]

        self.docker.before_create = image_changes
        with self.assertRaises(SandboxUnavailable):
            self.run_phase()
        report = self.record("configuration_checked")["applied"]["environment_report"]
        self.assertEqual(["LD_PRELOAD"], report["unexpected"])
        self.assertEqual([], self.docker.calls_for("start"))

    def test_image_baked_environment_is_merged_deterministically_with_the_fixed_values(self) -> None:
        self.docker.image_env = ["PATH=/opt/py/bin", "LANG=C.UTF-8", "PYTHONPATH=/image/default"]
        self.assertEqual((0, False), self.run_phase())
        merged = {"PATH": "/opt/py/bin", "LANG": "C.UTF-8", **dict(CONTAINER_ENVIRONMENT)}  # fixed values win
        self.assertEqual(raw_sha256(canonical_json_bytes(merged)),
                         self.record("image_verified")["expected_environment_digest"])

    def test_a_malformed_pinned_image_environment_stops_before_any_create(self) -> None:
        self.docker.image_env = ["not-a-key-value-entry"]
        with self.assertRaisesRegex(SandboxUnavailable, "malformed"):
            self.run_phase()
        self.assertEqual([], self.docker.calls_for("create"))
        self.assertEqual("not_attempted", self.record("create_result")["outcome"])
        self.assertTrue(self.last_receipt()["cleanup_verified"])

    def test_unknown_create_that_left_an_owned_container_is_removed_and_resolved(self) -> None:
        self.docker.create_mode = "unknown"
        with self.assertRaises(SandboxUnavailable):
            self.run_phase()
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertEqual({}, self.docker.containers)
        self.assertEqual(("ABORTED", True, False), (self.last_receipt()["status"],
                                                    self.last_receipt()["cleanup_verified"],
                                                    self.last_receipt()["create_unresolved"]))
        self.assertIn("create_resolved", [r["phase"] for r in self.journal()])

    def test_foreign_container_with_the_allocation_name_is_never_touched(self) -> None:
        foreign = self.docker.add_foreign(f"hive-verify-tests-{1:032x}")
        with self.assertRaises(SandboxOwnershipError):
            self.run_phase()
        self.assertEqual({foreign}, set(self.docker.containers))
        self.assertEqual([], self.docker.calls_for("kill") + self.docker.calls_for("rm"))
        self.assertFalse(self.last_receipt()["cleanup_verified"])

    def test_cleanup_failure_is_typed_and_evidence_is_preserved(self) -> None:
        self.docker.rm_fails = True
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        last = self.last_receipt()
        self.assertEqual(("EXITED", False), (last["status"], last["cleanup_verified"]))
        self.assertEqual(1, len(self.docker.containers))
        cleanup = next(r for r in self.journal() if r["phase"] == "cleanup")
        self.assertFalse(cleanup["verified"])
        self.assertEqual(0, json.loads((self.evidence / "sandbox-tests.receipt.json").read_bytes())["exit_code"])

    def test_one_execution_deadline_spans_create_inspect_and_attach(self) -> None:
        self.docker.cost = {"create": 20.0, "inspect": 3.0}
        self.assertEqual((0, False), self.run_phase(timeout=30))
        timeouts = dict(reversed(self.docker.timeouts))  # first call per verb wins
        self.assertAlmostEqual(30.0, timeouts["create"])
        first_inspect = next(t for verb, t in self.docker.timeouts if verb == "inspect")
        self.assertAlmostEqual(10.0, first_inspect)  # 30 - 20 already spent
        attach = next(t for verb, t in self.docker.timeouts if verb == "start")
        self.assertTrue(0 < attach <= 7.0 + 1e-6, attach)  # never the full original timeout again
        self.assertAlmostEqual(9.0, self.last_receipt()["cleanup_seconds"])  # three 3s inspects, own allowance

    def test_no_start_after_the_execution_deadline_expires(self) -> None:
        self.docker.cost = {"create": 31.0}
        with self.assertRaises(SandboxUnavailable):
            self.run_phase(timeout=30)
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertEqual({}, self.docker.containers)  # reaped inside the separate cleanup allowance
        receipt = self.last_receipt()
        self.assertTrue(receipt["cleanup_verified"])
        stored = json.loads((self.evidence / "sandbox-tests.receipt.json").read_bytes())
        self.assertGreaterEqual(stored["timing"]["execution_seconds_used"], 31.0)
        self.assertEqual(20.0, stored["timing"]["cleanup_allowance_seconds"])

    def test_deadline_that_expires_exactly_before_start_refuses_to_start(self) -> None:
        self.docker.cost = {"create": 15.0, "inspect": 15.0}
        with self.assertRaisesRegex(SandboxUnavailable, "expired before start"):
            self.run_phase(timeout=30)
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertIn("start_refused", [r["phase"] for r in self.journal()])

    def test_cleanup_allowance_is_shared_and_exhaustion_is_recorded(self) -> None:
        self.docker.attach_mode, self.docker.cost = "hang", {"kill": 25.0}
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        stored = json.loads((self.evidence / "sandbox-tests.receipt.json").read_bytes())
        self.assertTrue(stored["timing"]["cleanup_allowance_exhausted"])
        self.assertFalse(stored["cleanup_verified"])
        self.assertEqual(1, len(self.docker.containers))  # not removed; never claimed removed

    def test_swapped_docker_binary_is_never_executed(self) -> None:
        self.exe.write_bytes(GENUINE_CLIENT + b" swapped")
        with self.assertRaisesRegex(SandboxUnavailable, "changed"):
            self.run_phase()
        self.assertEqual([], self.docker.calls)
        self.assertFalse(self.journal_path().exists())

    def test_binary_swapped_mid_run_stops_all_further_execution(self) -> None:
        def swap_binary(argv: tuple[str, ...]) -> None:
            self.exe.write_bytes(GENUINE_CLIENT + b" swapped")

        self.docker.before_create = swap_binary
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        self.assertEqual(["image", "create"], self.docker.verbs())  # nothing after the swap was executed
        self.assertEqual(1, len(self.docker.containers))
        self.assertFalse(self.last_receipt()["cleanup_verified"])


class LateCreateTests(DockerCase):
    def unresolved_run(self) -> Path:
        self.docker.create_mode = "late"
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        return self.journal_path()

    def test_unknown_create_with_no_container_is_never_reported_as_clean(self) -> None:
        self.unresolved_run()
        receipt = self.last_receipt()
        self.assertEqual(("ABORTED", False, True), (receipt["status"], receipt["cleanup_verified"],
                                                    receipt["create_unresolved"]))
        records = self.journal()
        self.assertEqual("unknown", self.record("create_result")["outcome"])
        cleanup = next(r for r in records if r["phase"] == "cleanup")
        self.assertFalse(cleanup["verified"])
        self.assertFalse(records[-1]["cleanup_verified"])
        self.assertNotIn("create_resolved", [r["phase"] for r in records])

    def test_recover_stays_unresolved_while_absent_and_never_reports_settled(self) -> None:
        path = self.unresolved_run()
        before = len(self.docker.calls)
        for attempt in range(2):
            with self.subTest(attempt=attempt), self.assertRaisesRegex(SandboxCleanupError, "unresolved"):
                self.sandbox.recover(path)
        self.assertGreater(len(self.docker.calls), before)  # it really re-inspected each time
        self.assertEqual([], self.docker.calls_for("start"))
        outcomes = [r for r in self.journal() if r["phase"] == "outcome"]
        self.assertEqual(["ABORTED", "CREATE_UNRESOLVED", "CREATE_UNRESOLVED"], [o["status"] for o in outcomes])
        self.assertTrue(all(o["cleanup_verified"] is False for o in outcomes))

    def test_a_late_container_is_reaped_by_a_later_recover_without_execution(self) -> None:
        path = self.unresolved_run()
        with self.assertRaises(SandboxCleanupError):
            self.sandbox.recover(path)
        self.docker.materialize()
        self.assertEqual(1, len(self.docker.containers))
        report = self.sandbox.recover(path)
        self.assertEqual(("RECOVERED_NOT_STARTED", False), (report["status"], report["re_executed"]))
        self.assertEqual({}, self.docker.containers)
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertIn("create_resolved", [r["phase"] for r in self.journal()])
        self.assertTrue(self.sandbox.recover(path)["already_settled"])

    def test_a_late_container_that_is_foreign_labelled_is_left_alone(self) -> None:
        path = self.unresolved_run()
        self.docker.materialize()
        only = next(iter(self.docker.containers.values()))
        only["options"]["labels"] = {"synthetic.owner": "someone-else"}
        with self.assertRaises(SandboxOwnershipError):
            self.sandbox.recover(path)
        self.assertEqual(1, len(self.docker.containers))
        self.assertEqual([], self.docker.calls_for("kill") + self.docker.calls_for("rm"))

    def test_no_failed_create_wording_proves_that_the_request_was_not_submitted(self) -> None:
        # A clean exit 1 with the exact CLI wording can still be a read timeout or a proxy
        # error after the daemon accepted the request; the container then appears late.
        for index, mode in enumerate(FAILED_CREATE_MESSAGES):
            with self.subTest(mode=mode):
                evidence = self.make_evidence(f"late-{index}")
                self.docker.create_mode, self.docker.error_creates_late = mode, True
                with self.assertRaises(SandboxCleanupError):
                    self.run_phase(evidence=evidence)
                receipt = self.last_receipt()
                self.assertEqual((False, True), (receipt["cleanup_verified"], receipt["create_unresolved"]))
                journal = self.journal_path(evidence=evidence)
                self.assertNotIn("create_resolved", [r["phase"] for r in self.journal(evidence=evidence)])
                # The immediate inspect was absent, so a later recovery still has to look again.
                with self.assertRaisesRegex(SandboxCleanupError, "unresolved"):
                    self.sandbox.recover(journal)
                self.docker.materialize()
                self.assertEqual(1, len(self.docker.containers))
                report = self.sandbox.recover(journal)
                self.assertEqual(("RECOVERED_NOT_STARTED", False), (report["status"], report["re_executed"]))
                self.assertEqual({}, self.docker.containers)
                self.assertEqual([], self.docker.calls_for("start"))
                self.assertIn("create_resolved", [r["phase"] for r in self.journal(evidence=evidence)])
                self.assertTrue(self.sandbox.recover(journal)["already_settled"])

    def test_a_journal_that_stops_at_the_intent_is_unresolved_not_settled(self) -> None:
        self.run_never_attempted()
        path = self.journal_path()
        lines = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(lines[0])  # crash right after the durable intent, before any create result
        with self.assertRaisesRegex(SandboxCleanupError, "unresolved"):
            self.sandbox.recover(path)
        path.write_bytes(b"".join(lines[:2]))  # intent + a provable "never attempted"
        self.assertEqual("RECOVERED_ABSENT", self.sandbox.recover(path)["status"])
        # A journal that records an attempted-but-failed create is never settled by absence.
        evidence = self.make_evidence("attempted")
        self.docker.create_mode = "refuse"
        with self.assertRaises(SandboxCleanupError):
            self.run_phase(evidence=evidence)
        attempted = self.journal_path(evidence=evidence)
        failed_lines = attempted.read_bytes().splitlines(keepends=True)
        attempted.write_bytes(b"".join(failed_lines[:3]))  # intent, image_verified, create_result(unknown)
        with self.assertRaisesRegex(SandboxCleanupError, "unresolved"):
            self.sandbox.recover(attempted)


class RecoveryTests(DockerCase):
    def crash_mid_attach(self) -> str:
        self.docker.attach_mode, self.docker.control_fails = "crash", True
        with self.assertRaises(_Crash):
            self.run_phase()
        self.docker.attach_mode, self.docker.control_fails = "exit", False
        self.assertEqual(1, len(self.docker.containers))
        return next(iter(self.docker.containers))

    def test_started_allocation_is_reaped_without_running_again(self) -> None:
        self.crash_mid_attach()
        report = self.sandbox.recover(self.journal_path())
        self.assertEqual("RECOVERED_AFTER_START", report["status"])
        self.assertFalse(report["re_executed"])
        self.assertEqual({}, self.docker.containers)
        self.assertEqual(1, len(self.docker.calls_for("start")))
        self.assertEqual(1, len(self.docker.calls_for("create")))
        records = self.journal()
        self.assertEqual("outcome", records[-1]["phase"])
        self.assertEqual("allocation_intent", records[0]["phase"])  # earlier facts are retained, not overwritten
        self.assertTrue(self.sandbox.recover(self.journal_path())["already_settled"])

    def test_unknown_create_that_left_a_container_is_removed_not_started(self) -> None:
        self.docker.create_mode, self.docker.control_fails = "unknown", True
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        self.docker.control_fails = False
        report = self.sandbox.recover(self.journal_path())
        self.assertEqual("RECOVERED_NOT_STARTED", report["status"])
        self.assertEqual({}, self.docker.containers)
        self.assertEqual([], self.docker.calls_for("start"))

    def test_absent_never_attempted_allocation_is_recorded_without_touching_anything(self) -> None:
        self.run_never_attempted()
        # Model a controller that died right after the never-attempted result: keep only
        # the intent and create records, which is still a valid hash-chain prefix.
        path = self.journal_path()
        path.write_bytes(b"".join(path.read_bytes().splitlines(keepends=True)[:2]))
        foreign = self.docker.add_foreign("synthetic-unrelated-container")
        self.assertEqual("RECOVERED_ABSENT", self.sandbox.recover(path)["status"])
        self.assertEqual({foreign}, set(self.docker.containers))

    def test_relabelled_or_foreign_container_fails_closed(self) -> None:
        identifier = self.crash_mid_attach()
        self.docker.containers[identifier]["options"]["labels"] = {LABEL_KEY: "f" * 32}
        before = len(self.docker.calls)
        with self.assertRaises(SandboxOwnershipError):
            self.sandbox.recover(self.journal_path())
        self.assertEqual([], [c for c in self.docker.calls[before:] if verb_of(c) in {"kill", "rm", "start"}])
        self.assertIn(identifier, self.docker.containers)
        self.assertEqual("ownership_mismatch", self.journal()[-1]["phase"])

    def test_recovery_refuses_a_broken_chain_and_misplaced_journals(self) -> None:
        self.assertEqual((0, False), self.run_phase())
        path = self.journal_path()
        tampered = path.read_bytes().replace(b"allocation_intent", b"allocation_intenT", 1)
        path.write_bytes(tampered)
        with self.assertRaisesRegex(VerificationError, "chain"):
            self.sandbox.recover(path)
        self.assertEqual(tampered, path.read_bytes())
        stray = self.root / "sandbox-tests.journal.jsonl"
        stray.write_bytes(b"")
        with self.assertRaises(VerificationError):
            self.make_sandbox(evidence_root=self.evidence).recover(stray)

    def test_torn_final_record_is_preserved_and_reconciled_through_a_separate_journal(self) -> None:
        identifier = self.crash_mid_attach()
        path = self.journal_path()
        original = path.read_bytes() + b'{"seq":99,"phase":"out'  # torn write: no newline, invalid JSON
        path.write_bytes(original)
        complete = len(original.split(b"\n")) - 1
        report = self.sandbox.recover(path)
        self.assertEqual("RECOVERED_AFTER_START", report["status"])
        self.assertEqual(original, path.read_bytes())  # never rewritten or truncated
        self.assertEqual({}, self.docker.containers)
        self.assertNotIn(identifier, self.docker.containers)
        self.assertEqual(1, len(self.docker.calls_for("start")))  # no re-execution
        recovery = Path(report["recovery_journal"])
        self.assertNotEqual(path, recovery)
        records = [json.loads(line) for line in recovery.read_bytes().splitlines()]
        anchor = records[0]
        self.assertEqual("recovery_anchor", anchor["phase"])
        self.assertEqual(sha256_of(original), anchor["original_sha256"])
        self.assertEqual(complete, anchor["prefix_records"])
        self.assertEqual(json.loads(original.split(b"\n")[complete - 1])["digest"], anchor["prefix_head_digest"])
        self.assertEqual(sha256_of(b'{"seq":99,"phase":"out'), anchor["torn_tail_sha256"])
        # A repeat call continues the same recovery journal and settles without new docker effects.
        calls = len(self.docker.calls)
        again = self.sandbox.recover(path)
        self.assertTrue(again["already_settled"])
        self.assertEqual(report["recovery_journal"], again["recovery_journal"])
        self.assertEqual(calls, len(self.docker.calls))
        self.assertEqual(original, path.read_bytes())

    def test_damaged_last_line_is_treated_as_torn_and_kept_byte_for_byte(self) -> None:
        self.crash_mid_attach()
        path = self.journal_path()
        lines = path.read_bytes().split(b"\n")
        lines[-2] = lines[-2].replace(b"ABORTED", b"ABORTEd")  # valid JSON, broken digest
        original = b"\n".join(lines)
        path.write_bytes(original)
        report = self.sandbox.recover(path)
        self.assertEqual("RECOVERED_AFTER_START", report["status"])
        self.assertEqual(original, path.read_bytes())
        self.assertEqual({}, self.docker.containers)

    def test_damage_before_the_final_record_and_an_empty_prefix_are_refused_untouched(self) -> None:
        self.crash_mid_attach()
        path = self.journal_path()
        lines = path.read_bytes().split(b"\n")
        target = next(i for i, line in enumerate(lines) if b'"phase":"create_result"' in line)
        lines[target] = lines[target].replace(b"created", b"createD")
        damaged = b"\n".join(lines)
        path.write_bytes(damaged)
        with self.assertRaisesRegex(VerificationError, "chain is broken"):
            self.sandbox.recover(path)
        self.assertEqual(damaged, path.read_bytes())
        self.assertEqual([], list(self.evidence.glob("*recovery*")))
        partial = b'{"seq":0,"phase":"alloc'
        path.write_bytes(partial)
        with self.assertRaisesRegex(VerificationError, "no intact allocation intent"):
            self.sandbox.recover(path)
        self.assertEqual(partial, path.read_bytes())
        self.assertEqual(1, len(self.docker.containers))  # still visible for the manual procedure

    def test_recovery_never_runs_a_swapped_binary_against_an_old_journal(self) -> None:
        self.crash_mid_attach()
        self.exe.write_bytes(GENUINE_CLIENT + b" swapped")
        before = len(self.docker.calls)
        with self.assertRaisesRegex(SandboxUnavailable, "changed"):
            self.sandbox.recover(self.journal_path())  # sealed digest no longer matches the file
        with self.assertRaisesRegex(SandboxUnavailable, "different docker executable"):
            self.make_sandbox().recover(self.journal_path())  # new seal, but not the journal's binary
        self.assertEqual(before, len(self.docker.calls))
        self.assertEqual(1, len(self.docker.containers))

    def created_then_removed_prefix(self) -> tuple[Path, bytes]:
        """A journal whose create returned an ID; the container is really gone."""

        self.assertEqual((0, False), self.run_phase())
        path = self.journal_path()
        return path, b"".join(path.read_bytes().splitlines(keepends=True)[:3])  # intent, image, create_result

    def test_only_the_exact_identifier_bound_diagnostic_proves_a_container_absent(self) -> None:
        path, prefix = self.created_then_removed_prefix()
        exact = (
            b"Error: No such container: {ref}", b"Error: No such object: {ref}",
            b"Error response from daemon: No such container: {ref}", b"Error: No such container: {ref}\r\n",
        )
        for message in exact:
            with self.subTest(exact=message):
                path.write_bytes(prefix)
                self.docker.inspect_error = message
                self.assertEqual("RECOVERED_ABSENT", self.sandbox.recover(path)["status"])
        ambiguous = (
            SOCKET_MISSING, b"no such file or directory", b"Error response from daemon: gateway timeout",
            b"Error: No such container: someone-else", b"Error: No such container: {ref}extra",
            b"Error: No such container: {ref}\nWarning: proxy answered instead of the daemon",
            b"Error: No such image: {ref}", b"error: no such container: {ref}",
        )
        for message in ambiguous:
            with self.subTest(ambiguous=message):
                path.write_bytes(prefix)
                self.docker.inspect_error = message
                with self.assertRaises(SandboxUnavailable):
                    self.sandbox.recover(path)
                self.assertEqual("recovery_unavailable", self.journal()[-1]["phase"])
                self.assertNotIn("outcome", [r["phase"] for r in self.journal()])  # nothing was settled
        self.docker.inspect_error = None
        path.write_bytes(prefix)
        self.assertEqual("RECOVERED_ABSENT", self.sandbox.recover(path)["status"])  # real absence, once observable

    def test_lost_transport_never_settles_an_existing_allocation_and_a_later_recovery_reaps_it(self) -> None:
        self.docker.inspect_error = SOCKET_MISSING
        with self.assertRaises(SandboxCleanupError):
            self.run_phase()
        receipt = self.last_receipt()
        self.assertEqual(("ABORTED", False, False), (receipt["status"], receipt["cleanup_verified"],
                                                     receipt["create_unresolved"]))
        self.assertEqual(1, len(self.docker.containers))  # created before the transport failed
        self.assertFalse(self.record("cleanup")["verified"])
        self.assertEqual([], self.docker.calls_for("start"))
        path = self.journal_path()
        with self.assertRaises(SandboxUnavailable):
            self.sandbox.recover(path)  # still no connection: recorded, nothing settled
        self.assertEqual("recovery_unavailable", self.journal()[-1]["phase"])
        self.assertEqual(1, len(self.docker.containers))
        self.docker.inspect_error = None  # connection restored
        report = self.sandbox.recover(path)
        self.assertEqual(("RECOVERED_NOT_STARTED", False), (report["status"], report["re_executed"]))
        self.assertEqual({}, self.docker.containers)
        self.assertEqual([], self.docker.calls_for("start"))
        self.assertTrue(self.sandbox.recover(path)["already_settled"])

    def test_recovery_needs_the_original_daemon_endpoint_and_owned_config(self) -> None:
        host = "npipe:////./pipe/syntheticEngine"
        sandbox = self.make_sandbox(docker_host=host)
        self.docker.attach_mode, self.docker.control_fails = "crash", True
        with self.assertRaises(_Crash):
            self.run_phase(sandbox=sandbox)
        self.docker.attach_mode, self.docker.control_fails = "exit", False
        before = len(self.docker.calls)
        with self.assertRaisesRegex(SandboxUnavailable, "different docker client config or daemon endpoint"):
            self.sandbox.recover(self.journal_path())  # default endpoint: could report a false absence
        self.assertEqual(before, len(self.docker.calls))
        config = self.evidence / "docker-config" / "config.json"
        config.write_bytes(b'{"proxies":{}}\n')
        with self.assertRaisesRegex(SandboxUnavailable, "inert"):
            sandbox.recover(self.journal_path())
        config.write_bytes(b"{}\n")
        report = sandbox.recover(self.journal_path())
        self.assertEqual("RECOVERED_AFTER_START", report["status"])
        for call in self.docker.calls[before:]:  # recovery used the same owned config and endpoint
            self.assertEqual(("--config", str(self.evidence / "docker-config"), "--host", host), call[1:5])
        self.assertEqual({}, self.docker.containers)


class HangingStream:
    def __init__(self, released: threading.Event) -> None:
        self.released, self.closed = released, False

    def read1(self, size: int) -> bytes:
        self.released.wait(5)
        return b""

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, out: bytes = b"", err: bytes = b"", hang: bool = False, stuck: bool = False) -> None:
        self.release = threading.Event()
        self.stdout: Any = HangingStream(self.release) if hang else io.BytesIO(out)
        self.stderr: Any = io.BytesIO(err)
        # A stuck reader models a descendant that inherited the pipe: killing the client
        # does not end the read, so closing the handle under it could deadlock.
        self.hang, self.stuck, self.returncode, self.killed = hang, stuck, 0, False

    def poll(self) -> int | None:
        return None if self.hang and not self.killed else self.returncode

    def kill(self) -> None:
        self.killed = True
        if not self.stuck:
            self.release.set()

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


class BoundedRunnerTests(unittest.TestCase):
    def test_popen_gets_list_argv_no_shell_and_only_the_given_environment(self) -> None:
        process = FakeProcess(b"out", b"err")
        with mock.patch("hive_mind_os.docker_verification.subprocess.Popen", return_value=process) as popen:
            result = run_bounded(("docker", "inspect", "x"), environment={"HOME": "/h"}, timeout=5, limit=100)
        args, kwargs = popen.call_args
        self.assertEqual(["docker", "inspect", "x"], args[0])
        self.assertIs(False, kwargs["shell"])
        self.assertEqual({"HOME": "/h"}, kwargs["env"])
        self.assertEqual((0, b"out", b"err", False, False), (
            result.returncode, result.stdout, result.stderr, result.timed_out, result.truncated))
        self.assertFalse(process.killed)
        self.assertTrue(process.stdout.closed and process.stderr.closed)  # handles released after their readers

    def test_streams_are_capped_as_they_arrive_and_the_client_is_killed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sink = Path(directory) / "stdout.bin"
            sink.write_bytes(b"")
            process = FakeProcess(b"x" * 500_000, b"y" * 10)
            with mock.patch("hive_mind_os.docker_verification.subprocess.Popen", return_value=process):
                result = run_bounded(("docker", "start"), environment={}, timeout=5, limit=100, stdout_path=sink)
            self.assertEqual(100, sink.stat().st_size)
        self.assertEqual((100, 10, True), (result.stdout_bytes, result.stderr_bytes, result.truncated))
        self.assertTrue(process.killed)
        self.assertTrue(process.stdout.closed and process.stderr.closed)

    def test_wall_timeout_kills_the_client(self) -> None:
        process = FakeProcess(hang=True)
        with mock.patch("hive_mind_os.docker_verification.subprocess.Popen", return_value=process):
            result = run_bounded(("docker", "start"), environment={}, timeout=0.2, limit=100)
        self.assertTrue(result.timed_out)
        self.assertTrue(process.killed)
        self.assertTrue(process.stdout.closed and process.stderr.closed)  # the reader ended after the kill

    def test_a_reader_stuck_on_an_inherited_pipe_is_bounded_and_never_closed_under_itself(self) -> None:
        process = FakeProcess(hang=True, stuck=True)
        started = time.monotonic()
        with mock.patch("hive_mind_os.docker_verification.subprocess.Popen", return_value=process), \
                mock.patch("hive_mind_os.docker_verification._READER_JOIN_SECONDS", 0.05):
            result = run_bounded(("docker", "start"), environment={}, timeout=0.2, limit=100)
        try:
            self.assertTrue(result.timed_out)
            self.assertTrue(process.killed)
            self.assertLess(time.monotonic() - started, 3.0)  # bounded: no deadlock on the stuck handle
            self.assertFalse(process.stdout.closed)           # never closed while its reader is still blocked
            self.assertTrue(process.stderr.closed)            # the finished reader's handle is closed
        finally:
            process.release.set()  # let the daemon reader thread end

    def test_non_finite_timeouts_and_limits_are_refused_before_any_process_starts(self) -> None:
        for timeout, limit in ((float("nan"), 10), (float("inf"), 10), (0, 10), (5, float("nan")), (5, 0)):
            with self.subTest(timeout=timeout, limit=limit), mock.patch(
                "hive_mind_os.docker_verification.subprocess.Popen"
            ) as popen, self.assertRaises(VerificationError):
                run_bounded(("docker", "x"), environment={}, timeout=timeout, limit=cast(int, limit))
            popen.assert_not_called()

    def test_a_live_process_that_closed_its_pipes_still_hits_the_single_deadline(self) -> None:
        # Real, benign local child: closes stdout/stderr, then sleeps well past the deadline.
        code = "import os, time; os.close(1); os.close(2); time.sleep(3)"
        started = time.monotonic()
        result = run_bounded((sys.executable, "-c", code), environment=dict(os.environ), timeout=0.5, limit=100)
        elapsed = time.monotonic() - started
        self.assertTrue(result.timed_out)
        self.assertNotEqual(0, result.returncode)
        self.assertLess(elapsed, 2.5)

    def test_a_quick_real_child_completes_normally(self) -> None:
        code = "import sys; sys.stdout.buffer.write(b'hi'); sys.stderr.buffer.write(b'e')"
        result = run_bounded((sys.executable, "-c", code), environment=dict(os.environ), timeout=30, limit=100)
        self.assertEqual((0, b"hi", b"e", False, False), (
            result.returncode, result.stdout, result.stderr, result.timed_out, result.truncated))

    def test_real_children_leave_no_unclosed_pipe_handle_behind(self) -> None:
        # Retain our real children: finalizers cannot hide an open pipe, and unrelated
        # resources collected elsewhere in the full suite cannot affect this assertion.
        real_popen = subprocess.Popen
        quick = "import sys; sys.stdout.buffer.write(b'hi'); sys.stderr.buffer.write(b'e')"
        deadline = "import os, time; os.close(1); os.close(2); time.sleep(3)"
        for name, code, timeout in (("normal exit", quick, 30), ("deadline kill", deadline, 0.5)):
            processes: list[subprocess.Popen[Any]] = []

            def track_process(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
                process = real_popen(*args, **kwargs)
                processes.append(process)
                return process

            with self.subTest(name):
                try:
                    with mock.patch(
                        "hive_mind_os.docker_verification.subprocess.Popen",
                        side_effect=track_process,
                    ):
                        run_bounded((sys.executable, "-c", code), environment=dict(os.environ), timeout=timeout, limit=100)
                    self.assertEqual(1, len(processes))
                    process = processes[0]
                    self.assertIsNotNone(process.returncode, "run_bounded must reap its child")
                    self.assertIsNotNone(process.stdout)
                    self.assertIsNotNone(process.stderr)
                    assert process.stdout is not None and process.stderr is not None
                    self.assertTrue(process.stdout.closed, "run_bounded left its stdout pipe open")
                    self.assertTrue(process.stderr.closed, "run_bounded left its stderr pipe open")
                finally:
                    # Cleanup follows assertions, including when a regression leaks handles.
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
                        for stream in (process.stdout, process.stderr):
                            if stream is not None:
                                stream.close()


class VerifyRepositoryIntegrationTests(DockerCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.root / "repo"
        (self.repo / "tests").mkdir(parents=True)
        (self.repo / "tests" / "test_ok.py").write_text(OK_TEST, encoding="utf-8")
        self.registry = VerificationRegistry([ImagePythonUnittestAdapter(IMAGE)])
        self.trusted = SandboxRequirements(network_policy="deny", hostile_code_isolation=False)

    def verify(self, name: str, **overrides: Any) -> dict[str, Any]:
        options: dict[str, Any] = {"sandbox": self.sandbox, "requirements": self.trusted, "registry": self.registry}
        options.update(overrides)
        return verify_repository(self.repo, evidence_directory=self.root / name, **options)

    def fake_wall_clock(self) -> Any:
        return mock.patch("hive_mind_os.verification_adapters.time", SimpleNamespace(monotonic=lambda: self.docker.now))

    def test_default_isolation_requirement_still_blocks_before_docker_is_used(self) -> None:
        receipt = self.verify("blocked", requirements=None)
        self.assertEqual("BLOCKED", receipt["status"])
        self.assertIn("hostile-code isolation unavailable", receipt["reason"])
        self.assertFalse(receipt["sandbox"]["hostile_code_isolation"])
        self.assertEqual([], self.docker.calls)
        self.assertEqual("BLOCKED", verify_repository(
            self.repo, evidence_directory=self.root / "no-sandbox", registry=self.registry)["status"])

    def test_trusted_local_requirement_binds_image_command_and_sandbox_receipts(self) -> None:
        receipt = self.verify("passed")
        self.assertEqual("PASSED", receipt["status"], receipt)
        self.assertEqual("python-unittest-oci", receipt["adapter_id"])
        self.assertEqual(f"1|{IMAGE}", receipt["adapter_version"])
        self.assertEqual(IMAGE, receipt["image_identity"])
        self.assertEqual(IMAGE, receipt["runtime"]["image_identity"])
        self.assertFalse(receipt["runtime"]["hostile_code_isolation"])
        self.assertEqual(list(TEST_ARGV), receipt["argv"])
        self.assertEqual(list(VERSION_ARGV), receipt["tool_version_command"])
        self.assertEqual(["PYTHONDONTWRITEBYTECODE", "PYTHONPATH", "TMPDIR"], receipt["environment"])
        self.assertEqual(raw_sha256(canonical_json_bytes(dict(CONTAINER_ENVIRONMENT))), receipt["environment_digest"])
        self.assertIn("Python", receipt["tool_version"]["text"])
        self.assertEqual(["version-probe", "test-run"], [e["phase"] for e in receipt["sandbox_executions"]])
        self.assertNotIn("wall_budget_exceeded", receipt)
        for execution in receipt["sandbox_executions"]:
            stored = json.loads(Path(execution["receipt_path"]).read_bytes())
            self.assertEqual(execution["receipt_digest"], stored.pop("receipt_digest"))
            self.assertEqual(execution["receipt_digest"], raw_sha256(canonical_json_bytes(stored)))
            self.assertEqual(IMAGE, stored["image_identity"])
        written = json.loads((self.root / "passed" / "receipt.json").read_bytes())
        self.assertEqual(receipt, written)
        claimed = written.pop("receipt_digest")
        self.assertEqual(claimed, raw_sha256(canonical_json_bytes(written)))
        self.assertEqual(2, len(self.docker.calls_for("create")))

    def test_failing_tests_are_failed_not_passed(self) -> None:
        self.docker.exit_code = 1
        receipt = self.verify("failed")
        self.assertEqual(("FAILED", 1), (receipt["status"], receipt["exit_code"]))

    def test_a_run_that_outlives_the_wall_budget_cannot_pass(self) -> None:
        self.docker.test_run_cost = 400.0  # the attach "returns success" only after 400 fake seconds
        with self.fake_wall_clock():
            receipt = self.verify("over-wall", budget=VerificationBudget(wall_seconds=300))
        self.assertEqual(0, receipt["exit_code"])
        self.assertEqual("FAILED", receipt["status"])
        self.assertTrue(receipt["wall_budget_exceeded"])
        self.assertEqual(0.0, receipt["cleanup_grace_seconds"])

    def test_only_the_separately_bounded_cleanup_grace_may_exceed_the_wall_budget(self) -> None:
        self.docker.cost = {"rm": 18.0}  # each cleanup spends 18 fake seconds inside its 20s allowance
        with self.fake_wall_clock():
            receipt = self.verify("grace", budget=VerificationBudget(wall_seconds=30))
        self.assertEqual("PASSED", receipt["status"], receipt)
        self.assertAlmostEqual(36.0, receipt["cleanup_grace_seconds"], delta=1e-6)
        self.assertNotIn("wall_budget_exceeded", receipt)

    def test_image_mismatch_between_adapter_and_sandbox_blocks(self) -> None:
        registry = VerificationRegistry([ImagePythonUnittestAdapter(OTHER_IMAGE)])
        receipt = self.verify("mismatch", registry=registry)
        self.assertEqual("BLOCKED", receipt["status"])
        self.assertIn("image identity", receipt["reason"])
        self.assertEqual([], self.docker.calls)

    def test_image_adapter_never_runs_on_the_host_process_sandbox(self) -> None:
        receipt = self.verify("host", sandbox=LocalProcessSandbox(), requirements=SandboxRequirements(
            network_policy="inherit", hostile_code_isolation=False))
        self.assertEqual("BLOCKED", receipt["status"])
        self.assertEqual([], self.docker.calls)

    def test_unavailable_docker_blocks_with_a_retained_receipt(self) -> None:
        with mock.patch("hive_mind_os.docker_verification.shutil.which", return_value=None):
            sandbox = DockerPythonSandbox(IMAGE, evidence_root=self.root, runner=self.docker)
        receipt = self.verify("unavailable", sandbox=sandbox)
        self.assertEqual("BLOCKED", receipt["status"])
        self.assertIn("unavailable", receipt["reason"])
        self.assertTrue((self.root / "unavailable" / "receipt.json").is_file())

    def test_failed_create_blocks_and_binds_partial_sandbox_evidence_as_unresolved(self) -> None:
        self.docker.create_mode = "refuse"
        receipt = self.verify("daemon-down")
        self.assertEqual("BLOCKED", receipt["status"])
        self.assertIn("sandbox execution unavailable", receipt["reason"])
        self.assertEqual(["version-probe"], [e["phase"] for e in receipt["sandbox_executions"]])
        execution = receipt["sandbox_executions"][0]
        self.assertEqual(("ABORTED", False, True), (execution["status"], execution["cleanup_verified"],
                                                    execution["create_unresolved"]))
        self.assertEqual(receipt, json.loads((self.root / "daemon-down" / "receipt.json").read_bytes()))

    def test_docker_config_directory_is_bound_by_the_retained_sandbox_receipts(self) -> None:
        receipt = self.verify("bound")
        self.assertEqual("PASSED", receipt["status"], receipt)
        for execution in receipt["sandbox_executions"]:
            stored = json.loads(Path(execution["receipt_path"]).read_bytes())
            self.assertEqual(str(self.root / "bound" / "docker-config"), stored["docker"]["config_directory"])
            self.assertEqual(sha256_of(b"{}\n"), stored["docker"]["config_digest"])
            self.assertEqual(execution["receipt_digest"], raw_sha256(canonical_json_bytes(
                {k: v for k, v in stored.items() if k != "receipt_digest"})))

    def test_unresolved_create_blocks_and_the_receipt_says_so(self) -> None:
        self.docker.create_mode = "late"
        receipt = self.verify("unresolved")
        self.assertEqual("BLOCKED", receipt["status"])
        execution = receipt["sandbox_executions"][0]
        self.assertTrue(execution["create_unresolved"])
        self.assertFalse(execution["cleanup_verified"])
        self.docker.materialize()
        report = self.sandbox.recover(Path(execution["journal_path"]))
        self.assertEqual("RECOVERED_NOT_STARTED", report["status"])
        self.assertEqual({}, self.docker.containers)


if __name__ == "__main__":
    unittest.main()
