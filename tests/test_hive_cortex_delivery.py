"""DELIVERY-420: controlled GitHub delivery on the canonical effect path.

Every test in this module is fully in-process.  The only HTTP seam is a
``FakeTransport`` that answers from a local script and raises on anything it
was not told about, and the only push seam is a ``FakePushExecutor`` that
records branch names.  No socket is opened, no credential is read from the
real environment, no git command runs, and no GitHub API is contacted.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping
from unittest import mock

from hive_mind_os.brain_kernel.authority import AuthorityRegistry
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import (
    Budget,
    ConstraintEnvelope,
    EffectIntent,
)
from hive_mind_os.brain_kernel.effect_outbox import EffectReconciliationRequired
from hive_mind_os.brain_kernel.effects import EffectGateway
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.cortex.github.delivery_adapter import (
    COMMENT_MARKER_PREFIX,
    ControlledGitHubDelivery,
    DeliveryParametersUnbound,
)
from hive_mind_os.cortex.github.grants import (
    PROTECTED_BRANCHES,
    VALID_DELIVERY_ACTIONS,
    DeliveryGrant,
    DeliveryGrantError,
)
from hive_mind_os.cortex.github.rest_gateway import (
    ControlledRestGateway,
    DeliveryRestError,
)
from hive_mind_os.github_adapter import GitHubResponse

DIGEST = "sha256:" + "0" * 64
TIME = "2030-01-01T00:00:00Z"
OWNER = "octo"
REPOSITORY = "repo"
TARGET = f"github/{OWNER}/{REPOSITORY}"
BASE_BRANCH = "main"
BRANCH_PREFIX = "autopilot/"
RUN_BRANCH = "autopilot/delivery-420"
HEAD_SHA = "0" * 40
TOKEN_ENV = "HIVE_MIND_DELIVERY_420_TEST_TOKEN"
PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "hive_mind_os"
    / "cortex"
    / "github"
)


def _envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-delivery",
        "MISSION-delivery",
        "WORK-delivery",
        None,
        "builder",
        "R1",
        ("push", "open_draft_pr", "post_comment"),
        ("merge", "deploy"),
        ("workspace",),
        ("workspace",),
        (),
        (),
        (),
        (),
        Budget(30, 0, 0, 0, 0, 0, 1, 1),
        "2030-01-02T00:00:00Z",
        DIGEST,
        DIGEST,
    )


def _intent(
    *,
    action: str,
    adapter: str,
    parameters_digest: str,
    key: str = DIGEST,
    digest: str = DIGEST,
    target: str = TARGET,
) -> EffectIntent:
    return EffectIntent(
        "MISSION-delivery",
        "WORK-delivery",
        "ATTEMPT-delivery",
        "builder-1",
        "builder",
        action,
        "R1",
        adapter,
        target,
        parameters_digest,
        key,
        DIGEST,
        ("run branch exists",),
        "git revert the delivery commits",
        "POLICY-delivery",
        digest,
    )


def _grant(
    *,
    grant_id: str = "GRANT-delivery-420",
    base_branch: str = BASE_BRANCH,
    branch_prefix: str = BRANCH_PREFIX,
    allowed_actions: tuple[str, ...] = ("push", "open_draft_pr", "post_comment"),
) -> DeliveryGrant:
    return DeliveryGrant.issue(
        grant_id=grant_id,
        owner=OWNER,
        repository=REPOSITORY,
        base_branch=base_branch,
        branch_prefix=branch_prefix,
        allowed_actions=allowed_actions,
        issued_at=TIME,
    )


class FakeTransport:
    """A scripted, in-process stand-in for ``GitHubTransport``.

    It never performs I/O.  Any request that no rule covers raises, so a test
    can prove that a code path made no remote call at all.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.headers: list[dict[str, str]] = []
        self.bodies: list[bytes | None] = []
        self._rules: list[tuple[str, str, int, Any]] = []

    def script(self, method: str, contains: str, status: int, payload: Any) -> None:
        self._rules.append((method, contains, status, payload))

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> GitHubResponse:
        self.calls.append((method, url))
        self.headers.append(dict(headers))
        self.bodies.append(body)
        for rule_method, contains, status, payload in self._rules:
            if rule_method == method and contains in url:
                return GitHubResponse(
                    status, json.dumps(payload).encode("utf-8"), {}
                )
        raise AssertionError(f"unscripted GitHub request: {method} {url}")

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


class FakePushExecutor:
    """Records pushed branches; it has no force option and runs no command."""

    def __init__(self, head: str = HEAD_SHA) -> None:
        self.head = head
        self.branches: list[str] = []

    def push(self, branch: str) -> str:
        self.branches.append(branch)
        return self.head


class _DeliveryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.kernel_store = KernelStore(Path(self.temporary.name) / "kernel.sqlite3")
        self.addCleanup(self.kernel_store.close)
        self.registry = AuthorityRegistry()
        self.registry.register(_envelope())
        self.transport = FakeTransport()
        self.push_executor = FakePushExecutor()
        self.grant = _grant()
        self.rest = ControlledRestGateway(
            OWNER, REPOSITORY, transport=self.transport, token_env=TOKEN_ENV
        )
        self.delivery = ControlledGitHubDelivery(
            self.grant, rest=self.rest, push_executor=self.push_executor
        )
        credential = mock.patch.dict(
            os.environ, {TOKEN_ENV: "fake-local-delivery-token"}
        )
        credential.start()
        self.addCleanup(credential.stop)

    def token(self, action: str):
        return self.registry.authorize(DIGEST, action, TARGET, now=TIME)

    def in_memory_gateway(
        self, delivery: ControlledGitHubDelivery | None = None
    ) -> EffectGateway:
        gateway = EffectGateway()
        (delivery or self.delivery).register_with(gateway)
        return gateway

    def durable_gateway(
        self, delivery: ControlledGitHubDelivery | None = None
    ) -> EffectGateway:
        gateway = EffectGateway(store=self.kernel_store)
        (delivery or self.delivery).register_with(gateway)
        return gateway

    def stored_receipt(self, intent_digest: str) -> dict[str, Any]:
        row = self.kernel_store.connection.execute(
            "SELECT receipt_json FROM effect_receipts WHERE intent_digest=?",
            (intent_digest,),
        ).fetchone()
        self.assertIsNotNone(row)
        return json.loads(str(row["receipt_json"]))

    def receipt_count(self, intent_digest: str) -> int:
        row = self.kernel_store.connection.execute(
            "SELECT COUNT(*) AS total FROM effect_receipts WHERE intent_digest=?",
            (intent_digest,),
        ).fetchone()
        return int(row["total"])


class DeliveryAdapterTests(_DeliveryFixture):
    def test_push_executes_through_gateway_and_records_receipt(self) -> None:
        parameters_digest = self.delivery.bind_parameters({"branch": RUN_BRANCH})
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=parameters_digest,
        )
        gateway = self.durable_gateway()

        result = gateway.execute(intent, self.token("push"))

        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual([RUN_BRANCH], self.push_executor.branches)
        entry = self.kernel_store.effect_entry(intent_digest=intent.intent_digest)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual("receipt_recorded", entry["state"])
        self.assertEqual(result.receipt_digest, entry["receipt_digest"])
        receipt = self.stored_receipt(intent.intent_digest)
        self.assertEqual(
            [f"branch:{RUN_BRANCH}", f"sha:{HEAD_SHA}"],
            receipt["produced_identifiers"],
        )
        self.assertEqual(
            canonical_digest({"pushed": RUN_BRANCH, "head": HEAD_SHA}),
            receipt["postcondition_digest"],
        )
        self.assertEqual(
            ControlledGitHubDelivery.PUSH_ADAPTER, receipt["adapter_identity"]
        )
        self.assertEqual([], self.transport.calls)

    def test_draft_pr_creates_when_absent_and_reports_identifiers(self) -> None:
        url = "https://github.com/octo/repo/pull/41"
        self.transport.script("GET", "/pulls?", 200, [])
        self.transport.script(
            "POST",
            "/pulls",
            201,
            {"number": 41, "html_url": url, "draft": True},
        )
        parameters_digest = self.delivery.bind_parameters(
            {"branch": RUN_BRANCH, "title": "DELIVERY-420", "body": "node receipt"}
        )
        intent = _intent(
            action="open_draft_pr",
            adapter=ControlledGitHubDelivery.DRAFT_PR_ADAPTER,
            parameters_digest=parameters_digest,
        )
        gateway = self.durable_gateway()

        result = gateway.execute(intent, self.token("open_draft_pr"))

        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual(["GET", "POST"], self.transport.methods())
        created = json.loads(str(self.transport.bodies[-1], "utf-8"))
        self.assertIs(True, created["draft"])
        self.assertIs(False, created["maintainer_can_modify"])
        self.assertEqual(BASE_BRANCH, created["base"])
        self.assertEqual(RUN_BRANCH, created["head"])
        receipt = self.stored_receipt(intent.intent_digest)
        self.assertEqual(["pr:41", url], receipt["produced_identifiers"])
        self.assertEqual(
            canonical_digest({"pr": 41, "draft": True}),
            receipt["postcondition_digest"],
        )

    def test_comment_posts_with_marker(self) -> None:
        self.transport.script("GET", "/issues/41/comments", 200, [])
        self.transport.script("POST", "/issues/41/comments", 201, {"id": 900})
        parameters_digest = self.delivery.bind_parameters(
            {"pull_number": 41, "body": "controlled delivery status"}
        )
        intent = _intent(
            action="post_comment",
            adapter=ControlledGitHubDelivery.COMMENT_ADAPTER,
            parameters_digest=parameters_digest,
        )
        gateway = self.durable_gateway()

        gateway.execute(intent, self.token("post_comment"))

        self.assertEqual(["GET", "POST"], self.transport.methods())
        posted = json.loads(str(self.transport.bodies[-1], "utf-8"))
        marker = f"{COMMENT_MARKER_PREFIX}{intent.idempotency_key} -->"
        self.assertTrue(posted["body"].startswith("controlled delivery status"))
        self.assertIn(marker, posted["body"])
        receipt = self.stored_receipt(intent.intent_digest)
        self.assertEqual(["comment:900"], receipt["produced_identifiers"])
        self.assertNotIn("controlled delivery status", json.dumps(receipt))
        self.assertNotIn("fake-local-delivery-token", json.dumps(receipt))

    def test_unbound_parameters_fail_closed_without_remote_call(self) -> None:
        unbound = canonical_digest({"branch": RUN_BRANCH, "never": "registered"})
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=unbound,
        )
        gateway = self.in_memory_gateway()

        with self.assertRaises(DeliveryParametersUnbound):
            gateway.execute(intent, self.token("push"))

        self.assertEqual([], self.transport.calls)
        self.assertEqual([], self.push_executor.branches)

    def test_grant_tamper_is_rejected(self) -> None:
        sealed = _grant()

        with self.assertRaises(DeliveryGrantError):
            DeliveryGrant(
                sealed.grant_id,
                sealed.owner,
                sealed.repository,
                sealed.base_branch,
                sealed.branch_prefix,
                sealed.allowed_actions,
                sealed.issued_at,
                DIGEST,
            )
        with self.assertRaises(DeliveryGrantError):
            DeliveryGrant(
                sealed.grant_id,
                sealed.owner,
                sealed.repository,
                sealed.base_branch,
                "hive-mind/",
                sealed.allowed_actions,
                sealed.issued_at,
                sealed.grant_digest,
            )
        with self.assertRaises(DeliveryGrantError):
            DeliveryGrant(
                sealed.grant_id,
                sealed.owner,
                sealed.repository,
                sealed.base_branch,
                sealed.branch_prefix,
                ("push", "open_draft_pr", "post_comment", "post_comment"),
                sealed.issued_at,
                sealed.grant_digest,
            )

    def test_invalid_head_sha_from_push_executor_is_rejected(self) -> None:
        delivery = ControlledGitHubDelivery(
            _grant(),
            rest=self.rest,
            push_executor=FakePushExecutor(head="not-a-sha"),
        )
        parameters_digest = delivery.bind_parameters({"branch": RUN_BRANCH})
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=parameters_digest,
        )

        with self.assertRaises(DeliveryRestError):
            self.in_memory_gateway(delivery).execute(intent, self.token("push"))

    def test_draft_pr_response_without_number_is_rejected(self) -> None:
        self.transport.script("GET", "/pulls?", 200, [])
        self.transport.script(
            "POST",
            "/pulls",
            201,
            {"html_url": "https://github.com/octo/repo/pull/9", "draft": True},
        )
        parameters_digest = self.delivery.bind_parameters(
            {"branch": RUN_BRANCH, "title": "t", "body": "b"}
        )
        intent = _intent(
            action="open_draft_pr",
            adapter=ControlledGitHubDelivery.DRAFT_PR_ADAPTER,
            parameters_digest=parameters_digest,
        )

        with self.assertRaises(DeliveryRestError):
            self.in_memory_gateway().execute(intent, self.token("open_draft_pr"))

    def test_missing_token_environment_denies_before_transport_call(self) -> None:
        with mock.patch.dict(os.environ, {TOKEN_ENV: ""}):
            with self.assertRaises(DeliveryRestError):
                self.rest.list_comments(41)
        self.assertEqual([], self.transport.calls)


class ProtectedBranchDenialTests(_DeliveryFixture):
    def test_push_to_each_protected_branch_is_denied(self) -> None:
        self.assertEqual({"main", "master", "staging"}, set(PROTECTED_BRANCHES))
        for branch in sorted(PROTECTED_BRANCHES):
            with self.subTest(branch=branch):
                parameters_digest = self.delivery.bind_parameters({"branch": branch})
                intent = _intent(
                    action="push",
                    adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
                    parameters_digest=parameters_digest,
                    key=canonical_digest({"key": branch}),
                    digest=canonical_digest({"intent": branch}),
                )
                with self.assertRaises(DeliveryGrantError):
                    self.in_memory_gateway().execute(intent, self.token("push"))
        self.assertEqual([], self.push_executor.branches)
        self.assertEqual([], self.transport.calls)

    def test_push_outside_grant_prefix_is_denied(self) -> None:
        parameters_digest = self.delivery.bind_parameters(
            {"branch": "release/hive-mind-os-singleton"}
        )
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=parameters_digest,
        )

        with self.assertRaisesRegex(DeliveryGrantError, "outside the granted prefix"):
            self.in_memory_gateway().execute(intent, self.token("push"))

        self.assertEqual([], self.push_executor.branches)
        self.assertEqual([], self.transport.calls)

    def test_push_to_base_branch_is_denied(self) -> None:
        # "develop" is not a protected branch, so only the base-branch rule can
        # produce this denial.
        delivery = ControlledGitHubDelivery(
            _grant(grant_id="GRANT-develop-base", base_branch="develop"),
            rest=self.rest,
            push_executor=self.push_executor,
        )
        self.assertNotIn("develop", PROTECTED_BRANCHES)
        parameters_digest = delivery.bind_parameters({"branch": "develop"})
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=parameters_digest,
        )

        with self.assertRaisesRegex(DeliveryGrantError, "base branch"):
            self.in_memory_gateway(delivery).execute(intent, self.token("push"))

        self.assertEqual([], self.push_executor.branches)

    def test_action_not_granted_is_denied(self) -> None:
        delivery = ControlledGitHubDelivery(
            _grant(
                grant_id="GRANT-no-push",
                allowed_actions=("open_draft_pr", "post_comment"),
            ),
            rest=self.rest,
            push_executor=self.push_executor,
        )
        parameters_digest = delivery.bind_parameters({"branch": RUN_BRANCH})
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=parameters_digest,
        )

        with self.assertRaisesRegex(DeliveryGrantError, "does not allow action"):
            self.in_memory_gateway(delivery).execute(intent, self.token("push"))

        self.assertEqual([], self.push_executor.branches)
        self.assertEqual([], self.transport.calls)

    def test_merge_is_not_a_grantable_action(self) -> None:
        self.assertNotIn("merge", VALID_DELIVERY_ACTIONS)
        with self.assertRaises(DeliveryGrantError):
            _grant(grant_id="GRANT-merge", allowed_actions=("merge",))
        with self.assertRaises(DeliveryGrantError):
            _grant(grant_id="GRANT-merge-mixed", allowed_actions=("push", "merge"))
        with self.assertRaises(DeliveryGrantError):
            self.grant.require("merge")

    def test_no_merge_surface_exists(self) -> None:
        for surface in (ControlledGitHubDelivery, ControlledRestGateway, DeliveryGrant):
            for name in dir(surface):
                with self.subTest(surface=surface.__name__, attribute=name):
                    self.assertNotIn("merge", name.lower())
                    self.assertNotIn("force", name.lower())
        forbidden = ("--force", "force_push", "/merge", "merge_method", "/merges")
        modules = sorted(PACKAGE_ROOT.glob("*.py"))
        self.assertEqual(
            ["__init__.py", "delivery_adapter.py", "grants.py", "rest_gateway.py"],
            [module.name for module in modules],
        )
        for module in modules:
            source = module.read_text(encoding="utf-8")
            for needle in forbidden:
                with self.subTest(module=module.name, needle=needle):
                    self.assertNotIn(needle, source)

    def test_durable_path_denial_is_fail_closed(self) -> None:
        parameters_digest = self.delivery.bind_parameters({"branch": BASE_BRANCH})
        intent = _intent(
            action="push",
            adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
            parameters_digest=parameters_digest,
        )
        gateway = self.durable_gateway()

        with self.assertRaises(EffectReconciliationRequired):
            gateway.execute(intent, self.token("push"))

        entry = self.kernel_store.effect_entry(intent_digest=intent.intent_digest)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual("reconciliation_required", entry["state"])
        self.assertIsNone(entry["receipt_digest"])
        self.assertEqual(0, self.receipt_count(intent.intent_digest))
        self.assertEqual([], self.push_executor.branches)
        self.assertEqual([], self.transport.calls)


class DuplicatePrCommentTests(_DeliveryFixture):
    def test_same_intent_twice_returns_prior_receipt_without_second_remote_call(
        self,
    ) -> None:
        self.transport.script("GET", "/issues/41/comments", 200, [])
        self.transport.script("POST", "/issues/41/comments", 201, {"id": 900})
        parameters_digest = self.delivery.bind_parameters(
            {"pull_number": 41, "body": "first and only"}
        )
        intent = _intent(
            action="post_comment",
            adapter=ControlledGitHubDelivery.COMMENT_ADAPTER,
            parameters_digest=parameters_digest,
        )
        gateway = self.durable_gateway()
        token = self.token("post_comment")

        first = gateway.execute(intent, token)
        second = gateway.execute(intent, token)

        self.assertEqual(first, second)
        self.assertEqual(1, self.transport.methods().count("POST"))
        self.assertEqual(1, self.transport.methods().count("GET"))
        self.assertEqual(1, self.receipt_count(intent.intent_digest))

    def test_existing_open_draft_pr_is_reused_not_recreated(self) -> None:
        url = "https://github.com/octo/repo/pull/7"
        self.transport.script(
            "GET",
            "/pulls?",
            200,
            [
                {"number": 6, "html_url": "https://x/6", "draft": False},
                {"number": 7, "html_url": url, "draft": True},
            ],
        )
        parameters_digest = self.delivery.bind_parameters(
            {"branch": RUN_BRANCH, "title": "DELIVERY-420", "body": "node receipt"}
        )
        intent = _intent(
            action="open_draft_pr",
            adapter=ControlledGitHubDelivery.DRAFT_PR_ADAPTER,
            parameters_digest=parameters_digest,
        )
        gateway = self.durable_gateway()

        gateway.execute(intent, self.token("open_draft_pr"))

        self.assertEqual(["GET"], self.transport.methods())
        self.assertNotIn("POST", self.transport.methods())
        receipt = self.stored_receipt(intent.intent_digest)
        self.assertEqual(["pr:7", url], receipt["produced_identifiers"])

    def test_comment_with_existing_marker_is_not_reposted(self) -> None:
        parameters_digest = self.delivery.bind_parameters(
            {"pull_number": 41, "body": "duplicate across processes"}
        )
        intent = _intent(
            action="post_comment",
            adapter=ControlledGitHubDelivery.COMMENT_ADAPTER,
            parameters_digest=parameters_digest,
        )
        marker = f"{COMMENT_MARKER_PREFIX}{intent.idempotency_key} -->"
        self.transport.script(
            "GET",
            "/issues/41/comments",
            200,
            [
                {"id": 111, "body": "unrelated chatter"},
                {"id": 555, "body": f"duplicate across processes\n\n{marker}"},
            ],
        )
        gateway = self.durable_gateway()

        gateway.execute(intent, self.token("post_comment"))

        self.assertEqual(["GET"], self.transport.methods())
        receipt = self.stored_receipt(intent.intent_digest)
        self.assertEqual(["comment:555"], receipt["produced_identifiers"])

    def test_fresh_intent_new_key_posts_again(self) -> None:
        self.transport.script("GET", "/issues/41/comments", 200, [])
        self.transport.script("POST", "/issues/41/comments", 201, {"id": 901})
        parameters_digest = self.delivery.bind_parameters(
            {"pull_number": 41, "body": "round update"}
        )
        gateway = self.durable_gateway()
        token = self.token("post_comment")
        first = _intent(
            action="post_comment",
            adapter=ControlledGitHubDelivery.COMMENT_ADAPTER,
            parameters_digest=parameters_digest,
            key=canonical_digest({"key": "attempt-1"}),
            digest=canonical_digest({"intent": "attempt-1"}),
        )
        second = _intent(
            action="post_comment",
            adapter=ControlledGitHubDelivery.COMMENT_ADAPTER,
            parameters_digest=parameters_digest,
            key=canonical_digest({"key": "attempt-2"}),
            digest=canonical_digest({"intent": "attempt-2"}),
        )

        first_result = gateway.execute(first, token)
        second_result = gateway.execute(second, token)

        self.assertNotEqual(first.idempotency_key, second.idempotency_key)
        self.assertNotEqual(first_result.intent_digest, second_result.intent_digest)
        self.assertEqual(2, self.transport.methods().count("POST"))
        posted = [
            json.loads(str(body, "utf-8"))["body"]
            for method, body in zip(self.transport.methods(), self.transport.bodies)
            if method == "POST"
        ]
        self.assertIn(f"{COMMENT_MARKER_PREFIX}{first.idempotency_key} -->", posted[0])
        self.assertIn(f"{COMMENT_MARKER_PREFIX}{second.idempotency_key} -->", posted[1])
        self.assertEqual(1, self.receipt_count(first.intent_digest))
        self.assertEqual(1, self.receipt_count(second.intent_digest))


if __name__ == "__main__":
    unittest.main()
