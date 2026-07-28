"""Token-safe, idempotent GitHub delivery over the versioned REST API."""

from __future__ import annotations

import json
import os
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .contracts import tool_intent_digest, validate_contract
from .git_adapter import GitWorkspace
from .ledger import EvidenceLedger
from .mission_store import MissionStore, StepCheckpoint
from .models import AutonomyLevel, RiskTier, Role, utc_now
from .policy import Action, PolicyEngine
from .receipts import ReceiptReference, portable_path_parts, sha256_digest

_API_VERSION = "2022-11-28"
_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")
_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
_RUN_URL = re.compile(
    r"(?P<url>https://github\.com/[^/]+/[^/]+/(?:actions/)?runs/(?P<id>\d+))"
)
_SUCCESS_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})


class GitHubDeliveryError(RuntimeError):
    """Base error for external GitHub delivery."""


class MissingGitHubCredential(GitHubDeliveryError):
    """The configured environment variable has no token."""


class GitHubTransportError(GitHubDeliveryError):
    """The REST transport failed or returned an unexpected status."""


class GitHubResponseError(GitHubDeliveryError):
    """A REST response is not valid for the required delivery contract."""


class GitHubPolicyDenied(GitHubDeliveryError):
    """Policy denied delivery before a remote side effect."""


class CheckPollingTimeout(GitHubDeliveryError):
    """Check runs did not reach a terminal state within the bounded poll count."""

    def __init__(self, message: str, receipt: Mapping[str, str]) -> None:
        super().__init__(message)
        self.receipt = dict(receipt)


class CheckRunFailed(GitHubDeliveryError):
    """A completed GitHub check did not have an accepted conclusion."""


@dataclass(frozen=True, slots=True)
class GitHubResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


class GitHubTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> GitHubResponse: ...


class UrllibGitHubTransport:
    def __init__(self, context: ssl.SSLContext | None = None) -> None:
        if context is None:
            context = ssl.create_default_context()
            strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
            if strict:
                context.verify_flags &= ~strict
        self.context = context

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> GitHubResponse:
        request = urllib.request.Request(
            url,
            data=body,
            headers=dict(headers),
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_s,
                context=self.context,
            ) as response:
                return GitHubResponse(
                    int(response.status),
                    response.read(),
                    dict(response.headers.items()),
                )
        except urllib.error.HTTPError as error:
            try:
                return GitHubResponse(
                    int(error.code),
                    error.read(),
                    dict(error.headers.items()) if error.headers else {},
                )
            finally:
                error.close()


@dataclass(frozen=True, slots=True)
class PushResult:
    branch: str
    head_sha: str
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PullRequestResult:
    number: int
    url: str
    head_sha: str
    draft: bool
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    conclusion: str
    started_at: str
    completed_at: str
    workflow_run_id: int
    workflow_run_url: str
    head_sha: str
    json_digest: str
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProtectionReport:
    matches: bool
    desired: dict[str, Any]
    observed: dict[str, Any]
    mismatches: tuple[str, ...]
    evidence_path: str
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class GitHubDelivery:
    push: PushResult
    pull_request: PullRequestResult
    checks: tuple[CheckResult, ...]
    protection: ProtectionReport


@dataclass(frozen=True, slots=True)
class GitHubDeliveryTarget:
    client: GitHubClient
    base: str
    title: str
    body: str
    desired_rules_path: Path
    max_check_attempts: int = 20
    check_interval_s: float = 15.0


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            if path.read_bytes() != content:
                raise GitHubDeliveryError(
                    "content-addressed GitHub evidence path was reused"
                )
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_required_check_names(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("required check names must be a sequence")
    required = tuple(value)
    if (
        not required
        or any(not isinstance(name, str) or not name.strip() for name in required)
        or len(set(required)) != len(required)
    ):
        raise ValueError("required check names must be non-empty, unique strings")
    return required


def _required_string(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GitHubResponseError(f"GitHub response field {field} is required")
    return value


def _required_int(document: Mapping[str, Any], field: str) -> int:
    value = document.get(field)
    if type(value) is not int or value < 1:
        raise GitHubResponseError(f"GitHub response field {field} must be positive")
    return value


class GitHubClient:
    """High-level GitHub delivery with fakeable transport and durable deduplication."""

    def __init__(
        self,
        owner: str,
        repository: str,
        evidence_root: str | Path,
        *,
        transport: GitHubTransport | None = None,
        token_env: str | None = None,
        api_base: str = "https://api.github.com",
        timeout_s: float = 30.0,
        policy: PolicyEngine | None = None,
        ledger: EvidenceLedger | None = None,
        mission_store: MissionStore | None = None,
        mission_id: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        if not _NAME.fullmatch(owner) or not _NAME.fullmatch(repository):
            raise ValueError("GitHub owner and repository must be simple names")
        if not api_base.startswith("https://") or timeout_s <= 0:
            raise ValueError("GitHub API requires HTTPS and a positive timeout")
        self.owner = owner
        self.repository = repository.removesuffix(".git")
        self.evidence_root = Path(evidence_root).resolve()
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.transport = transport or UrllibGitHubTransport()
        self.token_env = token_env or os.environ.get(
            "HIVE_MIND_GITHUB_TOKEN_ENV",
            "GITHUB_TOKEN",
        )
        if not self.token_env.strip():
            raise ValueError("GitHub token environment name is required")
        self.api_base = api_base.rstrip("/")
        self.timeout_s = timeout_s
        self.policy = policy or PolicyEngine(AutonomyLevel.SANDBOX)
        self.ledger = ledger
        self.mission_store = mission_store
        self.mission_id = mission_id
        self.sleep = sleep
        self.clock = clock

    @property
    def remote_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}.git"

    def _token(self) -> str:
        token = os.environ.get(self.token_env, "")
        if not token:
            raise MissingGitHubCredential(
                "required GitHub credential environment variable is missing: "
                f"{self.token_env}"
            )
        return token

    def _authorize(self, action: Action) -> None:
        decision = self.policy.decide(Role.BUILDER, action, RiskTier.MODERATE)
        if self.ledger is not None:
            self.ledger.append_event(
                self.mission_id or "github-delivery",
                "policy.decision",
                Role.BUILDER.value,
                {
                    "action": action.value,
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "autonomy_level": int(self.policy.autonomy),
                },
            )
        if not decision.allowed:
            raise GitHubPolicyDenied(decision.reason)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        accepted: Sequence[int] = (200,),
        optional: Sequence[int] = (),
    ) -> tuple[dict[str, Any] | list[Any] | None, bytes]:
        token = self._token()
        encoded = _canonical_bytes(body) if body is not None else None
        try:
            response = self.transport.request(
                method,
                f"{self.api_base}{path}",
                {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "hive-mind-os-p07",
                    "X-GitHub-Api-Version": _API_VERSION,
                },
                encoded,
                self.timeout_s,
            )
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            message = f"GitHub transport failed: {type(error).__name__}: {error}"
            raise GitHubTransportError(message.replace(token, "[REDACTED]")) from None
        if response.status in optional:
            return None, response.body
        if response.status not in accepted:
            raise GitHubTransportError(
                "GitHub API returned HTTP "
                f"{response.status}; body digest {sha256_digest(response.body)}"
            )
        try:
            document = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubResponseError(
                "GitHub API returned invalid UTF-8 JSON; body digest "
                f"{sha256_digest(response.body)}"
            ) from None
        if not isinstance(document, (dict, list)):
            raise GitHubResponseError("GitHub API response must be an object or array")
        return document, response.body

    def _intent(
        self,
        kind: str,
        description: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        detail_digest = sha256_digest(_canonical_bytes(details))
        suffix = detail_digest.removeprefix("sha256:")
        intent: dict[str, Any] = {
            "schema_version": 1,
            "action_id": f"ACT-P07-{suffix[:24]}",
            "mission_id": self.mission_id or "github-delivery",
            "state_ref": f"MISSION_STATE:{self.mission_id or 'github-delivery'}:1",
            "actor_id": "agent-builder",
            "kind": kind,
            "description": description,
            "action_digest": f"sha256:{'0' * 64}",
            "policy_decision_ref": f"POLICY-P07-{suffix[:24]}",
            "lease_id": f"LEASE-P07-{suffix[:24]}",
            "idempotency_key": f"IDEMPOTENCY-P07-{suffix}",
            "rollback_ref": None,
            "status": "proposed",
        }
        intent["action_digest"] = tool_intent_digest(intent)
        return intent

    def _checkpoint(self, intent: Mapping[str, Any]) -> StepCheckpoint:
        if self.mission_store is None or self.mission_id is None:
            raise GitHubDeliveryError(
                "external side effects require a P06 MissionStore and mission_id"
            )
        return self.mission_store.checkpoint_for_intent(
            self.mission_id,
            intent,
            minimum_step_index=1_000_000,
        )

    def _idempotent_effect(
        self,
        intent: Mapping[str, Any],
        operation: Callable[[], tuple[dict[str, Any], tuple[dict[str, Any], ...]]],
    ) -> dict[str, Any]:
        assert self.mission_store is not None
        checkpoint = self._checkpoint(intent)
        found = self.mission_store.find_effect_receipt(checkpoint)
        if found is not None:
            reference, wrapper = found
            if checkpoint.state != "completed":
                self.mission_store.complete_step(
                    checkpoint,
                    reference,
                    wrapper["outcome"],
                )
            return dict(wrapper["outcome"]["value"])
        self.mission_store.begin_effect(checkpoint.mission_id, checkpoint.step_index)
        value, records = operation()
        outcome = {"value": value, "records": [dict(record) for record in records]}
        reference = self.mission_store.write_effect_receipt(
            checkpoint,
            outcome,
            records,
        )
        self.mission_store.complete_step(checkpoint, reference, outcome)
        return value

    def _persist_tool_receipt(
        self,
        intent: Mapping[str, Any],
        raw: bytes,
        *,
        provider: str,
        verifier: str,
        result: str = "succeeded",
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        artifact_digest = sha256_digest(raw)
        artifact_path = (
            Path("github")
            / "artifacts"
            / f"{artifact_digest.removeprefix('sha256:')}.json"
        )
        _atomic_write(self.evidence_root / artifact_path, raw)
        receipt = {
            "schema_version": 1,
            "receipt_id": (
                "REC-P07-" + str(intent["action_digest"]).removeprefix("sha256:")[:32]
            ),
            "action_id": intent["action_id"],
            "provider": provider,
            "execution_id": (
                "EXEC-P07-" + str(intent["action_digest"]).removeprefix("sha256:")[:32]
            ),
            "mission_id": intent["mission_id"],
            "state_ref": intent["state_ref"],
            "actor_id": intent["actor_id"],
            "policy_decision_ref": intent["policy_decision_ref"],
            "lease_id": intent["lease_id"],
            "action_kind": intent["kind"],
            "action_digest": intent["action_digest"],
            "executed": True,
            "result": result,
            "observed_at": observed_at or self.clock(),
            "artifacts": [
                {
                    "artifact_id": "github-json",
                    "path": artifact_path.as_posix(),
                    "digest": artifact_digest,
                }
            ],
            "verified_by": verifier,
        }
        validation = validate_contract("tool-receipt", receipt)
        if not validation.valid:
            raise GitHubDeliveryError(
                "GitHub receipt violates schema: " + "; ".join(validation.issues)
            )
        encoded = _canonical_bytes(receipt) + b"\n"
        receipt_path = (
            Path("github")
            / "receipts"
            / (str(intent["action_digest"]).removeprefix("sha256:") + ".json")
        )
        _atomic_write(self.evidence_root / receipt_path, encoded)
        return {
            "path": receipt_path.as_posix(),
            "digest": sha256_digest(encoded),
            "mission_id": receipt["mission_id"],
            "state_ref": receipt["state_ref"],
            "actor_id": receipt["actor_id"],
            "action_id": receipt["action_id"],
            "action_kind": receipt["action_kind"],
            "action_digest": receipt["action_digest"],
            "result": receipt["result"],
        }

    def push_branch(
        self,
        workspace: GitWorkspace,
        *,
        branch: str | None = None,
        remote_url: str | Path | None = None,
        allow_local_test_remote: bool = False,
    ) -> PushResult:
        self._authorize(Action.OPEN_PULL_REQUEST)
        target_branch = branch or workspace.branch_name
        if target_branch is None:
            raise GitHubDeliveryError("GitHub delivery requires a mission branch")
        head_sha = workspace._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "bind GitHub push intent to committed head",
        )
        intent = self._intent(
            "git",
            "push exact mission branch to GitHub",
            {
                "owner": self.owner,
                "repository": self.repository,
                "branch": target_branch,
                "head_sha": head_sha,
            },
        )

        def operation() -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
            before = len(workspace.receipt_records)
            observed_head = workspace.push_branch(
                remote_url or self.remote_url,
                self._token(),
                branch=target_branch,
                allow_local=allow_local_test_remote,
            )
            records = tuple(
                dict(record) for record in workspace.receipt_records[before:]
            )
            if not records:
                raise GitHubDeliveryError("Git push produced no sandbox receipt")
            return (
                {
                    "branch": target_branch,
                    "head_sha": observed_head,
                    "receipt": dict(records[-1]),
                },
                records,
            )

        value = self._idempotent_effect(intent, operation)
        return PushResult(
            _required_string(value, "branch"),
            _required_string(value, "head_sha"),
            dict(value["receipt"]),
        )

    def open_draft_pr(
        self,
        *,
        branch: str,
        base: str,
        head_sha: str,
        title: str,
        body: str,
    ) -> PullRequestResult:
        self._authorize(Action.OPEN_PULL_REQUEST)
        if not title.strip() or not body.strip() or not _FULL_SHA.fullmatch(head_sha):
            raise ValueError("draft PR title, body, and full head SHA are required")
        intent = self._intent(
            "network",
            "open draft GitHub pull request",
            {
                "owner": self.owner,
                "repository": self.repository,
                "base": base,
                "branch": branch,
                "head_sha": head_sha,
                "title": title,
                "body_digest": sha256_digest(body.encode("utf-8")),
                "draft": True,
            },
        )

        def operation() -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
            query = urllib.parse.urlencode(
                {
                    "state": "open",
                    "head": f"{self.owner}:{branch}",
                    "base": base,
                }
            )
            existing, raw = self._request_json(
                "GET",
                f"/repos/{self.owner}/{self.repository}/pulls?{query}",
            )
            selected: Mapping[str, Any] | None = None
            if isinstance(existing, list):
                for candidate in existing:
                    if not isinstance(candidate, Mapping):
                        continue
                    head = candidate.get("head")
                    if (
                        candidate.get("draft") is True
                        and isinstance(head, Mapping)
                        and head.get("sha") == head_sha
                    ):
                        selected = candidate
                        raw = _canonical_bytes(candidate)
                        break
            if selected is None:
                created, raw = self._request_json(
                    "POST",
                    f"/repos/{self.owner}/{self.repository}/pulls",
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
                if not isinstance(created, Mapping):
                    raise GitHubResponseError(
                        "create pull request response must be an object"
                    )
                selected = created
            head = selected.get("head")
            if not isinstance(head, Mapping) or head.get("sha") != head_sha:
                raise GitHubResponseError("draft PR response is not bound to head SHA")
            if selected.get("draft") is not True:
                raise GitHubResponseError("GitHub delivery created a non-draft PR")
            receipt = self._persist_tool_receipt(
                intent,
                raw,
                provider="github-rest-api",
                verifier="github-rest-tls-observer-v1",
            )
            return (
                {
                    "number": _required_int(selected, "number"),
                    "url": _required_string(selected, "html_url"),
                    "head_sha": head_sha,
                    "draft": True,
                    "receipt": receipt,
                },
                (receipt,),
            )

        value = self._idempotent_effect(intent, operation)
        return PullRequestResult(
            _required_int(value, "number"),
            _required_string(value, "url"),
            _required_string(value, "head_sha"),
            value.get("draft") is True,
            dict(value["receipt"]),
        )

    def _check_result(
        self,
        check: Mapping[str, Any],
        *,
        head_sha: str,
    ) -> CheckResult:
        details_url = _required_string(check, "details_url")
        run_match = _RUN_URL.search(details_url)
        if run_match is None:
            raise GitHubResponseError(
                "GitHub Actions check lacks a workflow run id and URL"
            )
        conclusion = _required_string(check, "conclusion")
        started_at = _required_string(check, "started_at")
        completed_at = _required_string(check, "completed_at")
        check_bytes = _canonical_bytes(check)
        intent = self._intent(
            "network",
            "observe completed GitHub Actions check",
            {
                "check_id": _required_int(check, "id"),
                "name": _required_string(check, "name"),
                "head_sha": head_sha,
                "conclusion": conclusion,
            },
        )
        receipt = self._persist_tool_receipt(
            intent,
            check_bytes,
            provider="github-actions",
            verifier="github-actions",
            result=("succeeded" if conclusion in _SUCCESS_CONCLUSIONS else "failed"),
            observed_at=completed_at,
        )
        return CheckResult(
            _required_string(check, "name"),
            _required_string(check, "status"),
            conclusion,
            started_at,
            completed_at,
            int(run_match.group("id")),
            run_match.group("url"),
            head_sha,
            sha256_digest(check_bytes),
            receipt,
        )

    def poll_checks(
        self,
        head_sha: str,
        *,
        required_check_names: Sequence[str],
        max_attempts: int = 20,
        interval_s: float = 15.0,
    ) -> tuple[CheckResult, ...]:
        if not _FULL_SHA.fullmatch(head_sha):
            raise ValueError("check polling requires a full lowercase head SHA")
        if max_attempts < 1 or interval_s < 0:
            raise ValueError("check polling bounds are invalid")
        required = _normalize_required_check_names(required_check_names)
        last_raw = b"{}"
        last_checks: list[Any] = []
        missing_required = sorted(required)
        nonterminal_required: list[str] = []
        for attempt in range(max_attempts):
            document, last_raw = self._request_json(
                "GET",
                (
                    f"/repos/{self.owner}/{self.repository}/commits/"
                    f"{head_sha}/check-runs?filter=latest&per_page=100"
                ),
            )
            if not isinstance(document, Mapping):
                raise GitHubResponseError("check-runs response must be an object")
            raw_checks = document.get("check_runs")
            if not isinstance(raw_checks, list):
                raise GitHubResponseError("check-runs response lacks check_runs")
            last_checks = raw_checks
            if any(not isinstance(check, Mapping) for check in raw_checks):
                raise GitHubResponseError(
                    "check-runs response contains a non-object check"
                )
            observed_names = {_required_string(check, "name") for check in raw_checks}
            missing_required = sorted(set(required) - observed_names)
            nonterminal_required = sorted(
                name
                for name in required
                if any(
                    check.get("name") == name and check.get("status") != "completed"
                    for check in raw_checks
                )
            )
            if raw_checks and all(
                check.get("status") == "completed" for check in raw_checks
            ):
                results = tuple(
                    self._check_result(check, head_sha=head_sha) for check in raw_checks
                )
                failures = [
                    result
                    for result in results
                    if result.conclusion not in _SUCCESS_CONCLUSIONS
                ]
                if failures:
                    names = ", ".join(result.name for result in failures)
                    raise CheckRunFailed(f"GitHub checks failed: {names}")
                if not missing_required:
                    return results
            if attempt + 1 < max_attempts:
                self.sleep(interval_s)
        intent = self._intent(
            "network",
            "observe GitHub Actions check timeout",
            {
                "head_sha": head_sha,
                "attempts": max_attempts,
                "observed_check_count": len(last_checks),
                "missing_required_checks": missing_required,
                "nonterminal_required_checks": nonterminal_required,
            },
        )
        receipt = self._persist_tool_receipt(
            intent,
            last_raw,
            provider="github-actions",
            verifier="github-actions",
            result="failed",
        )
        details = []
        if missing_required:
            details.append("missing=" + ", ".join(missing_required))
        if nonterminal_required:
            details.append("nonterminal=" + ", ".join(nonterminal_required))
        suffix = f" ({'; '.join(details)})" if details else ""
        raise CheckPollingTimeout(
            (f"GitHub checks did not complete after {max_attempts} attempts{suffix}"),
            {
                "path": ReceiptReference(
                    receipt["path"],
                    receipt["digest"],
                ).path,
                "digest": receipt["digest"],
            },
        )

    @staticmethod
    def _ruleset_observation(
        rulesets: Sequence[Mapping[str, Any]],
        branch: str,
    ) -> dict[str, Any]:
        candidates: list[Mapping[str, Any]] = []
        target = f"refs/heads/{branch}"
        for ruleset in rulesets:
            conditions = ruleset.get("conditions")
            if not isinstance(conditions, Mapping):
                continue
            ref_name = conditions.get("ref_name")
            if not isinstance(ref_name, Mapping):
                continue
            includes = ref_name.get("include")
            excludes = ref_name.get("exclude")
            if (
                ruleset.get("enforcement") != "active"
                or not isinstance(includes, list)
                or not includes
                or not all(isinstance(item, str) for item in includes)
                or not isinstance(excludes, list)
                or not all(isinstance(item, str) for item in excludes)
            ):
                continue
            included = target in includes or "~DEFAULT_BRANCH" in includes
            excluded = target in excludes or "~DEFAULT_BRANCH" in excludes
            ambiguous_exclusion = any(
                any(marker in item for marker in ("*", "?", "[")) for item in excludes
            )
            if included and not excluded and not ambiguous_exclusion:
                candidates.append(ruleset)
        rules: list[Mapping[str, Any]] = []
        for ruleset in candidates:
            raw_rules = ruleset.get("rules")
            if not isinstance(raw_rules, list):
                continue
            rules.extend(rule for rule in raw_rules if isinstance(rule, Mapping))
        by_type = {
            str(rule.get("type")): rule
            for rule in rules
            if isinstance(rule.get("type"), str)
        }
        pull = by_type.get("pull_request", {}).get("parameters", {})
        status = by_type.get("required_status_checks", {}).get("parameters", {})
        raw_status_values = (
            status.get("required_status_checks")
            if isinstance(status, Mapping)
            else None
        )
        status_values = raw_status_values if isinstance(raw_status_values, list) else []
        contexts = sorted(
            {
                str(item.get("context"))
                for item in status_values
                if isinstance(item, Mapping) and isinstance(item.get("context"), str)
            }
        )
        return {
            "active": bool(candidates),
            "enforce_admins": (
                all(
                    isinstance(ruleset.get("bypass_actors"), list)
                    and not ruleset["bypass_actors"]
                    for ruleset in candidates
                )
                if candidates
                else False
            ),
            "deletion": "blocked" if "deletion" in by_type else "unknown",
            "force_push": ("blocked" if "non_fast_forward" in by_type else "unknown"),
            "required_linear_history": "required_linear_history" in by_type,
            "required_signed_commits": "required_signatures" in by_type,
            "pull_request": {
                "required_approving_review_count": (
                    pull.get("required_approving_review_count")
                    if isinstance(pull, Mapping)
                    else None
                ),
                "require_code_owner_review": (
                    pull.get("require_code_owner_review")
                    if isinstance(pull, Mapping)
                    else None
                ),
                "dismiss_stale_reviews_on_push": (
                    pull.get("dismiss_stale_reviews_on_push")
                    if isinstance(pull, Mapping)
                    else None
                ),
                "require_last_push_approval": (
                    pull.get("require_last_push_approval")
                    if isinstance(pull, Mapping)
                    else None
                ),
                "required_review_thread_resolution": (
                    pull.get("required_review_thread_resolution")
                    if isinstance(pull, Mapping)
                    else None
                ),
            },
            "required_status_checks": contexts,
        }

    @staticmethod
    def _branch_observation(protection: Mapping[str, Any] | None) -> dict[str, Any]:
        if protection is None:
            return {"active": False}
        reviews = protection.get("required_pull_request_reviews")
        status = protection.get("required_status_checks")
        contexts = status.get("contexts") if isinstance(status, Mapping) else []
        return {
            "active": True,
            "enforce_admins": (
                isinstance(protection.get("enforce_admins"), Mapping)
                and protection["enforce_admins"].get("enabled") is True
            ),
            "deletion": (
                "allowed"
                if isinstance(protection.get("allow_deletions"), Mapping)
                and protection["allow_deletions"].get("enabled") is True
                else "blocked"
            ),
            "force_push": (
                "allowed"
                if isinstance(protection.get("allow_force_pushes"), Mapping)
                and protection["allow_force_pushes"].get("enabled") is True
                else "blocked"
            ),
            "required_linear_history": (
                isinstance(protection.get("required_linear_history"), Mapping)
                and protection["required_linear_history"].get("enabled") is True
            ),
            "required_signed_commits": (
                isinstance(protection.get("required_signatures"), Mapping)
                and protection["required_signatures"].get("enabled") is True
            ),
            "pull_request": {
                "required_approving_review_count": (
                    reviews.get("required_approving_review_count")
                    if isinstance(reviews, Mapping)
                    else None
                ),
                "require_code_owner_review": (
                    reviews.get("require_code_owner_reviews")
                    if isinstance(reviews, Mapping)
                    else None
                ),
                "dismiss_stale_reviews_on_push": (
                    reviews.get("dismiss_stale_reviews")
                    if isinstance(reviews, Mapping)
                    else None
                ),
                "require_last_push_approval": (
                    reviews.get("require_last_push_approval")
                    if isinstance(reviews, Mapping)
                    else None
                ),
                "required_review_thread_resolution": (
                    protection.get("required_conversation_resolution", {}).get(
                        "enabled"
                    )
                    if isinstance(
                        protection.get("required_conversation_resolution"),
                        Mapping,
                    )
                    else None
                ),
            },
            "required_status_checks": (
                sorted(str(item) for item in contexts)
                if isinstance(contexts, list)
                else []
            ),
        }

    @staticmethod
    def _merge_observations(
        ruleset: Mapping[str, Any],
        branch: Mapping[str, Any],
    ) -> dict[str, Any]:
        if ruleset.get("active") is True:
            merged = json.loads(json.dumps(ruleset))
            branch_pull = branch.get("pull_request")
            merged_pull = merged.get("pull_request")
            if isinstance(branch_pull, Mapping) and isinstance(merged_pull, dict):
                for key, value in branch_pull.items():
                    if merged_pull.get(key) is None:
                        merged_pull[key] = value
            for key, value in branch.items():
                if key not in merged or (
                    isinstance(merged[key], (str, bool, type(None)))
                    and merged[key] in {None, "unknown", False}
                ):
                    merged[key] = value
            return merged
        return dict(branch)

    @staticmethod
    def _compare(
        expected: object,
        observed: object,
        path: str,
    ) -> list[str]:
        if isinstance(expected, Mapping):
            if not isinstance(observed, Mapping):
                return [f"{path}: expected object"]
            issues: list[str] = []
            for key, value in expected.items():
                child = f"{path}.{key}" if path else str(key)
                issues.extend(GitHubClient._compare(value, observed.get(key), child))
            return issues
        if isinstance(expected, list):
            if not isinstance(observed, list) or sorted(expected) != sorted(observed):
                return [f"{path}: mismatch"]
            return []
        return [] if expected == observed else [f"{path}: mismatch"]

    def verify_protection(
        self,
        desired_rules_path: str | Path,
        *,
        branch: str = "main",
    ) -> ProtectionReport:
        desired = json.loads(Path(desired_rules_path).read_text(encoding="utf-8"))
        if not isinstance(desired, dict) or not isinstance(
            desired.get("rules"),
            dict,
        ):
            raise ValueError("declared repository rules are malformed")
        listed, rulesets_raw = self._request_json(
            "GET",
            (
                f"/repos/{self.owner}/{self.repository}/rulesets"
                "?includes_parents=true&targets=branch"
            ),
        )
        rulesets: list[Mapping[str, Any]] = []
        if isinstance(listed, list):
            for summary in listed:
                if not isinstance(summary, Mapping):
                    continue
                ruleset_id = summary.get("id")
                if type(ruleset_id) is not int:
                    continue
                detail, _ = self._request_json(
                    "GET",
                    f"/repos/{self.owner}/{self.repository}/rulesets/{ruleset_id}",
                )
                if isinstance(detail, Mapping):
                    rulesets.append(detail)
        protection, protection_raw = self._request_json(
            "GET",
            (
                f"/repos/{self.owner}/{self.repository}/branches/"
                f"{urllib.parse.quote(branch, safe='')}/protection"
            ),
            optional=(404,),
        )
        branch_document = protection if isinstance(protection, Mapping) else None
        observed = self._merge_observations(
            self._ruleset_observation(rulesets, branch),
            self._branch_observation(branch_document),
        )
        expected = {
            "active": desired.get("required_host_enforcement") == "active",
            **desired["rules"],
        }
        mismatches = tuple(self._compare(expected, observed, "rules"))
        report_document = {
            "schema_version": 1,
            "artifact_type": "GitHubProtectionReport",
            "owner": self.owner,
            "repository": self.repository,
            "branch": branch,
            "generated_at": self.clock(),
            "matches": not mismatches,
            "desired": desired,
            "observed": observed,
            "mismatches": list(mismatches),
            "rulesets_response_digest": sha256_digest(rulesets_raw),
            "protection_response_digest": sha256_digest(protection_raw),
        }
        encoded = _canonical_bytes(report_document) + b"\n"
        digest = sha256_digest(encoded)
        relative = (
            Path("github") / "protection" / f"{digest.removeprefix('sha256:')}.json"
        )
        _atomic_write(self.evidence_root / relative, encoded)
        return ProtectionReport(
            not mismatches,
            desired,
            observed,
            mismatches,
            relative.as_posix(),
            digest,
        )

    def deliver(
        self,
        workspace: GitWorkspace,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
        desired_rules_path: str | Path,
        max_check_attempts: int = 20,
        check_interval_s: float = 15.0,
    ) -> GitHubDelivery:
        desired = json.loads(Path(desired_rules_path).read_text(encoding="utf-8"))
        rules = desired.get("rules") if isinstance(desired, Mapping) else None
        required_check_names = (
            rules.get("required_status_checks") if isinstance(rules, Mapping) else None
        )
        required_check_names = _normalize_required_check_names(required_check_names)
        push = self.push_branch(workspace, branch=branch)
        pull_request = self.open_draft_pr(
            branch=branch,
            base=base,
            head_sha=push.head_sha,
            title=title,
            body=body,
        )
        checks = self.poll_checks(
            push.head_sha,
            required_check_names=required_check_names,
            max_attempts=max_check_attempts,
            interval_s=check_interval_s,
        )
        protection = self.verify_protection(desired_rules_path, branch=base)
        return GitHubDelivery(push, pull_request, checks, protection)


def validate_github_receipt(
    evidence_root: str | Path,
    record: Mapping[str, Any],
) -> bool:
    """Validate one GitHub receipt without trusting client memory."""

    from .receipts import FileReceiptValidator

    try:
        path = Path(evidence_root) / Path(*portable_path_parts(str(record["path"])))
        if not path.is_file():
            return False
        validation = FileReceiptValidator(evidence_root).validate(
            ReceiptReference(str(record["path"]), str(record["digest"])),
            mission_id=str(record["mission_id"]),
            state_ref=str(record["state_ref"]),
            actor_id=str(record["actor_id"]),
            action_id=str(record["action_id"]),
            action_kind=str(record["action_kind"]),
            action_digest=str(record["action_digest"]),
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return validation.valid
