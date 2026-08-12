"""A deliberately narrow GitHub REST surface for controlled delivery.

Eight calls exist: look up an open draft pull request, create one, read one,
close one, list issue comments, post one comment, read the repository default
branch, and delete one branch ref.  Closing and branch deletion exist only so a
pilot can retract exactly what it created; the two reads that precede them exist
only to enforce that refusal.  There is still no method for integrating a pull
request, reviewing, or writing branch protection, and none can be added without
changing this file.  The HTTP seam is the existing
:class:`hive_mind_os.github_adapter.GitHubTransport` protocol so tests can
supply a deterministic in-process fake.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

from hive_mind_os.brain_kernel.canonical import canonical_bytes
from hive_mind_os.github_adapter import (
    GitHubResponse,
    GitHubTransport,
    UrllibGitHubTransport,
)

_SIMPLE_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")
# A branch ref is slash-separated simple segments and nothing else, so a branch
# name can never smuggle a traversal, a query string, or a fragment into a path.
_BRANCH_REF = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")
_API_VERSION = "2022-11-28"
_USER_AGENT = "hive-mind-os-delivery-420"


class DeliveryRestError(RuntimeError):
    """The GitHub REST call failed or returned an invalid document."""


class ControlledRestGateway:
    """Draft-PR, comment, self-retraction, and the reads that gate them.

    No integration, review, or protection-write method exists on this class.
    """

    def __init__(
        self,
        owner: str,
        repository: str,
        *,
        transport: GitHubTransport | None = None,
        token_env: str = "GITHUB_TOKEN",
        api_base: str = "https://api.github.com",
        timeout_s: float = 30.0,
    ) -> None:
        if not isinstance(owner, str) or _SIMPLE_NAME.fullmatch(owner) is None:
            raise ValueError("GitHub owner must be a simple name")
        if not isinstance(repository, str) or _SIMPLE_NAME.fullmatch(repository) is None:
            raise ValueError("GitHub repository must be a simple name")
        if not isinstance(api_base, str) or not api_base.startswith("https://"):
            raise ValueError("GitHub API base must be HTTPS")
        if not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise ValueError("GitHub API timeout must be positive")
        if not isinstance(token_env, str) or not token_env.strip():
            raise ValueError("GitHub token environment name is required")
        self.owner = owner
        self.repository = repository
        self.transport: GitHubTransport = transport or UrllibGitHubTransport()
        self.token_env = token_env
        self.api_base = api_base.rstrip("/")
        self.timeout_s = float(timeout_s)

    @property
    def repository_path(self) -> str:
        return f"/repos/{self.owner}/{self.repository}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        accepted: tuple[int, ...] = (200,),
    ) -> GitHubResponse:
        """Issue one authorized call; a status outside ``accepted`` fails closed."""

        token = os.environ.get(self.token_env, "")
        if not token:
            raise DeliveryRestError(
                "required delivery credential environment variable is missing: "
                f"{self.token_env}"
            )
        encoded = canonical_bytes(dict(body)) if body is not None else None
        try:
            response: GitHubResponse = self.transport.request(
                method,
                f"{self.api_base}{path}",
                {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                    "X-GitHub-Api-Version": _API_VERSION,
                },
                encoded,
                self.timeout_s,
            )
        except (OSError, TimeoutError) as error:
            message = f"delivery transport failed: {type(error).__name__}: {error}"
            raise DeliveryRestError(message.replace(token, "[REDACTED]")) from None
        if response.status not in accepted:
            raise DeliveryRestError(
                f"GitHub API returned unexpected HTTP {response.status} for {method}"
            )
        return response

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        accepted: tuple[int, ...] = (200,),
    ) -> dict[str, Any] | list[Any]:
        response = self._request(method, path, body=body, accepted=accepted)
        try:
            document = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DeliveryRestError("GitHub API returned invalid UTF-8 JSON") from None
        if not isinstance(document, (dict, list)):
            raise DeliveryRestError("GitHub API response must be an object or array")
        return document

    @staticmethod
    def _pull_number(pull_number: int) -> int:
        if type(pull_number) is not int or pull_number < 1:
            raise DeliveryRestError("pull request number must be a positive integer")
        return pull_number

    @staticmethod
    def _branch_ref(branch: Any) -> str:
        """Accept only a plain slash-separated branch ref; anything else fails closed."""

        if not isinstance(branch, str) or _BRANCH_REF.fullmatch(branch) is None:
            raise DeliveryRestError(
                "branch ref must be slash-separated simple segments"
            )
        if any(segment.startswith(".") for segment in branch.split("/")):
            raise DeliveryRestError("branch ref segments must not start with '.'")
        return branch

    def find_open_draft_pr(self, branch: str, base: str) -> Mapping[str, Any] | None:
        """Return an existing open draft PR for the branch, or ``None``."""

        document = self._request_json(
            "GET",
            f"{self.repository_path}/pulls"
            f"?state=open&head={self.owner}:{branch}&base={base}",
        )
        if not isinstance(document, list):
            raise DeliveryRestError("pull request listing must be an array")
        for candidate in document:
            if isinstance(candidate, Mapping) and candidate.get("draft") is True:
                return candidate
        return None

    def create_draft_pr(
        self, branch: str, base: str, title: str, body: str
    ) -> Mapping[str, Any]:
        """Create exactly one draft pull request; a non-draft result fails closed."""

        document = self._request_json(
            "POST",
            f"{self.repository_path}/pulls",
            body={
                "title": title,
                "body": body,
                "head": branch,
                "base": base,
                "draft": True,
                "maintainer_can_modify": False,
            },
            accepted=(201,),
        )
        if not isinstance(document, Mapping) or document.get("draft") is not True:
            raise DeliveryRestError("GitHub did not create a draft pull request")
        return document

    def list_comments(self, pull_number: int) -> tuple[Mapping[str, Any], ...]:
        document = self._request_json(
            "GET",
            f"{self.repository_path}/issues/{self._pull_number(pull_number)}"
            "/comments?per_page=100",
        )
        if not isinstance(document, list):
            raise DeliveryRestError("comment listing must be an array")
        return tuple(item for item in document if isinstance(item, Mapping))

    def post_comment(self, pull_number: int, body: str) -> Mapping[str, Any]:
        document = self._request_json(
            "POST",
            f"{self.repository_path}/issues/{self._pull_number(pull_number)}/comments",
            body={"body": body},
            accepted=(201,),
        )
        if not isinstance(document, Mapping):
            raise DeliveryRestError("comment response must be an object")
        return document

    def get_pull_request(self, pull_number: int) -> Mapping[str, Any]:
        """Read one pull request so a caller can prove it is the one it opened."""

        document = self._request_json(
            "GET",
            f"{self.repository_path}/pulls/{self._pull_number(pull_number)}",
        )
        if not isinstance(document, Mapping):
            raise DeliveryRestError("pull request response must be an object")
        return document

    def close_pull_request(self, pull_number: int) -> Mapping[str, Any]:
        """Set one pull request to ``closed``; an integrated result fails closed.

        The only field ever sent is ``state``.  There is no code path on this
        class that can integrate a pull request into a branch, and a response
        claiming the pull request was integrated is treated as an error rather
        than as success.
        """

        document = self._request_json(
            "PATCH",
            f"{self.repository_path}/pulls/{self._pull_number(pull_number)}",
            body={"state": "closed"},
        )
        if not isinstance(document, Mapping):
            raise DeliveryRestError("pull request response must be an object")
        if document.get("state") != "closed":
            raise DeliveryRestError("GitHub did not close the pull request")
        if document.get("merged") is True or document.get("merged_at") is not None:
            raise DeliveryRestError("pull request was integrated, not closed")
        return document

    def default_branch(self) -> str:
        """Return the repository default branch; an unreadable one fails closed."""

        document = self._request_json("GET", self.repository_path)
        if not isinstance(document, Mapping):
            raise DeliveryRestError("repository response must be an object")
        name = document.get("default_branch")
        if not isinstance(name, str) or not name.strip():
            raise DeliveryRestError("repository response has no default_branch")
        return name

    def delete_branch(self, branch: str) -> None:
        """Delete exactly one branch ref; only HTTP 204 counts as deleted."""

        self._request(
            "DELETE",
            f"{self.repository_path}/git/refs/heads/{self._branch_ref(branch)}",
            accepted=(204,),
        )
