from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.brain_kernel.authority import AuthorityRegistry, RootProvenance
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import (
    Budget,
    ConstraintEnvelope,
    EffectIntent,
)
from hive_mind_os.brain_kernel.effects import EffectGateway, sealed_intent
from hive_mind_os.cortex.github import grants
from hive_mind_os.cortex.github.delivery_adapter import (
    COMMENT_MARKER_PREFIX,
    ControlledGitHubDelivery,
)
from hive_mind_os.cortex.github.grants import (
    PROTECTED_BRANCHES,
    VALID_DELIVERY_ACTIONS,
    DeliveryGrant,
    DeliveryGrantError,
    DeliveryGrantLedger,
)
from hive_mind_os.cortex.github.push_executor import WorkspacePushExecutor
from hive_mind_os.cortex.github.rest_gateway import (
    ControlledRestGateway,
    DeliveryRestError,
)
from hive_mind_os.git_adapter import GitWorkspace, PinViolation
from hive_mind_os.github_adapter import (
    CheckPollingTimeout,
    CheckRunFailed,
    GitHubClient,
    GitHubDeliveryError,
    GitHubDeliveryTarget,
    GitHubEffectReconciliationRequired,
    GitHubPolicyDenied,
    GitHubResponse,
    GitHubTransportError,
    MissingGitHubCredential,
    PushResult,
    UrllibGitHubTransport,
    validate_github_receipt,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission import RepositoryMission
from hive_mind_os.mission_store import (
    MissionStore,
    SimulatedCrash,
    _system_path,
    _temporary_name,
)
from hive_mind_os.models import AutonomyLevel
from hive_mind_os.policy import PolicyEngine
from tests.fixtures.fixture_repo import COMMIT_TWO_SHA, build_fixture_repo

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "github"
HEAD_SHA = "a" * 40


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeGitHubTransport:
    def __init__(self) -> None:
        self.responses: dict[
            tuple[str, str],
            list[GitHubResponse],
        ] = {}
        self.calls: list[dict[str, object]] = []

    def add(
        self,
        method: str,
        path: str,
        body: bytes,
        *,
        status: int = 200,
    ) -> None:
        self.responses.setdefault((method, path), []).append(
            GitHubResponse(status, body, {})
        )

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> GitHubResponse:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(headers),
                "body": body,
                "timeout_s": timeout_s,
            }
        )
        queue = self.responses.get((method, path))
        if not queue:
            raise AssertionError(f"unexpected GitHub request: {method} {path}")
        response = queue.pop(0)
        if queue:
            return response
        self.responses[(method, path)] = [response]
        return response


class ExplodingTransport:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.calls = 0

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> GitHubResponse:
        self.calls += 1
        raise OSError(f"transport failure carried {self.secret}")


class SingleEffectHost:
    """A queryable fake host that accepts one effect per idempotency key.

    Every answer comes from in-memory state, so nothing here opens a socket.
    A second attempt at an effect key the host already accepted is refused
    loudly: a duplicated remote effect fails the test instead of passing.
    """

    def __init__(
        self,
        *,
        owner: str = "octocat",
        repository: str = "hive-mind-os",
        head_sha: str = HEAD_SHA,
    ) -> None:
        self.owner = owner
        self.prefix = f"/repos/{owner}/{repository}"
        self.head_sha = head_sha
        self.accepted: list[str] = []
        self.refused: list[str] = []
        self.pulls: list[dict[str, Any]] = []
        self.refs: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def accept(self, key: str) -> None:
        if key in self.accepted:
            self.refused.append(key)
            raise AssertionError(f"the host was asked to perform {key} twice")
        self.accepted.append(key)

    def count(self, key: str) -> int:
        return self.accepted.count(key)

    def create_ref(self, branch: str, head_sha: str) -> None:
        self.accept(f"push:{branch}:{head_sha}")
        self.refs[branch] = head_sha

    @staticmethod
    def _response(status: int, payload: object) -> GitHubResponse:
        return GitHubResponse(status, json.dumps(payload).encode(), {})

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> GitHubResponse:
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.calls.append((method, parsed.path))
        if method == "GET" and parsed.path == f"{self.prefix}/pulls":
            branch = query.get("head", [""])[0].removeprefix(f"{self.owner}:")
            return self._response(
                200,
                [pull for pull in self.pulls if pull["head"]["ref"] == branch],
            )
        if method == "POST" and parsed.path == f"{self.prefix}/pulls":
            payload = json.loads(body or b"{}")
            self.accept(f"pull:{payload['head']}:{payload['base']}")
            number = 71 + len(self.pulls)
            pull = {
                "number": number,
                "draft": True,
                "state": "open",
                "html_url": f"https://github.com/{self.owner}/pull/{number}",
                "head": {
                    "ref": payload["head"],
                    "sha": self.refs.get(payload["head"], self.head_sha),
                },
                "base": {"ref": payload["base"]},
            }
            self.pulls.append(pull)
            return self._response(201, pull)
        if method == "GET" and parsed.path.startswith(f"{self.prefix}/git/ref/heads/"):
            branch = parsed.path.removeprefix(f"{self.prefix}/git/ref/heads/")
            head_sha = self.refs.get(branch)
            if head_sha is None:
                return self._response(404, {"message": "Not Found"})
            return self._response(
                200,
                {
                    "ref": f"refs/heads/{branch}",
                    "object": {"sha": head_sha, "type": "commit"},
                },
            )
        raise AssertionError(f"unexpected GitHub request: {method} {url}")


class RecordingWorkspace:
    """Answers the two calls ``push_branch`` makes; it runs no Git command.

    The push lands on the fake host, so an observation can witness it exactly
    the way a REST ref read witnesses a push that really happened.
    """

    def __init__(self, host: SingleEffectHost, head_sha: str = HEAD_SHA) -> None:
        self.host = host
        self.head_sha = head_sha
        self.branch_name = "phase/P07-live-fixture"
        self.receipt_records: list[dict[str, Any]] = []
        self.pushes: list[str] = []

    def _git_text(self, arguments: Any, action: Any, description: str) -> str:
        return self.head_sha

    def push_branch(
        self,
        remote_url: Any,
        token: str,
        *,
        branch: str,
        allow_local: bool = False,
    ) -> str:
        self.pushes.append(branch)
        self.host.create_ref(branch, self.head_sha)
        self.receipt_records.append({"command": "git push", "branch": branch})
        return self.head_sha


def _remove_long_tree(root: Path) -> None:
    """Delete a tree whose paths may exceed MAX_PATH, which rmtree cannot."""

    system_root = _system_path(root)
    if not os.path.isdir(system_root):
        return
    for parent, directories, files in os.walk(system_root, topdown=False):
        for name in files:
            os.remove(os.path.join(parent, name))
        for name in directories:
            os.rmdir(os.path.join(parent, name))
    os.rmdir(system_root)


class LocalDeliveryClient(GitHubClient):
    """Exercise the mission boundary while keeping the push entirely local."""

    def __init__(
        self,
        *args: object,
        transport: FakeGitHubTransport,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, transport=transport, **kwargs)  # type: ignore[arg-type]
        self.local_remote: Path | None = None
        self.fake_transport = transport

    def push_branch(
        self,
        workspace: GitWorkspace,
        *,
        branch: str | None = None,
        remote_url: str | Path | None = None,
        allow_local_test_remote: bool = False,
    ):
        remote = workspace.root / ".git" / "hive-mind-mission-test-remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.local_remote = remote
        result = super().push_branch(
            workspace,
            branch=branch,
            remote_url=Path(".git") / remote.name,
            allow_local_test_remote=True,
        )
        branch_name = result.branch
        query = (
            "/repos/octocat/hive-mind-os/pulls?"
            f"state=open&head=octocat%3A{urllib.parse.quote(branch_name, safe='')}"
            "&base=main"
        )
        self.fake_transport.add("GET", query, b"[]")
        pull = json.loads(_fixture("create-pr.json"))
        pull["head"]["sha"] = result.head_sha
        self.fake_transport.add(
            "POST",
            "/repos/octocat/hive-mind-os/pulls",
            json.dumps(pull).encode(),
            status=201,
        )
        checks = (
            f"/repos/octocat/hive-mind-os/commits/{result.head_sha}/"
            "check-runs?filter=latest&per_page=100"
        )
        complete = json.loads(_fixture("check-complete.json"))
        required_names = json.loads(
            (
                ROOT
                / ".github"
                / "governance"
                / "required-repository-rules.json"
            ).read_text(encoding="utf-8")
        )["rules"]["required_status_checks"]
        templates = complete["check_runs"]
        complete["check_runs"] = [
            {
                **templates[index % len(templates)],
                "id": 501 + index,
                "name": name,
            }
            for index, name in enumerate(required_names)
        ]
        complete["total_count"] = len(complete["check_runs"])
        self.fake_transport.add(
            "GET",
            checks,
            json.dumps(complete).encode(),
        )
        self.fake_transport.add(
            "GET",
            (
                "/repos/octocat/hive-mind-os/rulesets?"
                "includes_parents=true&targets=branch"
            ),
            _fixture("rulesets-list.json"),
        )
        self.fake_transport.add(
            "GET",
            "/repos/octocat/hive-mind-os/rulesets/42",
            _fixture("ruleset-detail.json"),
        )
        self.fake_transport.add(
            "GET",
            "/repos/octocat/hive-mind-os/branches/main/protection",
            _fixture("protection.json"),
        )
        return result


class GitHubAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.token = "fixture-github-token-value"
        self.environment = patch.dict(
            os.environ,
            {"GITHUB_TOKEN": self.token},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = MissionStore(self.root / "state")
        self.addCleanup(self.store.close)
        self.mission_id = "mission-p07-fixture"
        self.store.register_mission(
            self.mission_id,
            {
                "objective": "deliver one draft PR",
                "source_pack_fingerprint": f"sha256:{'1' * 64}",
            },
            AutonomyBudget(100, 100, 100.0),
        )

    def forbid_sockets(self) -> None:
        """Any socket this test creates is a failure, not a slow test."""

        def refuse(*arguments: object, **keywords: object) -> None:
            raise AssertionError("this test must not open a network connection")

        guard = patch("socket.socket", refuse)
        guard.start()
        self.addCleanup(guard.stop)

    def client(
        self,
        transport: object,
        *,
        policy: PolicyEngine | None = None,
        ledger: EvidenceLedger | None = None,
        evidence_root: Path | None = None,
        sleep=lambda _seconds: None,
    ) -> GitHubClient:
        return GitHubClient(
            "octocat",
            "hive-mind-os",
            evidence_root or self.root / "github-evidence",
            transport=transport,  # type: ignore[arg-type]
            policy=policy or PolicyEngine(AutonomyLevel.REPOSITORY),
            ledger=ledger,
            mission_store=self.store,
            mission_id=self.mission_id,
            sleep=sleep,
            clock=lambda: "2026-07-27T20:03:00Z",
        )

    @staticmethod
    def pulls_query() -> str:
        return (
            "/repos/octocat/hive-mind-os/pulls?"
            "state=open&head=octocat%3Aphase%2FP07-live-fixture&base=main"
        )

    def add_pr_routes(self, transport: FakeGitHubTransport) -> None:
        transport.add("GET", self.pulls_query(), b"[]")
        transport.add(
            "POST",
            "/repos/octocat/hive-mind-os/pulls",
            _fixture("create-pr.json"),
            status=201,
        )

    def test_draft_pr_request_and_response_are_head_bound(self) -> None:
        transport = FakeGitHubTransport()
        self.add_pr_routes(transport)
        result = self.client(transport).open_draft_pr(
            branch="phase/P07-live-fixture",
            base="main",
            head_sha=HEAD_SHA,
            title="P07 live delivery",
            body="Draft evidence only.",
        )
        self.assertEqual(result.number, 71)
        self.assertTrue(result.draft)
        self.assertEqual(result.head_sha, HEAD_SHA)
        request = next(
            call for call in transport.calls if call["method"] == "POST"
        )
        payload = json.loads(request["body"])  # type: ignore[arg-type]
        self.assertEqual(
            payload,
            {
                "base": "main",
                "body": "Draft evidence only.",
                "draft": True,
                "head": "phase/P07-live-fixture",
                "maintainer_can_modify": False,
                "title": "P07 live delivery",
            },
        )
        self.assertTrue(
            validate_github_receipt(
                self.root / "github-evidence",
                result.receipt,
            )
        )

    def test_default_transport_keeps_tls_chain_and_hostname_validation(self) -> None:
        transport = UrllibGitHubTransport()
        self.assertTrue(transport.context.check_hostname)
        self.assertEqual(transport.context.verify_mode, ssl.CERT_REQUIRED)
        strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
        if strict:
            self.assertEqual(transport.context.verify_flags & strict, 0)

    def test_pr_creation_is_durable_and_idempotent(self) -> None:
        transport = FakeGitHubTransport()
        self.add_pr_routes(transport)
        client = self.client(transport)
        arguments = {
            "branch": "phase/P07-live-fixture",
            "base": "main",
            "head_sha": HEAD_SHA,
            "title": "P07 live delivery",
            "body": "Draft evidence only.",
        }
        first = client.open_draft_pr(**arguments)
        second = client.open_draft_pr(**arguments)
        self.assertEqual(first, second)
        self.assertEqual(
            sum(call["method"] == "POST" for call in transport.calls),
            1,
        )
        self.assertEqual(self.store.idempotency_count(self.mission_id), 1)

    def draft_pr_arguments(self) -> dict[str, str]:
        return {
            "branch": "phase/P07-live-fixture",
            "base": "main",
            "head_sha": HEAD_SHA,
            "title": "P07 live delivery",
            "body": "Draft evidence only.",
        }

    def interrupt_receipt_write(self):
        """Kill the run exactly between the remote effect and its receipt."""

        return patch.object(
            self.store,
            "write_effect_receipt",
            side_effect=SimulatedCrash("interrupted before the receipt was written"),
        )

    def test_an_interrupted_draft_pr_is_reconciled_not_reissued(self) -> None:
        self.forbid_sockets()
        host = SingleEffectHost()
        client = self.client(host)
        arguments = self.draft_pr_arguments()
        effect = "pull:phase/P07-live-fixture:main"
        with self.interrupt_receipt_write():
            with self.assertRaises(SimulatedCrash):
                client.open_draft_pr(**arguments)
        # The effect fired; its receipt did not survive the interruption.
        self.assertEqual(1, host.count(effect))
        self.assertEqual(
            1,
            len(self.store.unreconciled_effects(self.mission_id)),
        )

        with patch.object(
            self.store, "reconcile_effect", wraps=self.store.reconcile_effect
        ) as reconciled, patch.object(
            self.store, "begin_effect", wraps=self.store.begin_effect
        ) as claimed:
            resumed = client.open_draft_pr(**arguments)

        # The outcome was adopted against the write-ahead record, and the
        # effect was never claimed for a second execution.
        self.assertEqual(1, reconciled.call_count)
        self.assertEqual(0, claimed.call_count)
        self.assertEqual(71, resumed.number)
        self.assertEqual(HEAD_SHA, resumed.head_sha)
        self.assertEqual(1, host.count(effect))
        self.assertEqual([], host.refused)
        self.assertEqual(1, sum(method == "POST" for method, _ in host.calls))
        self.assertEqual([], self.store.unreconciled_effects(self.mission_id))
        self.assertEqual(1, self.store.idempotency_count(self.mission_id))
        self.assertTrue(
            validate_github_receipt(self.root / "github-evidence", resumed.receipt)
        )

    def test_an_interrupted_push_is_reconciled_from_the_observed_ref(self) -> None:
        self.forbid_sockets()
        host = SingleEffectHost()
        workspace = RecordingWorkspace(host)
        client = self.client(host)
        with self.interrupt_receipt_write():
            with self.assertRaises(SimulatedCrash):
                client.push_branch(workspace, branch="phase/P07-live-fixture")
        self.assertEqual(["phase/P07-live-fixture"], workspace.pushes)

        resumed = client.push_branch(workspace, branch="phase/P07-live-fixture")

        self.assertEqual(HEAD_SHA, resumed.head_sha)
        self.assertEqual("phase/P07-live-fixture", resumed.branch)
        # The ref read witnessed the push; the push itself never happened twice.
        self.assertEqual(["phase/P07-live-fixture"], workspace.pushes)
        self.assertEqual([], host.refused)
        self.assertIn(
            ("GET", "/repos/octocat/hive-mind-os/git/ref/heads/phase/P07-live-fixture"),
            host.calls,
        )
        self.assertEqual([], self.store.unreconciled_effects(self.mission_id))

    def test_an_unwitnessed_interrupted_effect_refuses_to_fire_again(self) -> None:
        self.forbid_sockets()
        host = SingleEffectHost()
        workspace = RecordingWorkspace(host)
        client = self.client(host)
        with self.interrupt_receipt_write():
            with self.assertRaises(SimulatedCrash):
                client.push_branch(workspace, branch="phase/P07-live-fixture")
        host.refs.clear()

        with self.assertRaises(GitHubEffectReconciliationRequired):
            client.push_branch(workspace, branch="phase/P07-live-fixture")

        self.assertEqual(["phase/P07-live-fixture"], workspace.pushes)
        self.assertEqual(
            1,
            len(self.store.unreconciled_effects(self.mission_id)),
        )

    def test_receipts_are_written_beyond_max_path(self) -> None:
        self.forbid_sockets()
        deep = self.root / ("d" * 200)
        self.addCleanup(_remove_long_tree, deep)
        transport = FakeGitHubTransport()
        self.add_pr_routes(transport)

        result = self.client(transport, evidence_root=deep).open_draft_pr(
            **self.draft_pr_arguments()
        )

        receipt = deep / Path(*result.receipt["path"].split("/"))
        self.assertGreater(len(str(receipt)), 260)
        self.assertTrue(os.path.isfile(_system_path(receipt)))
        with open(_system_path(receipt), "rb") as stream:
            stored = stream.read()
        self.assertEqual(
            result.receipt["digest"],
            "sha256:" + hashlib.sha256(stored).hexdigest(),
        )

    def test_a_receipt_written_beyond_max_path_still_validates(self) -> None:
        self.forbid_sockets()
        deep = self.root / ("d" * 200)
        self.addCleanup(_remove_long_tree, deep)
        transport = FakeGitHubTransport()
        self.add_pr_routes(transport)

        result = self.client(transport, evidence_root=deep).open_draft_pr(
            **self.draft_pr_arguments()
        )

        receipt = deep / Path(*result.receipt["path"].split("/"))
        self.assertGreater(len(str(receipt)), 260)
        self.assertFalse(receipt.is_file())
        self.assertTrue(validate_github_receipt(deep, result.receipt))

    def test_a_receipt_temporary_name_never_outgrows_its_final_name(self) -> None:
        self.forbid_sockets()
        transport = FakeGitHubTransport()
        self.add_pr_routes(transport)
        renames: list[tuple[str, str]] = []
        real_replace = os.replace

        def recording_replace(source: Any, target: Any) -> None:
            renames.append((os.path.basename(source), os.path.basename(target)))
            real_replace(source, target)

        with patch("hive_mind_os.github_adapter.os.replace", recording_replace):
            self.client(transport).open_draft_pr(**self.draft_pr_arguments())

        self.assertTrue(renames)
        for temporary, final in renames:
            self.assertLessEqual(len(temporary), len(final))
        self.assertLessEqual(len(_temporary_name("a" * 64 + ".json")), 69)

    def test_check_polling_transitions_and_persists_external_receipts(self) -> None:
        transport = FakeGitHubTransport()
        path = (
            f"/repos/octocat/hive-mind-os/commits/{HEAD_SHA}/"
            "check-runs?filter=latest&per_page=100"
        )
        transport.add("GET", path, _fixture("check-pending.json"))
        transport.add("GET", path, _fixture("check-complete.json"))
        pauses: list[float] = []
        results = self.client(
            transport,
            sleep=pauses.append,
        ).poll_checks(
            HEAD_SHA,
            required_check_names=(
                "unit-tests (Python 3.12)",
                "static-and-type-checks",
            ),
            max_attempts=3,
            interval_s=0.25,
        )
        self.assertEqual(pauses, [0.25])
        self.assertEqual(len(results), 2)
        self.assertEqual({item.workflow_run_id for item in results}, {9001})
        self.assertTrue(all(item.conclusion == "success" for item in results))
        self.assertTrue(
            all(
                validate_github_receipt(
                    self.root / "github-evidence",
                    item.receipt,
                )
                for item in results
            )
        )
        expected = json.loads(_fixture("check-complete.json"))["check_runs"]
        self.assertEqual(
            [item.json_digest for item in results],
            [
                "sha256:"
                + __import__("hashlib").sha256(
                    json.dumps(
                        check,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                for check in expected
            ],
        )

    def test_code_scanning_run_url_is_receipted(self) -> None:
        transport = FakeGitHubTransport()
        path = (
            f"/repos/octocat/hive-mind-os/commits/{HEAD_SHA}/"
            "check-runs?filter=latest&per_page=100"
        )
        document = json.loads(_fixture("check-complete.json"))
        check = document["check_runs"][0]
        check["id"] = 90154969167
        check["name"] = "CodeQL"
        check["details_url"] = (
            "https://github.com/octocat/hive-mind-os/runs/90154969167"
        )
        document["check_runs"] = [check]
        transport.add("GET", path, json.dumps(document).encode())
        result = self.client(transport).poll_checks(
            HEAD_SHA,
            required_check_names=("CodeQL",),
            max_attempts=1,
            interval_s=0,
        )
        self.assertEqual(result[0].workflow_run_id, 90154969167)
        self.assertEqual(
            result[0].workflow_run_url,
            "https://github.com/octocat/hive-mind-os/runs/90154969167",
        )

    def test_check_timeout_fails_closed_with_failed_observation(self) -> None:
        transport = FakeGitHubTransport()
        path = (
            f"/repos/octocat/hive-mind-os/commits/{HEAD_SHA}/"
            "check-runs?filter=latest&per_page=100"
        )
        transport.add("GET", path, _fixture("check-pending.json"))
        with self.assertRaises(CheckPollingTimeout) as captured:
            self.client(transport).poll_checks(
                HEAD_SHA,
                required_check_names=(
                    "unit-tests (Python 3.12)",
                    "static-and-type-checks",
                    "secret-scan",
                ),
                max_attempts=2,
                interval_s=0,
            )
        self.assertIn("missing=secret-scan", str(captured.exception))
        self.assertIn(
            "nonterminal=static-and-type-checks, unit-tests (Python 3.12)",
            str(captured.exception),
        )
        receipt_path = (
            self.root
            / "github-evidence"
            / Path(*captured.exception.receipt["path"].split("/"))
        )
        document = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(document["result"], "failed")
        self.assertEqual(len(transport.calls), 2)

    def test_check_polling_waits_for_late_required_check(self) -> None:
        transport = FakeGitHubTransport()
        path = (
            f"/repos/octocat/hive-mind-os/commits/{HEAD_SHA}/"
            "check-runs?filter=latest&per_page=100"
        )
        first = json.loads(_fixture("check-complete.json"))
        first["check_runs"] = first["check_runs"][:1]
        first["total_count"] = 1
        late = json.loads(_fixture("check-complete.json"))
        late["check_runs"][1]["conclusion"] = "failure"
        transport.add("GET", path, json.dumps(first).encode())
        transport.add("GET", path, json.dumps(late).encode())

        with self.assertRaisesRegex(
            CheckRunFailed,
            "GitHub checks failed: static-and-type-checks",
        ):
            self.client(transport).poll_checks(
                HEAD_SHA,
                required_check_names=(
                    "unit-tests (Python 3.12)",
                    "static-and-type-checks",
                ),
                max_attempts=2,
                interval_s=0,
            )
        self.assertEqual(len(transport.calls), 2)

    def test_token_never_persists_or_escapes_errors(self) -> None:
        fixture = build_fixture_repo(self.root / "fixture-parent")
        workspace = GitWorkspace.materialize(
            fixture.root,
            COMMIT_TWO_SHA,
            self.root / "workspace",
            self.root / "git-evidence",
        )
        workspace.create_branch("phase/P07-live-fixture")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        workspace.commit("fix: restore increment")
        bare = workspace.root / ".git" / "hive-mind-test-remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(bare)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ledger = EvidenceLedger(self.root / "ledger.sqlite3")
        self.addCleanup(ledger.close)
        result = self.client(
            FakeGitHubTransport(),
            ledger=ledger,
        ).push_branch(
            workspace,
            branch="phase/P07-live-fixture",
            remote_url=Path(".git") / bare.name,
            allow_local_test_remote=True,
        )
        self.assertEqual(
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(bare),
                    "rev-parse",
                    "refs/heads/phase/P07-live-fixture",
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip(),
            result.head_sha,
        )
        self.assertNotIn(
            self.token,
            (workspace.root / ".git" / "config").read_text(encoding="utf-8"),
        )
        for base in (
            workspace.container_root,
            workspace.trusted_root,
            self.root / "github-evidence",
        ):
            for path in base.rglob("*"):
                if path.is_file():
                    self.assertNotIn(
                        self.token.encode(),
                        path.read_bytes(),
                        str(path),
                    )
        self.assertNotIn(
            self.token,
            json.dumps(ledger.events(self.mission_id), sort_keys=True),
        )

        exploding = ExplodingTransport(self.token)
        with self.assertRaises(GitHubTransportError) as captured:
            self.client(exploding).open_draft_pr(
                branch="phase/another",
                base="main",
                head_sha=HEAD_SHA,
                title="safe title",
                body="safe body",
            )
        self.assertNotIn(self.token, str(captured.exception))
        self.assertEqual(exploding.calls, 1)

    def add_protection_routes(
        self,
        transport: FakeGitHubTransport,
        detail: bytes | None = None,
    ) -> None:
        transport.add(
            "GET",
            (
                "/repos/octocat/hive-mind-os/rulesets?"
                "includes_parents=true&targets=branch"
            ),
            _fixture("rulesets-list.json"),
        )
        transport.add(
            "GET",
            "/repos/octocat/hive-mind-os/rulesets/42",
            detail or _fixture("ruleset-detail.json"),
        )
        transport.add(
            "GET",
            "/repos/octocat/hive-mind-os/branches/main/protection",
            _fixture("protection.json"),
        )

    def test_protection_match_and_mismatch_are_evidenced(self) -> None:
        matching = FakeGitHubTransport()
        self.add_protection_routes(matching)
        report = self.client(matching).verify_protection(
            ROOT / ".github" / "governance" / "required-repository-rules.json"
        )
        self.assertTrue(report.matches, report.mismatches)
        self.assertTrue(
            (self.root / "github-evidence" / report.evidence_path).is_file()
        )

        detail = json.loads(_fixture("ruleset-detail.json"))
        detail["rules"] = [
            rule
            for rule in detail["rules"]
            if rule["type"] != "required_signatures"
        ]
        protection = json.loads(_fixture("protection.json"))
        protection["required_signatures"]["enabled"] = False
        mismatch = FakeGitHubTransport()
        self.add_protection_routes(
            mismatch,
            json.dumps(detail).encode(),
        )
        mismatch.responses[
            (
                "GET",
                "/repos/octocat/hive-mind-os/branches/main/protection",
            )
        ] = [GitHubResponse(200, json.dumps(protection).encode(), {})]
        report = self.client(mismatch).verify_protection(
            ROOT / ".github" / "governance" / "required-repository-rules.json"
        )
        self.assertFalse(report.matches)
        self.assertIn("rules.required_signed_commits: mismatch", report.mismatches)

    def test_ruleset_branch_exclusion_and_malformed_conditions_fail_closed(
        self,
    ) -> None:
        detail = json.loads(_fixture("ruleset-detail.json"))
        detail["conditions"]["ref_name"] = {
            "include": ["~DEFAULT_BRANCH"],
            "exclude": ["refs/heads/main"],
        }
        observed = GitHubClient._ruleset_observation([detail], "main")
        self.assertFalse(observed["active"])

        for malformed in (
            None,
            {},
            {"ref_name": {"include": ["~DEFAULT_BRANCH"]}},
            {
                "ref_name": {
                    "include": ["~DEFAULT_BRANCH"],
                    "exclude": ["refs/heads/release-*"],
                }
            },
        ):
            with self.subTest(conditions=malformed):
                detail["conditions"] = malformed
                observed = GitHubClient._ruleset_observation([detail], "main")
                self.assertFalse(observed["active"])

    def test_lower_authority_denies_before_push_or_pr(self) -> None:
        transport = FakeGitHubTransport()
        ledger = EvidenceLedger()
        self.addCleanup(ledger.close)
        client = self.client(
            transport,
            policy=PolicyEngine(AutonomyLevel.SANDBOX),
            ledger=ledger,
        )
        with self.assertRaises(GitHubPolicyDenied):
            client.open_draft_pr(
                branch="phase/P07-live-fixture",
                base="main",
                head_sha=HEAD_SHA,
                title="denied",
                body="denied",
            )
        self.assertEqual(transport.calls, [])
        decisions = [
            event
            for event in ledger.events(self.mission_id)
            if event["event_type"] == "policy.decision"
        ]
        self.assertEqual(len(decisions), 1)
        self.assertFalse(decisions[0]["payload"]["allowed"])

    def test_remote_materialization_is_explicit_and_github_only(self) -> None:
        for url, allow_remote in (
            ("https://github.com/octocat/hive-mind-os.git", False),
            ("https://example.com/octocat/hive-mind-os.git", True),
            ("https://user:secret@github.com/octocat/hive-mind-os.git", True),
            ("http://github.com/octocat/hive-mind-os.git", True),
        ):
            with self.subTest(url=url, allow_remote=allow_remote):
                with self.assertRaises(PinViolation):
                    GitWorkspace.materialize(
                        url,
                        HEAD_SHA,
                        self.root / f"workspace-{len(url)}-{allow_remote}",
                        self.root / f"evidence-{len(url)}-{allow_remote}",
                        allow_remote=allow_remote,
                    )

    def test_repository_mission_delivers_after_curator_adoption(self) -> None:
        fixture = build_fixture_repo(self.root / "mission-fixture")
        mission_id = "mission-p07-integration"
        store = MissionStore(self.root / "mission-state")
        self.addCleanup(store.close)
        transport = FakeGitHubTransport()
        evidence = store.mission_root(mission_id) / "staging" / "evidence"
        client = LocalDeliveryClient(
            "octocat",
            "hive-mind-os",
            evidence,
            transport=transport,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            mission_store=store,
            mission_id=mission_id,
            sleep=lambda _seconds: None,
        )
        report = asyncio.run(
            RepositoryMission(
                fixture.root,
                "Fix the failing test",
                acceptance_criteria=("increment(1) returns 2",),
                acceptance_specifications=(
                    AcceptanceSpecification(
                        "increment-returns-two",
                        "increment(1) returns 2",
                        (
                            sys.executable,
                            "-B",
                            "-c",
                            "from tiny_pkg.maths import increment; assert increment(1) == 2",
                        ),
                    ),
                ),
                pin=fixture.commit_two,
                output_dir=self.root / "mission-output",
                policy=PolicyEngine(AutonomyLevel.REPOSITORY),
                mission_store=store,
                github_delivery=GitHubDeliveryTarget(
                    client,
                    "main",
                    "P07 offline mission integration",
                    "Draft evidence only.",
                    ROOT
                    / ".github"
                    / "governance"
                    / "required-repository-rules.json",
                    max_check_attempts=1,
                    check_interval_s=0,
                ),
                _run_id=mission_id,
            ).run()
        )
        self.assertEqual(report.curator_verdict, "adopt")
        self.assertIsNotNone(report.github_delivery)
        self.assertTrue(report.github_delivery["draft"])
        self.assertIn("github.delivery.completed", report.event_types)
        self.assertIsNotNone(client.local_remote)
        self.assertEqual(
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(client.local_remote),
                    "rev-parse",
                    "refs/heads/phase/mission-delivery",
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip(),
            report.head_sha,
        )


R2_OWNER = "octocat"
R2_REPOSITORY = "hive-mind-os"
R2_TARGET = f"github/{R2_OWNER}/{R2_REPOSITORY}"
R2_FULL_NAME = f"{R2_OWNER}/{R2_REPOSITORY}"
R2_BASE = "main"
R2_PREFIX = "autopilot/"
R2_BRANCH = "autopilot/a4-800"
R2_PULL = 71
R2_DIGEST = "sha256:" + "0" * 64
R2_TIME = "2030-01-01T00:00:00Z"
R2_ACTIONS = (
    "push",
    "open_draft_pr",
    "post_comment",
    "close_own_pr",
    "delete_own_branch",
)


def _r2_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-a4-800",
        "MISSION-a4-800",
        "WORK-a4-800",
        None,
        "builder",
        "R1",
        R2_ACTIONS,
        ("merge", "deploy"),
        ("workspace",),
        ("workspace", R2_TARGET),
        (),
        (),
        (),
        (),
        Budget(30, 0, 0, 0, 0, 0, 1, 1),
        "2030-01-02T00:00:00Z",
        R2_DIGEST,
        R2_DIGEST,
    ).sealed()


R2_AUTH = _r2_envelope().digest_value


def _mint_root(registry: AuthorityRegistry, envelope: ConstraintEnvelope) -> None:
    registry.mint_root(
        envelope,
        issuer="owner:a4-800-fixture",
        authority_ref="AUTHORITY-RECORD-a4-800",
        recorded_at="2026-01-01T00:00:00Z",
    )


def _r2_owner_authority() -> RootProvenance:
    """The owner authority every R2 grant is issued under.

    ``mint_root`` is deterministic over its inputs, so each call reproduces the
    same ``record_digest`` the ledger was anchored to.
    """

    return AuthorityRegistry().mint_root(
        _r2_envelope(),
        issuer="repository-owner:a4-800",
        authority_ref="OWNER-DELEGATION-a4-800",
        recorded_at="2026-01-01T00:00:00Z",
    )


def _anchor_delivery_ledger(case: unittest.TestCase) -> RootProvenance:
    """A5-F6: anchor a fresh process ledger before any grant is issued."""

    case.addCleanup(setattr, grants, "LEDGER", grants.LEDGER)
    grants.LEDGER = DeliveryGrantLedger()
    return grants.LEDGER.anchor(_r2_owner_authority())


class RecordingPushExecutor:
    """Records branch names; it opens no socket and runs no command."""

    def __init__(self) -> None:
        self.branches: list[str] = []

    def push(self, branch: str) -> str:
        self.branches.append(branch)
        return HEAD_SHA


class ControlledRetractionTests(unittest.TestCase):
    """R2: a pilot that can push and open a draft PR can also retract both.

    A4-800's Path B stop-and-rollback needs ``close-own-pr`` and
    ``delete-own-branch``.  Every request below is answered by the same
    in-process ``FakeGitHubTransport`` the rest of this module uses; it raises
    on any request no test scripted, so a code path that reached an unexpected
    endpoint fails loudly rather than silently.  Nothing here opens a socket.
    """

    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "fixture-github-token-value"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        def refuse(*arguments: object, **keywords: object) -> None:
            raise AssertionError("this test must not open a network connection")

        sockets = patch("socket.socket", refuse)
        sockets.start()
        self.addCleanup(sockets.stop)
        self.owner_authority = _anchor_delivery_ledger(self)
        self.registry = AuthorityRegistry()
        _mint_root(self.registry, self.envelope())
        self.transport = FakeGitHubTransport()
        self.delivery = self.delivery_for(self.transport)

    # -- fixtures ----------------------------------------------------------

    @staticmethod
    def envelope() -> ConstraintEnvelope:
        return _r2_envelope()

    @staticmethod
    def grant(
        *,
        grant_id: str = "GRANT-a4-800",
        base_branch: str = R2_BASE,
        branch_prefix: str = R2_PREFIX,
        allowed_actions: tuple[str, ...] = R2_ACTIONS,
    ) -> DeliveryGrant:
        return DeliveryGrant.issue(
            grant_id=grant_id,
            owner=R2_OWNER,
            repository=R2_REPOSITORY,
            base_branch=base_branch,
            branch_prefix=branch_prefix,
            allowed_actions=allowed_actions,
            issued_at=R2_TIME,
            provenance=_r2_owner_authority(),
        )

    def delivery_for(
        self,
        transport: FakeGitHubTransport,
        *,
        grant: DeliveryGrant | None = None,
    ) -> ControlledGitHubDelivery:
        return ControlledGitHubDelivery(
            grant or self.grant(),
            rest=ControlledRestGateway(
                R2_OWNER,
                R2_REPOSITORY,
                transport=transport,  # type: ignore[arg-type]
            ),
            push_executor=RecordingPushExecutor(),
        )

    @staticmethod
    def intent(
        *,
        action: str,
        adapter: str,
        parameters_digest: str,
        target: str = R2_TARGET,
    ) -> EffectIntent:
        return sealed_intent(EffectIntent(
            "MISSION-a4-800",
            "WORK-a4-800",
            "ATTEMPT-a4-800",
            "builder-1",
            "builder",
            action,
            "R1",
            adapter,
            target,
            parameters_digest,
            R2_DIGEST,
            R2_AUTH,
            ("the pilot opened this draft pull request",),
            "reopen the draft pull request and restore the branch",
            "POLICY-a4-800",
            R2_DIGEST,
        ))

    def execute(
        self,
        intent: EffectIntent,
        action: str,
        delivery: ControlledGitHubDelivery | None = None,
    ):
        gateway = EffectGateway(authority=self.registry, clock=lambda: R2_TIME)
        (delivery or self.delivery).register_with(gateway)
        token = self.registry.authorize(R2_AUTH, action, R2_TARGET, now=R2_TIME)
        return gateway.execute(intent, token)

    @staticmethod
    def pull_path() -> str:
        return f"/repos/{R2_OWNER}/{R2_REPOSITORY}/pulls/{R2_PULL}"

    @staticmethod
    def repository_path() -> str:
        return f"/repos/{R2_OWNER}/{R2_REPOSITORY}"

    @staticmethod
    def branch_path(branch: str) -> str:
        return f"/repos/{R2_OWNER}/{R2_REPOSITORY}/git/refs/heads/{branch}"

    @staticmethod
    def pull_document(**overrides: Any) -> dict[str, Any]:
        """The draft pull request this pilot itself would have opened."""

        document: dict[str, Any] = {
            "number": R2_PULL,
            "state": "open",
            "draft": True,
            "html_url": f"https://github.com/{R2_FULL_NAME}/pull/{R2_PULL}",
            "base": {"ref": R2_BASE},
            "head": {"ref": R2_BRANCH, "repo": {"full_name": R2_FULL_NAME}},
        }
        document.update(overrides)
        return document

    def close_intent(self, delivery: ControlledGitHubDelivery) -> EffectIntent:
        return self.intent(
            action="close_own_pr",
            adapter=ControlledGitHubDelivery.CLOSE_PR_ADAPTER,
            parameters_digest=delivery.bind_parameters({"pull_number": R2_PULL}),
        )

    def delete_intent(
        self, delivery: ControlledGitHubDelivery, branch: str
    ) -> EffectIntent:
        return self.intent(
            action="delete_own_branch",
            adapter=ControlledGitHubDelivery.DELETE_BRANCH_ADAPTER,
            parameters_digest=delivery.bind_parameters({"branch": branch}),
        )

    def methods(self, transport: FakeGitHubTransport) -> list[object]:
        return [call["method"] for call in transport.calls]

    def script_successful_close(self, transport: FakeGitHubTransport) -> None:
        transport.add(
            "GET",
            self.pull_path(),
            json.dumps(self.pull_document()).encode(),
        )
        transport.add(
            "PATCH",
            self.pull_path(),
            json.dumps(
                self.pull_document(state="closed", merged=False, merged_at=None)
            ).encode(),
        )

    # -- close-own-pr ------------------------------------------------------

    def test_close_own_draft_pr_succeeds_and_issues_a_state_only_patch(self) -> None:
        self.script_successful_close(self.transport)

        result = self.execute(self.close_intent(self.delivery), "close_own_pr")

        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual(["GET", "PATCH"], self.methods(self.transport))
        read, closed = self.transport.calls
        self.assertEqual(self.pull_path(), read["path"])
        self.assertIsNone(read["body"])
        self.assertEqual(self.pull_path(), closed["path"])
        self.assertEqual(
            {"state": "closed"},
            json.loads(closed["body"]),  # type: ignore[arg-type]
        )

    def test_close_own_pr_receipt_identifies_the_pull_request_and_branch(self) -> None:
        self.script_successful_close(self.transport)
        intent = self.close_intent(self.delivery)

        outcome = self.delivery.close_pr_adapter(intent)

        self.assertEqual(
            (f"pr:{R2_PULL}", f"branch:{R2_BRANCH}"),
            outcome["produced_identifiers"],
        )
        self.assertEqual(
            canonical_digest({"pr": R2_PULL, "state": "closed"}),
            outcome["postcondition_digest"],
        )

    def test_closing_a_pull_request_this_pilot_did_not_open_is_refused(self) -> None:
        foreign = {
            "head branch outside the granted prefix": {
                "head": {
                    "ref": "release/hive-mind-os-singleton",
                    "repo": {"full_name": R2_FULL_NAME},
                }
            },
            "head branch is the grant base branch": {
                "head": {"ref": R2_BASE, "repo": {"full_name": R2_FULL_NAME}}
            },
            "head branch is a protected branch": {
                "head": {"ref": "master", "repo": {"full_name": R2_FULL_NAME}}
            },
            "head lives in somebody else's fork": {
                "head": {
                    "ref": R2_BRANCH,
                    "repo": {"full_name": "somebody-else/hive-mind-os"},
                }
            },
            "head repository is unreadable": {"head": {"ref": R2_BRANCH}},
            "head reference is unreadable": {
                "head": {"repo": {"full_name": R2_FULL_NAME}}
            },
            "base is not the granted base branch": {"base": {"ref": "release/train"}},
            "pull request is not a draft": {"draft": False},
            "pull request is already closed": {"state": "closed"},
        }
        for label, override in foreign.items():
            with self.subTest(case=label):
                transport = FakeGitHubTransport()
                delivery = self.delivery_for(transport)
                transport.add(
                    "GET",
                    self.pull_path(),
                    json.dumps(self.pull_document(**override)).encode(),
                )

                with self.assertRaises(DeliveryGrantError):
                    self.execute(
                        self.close_intent(delivery), "close_own_pr", delivery
                    )

                # The read happened; the state change never did.
                self.assertEqual(["GET"], self.methods(transport))

    def test_closing_never_reaches_a_pull_request_integration_endpoint(self) -> None:
        self.script_successful_close(self.transport)

        self.execute(self.close_intent(self.delivery), "close_own_pr")

        self.assertEqual({"GET", "PATCH"}, set(self.methods(self.transport)))
        for call in self.transport.calls:
            path = str(call["path"])
            self.assertNotIn("/merge", path)
            self.assertNotIn("/merges", path)
            self.assertNotEqual("PUT", call["method"])
            body = call["body"]
            if isinstance(body, bytes):
                self.assertNotIn(b"merge", body.lower())
        self.assertNotIn("merge", VALID_DELIVERY_ACTIONS)
        with self.assertRaises(DeliveryGrantError):
            self.grant().require("merge")

    def test_a_close_response_claiming_integration_fails_closed(self) -> None:
        self.transport.add(
            "GET", self.pull_path(), json.dumps(self.pull_document()).encode()
        )
        self.transport.add(
            "PATCH",
            self.pull_path(),
            json.dumps(
                self.pull_document(
                    state="closed", merged=True, merged_at="2030-01-01T00:00:01Z"
                )
            ).encode(),
        )

        with self.assertRaisesRegex(DeliveryRestError, "integrated, not closed"):
            self.execute(self.close_intent(self.delivery), "close_own_pr")

    def test_close_without_the_grant_action_is_refused_before_any_request(self) -> None:
        delivery = self.delivery_for(
            self.transport,
            grant=self.grant(
                grant_id="GRANT-a4-800-no-close",
                allowed_actions=("push", "open_draft_pr", "post_comment"),
            ),
        )

        with self.assertRaisesRegex(DeliveryGrantError, "does not allow action"):
            self.execute(self.close_intent(delivery), "close_own_pr", delivery)

        self.assertEqual([], self.transport.calls)

    # -- delete-own-branch -------------------------------------------------

    def test_delete_own_branch_succeeds_and_issues_one_ref_delete(self) -> None:
        self.transport.add(
            "GET",
            self.repository_path(),
            json.dumps({"default_branch": R2_BASE}).encode(),
        )
        self.transport.add("DELETE", self.branch_path(R2_BRANCH), b"", status=204)

        result = self.execute(
            self.delete_intent(self.delivery, R2_BRANCH), "delete_own_branch"
        )

        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual(["GET", "DELETE"], self.methods(self.transport))
        deleted = self.transport.calls[-1]
        self.assertEqual(self.branch_path(R2_BRANCH), deleted["path"])
        self.assertIsNone(deleted["body"])

    def test_delete_own_branch_receipt_identifies_the_branch(self) -> None:
        self.transport.add(
            "GET",
            self.repository_path(),
            json.dumps({"default_branch": R2_BASE}).encode(),
        )
        self.transport.add("DELETE", self.branch_path(R2_BRANCH), b"", status=204)
        intent = self.delete_intent(self.delivery, R2_BRANCH)

        outcome = self.delivery.delete_branch_adapter(intent)

        self.assertEqual((f"branch:{R2_BRANCH}",), outcome["produced_identifiers"])
        self.assertEqual(
            canonical_digest({"deleted": R2_BRANCH}),
            outcome["postcondition_digest"],
        )

    def test_deleting_a_protected_branch_is_refused_before_any_request(self) -> None:
        self.assertEqual({"main", "master", "staging"}, set(PROTECTED_BRANCHES))
        for branch in sorted(PROTECTED_BRANCHES):
            with self.subTest(branch=branch):
                transport = FakeGitHubTransport()
                delivery = self.delivery_for(transport)

                with self.assertRaisesRegex(DeliveryGrantError, "protected branch"):
                    self.execute(
                        self.delete_intent(delivery, branch),
                        "delete_own_branch",
                        delivery,
                    )

                self.assertEqual([], transport.calls)

    def test_deleting_the_repository_default_branch_is_refused(self) -> None:
        # A default branch the static rules cannot catch: it is not protected,
        # it is not the grant base, and it sits inside the granted prefix.  Only
        # the live default-branch read can deny it.
        default = "autopilot/trunk"
        self.assertNotIn(default, PROTECTED_BRANCHES)
        transport = FakeGitHubTransport()
        delivery = self.delivery_for(
            transport,
            grant=self.grant(grant_id="GRANT-a4-800-develop", base_branch="develop"),
        )
        transport.add(
            "GET",
            self.repository_path(),
            json.dumps({"default_branch": default}).encode(),
        )

        with self.assertRaisesRegex(DeliveryGrantError, "default branch"):
            self.execute(
                self.delete_intent(delivery, default), "delete_own_branch", delivery
            )

        self.assertEqual(["GET"], self.methods(transport))

    def test_an_unreadable_default_branch_denies_the_delete(self) -> None:
        self.transport.add("GET", self.repository_path(), json.dumps({}).encode())

        with self.assertRaisesRegex(DeliveryRestError, "no default_branch"):
            self.execute(
                self.delete_intent(self.delivery, R2_BRANCH), "delete_own_branch"
            )

        self.assertEqual(["GET"], self.methods(self.transport))

    def test_deleting_outside_the_grant_prefix_is_refused_before_any_request(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            DeliveryGrantError, "outside the granted prefix"
        ):
            self.execute(
                self.delete_intent(self.delivery, "release/hive-mind-os-singleton"),
                "delete_own_branch",
            )

        self.assertEqual([], self.transport.calls)

    def test_deleting_the_grant_base_branch_is_refused_before_any_request(self) -> None:
        # "develop" is not protected, so only the base-branch rule can deny it.
        self.assertNotIn("develop", PROTECTED_BRANCHES)
        delivery = self.delivery_for(
            self.transport,
            grant=self.grant(grant_id="GRANT-a4-800-base", base_branch="develop"),
        )

        with self.assertRaisesRegex(DeliveryGrantError, "base branch"):
            self.execute(
                self.delete_intent(delivery, "develop"), "delete_own_branch", delivery
            )

        self.assertEqual([], self.transport.calls)

    def test_delete_without_the_grant_action_is_refused_before_any_request(
        self,
    ) -> None:
        delivery = self.delivery_for(
            self.transport,
            grant=self.grant(
                grant_id="GRANT-a4-800-no-delete",
                allowed_actions=("push", "open_draft_pr", "post_comment"),
            ),
        )

        with self.assertRaisesRegex(DeliveryGrantError, "does not allow action"):
            self.execute(
                self.delete_intent(delivery, R2_BRANCH), "delete_own_branch", delivery
            )

        self.assertEqual([], self.transport.calls)

    def test_a_branch_name_cannot_smuggle_a_path_into_the_ref_delete(self) -> None:
        # These all satisfy the grant prefix rule, so only the REST-layer ref
        # shape check stands between them and a DELETE on another path.
        for branch in (
            "autopilot/../../../repos/octocat/hive-mind-os/git/refs/heads/main",
            "autopilot/a4-800?ref=main",
            "autopilot/a4-800#fragment",
            "autopilot/.hidden",
            "autopilot/a4 800",
        ):
            with self.subTest(branch=branch):
                transport = FakeGitHubTransport()
                delivery = self.delivery_for(transport)
                transport.add(
                    "GET",
                    self.repository_path(),
                    json.dumps({"default_branch": R2_BASE}).encode(),
                )

                with self.assertRaises(DeliveryRestError):
                    self.execute(
                        self.delete_intent(delivery, branch),
                        "delete_own_branch",
                        delivery,
                    )

                self.assertEqual(["GET"], self.methods(transport))

    # -- ref reads ---------------------------------------------------------

    def gateway(self, transport: FakeGitHubTransport) -> ControlledRestGateway:
        return ControlledRestGateway(
            R2_OWNER,
            R2_REPOSITORY,
            transport=transport,  # type: ignore[arg-type]
        )

    @staticmethod
    def ref_path(branch: str) -> str:
        return f"/repos/{R2_OWNER}/{R2_REPOSITORY}/git/ref/heads/{branch}"

    def test_a_branch_ref_read_snapshots_the_head_it_points_at(self) -> None:
        # A4 D6: without this read the replay's before/after snapshots were
        # both null, so "branch head unchanged" compared None to None.
        transport = FakeGitHubTransport()
        transport.add(
            "GET",
            self.ref_path(R2_BRANCH),
            json.dumps(
                {
                    "ref": f"refs/heads/{R2_BRANCH}",
                    "object": {"sha": HEAD_SHA, "type": "commit"},
                }
            ).encode(),
        )

        head = self.gateway(transport).read_branch_ref(R2_BRANCH)

        self.assertEqual(HEAD_SHA, head)
        self.assertEqual(["GET"], self.methods(transport))
        self.assertEqual(self.ref_path(R2_BRANCH), transport.calls[0]["path"])
        self.assertIsNone(transport.calls[0]["body"])

    def test_a_missing_branch_ref_reads_as_absent_not_as_an_error(self) -> None:
        transport = FakeGitHubTransport()
        transport.add("GET", self.ref_path(R2_BRANCH), b"{}", status=404)

        self.assertIsNone(self.gateway(transport).read_branch_ref(R2_BRANCH))

    def test_a_branch_ref_read_without_a_full_head_sha_fails_closed(self) -> None:
        transport = FakeGitHubTransport()
        transport.add(
            "GET",
            self.ref_path(R2_BRANCH),
            json.dumps({"object": {"sha": "abc", "type": "commit"}}).encode(),
        )

        with self.assertRaisesRegex(DeliveryRestError, "full head SHA"):
            self.gateway(transport).read_branch_ref(R2_BRANCH)

    def test_every_r2_grant_is_issued_under_the_anchored_owner_authority(self) -> None:
        """A5-F6: no grant in this class depends on an anchoring step nobody ran."""

        self.assertEqual(self.owner_authority.record_digest, grants.LEDGER.anchor_digest)
        record = grants.LEDGER.issuance(self.grant().grant_digest)
        assert record is not None
        self.assertEqual(self.owner_authority.record_digest, record.anchor_digest)
        self.assertEqual(self.owner_authority.issuer, self.grant().issuer)
        # Cheat: cut a grant the anchored owner never backed.
        with self.assertRaisesRegex(DeliveryGrantError, "not anchored"):
            DeliveryGrant.issue(
                grant_id="GRANT-a4-800-self-issued",
                owner=R2_OWNER,
                repository=R2_REPOSITORY,
                base_branch=R2_BASE,
                branch_prefix=R2_PREFIX,
                allowed_actions=("push",),
                issued_at=R2_TIME,
            )

    def test_the_delivery_boundary_exposes_the_snapshot_read(self) -> None:
        transport = FakeGitHubTransport()
        transport.add(
            "GET",
            self.ref_path(R2_BRANCH),
            json.dumps({"object": {"sha": HEAD_SHA, "type": "commit"}}).encode(),
        )
        delivery = self.delivery_for(transport)

        self.assertEqual(HEAD_SHA, delivery.branch_head(R2_BRANCH))
        # A read is not a sixth adapter: nothing new is registered.
        gateway = EffectGateway(authority=self.registry, clock=lambda: R2_TIME)
        delivery.register_with(gateway)
        self.assertEqual(
            {
                ControlledGitHubDelivery.PUSH_ADAPTER,
                ControlledGitHubDelivery.DRAFT_PR_ADAPTER,
                ControlledGitHubDelivery.COMMENT_ADAPTER,
                ControlledGitHubDelivery.CLOSE_PR_ADAPTER,
                ControlledGitHubDelivery.DELETE_BRANCH_ADAPTER,
            },
            set(gateway._adapters),
        )

    def test_a_branch_name_cannot_smuggle_a_path_into_the_ref_read(self) -> None:
        # The same names the delete-side guard refuses; the read carries the
        # same guard, so none of them reaches the transport at all.
        for branch in (
            "autopilot/../../../repos/octocat/hive-mind-os/git/refs/heads/main",
            "autopilot/a4-800?ref=main",
            "autopilot/a4-800#fragment",
            "autopilot/.hidden",
            "autopilot/a4 800",
        ):
            with self.subTest(branch=branch):
                transport = FakeGitHubTransport()

                with self.assertRaises(DeliveryRestError):
                    self.gateway(transport).read_branch_ref(branch)

                self.assertEqual([], transport.calls)

    # -- query encoding and paging ----------------------------------------

    def test_find_open_draft_pr_encodes_its_query_parameters(self) -> None:
        transport = FakeGitHubTransport()
        expected = (
            f"/repos/{R2_OWNER}/{R2_REPOSITORY}/pulls?state=open"
            f"&head={R2_OWNER}%3Aautopilot%2Fa4-800%2Bfeature&base=release%2Fnext"
        )
        transport.add("GET", expected, b"[]")

        found = self.gateway(transport).find_open_draft_pr(
            "autopilot/a4-800+feature",
            "release/next",
        )

        self.assertIsNone(found)
        self.assertEqual(expected, transport.calls[0]["path"])

    def comment_page_path(self, page: int) -> str:
        return (
            f"/repos/{R2_OWNER}/{R2_REPOSITORY}/issues/{R2_PULL}"
            f"/comments?per_page=100&page={page}"
        )

    def test_a_comment_marker_beyond_page_one_is_found_and_not_reposted(self) -> None:
        # A4 D3: with a single unpaged read the marker fell off page one and
        # the adapter posted a second identical comment.
        intent = self.intent(
            action="post_comment",
            adapter=ControlledGitHubDelivery.COMMENT_ADAPTER,
            parameters_digest=self.delivery.bind_parameters(
                {"pull_number": R2_PULL, "body": "node receipt"}
            ),
        )
        marker = f"{COMMENT_MARKER_PREFIX}{intent.idempotency_key} -->"
        first = [
            {"id": index, "body": f"unrelated chatter {index}"}
            for index in range(1, 101)
        ]
        second = [{"id": 900, "body": f"node receipt\n\n{marker}"}]
        self.assertEqual(100, len(first))
        self.transport.add("GET", self.comment_page_path(1), json.dumps(first).encode())
        self.transport.add(
            "GET", self.comment_page_path(2), json.dumps(second).encode()
        )

        outcome = self.delivery.comment_adapter(intent)

        self.assertEqual(("comment:900",), outcome["produced_identifiers"])
        self.assertEqual(["GET", "GET"], self.methods(self.transport))
        self.assertNotIn("POST", self.methods(self.transport))
        self.assertEqual(
            [self.comment_page_path(1), self.comment_page_path(2)],
            [call["path"] for call in self.transport.calls],
        )

    def test_a_short_first_comment_page_ends_the_read(self) -> None:
        self.transport.add(
            "GET",
            self.comment_page_path(1),
            json.dumps([{"id": 5, "body": "unrelated"}]).encode(),
        )

        comments = self.delivery.rest.list_comments(R2_PULL)

        self.assertEqual((5,), tuple(comment["id"] for comment in comments))
        self.assertEqual(["GET"], self.methods(self.transport))

    def test_retractions_refuse_an_intent_aimed_at_another_repository(self) -> None:
        for action, adapter, parameters in (
            (
                "close_own_pr",
                ControlledGitHubDelivery.CLOSE_PR_ADAPTER,
                {"pull_number": R2_PULL},
            ),
            (
                "delete_own_branch",
                ControlledGitHubDelivery.DELETE_BRANCH_ADAPTER,
                {"branch": R2_BRANCH},
            ),
        ):
            with self.subTest(action=action):
                transport = FakeGitHubTransport()
                delivery = self.delivery_for(transport)
                intent = self.intent(
                    action=action,
                    adapter=adapter,
                    parameters_digest=delivery.bind_parameters(parameters),
                    target=R2_TARGET,
                )
                # The adapter is called directly with an intent whose target is
                # a different repository; the gateway token binds the granted
                # target, so only the adapter's own check can deny this.
                foreign = self.intent(
                    action=action,
                    adapter=adapter,
                    parameters_digest=intent.parameters_digest,
                    target="github/somebody-else/hive-mind-os",
                )
                adapter_callable = getattr(
                    delivery,
                    "close_pr_adapter"
                    if action == "close_own_pr"
                    else "delete_branch_adapter",
                )

                with self.assertRaisesRegex(
                    DeliveryGrantError, "not the granted repository"
                ):
                    adapter_callable(foreign)

                self.assertEqual([], transport.calls)


class ScriptedHeadClient(GitHubClient):
    """Answers a push with a scripted head; it runs no Git and opens no socket."""

    def __init__(
        self,
        *args: object,
        head_sha: object,
        transport: FakeGitHubTransport,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, transport=transport, **kwargs)  # type: ignore[arg-type]
        self.scripted_head = head_sha
        self.calls = 0

    def push_branch(
        self,
        workspace: GitWorkspace,
        *,
        branch: str | None = None,
        remote_url: str | Path | None = None,
        allow_local_test_remote: bool = False,
    ) -> PushResult:
        self.calls += 1
        return PushResult(branch or "", self.scripted_head, {})  # type: ignore[arg-type]


class WorkspacePushExecutorTests(unittest.TestCase):
    """A4-800 Path B: the production binding from ``PushExecutor`` to a real push.

    Every push below lands in a bare repository created by ``git init --bare``
    inside the workspace and reached through ``allow_local_test_remote``,
    exactly as ``test_token_never_persists_or_escapes_errors`` does.  Nothing
    here opens a socket: the REST transport is the same in-process fake the
    rest of this module uses and it raises on any request, and the credential
    is a dummy value in an environment variable this class owns and restores.
    """

    TOKEN_ENV = "HIVE_PUSH_EXECUTOR_TEST_TOKEN"

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.owner_authority = _anchor_delivery_ledger(self)
        self.environment = patch.dict(
            os.environ,
            {self.TOKEN_ENV: "fixture-push-executor-token"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = MissionStore(self.root / "state")
        self.addCleanup(self.store.close)
        self.mission_id = "mission-push-executor"
        self.store.register_mission(
            self.mission_id,
            {
                "objective": "push one granted run branch",
                "source_pack_fingerprint": f"sha256:{'2' * 64}",
            },
            AutonomyBudget(100, 100, 100.0),
        )
        fixture = build_fixture_repo(self.root / "parent")
        self.workspace = GitWorkspace.materialize(
            fixture.root,
            COMMIT_TWO_SHA,
            self.root / "work",
            self.root / "ev",
        )
        self.workspace.create_branch(R2_BRANCH)
        self.workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        self.workspace.commit("fix: restore increment")
        self.bare = self.workspace.root / ".git" / "push-executor-remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(self.bare)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    # -- fixtures ----------------------------------------------------------

    def client(self, *, token_env: str | None = None) -> GitHubClient:
        return GitHubClient(
            R2_OWNER,
            R2_REPOSITORY,
            self.root / "gh",
            transport=FakeGitHubTransport(),
            token_env=token_env or self.TOKEN_ENV,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            mission_store=self.store,
            mission_id=self.mission_id,
            sleep=lambda _seconds: None,
            clock=lambda: "2026-07-27T20:03:00Z",
        )

    def scripted_client(self, head_sha: object) -> ScriptedHeadClient:
        return ScriptedHeadClient(
            R2_OWNER,
            R2_REPOSITORY,
            self.root / "gh",
            head_sha=head_sha,
            transport=FakeGitHubTransport(),
            token_env=self.TOKEN_ENV,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            mission_store=self.store,
            mission_id=self.mission_id,
        )

    def executor(self, client: GitHubClient | None = None) -> WorkspacePushExecutor:
        return WorkspacePushExecutor(
            client or self.client(),
            self.workspace,
            remote_url=Path(".git") / self.bare.name,
            allow_local_test_remote=True,
        )

    def workspace_head(self) -> str:
        return subprocess.run(
            ["git", "-C", str(self.workspace.root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def remote_head(self) -> str:
        return subprocess.run(
            ["git", "--git-dir", str(self.bare), "rev-parse", f"refs/heads/{R2_BRANCH}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    # -- the seam ----------------------------------------------------------

    def test_push_returns_the_committed_head_it_actually_wrote(self) -> None:
        head = self.executor().push(R2_BRANCH)

        self.assertEqual(self.workspace_head(), head)
        self.assertEqual(self.remote_head(), head)

    def test_returned_head_is_a_lowercase_full_hex_sha(self) -> None:
        head = self.executor().push(R2_BRANCH)

        self.assertRegex(head, r"\A[0-9a-f]{40}\Z")
        self.assertEqual(head.lower(), head)
        # An uppercase head from a delegate is normalized, not rejected.
        upper = self.workspace_head().upper()
        self.assertEqual(
            upper.lower(),
            self.executor(self.scripted_client(upper)).push(R2_BRANCH),
        )

    def test_a_head_that_is_not_a_full_sha_raises_instead_of_returning(self) -> None:
        for head in (
            "",
            "abc123",
            "z" * 40,
            "a" * 39,
            "a" * 41,
            " " + "a" * 39,
            "a" * 40 + "\n",
            None,
            b"a" * 40,
        ):
            with self.subTest(head=head):
                executor = self.executor(self.scripted_client(head))

                with self.assertRaisesRegex(
                    GitHubDeliveryError, "full 40-hex head SHA"
                ):
                    executor.push(R2_BRANCH)

    def test_a_blank_branch_never_falls_back_to_the_workspace_branch(self) -> None:
        client = self.scripted_client("b" * 40)

        for branch in ("", "   "):
            with self.subTest(branch=branch):
                with self.assertRaisesRegex(
                    GitHubDeliveryError, "requires a mission branch"
                ):
                    self.executor(client).push(branch)

        self.assertEqual(0, client.calls)

    def test_a_missing_credential_propagates_unweakened(self) -> None:
        absent = f"{self.TOKEN_ENV}_ABSENT"
        self.assertNotIn(absent, os.environ)
        executor = self.executor(self.client(token_env=absent))

        with self.assertRaises(MissingGitHubCredential) as captured:
            executor.push(R2_BRANCH)

        self.assertIs(MissingGitHubCredential, type(captured.exception))
        self.assertIn(absent, str(captured.exception))
        # The denial preceded the push: the remote has no such ref.
        with self.assertRaises(subprocess.CalledProcessError):
            self.remote_head()

    def test_executor_matches_the_push_executor_protocol_signature(self) -> None:
        # Imported here so this addition leaves the module's import block as it
        # was; only this test needs the protocol object itself.
        from hive_mind_os.cortex.github.delivery_adapter import PushExecutor

        self.assertEqual(
            inspect.signature(PushExecutor.push),
            inspect.signature(WorkspacePushExecutor.push),
        )

    def test_controlled_delivery_accepts_the_executor_and_pushes_through_it(
        self,
    ) -> None:
        registry = AuthorityRegistry()
        _mint_root(registry, ControlledRetractionTests.envelope())
        transport = FakeGitHubTransport()
        delivery = ControlledGitHubDelivery(
            ControlledRetractionTests.grant(),
            rest=ControlledRestGateway(
                R2_OWNER,
                R2_REPOSITORY,
                transport=transport,  # type: ignore[arg-type]
            ),
            push_executor=self.executor(),
        )
        gateway = EffectGateway(authority=registry, clock=lambda: R2_TIME)
        delivery.register_with(gateway)
        intent = ControlledRetractionTests.intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=delivery.bind_parameters({"branch": R2_BRANCH}),
        )

        result = gateway.execute(
            intent,
            registry.authorize(R2_AUTH, "push", R2_TARGET, now=R2_TIME),
        )

        head = self.workspace_head()
        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual(head, self.remote_head())
        # The gateway result carries digests only, so read the identifiers the
        # push adapter produced by replaying the same bound intent; the mission
        # store answers that from its effect receipt without pushing again.
        self.assertEqual(
            {
                "produced_identifiers": (f"branch:{R2_BRANCH}", f"sha:{head}"),
                "postcondition_digest": canonical_digest(
                    {"pushed": R2_BRANCH, "head": head}
                ),
            },
            delivery.push_adapter(intent),
        )
        # The push adapter is Git only; it reached no REST endpoint.
        self.assertEqual([], transport.calls)


if __name__ == "__main__":
    unittest.main()
