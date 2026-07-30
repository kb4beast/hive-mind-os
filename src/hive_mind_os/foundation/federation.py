from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision

from .authority import (
    AuthorityDecision,
    authority_decision_is_authentic,
    decide_foundation_write,
)
from .canonical import canonical_bytes, digest, reject_private_content, stable_id
from .cognitive_contracts import validate_cognitive
from .federation_contracts import validate_federation

FEDERATION_ACTION = "foundation.federation.write"
FEDERATION_ACTOR = "foundation-federation-projector-v1"
FEDERATION_NAMESPACE = "hive-mind/federated-cognitive"
MAX_SOURCES = 64
MAX_NOTES = 100_000
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_NOTE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


class FederationError(RuntimeError):
    """A federation input or target failed closed."""


@dataclass(frozen=True, slots=True)
class FederationResult:
    schema_version: str
    status: str
    portfolio_tenant_digest: str
    portfolio_repository_id: str
    namespace_path: str
    manifest_digest: str
    source_count: int
    note_count: int
    tree_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "portfolio_tenant_digest": self.portfolio_tenant_digest,
            "portfolio_repository_id": self.portfolio_repository_id,
            "namespace_path": self.namespace_path,
            "manifest_digest": self.manifest_digest,
            "source_count": self.source_count,
            "note_count": self.note_count,
            "tree_digest": self.tree_digest,
        }


def _file_digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _json_bytes(document: Any) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _tenant_digest(tenant_id: str) -> str:
    return digest({"identity_domain": "portfolio-tenant/v1", "tenant_id": tenant_id})


def _safe_relative_path(value: str) -> PurePosixPath:
    if (
        not value
        or len(value) > 240
        or "\\" in value
        or value.startswith("/")
        or ":" in value
    ):
        raise FederationError("source manifest contains an unsafe path")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise FederationError("source manifest contains a non-normal path")
    return path


def _read_regular_file(path: Path, limit: int, label: str) -> bytes:
    try:
        info = path.lstat()
    except OSError as error:
        raise FederationError(f"{label} is unavailable") from error
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > limit
    ):
        raise FederationError(f"{label} must be a bounded single-link regular file")
    try:
        with path.open("rb") as handle:
            content = handle.read(limit + 1)
    except OSError as error:
        raise FederationError(f"{label} could not be read") from error
    if len(content) > limit:
        raise FederationError(f"{label} exceeds its size bound")
    try:
        after = path.lstat()
    except OSError as error:
        raise FederationError(f"{label} changed during its read") from error
    if (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_nlink,
    ) != (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_nlink,
    ):
        raise FederationError(f"{label} changed during its read")
    return content


def _read_json_object(path: Path, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    content = _read_regular_file(path, limit, label)
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise FederationError(f"{label} is invalid JSON") from error
    if not isinstance(document, dict):
        raise FederationError(f"{label} is not an object")
    return document, content


def _parse_cognitive_note(content: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        text = content.decode("utf-8")
    except UnicodeError as error:
        raise FederationError("source cognitive note is not UTF-8") from error
    if not text.startswith("---\n"):
        raise FederationError("source cognitive note lacks deterministic frontmatter")
    boundary = text.find("\n---\n", 4)
    if boundary < 0:
        raise FederationError("source cognitive note frontmatter is incomplete")
    properties: dict[str, Any] = {}
    for line in text[4:boundary].splitlines():
        name, separator, encoded = line.partition(": ")
        if not separator or not name or name in properties:
            raise FederationError("source cognitive note frontmatter is ambiguous")
        try:
            properties[name] = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise FederationError("source cognitive note frontmatter is invalid") from error
    validation = validate_cognitive("cognitive-note-v1", properties)
    if not validation.valid:
        raise FederationError(
            "source cognitive note contract failed: " + "; ".join(validation.issues)
        )
    body = text[boundary + 5 :]
    if body.startswith("\n"):
        body = body[1:]
    prefixes = (
        "# Released cognitive record\n\n## Safe-public metadata\n\n",
        (
            "# Telemetry metadata\n\n"
            "Usage accounting is unavailable in this released cognitive note; "
            "no zero usage is implied.\n\n"
        ),
    )
    prefix = next((item for item in prefixes if body.startswith(item)), None)
    if prefix is None:
        raise FederationError("source cognitive note body is not a known safe projection")
    encoded_payload = body[len(prefix) :]
    payload_lines = encoded_payload.splitlines()
    while payload_lines and not payload_lines[-1]:
        payload_lines.pop()
    if not payload_lines or any(
        line and not line.startswith("    ") for line in payload_lines
    ):
        raise FederationError("source cognitive note payload is not deterministic JSON")
    try:
        payload = json.loads(
            "\n".join(line[4:] if line else "" for line in payload_lines)
        )
    except json.JSONDecodeError as error:
        raise FederationError("source cognitive note payload is invalid") from error
    if not isinstance(payload, dict):
        raise FederationError("source cognitive note payload is not an object")
    try:
        reject_private_content(payload)
    except ValueError as error:
        raise FederationError("source cognitive note payload is not safe-public") from error
    if prefix == prefixes[0] and (
        payload.get("tenant_id") != properties["tenant_id"]
        or payload.get("repository_id") != properties["repository_id"]
        or payload.get("memory_id") != properties["subject_id"]
        or payload.get("content_digest") != properties["content_digest"]
    ):
        raise FederationError("source cognitive note payload scope is inconsistent")
    return properties, payload


def _render_federated_note(
    *,
    source_alias: str,
    repository_identity_digest: str,
    source_manifest_digest: str,
    source_properties: Mapping[str, Any],
    source_payload: Mapping[str, Any],
) -> tuple[str, str, bytes]:
    identity_subject = {
        "source_repository_identity_digest": repository_identity_digest,
        "source_note_id": source_properties["note_id"],
    }
    note_id = stable_id("federated-note", identity_subject)
    properties = {
        "schema_version": "hive-federated-note/v1",
        "federated_note_id": note_id,
        "source_alias": source_alias,
        "source_repository_identity_digest": repository_identity_digest,
        "source_manifest_digest": source_manifest_digest,
        "source_note_id": source_properties["note_id"],
        "source_record_id": source_properties["source_record_id"],
        "source_content_digest": source_properties["source_digest"],
        "note_kind": source_properties["note_kind"],
        "sensitivity": "safe-public",
        "source_identity_role": "provenance-only",
        "is_generated": True,
        "is_authoritative": False,
    }
    validation = validate_federation("federated-note-v1", properties)
    if not validation.valid:
        raise FederationError("federated note contract failed: " + "; ".join(validation.issues))
    portfolio_payload = {
        name: value
        for name, value in source_payload.items()
        if name
        not in {
            "tenant_id",
            "repository_id",
            "protected_content_ref",
            "retrieval_receipt",
        }
    }
    lines = [
        "---",
        *(
            f"{name}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            for name, value in properties.items()
        ),
        "---",
        "",
        "# Federated safe-public record",
        "",
        (
            "This portfolio-local note is a non-authoritative projection. "
            "Its source identities are provenance only."
        ),
        "",
        "## Released source payload",
        "",
        *(
            f"    {line}"
            for line in json.dumps(
                portfolio_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).splitlines()
        ),
        "",
    ]
    content = "\n".join(lines).encode("utf-8")
    if len(content) > MAX_NOTE_BYTES:
        raise FederationError("federated note exceeds its size bound")
    key = note_id.removeprefix("federated-note:")
    folder = "evidence" if source_properties["note_kind"] == "evidence" else (
        f"{source_properties['note_kind']}s"
    )
    return (
        f"r/{source_alias.removeprefix('repo-')[:16]}/{folder}/{key[:32]}.md",
        note_id,
        content,
    )


def _load_source(
    source_root: Path,
    tenant_id: str,
) -> tuple[dict[str, Any], dict[str, bytes], list[dict[str, Any]]]:
    try:
        root_info = source_root.lstat()
    except OSError as error:
        raise FederationError("source cognitive namespace is unavailable") from error
    if not stat.S_ISDIR(root_info.st_mode):
        raise FederationError("source cognitive namespace must be a real directory")
    manifest, manifest_bytes = _read_json_object(
        source_root / "manifest.json",
        MAX_MANIFEST_BYTES,
        "source cognitive manifest",
    )
    validation = validate_cognitive("cognitive-manifest-v1", manifest)
    if not validation.valid:
        raise FederationError(
            "source cognitive manifest contract failed: "
            + "; ".join(validation.issues)
        )
    if manifest["tenant_id"] != tenant_id:
        raise FederationError("cross-tenant federation is prohibited")
    manifest_digest = _file_digest(manifest_bytes)
    source_alias = "repo-" + sha256(
        canonical_bytes(
            {
                "identity_domain": "federation-source-alias/v1",
                "repository_identity_digest": manifest["repository_identity_digest"],
            }
        )
    ).hexdigest()
    desired: dict[str, bytes] = {}
    notes: list[dict[str, Any]] = []
    listed_paths: set[str] = set()
    total_bytes = len(manifest_bytes)
    for entry in manifest["files"]:
        relative = _safe_relative_path(entry["path"])
        if entry["path"] in listed_paths:
            raise FederationError("source manifest repeats a path")
        listed_paths.add(entry["path"])
        candidate = source_root.joinpath(*relative.parts)
        try:
            if candidate.resolve(strict=True).parent != source_root.resolve(strict=True).joinpath(
                *relative.parts[:-1]
            ):
                raise FederationError("source manifest path escapes its namespace")
        except OSError as error:
            raise FederationError("source manifest path is unavailable") from error
        content = _read_regular_file(candidate, MAX_NOTE_BYTES, "source cognitive file")
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_BYTES:
            raise FederationError("source cognitive namespaces exceed the total bound")
        if _file_digest(content) != entry["content_digest"]:
            raise FederationError("source cognitive file digest is inconsistent")
        if entry["source_record_id"] is None:
            continue
        properties, payload = _parse_cognitive_note(content)
        if (
            properties["tenant_id"] != tenant_id
            or properties["repository_id"] != manifest["repository_id"]
            or properties["repository_identity_digest"]
            != manifest["repository_identity_digest"]
            or properties["note_id"] != entry["note_id"]
            or properties["source_record_id"] != entry["source_record_id"]
            or properties["source_digest"] != entry["source_digest"]
        ):
            raise FederationError("source cognitive note scope or identity is inconsistent")
        path, note_id, rendered = _render_federated_note(
            source_alias=source_alias,
            repository_identity_digest=manifest["repository_identity_digest"],
            source_manifest_digest=manifest_digest,
            source_properties=properties,
            source_payload=payload,
        )
        if path in desired:
            raise FederationError("federated note identity collision")
        desired[path] = rendered
        notes.append(
            {
                "path": path,
                "federated_note_id": note_id,
                "source_alias": source_alias,
                "content_digest": _file_digest(rendered),
            }
        )
    if len(notes) != manifest["note_counts"]["total"]:
        raise FederationError("source cognitive note count is inconsistent")
    source = {
        "source_alias": source_alias,
        "repository_identity_digest": manifest["repository_identity_digest"],
        "repository_id_digest": digest(
            {
                "identity_domain": "federation-repository-id/v1",
                "repository_id": manifest["repository_id"],
            }
        ),
        "source_manifest_digest": manifest_digest,
        "source_cursor": manifest["source_cursor"],
        "note_count": len(notes),
    }
    return source, desired, notes


def _desired_portfolio(
    source_roots: Sequence[Path],
    *,
    tenant_id: str,
    portfolio_repository_id: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise FederationError("portfolio tenant is required")
    if not isinstance(portfolio_repository_id, str) or not portfolio_repository_id.strip():
        raise FederationError("portfolio repository identity is required")
    if not 2 <= len(source_roots) <= MAX_SOURCES:
        raise FederationError("federation requires between 2 and 64 sources")
    loaded = [_load_source(root, tenant_id) for root in source_roots]
    loaded.sort(key=lambda item: item[0]["source_alias"])
    aliases = [item[0]["source_alias"] for item in loaded]
    if len(aliases) != len(set(aliases)):
        raise FederationError("federation sources repeat a repository identity")
    desired: dict[str, bytes] = {}
    file_entries: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []
    for source, files, notes in loaded:
        source_entries.append(source)
        for path, content in files.items():
            if path in desired:
                raise FederationError("federated path collision")
            desired[path] = content
        file_entries.extend(notes)
    if len(file_entries) > MAX_NOTES:
        raise FederationError("federated note count exceeds its bound")
    home = "\n".join(
        [
            "---",
            'schema_version: "hive-federation-home/v1"',
            f"portfolio_tenant_digest: {json.dumps(_tenant_digest(tenant_id))}",
            f"source_count: {len(source_entries)}",
            f"note_count: {len(file_entries)}",
            "is_generated: true",
            "is_authoritative: false",
            "---",
            "",
            "# Federated safe-public portfolio",
            "",
            (
                "This vault contains portfolio-local, read-only projections. "
                "Source identities are provenance only."
            ),
            "",
            *(
                f"- `{source['source_alias']}` — {source['note_count']} notes"
                for source in source_entries
            ),
            "",
        ]
    ).encode("utf-8")
    desired["HOME.md"] = home
    file_entries.append(
        {
            "path": "HOME.md",
            "federated_note_id": None,
            "source_alias": None,
            "content_digest": _file_digest(home),
        }
    )
    file_entries.sort(key=lambda item: item["path"])
    manifest = {
        "schema_version": "hive-federation-manifest/v1",
        "federation_contract": "hive-safe-public-federation/v1",
        "projector_version": "hive-federation-projector/v1",
        "portfolio_tenant_digest": _tenant_digest(tenant_id),
        "portfolio_repository_id": portfolio_repository_id,
        "generated_namespace": FEDERATION_NAMESPACE,
        "source_count": len(source_entries),
        "note_count": len(file_entries) - 1,
        "sources": source_entries,
        "files": file_entries,
    }
    validation = validate_federation("federation-manifest-v1", manifest)
    if not validation.valid:
        raise FederationError("federation manifest failed: " + "; ".join(validation.issues))
    desired["manifest.json"] = _json_bytes(manifest)
    if sum(len(content) for content in desired.values()) > MAX_TOTAL_BYTES:
        raise FederationError("federated portfolio exceeds its total size bound")
    return desired, manifest


def _tree_digest(desired: Mapping[str, bytes]) -> str:
    return digest(
        [
            {"path": path, "content_digest": _file_digest(content)}
            for path, content in sorted(desired.items())
        ]
    )


def _verify_existing(namespace: Path, desired: Mapping[str, bytes]) -> bool:
    if not namespace.exists():
        return False
    try:
        info = namespace.lstat()
    except OSError as error:
        raise FederationError("federation namespace is unavailable") from error
    if not stat.S_ISDIR(info.st_mode):
        raise FederationError("federation namespace is not a real directory")
    observed: set[str] = set()
    for candidate in namespace.rglob("*"):
        relative = candidate.relative_to(namespace).as_posix()
        if candidate.is_dir() and not candidate.is_symlink():
            continue
        observed.add(relative)
        expected = desired.get(relative)
        if expected is None:
            raise FederationError("existing federation namespace has unmanaged content")
        content = _read_regular_file(
            candidate,
            max(len(expected), 1),
            "existing federated file",
        )
        if content != expected:
            raise FederationError("existing federation namespace conflicts with desired bytes")
    if observed != set(desired):
        raise FederationError("existing federation namespace is incomplete")
    return True


def _write_new_namespace(namespace: Path, desired: Mapping[str, bytes]) -> None:
    parent = namespace.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        parent_info = parent.lstat()
    except OSError as error:
        raise FederationError("federation target parent is unavailable") from error
    if not stat.S_ISDIR(parent_info.st_mode):
        raise FederationError("federation target parent is not a real directory")
    staging = Path(tempfile.mkdtemp(prefix=".federation-", dir=parent))
    try:
        for relative, content in sorted(desired.items()):
            target = staging.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if namespace.exists():
            raise FederationError("federation namespace appeared during projection")
        os.replace(staging, namespace)
    except BaseException:
        if staging.exists() and staging.parent == parent and staging.name.startswith(
            ".federation-"
        ):
            shutil.rmtree(staging)
        raise


def project_federation(
    source_namespaces: Iterable[str | Path],
    target_vault: str | Path,
    *,
    tenant_id: str,
    portfolio_repository_id: str,
    check: bool = False,
    authority: AuthorityDecision | None = None,
) -> FederationResult:
    if not check and (
        authority is None
        or not authority_decision_is_authentic(authority)
        or not authority.allowed
        or authority.foundation_action != FEDERATION_ACTION
        or authority.tenant_id != tenant_id
        or authority.repository_id != portfolio_repository_id
        or authority.actor_id != FEDERATION_ACTOR
    ):
        raise PermissionError("federation authority is missing or inconsistent")
    source_roots = [Path(path).absolute() for path in source_namespaces]
    target_root = Path(target_vault).absolute()
    if target_root.exists():
        try:
            target_info = target_root.lstat()
        except OSError as error:
            raise FederationError("portfolio vault is unavailable") from error
        if not stat.S_ISDIR(target_info.st_mode):
            raise FederationError("portfolio vault must be a real directory")
    target_resolved = target_root.resolve(strict=False)
    namespace = target_resolved.joinpath(*PurePosixPath(FEDERATION_NAMESPACE).parts)
    for source in source_roots:
        source_resolved = source.resolve(strict=True)
        if source_resolved == target_resolved or source_resolved in target_resolved.parents:
            raise FederationError("portfolio vault cannot be inside a source vault")
        if target_resolved in source_resolved.parents:
            raise FederationError("source vault cannot be inside the portfolio vault")
    desired, manifest = _desired_portfolio(
        source_roots,
        tenant_id=tenant_id,
        portfolio_repository_id=portfolio_repository_id,
    )
    manifest_digest = _file_digest(desired["manifest.json"])
    status = "checked"
    if not check:
        if _verify_existing(namespace, desired):
            status = "unchanged"
        else:
            _write_new_namespace(namespace, desired)
            status = "projected"
    result = FederationResult(
        schema_version="hive-federation-result/v1",
        status=status,
        portfolio_tenant_digest=manifest["portfolio_tenant_digest"],
        portfolio_repository_id=portfolio_repository_id,
        namespace_path=str(namespace),
        manifest_digest=manifest_digest,
        source_count=manifest["source_count"],
        note_count=manifest["note_count"],
        tree_digest=_tree_digest(desired),
    )
    validation = validate_federation("federation-result-v1", result.to_dict())
    if not validation.valid:
        raise FederationError("federation result failed: " + "; ".join(validation.issues))
    return result


def evaluate_self_host_context(
    context: Mapping[str, Any],
    prior_contexts: Iterable[Mapping[str, Any]] = (),
    *,
    max_self_host_depth: int = 1,
    max_delegation_hops: int = 8,
) -> dict[str, Any]:
    validation = validate_federation("self-host-context-v1", context)
    if not validation.valid:
        raise FederationError("self-host context failed: " + "; ".join(validation.issues))
    if not 0 <= max_self_host_depth <= 64:
        raise ValueError("max_self_host_depth is outside the schema bound")
    if not 0 <= max_delegation_hops <= 1024:
        raise ValueError("max_delegation_hops is outside the schema bound")
    priors = list(prior_contexts)
    for prior in priors:
        prior_validation = validate_federation("self-host-context-v1", prior)
        if not prior_validation.valid:
            raise FederationError("prior self-host context failed closed")
    status = "accepted"
    reason = "admitted"
    if any(
        prior["idempotency_key"] == context["idempotency_key"]
        or (
            prior["origin_record_id"] == context["origin_record_id"]
            and prior["origin_digest"] == context["origin_digest"]
        )
        for prior in priors
    ):
        status, reason = "collapsed", "duplicate-origin"
    elif (
        context["event_kind"] == "evidence-ingestion"
        and context["origin_kind"] == "generated-memory"
    ):
        status, reason = "rejected", "generated-memory-reingestion"
    elif (
        context["event_kind"] == "projection"
        and context["origin_kind"] in {"generated-memory", "projection-event"}
    ):
        status, reason = "rejected", "projection-feedback"
    elif (
        context["event_kind"] == "telemetry"
        and context["origin_kind"] == "telemetry-event"
    ):
        status, reason = "rejected", "telemetry-feedback"
    elif (
        context["event_kind"] == "idea"
        and context["origin_kind"] in {"generated-memory", "projection-event", "idea-event"}
    ):
        status, reason = "rejected", "idea-feedback"
    elif (
        context["event_kind"] == "delegation"
        and context["origin_kind"] == "delegation-event"
    ):
        status, reason = "rejected", "delegation-feedback"
    elif context["delegation_hops"] > max_delegation_hops:
        status, reason = "rejected", "delegation-hop-limit"
    elif context["self_host_depth"] > max_self_host_depth:
        status, reason = "rejected", "self-host-depth-limit"
    elif context["event_kind"] == "self-analysis" and not context["target_boundary"]:
        status, reason = "rejected", "missing-target-boundary"
    elif any(
        prior["controller_os_build_id"] == context["controller_os_build_id"]
        and prior["controller_instance_id"] == context["controller_instance_id"]
        and prior["tenant_id"] == context["tenant_id"]
        and prior["project_lineage_id"] == context["project_lineage_id"]
        and prior["repo_instance_id"] == context["repo_instance_id"]
        and prior["subject_commit"] != context["subject_commit"]
        and prior["observation_epoch"] == context["observation_epoch"]
        for prior in priors
    ):
        status, reason = "rejected", "stale-observation-epoch"
    context_digest = digest(dict(context))
    decision = {
        "schema_version": "hive-self-host-decision/v1",
        "decision_id": stable_id(
            "self-host-decision",
            {"context_digest": context_digest, "status": status, "reason": reason},
        ),
        "status": status,
        "reason": reason,
        "context_digest": context_digest,
        "idempotency_key": context["idempotency_key"],
        "observation_epoch": context["observation_epoch"],
        "self_host_depth": context["self_host_depth"],
        "delegation_hops": context["delegation_hops"],
    }
    decision_validation = validate_federation("self-host-decision-v1", decision)
    if not decision_validation.valid:
        raise FederationError(
            "self-host decision failed: " + "; ".join(decision_validation.issues)
        )
    return decision


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hive_mind_os.foundation.federation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("project", "check"):
        command = commands.add_parser(name)
        command.add_argument("--source", action="append", required=True)
        command.add_argument("--portfolio-vault", required=True)
        command.add_argument("--tenant", required=True)
        command.add_argument("--portfolio-repository-id", required=True)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    check = args.command == "check"
    authority = (
        None
        if check
        else decide_foundation_write(
            role=Role.BUILDER,
            action=FEDERATION_ACTION,
            policy_decision=PolicyDecision(True, "explicit local safe-public federation"),
            lease_actions={FEDERATION_ACTION},
            adapter_actions={FEDERATION_ACTION},
            mission_risk_allowed=True,
            budget_available=True,
            tenant_id=args.tenant,
            repository_id=args.portfolio_repository_id,
            actor_id=FEDERATION_ACTOR,
            decision_id="decision:explicit-local-safe-public-federation",
            lease_id="lease:single-local-safe-public-federation",
        )
    )
    try:
        result = project_federation(
            args.source,
            args.portfolio_vault,
            tenant_id=args.tenant,
            portfolio_repository_id=args.portfolio_repository_id,
            check=check,
            authority=authority,
        )
    except (FederationError, OSError, PermissionError, ValueError) as error:
        print(
            json.dumps(
                {"schema_version": "hive-federation-failure/v1", "status": "failed", "error": f"{type(error).__name__}: {error}"[:8192]},
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
