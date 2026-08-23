"""The production Git push implementation for controlled delivery only.

The legacy :class:`hive_mind_os.github_adapter.GitHubClient` write surface is
quarantined. This executor invokes the existing constrained ``GitWorkspace``
operation directly, but only while an ``EffectGateway``-validated
``github-push`` adapter is active. A direct call therefore fails before reading
a credential or running Git.

The executor never selects a fallback branch. It accepts exactly the branch
the grant adapter has checked and returns only a full lowercase 40-hex SHA.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from hive_mind_os.brain_kernel.effects import require_active_effect_execution
from hive_mind_os.cortex.github.grants import DeliveryGrant, DeliveryGrantError
from hive_mind_os.git_adapter import GitWorkspace
from hive_mind_os.github_adapter import GitHubDeliveryError, MissingGitHubCredential

_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")


class WorkspacePushExecutor:
    """Push one grant-checked branch from one workspace under an effect gateway."""

    def __init__(
        self,
        workspace: GitWorkspace,
        *,
        remote_url: str | Path,
        token_env: str = "GITHUB_TOKEN",
        allow_local_test_remote: bool = False,
    ) -> None:
        if not isinstance(workspace, GitWorkspace):
            raise ValueError("push executor requires a GitWorkspace to push from")
        if not isinstance(token_env, str) or not token_env.strip():
            raise ValueError("push executor requires a credential environment name")
        if not isinstance(remote_url, (str, Path)) or not str(remote_url).strip():
            raise ValueError("push executor requires an explicit remote URL")
        self.workspace = workspace
        self.remote_url = remote_url
        self.token_env = token_env
        # Local bare remotes exist for controlled, socket-free tests only.
        self.allow_local_test_remote = bool(allow_local_test_remote)

    @property
    def network_hosts(self) -> tuple[str, ...]:
        """Hosts reached by the Git half of controlled delivery."""

        parsed = urlsplit(str(self.remote_url))
        if parsed.scheme == "https" and parsed.hostname:
            return (parsed.hostname,)
        return ()

    def push(self, grant: DeliveryGrant, branch: str) -> str:
        """Push one granted branch under an active effect invocation."""

        if not isinstance(grant, DeliveryGrant):
            raise DeliveryGrantError("workspace push requires an immutable delivery grant")
        if not isinstance(branch, str) or not branch.strip():
            raise GitHubDeliveryError("GitHub delivery requires a mission branch")
        grant.require("push")
        grant.require_push_branch(branch)
        require_active_effect_execution(target_adapter="github-push")
        self._require_grant_remote(grant)
        token = os.environ.get(self.token_env, "")
        if not token:
            raise MissingGitHubCredential(
                "required GitHub credential environment variable is missing: "
                f"{self.token_env}"
            )
        head = self.workspace.push_branch(
            self.remote_url,
            token,
            branch=branch,
            allow_local=self.allow_local_test_remote,
        )
        normalized = head.lower() if isinstance(head, str) else ""
        if _FULL_SHA.fullmatch(normalized) is None:
            raise GitHubDeliveryError(
                "GitHub push did not return a full 40-hex head SHA for branch "
                f"{branch}"
            )
        return normalized

    def _require_grant_remote(self, grant: DeliveryGrant) -> None:
        """Bind a production Git remote to the same repository as the grant."""

        parsed = urlsplit(str(self.remote_url))
        if parsed.scheme == "" and self.allow_local_test_remote:
            return
        expected_path = f"/{grant.owner}/{grant.repository}.git"
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.path != expected_path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise DeliveryGrantError(
                "workspace push remote is not the grant's HTTPS GitHub repository"
            )
