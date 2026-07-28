from __future__ import annotations

import asyncio
import json
import os
import ssl
import subprocess
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.git_adapter import GitWorkspace, PinViolation
from hive_mind_os.github_adapter import (
    CheckPollingTimeout,
    CheckRunFailed,
    GitHubClient,
    GitHubDeliveryTarget,
    GitHubPolicyDenied,
    GitHubResponse,
    GitHubTransportError,
    UrllibGitHubTransport,
    validate_github_receipt,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission import RepositoryMission
from hive_mind_os.mission_store import MissionStore
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


class LocalDeliveryClient(GitHubClient):
    """Exercise the mission boundary while keeping the push entirely local."""

    def __init__(
        self,
        *args: object,
        remote: Path,
        transport: FakeGitHubTransport,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, transport=transport, **kwargs)  # type: ignore[arg-type]
        self.local_remote = remote
        self.fake_transport = transport

    def push_branch(
        self,
        workspace: GitWorkspace,
        *,
        branch: str | None = None,
        remote_url: str | Path | None = None,
        allow_local_test_remote: bool = False,
    ):
        result = super().push_branch(
            workspace,
            branch=branch,
            remote_url=self.local_remote,
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
                ROOT / ".github" / "governance" / "required-repository-rules.json"
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

    def client(
        self,
        transport: object,
        *,
        policy: PolicyEngine | None = None,
        ledger: EvidenceLedger | None = None,
        sleep=lambda _seconds: None,
    ) -> GitHubClient:
        return GitHubClient(
            "octocat",
            "hive-mind-os",
            self.root / "github-evidence",
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
        request = next(call for call in transport.calls if call["method"] == "POST")
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
                + __import__("hashlib")
                .sha256(
                    json.dumps(
                        check,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                .hexdigest()
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
        bare = self.root / "remote.git"
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
            remote_url=bare,
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
            rule for rule in detail["rules"] if rule["type"] != "required_signatures"
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

        protection = json.loads(_fixture("protection.json"))
        protection["enforce_admins"]["enabled"] = False
        observed = GitHubClient._branch_observation(protection)
        self.assertFalse(observed["enforce_admins"])

        detail = json.loads(_fixture("ruleset-detail.json"))
        del detail["bypass_actors"]
        observed = GitHubClient._ruleset_observation([detail], "main")
        self.assertFalse(observed["enforce_admins"])

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
        remote = self.root / "mission-remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        mission_id = "mission-p07-integration"
        store = MissionStore(self.root / "mission-state")
        self.addCleanup(store.close)
        transport = FakeGitHubTransport()
        evidence = store.mission_root(mission_id) / "staging" / "evidence"
        client = LocalDeliveryClient(
            "octocat",
            "hive-mind-os",
            evidence,
            remote=remote,
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
                pin=fixture.commit_two,
                output_dir=self.root / "mission-output",
                policy=PolicyEngine(AutonomyLevel.REPOSITORY),
                mission_store=store,
                github_delivery=GitHubDeliveryTarget(
                    client,
                    "main",
                    "P07 offline mission integration",
                    "Draft evidence only.",
                    ROOT / ".github" / "governance" / "required-repository-rules.json",
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
        self.assertEqual(
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(remote),
                    "rev-parse",
                    "refs/heads/phase/mission-delivery",
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip(),
            report.head_sha,
        )


if __name__ == "__main__":
    unittest.main()
