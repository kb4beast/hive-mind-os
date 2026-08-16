from __future__ import annotations

import contextlib
import copy
import importlib.util
import json
import os
import queue
import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
MODULE_PATH = BIN_DIR / "app_server_host.py"
SPEC = importlib.util.spec_from_file_location("isolated_app_server_host", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
app_server_host = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = app_server_host
SPEC.loader.exec_module(app_server_host)


def digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def digest_object(value: object) -> str:
    return digest_bytes(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


class QueueTextReader:
    def __init__(self) -> None:
        self.items: queue.Queue[str | None] = queue.Queue()
        self.closed = False

    def put_json(self, value: object) -> None:
        self.items.put(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.items.put(None)

    def readline(self) -> str:
        value = self.items.get()
        return "" if value is None else value

    def __iter__(self):
        while True:
            value = self.readline()
            if value == "":
                return
            yield value


class FakeWriter:
    def __init__(self, process: "FakeProcess") -> None:
        self.process = process
        self.buffer = ""
        self.closed = False

    def write(self, value: str) -> int:
        if self.closed or self.process.poll() is not None:
            raise BrokenPipeError("fake App Server is closed")
        self.buffer += value
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line:
                self.process.server.handle(json.loads(line), self.process)
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, server: "FakeAppServer") -> None:
        self.server = server
        self.stdout = QueueTextReader()
        self.stderr = QueueTextReader()
        self.stdin = FakeWriter(self)
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def crash(self, code: int = 91) -> None:
        if self.returncode is None:
            self.returncode = code
            self.stdout.close()
            self.stderr.close()

    def terminate(self) -> None:
        self.crash(0)

    def kill(self) -> None:
        self.crash(9)

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            self.crash(0)
        assert self.returncode is not None
        return self.returncode


class FakeAppServer:
    def __init__(self) -> None:
        self.threads: dict[str, dict[str, object]] = {}
        self.archived: dict[str, dict[str, object]] = {}
        self.next_thread = 1
        self.next_turn = 1
        self.requests: list[dict[str, object]] = []
        self.drop_after_acceptance: dict[str, int] = {}
        self.processes: list[FakeProcess] = []
        self.lock = threading.RLock()
        self.config: dict[str, object] = {
            "model": "gpt-test",
            "model_provider": None,
        }
        self.config_by_cwd: dict[str, dict[str, object]] = {}
        self.account: dict[str, object] = {
            "account": {
                "type": "chatgpt",
                "email": "fixture@example.invalid",
                "planType": "team",
            },
            "requiresOpenaiAuth": True,
        }

    def process_factory(self, argv, cwd, environment):
        process = FakeProcess(self)
        process.argv = tuple(argv)
        process.cwd = Path(cwd)
        process.environment = dict(environment)
        self.processes.append(process)
        return process

    def drop_once(self, method: str) -> None:
        self.drop_after_acceptance[method] = (
            self.drop_after_acceptance.get(method, 0) + 1
        )

    def _copy(self, value: object) -> object:
        return copy.deepcopy(value)

    def _status(self, thread: dict[str, object], kind: str) -> None:
        thread["status"] = (
            {"type": "active", "activeFlags": []}
            if kind == "active"
            else {"type": kind}
        )

    def complete(self, thread_id: str, state: str = "completed") -> None:
        with self.lock:
            thread = self.threads[thread_id]
            turns = thread["turns"]
            assert isinstance(turns, list) and turns
            turns[-1]["status"] = state
            self._status(thread, "idle" if state != "failed" else "systemError")
            for process in self.processes:
                if process.poll() is None:
                    process.stdout.put_json(
                        {
                            "method": "turn/completed",
                            "params": {
                                "threadId": thread_id,
                                "turn": self._copy(turns[-1]),
                            },
                        }
                    )

    def _reply(self, process: FakeProcess, request_id: int, result: object) -> None:
        process.stdout.put_json({"id": request_id, "result": result})

    def handle(self, message: dict[str, object], process: FakeProcess) -> None:
        with self.lock:
            method = str(message.get("method"))
            params = message.get("params")
            assert isinstance(params, dict)
            self.requests.append(self._copy(message))
            if "id" not in message:
                return
            request_id = int(message["id"])
            result: object
            if method == "initialize":
                result = {
                    "userAgent": "codex_app_server/0.146.0",
                    "platformFamily": "windows",
                    "platformOs": "windows",
                }
            elif method == "config/read":
                selected_config = self.config_by_cwd.get(
                    str(params.get("cwd")), self.config
                )
                result = {
                    "config": self._copy(selected_config),
                    "layers": [],
                    "origins": {},
                }
            elif method == "account/read":
                if params.get("refreshToken") is not False:
                    raise AssertionError(
                        "account identity probe must not refresh tokens"
                    )
                result = self._copy(self.account)
            elif method == "thread/list":
                source = self.archived if params.get("archived") else self.threads
                search = params.get("searchTerm")
                values = [
                    self._copy(thread)
                    for thread in source.values()
                    if search is None or str(search) in str(thread.get("name") or "")
                ]
                result = {"data": values, "nextCursor": None}
            elif method == "thread/start":
                thread_id = f"thread-{self.next_thread}"
                self.next_thread += 1
                thread = {
                    "id": thread_id,
                    "name": None,
                    "cwd": params.get("cwd"),
                    "status": {"type": "idle"},
                    "turns": [],
                }
                self.threads[thread_id] = thread
                result = {"thread": self._copy(thread)}
            elif method == "thread/name/set":
                self.threads[str(params["threadId"])]["name"] = params["name"]
                result = {}
            elif method == "thread/read":
                thread_id = str(params["threadId"])
                thread = self.threads.get(thread_id) or self.archived.get(thread_id)
                if thread is None:
                    raise AssertionError(f"unknown fake thread {thread_id}")
                result = {"thread": self._copy(thread)}
            elif method == "thread/resume":
                thread = self.threads[str(params["threadId"])]
                self._status(thread, "idle")
                result = {"thread": self._copy(thread)}
            elif method == "turn/start":
                thread = self.threads[str(params["threadId"])]
                turn_id = f"turn-{self.next_turn}"
                self.next_turn += 1
                turn = {
                    "id": turn_id,
                    "status": "inProgress",
                    "input": self._copy(params.get("input", [])),
                    "clientUserMessageId": params.get("clientUserMessageId"),
                }
                turns = thread["turns"]
                assert isinstance(turns, list)
                turns.append(turn)
                self._status(thread, "active")
                result = {"turn": self._copy(turn)}
            elif method == "turn/steer":
                thread = self.threads[str(params["threadId"])]
                turns = thread["turns"]
                assert isinstance(turns, list) and turns
                turns[-1].setdefault("steeredInput", []).extend(
                    self._copy(params.get("input", []))
                )
                result = {"turnId": turns[-1]["id"]}
            elif method == "turn/interrupt":
                thread = self.threads[str(params["threadId"])]
                turns = thread["turns"]
                assert isinstance(turns, list) and turns
                turns[-1]["status"] = "interrupted"
                self._status(thread, "idle")
                result = {}
            elif method == "thread/archive":
                thread_id = str(params["threadId"])
                self.archived[thread_id] = self.threads.pop(thread_id)
                result = {}
            else:
                raise AssertionError(f"unexpected App Server method {method}")
            remaining = self.drop_after_acceptance.get(method, 0)
            if remaining:
                self.drop_after_acceptance[method] = remaining - 1
                process.crash()
                return
            self._reply(process, request_id, result)


class FakePlane:
    def __init__(self, root: Path) -> None:
        self.repo_root = root / "repo"
        self.repo_root.mkdir()
        self.execution_dir = root / "runtime" / "executions" / "unit"
        self.execution_dir.mkdir(parents=True)
        self.host_runtime_dir = root / "host-runtime"
        self.host_runtime_dir.mkdir()
        host_identity = {
            "schema_version": 1,
            "kind": "hive-mind-host-runtime-identity-v1",
            "machine_user_id": digest_text("machine-user"),
        }
        (self.host_runtime_dir / "host-runtime-identity.json").write_text(
            json.dumps(
                {**host_identity, "record_id": digest_object(host_identity)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        self.execution_namespace = "unit"
        self.execution_id = digest_text("execution")
        self.target_branch = "release/unit"
        self.release = None

    @contextlib.contextmanager
    def dispatcher_launch_authority_guard(self, node_id, *, host_id, release_id):
        yield {"node_id": node_id, "host_id": host_id, "release_id": release_id}

    def active_claims(self):
        return {}

    def current_release(self):
        return self.release


class CodexAppServerHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="hive-app-server-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plane = FakePlane(self.root)
        self.executable = self.root / "codex.exe"
        self.executable.write_bytes(b"fake-codex-0.146.0")
        # The adapter correctly requires its launch target to be executable.
        # A Windows-suffixed fixture does not automatically receive that mode
        # bit on Linux runners, so make the cross-platform test double match
        # the authenticated executable contract explicitly.
        self.executable.chmod(0o700)
        self.server = FakeAppServer()
        self.adapters: list[object] = []

    def tearDown(self) -> None:
        for adapter in reversed(self.adapters):
            adapter.close()

    def adapter(
        self, *, host_id=None, environment=None, plane=None, process_factory=None
    ):
        selected_plane = plane or self.plane
        selected_environment = environment or {
            "PATH": "isolated-path",
            "SYSTEMROOT": "C:\\Windows",
            "PYTHONPATH": "foreign-module",
            "NODE_OPTIONS": "--require foreign-module",
            "UNRELATED_SECRET": "must-not-pass",
        }
        adapter = app_server_host.CodexAppServerHost(
            plane=selected_plane,
            host_id=host_id,
            execution_namespace=selected_plane.execution_namespace,
            execution_id=selected_plane.execution_id,
            execution_dir=selected_plane.execution_dir,
            host_runtime_dir=selected_plane.host_runtime_dir,
            wait_seconds=1,
            adapter_module_digest=digest_bytes(MODULE_PATH.read_bytes()),
            executable_path=self.executable,
            process_factory=process_factory or self.server.process_factory,
            version_probe=lambda _path, _environment: "codex-cli 0.146.0",
            schema_probe=lambda _path, _environment: {
                "schema_bundle_digest": digest_text("bundle"),
                "thread_start_schema_digest": digest_text("thread/start"),
                "turn_start_schema_digest": digest_text("turn/start"),
            },
            environment=selected_environment,
            clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        )
        self.adapters.append(adapter)
        return adapter

    def create(self, adapter, key: str = "thread-one"):
        return adapter.create_thread(
            title="Managed unit task",
            prompt="Perform the bounded unit task.",
            idempotency_key=digest_text(key),
        )

    def test_stale_atomic_temporary_is_quarantined_without_wedging_retry(
        self,
    ) -> None:
        evidence = self.root / "atomic-evidence"
        evidence.mkdir()
        target = evidence / "record.json"
        stale = evidence / (f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        stale_payload = b'{"partial":"crash-preserved"}\n'
        stale.write_bytes(stale_payload)
        os.utime(stale, (1, 1))

        # PID/thread reuse cannot collide with the new random private-name scheme.
        app_server_host._atomic_write(target, {"installed": True})
        app_server_host._reconcile_stale_atomic_temporaries(
            evidence,
            (evidence,),
            clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            minimum_age_seconds=0,
        )

        self.assertFalse(stale.exists())
        self.assertEqual(target.read_bytes(), b'{"installed":true}\n')
        quarantine = evidence / "stale-temporary-quarantine"
        blobs = list(quarantine.glob("*.blob"))
        receipts = list(quarantine.glob("*.json"))
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0].read_bytes(), stale_payload)
        self.assertEqual(len(receipts), 1)
        receipt = app_server_host._read_sealed(
            receipts[0],
            kind=app_server_host._STALE_TEMPORARY_KIND,
            fields=app_server_host._STALE_TEMPORARY_FIELDS,
        )
        self.assertEqual(receipt["payload_digest"], digest_bytes(stale_payload))
        self.assertEqual(receipt["source_relative_path"], stale.name)

    def test_file_lock_rejects_a_link_backed_lock_path(self) -> None:
        lock_root = self.root / "lock-link"
        lock_root.mkdir()
        external = self.root / "external.lock"
        external.write_bytes(b"\0")
        link = lock_root / "authority.lock"
        try:
            link.symlink_to(external)
        except OSError:
            # Non-elevated Windows commonly forbids creating a test symlink.  Still
            # exercise the fail-closed branch used after the OS link inspection.
            original = app_server_host._is_link_like
            with mock.patch.object(
                app_server_host,
                "_is_link_like",
                side_effect=lambda path: (
                    Path(path).absolute() == link.absolute() or original(Path(path))
                ),
            ):
                with self.assertRaisesRegex(
                    app_server_host.AppServerHostError, "lock path uses a link"
                ):
                    with app_server_host._FileLock(link, 0.1):
                        self.fail("link-backed lock must never be acquired")
            return
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "lock path uses a link"
        ):
            with app_server_host._FileLock(link, 0.1):
                self.fail("link-backed lock must never be acquired")

    def test_handshake_binds_executable_schema_module_and_sanitized_stdio(self) -> None:
        adapter = self.adapter()
        process = self.server.processes[-1]
        self.assertEqual(
            process.argv,
            (str(self.executable), "app-server", "--listen", "stdio://"),
        )
        self.assertNotIn("PYTHONPATH", process.environment)
        self.assertNotIn("NODE_OPTIONS", process.environment)
        self.assertNotIn("UNRELATED_SECRET", process.environment)
        self.assertEqual(process.environment["NO_COLOR"], "1")
        self.assertEqual(
            [item["method"] for item in self.server.requests[:5]],
            [
                "initialize",
                "initialized",
                "config/read",
                "config/read",
                "account/read",
            ],
        )
        capability = adapter.host_lifecycle_authority(repo_root=self.plane.repo_root)
        for field in ("create", "query", "resume", "interrupt", "archive"):
            self.assertIs(capability[field], True)
        self.assertIs(capability["autonomous_launch"], False)
        self.assertTrue(
            str(capability["source"]).endswith(str(adapter.identity["record_id"]))
        )
        self.assertEqual(adapter.identity["executable_version"], "codex-cli 0.146.0")
        self.assertEqual(adapter.identity["transport"], "stdio://")
        self.assertEqual(
            adapter.identity["schema_bundle_digest"], digest_text("bundle")
        )
        self.assertEqual(
            adapter.identity["machine_user_id"], digest_text("machine-user")
        )
        self.assertEqual(
            adapter.identity["behavior_environment_digest"],
            adapter.behavior_environment_digest,
        )
        self.assertEqual(
            adapter.identity["provider_config_digest"],
            adapter.provider_config_digest,
        )
        self.assertEqual(
            adapter.identity["execution_config_digest"],
            adapter.execution_config_digest,
        )
        self.assertEqual(
            adapter.identity["account_identity_digest"],
            adapter.account_identity_digest,
        )
        self.assertEqual(adapter.identity["effective_model"], "gpt-test")
        self.assertIsNone(adapter.identity["effective_model_provider"])
        self.assertEqual(adapter.identity["launcher_path"], str(self.executable))
        self.assertEqual(
            adapter.identity["launcher_digest"],
            digest_bytes(self.executable.read_bytes()),
        )
        self.assertIsNone(adapter.identity["cli_module_path"])
        self.assertIsNone(adapter.identity["cli_module_digest"])
        self.assertEqual(
            adapter.host_provider_identity(repo_root=self.plane.repo_root),
            adapter.identity,
        )
        self.assertEqual(
            adapter.identity["provider_identity_digest"],
            adapter.provider_identity_digest,
        )
        self.assertEqual(
            adapter.host_id,
            digest_object(
                {
                    "kind": "hive-mind-codex-app-server-provider-v1",
                    "machine_user_id": digest_text("machine-user"),
                }
            ),
        )
        self.assertFalse(hasattr(adapter, "supervisor_step"))

    def test_provider_identity_is_shared_across_repositories_and_namespaces(
        self,
    ) -> None:
        first = self.adapter()
        second_root = self.root / "second"
        second_root.mkdir()
        second_plane = FakePlane(second_root)
        second_plane.execution_namespace = "another"
        second_plane.execution_id = digest_text("another-execution")
        second = self.adapter(plane=second_plane)
        self.assertEqual(first.host_id, second.host_id)
        self.assertEqual(
            first.provider_identity_digest, second.provider_identity_digest
        )

    def test_project_config_is_execution_local_not_a_capacity_generation(
        self,
    ) -> None:
        second_root = self.root / "project-config-second"
        second_root.mkdir()
        second_plane = FakePlane(second_root)
        second_plane.host_runtime_dir = self.plane.host_runtime_dir
        second_plane.execution_namespace = "project-config-second"
        second_plane.execution_id = digest_text("project-config-second")
        self.server.config_by_cwd = {
            str(self.plane.host_runtime_dir): {
                "model": "provider-default",
                "model_provider": "provider-global",
            },
            str(self.plane.repo_root): {
                "model": "project-a-model",
                "model_provider": "project-a-provider",
            },
            str(second_plane.repo_root): {
                "model": "project-b-model",
                "model_provider": "project-b-provider",
            },
        }

        first = self.adapter()
        second = self.adapter(plane=second_plane, host_id=first.host_id)

        self.assertEqual(first.host_id, second.host_id)
        self.assertEqual(
            first.provider_identity_digest, second.provider_identity_digest
        )
        self.assertNotEqual(first.identity["record_id"], second.identity["record_id"])
        self.assertNotEqual(
            first.execution_config_digest, second.execution_config_digest
        )
        self.assertEqual(first.effective_model, "project-a-model")
        self.assertEqual(second.effective_model, "project-b-model")
        self.assertEqual(first.effective_model_provider, "project-a-provider")
        self.assertEqual(second.effective_model_provider, "project-b-provider")

    def test_caller_cannot_alias_capacity_domain_or_change_environment_roots(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "caller host id differs"
        ):
            self.adapter(host_id="codex-app-server:caller-selected-alias")
        root_a = self.root / "codex-home-a"
        root_b = self.root / "codex-home-b"
        root_a.mkdir()
        root_b.mkdir()
        first = self.adapter(
            environment={"PATH": "isolated-path", "CODEX_HOME": str(root_a)}
        )
        first.close()
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError,
            "identity changed|caller host id differs",
        ):
            self.adapter(
                host_id=first.host_id,
                environment={"PATH": "isolated-path", "CODEX_HOME": str(root_b)},
            )

    def test_provider_identity_binds_hash_only_backend_and_trust_route(self) -> None:
        first = self.adapter(
            environment={
                "PATH": "isolated-path",
                "OPENAI_BASE_URL": "https://api.example.invalid/v1",
                "HTTPS_PROXY": "https://proxy-a.example.invalid",
                "SSL_CERT_FILE": str(self.root / "trust-a.pem"),
            }
        )
        second_root = self.root / "routed-second"
        second_root.mkdir()
        second_plane = FakePlane(second_root)
        second_plane.execution_namespace = "routed-second"
        second_plane.execution_id = digest_text("routed-second")
        second = self.adapter(
            plane=second_plane,
            environment={
                "PATH": "isolated-path",
                "OPENAI_BASE_URL": "https://api.example.invalid/v1",
                "HTTPS_PROXY": "https://proxy-b.example.invalid",
                "SSL_CERT_FILE": str(self.root / "trust-a.pem"),
            },
        )

        self.assertNotEqual(
            first.behavior_environment_digest,
            second.behavior_environment_digest,
        )
        self.assertNotEqual(
            first.provider_identity_digest,
            second.provider_identity_digest,
        )
        serialized = json.dumps(second.identity, sort_keys=True)
        self.assertNotIn("proxy-b", serialized)
        self.assertNotIn("api.example", serialized)

    def test_provider_identity_binds_effective_config_account_and_model(self) -> None:
        codex_home = self.root / "stable-codex-home"
        codex_home.mkdir()
        first = self.adapter(
            environment={"PATH": "isolated-path", "CODEX_HOME": str(codex_home)}
        )
        first_digest = first.provider_identity_digest
        first.close()

        # The installation paths and executable remain byte-identical.  A
        # changed effective config/principal must nevertheless require an
        # explicit provider-generation transition rather than silently changing
        # the model or account behind an installed host identity.
        self.server.config = {
            "model": "gpt-test-next",
            "model_provider": "fixture-provider",
        }
        self.server.account = {
            "account": {
                "type": "chatgpt",
                "email": "other@example.invalid",
                "planType": "team",
            },
            "requiresOpenaiAuth": True,
        }
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "identity changed"
        ):
            self.adapter(
                host_id=first.host_id,
                environment={
                    "PATH": "isolated-path",
                    "CODEX_HOME": str(codex_home),
                },
            )

        second_root = self.root / "changed-provider"
        second_root.mkdir()
        second_plane = FakePlane(second_root)
        changed = self.adapter(
            plane=second_plane,
            host_id=first.host_id,
            environment={"PATH": "isolated-path", "CODEX_HOME": str(codex_home)},
        )
        self.assertNotEqual(first_digest, changed.provider_identity_digest)
        self.assertEqual(changed.effective_model, "gpt-test-next")
        self.assertEqual(changed.effective_model_provider, "fixture-provider")
        created = self.create(changed, "changed-provider-thread")
        self.assertEqual(created["host_id"], changed.host_id)
        start = next(
            item
            for item in reversed(self.server.requests)
            if item["method"] == "thread/start"
        )
        self.assertEqual(start["params"]["model"], "gpt-test-next")
        self.assertEqual(start["params"]["modelProvider"], "fixture-provider")

    def test_thread_create_is_durable_and_idempotently_adopted_after_restart(
        self,
    ) -> None:
        first = self.adapter()
        binding = self.create(first)
        repeated = self.create(first)
        self.assertEqual(binding, repeated)
        self.assertEqual(len(self.server.threads), 1)
        first.close()
        replacement = self.adapter()
        adopted = self.create(replacement)
        self.assertEqual(binding, adopted)
        self.assertEqual(len(self.server.threads), 1)
        starts = [
            item for item in self.server.requests if item["method"] == "thread/start"
        ]
        turns = [
            item for item in self.server.requests if item["method"] == "turn/start"
        ]
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(turns), 1)
        self.assertEqual(starts[0]["params"]["sandbox"], "workspace-write")
        self.assertEqual(turns[0]["params"]["sandboxPolicy"]["type"], "workspaceWrite")
        self.assertIn("clientUserMessageId", turns[0]["params"])

    def test_thread_record_requires_semantic_append_only_history(self) -> None:
        adapter = self.adapter()
        key = digest_text("strict-thread-history")
        binding = self.create(adapter, "strict-thread-history")
        path = adapter._thread_path(key)
        installed = json.loads(path.read_text(encoding="utf-8"))
        history: list[dict[str, object]] = []
        for item in adapter.thread_history_dir.glob("*.json"):
            record = json.loads(item.read_text(encoding="utf-8"))
            if record.get("idempotency_key") == key:
                history.append(record)
        history.sort(key=lambda item: int(item["transition_index"]))
        self.assertGreaterEqual(len(history), 5)
        self.assertEqual(history[-1], installed)

        # A projection rollback is repaired only from the immutable complete
        # history; it never makes the older state authoritative again.
        path.write_bytes(app_server_host._canonical(history[1]) + b"\n")
        self.assertEqual(adapter.lookup_thread(idempotency_key=key), binding)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), installed)

        for state in ("ATTEMPTED", "BOUND", "ARCHIVED"):
            with self.subTest(state=state):
                forged = copy.deepcopy(installed)
                forged["state"] = state
                forged["unobserved_thread_ids"] = []
                if state == "ATTEMPTED":
                    forged["thread_id"] = None
                    forged["turn_id"] = None
                elif state == "BOUND":
                    forged["turn_id"] = "forged-turn"
                material = dict(forged)
                material.pop("record_id")
                forged["record_id"] = digest_object(material)
                path.write_bytes(app_server_host._canonical(forged) + b"\n")
                with self.assertRaisesRegex(
                    app_server_host.AppServerHostError,
                    "immutable lifecycle history|anchored",
                ):
                    adapter._read_thread_record(path)
                path.write_bytes(app_server_host._canonical(installed) + b"\n")

    def test_thread_start_accepted_before_response_is_not_retried(self) -> None:
        adapter = self.adapter()
        self.server.drop_once("thread/start")
        with self.assertRaises(app_server_host.AppServerHostError):
            self.create(adapter, "ambiguous-start")
        self.assertEqual(len(self.server.threads), 1)
        adapter.close()
        replacement = self.adapter()
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "explicit external adjudication"
        ):
            self.create(replacement, "ambiguous-start")
        self.assertEqual(len(self.server.threads), 1)
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "thread/start"
                ]
            ),
            1,
        )
        observation = replacement.read_effect_reconciliation(
            effect_kind="CREATE_THREAD", idempotency_key=digest_text("ambiguous-start")
        )
        self.assertEqual(observation["outcome"], "UNKNOWN")
        self.assertTrue(observation["unobserved_host_lifecycle_items"])
        self.assertIsInstance(observation["external_identity"], dict)
        self.assertIsNone(observation["external_identity"]["external_id"])
        self.server.threads.clear()
        replacement.close()
        final = self.adapter()
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "explicit external adjudication"
        ):
            self.create(final, "ambiguous-start")
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "thread/start"
                ]
            ),
            1,
        )

    def test_observed_multiple_threads_cannot_be_cleared_by_list_shrinkage(
        self,
    ) -> None:
        adapter = self.adapter()
        key = digest_text("multiple-thread-ambiguity")
        token = (
            "hive-"
            + adapter.execution_id.removeprefix("sha256:")[:12]
            + "-"
            + key.removeprefix("sha256:")
        )
        for index in (1, 2):
            thread_id = f"ambiguous-{index}"
            self.server.threads[thread_id] = {
                "id": thread_id,
                "name": f"ambiguous [{token}]",
                "cwd": str(adapter.repo_root),
                "status": {"type": "idle"},
                "turns": [],
            }
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "multiple App Server threads"
        ):
            self.create(adapter, "multiple-thread-ambiguity")
        self.server.archived["ambiguous-2"] = self.server.threads.pop("ambiguous-2")
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "retained ambiguity"
        ):
            self.create(adapter, "multiple-thread-ambiguity")

    def test_thread_start_unknown_is_not_retried_after_external_disappearance(
        self,
    ) -> None:
        adapter = self.adapter()
        self.server.drop_once("thread/start")
        with self.assertRaises(app_server_host.AppServerHostError):
            self.create(adapter, "disappeared-start")
        self.assertEqual(len(self.server.threads), 1)
        # The external host may archive or delete an accepted thread before a
        # replacement controller can observe it. Absence is not non-acceptance.
        self.server.threads.clear()
        adapter.close()

        replacement = self.adapter()
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError, "explicit external adjudication"
        ):
            self.create(replacement, "disappeared-start")
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "thread/start"
                ]
            ),
            1,
        )
        observation = replacement.read_effect_reconciliation(
            effect_kind="CREATE_THREAD",
            idempotency_key=digest_text("disappeared-start"),
        )
        self.assertEqual(observation["outcome"], "UNKNOWN")
        self.assertTrue(observation["unobserved_host_lifecycle_items"])
        self.assertIsNone(observation["external_identity"]["external_id"])

    def test_turn_start_accepted_before_response_is_adopted_without_duplicate(
        self,
    ) -> None:
        adapter = self.adapter()
        self.server.drop_once("turn/start")
        with self.assertRaises(app_server_host.AppServerHostError):
            self.create(adapter, "accepted-turn")
        self.assertEqual(len(self.server.threads), 1)
        thread = next(iter(self.server.threads.values()))
        self.assertEqual(len(thread["turns"]), 1)
        adapter.close()
        replacement = self.adapter()
        binding = self.create(replacement, "accepted-turn")
        self.assertEqual(binding["task_id"], thread["id"])
        self.assertEqual(len(thread["turns"]), 1)
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "turn/start"
                ]
            ),
            1,
        )

    def test_turn_steer_accepted_before_response_is_adopted_without_duplicate(
        self,
    ) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "message-thread")
        self.server.drop_once("turn/steer")
        message_key = digest_text("message")
        with self.assertRaises(app_server_host.AppServerHostError):
            adapter.send_message_to_thread(
                host_id=binding["host_id"],
                task_id=binding["task_id"],
                cursor=binding["cursor"],
                capability=binding["capability"],
                message="Continue with the exact next action.",
                idempotency_key=message_key,
            )
        adapter.close()
        replacement = self.adapter()
        ack = replacement.send_message_to_thread(
            host_id=binding["host_id"],
            task_id=binding["task_id"],
            cursor=binding["cursor"],
            capability=binding["capability"],
            message="Continue with the exact next action.",
            idempotency_key=message_key,
        )
        self.assertTrue(ack["accepted"])
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "turn/steer"
                ]
            ),
            1,
        )
        observed = replacement.read_effect_reconciliation(
            effect_kind="SEND_PRIMARY_MESSAGE", idempotency_key=message_key
        )
        self.assertEqual(observed["outcome"], "COMPLETED")
        self.assertEqual(observed["unobserved_host_lifecycle_items"], [])
        self.assertEqual(
            observed["external_identity"]["external_id"],
            observed["result"]["turn_id"],
        )

    def test_archive_accepted_before_response_is_adopted_without_duplicate(
        self,
    ) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "archive-thread")
        self.server.drop_once("thread/archive")
        with self.assertRaises(app_server_host.AppServerHostError):
            adapter.archive_thread(thread_id=binding["task_id"])
        adapter.close()
        replacement = self.adapter()
        result = replacement.archive_thread(thread_id=binding["task_id"])
        self.assertTrue(result["archived"])
        self.assertIsNone(
            replacement.lookup_thread(idempotency_key=digest_text("archive-thread"))
        )
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "thread/archive"
                ]
            ),
            1,
        )

    def test_lifecycle_observation_is_sealed_fact_not_fixed_point_evidence(
        self,
    ) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "observed-thread")
        frontier = digest_text("frontier")
        first = adapter.capture_lifecycle_observation(
            frontier_id=frontier, disposition="HOST_ACTIVE"
        )
        self.assertEqual(first["active_host_threads"], 1)
        self.assertEqual(first["active_host_turns"], 1)
        self.assertNotIn("fixed_point_evidence", first)
        replay = adapter.read_lifecycle_observation(
            execution_namespace=self.plane.execution_namespace,
            execution_id=self.plane.execution_id,
            execution_dir=self.plane.execution_dir,
            host_id=adapter.host_id,
            frontier_id=frontier,
            observation_id=first["observation_id"],
        )
        self.assertEqual(first, replay)
        self.server.complete(binding["task_id"])
        second = adapter.capture_lifecycle_observation(
            frontier_id=digest_text("terminal-frontier"), disposition="HOST_TERMINAL"
        )
        self.assertEqual(second["active_host_threads"], 0)
        self.assertEqual(second["active_host_turns"], 0)
        release_id = digest_text("release")
        self.plane.release = {"release_id": release_id}
        terminal = adapter.capture_terminal_lifecycle_observation(
            execution_namespace=self.plane.execution_namespace,
            execution_id=self.plane.execution_id,
            execution_dir=self.plane.execution_dir,
            host_id=adapter.host_id,
            frontier_id=digest_text("fixed-point-frontier"),
            release_id=release_id,
        )
        self.assertEqual(terminal["disposition"], "PLAN_QUIESCENT")
        self.assertNotIn("fixed_point_evidence", terminal)
        self.assertEqual(
            terminal,
            adapter.capture_terminal_lifecycle_observation(
                execution_namespace=self.plane.execution_namespace,
                execution_id=self.plane.execution_id,
                execution_dir=self.plane.execution_dir,
                host_id=adapter.host_id,
                frontier_id=digest_text("fixed-point-frontier"),
                release_id=release_id,
            ),
        )

    def test_turn_completed_stream_wakes_wait_and_reports_terminal(self) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "streamed-turn")
        self.server.complete(binding["task_id"])
        adapter.client.wait_notification_change(0, 1.0)
        events = adapter.wait_threads(
            [
                {
                    "host_id": binding["host_id"],
                    "task_id": binding["task_id"],
                    "cursor": binding["cursor"],
                    "capability": binding["capability"],
                    "after_event_cursor": None,
                }
            ]
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["state"], "SUCCEEDED")
        self.assertIn(
            "turn/completed",
            [item["method"] for item in adapter.client.notification_snapshot()],
        )

    def test_restart_can_resume_an_exact_not_loaded_thread(self) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "resumed-thread")
        thread = self.server.threads[binding["task_id"]]
        thread["status"] = {"type": "notLoaded"}
        resumed = adapter.resume_thread(thread_id=binding["task_id"])
        self.assertEqual(resumed["status"], {"type": "idle"})
        self.assertEqual(
            len(
                [
                    item
                    for item in self.server.requests
                    if item["method"] == "thread/resume"
                ]
            ),
            1,
        )

    def test_expired_reservation_is_not_freed_until_lifecycle_is_terminal(self) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "reservation-thread")
        reservation = {
            "reservation_id": digest_text("reservation"),
            # A host-global coordinator must resolve the reservation's exact
            # execution adapter rather than reusing its own adapter instance.
            "execution_id": adapter.execution_id,
            "local_reservation_id": digest_text("local-reservation"),
            "capacity_generation": digest_text("capacity-generation"),
            "host_id": adapter.host_id,
            "reservation_kind": "PRIMARY",
        }
        local = {
            "task_id": binding["task_id"],
            "cursor": binding["cursor"],
            "capability_digest": digest_text(str(binding["capability"])),
        }
        self.assertIsNone(
            adapter.observe_task_lifecycle(
                reservation=reservation,
                local_binding=local,
                idempotency_key=digest_text("active-observation"),
            )
        )
        self.server.complete(binding["task_id"])
        terminal = adapter.observe_task_lifecycle(
            reservation=reservation,
            local_binding=local,
            idempotency_key=digest_text("terminal-observation"),
        )
        assert terminal is not None
        self.assertEqual(terminal["state"], "TERMINAL")
        self.assertEqual(terminal["terminal_state"], "SUCCEEDED")
        self.assertRegex(str(terminal["source_event_id"]), r"^sha256:[0-9a-f]{64}$")

    def test_global_recovery_observes_exact_thread_not_cwd_filtered_absence(
        self,
    ) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "foreign-cwd-reservation-thread")
        reservation = {
            "reservation_id": digest_text("foreign-cwd-reservation"),
            "execution_id": adapter.execution_id,
            "local_reservation_id": digest_text("foreign-cwd-local"),
            "capacity_generation": digest_text("foreign-cwd-capacity"),
            "host_id": adapter.host_id,
            "reservation_kind": "PRIMARY",
        }
        local = {
            "task_id": binding["task_id"],
            "cursor": binding["cursor"],
            "capability_digest": digest_text(str(binding["capability"])),
        }
        self.server.complete(binding["task_id"])
        with mock.patch.object(
            adapter,
            "_list_threads",
            side_effect=AssertionError("cwd-filtered list is not absence authority"),
        ):
            observed = adapter.observe_task_lifecycle(
                reservation=reservation,
                local_binding=local,
                idempotency_key=digest_text("foreign-cwd-observation"),
            )
        assert observed is not None
        self.assertEqual(observed["state"], "TERMINAL")
        self.assertEqual(observed["host_task_id"], binding["task_id"])

    def test_lifecycle_observer_rejects_another_execution_reservation(self) -> None:
        adapter = self.adapter()
        binding = self.create(adapter, "foreign-execution-reservation-thread")
        reservation = {
            "reservation_id": digest_text("foreign-execution-reservation"),
            "execution_id": digest_text("another-execution"),
            "local_reservation_id": digest_text("foreign-execution-local"),
            "capacity_generation": digest_text("foreign-execution-capacity"),
            "host_id": adapter.host_id,
            "reservation_kind": "PRIMARY",
        }
        local = {
            "task_id": binding["task_id"],
            "cursor": binding["cursor"],
            "capability_digest": digest_text(str(binding["capability"])),
        }
        self.server.complete(binding["task_id"])
        with self.assertRaisesRegex(
            app_server_host.AppServerHostError,
            "another execution adapter",
        ):
            adapter.observe_task_lifecycle(
                reservation=reservation,
                local_binding=local,
                idempotency_key=digest_text("foreign-execution-observation"),
            )

    def test_global_recovery_rejects_a_different_thread_read_identity(self) -> None:
        adapter = self.adapter()
        requested = self.create(adapter, "requested-recovery-thread")
        different = self.create(adapter, "different-recovery-thread")
        self.server.complete(different["task_id"])
        reservation = {
            "reservation_id": digest_text("mismatched-thread-reservation"),
            "execution_id": adapter.execution_id,
            "local_reservation_id": digest_text("mismatched-thread-local"),
            "capacity_generation": digest_text("mismatched-thread-capacity"),
            "host_id": adapter.host_id,
            "reservation_kind": "PRIMARY",
        }
        local = {
            "task_id": requested["task_id"],
            "cursor": requested["cursor"],
            "capability_digest": digest_text(str(requested["capability"])),
        }
        original_request = adapter.client.request

        def mismatched_read(method: str, params: object) -> object:
            if method == "thread/read":
                return {
                    "thread": self.server._copy(
                        self.server.threads[different["task_id"]]
                    )
                }
            return original_request(method, params)

        with mock.patch.object(adapter.client, "request", side_effect=mismatched_read):
            observed = adapter.observe_task_lifecycle(
                reservation=reservation,
                local_binding=local,
                idempotency_key=digest_text("mismatched-thread-observation"),
            )

        self.assertIsNone(observed)
        self.assertFalse(
            (
                adapter.reconciliations_dir
                / (
                    "task-"
                    + digest_text("mismatched-thread-observation").removeprefix(
                        "sha256:"
                    )
                    + ".json"
                )
            ).exists()
        )

    def test_sidecar_create_and_close_are_idempotent_lifecycle_effects(self) -> None:
        adapter = self.adapter()
        sidecar_id = digest_text("sidecar")
        binding = adapter.spawn_sidecar(
            prompt="Inspect only the bounded sidecar question.",
            token_budget=1000,
            idempotency_key=sidecar_id,
            parent_launch_instruction_id=digest_text("parent"),
        )
        self.assertEqual(
            binding,
            adapter.spawn_sidecar(
                prompt="Inspect only the bounded sidecar question.",
                token_budget=1000,
                idempotency_key=sidecar_id,
                parent_launch_instruction_id=digest_text("parent"),
            ),
        )
        closed = adapter.close_sidecar(
            host_id=binding["host_id"],
            sidecar_task_id=binding["sidecar_task_id"],
            cursor=binding["cursor"],
            capability=binding["capability"],
            reason="bounded completion",
            idempotency_key=digest_text("sidecar-close"),
        )
        self.assertEqual(closed["state"], "CANCELLED")
        self.assertIsNone(adapter.lookup_sidecar(idempotency_key=sidecar_id))
        adapter.close()
        replacement = self.adapter()
        reconciled = replacement.read_effect_reconciliation(
            effect_kind="CLOSE_SIDECAR",
            idempotency_key=digest_text("sidecar-close"),
        )
        self.assertEqual(reconciled["outcome"], "COMPLETED")
        self.assertEqual(reconciled["result"], closed)
        self.assertEqual(
            reconciled["external_identity"]["external_id"],
            binding["sidecar_task_id"],
        )

    def test_generated_schema_probe_pins_no_idempotency_contract(self) -> None:
        def fake_run(argv, **_kwargs):
            destination = Path(argv[argv.index("--out") + 1])
            target = destination / "v2"
            target.mkdir(parents=True)
            thread = {
                "title": "ThreadStartParams",
                "properties": {
                    "cwd": {},
                    "approvalPolicy": {},
                    "sandbox": {"anyOf": [{"$ref": "#/definitions/SandboxMode"}]},
                    "serviceName": {},
                },
                "definitions": {"SandboxMode": {"enum": ["workspace-write"]}},
            }
            turn = {
                "title": "TurnStartParams",
                "properties": {
                    "threadId": {},
                    "input": {},
                    "cwd": {},
                    "approvalPolicy": {},
                    "sandboxPolicy": {
                        "anyOf": [{"$ref": "#/definitions/SandboxPolicy"}]
                    },
                    "clientUserMessageId": {},
                },
                "definitions": {
                    "SandboxPolicy": {
                        "oneOf": [
                            {"properties": {"type": {"enum": ["workspaceWrite"]}}}
                        ]
                    }
                },
            }
            (target / "ThreadStartParams.json").write_text(
                json.dumps(thread), encoding="utf-8"
            )
            (target / "TurnStartParams.json").write_text(
                json.dumps(turn), encoding="utf-8"
            )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(app_server_host.subprocess, "run", side_effect=fake_run):
            identity = app_server_host._default_schema_probe(
                self.executable, {"PATH": "x"}
            )
        self.assertEqual(
            set(identity),
            {
                "schema_bundle_digest",
                "thread_start_schema_digest",
                "turn_start_schema_digest",
            },
        )

        def bad_run(argv, **kwargs):
            result = fake_run(argv, **kwargs)
            destination = Path(argv[argv.index("--out") + 1])
            path = destination / "v2" / "ThreadStartParams.json"
            schema = json.loads(path.read_text(encoding="utf-8"))
            schema["properties"]["idempotencyKey"] = {}
            path.write_text(json.dumps(schema), encoding="utf-8")
            return result

        with mock.patch.object(app_server_host.subprocess, "run", side_effect=bad_run):
            with self.assertRaisesRegex(
                app_server_host.AppServerHostError,
                "differs from the authenticated adapter contract",
            ):
                app_server_host._default_schema_probe(self.executable, {"PATH": "x"})

    def test_default_resolution_selects_exact_codex_launcher(self) -> None:
        expected_name = "codex.cmd" if app_server_host.os.name == "nt" else "codex"
        with mock.patch.object(
            app_server_host.shutil, "which", return_value=str(self.executable)
        ) as which:
            identity = app_server_host._executable_identity(
                None,
                {"PATH": "isolated-path"},
                lambda _path, _environment: "codex-cli 0.146.0",
            )
        which.assert_called_once_with(expected_name, path="isolated-path")
        self.assertEqual(identity.executable_path, self.executable)
        self.assertEqual(
            identity.executable_digest, digest_bytes(self.executable.read_bytes())
        )
        self.assertEqual(identity.executable_version, "codex-cli 0.146.0")

    def test_executable_replacement_during_process_creation_fails_closed(self) -> None:
        original = self.executable.read_bytes()

        def replacing_factory(argv, cwd, environment):
            process = self.server.process_factory(argv, cwd, environment)
            self.executable.write_bytes(b"replaced-after-authentication")
            return process

        with self.assertRaisesRegex(
            app_server_host.AppServerHostError,
            "changed across App Server process creation|authenticated bytes",
        ):
            self.adapter(process_factory=replacing_factory)
        self.assertTrue(self.server.processes)
        self.assertIsNotNone(self.server.processes[-1].poll())
        self.executable.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
