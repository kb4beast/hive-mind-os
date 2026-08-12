"""Bind controlled GitHub delivery to the canonical kernel effect path.

Five adapters — branch push, draft pull request, pull-request comment, and the
two retractions that undo them (close own pull request, delete own branch) —
register with :class:`hive_mind_os.brain_kernel.effects.EffectGateway`.  Every
one of them starts from an immutable :class:`DeliveryGrant`, resolves its
parameters from a pre-bound digest, and returns the mapping shape that
``DurableEffectOutbox.execute`` folds into an ``EffectReceipt``.

There is no sixth adapter.  The two retractions are strictly self-scoped: each
one refuses any target the grant could not itself have created, so they can only
ever undo this pilot's own work.  Integrating a pull request, reviewing, and
protection writes are not implemented here and are not grantable, so no routine
mission can reach them through this boundary.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Protocol

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import EffectIntent
from hive_mind_os.brain_kernel.effects import EffectGateway
from hive_mind_os.cortex.github.grants import DeliveryGrant, DeliveryGrantError
from hive_mind_os.cortex.github.rest_gateway import (
    ControlledRestGateway,
    DeliveryRestError,
)

COMMENT_MARKER_PREFIX = "<!-- hive-effect:"

_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")


class PushExecutor(Protocol):
    """Pushes exactly one non-force branch ref and returns the full head SHA."""

    def push(self, branch: str) -> str: ...


class DeliveryParametersUnbound(RuntimeError):
    """No registered parameters match the intent parameters_digest."""


def _required_text(parameters: Mapping[str, Any], field: str) -> str:
    value = parameters.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DeliveryGrantError(f"delivery parameter {field} must be a non-empty string")
    return value


def _required_pull_number(parameters: Mapping[str, Any]) -> int:
    pull_number = parameters.get("pull_number")
    if type(pull_number) is not int or pull_number < 1:
        raise DeliveryGrantError(
            "delivery parameter pull_number must be a positive integer"
        )
    return pull_number


class ControlledGitHubDelivery:
    """The whole remote authority surface of a routine mission, and no more."""

    PUSH_ADAPTER = "github-push"
    DRAFT_PR_ADAPTER = "github-draft-pr"
    COMMENT_ADAPTER = "github-comment"
    CLOSE_PR_ADAPTER = "github-close-own-pr"
    DELETE_BRANCH_ADAPTER = "github-delete-own-branch"
    adapter_version = "1"

    def __init__(
        self,
        grant: DeliveryGrant,
        *,
        rest: ControlledRestGateway,
        push_executor: PushExecutor,
    ) -> None:
        if not isinstance(grant, DeliveryGrant):
            raise DeliveryGrantError("controlled delivery requires an immutable grant")
        if grant.owner != rest.owner or grant.repository != rest.repository:
            raise DeliveryGrantError("grant and REST gateway address different repositories")
        self.grant = grant
        self.rest = rest
        self.push_executor = push_executor
        self._bound_parameters: dict[str, dict[str, Any]] = {}

    # -- parameter binding -------------------------------------------------

    def bind_parameters(self, parameters: Mapping[str, Any]) -> str:
        """Register concrete parameters and return the digest an intent carries."""

        bound = dict(parameters)
        digest = canonical_digest(bound)
        self._bound_parameters.setdefault(digest, bound)
        return digest

    def _parameters(self, intent: EffectIntent) -> dict[str, Any]:
        bound = self._bound_parameters.get(intent.parameters_digest)
        if bound is None:
            raise DeliveryParametersUnbound(
                "delivery intent parameters_digest is not bound to any parameters"
            )
        return bound

    def _require_target(self, intent: EffectIntent) -> None:
        expected = f"github/{self.grant.owner}/{self.grant.repository}"
        if intent.target != expected:
            raise DeliveryGrantError(
                "delivery intent target is not the granted repository"
            )

    # -- registration ------------------------------------------------------

    def register_with(self, gateway: EffectGateway) -> None:
        """Register exactly the five delivery adapters on a kernel gateway."""

        gateway.register_adapter(
            self.PUSH_ADAPTER, self.push_adapter, version=self.adapter_version
        )
        gateway.register_adapter(
            self.DRAFT_PR_ADAPTER, self.draft_pr_adapter, version=self.adapter_version
        )
        gateway.register_adapter(
            self.COMMENT_ADAPTER, self.comment_adapter, version=self.adapter_version
        )
        gateway.register_adapter(
            self.CLOSE_PR_ADAPTER, self.close_pr_adapter, version=self.adapter_version
        )
        gateway.register_adapter(
            self.DELETE_BRANCH_ADAPTER,
            self.delete_branch_adapter,
            version=self.adapter_version,
        )

    # -- adapters ----------------------------------------------------------

    def push_adapter(self, intent: EffectIntent) -> dict[str, Any]:
        """Push one granted run branch; every denial precedes the push call."""

        self.grant.require("push")
        self._require_target(intent)
        parameters = self._parameters(intent)
        branch = _required_text(parameters, "branch")
        self.grant.require_push_branch(branch)
        head = self.push_executor.push(branch)
        if not isinstance(head, str) or _FULL_SHA.fullmatch(head) is None:
            raise DeliveryRestError(
                "push executor did not return a full lowercase head SHA"
            )
        return {
            "produced_identifiers": (f"branch:{branch}", f"sha:{head}"),
            "postcondition_digest": canonical_digest(
                {"pushed": branch, "head": head}
            ),
        }

    def draft_pr_adapter(self, intent: EffectIntent) -> dict[str, Any]:
        """Reuse or open one draft pull request against the granted base branch."""

        self.grant.require("open_draft_pr")
        self._require_target(intent)
        parameters = self._parameters(intent)
        branch = _required_text(parameters, "branch")
        title = _required_text(parameters, "title")
        body = _required_text(parameters, "body")
        self.grant.require_push_branch(branch)
        base = self.grant.base_branch
        document = self.rest.find_open_draft_pr(branch, base)
        if document is None:
            document = self.rest.create_draft_pr(branch, base, title, body)
        number = document.get("number")
        if type(number) is not int or number < 1:
            raise DeliveryRestError("draft pull request response has no valid number")
        url = document.get("html_url")
        if not isinstance(url, str) or not url:
            raise DeliveryRestError("draft pull request response has no html_url")
        return {
            "produced_identifiers": (f"pr:{number}", url),
            "postcondition_digest": canonical_digest({"pr": number, "draft": True}),
        }

    def comment_adapter(self, intent: EffectIntent) -> dict[str, Any]:
        """Post one marker-tagged comment, or adopt the one already posted."""

        self.grant.require("post_comment")
        self._require_target(intent)
        parameters = self._parameters(intent)
        pull_number = _required_pull_number(parameters)
        body = _required_text(parameters, "body")
        marker = f"{COMMENT_MARKER_PREFIX}{intent.idempotency_key} -->"
        for comment in self.rest.list_comments(pull_number):
            existing = comment.get("body")
            if isinstance(existing, str) and marker in existing:
                return self._comment_result(comment, pull_number)
        document = self.rest.post_comment(pull_number, f"{body}\n\n{marker}")
        return self._comment_result(document, pull_number)

    def close_pr_adapter(self, intent: EffectIntent) -> dict[str, Any]:
        """Close one draft pull request this grant opened, and nothing else."""

        self.grant.require("close_own_pr")
        self._require_target(intent)
        parameters = self._parameters(intent)
        pull_number = _required_pull_number(parameters)
        # Read first: every ownership denial happens before the state change.
        head_branch = self._own_open_draft_head(
            self.rest.get_pull_request(pull_number), pull_number
        )
        document = self.rest.close_pull_request(pull_number)
        if document.get("number") != pull_number:
            raise DeliveryRestError("close response is for a different pull request")
        return {
            "produced_identifiers": (f"pr:{pull_number}", f"branch:{head_branch}"),
            "postcondition_digest": canonical_digest(
                {"pr": pull_number, "state": "closed"}
            ),
        }

    def delete_branch_adapter(self, intent: EffectIntent) -> dict[str, Any]:
        """Delete one branch this grant could have created, and nothing else."""

        self.grant.require("delete_own_branch")
        self._require_target(intent)
        parameters = self._parameters(intent)
        branch = _required_text(parameters, "branch")
        # Static denial first, so a protected, base, or foreign branch never
        # reaches the network at all.
        self.grant.require_own_run_branch(branch, "delete_own_branch")
        # Then the live default branch, which a static list cannot know for an
        # owner-chosen pilot repository.  An unreadable default branch denies.
        if branch == self.rest.default_branch():
            raise DeliveryGrantError(
                f"delete_own_branch on repository default branch {branch!r} is denied"
            )
        self.rest.delete_branch(branch)
        return {
            "produced_identifiers": (f"branch:{branch}",),
            "postcondition_digest": canonical_digest({"deleted": branch}),
        }

    def _own_open_draft_head(
        self, document: Mapping[str, Any], pull_number: int
    ) -> str:
        """Return the head branch, having proven this grant opened this pull request.

        ``draft_pr_adapter`` is the only way this boundary can open a pull
        request, and it always opens an untouched draft from a branch under the
        granted prefix in the granted repository against the granted base.  A
        pull request that does not still match that description in every part
        was not opened here, so closing it is refused.
        """

        if document.get("state") != "open":
            raise DeliveryGrantError(
                f"pull request {pull_number} is not open, so it will not be closed"
            )
        if document.get("draft") is not True:
            raise DeliveryGrantError(
                f"pull request {pull_number} is not a draft, so it was not opened here"
            )
        base = document.get("base")
        if not isinstance(base, Mapping) or base.get("ref") != self.grant.base_branch:
            raise DeliveryGrantError(
                f"pull request {pull_number} does not target the granted base branch"
            )
        head = document.get("head")
        if not isinstance(head, Mapping):
            raise DeliveryGrantError(
                f"pull request {pull_number} has no readable head reference"
            )
        repository = head.get("repo")
        expected = f"{self.grant.owner}/{self.grant.repository}"
        if not isinstance(repository, Mapping) or repository.get("full_name") != expected:
            raise DeliveryGrantError(
                f"pull request {pull_number} head is not in the granted repository"
            )
        head_branch = head.get("ref")
        if not isinstance(head_branch, str):
            raise DeliveryGrantError(
                f"pull request {pull_number} has no readable head branch"
            )
        self.grant.require_own_run_branch(head_branch, "close_own_pr")
        return head_branch

    @staticmethod
    def _comment_result(
        document: Mapping[str, Any], pull_number: int
    ) -> dict[str, Any]:
        comment_id = document.get("id")
        if type(comment_id) is not int or comment_id < 1:
            raise DeliveryRestError("comment response has no valid identifier")
        return {
            "produced_identifiers": (f"comment:{comment_id}",),
            "postcondition_digest": canonical_digest(
                {"comment": comment_id, "pull": pull_number}
            ),
        }
