"""Portable entry point for intent-driven repository Autopilot workflows."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

GENERIC_PROMPT_SOURCE = {
    "uri": "https://github.com/kb4beast/Junk/blob/main/Generic%20prompt",
    "pinned_uri": (
        "https://raw.githubusercontent.com/kb4beast/Junk/"
        "760d5e2468484924cbdd077a78584f570a67bd2c/Generic%20prompt"
    ),
    "repository_commit": "760d5e2468484924cbdd077a78584f570a67bd2c",
    "blob_sha": "0fce4315bdaaaf0e1cf4ed5b57dfd15efacd4717",
    "sha256": "f810b17311cebae09413abcfbb1c2155a4934d8ebefa483aadb512e36eed2c5b",
    "bytes": 30114,
    "license": "unresolved-no-repository-license-declared",
}

DEFAULT_OBJECTIVE = (
    "Discover and execute the strongest evidence-backed improvement for this "
    "repository within its checked-in authority and acceptance boundaries."
)
DEFAULT_TARGET_BRANCH = "release/hive-mind-autopilot"


class PortableAutopilotError(RuntimeError):
    """A portable Autopilot operation cannot proceed safely."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _validate_managed_path(root: Path, path: Path) -> Path:
    root = root.resolve()
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as error:
        raise PortableAutopilotError("managed Autopilot state path escapes the repository") from error
    current = root
    for part in relative.parts:
        current = current / part
        if _is_link_like(current):
            raise PortableAutopilotError(
                f"managed Autopilot state path uses a symlink or junction: {current}"
            )
        if current.exists() and not current.resolve().is_relative_to(root):
            raise PortableAutopilotError(
                f"managed Autopilot state path escapes the repository: {current}"
            )
    return root / relative


def _atomic_write_json(root: Path, path: Path, value: object) -> None:
    path = _validate_managed_path(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _validate_managed_path(root, path)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _git(repo: Path, args: Sequence[str]) -> str:
    environment = {
        key: os.environ[key]
        for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP")
        if os.environ.get(key)
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=30,
    )
    if result.returncode != 0:
        raise PortableAutopilotError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _git_bytes(repo: Path, args: Sequence[str]) -> bytes:
    environment = {
        key: os.environ[key]
        for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP")
        if os.environ.get(key)
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        env=environment,
        timeout=30,
    )
    if result.returncode != 0:
        raise PortableAutopilotError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout


def _git_optional(repo: Path, args: Sequence[str]) -> str | None:
    try:
        return _git(repo, args)
    except PortableAutopilotError:
        return None


def _safe_remote(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme or parts.hostname is None:
        match = re.fullmatch(r"[^/@:\\]+@([^:]+):(.+)", value)
        return f"{match.group(1)}:{match.group(2)}" if match else value
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError as error:
        raise PortableAutopilotError("origin remote URL contains an invalid port") from error
    if port is not None:
        host = f"{host}:{port}"
    # User info, query strings, and fragments can all carry credentials.  The
    # persisted request needs repository identity, never connection secrets.
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _repository_id(root: Path, remote: str | None) -> str:
    identity = remote or str(root)
    return "sha256:" + sha256(identity.casefold().encode("utf-8")).hexdigest()


_SECRET_TEXT = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password)\b\s*[:=]\s*\S+|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|\b(?:gh[oprsu]_|sk-)[A-Za-z0-9_-]{12,})"
)


def _reject_secret_like_text(value: str, label: str) -> None:
    if _SECRET_TEXT.search(value):
        raise PortableAutopilotError(
            f"{label} appears to contain a credential; remove it and use the host secret store"
        )


def _default_trust_root() -> Path:
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]) / "hive-mind-os" / "controller-trust"
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "HiveMindOS" / "controller-trust"
    return Path.home() / ".local" / "state" / "hive-mind-os" / "controller-trust"


def _default_authorization_root() -> Path:
    return _default_trust_root().parent / "controller-trust-authority"


def _canonical_contract_id(value: Mapping[str, Any]) -> str:
    material = dict(value)
    material.pop("contract_id", None)
    return "sha256:" + sha256(_canonical_bytes(material)).hexdigest()


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PortableAutopilotError(f"{label} is unreadable: {error}") from error
    if not isinstance(value, Mapping):
        raise PortableAutopilotError(f"{label} must be an object")
    return value


def _digest(value: object) -> str:
    return "sha256:" + sha256(_canonical_bytes(value)).hexdigest()


def _external_file(
    repository: Path,
    authority_root: Path,
    reference: str | Path,
    label: str,
) -> Path:
    root = authority_root.resolve()
    if root.is_relative_to(repository) or _is_link_like(authority_root):
        raise PortableAutopilotError(f"{label} root must be host-owned and outside the target repository")
    candidate = Path(reference)
    candidate = candidate if candidate.is_absolute() else authority_root / candidate
    try:
        relative = candidate.absolute().relative_to(authority_root.absolute())
    except ValueError as error:
        raise PortableAutopilotError(f"{label} escapes the host authorization root") from error
    current = authority_root
    for part in relative.parts:
        current = current / part
        if _is_link_like(current):
            raise PortableAutopilotError(f"{label} must not use a symlink or junction")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or resolved.is_relative_to(repository):
        raise PortableAutopilotError(f"{label} escapes the host authorization root")
    if not resolved.is_file():
        raise PortableAutopilotError(f"{label} is not a resolvable regular file")
    return resolved


def _parse_authorization_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PortableAutopilotError(f"controller trust authorization {label} must be UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise PortableAutopilotError(
            f"controller trust authorization {label} must be UTC RFC3339"
        ) from error
    if parsed.tzinfo is None:
        raise PortableAutopilotError(f"controller trust authorization {label} must include a timezone")
    return parsed.astimezone(UTC)


def _validate_contract(value: object, root: Path) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PortableAutopilotError("installed Autopilot contract must be an object")
    required = {
        "schema_version",
        "kind",
        "intent",
        "tasks",
        "outcome",
        "successful",
        "quiescent",
        "contract_id",
    }
    missing = sorted(required - set(value))
    if missing:
        raise PortableAutopilotError(
            "installed Autopilot contract is missing: " + ", ".join(missing)
        )
    if value.get("schema_version") != 1 or value.get("kind") != "hive-mind-autopilot-orchestration-contract-v1":
        raise PortableAutopilotError("installed Autopilot contract identity is invalid")
    intent = value.get("intent")
    if not isinstance(intent, Mapping) or intent.get("intent") not in {
        "BUILD_DAG", "START", "CONTINUE", "CHECK", "FINISH"
    }:
        raise PortableAutopilotError("installed Autopilot intent is invalid")
    tasks = value.get("tasks")
    if not isinstance(tasks, list) or any(not isinstance(item, Mapping) for item in tasks):
        raise PortableAutopilotError("installed Autopilot tasks must be objects")
    plan_nodes: dict[str, Mapping[str, Any]] = {}
    control: Mapping[str, Any] = {}
    if tasks:
        plan = _load_json_object(root / ".autopilot" / "plan.json", "installed Autopilot plan")
        raw_nodes = plan.get("nodes")
        if not isinstance(raw_nodes, list):
            raise PortableAutopilotError("installed Autopilot plan nodes must be a list")
        for node in raw_nodes:
            if not isinstance(node, Mapping) or not isinstance(node.get("id"), str):
                raise PortableAutopilotError("installed Autopilot plan contains an invalid node")
            plan_nodes[str(node["id"])] = node
        control = _load_json_object(
            root / ".autopilot" / "control-plane.json", "installed Autopilot control plane"
        )
        target = control.get("target")
        if not isinstance(target, Mapping) or value.get("target_branch") != target.get("branch"):
            raise PortableAutopilotError("installed Autopilot contract target is not control-plane bound")
    allowed_actions = {
        "CREATE",
        "RESUME",
        "RESUME_BOUND",
        "RECOVER_PREPARED",
        "PUBLISH_RECEIPT",
        "VALIDATE_PR",
        "REPAIR_CI",
        "REPAIR_NODE",
        "RECONCILE_NODE",
        "REPLAN_NODE",
        "RECONCILE",
        "RELEASE_TERMINAL",
    }
    for index, task in enumerate(tasks):
        assert isinstance(task, Mapping)
        task_required = {
            "task_key",
            "launch_instruction_id",
            "action",
            "transport",
            "binding_required",
            "host_adapters",
            "expected_artifact",
            "prompt",
        }
        task_missing = sorted(task_required - set(task))
        if task_missing:
            raise PortableAutopilotError(
                f"installed Autopilot task {index} is missing: " + ", ".join(task_missing)
            )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(task.get("launch_instruction_id"))):
            raise PortableAutopilotError(f"installed Autopilot task {index} has an invalid launch id")
        if task.get("transport") != "durable_user_owned_task" or task.get("binding_required") is not True:
            raise PortableAutopilotError(f"installed Autopilot task {index} weakens durable binding")
        if not isinstance(task.get("host_adapters"), Mapping):
            raise PortableAutopilotError(f"installed Autopilot task {index} lacks host adapters")
        codex = task["host_adapters"].get("codex")
        if not isinstance(codex, Mapping) or {
            "create": codex.get("create"),
            "wait": codex.get("wait"),
            "message": codex.get("message"),
        } != {
            "create": "create_thread",
            "wait": "wait_threads",
            "message": "send_message_to_thread",
        }:
            raise PortableAutopilotError(f"installed Autopilot task {index} has an unsafe Codex adapter")
        for key in ("task_key", "action", "expected_artifact", "prompt"):
            if not isinstance(task.get(key), str) or not str(task.get(key)).strip():
                raise PortableAutopilotError(f"installed Autopilot task {index} has invalid {key}")
        if task.get("action") not in allowed_actions:
            raise PortableAutopilotError(f"installed Autopilot task {index} has an unknown action")
        node_id = task.get("node_id")
        if node_id is None:
            if task.get("action") != "RECONCILE":
                raise PortableAutopilotError(f"installed Autopilot task {index} lacks node authority")
        else:
            node = plan_nodes.get(str(node_id))
            if node is None:
                raise PortableAutopilotError(f"installed Autopilot task {index} names an unknown node")
            expected_fields = {
                "branch": str(node.get("branch")),
                "target_branch": str(node.get("pr_target")),
                "write_scope": list(node.get("write_scope", [])),
            }
            for key, expected in expected_fields.items():
                if task.get(key) != expected:
                    raise PortableAutopilotError(
                        f"installed Autopilot task {index} exceeds plan authority for {key}"
                    )
    if value.get("outcome") not in {"ACTIVE", "SUCCESS", "BLOCKED", "IDLE"}:
        raise PortableAutopilotError("installed Autopilot outcome is invalid")
    if type(value.get("successful")) is not bool or type(value.get("quiescent")) is not bool:
        raise PortableAutopilotError("installed Autopilot outcome flags must be booleans")
    outcome = value.get("outcome")
    successful = value.get("successful")
    quiescent = value.get("quiescent")
    if successful is not (outcome == "SUCCESS"):
        raise PortableAutopilotError("installed Autopilot success flag contradicts outcome")
    if outcome == "SUCCESS" and quiescent is not True:
        raise PortableAutopilotError("installed Autopilot success must be quiescent")
    if tasks and (outcome != "ACTIVE" or quiescent is not False):
        raise PortableAutopilotError("installed Autopilot active tasks contradict outcome")
    if intent.get("intent") == "CHECK" and (tasks or value.get("dispatch_required") is True):
        raise PortableAutopilotError("installed Autopilot CHECK contract authorizes effects")
    closure_target = value.get("closure_target")
    task_keys = {task.get("task_key") for task in tasks}
    if tasks and closure_target not in task_keys:
        raise PortableAutopilotError("installed Autopilot closure target is not an active task")
    if not tasks and closure_target is not None:
        raise PortableAutopilotError("installed Autopilot closure target has no task")
    if value.get("contract_id") != _canonical_contract_id(value):
        raise PortableAutopilotError("installed Autopilot contract digest is invalid")
    return value


def _load_bootstrap_request(path: Path, root: Path) -> Mapping[str, Any]:
    path = _validate_managed_path(root, path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PortableAutopilotError(f"portable Autopilot request is unreadable: {error}") from error
    if not isinstance(value, Mapping):
        raise PortableAutopilotError("portable Autopilot request must be an object")
    required = {
        "schema_version", "kind", "repository_root", "repository_id", "objective",
        "target_branch", "protected_branches", "protection_verification", "source",
        "orchestration_requirements",
        "request_id",
    }
    missing = sorted(required - set(value))
    if missing:
        raise PortableAutopilotError("portable Autopilot request is missing: " + ", ".join(missing))
    material = dict(value)
    request_id = material.pop("request_id", None)
    expected = "sha256:" + sha256(_canonical_bytes(material)).hexdigest()
    if request_id != expected:
        raise PortableAutopilotError("portable Autopilot request digest is invalid")
    if value.get("schema_version") != 1 or value.get("kind") != "hive-mind-portable-autopilot-request-v1":
        raise PortableAutopilotError("portable Autopilot request identity is invalid")
    if Path(str(value.get("repository_root"))).resolve() != root:
        raise PortableAutopilotError("portable Autopilot request is bound to another repository")
    remote = value.get("repository_remote")
    if remote is not None and not isinstance(remote, str):
        raise PortableAutopilotError("portable Autopilot request remote identity is invalid")
    if value.get("repository_id") != _repository_id(root, remote):
        raise PortableAutopilotError("portable Autopilot request repository identity is invalid")
    target = str(value.get("target_branch", ""))
    if not target or target.casefold() in {"main", "master", "trunk"} or target.casefold().startswith("refs/heads/"):
        raise PortableAutopilotError("portable Autopilot request target is unsafe")
    protected = value.get("protected_branches")
    if not isinstance(protected, list) or any(
        not isinstance(item, str) or not item.strip() for item in protected
    ):
        raise PortableAutopilotError("portable Autopilot protected branches are invalid")
    folded_target = target.casefold()
    if any(fnmatchcase(folded_target, item.strip().casefold()) for item in protected):
        raise PortableAutopilotError("portable Autopilot target is declared protected")
    protection = value.get("protection_verification")
    if not isinstance(protection, Mapping) or protection.get("status") != "RECHECK_REQUIRED_BEFORE_REMOTE_MUTATION":
        raise PortableAutopilotError("portable Autopilot protection verification is invalid")
    requirements = value.get("orchestration_requirements")
    if not isinstance(requirements, Mapping) or requirements.get("protected_branch_mutation") is not False:
        raise PortableAutopilotError("portable Autopilot request permits protected branch mutation")
    source = value.get("source")
    if not isinstance(source, Mapping) or source.get("sha256") != GENERIC_PROMPT_SOURCE["sha256"]:
        raise PortableAutopilotError("portable Autopilot source provenance is invalid")
    _git(root, ["check-ref-format", "--branch", target])
    return value


def _controller_environment() -> dict[str, str]:
    allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP")
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}


def _verify_tracked_python_bundle(
    root: Path, controller: Path
) -> tuple[Path, tuple[Mapping[str, str], ...]]:
    resolved_controller = controller.resolve()
    if controller.is_symlink() or not resolved_controller.is_relative_to(root):
        raise PortableAutopilotError("installed Autopilot controller escapes the repository")
    bin_root = (root / ".autopilot" / "bin").resolve()
    if not bin_root.is_relative_to(root):
        raise PortableAutopilotError("installed Autopilot executable directory escapes the repository")
    candidates = sorted(bin_root.glob("*.py"))
    if resolved_controller not in {item.resolve() for item in candidates}:
        raise PortableAutopilotError("installed Autopilot controller is not a regular Python source file")
    if any(bin_root.glob("*.pyc")):
        raise PortableAutopilotError("sourceless bytecode is forbidden in the Autopilot executable directory")
    bundle: list[Mapping[str, str]] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if candidate.is_symlink() or not resolved.is_relative_to(bin_root):
            raise PortableAutopilotError("installed Autopilot executable source escapes its directory")
        relative = resolved.relative_to(root).as_posix()
        if _git(root, ["ls-files", "--error-unmatch", relative]) != relative:
            raise PortableAutopilotError(f"installed Autopilot source is not tracked at HEAD: {relative}")
        index_row = _git(root, ["ls-files", "--stage", "--", relative]).split()
        if not index_row or index_row[0] not in {"100644", "100755"}:
            raise PortableAutopilotError(f"installed Autopilot source is not a regular file: {relative}")
        head_bytes = _git_bytes(root, ["show", f"HEAD:{relative}"])
        worktree_bytes = resolved.read_bytes()
        if head_bytes.replace(b"\r\n", b"\n") != worktree_bytes.replace(b"\r\n", b"\n"):
            raise PortableAutopilotError(f"installed Autopilot source has uncommitted changes: {relative}")
        bundle.append(
            {
                "path": relative,
                "sha256": "sha256:" + sha256(head_bytes).hexdigest(),
            }
        )
    return resolved_controller, tuple(bundle)


def _trust_path(repository_id: str, trust_state_root: str | Path | None) -> Path:
    root = Path(trust_state_root).resolve() if trust_state_root else _default_trust_root()
    return root / f"{repository_id.removeprefix('sha256:')}.json"


def _controller_bundle_digest(bundle: Sequence[Mapping[str, str]]) -> str:
    return _digest(list(bundle))


def _verify_controller_trust_authorization(
    repository: Path,
    *,
    repository_id: str,
    controller_bundle: Sequence[Mapping[str, str]],
    authorization_capability: str | Path,
    actor: str | None = None,
    controller_source_commit: str | None = None,
) -> tuple[Mapping[str, Any], str]:
    authority_root = _default_authorization_root().resolve()
    capability_path = _external_file(
        repository,
        authority_root,
        authorization_capability,
        "controller trust authorization capability",
    )
    key_path = _external_file(
        repository,
        authority_root,
        "controller-trust-authority.key",
        "controller trust authorization key",
    )
    if os.name != "nt" and (
        authority_root.stat().st_mode & 0o077 or key_path.stat().st_mode & 0o077
    ):
        raise PortableAutopilotError(
            "controller trust authorization root and key must be accessible only to the host owner"
        )
    try:
        key = key_path.read_bytes()
    except OSError as error:
        raise PortableAutopilotError(
            f"controller trust authorization key is unreadable: {error}"
        ) from error
    if len(key) < 32 or len(key) > 4096:
        raise PortableAutopilotError("controller trust authorization key length is invalid")
    capability = _load_json_object(
        capability_path,
        "controller trust authorization capability",
    )
    expected_top_level = {
        "schema_version",
        "kind",
        "key_id",
        "authorization",
        "signature",
        "capability_id",
    }
    if set(capability) != expected_top_level:
        raise PortableAutopilotError("controller trust authorization capability fields are invalid")
    material = dict(capability)
    capability_id = material.pop("capability_id", None)
    if capability_id != _digest(material):
        raise PortableAutopilotError("controller trust authorization capability digest is invalid")
    key_id = "sha256:" + sha256(key).hexdigest()
    authorization = capability.get("authorization")
    signature = capability.get("signature")
    if (
        capability.get("schema_version") != 1
        or capability.get("kind") != "hive-mind-controller-trust-authorization-v1"
        or capability.get("key_id") != key_id
        or not isinstance(authorization, Mapping)
        or not isinstance(signature, str)
        or not signature.startswith("sha256:")
    ):
        raise PortableAutopilotError("controller trust authorization capability identity is invalid")
    signed_material = {
        "schema_version": capability["schema_version"],
        "kind": capability["kind"],
        "key_id": capability["key_id"],
        "authorization": authorization,
    }
    expected_signature = "sha256:" + hmac_new(
        key,
        _canonical_bytes(signed_material),
        "sha256",
    ).hexdigest()
    if not compare_digest(signature, expected_signature):
        raise PortableAutopilotError("controller trust authorization signature is invalid")
    expected_authorization_fields = {
        "grant",
        "repository_id",
        "controller_source_commit",
        "controller_bundle_digest",
        "authorized_actor",
        "issuer",
        "independent_reviewer",
        "evidence",
        "issued_at",
        "expires_at",
    }
    if set(authorization) != expected_authorization_fields:
        raise PortableAutopilotError("controller trust authorization grant fields are invalid")
    authorized_actor = authorization.get("authorized_actor")
    issuer = authorization.get("issuer")
    reviewer = authorization.get("independent_reviewer")
    identities = (authorized_actor, issuer, reviewer)
    if (
        any(not isinstance(identity, str) or not identity.strip() for identity in identities)
        or len({str(identity).strip().casefold() for identity in identities}) != 3
    ):
        raise PortableAutopilotError(
            "controller trust requires distinct authorized actor, host issuer, and independent reviewer"
        )
    for identity_label, identity in zip(
        ("authorized actor", "host issuer", "independent reviewer"),
        identities,
        strict=True,
    ):
        _reject_secret_like_text(str(identity), identity_label)
    if actor is not None and authorized_actor != actor:
        raise PortableAutopilotError("controller trust capability does not authorize this actor")
    if (
        authorization.get("grant") != "PIN_CONTROLLER_TRUST"
        or authorization.get("repository_id") != repository_id
        or authorization.get("controller_bundle_digest")
        != _controller_bundle_digest(controller_bundle)
    ):
        raise PortableAutopilotError("controller trust authorization scope is stale or invalid")
    if (
        controller_source_commit is not None
        and authorization.get("controller_source_commit") != controller_source_commit
    ):
        raise PortableAutopilotError("controller trust authorization source commit is stale")
    issued_at = _parse_authorization_time(authorization.get("issued_at"), "issued_at")
    expires_at = _parse_authorization_time(authorization.get("expires_at"), "expires_at")
    now = datetime.now(UTC)
    if (
        expires_at <= issued_at
        or expires_at - issued_at > timedelta(hours=24)
        or issued_at > now
        or expires_at <= now
    ):
        raise PortableAutopilotError("controller trust authorization is not currently valid")
    evidence = authorization.get("evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != {"uri", "sha256"}:
        raise PortableAutopilotError("controller trust authorization evidence binding is invalid")
    evidence_uri = evidence.get("uri")
    evidence_digest = evidence.get("sha256")
    if (
        not isinstance(evidence_uri, str)
        or not evidence_uri.strip()
        or not isinstance(evidence_digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", evidence_digest)
    ):
        raise PortableAutopilotError("controller trust authorization evidence binding is invalid")
    _reject_secret_like_text(evidence_uri, "independent controller review evidence URI")
    evidence_path = _external_file(
        repository,
        authority_root,
        evidence_uri,
        "independent controller review evidence",
    )
    if "sha256:" + sha256(evidence_path.read_bytes()).hexdigest() != evidence_digest:
        raise PortableAutopilotError("independent controller review evidence digest is invalid")
    capability_uri = capability_path.relative_to(authority_root).as_posix()
    return capability, capability_uri


def trust_controller(
    repository: str | Path,
    *,
    actor: str,
    authorization_capability: str | Path,
    trust_state_root: str | Path | None = None,
) -> Mapping[str, Any]:
    root = Path(repository).resolve()
    root = Path(_git(root, ["rev-parse", "--show-toplevel"])).resolve()
    if not actor.strip():
        raise PortableAutopilotError("controller trust requires an authorized actor")
    controller = root / ".autopilot" / "bin" / "autopilot.py"
    if not controller.is_file():
        raise PortableAutopilotError("repository has no installed Autopilot controller")
    _, bundle = _verify_tracked_python_bundle(root, controller)
    raw_remote = _git_optional(root, ["remote", "get-url", "origin"])
    remote = _safe_remote(raw_remote) if raw_remote else None
    repository_id = _repository_id(root, remote)
    source_commit = _git(root, ["rev-parse", "HEAD"])
    capability, capability_uri = _verify_controller_trust_authorization(
        root,
        repository_id=repository_id,
        controller_bundle=bundle,
        authorization_capability=authorization_capability,
        actor=actor,
        controller_source_commit=source_commit,
    )
    authorization = capability["authorization"]
    material: dict[str, Any] = {
        "schema_version": 2,
        "kind": "hive-mind-controller-trust-v2",
        "repository_id": repository_id,
        "controller_source_commit": source_commit,
        "controller_bundle": list(bundle),
        "controller_bundle_digest": _controller_bundle_digest(bundle),
        "authorized_actor": actor,
        "authorization_capability_id": capability["capability_id"],
        "authorization_capability_uri": capability_uri,
        "authorization_key_id": capability["key_id"],
        "authorization_issuer": authorization["issuer"],
        "independent_reviewer": authorization["independent_reviewer"],
        "independent_review_evidence": authorization["evidence"],
        "trusted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    material["trust_id"] = _digest(material)
    path = _trust_path(repository_id, trust_state_root)
    if path.resolve().is_relative_to(root):
        raise PortableAutopilotError("controller trust must be stored outside the target repository")
    if _is_link_like(path.parent):
        raise PortableAutopilotError("controller trust root must not be a symlink or junction")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path.parent, path, material)
    return {"status": "trusted", "path": str(path), "trust": material}


def _require_controller_trust(
    root: Path,
    bundle: Sequence[Mapping[str, str]],
    trust_state_root: str | Path | None,
) -> Mapping[str, Any]:
    raw_remote = _git_optional(root, ["remote", "get-url", "origin"])
    remote = _safe_remote(raw_remote) if raw_remote else None
    repository_id = _repository_id(root, remote)
    path = _trust_path(repository_id, trust_state_root)
    if path.resolve().is_relative_to(root):
        raise PortableAutopilotError("controller trust must be stored outside the target repository")
    trust = _load_json_object(path, "external controller trust record")
    material = dict(trust)
    trust_id = material.pop("trust_id", None)
    if trust_id != _digest(material):
        raise PortableAutopilotError("external controller trust record digest is invalid")
    if (
        trust.get("schema_version") != 2
        or trust.get("kind") != "hive-mind-controller-trust-v2"
        or trust.get("repository_id") != repository_id
        or trust.get("controller_bundle") != list(bundle)
        or trust.get("controller_bundle_digest") != _controller_bundle_digest(bundle)
    ):
        raise PortableAutopilotError(
            "controller trust is missing or stale; obtain host authorization for the clean controller bundle"
        )
    capability_uri = trust.get("authorization_capability_uri")
    if not isinstance(capability_uri, str) or not capability_uri:
        raise PortableAutopilotError("external controller trust authorization reference is invalid")
    capability, resolved_uri = _verify_controller_trust_authorization(
        root,
        repository_id=repository_id,
        controller_bundle=bundle,
        authorization_capability=capability_uri,
    )
    authorization = capability["authorization"]
    if (
        resolved_uri != capability_uri
        or trust.get("authorization_capability_id") != capability.get("capability_id")
        or trust.get("authorization_key_id") != capability.get("key_id")
        or trust.get("authorized_actor") != authorization.get("authorized_actor")
        or trust.get("authorization_issuer") != authorization.get("issuer")
        or trust.get("independent_reviewer") != authorization.get("independent_reviewer")
        or trust.get("independent_review_evidence") != authorization.get("evidence")
    ):
        raise PortableAutopilotError("external controller trust authorization binding is invalid")
    return trust


def _requests_read_only(request: str) -> bool:
    text = re.sub(r'"[^"]*"|“[^”]*”', " ", request).casefold()
    action = r"(?:start(?:ing)?|run(?:ning)?|execute|continue|resume|finish|complete|build|create|generate|launch|kick\s+off|modif(?:y|ies|ied|ying)|chang(?:e|es|ed|ing)|writ(?:e|es|ing)|apply|dispatch)"
    if re.search(r"\b(?:do\s+nothing|don['’]?t\s+do\s+anything|dont\s+do\s+anything|no\s+changes?)\b", text):
        return True
    if re.search(rf"\b(?:do\s+not|don['’]?t|dont|never)\s+(?:\w+\s+){{0,3}}{action}\b", text):
        return True
    if re.search(r"\b(?:only|just)\s+(?:check|inspect|report|summari[sz]e|explain|review)\b", text):
        return True
    if re.search(r"\b(?:explain|describe|summari[sz]e|tell\s+me|show\s+me)\s+(?:how|why|what|when|where|whether)\b", text):
        return True
    if re.search(r"\b(?:review|audit|analy[sz]e|discuss)\s+(?:how|why|what|when|where|whether)\b", text):
        return True
    if re.search(r"\bhow\s+(?:can|could|would|should|do|does|did)\s+(?:i|we|you|this|it|the\s+dag)\b", text):
        return True
    if re.search(r"\b(?:check|inspect|report|summari[sz]e|explain|review)\s+only\b", text):
        return True
    if re.search(r"\bshould\s+(?:i|we|you)\b", text):
        return True
    if re.search(r"\b(?:is|would)\s+it\b.*\b(?:start|finish|continue|run|execute)\b", text):
        return True
    if re.search(r"\b(?:can|could)\s+(?:this|it|the\s+dag)\b", text):
        return True
    return any(
        phrase in text
        for phrase in (
            "read only",
            "read-only",
            "explain the",
            "summarize the",
            "what would you do",
            "what should we do",
            "how would you",
            "how do i",
            "how do we",
            "why did",
            "why didn",
        )
    )


def initialize_repository(
    repository: str | Path,
    *,
    objective: str = DEFAULT_OBJECTIVE,
    target_branch: str = DEFAULT_TARGET_BRANCH,
    remote_name: str | None = "origin",
    protected_branches: Sequence[str] = (),
) -> Mapping[str, Any]:
    _reject_secret_like_text(objective, "objective")
    root = Path(repository).resolve()
    if not root.is_dir():
        raise PortableAutopilotError(f"repository directory does not exist: {root}")
    git_root = Path(_git(root, ["rev-parse", "--show-toplevel"])).resolve()
    if git_root != root:
        root = git_root
    head = _git(root, ["rev-parse", "HEAD"])
    tree = _git(root, ["rev-parse", "HEAD^{tree}"])
    selected_remote = remote_name.strip() if isinstance(remote_name, str) and remote_name.strip() else None
    raw_remote = _git_optional(root, ["remote", "get-url", selected_remote]) if selected_remote else None
    if raw_remote is None and selected_remote == "origin":
        remotes = [item for item in (_git_optional(root, ["remote"]) or "").splitlines() if item]
        if len(remotes) == 1:
            selected_remote = remotes[0]
            raw_remote = _git_optional(root, ["remote", "get-url", selected_remote])
    elif raw_remote is None and selected_remote is not None:
        raise PortableAutopilotError(f"configured Git remote does not exist: {selected_remote}")
    remote = _safe_remote(raw_remote) if raw_remote else None
    current_branch = _git_optional(root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    protected = {"main", "master", "trunk"}
    if current_branch:
        protected.add(current_branch)
    protected.update(item.strip() for item in protected_branches if item.strip())
    protected_folded = {item.casefold() for item in protected}
    if target_branch.casefold() in protected_folded or target_branch.casefold().startswith("refs/heads/"):
        raise PortableAutopilotError(
            "portable Autopilot target must be an unprotected integration/release branch"
        )
    _git(root, ["check-ref-format", "--branch", target_branch])
    request: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-portable-autopilot-request-v1",
        "repository_root": str(root),
        "repository_remote": remote,
        "repository_remote_name": selected_remote if remote else None,
        "repository_id": _repository_id(root, remote),
        "observed_head": head,
        "observed_tree": tree,
        "objective": objective.strip() or DEFAULT_OBJECTIVE,
        "target_branch": target_branch,
        "protected_branches": sorted(protected, key=str.casefold),
        "protection_verification": {
            "status": "RECHECK_REQUIRED_BEFORE_REMOTE_MUTATION",
            "required_before": ["push", "pull_request", "merge"],
            "rule": "verify the current provider ruleset or checked-in protected-ref policy and fail closed",
        },
        "state": "DAG_BUILD_REQUIRED",
        "source": dict(GENERIC_PROMPT_SOURCE),
        "orchestration_requirements": {
            "infer_user_intent": True,
            "supported_intents": ["BUILD_DAG", "START", "CONTINUE", "CHECK", "FINISH"],
            "primary_task_transport": "durable_user_owned_task",
            "nested_agents": "bounded_sidecars_only",
            "parallel_wave": "deterministic_priority_ordered_maximal_conflict_free",
            "closure_first": True,
            "poll_until_terminal": True,
            "minimum_primary_completions_before_parent_yield": 1,
            "resume_by_node_identity": True,
            "record_and_repair_resolved_blockers": True,
            "protected_branch_mutation": False,
        },
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    request["request_id"] = "sha256:" + sha256(_canonical_bytes(request)).hexdigest()
    path = _validate_managed_path(root, root / ".hive-mind" / "autopilot-request.json")
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        stable_keys = (
            "repository_root",
            "repository_remote",
            "repository_remote_name",
            "repository_id",
            "objective",
            "target_branch",
            "source",
            "orchestration_requirements",
            "protection_verification",
        )
        if isinstance(existing, Mapping) and all(
            existing.get(key) == request.get(key) for key in stable_keys
        ):
            return {"status": "already-initialized", "request": existing, "path": str(path)}
        raise PortableAutopilotError(
            f"portable Autopilot request already exists: {path}; inspect it before replacing"
        )
    _atomic_write_json(root, path, request)
    return {"status": "initialized", "request": request, "path": str(path)}


def simple_prompt() -> str:
    return (
        "Use Hive Mind OS Autopilot on this repository. Infer whether I mean build, "
        "start, continue, check, or finish; execute its durable parallel-task contract, "
        "recover blockers, and continue until the current DAG is quiescent."
    )


def _uninstalled_contract(root: Path, request: str) -> Mapping[str, Any]:
    request_path = root / ".hive-mind" / "autopilot-request.json"
    if not request_path.is_file():
        raise PortableAutopilotError(
            "Autopilot is not initialized; run `hive-mind autopilot init --repository <path>`"
        )
    bootstrap = _load_bootstrap_request(request_path, root)
    repository_id = str(
        bootstrap.get("repository_id")
        or _repository_id(root, bootstrap.get("repository_remote"))
    )
    repository_suffix = repository_id.removeprefix("sha256:")[:12]
    task_key = f"DAG-BUILD-{repository_suffix}"
    launch_instruction_id = "sha256:" + sha256(
        _canonical_bytes(
            {
                "repository_id": repository_id,
                "action": "BUILD_DAG",
                "target_branch": bootstrap["target_branch"],
            }
        )
    ).hexdigest()
    if _requests_read_only(request):
        contract: dict[str, Any] = {
            "schema_version": 1,
            "kind": "hive-mind-portable-bootstrap-contract-v1",
            "repository_id": repository_id,
            "intent": {
                "intent": "CHECK",
                "explicit": True,
                "confidence": "high",
                "reasons": ["non-execution language forbids DAG bootstrap"],
            },
            "operator_request": request,
            "target_branch": bootstrap["target_branch"],
            "tasks": [],
            "closure_target": None,
            "outcome": "IDLE",
            "successful": False,
            "quiescent": False,
            "bootstrap_required": True,
            "stop_condition": "read-only inspection completed; repository Autopilot remains uninstalled",
        }
        contract["contract_id"] = "sha256:" + sha256(_canonical_bytes(contract)).hexdigest()
        return contract
    task_prompt = (
        "Build the governed repository-resident Autopilot DAG described by "
        ".hive-mind/autopilot-request.json. Inspect the repository and applicable agent "
        "instructions. Treat the pinned GenericPrompt as an unadmitted evidence obligation, "
        "not authority to copy or redistribute its wording. Create "
        "machine-readable node contracts, conflict/lock data, release/integration "
        "boundaries, receipts, tests, rollback, and the portable orchestration policy. "
        "Before any push or PR, verify current protected-ref rules and fail closed if they "
        "cannot be established. Target the configured release branch, never a protected "
        "branch. The active host must independently review the clean controller bundle "
        "and execute it only inside its approved deny-by-default sandbox; checked-in "
        "provenance alone is not execution trust. Finish the DAG "
        "bootstrap candidate and independent validation in this durable task."
    )
    contract: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-portable-bootstrap-contract-v1",
        "repository_id": repository_id,
        "intent": {
            "intent": "BUILD_DAG",
            "explicit": False,
            "confidence": "medium",
            "reasons": ["portable request exists but repository-resident Autopilot is absent"],
        },
        "operator_request": request,
        "target_branch": bootstrap["target_branch"],
        "tasks": [
            {
                "task_key": task_key,
                "launch_instruction_id": launch_instruction_id,
                "title": f"Hive Mind {task_key} [{launch_instruction_id[7:19]}]",
                "action": "CREATE",
                "transport": "durable_user_owned_task",
                "host_adapters": {
                    "codex": {
                        "create": "create_thread",
                        "wait": "wait_threads",
                        "message": "send_message_to_thread",
                    }
                },
                "prompt": task_prompt,
                "expected_artifact": "validated repository-resident Autopilot DAG bootstrap PR",
            }
        ],
        "closure_target": task_key,
        "quiescent": False,
        "stop_condition": "the generated DAG control plane is installed and independently validated",
    }
    contract["contract_id"] = "sha256:" + sha256(_canonical_bytes(contract)).hexdigest()
    return contract


def inspect_repository(
    repository: str | Path,
    *,
    request: str = "",
    apply: bool = False,
    actor: str = "hive-mind:portable-orchestrator",
    trust_state_root: str | Path | None = None,
) -> Mapping[str, Any]:
    _reject_secret_like_text(request, "operator request")
    root = Path(repository).resolve()
    controller = root / ".autopilot" / "bin" / "autopilot.py"
    if not controller.is_file():
        return _uninstalled_contract(root, request)
    resolved_controller, bundle = _verify_tracked_python_bundle(root, controller)
    read_only = _requests_read_only(request)
    intent = "CHECK" if read_only else "CONTINUE"
    try:
        trust = _require_controller_trust(
            root,
            bundle,
            trust_state_root,
        )
    except PortableAutopilotError as error:
        raw_remote = _git_optional(root, ["remote", "get-url", "origin"])
        remote = _safe_remote(raw_remote) if raw_remote else None
        review_material = {
            "repository": str(root),
            "repository_id": _repository_id(root, remote),
            "controller_source_commit": _git(root, ["rev-parse", "HEAD"]),
            "controller_bundle": list(bundle),
            "controller_bundle_digest": _controller_bundle_digest(bundle),
            "action": "INDEPENDENT_CONTROLLER_REVIEW",
        }
        review_id = "sha256:" + sha256(_canonical_bytes(review_material)).hexdigest()
        return {
            "schema_version": 1,
            "kind": "hive-mind-portable-controller-review-required-v1",
            "intent": {
                "intent": "CHECK" if read_only else "CONTINUE",
                "explicit": read_only,
                "confidence": "high",
                "reasons": ["target controller execution requires an external independent bundle pin"],
            },
            "operator_request": request,
            "repository_id": review_material["repository_id"],
            "controller_source_commit": review_material["controller_source_commit"],
            "controller_bundle": list(bundle),
            "controller_bundle_digest": review_material["controller_bundle_digest"],
            "authorization_requirements": {
                "kind": "hive-mind-controller-trust-authorization-v1",
                "grant": "PIN_CONTROLLER_TRUST",
                "host_owned": True,
                "pairwise_distinct_identities": [
                    "authorized_actor",
                    "issuer",
                    "independent_reviewer",
                ],
                "evidence": "resolvable host-external artifact with an exact sha256 digest",
            },
            "tasks": [] if read_only else [
                {
                    "task_key": "CONTROLLER-TRUST",
                    "launch_instruction_id": review_id,
                    "idempotency_key": review_id,
                    "action": "INDEPENDENT_REVIEW",
                    "transport": "durable_user_owned_task",
                    "prompt": (
                        "Independently review the exact clean controller bundle listed in this "
                        "contract. A distinct host authority must issue a digest-bound capability "
                        "authorizing another actor to pin it; the capability must name your Curator "
                        "identity and resolve to exact external evidence bytes. Then use "
                        "`hive-mind autopilot trust-controller` with that capability. Do not execute "
                        "the target controller during review."
                    ),
                }
            ],
            "outcome": "CONTROLLER_REVIEW_REQUIRED",
            "successful": False,
            "quiescent": read_only,
            "blocker": str(error),
            "stop_condition": "an independent external pin authorizes this exact controller bundle",
        }
    instruction_material = {
        "repository": str(root),
        "controller_bundle": list(bundle),
        "controller_trust": trust,
        "request": request,
        "apply": apply,
        "actor": actor,
    }
    instruction_id = "sha256:" + sha256(_canonical_bytes(instruction_material)).hexdigest()
    contract: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-portable-controller-invocation-v1",
        "intent": {
            "intent": intent,
            "explicit": read_only,
            "confidence": "high" if read_only else "low",
            "reasons": [
                "portable code never executes target-repository Python; the active host must use its approved sandbox"
            ],
        },
        "operator_request": request,
        "controller_bundle": list(bundle),
        "invocation": {
            "instruction_id": instruction_id,
            "executable": str(resolved_controller.relative_to(root).as_posix()),
            "arguments": [
                "--repo-root",
                ".",
                "orchestrate",
                "--request",
                request,
                "--actor",
                actor,
                "--json",
                *(["--apply"] if apply else []),
            ],
            "execution_owner": "active_host_sandbox",
            "deny_outside_repository_filesystem": True,
            "deny_network_unless_separately_authorized": True,
            "allow_descendant_processes": ["git", "approved test commands declared by the controller"],
            "validate_returned_contract": True,
        },
        "outcome": "HOST_EXECUTION_REQUIRED",
        "successful": False,
        "quiescent": False,
        "stop_condition": "the approved host sandbox executes and validates the repository controller contract",
    }
    contract["contract_id"] = "sha256:" + sha256(_canonical_bytes(contract)).hexdigest()
    return contract
