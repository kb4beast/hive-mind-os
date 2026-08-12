"""The one production implementation of the delivery ``PushExecutor`` seam.

:class:`hive_mind_os.cortex.github.delivery_adapter.ControlledGitHubDelivery`
declares a ``PushExecutor`` protocol but deliberately owns no Git of its own:
the receipted, policy-authorized push already exists as
:meth:`hive_mind_os.github_adapter.GitHubClient.push_branch`.  This module is
the thin binding between the two, and it is only a binding.  It opens no
socket, runs no Git command, mints no receipt, and makes no authorization
decision -- every one of those stays behind ``push_branch``, which authorizes
:data:`hive_mind_os.policy.Action.OPEN_PULL_REQUEST`, binds the intent to the
committed head, requires a sandbox receipt, and deduplicates through the
mission store.

The two things this module does add are the guarantees the protocol states and
the delegate does not: the branch actually pushed is the branch that was asked
for, never a fallback to whatever the workspace happens to be on, and the value
handed back is a full lowercase 40-hex SHA or an exception.  A malformed head
fails here, at the source, rather than as an opaque rejection one frame later
in ``push_adapter``.
"""

from __future__ import annotations

import re
from pathlib import Path

from hive_mind_os.git_adapter import GitWorkspace
from hive_mind_os.github_adapter import GitHubClient, GitHubDeliveryError

_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")


class WorkspacePushExecutor:
    """Push one granted branch from one workspace and return its head SHA."""

    def __init__(
        self,
        client: GitHubClient,
        workspace: GitWorkspace,
        *,
        remote_url: str | Path | None = None,
        allow_local_test_remote: bool = False,
    ) -> None:
        if not isinstance(client, GitHubClient):
            raise ValueError("push executor requires a GitHubClient delegate")
        if not isinstance(workspace, GitWorkspace):
            raise ValueError("push executor requires a GitWorkspace to push from")
        self.client = client
        self.workspace = workspace
        # None means the delegate's own https://github.com/<owner>/<repo>.git.
        self.remote_url = remote_url
        # Local bare remotes exist for tests only; production pushes leave this
        # False so a non-HTTPS remote is refused by the Git layer.
        self.allow_local_test_remote = bool(allow_local_test_remote)

    def push(self, branch: str) -> str:
        """Delegate the push and return the committed head as lowercase 40-hex.

        Authorization and credential failures are the delegate's to raise and
        are not caught here, so a policy denial stays a
        :class:`~hive_mind_os.github_adapter.GitHubPolicyDenied` and a missing
        token stays a
        :class:`~hive_mind_os.github_adapter.MissingGitHubCredential`.
        """

        if not isinstance(branch, str) or not branch.strip():
            # push_branch would fall back to workspace.branch_name here, which
            # would push a branch nobody granted.  Refuse instead.
            raise GitHubDeliveryError("GitHub delivery requires a mission branch")
        result = self.client.push_branch(
            self.workspace,
            branch=branch,
            remote_url=self.remote_url,
            allow_local_test_remote=self.allow_local_test_remote,
        )
        head = result.head_sha
        normalized = head.lower() if isinstance(head, str) else ""
        if _FULL_SHA.fullmatch(normalized) is None:
            raise GitHubDeliveryError(
                "GitHub push did not return a full 40-hex head SHA for branch "
                f"{branch}"
            )
        return normalized
