"""Deterministic implementation control plane for the Hive Mind OS autonomy program.

This module coordinates repository implementation work. It is not the Hive Mind OS
product runtime. It intentionally uses only the Python standard library so the control
plane remains inspectable, portable, and independent of model providers.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = 1
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
ROLE_NAMES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)
UNSAFE_REMEDIATION_MARKERS = (
    "disable tls",
    "skip tls",
    "disable certificate",
    "skip certificate",
    "disable revocation",
    "skip revocation",
    "sslverify=false",
    "verify=false",
    "ignore certificate",
)
SUBTASK_EXECUTION_SEQUENCE = (
    "fetch_current_singleton_release",
    "install_current_github_snapshot",
    "reconcile_target",
    "run_doctor_and_status",
    "dispatch_explicit_start_now",
    "claim_remote_node_branch",
)
STALE_TARGET_RECOVERY_SEQUENCE = (
    "preserve_scoped_work_with_node_named_stash",
    "verify_current_singleton_remote_sha",
    "refresh_validated_github_snapshot",
    "archive_stale_runtime_projection",
    "retire_exact_stale_remote_claim_ref",
    "install_snapshot_and_reconcile",
    "doctor_status_dispatch_and_reclaim",
    "apply_exact_node_named_stash",
    "verify_changed_paths_against_node_scope",
)
SAFE_GIT_TRANSPORT_ENVIRONMENT_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
SUBTASK_STATES = frozenset(
    {
        "PENDING",
        "ACTIVE",
        "IDLE_UNCOLLECTED",
        "BLOCKED_RECOVERABLE",
        "SUCCEEDED",
        "BLOCKED_EXTERNAL_AUTHORITY",
    }
)
SUBTASK_SETTLED_STATES = frozenset({"SUCCEEDED", "BLOCKED_EXTERNAL_AUTHORITY"})
LEGAL_STATES = (
    "BOOTSTRAP_REQUIRED",
    "BOOTSTRAP_INVALID",
    "READY",
    "CLAIMED",
    "RUNNING",
    "WAITING_FOR_RECEIPT",
    "PR_OPEN",
    "CI_FAILED",
    "REPAIR_REQUIRED",
    "RECONCILIATION_REQUIRED",
    "INTEGRATION_READY",
    "INTEGRATING",
    "PROMOTION_READY",
    "BLOCKED",
    "ESCALATION_REQUIRED",
    "QUARANTINED",
    "COMPLETE",
    "SUPERSEDED",
    "CANCELLED",
    "REPLAN_REQUIRED",
)
TERMINAL_STATES = {
    "COMPLETE",
    "SUPERSEDED",
    "CANCELLED",
    "QUARANTINED",
}
HUMAN_AUTHORITY_CLASSES = {
    "credential_or_secret",
    "legal_or_regulatory_signoff",
    "financial_spend",
    "production_access",
    "protected_branch_merge",
    "owner_value_choice",
    "personal_consent",
    "external_contractual_commitment",
}
CONSULTATION_DECISIONS = {
    "RESOLVED",
    "REMAND",
    "REPLAN",
    "BLOCKED_EVIDENCE",
    "TRUE_AUTHORITY_REQUIRED",
    "QUARANTINE",
}
CHEATING_DISPOSITIONS = {"NOT_APPLICABLE", "CONFIRMED", "DISPROVED", "UNRESOLVED"}


class AutopilotError(RuntimeError):
    """The deterministic control plane cannot safely continue."""


class ConfigurationError(AutopilotError):
    """Repository-resident control-plane configuration is invalid."""


class ClaimError(AutopilotError):
    """A node claim or lease operation is invalid."""


class ReceiptError(AutopilotError):
    """A node completion receipt is invalid."""


@dataclass(frozen=True, slots=True)
class NodeView:
    node_id: str
    state: str
    reasons: tuple[str, ...]
    dependencies: tuple[str, ...]
    active_claim_owner: str | None = None
    branch: str | None = None
    pr_number: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be non-empty text")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_json(value: object) -> str:
    return "sha256:" + sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"required file is missing: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot parse JSON file {path}: {error}") from error


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(encoded)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def append_jsonl(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(value), ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def normalize_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be non-empty text")
    raw = value.replace("\\", "/").strip()
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError("absolute paths are prohibited")
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("path traversal is prohibited")
        parts.append(part)
    if not parts:
        raise ValueError("path cannot normalize to repository root")
    return "/".join(parts)


def _scope_static_prefix(scope: str) -> str:
    normalized = scope.replace("\\", "/").strip().rstrip("/")
    wildcard_index = min(
        (index for marker in ("*", "?", "[") if (index := normalized.find(marker)) >= 0),
        default=len(normalized),
    )
    prefix = normalized[:wildcard_index].rstrip("/")
    if not prefix:
        raise ValueError("scope wildcard must retain a repository-relative prefix")
    return normalize_path(prefix)


def path_matches_scope(path: str, scope: str) -> bool:
    normalized_path = normalize_path(path)
    normalized_scope = scope.replace("\\", "/").strip().rstrip("/")
    if any(marker in normalized_scope for marker in ("*", "?", "[")):
        # ``fnmatch`` gives exact portable glob semantics. ``/**`` additionally
        # includes the named root itself so directory-scoped locks remain useful.
        if normalized_scope.endswith("/**"):
            root = normalize_path(normalized_scope[:-3])
            if normalized_path == root:
                return True
        return fnmatch.fnmatchcase(normalized_path, normalized_scope)
    root = normalize_path(normalized_scope)
    return normalized_path == root or normalized_path.startswith(root + "/")


def scopes_overlap(first: str, second: str) -> bool:
    first_root = _scope_static_prefix(first)
    second_root = _scope_static_prefix(second)
    if (
        first_root == second_root
        or first_root.startswith(second_root + "/")
        or second_root.startswith(first_root + "/")
    ):
        return True
    # Distinct sibling glob scopes may still collide on one concrete path. Probe the
    # static prefixes against both patterns without claiming disjointness from names.
    return path_matches_scope(first_root, second) or path_matches_scope(second_root, first)


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{label} must be a list")
    return value


def _require_nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be non-empty text")
    return value.strip()


class ControlPlane:
    """Read, validate, and mutate deterministic implementation-plan state."""

    REQUIRED_FILES = (
        ".autopilot/README.md",
        ".autopilot/plan.json",
        ".autopilot/control-plane.json",
        ".autopilot/provider-catalog.json",
        ".autopilot/model-routing.json",
        ".autopilot/receipt.schema.json",
        ".autopilot/consultation.schema.json",
        ".autopilot/role-wiring.schema.json",
        ".autopilot/acceptance-matrix.json",
        ".autopilot/templates/worker.md",
        ".autopilot/templates/repair.md",
        ".autopilot/templates/consultation.md",
        ".autopilot/templates/reconciliation.md",
        ".autopilot/templates/integration.md",
        ".autopilot/templates/promotion.md",
        ".autopilot/templates/replan.md",
        ".autopilot/templates/human-escalation.md",
    )

    def __init__(
        self,
        repo_root: str | Path,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.ap_root = self.repo_root / ".autopilot"
        self.clock = clock
        self.plan_path = self.ap_root / "plan.json"
        self.control_path = self.ap_root / "control-plane.json"
        self.provider_path = self.ap_root / "provider-catalog.json"
        self.routing_path = self.ap_root / "model-routing.json"
        self.role_matrix_path = self.ap_root / "role-wiring.json"
        self.acceptance_path = self.ap_root / "acceptance-matrix.json"
        self.state_dir = self.ap_root / "state"
        self.claims_dir = self.state_dir / "claims"
        self.receipts_dir = self.state_dir / "receipts"
        self.failures_dir = self.state_dir / "failures"
        self.blockers_dir = self.state_dir / "blockers"
        self.questions_dir = self.state_dir / "questions"
        self.subtask_waves_dir = self.state_dir / "subtask-waves"
        self.validation_lease_path = self.state_dir / "global-validation-lease.json"
        self.quarantine_dir = self.state_dir / "quarantine"
        self.escalations_dir = self.state_dir / "escalations"
        self.plan = _require_mapping(read_json(self.plan_path), "plan")
        self.control = _require_mapping(read_json(self.control_path), "control plane")
        self.provider_catalog = _require_mapping(
            read_json(self.provider_path), "provider catalog"
        )
        self.model_routing = _require_mapping(
            read_json(self.routing_path), "model routing"
        )
        self.role_matrix = _require_mapping(
            read_json(self.role_matrix_path), "role wiring matrix"
        )
        self.acceptance_matrix = _require_mapping(
            read_json(self.acceptance_path), "acceptance matrix"
        )
        self._nodes = {
            str(node["id"]): node
            for node in _require_list(self.plan.get("nodes"), "plan.nodes")
            if isinstance(node, Mapping) and "id" in node
        }

    @property
    def plan_fingerprint(self) -> str:
        document = dict(self.plan)
        document.pop("plan_fingerprint", None)
        return digest_json(document)

    @property
    def expected_plan_fingerprint(self) -> str:
        return _require_nonempty_text(
            self.control.get("plan_fingerprint"),
            "control-plane.plan_fingerprint",
        )

    @property
    def target_branch(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        return _require_nonempty_text(target.get("branch"), "target.branch")

    @property
    def final_integration_branch(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        return _require_nonempty_text(
            target.get("final_integration_branch"),
            "target.final_integration_branch",
        )

    @property
    def execution_mode(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        mode = _require_nonempty_text(target.get("execution_mode"), "target.execution_mode")
        if mode != "singleton-release-branch":
            raise ConfigurationError("target.execution_mode must be singleton-release-branch")
        if self.target_branch == self.final_integration_branch:
            raise ConfigurationError("singleton release target must not equal final integration branch")
        return mode

    @property
    def baseline_sha(self) -> str:
        target = _require_mapping(self.control.get("target"), "control-plane.target")
        sha = _require_nonempty_text(target.get("baseline_sha"), "target.baseline_sha")
        if FULL_SHA.fullmatch(sha) is None:
            raise ConfigurationError("target.baseline_sha must be a full lowercase Git SHA")
        return sha

    @property
    def verify_git_objects(self) -> bool:
        value = self.control.get("verify_git_objects", True)
        if not isinstance(value, bool):
            raise ConfigurationError("verify_git_objects must be boolean")
        return value

    def node(self, node_id: str) -> Mapping[str, Any]:
        try:
            return self._nodes[node_id]
        except KeyError as error:
            raise AutopilotError(f"unknown node: {node_id}") from error

    def nodes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._nodes[node_id] for node_id in sorted(self._nodes))

    def validate_configuration(self) -> tuple[str, ...]:
        issues: list[str] = []
        try:
            self.execution_mode
            target = _require_mapping(self.control.get("target"), "control-plane.target")
            protected = target.get("protected_until_final_integration")
            if protected != [self.final_integration_branch]:
                issues.append("target.protected_until_final_integration must protect final integration branch")
            release_base = target.get("release_branch_base")
            if not isinstance(release_base, str) or FULL_SHA.fullmatch(release_base) is None:
                issues.append("target.release_branch_base must be a full lowercase Git SHA")
        except ConfigurationError as error:
            issues.append(str(error))
        if self.plan.get("schema_version") != SCHEMA_VERSION:
            issues.append("plan schema_version is unsupported")
        if self.control.get("schema_version") != SCHEMA_VERSION:
            issues.append("control-plane schema_version is unsupported")
        if self.plan_fingerprint != self.expected_plan_fingerprint:
            issues.append(
                "plan fingerprint mismatch: expected "
                f"{self.expected_plan_fingerprint}, observed {self.plan_fingerprint}"
            )
        raw_nodes = _require_list(self.plan.get("nodes"), "plan.nodes")
        observed_ids = [
            str(item.get("id"))
            for item in raw_nodes
            if isinstance(item, Mapping)
        ]
        if len(observed_ids) != len(set(observed_ids)):
            issues.append("node IDs are not unique")
        if len(self._nodes) != len(raw_nodes):
            issues.append("every node must be an object with an id")
        dependencies: dict[str, tuple[str, ...]] = {}
        for node_id, node in self._nodes.items():
            issues.extend(self._validate_node(node_id, node))
            deps = node.get("dependencies", [])
            if not isinstance(deps, list) or any(not isinstance(item, str) for item in deps):
                issues.append(f"{node_id}: dependencies must be a string list")
                continue
            dependencies[node_id] = tuple(deps)
            for dependency in deps:
                if dependency not in self._nodes:
                    issues.append(f"{node_id}: unknown dependency {dependency}")
        cycle = self._find_cycle(dependencies)
        if cycle:
            issues.append("dependency cycle: " + " -> ".join(cycle))
        tiers = self.provider_catalog.get("tiers")
        if not isinstance(tiers, Mapping):
            issues.append("provider catalog tiers must be an object")
            tiers = {}
        for tier in ("T0", "T1", "T2", "T3", "T4"):
            route = tiers.get(tier)
            if not isinstance(route, Mapping):
                issues.append(f"provider route missing for {tier}")
                continue
            for provider in ("openai", "anthropic"):
                provider_route = route.get(provider)
                if not isinstance(provider_route, Mapping):
                    issues.append(f"provider route {tier}.{provider} is missing")
                elif not isinstance(provider_route.get("model"), str):
                    issues.append(f"provider route {tier}.{provider}.model is missing")
        role_rows = self.role_matrix.get("roles")
        if not isinstance(role_rows, list):
            issues.append("role-wiring roles must be a list")
        else:
            role_names = {
                row.get("role") for row in role_rows if isinstance(row, Mapping)
            }
            if role_names != set(ROLE_NAMES):
                issues.append("role-wiring matrix must contain exactly all eight roles")
        required_acceptance = {
            "all_role",
            "humanless_operation",
            "no_cheating",
            "learning",
            "self_healing",
            "repository_safety",
            "staged_autonomy",
        }
        acceptance_suites = self.acceptance_matrix.get("suites")
        if not isinstance(acceptance_suites, Mapping):
            issues.append("acceptance matrix suites must be an object")
        elif not required_acceptance.issubset(acceptance_suites):
            issues.append("acceptance matrix omits required suites")
        for relative in self.REQUIRED_FILES:
            if not (self.repo_root / relative).is_file():
                issues.append(f"required root file is missing: {relative}")
        nested = self.repo_root / "REPO_ROOT" / ".autopilot"
        if nested.exists():
            issues.append(
                "archive-only installation detected: REPO_ROOT contents were not installed "
                "into repository-root paths"
            )
        return tuple(dict.fromkeys(issues))

    def _validate_node(
        self, node_id: str, node: Mapping[str, Any]
    ) -> tuple[str, ...]:
        issues: list[str] = []
        required_text = (
            "objective",
            "rationale",
            "branch",
            "pr_target",
            "risk",
            "reversibility",
            "rollback",
            "stopping_condition",
        )
        for key in required_text:
            if not isinstance(node.get(key), str) or not str(node.get(key)).strip():
                issues.append(f"{node_id}: {key} must be non-empty text")
        if node.get("contract_version") != 1:
            issues.append(f"{node_id}: contract_version must be 1")
        list_fields = (
            "dependencies",
            "assumptions",
            "required_inputs",
            "expected_outputs",
            "interfaces",
            "read_scope",
            "write_scope",
            "forbidden_scope",
            "roles",
            "consultation_routes",
            "acceptance_criteria",
            "required_tests",
            "evidence_requirements",
            "file_locks",
            "semantic_locks",
            "escalation_conditions",
        )
        for key in list_fields:
            value = node.get(key)
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                issues.append(f"{node_id}: {key} must be a string list")
        roles = node.get("roles")
        if isinstance(roles, list) and not set(roles).issubset(ROLE_NAMES):
            issues.append(f"{node_id}: roles contain an unknown role")
        routes = node.get("routes")
        if not isinstance(routes, Mapping):
            issues.append(f"{node_id}: routes must be an object")
        else:
            tier = routes.get("tier")
            if tier not in {"T0", "T1", "T2", "T3", "T4"}:
                issues.append(f"{node_id}: routes.tier is invalid")
            for provider in ("openai", "anthropic"):
                route = routes.get(provider)
                if not isinstance(route, Mapping):
                    issues.append(f"{node_id}: routes.{provider} is missing")
                else:
                    if not isinstance(route.get("model"), str):
                        issues.append(f"{node_id}: routes.{provider}.model missing")
                    if not isinstance(route.get("reasoning_effort"), str):
                        issues.append(
                            f"{node_id}: routes.{provider}.reasoning_effort missing"
                        )
        for scope_key in ("read_scope", "write_scope", "forbidden_scope", "file_locks"):
            scopes = node.get(scope_key)
            if isinstance(scopes, list):
                for scope in scopes:
                    try:
                        normalize_path(str(scope).removesuffix("/**"))
                    except ValueError as error:
                        issues.append(f"{node_id}: invalid {scope_key} {scope!r}: {error}")
        if not isinstance(node.get("parallel_safe"), bool):
            issues.append(f"{node_id}: parallel_safe must be boolean")
        for numeric in ("critical_path_importance", "downstream_unlock_value"):
            value = node.get(numeric)
            if type(value) is not int or not 0 <= value <= 100:
                issues.append(f"{node_id}: {numeric} must be an integer from 0 to 100")
        retries = node.get("max_retries")
        if type(retries) is not int or retries < 0:
            issues.append(f"{node_id}: max_retries must be non-negative integer")
        return tuple(issues)

    @staticmethod
    def _find_cycle(
        dependencies: Mapping[str, Sequence[str]],
    ) -> tuple[str, ...] | None:
        visiting: set[str] = set()
        visited: set[str] = set()
        stack: list[str] = []

        def visit(node_id: str) -> tuple[str, ...] | None:
            if node_id in visited:
                return None
            if node_id in visiting:
                index = stack.index(node_id)
                return tuple((*stack[index:], node_id))
            visiting.add(node_id)
            stack.append(node_id)
            for dependency in dependencies.get(node_id, ()):
                cycle = visit(dependency)
                if cycle:
                    return cycle
            stack.pop()
            visiting.remove(node_id)
            visited.add(node_id)
            return None

        for node_id in dependencies:
            cycle = visit(node_id)
            if cycle:
                return cycle
        return None

    def _git(
        self,
        args: Sequence[str],
        *,
        check: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        # Preserve the host runtime environment in memory. Windows Git and
        # Schannel need variables such as SystemRoot, TEMP, USERPROFILE, and
        # LOCALAPPDATA; reducing this to PATH makes getaddrinfo/credential
        # helpers fail even when standalone Git succeeds. Nothing here is
        # persisted or printed, and prompts remain disabled.
        base_environment = dict(os.environ)
        base_environment["GIT_TERMINAL_PROMPT"] = "0"
        # Keep the controller deterministic while allowing a trusted local
        # proxy/network path to reach GitHub. These values exist only in the
        # child process environment; they are never persisted or printed.
        for key in SAFE_GIT_TRANSPORT_ENVIRONMENT_KEYS:
            value = os.environ.get(key)
            if not value or any(character in value for character in "\r\n"):
                base_environment.pop(key, None)
                continue
            if key.lower() in {"http_proxy", "https_proxy"}:
                parsed = urlparse(value)
                if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
                    base_environment.pop(key, None)
                    continue
            base_environment[key] = value
        if environment is not None:
            base_environment.update(environment)
        completed = subprocess.run(
            ("git", "-C", str(self.repo_root), *args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
            env=base_environment,
        )
        if check and completed.returncode:
            raise AutopilotError(
                f"git {' '.join(args)} failed: {completed.stderr.strip()}"
            )
        return completed

    def git_object_exists(self, sha: str) -> bool:
        if FULL_SHA.fullmatch(sha) is None:
            return False
        return self._git(("cat-file", "-e", f"{sha}^{{commit}}"), check=False).returncode == 0

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        if not (self.git_object_exists(ancestor) and self.git_object_exists(descendant)):
            return False
        return (
            self._git(("merge-base", "--is-ancestor", ancestor, descendant)).returncode
            == 0
        )

    def current_target_sha(self) -> str:
        if not self.verify_git_objects:
            snapshot = self.github_snapshot()
            value = snapshot.get("target_sha")
            return value if isinstance(value, str) and FULL_SHA.fullmatch(value) else self.baseline_sha
        candidates = (
            f"refs/remotes/origin/{self.target_branch}",
            f"refs/heads/{self.target_branch}",
        )
        for reference in candidates:
            completed = self._git(("rev-parse", "--verify", reference))
            value = completed.stdout.strip()
            if completed.returncode == 0 and FULL_SHA.fullmatch(value):
                return value
        raise AutopilotError(
            f"cannot resolve target branch {self.target_branch!r}; fetch it before dispatch"
        )

    def reconciled_target_sha(self) -> str:
        path = self.state_dir / "target.json"
        if not path.is_file():
            return self.baseline_sha
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ConfigurationError("state target record must be an object")
        sha = value.get("target_sha")
        if not isinstance(sha, str) or FULL_SHA.fullmatch(sha) is None:
            raise ConfigurationError("state target record has an invalid SHA")
        return sha

    def target_requires_reconciliation(self) -> bool:
        return self.current_target_sha() != self.reconciled_target_sha()

    def changed_paths_since_reconciliation(self) -> tuple[str, ...]:
        current = self.current_target_sha()
        prior = self.reconciled_target_sha()
        if current == prior or not self.verify_git_objects:
            return ()
        if not self.is_ancestor(prior, current):
            return ("<target-history-diverged>",)
        completed = self._git(("diff", "--name-only", f"{prior}..{current}"), check=True)
        return tuple(
            sorted(
                {
                    normalize_path(line)
                    for line in completed.stdout.splitlines()
                    if line.strip()
                }
            )
        )

    def github_snapshot(self) -> Mapping[str, Any]:
        path = self.state_dir / "github-state.json"
        if not path.is_file():
            return {}
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ConfigurationError("github-state snapshot must be an object")
        return value

    def github_pr_for_node(self, node_id: str) -> Mapping[str, Any] | None:
        prs = self.github_snapshot().get("pull_requests", [])
        if not isinstance(prs, list):
            return None
        for item in prs:
            if isinstance(item, Mapping) and item.get("node_id") == node_id:
                return item
        return None

    def branch_snapshot(self, branch: str) -> Mapping[str, Any] | None:
        branches = self.github_snapshot().get("branches", [])
        if not isinstance(branches, list):
            return None
        for item in branches:
            if isinstance(item, Mapping) and item.get("name") == branch:
                return item
        return None

    def remote_branch_sha(self, branch: str, *, remote: str = "origin") -> str | None:
        completed = self._git(
            ("ls-remote", "--heads", remote, f"refs/heads/{branch}"),
            check=False,
        )
        if completed.returncode != 0:
            raise ClaimError(
                f"cannot inspect remote {remote!r}: {completed.stderr.strip()}"
            )
        fields = completed.stdout.strip().split()
        if not fields:
            return None
        sha = fields[0]
        if FULL_SHA.fullmatch(sha) is None:
            raise ClaimError("remote branch returned an invalid commit identity")
        return sha

    def publish_remote_claim(
        self,
        node_id: str,
        owner: str,
        expires_at: str,
        *,
        remote: str = "origin",
    ) -> str:
        node = self.node(node_id)
        branch = str(node.get("branch"))
        if self.remote_branch_sha(branch, remote=remote) is not None:
            raise ClaimError(
                f"remote branch {branch!r} already exists; reconcile it before claiming"
            )
        target = self.current_target_sha()
        tree = self._git(("rev-parse", f"{target}^{{tree}}"), check=True).stdout.strip()
        message = json.dumps(
            {
                "kind": "hive-mind-autopilot-remote-claim-v1",
                "node_id": node_id,
                "owner": owner,
                "expires_at": expires_at,
                "plan_fingerprint": self.expected_plan_fingerprint,
                "target_sha": target,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        created = self._git(
            (
                "-c",
                "user.name=Hive Mind Autopilot Claim",
                "-c",
                "user.email=autopilot-claim@hive-mind.invalid",
                "commit-tree",
                tree,
                "-p",
                target,
                "-m",
                message,
            ),
            check=True,
            environment={
                "GIT_AUTHOR_NAME": "Hive Mind Autopilot Claim",
                "GIT_AUTHOR_EMAIL": "autopilot-claim@hive-mind.invalid",
                "GIT_COMMITTER_NAME": "Hive Mind Autopilot Claim",
                "GIT_COMMITTER_EMAIL": "autopilot-claim@hive-mind.invalid",
            },
        ).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise ClaimError("failed to create a remote claim commit")
        pushed = self._git(
            ("push", remote, f"{created}:refs/heads/{branch}"),
            check=False,
        )
        if pushed.returncode != 0:
            raise ClaimError(
                "remote claim race or push failure: " + pushed.stderr.strip()
            )
        observed = self.remote_branch_sha(branch, remote=remote)
        if observed != created:
            raise ClaimError("remote claim branch does not bind the created claim commit")
        return created

    def release_remote_claim(
        self,
        node_id: str,
        claim_commit: str,
        *,
        remote: str = "origin",
    ) -> None:
        branch = str(self.node(node_id).get("branch"))
        observed = self.remote_branch_sha(branch, remote=remote)
        if observed is None:
            return
        if observed != claim_commit:
            # The worker has advanced the implementation branch; never delete it.
            return
        deleted = self._git(
            ("push", remote, f":refs/heads/{branch}"),
            check=False,
        )
        if deleted.returncode != 0:
            raise ClaimError(
                "failed to release untouched remote claim branch: "
                + deleted.stderr.strip()
            )

    def claim_path(self, node_id: str) -> Path:
        return self.claims_dir / f"{node_id}.json"

    def receipt_path(self, node_id: str) -> Path:
        return self.receipts_dir / f"{node_id}.json"

    def active_claims(self) -> dict[str, Mapping[str, Any]]:
        claims: dict[str, Mapping[str, Any]] = {}
        if not self.claims_dir.is_dir():
            return claims
        now = self.clock()
        for path in sorted(self.claims_dir.glob("*.json")):
            try:
                value = read_json(path)
                if not isinstance(value, Mapping):
                    continue
                expires = parse_time(value.get("expires_at"))
            except (ConfigurationError, ValueError):
                continue
            if expires <= now:
                continue
            node_id = value.get("node_id")
            if isinstance(node_id, str):
                claims[node_id] = value
        return claims

    def clean_stale_claims(self) -> tuple[str, ...]:
        removed: list[str] = []
        if not self.claims_dir.is_dir():
            return ()
        now = self.clock()
        for path in sorted(self.claims_dir.glob("*.json")):
            try:
                value = read_json(path)
                expires = parse_time(value.get("expires_at")) if isinstance(value, Mapping) else now
            except (ConfigurationError, ValueError):
                expires = now
            if expires <= now:
                stale = self.state_dir / "stale-claims" / path.name
                stale.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, stale)
                removed.append(path.stem)
        return tuple(removed)

    def failures(self, node_id: str) -> tuple[Mapping[str, Any], ...]:
        path = self.failures_dir / f"{node_id}.jsonl"
        if not path.is_file():
            return ()
        records: list[Mapping[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                records.append(value)
        return tuple(records)

    def record_blocker(
        self,
        node_id: str,
        *,
        cause: str,
        fix: str,
        retry_when: str,
        attempted_command: Sequence[str] = (),
        category: str = "unknown",
        evidence_refs: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Preserve an actionable blocker instead of emitting an opaque failure.

        A blocker is an operating-system learning record: it names the exact
        cause, the safe fix, and the condition that makes retry valid.  The
        append-only JSONL ledger is runtime state, while the protocol and its
        tests are repository code so future sessions cannot silently repeat the
        same failed attempt.
        """

        for value, label in (
            (cause, "cause"),
            (fix, "fix"),
            (retry_when, "retry_when"),
            (category, "category"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise AutopilotError(f"blocker {label} is required")
        command = [str(item) for item in attempted_command]
        packet_without_id = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "category": category,
            "cause": cause,
            "fix": fix,
            "retry_when": retry_when,
            "attempted_command": command,
            "evidence_refs": [str(item) for item in evidence_refs],
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "OPEN",
        }
        packet_without_id["recovery_action"] = self.recovery_action(packet_without_id)
        packet = {
            **packet_without_id,
            "blocker_id": digest_json(packet_without_id),
        }
        append_jsonl(self.blockers_dir / f"{node_id}.jsonl", packet)
        return packet

    def record_human_question(
        self,
        node_id: str,
        *,
        question: str,
        cause: str,
        attempted_command: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        """Track a human question without persisting its potentially sensitive answer.

        Asking a human is a recoverable control-plane event, not a stopping point.
        The question is append-only; ``resolve_human_question`` records the answer
        digest, fix, and immediate retry action so the next run can resume itself.
        """

        for value, label in ((question, "question"), (cause, "cause")):
            if not isinstance(value, str) or not value.strip():
                raise AutopilotError(f"human question {label} is required")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "QUESTION_OPENED",
            "node_id": node_id,
            "question": question,
            "cause": cause,
            "attempted_command": [str(item) for item in attempted_command],
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "OPEN",
        }
        record["question_id"] = digest_json(record)
        append_jsonl(self.questions_dir / f"{node_id}.jsonl", record)
        return record

    def resolve_human_question(
        self,
        node_id: str,
        question_id: str,
        *,
        answer: str,
        fix: str,
        retry_command: Sequence[str],
    ) -> Mapping[str, Any]:
        """Record a human result and make the safe retry immediately actionable.

        Only a digest of ``answer`` is retained. Secrets therefore cannot be
        copied into repository or runtime evidence by the learning mechanism.
        """

        for value, label in ((answer, "answer"), (fix, "fix")):
            if not isinstance(value, str) or not value.strip():
                raise AutopilotError(f"question resolution {label} is required")
        if not retry_command:
            raise AutopilotError("question resolution retry_command is required")
        result = {
            "schema_version": SCHEMA_VERSION,
            "event": "QUESTION_RESOLVED",
            "node_id": node_id,
            "question_id": question_id,
            "answer_digest": digest_json({"answer": answer}),
            "fix": fix,
            "retry_command": [str(item) for item in retry_command],
            "plan_fingerprint": self.expected_plan_fingerprint,
            "timestamp": format_time(self.clock()),
            "status": "RESOLVED",
            "recovery_action": {"action": "RETRY_NOW", "reason": "human_result_recorded"},
        }
        result["resolution_id"] = digest_json(result)
        append_jsonl(self.questions_dir / f"{node_id}.jsonl", result)
        return result

    def start_subtask_wave(
        self,
        wave_id: str,
        node_ids: Sequence[str],
        *,
        target_sha: str | None = None,
    ) -> Mapping[str, Any]:
        """Register children that the orchestrator must supervise to settlement."""

        if not isinstance(wave_id, str) or not wave_id.strip():
            raise AutopilotError("subtask wave_id is required")
        nodes = tuple(dict.fromkeys(str(node) for node in node_ids))
        if not nodes:
            raise AutopilotError("subtask wave requires at least one node")
        unknown = sorted(set(nodes) - set(self._nodes))
        if unknown:
            raise AutopilotError("subtask wave has unknown nodes: " + ", ".join(unknown))
        target = target_sha or self.current_target_sha()
        if FULL_SHA.fullmatch(target) is None:
            raise AutopilotError("subtask wave target_sha must be a full lowercase Git SHA")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "SUBTASK_WAVE_STARTED",
            "wave_id": wave_id,
            "target_sha": target,
            "nodes": list(nodes),
            "statuses": {node: "PENDING" for node in nodes},
            "timestamp": format_time(self.clock()),
            "may_end_turn": False,
            "target_mutation_allowed": False,
            "next_action": "POLL_AGAIN",
            "work_preservation_sequence": list(STALE_TARGET_RECOVERY_SEQUENCE),
        }
        append_jsonl(self.subtask_waves_dir / f"{wave_id}.jsonl", record)
        return record

    def poll_subtask_wave(
        self,
        wave_id: str,
        statuses: Mapping[str, str],
    ) -> Mapping[str, Any]:
        """Record one poll and require supervision until every result is collected.

        UI ``idle`` is deliberately represented as ``IDLE_UNCOLLECTED``. It is
        not success: the parent must read the result and classify it. Recoverable
        blockers require retry; only success or genuine external authority can
        settle a child and permit the parent turn to end.
        """

        path = self.subtask_waves_dir / f"{wave_id}.jsonl"
        if not path.is_file():
            raise AutopilotError(f"unknown subtask wave: {wave_id}")
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        started = next((record for record in records if record.get("event") == "SUBTASK_WAVE_STARTED"), None)
        if not isinstance(started, Mapping):
            raise AutopilotError(f"subtask wave lacks start record: {wave_id}")
        nodes = tuple(str(node) for node in started.get("nodes", ()))
        if set(statuses) != set(nodes):
            raise AutopilotError("subtask poll must classify every wave node exactly once")
        normalized = {node: str(statuses[node]).upper() for node in nodes}
        invalid = sorted({status for status in normalized.values() if status not in SUBTASK_STATES})
        if invalid:
            raise AutopilotError("invalid subtask states: " + ", ".join(invalid))
        actions: dict[str, str] = {}
        for node, state in normalized.items():
            if state in {"PENDING", "ACTIVE"}:
                actions[node] = "POLL_AGAIN"
            elif state == "IDLE_UNCOLLECTED":
                actions[node] = "COLLECT_RESULT_NOW"
            elif state == "BLOCKED_RECOVERABLE":
                actions[node] = "APPLY_FIX_AND_RETRY_NOW"
        settled = all(state in SUBTASK_SETTLED_STATES for state in normalized.values())
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": "SUBTASK_WAVE_POLLED",
            "wave_id": wave_id,
            "target_sha": started.get("target_sha"),
            "statuses": normalized,
            "recovery_actions": actions,
            "timestamp": format_time(self.clock()),
            "may_end_turn": settled,
            "target_mutation_allowed": settled,
            "next_action": "QUIESCENT" if settled else "CONTINUE_SUPERVISION",
        }
        append_jsonl(path, record)
        return record

    def acquire_global_validation_lease(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 10,
    ) -> Mapping[str, Any]:
        """Serialize repository-wide gates while focused node checks stay parallel."""

        if node_id not in self._nodes:
            raise AutopilotError(f"unknown validation node: {node_id}")
        if not isinstance(owner, str) or not owner.strip():
            raise AutopilotError("validation lease owner is required")
        if type(lease_minutes) is not int or lease_minutes < 1:
            raise AutopilotError("validation lease_minutes must be positive")
        now = self.clock()
        if self.validation_lease_path.is_file():
            current = read_json(self.validation_lease_path)
            if isinstance(current, Mapping):
                expires = parse_time(current.get("expires_at"))
                identity = (current.get("node_id"), current.get("owner"))
                if expires > now:
                    if identity == (node_id, owner):
                        return current
                    raise AutopilotError(
                        "global validation lease is active for "
                        f"{current.get('node_id')} owned by {current.get('owner')}"
                    )
                raise AutopilotError(
                    "expired global validation lease requires exact-identity release before reacquisition"
                )
            raise AutopilotError("global validation lease is malformed")
        lease = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "owner": owner,
            "target_sha": self.current_target_sha(),
            "acquired_at": format_time(now),
            "expires_at": format_time(now + timedelta(minutes=lease_minutes)),
            "status": "ACTIVE",
        }
        lease["lease_id"] = digest_json(lease)
        self.validation_lease_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self.validation_lease_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as error:
            raise AutopilotError("global validation lease acquisition raced") from error
        try:
            os.write(descriptor, (json.dumps(lease, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(descriptor)
        except Exception:
            self.validation_lease_path.unlink(missing_ok=True)
            raise
        finally:
            os.close(descriptor)
        return lease

    def release_global_validation_lease(self, node_id: str, owner: str) -> None:
        if not self.validation_lease_path.is_file():
            raise AutopilotError("global validation lease is absent")
        current = read_json(self.validation_lease_path)
        identity = (
            current.get("node_id"),
            current.get("owner"),
        ) if isinstance(current, Mapping) else (None, None)
        if identity != (node_id, owner):
            raise AutopilotError("global validation lease identity mismatch")
        lease_id = str(current.get("lease_id", "unknown")).replace(":", "-")
        archive = self.state_dir / "validation-leases" / f"{lease_id}.json"
        atomic_write_json(
            archive,
            {**current, "status": "RELEASED", "released_at": format_time(self.clock())},
        )
        self.validation_lease_path.unlink()

    @staticmethod
    def recovery_action(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        """Turn known orchestration blockers into bounded child-task work."""

        text = " ".join(
            str(packet.get(key, "")) for key in ("category", "cause", "fix")
        ).lower()
        if any(
            marker in text
            for marker in ("dispatcher release", "release record", "dispatch release")
        ):
            return {
                "action": "SPAWN_SUBTASK",
                "role": "orchestrator",
                "objective": "refresh the singleton release snapshot, reconcile the current target, dispatch the exact eligible node, and retry its claim",
                "required_sequence": list(SUBTASK_EXECUTION_SEQUENCE),
                "stop_if": "target or snapshot changes again, or a protected/security control would need weakening",
            }
        if "snapshot" in text and any(marker in text for marker in ("stale", "target", "mismatch")):
            return {
                "action": "SPAWN_SUBTASK",
                "role": "orchestrator",
                "objective": "refresh the validated singleton snapshot and resume every child invalidated by the target advance",
                "required_sequence": list(STALE_TARGET_RECOVERY_SEQUENCE),
                "stop_if": "remote SHA cannot be verified normally or recovery would weaken provenance/security controls",
            }
        return {
            "action": "REPORT_BLOCKER",
            "role": "orchestrator",
            "objective": "report the exact fix and retry condition to the controlling task",
            "stop_if": "the blocker remains unresolved",
        }

    @staticmethod
    def safe_retry_allowed(packet: Mapping[str, Any]) -> bool:
        """Reject remediation that weakens TLS, certificate, or verification controls."""

        remediation = " ".join(
            str(packet.get(key, "")) for key in ("fix", "retry_when")
        ).lower()
        return not any(marker in remediation for marker in UNSAFE_REMEDIATION_MARKERS)

    def is_quarantined(self, node_id: str) -> bool:
        return (self.quarantine_dir / f"{node_id}.json").is_file()

    def is_escalated(self, node_id: str) -> bool:
        return (self.escalations_dir / f"{node_id}.json").is_file()

    def validate_consultation(self, value: object) -> tuple[str, ...]:
        issues: list[str] = []
        if not isinstance(value, Mapping):
            return ("consultation must be an object",)
        for key in (
            "request_id",
            "mission_id",
            "question",
            "reason_code",
            "requesting_role",
            "decision",
            "cheating_disposition",
        ):
            if not isinstance(value.get(key), str) or not str(value.get(key)).strip():
                issues.append(f"consultation.{key} must be non-empty text")
        requesting = value.get("requesting_role")
        if requesting not in ROLE_NAMES:
            issues.append("consultation.requesting_role is unknown")
        consulted = value.get("consulted_roles")
        if not isinstance(consulted, list) or any(role not in ROLE_NAMES for role in consulted):
            issues.append("consultation.consulted_roles must contain known roles")
            consulted = []
        elif len(set(consulted)) < 2:
            issues.append("consultation requires at least two distinct consulted roles")
        round_number = value.get("round")
        if type(round_number) is not int or not 1 <= round_number <= 3:
            issues.append("consultation.round must be an integer from 1 to 3")
        decision = value.get("decision")
        if decision not in CONSULTATION_DECISIONS:
            issues.append("consultation.decision is invalid")
        evidence = value.get("evidence_refs")
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) or not item for item in evidence
        ):
            issues.append("consultation.evidence_refs must be a string list")
            evidence = []
        dissent = value.get("dissent", [])
        if not isinstance(dissent, list) or any(not isinstance(item, str) for item in dissent):
            issues.append("consultation.dissent must be a string list")
        suspected = value.get("suspected_cheating")
        if not isinstance(suspected, bool):
            issues.append("consultation.suspected_cheating must be boolean")
        disposition = value.get("cheating_disposition")
        if disposition not in CHEATING_DISPOSITIONS:
            issues.append("consultation.cheating_disposition is invalid")
        if suspected is True:
            if disposition == "DISPROVED" and not evidence:
                issues.append("disproving suspected cheating requires evidence")
            if disposition == "NOT_APPLICABLE":
                issues.append("suspected cheating cannot be marked not applicable")
            if decision == "RESOLVED" and disposition not in {"DISPROVED", "UNRESOLVED"}:
                issues.append("confirmed cheating cannot be resolved as ordinary work")
        human = value.get("human_escalation")
        if not isinstance(human, bool):
            issues.append("consultation.human_escalation must be boolean")
            human = False
        authority_class = value.get("authority_class")
        if human:
            if decision != "TRUE_AUTHORITY_REQUIRED":
                issues.append("human escalation requires TRUE_AUTHORITY_REQUIRED")
            if authority_class not in HUMAN_AUTHORITY_CLASSES:
                issues.append("human escalation lacks a genuine authority class")
            if value.get("role_first_exhausted") is not True:
                issues.append("human escalation requires role-first exhaustion proof")
        elif decision == "TRUE_AUTHORITY_REQUIRED":
            issues.append("TRUE_AUTHORITY_REQUIRED must set human_escalation=true")
        if decision == "RESOLVED" and not isinstance(value.get("answer"), str):
            issues.append("resolved consultation requires an answer")
        identity_records = value.get("identity_records", [])
        if not isinstance(identity_records, list):
            issues.append("consultation.identity_records must be a list")
        else:
            for record in identity_records:
                if not isinstance(record, Mapping):
                    issues.append("consultation identity record must be an object")
                    continue
                if record.get("role") not in consulted:
                    issues.append("consultation identity record role was not consulted")
                if record.get("identity_kind") not in {
                    "model_role",
                    "service",
                    "human",
                }:
                    issues.append("consultation identity kind is invalid")
        return tuple(dict.fromkeys(issues))

    def validate_receipt(
        self,
        node_id: str,
        value: object,
        *,
        require_integrated: bool = False,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        node = self.node(node_id)
        if not isinstance(value, Mapping):
            return ("receipt must be an object",)
        required = (
            "schema_version",
            "plan_fingerprint",
            "node_id",
            "contract_version",
            "base_commit",
            "final_commit",
            "branch",
            "pr",
            "changed_paths",
            "tests",
            "evidence_refs",
            "model_runtime",
            "role_identities",
            "authority",
            "consultations",
            "acceptance_decision",
            "timestamp",
            "rollback_ref",
        )
        for key in required:
            if key not in value:
                issues.append(f"receipt missing {key}")
        if value.get("schema_version") != SCHEMA_VERSION:
            issues.append("receipt schema_version is unsupported")
        if value.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("receipt plan fingerprint is stale")
        if value.get("node_id") != node_id:
            issues.append("receipt node ID does not match")
        if value.get("contract_version") != node.get("contract_version"):
            issues.append("receipt contract version does not match")
        base = value.get("base_commit")
        final = value.get("final_commit")
        if not isinstance(base, str) or FULL_SHA.fullmatch(base) is None:
            issues.append("receipt base_commit is invalid")
        if not isinstance(final, str) or FULL_SHA.fullmatch(final) is None:
            issues.append("receipt final_commit is invalid")
        if isinstance(base, str) and isinstance(final, str) and base == final:
            issues.append("receipt final commit must differ from base commit")
        if value.get("branch") != node.get("branch"):
            issues.append("receipt branch does not match node contract")
        changed = value.get("changed_paths")
        if not isinstance(changed, list) or not changed:
            issues.append("receipt changed_paths must be a non-empty list")
            changed = []
        else:
            write_scope = node.get("write_scope", [])
            for raw in changed:
                try:
                    path = normalize_path(raw)
                except ValueError as error:
                    issues.append(f"receipt changed path is unsafe: {error}")
                    continue
                if not any(path_matches_scope(path, scope) for scope in write_scope):
                    issues.append(f"changed path outside node write scope: {path}")
                if any(path_matches_scope(path, scope) for scope in node.get("forbidden_scope", [])):
                    issues.append(f"changed path enters forbidden scope: {path}")
        tests = value.get("tests")
        if not isinstance(tests, list):
            issues.append("receipt tests must be a list")
        else:
            test_names = {
                item.get("name")
                for item in tests
                if isinstance(item, Mapping) and item.get("status") == "passed"
            }
            for required_test in node.get("required_tests", []):
                if required_test not in test_names:
                    issues.append(f"required test did not pass: {required_test}")
            if any(
                isinstance(item, Mapping) and item.get("status") != "passed"
                for item in tests
            ):
                issues.append("receipt contains a non-passing test")
        evidence = value.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence:
            issues.append("receipt requires retained evidence references")
        roles = value.get("role_identities")
        observed_roles: set[str] = set()
        if not isinstance(roles, list):
            issues.append("receipt role_identities must be a list")
        else:
            for record in roles:
                if not isinstance(record, Mapping):
                    issues.append("role identity must be an object")
                    continue
                role = record.get("role")
                if role in ROLE_NAMES:
                    observed_roles.add(str(role))
                else:
                    issues.append("role identity contains an unknown role")
                if record.get("identity_kind") not in {
                    "model_role",
                    "service",
                    "human",
                }:
                    issues.append("role identity kind is invalid")
            missing_roles = set(node.get("roles", [])) - observed_roles
            if missing_roles:
                issues.append(
                    "receipt omits required role identities: "
                    + ", ".join(sorted(missing_roles))
                )
        authority = value.get("authority")
        if not isinstance(authority, Mapping):
            issues.append("receipt authority must be an object")
        else:
            if authority.get("node_id") != node_id:
                issues.append("receipt authority is not bound to the node")
            if not isinstance(authority.get("autonomy_level"), str):
                issues.append("receipt authority lacks autonomy_level")
            if not isinstance(authority.get("grants"), list):
                issues.append("receipt authority grants must be a list")
        consultations = value.get("consultations")
        if not isinstance(consultations, list):
            issues.append("receipt consultations must be a list")
        else:
            for index, consultation in enumerate(consultations):
                for issue in self.validate_consultation(consultation):
                    issues.append(f"consultation[{index}]: {issue}")
        if value.get("acceptance_decision") not in {"ADOPT", "ADAPT"}:
            issues.append("receipt acceptance decision must be ADOPT or ADAPT")
        try:
            parse_time(value.get("timestamp"))
        except ValueError:
            issues.append("receipt timestamp is invalid")
        if not isinstance(value.get("rollback_ref"), str) or not value.get("rollback_ref"):
            issues.append("receipt rollback_ref must be non-empty")
        if self.verify_git_objects and isinstance(base, str) and isinstance(final, str):
            if not self.git_object_exists(base):
                issues.append("receipt base commit is unavailable")
            if not self.git_object_exists(final):
                issues.append("receipt final commit is unavailable")
            elif not self.is_ancestor(base, final):
                issues.append("receipt final commit does not descend from base")
            if require_integrated and not self.is_ancestor(final, self.current_target_sha()):
                issues.append("receipt final commit is not integrated into target history")
        return tuple(dict.fromkeys(issues))

    def stored_receipt(self, node_id: str) -> Mapping[str, Any] | None:
        path = self.receipt_path(node_id)
        if not path.is_file():
            return None
        value = read_json(path)
        return value if isinstance(value, Mapping) else None

    def completed(self, node_id: str) -> bool:
        receipt = self.stored_receipt(node_id)
        if receipt is None:
            return False
        return not self.validate_receipt(node_id, receipt, require_integrated=True)

    def _claim_conflicts(
        self, node_id: str, claims: Mapping[str, Mapping[str, Any]]
    ) -> tuple[str, ...]:
        node = self.node(node_id)
        conflicts: list[str] = []
        for other_id in claims:
            if other_id == node_id:
                continue
            other = self.node(other_id)
            if any(
                scopes_overlap(first, second)
                for first in node.get("file_locks", [])
                for second in other.get("file_locks", [])
            ):
                conflicts.append(f"file lock conflicts with {other_id}")
            shared_semantic = set(node.get("semantic_locks", [])) & set(
                other.get("semantic_locks", [])
            )
            if shared_semantic:
                conflicts.append(
                    f"semantic lock conflicts with {other_id}: "
                    + ", ".join(sorted(shared_semantic))
                )
        return tuple(conflicts)

    def node_view(self, node_id: str) -> NodeView:
        node = self.node(node_id)
        receipt = self.stored_receipt(node_id)
        if receipt is not None:
            receipt_issues = self.validate_receipt(
                node_id, receipt, require_integrated=True
            )
            if not receipt_issues:
                return NodeView(
                    node_id,
                    "COMPLETE",
                    (),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=(
                        int(receipt.get("pr"))
                        if isinstance(receipt.get("pr"), int)
                        else None
                    ),
                )
        if self.is_quarantined(node_id):
            return NodeView(
                node_id,
                "QUARANTINED",
                ("repeated failure or policy violation",),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        if self.is_escalated(node_id):
            return NodeView(
                node_id,
                "ESCALATION_REQUIRED",
                ("worker preserved an escalation packet",),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        if node_id == "BOOT-000" and receipt is None:
            return NodeView(
                node_id,
                "BOOTSTRAP_REQUIRED",
                ("install and validate the repository-resident control plane",),
                (),
                branch=str(node.get("branch")),
            )
        if self.target_requires_reconciliation():
            return NodeView(
                node_id,
                "RECONCILIATION_REQUIRED",
                (
                    f"target advanced from {self.reconciled_target_sha()} to "
                    f"{self.current_target_sha()}",
                ),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        pr = self.github_pr_for_node(node_id)
        if pr is not None:
            number = pr.get("number")
            pr_number = int(number) if isinstance(number, int) else None
            state = pr.get("state")
            merged = pr.get("merged") is True
            ci = pr.get("ci")
            if merged and receipt is None:
                return NodeView(
                    node_id,
                    "WAITING_FOR_RECEIPT",
                    ("PR merged but no validated completion receipt is installed",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
            if state == "open" and ci == "failure":
                return NodeView(
                    node_id,
                    "CI_FAILED",
                    ("open node PR has failing CI",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
            if state == "open":
                return NodeView(
                    node_id,
                    "PR_OPEN",
                    ("node PR is open",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
            if state == "closed" and not merged:
                return NodeView(
                    node_id,
                    "REPAIR_REQUIRED",
                    ("node PR was closed without integration",),
                    tuple(node.get("dependencies", [])),
                    branch=str(node.get("branch")),
                    pr_number=pr_number,
                )
        branch = self.branch_snapshot(str(node.get("branch")))
        if branch is not None and branch.get("stale") is True:
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                ("node branch is stale relative to target",),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        claims = self.active_claims()
        claim = claims.get(node_id)
        if claim is not None:
            status = claim.get("status")
            state = "RUNNING" if status == "RUNNING" else "CLAIMED"
            return NodeView(
                node_id,
                state,
                (),
                tuple(node.get("dependencies", [])),
                active_claim_owner=(
                    str(claim.get("owner")) if claim.get("owner") else None
                ),
                branch=str(node.get("branch")),
            )
        dependency_states = {
            dependency: self.node_view(dependency).state
            for dependency in node.get("dependencies", [])
        }
        incomplete = [
            dependency
            for dependency, state in dependency_states.items()
            if state != "COMPLETE"
        ]
        if incomplete:
            return NodeView(
                node_id,
                "BLOCKED",
                ("incomplete dependencies: " + ", ".join(incomplete),),
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        conflicts = self._claim_conflicts(node_id, claims)
        if conflicts:
            return NodeView(
                node_id,
                "BLOCKED",
                conflicts,
                tuple(node.get("dependencies", [])),
                branch=str(node.get("branch")),
            )
        if node.get("category") == "integration":
            state = "INTEGRATION_READY"
        elif node.get("category") == "promotion":
            state = "PROMOTION_READY"
        else:
            state = "READY"
        return NodeView(
            node_id,
            state,
            (),
            tuple(node.get("dependencies", [])),
            branch=str(node.get("branch")),
        )

    def status(self) -> dict[str, object]:
        self.clean_stale_claims()
        target = self.current_target_sha()
        changed = self.changed_paths_since_reconciliation()
        # The plan is a DAG with substantial fan-in.  Re-evaluating every
        # dependency recursively for every node turns status into exponential
        # work and can make the dispatcher appear hung on a full plan.  Keep
        # this cache scoped to one status snapshot so all consumers observe a
        # consistent view without retaining stale receipt or claim state.
        uncached_node_view = self.node_view
        view_cache: dict[str, NodeView] = {}

        def cached_node_view(node_id: str) -> NodeView:
            if node_id not in view_cache:
                view_cache[node_id] = uncached_node_view(node_id)
            return view_cache[node_id]

        self.node_view = cached_node_view  # type: ignore[method-assign]
        try:
            views = [cached_node_view(node_id) for node_id in sorted(self._nodes)]
        finally:
            self.node_view = uncached_node_view  # type: ignore[method-assign]
        counts: dict[str, int] = {state: 0 for state in LEGAL_STATES}
        for view in views:
            counts[view.state] = counts.get(view.state, 0) + 1
        ready = [
            view.node_id
            for view in views
            if view.state in {"READY", "INTEGRATION_READY", "PROMOTION_READY"}
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan.get("plan_id"),
            "plan_fingerprint": self.expected_plan_fingerprint,
            "target_branch": self.target_branch,
            "target_sha": target,
            "last_reconciled_sha": self.reconciled_target_sha(),
            "reconciliation_required": self.target_requires_reconciliation(),
            "changed_paths_since_reconciliation": list(changed),
            "counts": {key: value for key, value in counts.items() if value},
            "ready": ready,
            "nodes": [view.to_dict() for view in views],
            "complete": all(view.state in TERMINAL_STATES for view in views),
            "generated_at": format_time(self.clock()),
        }

    def ready_nodes(self) -> tuple[str, ...]:
        status = self.status()
        ready = status["ready"]
        assert isinstance(ready, list)
        return tuple(str(item) for item in ready)

    def claim(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        if not owner.strip():
            raise ClaimError("claim owner is required")
        if lease_minutes < 1 or lease_minutes > 1_440:
            raise ClaimError("lease must be between 1 and 1440 minutes")
        self.clean_stale_claims()
        view = self.node_view(node_id)
        if view.state not in {"READY", "INTEGRATION_READY", "PROMOTION_READY"}:
            raise ClaimError(f"node {node_id} is not claimable: {view.state}")
        claims = self.active_claims()
        conflicts = self._claim_conflicts(node_id, claims)
        if conflicts:
            raise ClaimError("; ".join(conflicts))
        now = self.clock()
        expires_at = format_time(now + timedelta(minutes=lease_minutes))
        remote_claim_commit = (
            self.publish_remote_claim(
                node_id, owner, expires_at, remote=remote
            )
            if publish_remote
            else None
        )
        record = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "owner": owner,
            "status": "CLAIMED",
            "claimed_at": format_time(now),
            "heartbeat_at": format_time(now),
            "expires_at": expires_at,
            "plan_fingerprint": self.expected_plan_fingerprint,
            "remote": remote if publish_remote else None,
            "remote_claim_commit": remote_claim_commit,
            "target_sha": self.current_target_sha(),
            "branch": self.node(node_id).get("branch"),
        }
        path = self.claim_path(node_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ClaimError(f"node {node_id} already has a claim") from error
        try:
            os.write(descriptor, (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return record

    def heartbeat(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        running: bool = True,
    ) -> Mapping[str, Any]:
        path = self.claim_path(node_id)
        if not path.is_file():
            raise ClaimError("claim is unavailable")
        value = read_json(path)
        if not isinstance(value, Mapping) or value.get("owner") != owner:
            raise ClaimError("claim owner does not match")
        if parse_time(value.get("expires_at")) <= self.clock():
            raise ClaimError("claim lease has expired")
        now = self.clock()
        updated = dict(value)
        updated["status"] = "RUNNING" if running else "CLAIMED"
        updated["heartbeat_at"] = format_time(now)
        updated["expires_at"] = format_time(now + timedelta(minutes=lease_minutes))
        atomic_write_json(path, updated)
        return updated

    def release(self, node_id: str, owner: str, *, reason: str) -> None:
        path = self.claim_path(node_id)
        if not path.is_file():
            return
        value = read_json(path)
        if not isinstance(value, Mapping) or value.get("owner") != owner:
            raise ClaimError("claim owner does not match")
        remote_claim_commit = value.get("remote_claim_commit")
        remote = value.get("remote")
        if isinstance(remote_claim_commit, str) and isinstance(remote, str):
            self.release_remote_claim(
                node_id, remote_claim_commit, remote=remote
            )
        append_jsonl(
            self.state_dir / "releases.jsonl",
            {
                "node_id": node_id,
                "owner": owner,
                "reason": reason,
                "released_at": format_time(self.clock()),
            },
        )
        path.unlink()

    def fail(
        self,
        node_id: str,
        owner: str,
        *,
        error: str,
        kind: str = "failure",
        evidence_refs: Sequence[str] = (),
        blocker_cause: str | None = None,
        blocker_fix: str | None = None,
        retry_when: str | None = None,
        attempted_command: Sequence[str] = (),
        blocker_category: str = "execution",
    ) -> Mapping[str, Any]:
        if not error.strip():
            raise AutopilotError("failure requires an error description")
        path = self.claim_path(node_id)
        if path.is_file():
            claim = read_json(path)
            if not isinstance(claim, Mapping) or claim.get("owner") != owner:
                raise ClaimError("claim owner does not match")
        record = {
            "schema_version": SCHEMA_VERSION,
            "node_id": node_id,
            "owner": owner,
            "kind": kind,
            "error": error,
            "evidence_refs": list(evidence_refs),
            "timestamp": format_time(self.clock()),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        append_jsonl(self.failures_dir / f"{node_id}.jsonl", record)
        blocker = self.record_blocker(
            node_id,
            cause=blocker_cause or error,
            fix=blocker_fix or "Inspect the retained evidence and correct the reported cause.",
            retry_when=retry_when or "Retry only after the cause is corrected and the same checks pass.",
            attempted_command=attempted_command,
            category=blocker_category,
            evidence_refs=evidence_refs,
        )
        if path.is_file():
            path.unlink()
        if kind == "escalation":
            atomic_write_json(self.escalations_dir / f"{node_id}.json", record)
        max_retries = int(self.node(node_id).get("max_retries", 0))
        if len(self.failures(node_id)) > max_retries:
            atomic_write_json(
                self.quarantine_dir / f"{node_id}.json",
                {
                    **record,
                    "reason": "configured retry budget exhausted",
                },
            )
        return {**record, "blocker": blocker}

    def complete(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
    ) -> Path:
        claim_path = self.claim_path(node_id)
        if not claim_path.is_file():
            raise ClaimError("node completion requires an active claim")
        claim = read_json(claim_path)
        if not isinstance(claim, Mapping) or claim.get("owner") != owner:
            raise ClaimError("claim owner does not match")
        if parse_time(claim.get("expires_at")) <= self.clock():
            raise ClaimError("claim expired before receipt publication")
        issues = self.validate_receipt(node_id, receipt, require_integrated=False)
        if issues:
            raise ReceiptError("; ".join(issues))
        path = self.receipt_path(node_id)
        if path.exists():
            existing = read_json(path)
            if digest_json(existing) == digest_json(receipt):
                claim_path.unlink(missing_ok=True)
                return path
            raise ReceiptError("node already has a different completion receipt")
        atomic_write_json(path, receipt)
        append_jsonl(
            self.state_dir / "receipt-index.jsonl",
            {
                "node_id": node_id,
                "receipt_digest": digest_json(receipt),
                "final_commit": receipt.get("final_commit"),
                "timestamp": receipt.get("timestamp"),
            },
        )
        claim_path.unlink()
        return path

    def reconcile(
        self,
        target_sha: str,
        *,
        actor: str,
        reason: str,
        changed_paths: Sequence[str] = (),
    ) -> Path:
        if FULL_SHA.fullmatch(target_sha) is None:
            raise AutopilotError("reconciled target must be a full lowercase SHA")
        if not actor.strip() or not reason.strip():
            raise AutopilotError("reconciliation actor and reason are required")
        if self.verify_git_objects:
            current = self.current_target_sha()
            if target_sha != current:
                raise AutopilotError(
                    f"reconciled target {target_sha} does not match current target {current}"
                )
            if not self.is_ancestor(self.baseline_sha, target_sha):
                raise AutopilotError("target no longer descends from the sealed baseline")
        normalized = [normalize_path(path) for path in changed_paths]
        record = {
            "schema_version": SCHEMA_VERSION,
            "target_sha": target_sha,
            "actor": actor,
            "reason": reason,
            "changed_paths": normalized,
            "timestamp": format_time(self.clock()),
            "plan_fingerprint": self.expected_plan_fingerprint,
        }
        path = self.state_dir / "target.json"
        atomic_write_json(path, record)
        append_jsonl(self.state_dir / "graph-changes.jsonl", record)
        return path

    def install_github_snapshot(self, source: Path) -> Path:
        value = read_json(source)
        if not isinstance(value, Mapping):
            raise AutopilotError("GitHub snapshot must be an object")
        target = value.get("target_sha")
        if not isinstance(target, str) or FULL_SHA.fullmatch(target) is None:
            raise AutopilotError("GitHub snapshot target_sha is invalid")
        for key in ("pull_requests", "branches"):
            if not isinstance(value.get(key, []), list):
                raise AutopilotError(f"GitHub snapshot {key} must be a list")
        path = self.state_dir / "github-state.json"
        atomic_write_json(path, value)
        return path

    def render_worker_prompt(self, node_id: str) -> str:
        node = self.node(node_id)
        view = self.node_view(node_id)
        template_name = {
            "integration": "integration.md",
            "promotion": "promotion.md",
            "reconciliation": "reconciliation.md",
        }.get(str(node.get("category")), "worker.md")
        template = (self.ap_root / "templates" / template_name).read_text(
            encoding="utf-8"
        )
        routes = _require_mapping(node.get("routes"), f"{node_id}.routes")
        openai = _require_mapping(routes.get("openai"), f"{node_id}.routes.openai")
        anthropic = _require_mapping(
            routes.get("anthropic"), f"{node_id}.routes.anthropic"
        )
        values = {
            "NODE_ID": node_id,
            "NODE_STATE": view.state,
            "OBJECTIVE": str(node.get("objective")),
            "BRANCH": str(node.get("branch")),
            "PR_TARGET": self.target_branch,
            "ROLES": ", ".join(node.get("roles", [])),
            "DEPENDENCIES": ", ".join(node.get("dependencies", [])) or "none",
            "READ_SCOPE": "\n".join(f"- {item}" for item in node.get("read_scope", [])),
            "WRITE_SCOPE": "\n".join(f"- {item}" for item in node.get("write_scope", [])),
            "FORBIDDEN_SCOPE": "\n".join(f"- {item}" for item in node.get("forbidden_scope", [])),
            "ACCEPTANCE": "\n".join(f"- {item}" for item in node.get("acceptance_criteria", [])),
            "TESTS": "\n".join(f"- {item}" for item in node.get("required_tests", [])),
            "STOPPING_CONDITION": str(node.get("stopping_condition")),
            "ESCALATION": "\n".join(f"- {item}" for item in node.get("escalation_conditions", [])),
            "OPENAI_ROUTE": f"{openai.get('model')} / {openai.get('reasoning_effort')}",
            "ANTHROPIC_ROUTE": f"{anthropic.get('model')} / {anthropic.get('reasoning_effort')}",
            "ROUTE_RATIONALE": str(routes.get("rationale")),
            "TARGET_SHA": self.current_target_sha(),
            "PLAN_FINGERPRINT": self.expected_plan_fingerprint,
        }
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def doctor(
        self,
        *,
        run_controller_tests: bool,
    ) -> dict[str, object]:
        issues = list(self.validate_configuration())
        checks: list[dict[str, object]] = []
        checks.append(
            {
                "name": "configuration",
                "passed": not issues,
                "details": list(issues),
            }
        )
        if self.verify_git_objects:
            git_details: list[str] = []
            if not (self.repo_root / ".git").exists():
                git_details.append("repository root lacks .git")
            if not self.git_object_exists(self.baseline_sha):
                git_details.append("sealed baseline commit is unavailable")
            try:
                target = self.current_target_sha()
            except AutopilotError as error:
                git_details.append(str(error))
                target = None
            if target and not self.is_ancestor(self.baseline_sha, target):
                git_details.append("target does not descend from sealed baseline")
            checks.append(
                {
                    "name": "repository",
                    "passed": not git_details,
                    "details": git_details,
                }
            )
        receipt_details: list[str] = []
        if self.receipts_dir.is_dir():
            for path in sorted(self.receipts_dir.glob("*.json")):
                node_id = path.stem
                if node_id not in self._nodes:
                    receipt_details.append(f"receipt exists for unknown node {node_id}")
                    continue
                value = read_json(path)
                receipt_details.extend(
                    f"{node_id}: {issue}"
                    for issue in self.validate_receipt(node_id, value)
                )
        checks.append(
            {
                "name": "receipts",
                "passed": not receipt_details,
                "details": receipt_details,
            }
        )
        consultation_details: list[str] = []
        fixture_dir = self.ap_root / "tests" / "fixtures" / "consultations"
        if fixture_dir.is_dir():
            for path in sorted(fixture_dir.glob("*.json")):
                value = read_json(path)
                if path.name.startswith("valid-"):
                    consultation_details.extend(
                        f"{path.name}: {issue}"
                        for issue in self.validate_consultation(value)
                    )
        checks.append(
            {
                "name": "consultation-contracts",
                "passed": not consultation_details,
                "details": consultation_details,
            }
        )
        test_details: list[str] = []
        if run_controller_tests:
            completed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(self.ap_root / "tests"),
                    "-v",
                ),
                cwd=self.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=180,
            )
            if completed.returncode:
                test_details.append(completed.stdout[-20_000:])
            checks.append(
                {
                    "name": "controller-tests",
                    "passed": completed.returncode == 0,
                    "details": test_details,
                }
            )
        passed = all(bool(check["passed"]) for check in checks)
        return {
            "schema_version": SCHEMA_VERSION,
            "passed": passed,
            "state": "READY" if passed else "BOOTSTRAP_INVALID",
            "plan_fingerprint": self.expected_plan_fingerprint,
            "checks": checks,
            "generated_at": format_time(self.clock()),
        }
