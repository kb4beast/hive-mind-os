#!/usr/bin/env python3
"""Fail-closed independent verifier for the Generic Hive Mind V3 overlay.

The verifier deliberately does not import or execute ``materialize_plan.py`` or
any target-repository Python.  It validates the manifest and every declared
source byte snapshot first, then independently reconstructs the complete plan,
its Standard-V2 node seals, plan seal, topology, traceability, ownership,
effects, host manifest, and manual-parent boundary.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parents[3]

MAX_MANIFEST_BYTES = 262_144
MAX_SOURCE_JSON_BYTES = 1_000_000
MAX_PLAN_BYTES = 2_000_000
MAX_JSON_DEPTH = 48
MAX_GIT_OUTPUT_BYTES = 16_777_216
GIT_TIMEOUT_SECONDS = 60
MAX_TRACKED_FILE_BYTES = 2_097_152
MAX_GIT_POINTER_BYTES = 4_096
MAX_GIT_INDEX_BYTES = 16_777_216

PLAN_ID = "generic-hive-mind-product-v3"
REQUEST_ID = "sha256:baa813bdcbd1b3bd459736cb65dccaf060758991a8a9b581fe8a1bf17dd65562"
OBJECTIVE_DIGEST = "sha256:36125297e861b0fea8d1be8b81e985445957f85378dc35c6712896b7b4d93c9c"
REPOSITORY_ID = "sha256:48eb2b11cd99bb34f430f5e1c7a39d9a32b9bbaac6a99db4736d2ac422915590"
TASK_KEY = "DAG-BUILD-48eb2b11cd99-baa813bdcbd1"
LAUNCH_DIGEST = "sha256:475c6908392956991faec25293170750e17fac70a97e62f550bb6d6164eb4461"
TARGET_BRANCH = "release/hive-mind-autopilot"
REQUEST_OBSERVED_HEAD = "44224532dc25b94a95c3184054ec81762a258259"
REQUEST_OBSERVED_TREE = "c2e7b983e9ed430ea8e3f7013ee2d8cb02a60e33"
QUALIFIED_PREREQUISITE_COMMIT = "ca43709591313c1c166a2e655b8982ccff16daf3"
QUALIFIED_PREREQUISITE_TREE = "22639258c7a524ffda25272ccf34fede176b2663"
COMBINED_ENVELOPE_COMMIT = "877bf9fc9cdbef94e6fc33ff9e22fe53349db130"
COMBINED_ENVELOPE_TREE = "1ede87e53fc7fc75d29968698ba4b8dab082dd1e"
PLAN_AUTHORING_BASE_COMMIT = "42b4aeef17f816430a7d8a435102635afea8761a"
PLAN_AUTHORING_BASE_TREE = "b896e16755a1d6864989757732fdc5ca9d2b5eed"
PAYLOAD_A_COMMIT = "4e2b81b932e5145f24c4b52ceeee664bff91df2e"
PAYLOAD_A_TREE = "8c42aeaf4ed480dd3ccc353356b7fa9f3ed49157"
PAYLOAD_A_MANIFEST_RAW_DIGEST = "sha256:87914018e98effc32a067146593191a82f4a01c122f4ab0695304c0c3eb54522"
PAYLOAD_A_AGGREGATE_DIGEST = "sha256:ff7a0f323aac32da18c70d6f871ddc0918225ddd47de0c15618822be84706d78"
CORRECTION_PARENT_COMMIT = "f06e52c43a1e2d1d53523378c0d6f5564fb984bf"
CORRECTION_PARENT_TREE = "8730203c89835c4d1d9dac4be9b2086dacd2d869"
CORRECTION_PARENT_MANIFEST_RAW_DIGEST = "sha256:b3ea9cbc2766cc1fa72a41f097de491a8b0ae5b9b482c57667bd31c1393fa339"
CORRECTION_PARENT_AGGREGATE_DIGEST = "sha256:229821586021d8e2769035aeca4a4589cb7b458a9740a8b8ca82ebdfdadaee36"
CORRECTION_PARENT_REPORT_DIGEST = "sha256:731beb68c2fed2c1a3d8666530c1f193b2e21144428448816216b4f9b0bba810"
SOURCE_INTAKE_DIGEST = "sha256:dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c"
STANDARD_DIGEST = "sha256:3b072fee295e75b8c28709d417f9036fa384e31dc53ca85526babd0881d0e90a"
STANDARD_BLOB = "2bc9c0fa3baf6fb5cc720ffdbf7528e93f4e7374"
COMPILER_DIGEST = "sha256:105674faf15aaf7b9f4c9db7ad4003fda404438eed2bf8cc3a1782c1cf321e6a"
COMPILER_BLOB = "f170ac4f388d265fcaafd32437e449945dcebee3"
V1_EXPECTED_PLAN_DIGEST = "sha256:b8879d09c5a42b0feeeec19b9c8f6a7523e4ef69b117eea1a18ef6dfaf35f977"
EXPECTED_PLAN_DIGEST = "sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1"
EXPECTED_PLAN_RAW_DIGEST = "sha256:5e03c7638b2d4865dda2b2c3a5e615ea4b2b8d37f61a3a5fdfbf29c1750827c4"
EXPECTED_FROZEN_HOST_BUNDLE = "sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255"

EXPECTED_OVERLAY_SOURCES = {
    "node-contracts.json": (64381, "sha256:eef8694c935467bade1fed286ef9cce67f01e2f35f0b914105255bf8681e3cf8"),
    "traceability.json": (24865, "sha256:4182ab1d43deaabe41b50e8c534d2f6de33d399696cb69611391858f17eaa786"),
    "ownership-effects.json": (10943, "sha256:056b74b37da1e7292d7931b93c5975c2c589ce4b64c8bf0004ca12f5deebaf80"),
    "materialize_plan.py": (25309, "sha256:63c2dd154fc1a6e4db9e9ca5ca7e06d57ef93f141a921ff3189fa77b4b48464c"),
}

EXPECTED_PAYLOAD_PATHS = (
    "docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md",
    "docs/architecture/ADR_INDEX.md",
    "docs/execution/dags/generic-hive-mind-product-v3/README.md",
    "docs/execution/dags/generic-hive-mind-product-v3/manifest.json",
    "docs/execution/dags/generic-hive-mind-product-v3/materialize_plan.py",
    "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json",
    "docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json",
    "docs/execution/dags/generic-hive-mind-product-v3/plan.json",
    "docs/execution/dags/generic-hive-mind-product-v3/traceability.json",
    "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py",
    "tests/test_generic_dag_v3_overlay.py",
)
EXPECTED_CHANGED_PATHS = (
    "docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md",
    "docs/execution/dags/generic-hive-mind-product-v3/README.md",
    "docs/execution/dags/generic-hive-mind-product-v3/manifest.json",
    "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py",
    "tests/test_generic_dag_v3_overlay.py",
)
MANIFEST_RELATIVE_PATH = "docs/execution/dags/generic-hive-mind-product-v3/manifest.json"
OVERLAY_RELATIVE_DIRECTORY = "docs/execution/dags/generic-hive-mind-product-v3"
ALLOWED_UNTRACKED_PATH = ".hive-mind/autopilot-request.json"

EXPECTED_REPOSITORY_SOURCES = {
    "LICENSE": (1065, "sha256:6e76d648ae297aa3dcefc739604cfcfab2a50b484ab7331090c745a089de21f8", "06da1af7996f5e2b059cd52045e36f9f2cfac201"),
    "docs/execution/DAG_AUTHORING_STANDARD.md": (27006, "sha256:86d1c1c81a27fc3e3ffd931193e0e145030756f78b58c674e8ba8b1c1bd3397d", "70e43b0a8078a303d44c0109b8dd218a948258c2"),
    "docs/execution/DAG_AUTHORING_STANDARD_V2.md": (12312, STANDARD_DIGEST, STANDARD_BLOB),
    ".autopilot/bin/dag_standard.py": (104317, COMPILER_DIGEST, COMPILER_BLOB),
    ".autopilot/plan.json": (169053, "sha256:85fd0c69fed4aa8cd40019bfeaccc5a686fa408ae5183060ae0320d412cea9ef", "ee7ec9f2756fcff2b7010238d7064d017c4df7af"),
    "docs/execution/dags/generic-hive-mind-product-v3/source-intake.json": (58463, SOURCE_INTAKE_DIGEST, "6dcc1b506fe9806b32eb6160de6994bd9e71bf58"),
    "evidence/autopilot/COMBINED-PREREQUISITE-QUALIFICATION-2026-08-23.md": (10498, "sha256:a514b794be97268b6b2fe1daae08e191ef7c993e0928b73d977802a8137cc95e", "fc56f63f576a2839ef7b3b24e72f246e1dc5644b"),
    "evidence/courts/CASE-COMBINED-AUTOPILOT-PREREQUISITES-2026-08-23.json": (6586, "sha256:fcd5b64824ac6a31492b4a454528b6093648ac170c0fdaaa9f00d69bf869e8dc", "2de4ddb37d5b8605f74a060377e52c9b5923fba9"),
    "docs/execution/dags/generic-hive-mind-product-v1/README.md": (3506, "sha256:b83c659f3a4f9cf1be4ab707246636d9cc40f09ee28d14a6e0020b31b512f82b", "7fe726912358e62bb557a0dcf043ad6e69629302"),
    "docs/execution/dags/generic-hive-mind-product-v1/generate_plan.py": (6128, "sha256:ad540bf2e29e147671b715098ae3a9209fa7e9d4cdc62bd7bdd3df0368ba726c", "b61407bb871e17e07da060ee4796bae05957afa6"),
    "docs/execution/dags/generic-hive-mind-product-v1/manifest.json": (1363, "sha256:dd0adbe4bef4cce5343e5852a6d7076fb71c383f71456b4a86acbc11e187e02e", "e4e0d24c90c0e9b9f13e15fb90b9bd31a75e3bf5"),
    "docs/execution/dags/generic-hive-mind-product-v1/specs_a.py": (15352, "sha256:7616bd7229670daffed1040b037a9d2de73e447e9b50115bb0a7aab2334e4027", "0adb16c3de4b7f78739aed2d00b64eb8a549f4f8"),
    "docs/execution/dags/generic-hive-mind-product-v1/specs_b.py": (14810, "sha256:5f9cde6830880c5e5fcee88ac4973c172133e12bceb8b13514a192dbb3444eb6", "0ed6d109bdf09037c41db56f25ca155b4179b2d4"),
    "docs/execution/dags/generic-hive-mind-product-v1/verify_plan.py": (5684, "sha256:467e07a363a150914fa40ee3a225f4adc9a49a7f7e7be06fd287e60a425c43bf", "4078803e652ca3be1a38baafb0b186be9420d848"),
}

EXPECTED_NODE_ORDER = [
    "BASELINE-000", "DOCTOR-PREFLIGHT-005", "FOUNDATION-010", "PLAN-CORE-100",
    "RUNTIME-CONTRACTS-150", "BUILD-SYSTEM-200", "ADAPTER-INDEX-210",
    "WAVE-HOST-300", "TASK-REUSE-310", "RUNTIME-TOKEN-320",
    "GENERIC-EXECUTOR-400", "CONTROL-TOKEN-410", "PUBLIC-RUNTIME-500",
    "GENERIC-FIXTURES-600", "FAILURE-QUALIFICATION-610", "TOKEN-BENCHMARK-620",
    "QUALIFICATION-PREP-625", "CANDIDATE-CI-627", "GENERIC-QUALIFICATION-630",
    "HANDOFF-700",
]


class VerificationError(RuntimeError):
    """A declared V3 trust or data invariant did not verify."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def read_bounded_bytes(path: Path, *, label: str, size_limit: int) -> bytes:
    require(isinstance(size_limit, int) and size_limit >= 0, f"invalid {label} size limit")
    try:
        require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
        path_state = path.stat()
        require(path_state.st_size <= size_limit, f"{label} exceeds size limit {size_limit}")
        with path.open("rb") as handle:
            open_state = os.fstat(handle.fileno())
            require(
                (open_state.st_dev, open_state.st_ino) == (path_state.st_dev, path_state.st_ino),
                f"{label} path/open-file identity mismatch",
            )
            raw = handle.read(size_limit + 1)
            require(len(raw) <= size_limit, f"{label} exceeds size limit {size_limit}")
            final_open_state = os.fstat(handle.fileno())
        final_path_state = path.stat()
    except OSError as error:
        raise VerificationError(f"cannot read {label}: {error}") from error
    require(
        (final_open_state.st_dev, final_open_state.st_ino, final_open_state.st_size)
        == (open_state.st_dev, open_state.st_ino, open_state.st_size),
        f"{label} open-file identity/size changed while reading",
    )
    require(
        (final_path_state.st_dev, final_path_state.st_ino, final_path_state.st_size)
        == (path_state.st_dev, path_state.st_ino, path_state.st_size),
        f"{label} path identity/size changed while reading",
    )
    require(len(raw) == final_open_state.st_size, f"{label} read length differs from file size")
    return raw


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise VerificationError(f"non-canonical JSON material: {error}") from error


def digest(value: object) -> str:
    return sha256_bytes(canonical_bytes(value))


def reject_constant(value: str) -> None:
    raise VerificationError(f"non-finite JSON number is forbidden: {value}")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def validate_depth_and_numbers(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise VerificationError(f"JSON nesting exceeds maximum depth {MAX_JSON_DEPTH}")
        if isinstance(current, float) and not math.isfinite(current):
            raise VerificationError("non-finite JSON number is forbidden")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def parse_strict_json(raw: bytes, *, label: str, size_limit: int) -> dict[str, Any]:
    require(len(raw) <= size_limit, f"{label} exceeds size limit {size_limit}")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise VerificationError(f"cannot parse strict JSON {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be a JSON object")
    validate_depth_and_numbers(value)
    return value


def read_strict_json(path: Path, *, label: str, size_limit: int) -> tuple[dict[str, Any], bytes]:
    raw = read_bounded_bytes(path, label=label, size_limit=size_limit)
    return parse_strict_json(raw, label=label, size_limit=size_limit), raw


def safe_child(root: Path, relative: str, *, label: str) -> Path:
    require(isinstance(relative, str) and relative and "\\" not in relative, f"bad {label} path")
    candidate = root / relative
    require(not candidate.is_symlink(), f"symlink is forbidden for {label}: {relative}")
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise VerificationError(f"{label} path escapes its root: {relative}") from error
    return resolved


_GIT_BOUNDARY: dict[str, Any] | None = None


def _windows_system_environment() -> dict[str, str]:
    if os.name != "nt":
        return {}
    buffer = ctypes.create_unicode_buffer(32_768)
    length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    require(0 < length < len(buffer), "cannot resolve the Windows system directory")
    windows_root = str(Path(buffer.value).resolve())
    return {"SYSTEMROOT": windows_root, "WINDIR": windows_root}


def _read_gitdir_pointer(path: Path, *, label: str) -> Path:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    raw = read_bounded_bytes(path, label=label, size_limit=MAX_GIT_POINTER_BYTES)
    require(0 < len(raw) and b"\0" not in raw, f"{label} is malformed")
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeError as error:
        raise VerificationError(f"{label} is not UTF-8") from error
    prefix = "gitdir:"
    require(text.casefold().startswith(prefix), f"{label} lacks a gitdir pointer")
    value = text[len(prefix) :].strip()
    require(bool(value), f"{label} gitdir pointer is empty")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = path.parent / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"{label} gitdir cannot be resolved: {error}") from error
    require(resolved.is_dir() and not resolved.is_symlink(), f"{label} gitdir is not a regular directory")
    return resolved


def _resolve_git_dir(repo_root: Path) -> Path:
    dot_git = repo_root / ".git"
    require(not dot_git.is_symlink(), "repository .git symlink is forbidden")
    if dot_git.is_dir():
        return dot_git.resolve(strict=True)
    git_dir = _read_gitdir_pointer(dot_git, label="repository .git file")
    back_pointer = git_dir / "gitdir"
    require(back_pointer.is_file() and not back_pointer.is_symlink(), "linked-worktree gitdir backlink missing")
    raw = read_bounded_bytes(
        back_pointer,
        label="linked-worktree gitdir backlink",
        size_limit=MAX_GIT_POINTER_BYTES,
    )
    require(0 < len(raw) and b"\0" not in raw, "linked-worktree gitdir backlink is malformed")
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeError as error:
        raise VerificationError("linked-worktree gitdir backlink is not UTF-8") from error
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = git_dir / candidate
    try:
        resolved_back_pointer = candidate.resolve(strict=True)
        resolved_dot_git = dot_git.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"linked-worktree gitdir backlink cannot be resolved: {error}") from error
    require(resolved_back_pointer == resolved_dot_git, "linked-worktree gitdir backlink mismatch")
    return git_dir


def _resolve_common_git_dir(git_dir: Path) -> Path:
    pointer = git_dir / "commondir"
    if not pointer.exists():
        common_dir = git_dir
    else:
        require(pointer.is_file() and not pointer.is_symlink(), "Git commondir pointer must be a regular file")
        raw = read_bounded_bytes(pointer, label="Git commondir pointer", size_limit=MAX_GIT_POINTER_BYTES)
        require(0 < len(raw) and b"\0" not in raw, "Git commondir pointer is malformed")
        try:
            value = raw.decode("utf-8").strip()
        except UnicodeError as error:
            raise VerificationError("Git commondir pointer is not UTF-8") from error
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = git_dir / candidate
        try:
            common_dir = candidate.resolve(strict=True)
        except OSError as error:
            raise VerificationError(f"Git commondir cannot be resolved: {error}") from error
    require(common_dir.is_dir() and not common_dir.is_symlink(), "Git common directory is not a regular directory")
    objects = common_dir / "objects"
    require(objects.is_dir() and not objects.is_symlink(), "Git object directory is not a regular directory")
    require(not (objects / "info" / "alternates").exists(), "Git object alternates are forbidden")
    require(not (objects / "info" / "http-alternates").exists(), "Git HTTP object alternates are forbidden")
    return common_dir


def _git_executable_path_state(path: Path) -> tuple[int, int, int, int, int]:
    require(path.is_file() and not path.is_symlink(), "Git executable is no longer a regular file")
    stat_result = path.stat()
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def _open_file_identity(handle: Any) -> tuple[int, int, int, int]:
    stat_result = os.fstat(handle.fileno())
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def _open_file_sha256(handle: Any) -> str:
    digest_state = hashlib.sha256()
    handle.seek(0)
    while True:
        chunk = handle.read(1_048_576)
        if not chunk:
            break
        digest_state.update(chunk)
    handle.seek(0)
    return "sha256:" + digest_state.hexdigest()


def configure_git_boundary(
    repo_root: Path,
    *,
    git_executable: Path,
    expected_git_executable_sha256: str,
) -> None:
    global _GIT_BOUNDARY
    require(_GIT_BOUNDARY is None, "Git execution boundary was already configured")
    inherited_git = sorted(key for key in os.environ if key.casefold().startswith("git_"))
    require(not inherited_git, f"inherited Git environment is forbidden: {', '.join(inherited_git)}")
    require(
        isinstance(expected_git_executable_sha256, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", expected_git_executable_sha256) is not None,
        "caller must supply a canonical expected Git executable SHA-256",
    )
    require(git_executable.is_absolute(), "Git executable path must be absolute")
    try:
        resolved_executable = git_executable.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"Git executable cannot be resolved: {error}") from error
    require(resolved_executable == git_executable, "Git executable path must already be canonical")
    if os.name == "nt":
        require(resolved_executable.suffix.casefold() == ".exe", "Git executable must be a native .exe file")
    else:
        require(os.access(resolved_executable, os.X_OK), "Git executable is not executable")
    try:
        executable_handle = resolved_executable.open("rb")
    except OSError as error:
        raise VerificationError(f"cannot open Git executable: {error}") from error
    path_state = _git_executable_path_state(resolved_executable)
    handle_identity = _open_file_identity(executable_handle)
    require(handle_identity == path_state[:4], "Git executable path/open-file identity mismatch")
    require(
        _open_file_sha256(executable_handle) == expected_git_executable_sha256,
        "caller-authenticated Git executable digest mismatch",
    )
    git_dir = _resolve_git_dir(repo_root)
    common_dir = _resolve_common_git_dir(git_dir)
    index_path = git_dir / "index"
    require(index_path.is_file() and not index_path.is_symlink(), "Git index must be a regular file")
    require(index_path.stat().st_size <= MAX_GIT_INDEX_BYTES, "Git index exceeds the verifier limit")
    environment = {
        "PATH": str(resolved_executable.parent),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_DISCOVERY_ACROSS_FILESYSTEM": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    environment.update(_windows_system_environment())
    _GIT_BOUNDARY = {
        "executable": resolved_executable,
        "expected_sha256": expected_git_executable_sha256,
        "path_state": path_state,
        "handle_identity": handle_identity,
        "handle": executable_handle,
        "git_dir": git_dir,
        "common_dir": common_dir,
        "index_path": index_path.resolve(strict=True),
        "work_tree": repo_root,
        "environment": environment,
    }


def verify_git_executable_stable(*, full_digest: bool) -> None:
    require(_GIT_BOUNDARY is not None, "Git execution boundary is not configured")
    executable = _GIT_BOUNDARY["executable"]
    handle = _GIT_BOUNDARY["handle"]
    require(_git_executable_path_state(executable) == _GIT_BOUNDARY["path_state"], "Git executable identity changed during verification")
    require(
        _open_file_identity(handle) == _GIT_BOUNDARY["handle_identity"],
        "open Git executable identity changed during verification",
    )
    if full_digest:
        require(
            _open_file_sha256(handle) == _GIT_BOUNDARY["expected_sha256"],
            "retained Git executable bytes changed during verification",
        )
        try:
            with executable.open("rb") as current_handle:
                require(
                    _open_file_identity(current_handle) == _GIT_BOUNDARY["handle_identity"],
                    "Git executable path now addresses a different file",
                )
                require(
                    _open_file_sha256(current_handle) == _GIT_BOUNDARY["expected_sha256"],
                    "Git executable path bytes changed during verification",
                )
        except OSError as error:
            raise VerificationError(f"cannot re-open Git executable: {error}") from error


def git(repo_root: Path, *args: str, binary: bool = False) -> str | bytes:
    require(_GIT_BOUNDARY is not None, "Git execution boundary is not configured")
    require(repo_root == _GIT_BOUNDARY["work_tree"], "Git worktree binding mismatch")
    verify_git_executable_stable(full_digest=True)
    command = [
        str(_GIT_BOUNDARY["executable"]),
        "--no-pager",
        "--no-replace-objects",
        "--no-lazy-fetch",
        "--no-optional-locks",
        "--literal-pathspecs",
        f"--git-dir={_GIT_BOUNDARY['git_dir']}",
        f"--work-tree={repo_root}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        f"core.attributesFile={os.devnull}",
        "-c",
        f"core.excludesFile={os.devnull}",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "diff.external=",
        *args,
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=_GIT_BOUNDARY["executable"].parent,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_GIT_BOUNDARY["environment"],
            executable=str(_GIT_BOUNDARY["executable"]),
            shell=False,
            close_fds=True,
            bufsize=0,
        )
    except OSError as error:
        verify_git_executable_stable(full_digest=True)
        raise VerificationError(f"git {' '.join(args)} could not start: {error}") from error

    require(process.stdout is not None, "Git output pipe was not created")
    output = bytearray()
    output_overflow = threading.Event()
    reader_errors: list[BaseException] = []

    def read_bounded_output() -> None:
        try:
            with process.stdout:
                while True:
                    remaining = MAX_GIT_OUTPUT_BYTES + 1 - len(output)
                    chunk = process.stdout.read(min(65_536, remaining))
                    if not chunk:
                        return
                    output.extend(chunk)
                    if len(output) > MAX_GIT_OUTPUT_BYTES:
                        output_overflow.set()
                        try:
                            process.kill()
                        except OSError:
                            pass
                        return
        except BaseException as error:  # pragma: no cover - defensive pipe failure
            reader_errors.append(error)
            try:
                process.kill()
            except OSError:
                pass

    reader = threading.Thread(target=read_bounded_output, name="v3-git-output-reader", daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait(timeout=5)
    reader.join(timeout=5)
    if reader.is_alive():
        process.stdout.close()
        reader.join(timeout=1)
    verify_git_executable_stable(full_digest=True)
    require(not reader.is_alive(), "Git output pipe did not close after process exit")
    require(not reader_errors, f"Git output reader failed: {reader_errors[0] if reader_errors else ''}")
    raw = bytes(output)
    require(not output_overflow.is_set(), "Git output exceeds the verifier limit")
    if timed_out:
        rendered = raw.decode("utf-8", errors="replace").strip()
        raise VerificationError(
            f"git {' '.join(args)} timed out: {rendered or f'{GIT_TIMEOUT_SECONDS} seconds'}"
        )
    if process.returncode != 0:
        rendered = raw.decode("utf-8", errors="replace").strip()
        raise VerificationError(
            f"git {' '.join(args)} failed: {rendered or f'exit {process.returncode}'}"
        )
    if binary:
        return raw
    try:
        return raw.decode("utf-8").strip()
    except UnicodeError as error:
        raise VerificationError(f"git {' '.join(args)} returned non-UTF-8 output") from error


def verify_commit_object(
    repo_root: Path,
    *,
    commit: str,
    tree: str,
    parent: str | None,
    label: str,
) -> None:
    require(git(repo_root, "cat-file", "-t", commit) == "commit", f"{label} is not a commit object")
    lines = str(git(repo_root, "cat-file", "-p", commit)).splitlines()
    trees = [line.removeprefix("tree ") for line in lines if line.startswith("tree ")]
    parents = [line.removeprefix("parent ") for line in lines if line.startswith("parent ")]
    require(trees == [tree], f"{label} tree mismatch")
    if parent is not None:
        require(parents == [parent], f"{label} parent mismatch")


def validate_manifest_constants(manifest: dict[str, Any]) -> None:
    require(
        set(manifest)
        == {
            "schema_version",
            "kind",
            "plan_id",
            "authorship",
            "request_binding",
            "snapshot_lineage",
            "committed_payload_contract",
            "source_bindings",
            "plan_binding",
            "topology",
            "execution_contract",
            "standard_and_compiler",
            "frozen_host_prerequisite",
            "evidence_partition",
            "source_governance",
            "execution_authorized",
            "nonclaims",
        },
        "manifest top-level field inventory mismatch",
    )
    require(manifest.get("schema_version") == 3, "manifest schema mismatch")
    require(manifest.get("kind") == "hive-mind-generic-product-overlay-manifest-v3", "manifest kind mismatch")
    require(manifest.get("plan_id") == PLAN_ID, "manifest plan id mismatch")
    request = manifest.get("request_binding")
    require(isinstance(request, dict), "manifest request binding missing")
    expected_request = {
        "request_id": REQUEST_ID,
        "objective_digest": OBJECTIVE_DIGEST,
        "repository_id": REPOSITORY_ID,
        "task_key": TASK_KEY,
        "launch_digest": LAUNCH_DIGEST,
        "target_branch": TARGET_BRANCH,
    }
    require(request == expected_request, "manifest request/repository/objective binding mismatch")
    lineage = manifest.get("snapshot_lineage")
    require(isinstance(lineage, dict), "manifest snapshot lineage missing")
    require(
        set(lineage)
        == {
            "request_observation",
            "qualified_prerequisite",
            "combined_envelope_b",
            "authoring_base_parent",
            "correction_parent",
        },
        "snapshot lineage field inventory mismatch",
    )
    require(lineage.get("request_observation") == {"commit": REQUEST_OBSERVED_HEAD, "tree": REQUEST_OBSERVED_TREE}, "request snapshot mismatch")
    require(lineage.get("qualified_prerequisite") == {"commit": QUALIFIED_PREREQUISITE_COMMIT, "tree": QUALIFIED_PREREQUISITE_TREE}, "qualified prerequisite mismatch")
    require(lineage.get("combined_envelope_b") == {"commit": COMBINED_ENVELOPE_COMMIT, "tree": COMBINED_ENVELOPE_TREE}, "Envelope B snapshot mismatch")
    require(
        lineage.get("authoring_base_parent")
        == {"commit": PLAN_AUTHORING_BASE_COMMIT, "tree": PLAN_AUTHORING_BASE_TREE},
        "authoring-base parent commit/tree mismatch",
    )
    require(
        lineage.get("correction_parent")
        == {"commit": CORRECTION_PARENT_COMMIT, "tree": CORRECTION_PARENT_TREE},
        "correction parent commit/tree mismatch",
    )
    require(
        manifest.get("plan_binding")
        == {
            "expected_plan_digest": EXPECTED_PLAN_DIGEST,
            "expected_raw_bytes_digest": EXPECTED_PLAN_RAW_DIGEST,
            "external_path": "docs/execution/dags/generic-hive-mind-product-v3/plan.json",
            "historical_autopilot_plan_policy": "BYTE_IDENTICAL_READ_ONLY",
            "historical_v1_expected_plan_digest": V1_EXPECTED_PLAN_DIGEST,
        },
        "plan binding mismatch",
    )
    topology = manifest.get("topology")
    require(topology == {"node_count": 20, "raw_edge_count": 28, "level_count": 17, "round_count": 20, "redundant_direct_edge_count": 6}, "manifest topology mismatch")
    require(
        manifest.get("execution_contract")
        == {
            "mode": "manual-parent-v1",
            "executable_dispatch_command_available": False,
            "every_round_command": None,
            "legacy_fallback": "PROHIBITED",
        },
        "manifest execution contract mismatch",
    )
    require(manifest.get("execution_authorized") is False, "checked-in manifest cannot authorize execution")
    authorship = manifest.get("authorship")
    require(isinstance(authorship, dict), "manifest authorship missing")
    require(
        set(authorship) == {"architect", "judge", "court_status", "execution_authority"},
        "manifest authorship field inventory mismatch",
    )
    require(authorship.get("architect") == "/root/generation_architect", "architect identity mismatch")
    require(authorship.get("judge") == "UNASSIGNED", "author manifest cannot self-assign a judge")
    require(authorship.get("court_status") == "PENDING_DISTINCT_COURT", "self-review boundary missing")
    require(authorship.get("execution_authority") == "NONE", "author manifest cannot grant execution authority")
    payload = manifest.get("committed_payload_contract")
    require(isinstance(payload, dict), "committed payload contract missing")
    require(
        set(payload)
        == {
            "mode",
            "authoring_base_parent",
            "correction_parent",
            "predecessor_payload",
            "historical_payload_a",
            "expected_changed_paths",
            "payload_inventory",
            "activation_anti_downgrade",
            "git_execution_boundary",
            "payload_bindings",
            "manifest_authentication",
            "court_envelope_b_bindings",
            "allowed_untracked_paths",
            "authoring_check",
        },
        "committed payload field inventory mismatch",
    )
    require(payload.get("mode") == "exact-append-only-git-boundary-correction-v3", "committed payload mode mismatch")
    require(
        payload.get("authoring_base_parent")
        == {"commit": PLAN_AUTHORING_BASE_COMMIT, "tree": PLAN_AUTHORING_BASE_TREE},
        "committed payload parent mismatch",
    )
    require(
        payload.get("correction_parent")
        == {"commit": CORRECTION_PARENT_COMMIT, "tree": CORRECTION_PARENT_TREE},
        "committed correction parent mismatch",
    )
    require(
        payload.get("predecessor_payload")
        == {
            "commit": CORRECTION_PARENT_COMMIT,
            "tree": CORRECTION_PARENT_TREE,
            "parent_commit": PAYLOAD_A_COMMIT,
            "parent_tree": PAYLOAD_A_TREE,
            "manifest_raw_sha256": CORRECTION_PARENT_MANIFEST_RAW_DIGEST,
            "full_payload_aggregate": {
                "domain": "hive-mind-os/v3-append-only-correction-content/v2",
                "sha256": CORRECTION_PARENT_AGGREGATE_DIGEST,
            },
            "qualification_report_sha256": CORRECTION_PARENT_REPORT_DIGEST,
            "observed_status": "QUALIFICATION_REMANDED_GIT_ENVIRONMENT_FAIL_OPEN",
            "author_proposed_disposition": "ADAPT_REMAND",
        },
        "predecessor correction identity/status mismatch",
    )
    require(
        payload.get("historical_payload_a")
        == {
            "commit": PAYLOAD_A_COMMIT,
            "tree": PAYLOAD_A_TREE,
            "parent_commit": PLAN_AUTHORING_BASE_COMMIT,
            "parent_tree": PLAN_AUTHORING_BASE_TREE,
            "manifest_raw_sha256": PAYLOAD_A_MANIFEST_RAW_DIGEST,
            "full_payload_aggregate": {
                "domain": "hive-mind-os/v3-payload-a-content/v1",
                "sha256": PAYLOAD_A_AGGREGATE_DIGEST,
            },
            "observed_status": "FOCUSED_SUITE_FAILED_12_OF_14",
            "author_proposed_disposition": "ADAPT_SUPERSEDE",
        },
        "historical Payload A identity/status mismatch",
    )
    require(payload.get("expected_changed_paths") == list(EXPECTED_CHANGED_PATHS), "committed payload path allowlist mismatch")
    require(payload.get("payload_inventory") == list(EXPECTED_PAYLOAD_PATHS), "committed payload inventory mismatch")
    require(
        payload.get("activation_anti_downgrade")
        == {
            "required_contract_mode": "exact-append-only-git-boundary-correction-v3",
            "rejected_predecessor_manifest_raw_sha256": CORRECTION_PARENT_MANIFEST_RAW_DIGEST,
            "rejected_historical_payload_a_manifest_raw_sha256": PAYLOAD_A_MANIFEST_RAW_DIGEST,
            "predecessor_activation": "PROHIBITED",
            "historical_payload_a_activation": "PROHIBITED",
            "legacy_v1_fallback": "PROHIBITED",
            "external_minimum_version_and_revocation_policy": "REQUIRED_NOT_SATISFIED",
        },
        "activation anti-downgrade contract mismatch",
    )
    require(
        payload.get("git_execution_boundary")
        == {
            "policy": "caller-absolute-raw-sha256-v1",
            "inherited_git_environment": "REJECT_ALL_CASE_INSENSITIVE_GIT_PREFIX",
            "child_environment": "MINIMAL_ALLOWLIST_V1",
            "path_lookup": "PROHIBITED",
            "repository_addressing": "EXPLICIT_GIT_DIR_AND_WORK_TREE",
            "system_and_global_config": "DISABLED",
            "local_risk_overrides": [
                "core.fsmonitor=false",
                "core.hooksPath=<os-devnull>",
                "core.attributesFile=<os-devnull>",
                "core.excludesFile=<os-devnull>",
                "core.untrackedCache=false",
                "diff.external=",
            ],
            "tracked_state": "RAW_HEAD_INDEX_WORKTREE_BLOB_EQUALITY",
            "object_alternates": "PROHIBITED",
            "per_invocation_executable_revalidation": True,
            "final_cleanliness_revalidation": True,
            "strong_read_only_runtime": "REQUIRED_FOR_EXECUTION_NOT_SATISFIED",
        },
        "Git execution boundary contract mismatch",
    )
    require(payload.get("allowed_untracked_paths") == [ALLOWED_UNTRACKED_PATH], "untracked exception contract mismatch")
    require(payload.get("authoring_check") == "NON_EXECUTING_NON_QUALIFYING_ONLY", "authoring mode boundary mismatch")
    require(
        payload.get("manifest_authentication")
        == {"mode": "caller-supplied-raw-sha256", "required": True},
        "caller manifest authentication contract mismatch",
    )
    require(
        payload.get("court_envelope_b_bindings")
        == [
            "committed_contract_mode",
            "correction_parent_commit",
            "correction_parent_tree",
            "committed_payload_head",
            "committed_payload_tree",
            "caller_authenticated_manifest_digest",
            "caller_authenticated_git_executable_path_and_digest",
            "corrected_full_payload_aggregate_digest",
            "predecessor_payload_identity",
            "predecessor_supersession_verdict",
            "predecessor_qualification_report_digest",
            "historical_payload_a_identity_and_disposition",
            "court_verdict",
            "external_minimum_version_and_revocation_policy_digest",
        ],
        "court Envelope B committed identity contract mismatch",
    )
    bindings = manifest.get("source_bindings")
    require(isinstance(bindings, dict) and set(bindings) == {"repository", "overlay"}, "source binding field inventory mismatch")
    require(
        manifest.get("standard_and_compiler")
        == {
            "standard_v2_sha256": STANDARD_DIGEST,
            "standard_v2_git_blob": STANDARD_BLOB,
            "compiler_sha256": COMPILER_DIGEST,
            "compiler_git_blob": COMPILER_BLOB,
        },
        "standard/compiler contract mismatch",
    )
    require(
        manifest.get("frozen_host_prerequisite")
        == {
            "extraction_commit": QUALIFIED_PREREQUISITE_COMMIT,
            "extraction_tree": QUALIFIED_PREREQUISITE_TREE,
            "manifest_location": "node-contracts.json#/frozen_host_contract/file_manifest",
            "file_count": 16,
            "bundle_sha256": EXPECTED_FROZEN_HOST_BUNDLE,
            "status": "REQUIRED_NOT_SATISFIED",
        },
        "frozen-host prerequisite contract mismatch",
    )
    require(
        manifest.get("evidence_partition")
        == {
            "checked_in": "Inert design, traceability, source bindings, and sealed external plan; never activation authority.",
            "host_external": "Distinct-principal signed one-run activation bundle, pristine cache-free host extraction, trust receipts, lease ledger, and Envelope B evidence-only worktree/branch.",
            "candidate_rule": "Qualification evidence never dirties or reidentifies the frozen candidate tree.",
        },
        "evidence partition contract mismatch",
    )
    require(
        manifest.get("source_governance")
        == {
            "SRC-024": "QUARANTINE_CONTENT_UNREAD",
            "SRC-025": "UNRESOLVED",
            "a5_full_autonomy": "NOT_READY",
        },
        "source governance contract mismatch",
    )
    require(
        manifest.get("nonclaims")
        == [
            "This checked-in manifest is not an activation bundle or execution authority.",
            "The legacy continuation outcome was withheld and does not dispatch V3.",
            "No full-autonomy, production, release, or superiority claim is made.",
            "Every manual-parent-v1 round command is null until a separately trusted host supplies bounded execution.",
        ],
        "manifest nonclaims mismatch",
    )
    verify_no_runnable_commands(manifest, label="manifest")


def source_rows(section: object, *, label: str) -> dict[str, dict[str, Any]]:
    require(isinstance(section, list), f"{label} source list missing")
    result: dict[str, dict[str, Any]] = {}
    for item in section:
        require(isinstance(item, dict), f"{label} source entry malformed")
        path = item.get("path")
        require(isinstance(path, str) and path and path not in result, f"{label} source path malformed")
        result[path] = item
    return result


def verify_manifest_declared_sources(
    manifest: dict[str, Any], *, overlay_dir: Path, repo_root: Path
) -> dict[str, bytes]:
    """Verify every source byte declaration before authored data is interpreted."""

    bindings = manifest.get("source_bindings")
    require(isinstance(bindings, dict), "manifest source bindings missing")
    repository = source_rows(bindings.get("repository"), label="repository")
    overlay = source_rows(bindings.get("overlay"), label="overlay")
    require(set(repository) == set(EXPECTED_REPOSITORY_SOURCES), "repository source inventory mismatch")
    require(set(overlay) == set(EXPECTED_OVERLAY_SOURCES) | {"verify_plan.py"}, "overlay source inventory mismatch")

    verified: dict[str, bytes] = {}
    for relative, expected in EXPECTED_REPOSITORY_SOURCES.items():
        row = repository[relative]
        expected_bytes, expected_digest, expected_blob = expected
        require(row == {"path": relative, "bytes": expected_bytes, "sha256": expected_digest, "git_blob": expected_blob}, f"manifest repository source binding mismatch: {relative}")
        path = safe_child(repo_root, relative, label="repository source")
        raw = read_bounded_bytes(path, label=f"repository source {relative}", size_limit=MAX_TRACKED_FILE_BYTES)
        require(len(raw) == expected_bytes, f"repository source size mismatch: {relative}")
        require(sha256_bytes(raw) == expected_digest, f"repository source digest mismatch: {relative}")
        require(
            git(repo_root, "rev-parse", f"{PLAN_AUTHORING_BASE_COMMIT}:{relative}") == expected_blob,
            f"repository source Git blob mismatch: {relative}",
        )
        verified[f"repository:{relative}"] = raw

    for relative, (expected_bytes, expected_digest) in EXPECTED_OVERLAY_SOURCES.items():
        row = overlay[relative]
        require(row == {"path": relative, "bytes": expected_bytes, "sha256": expected_digest}, f"manifest overlay source binding mismatch: {relative}")
        path = safe_child(overlay_dir, relative, label="overlay source")
        raw = read_bounded_bytes(path, label=f"overlay source {relative}", size_limit=MAX_TRACKED_FILE_BYTES)
        require(len(raw) == expected_bytes, f"overlay source size mismatch: {relative}")
        require(sha256_bytes(raw) == expected_digest, f"overlay source digest mismatch: {relative}")
        verified[f"overlay:{relative}"] = raw

    verifier_row = overlay["verify_plan.py"]
    require(set(verifier_row) == {"path", "bytes", "sha256"}, "verifier source binding malformed")
    verifier_path = safe_child(overlay_dir, "verify_plan.py", label="verifier source")
    verifier_raw = read_bounded_bytes(verifier_path, label="verifier source", size_limit=MAX_TRACKED_FILE_BYTES)
    require(verifier_row["bytes"] == len(verifier_raw), "verifier source size mismatch")
    require(verifier_row["sha256"] == sha256_bytes(verifier_raw), "verifier source digest mismatch")
    verified["overlay:verify_plan.py"] = verifier_raw
    return verified


def payload_path(repo_root: Path, overlay_dir: Path, relative: str) -> Path:
    prefix = OVERLAY_RELATIVE_DIRECTORY + "/"
    if relative.startswith(prefix):
        return safe_child(overlay_dir, relative[len(prefix):], label="committed payload")
    return safe_child(repo_root, relative, label="committed payload")


def verify_payload_bindings(
    manifest: dict[str, Any], *, repo_root: Path, overlay_dir: Path, manifest_raw: bytes
) -> dict[str, bytes]:
    contract = manifest["committed_payload_contract"]
    rows = source_rows(contract.get("payload_bindings"), label="committed payload")
    expected_bound = set(EXPECTED_PAYLOAD_PATHS) - {MANIFEST_RELATIVE_PATH}
    require(set(rows) == expected_bound, "committed payload binding inventory mismatch")
    verified: dict[str, bytes] = {}
    for relative in sorted(expected_bound):
        row = rows[relative]
        require(set(row) == {"path", "bytes", "sha256"}, f"committed payload binding malformed: {relative}")
        raw = read_bounded_bytes(
            payload_path(repo_root, overlay_dir, relative),
            label=f"committed payload {relative}",
            size_limit=MAX_TRACKED_FILE_BYTES,
        )
        require(row["bytes"] == len(raw), f"committed payload size mismatch: {relative}")
        require(row["sha256"] == sha256_bytes(raw), f"committed payload digest mismatch: {relative}")
        verified[relative] = raw
    require(
        read_bounded_bytes(
            payload_path(repo_root, overlay_dir, MANIFEST_RELATIVE_PATH),
            label="authenticated manifest path",
            size_limit=MAX_MANIFEST_BYTES,
        )
        == manifest_raw,
        "authenticated manifest path bytes mismatch",
    )
    return verified


def verify_committed_payload_git_bytes(repo_root: Path, overlay_dir: Path) -> None:
    changed_paths = set(EXPECTED_CHANGED_PATHS)
    for relative in EXPECTED_PAYLOAD_PATHS:
        entry = str(git(repo_root, "ls-tree", "HEAD", "--", relative))
        header, separator, listed_path = entry.partition("\t")
        fields = header.split()
        require(
            separator == "\t"
            and listed_path == relative
            and len(fields) == 3
            and fields[0] == "100644"
            and fields[1] == "blob",
            f"committed payload is not one regular file: {relative}",
        )
        head_raw = git(repo_root, "cat-file", "blob", f"HEAD:{relative}", binary=True)
        parent_raw = git(
            repo_root,
            "cat-file",
            "blob",
            f"{CORRECTION_PARENT_COMMIT}:{relative}",
            binary=True,
        )
        require(
            read_bounded_bytes(
                payload_path(repo_root, overlay_dir, relative),
                label=f"committed payload worktree {relative}",
                size_limit=MAX_TRACKED_FILE_BYTES,
            )
            == head_raw,
            f"worktree bytes differ from committed payload blob: {relative}",
        )
        if relative in changed_paths:
            require(head_raw != parent_raw, f"successor path did not change from the predecessor correction: {relative}")
        else:
            require(head_raw == parent_raw, f"inherited payload path changed from the predecessor correction: {relative}")


def verify_global_index_visibility(repo_root: Path) -> str:
    raw = git(repo_root, "ls-files", "-v", "-z", binary=True)
    require(isinstance(raw, bytes), "Git index visibility inventory is not binary")
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        require(
            len(entry) > 2 and entry[:2] == b"H ",
            "tracked index visibility flag is not pristine",
        )
    return sha256_bytes(raw)


def _decode_git_path(raw: bytes, *, label: str) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeError as error:
        raise VerificationError(f"{label} path is not UTF-8") from error
    require(value and "\\" not in value, f"{label} path is malformed")
    return value


def verify_tracked_index_and_worktree(repo_root: Path) -> tuple[int, str]:
    tree_raw = git(repo_root, "ls-tree", "-r", "-z", "--full-tree", "HEAD", binary=True)
    index_raw = git(repo_root, "ls-files", "--stage", "-z", binary=True)
    require(isinstance(tree_raw, bytes) and isinstance(index_raw, bytes), "tracked inventory is not binary")

    tree_entries: dict[str, tuple[str, str]] = {}
    for entry in tree_raw.split(b"\0"):
        if not entry:
            continue
        header, separator, path_raw = entry.partition(b"\t")
        fields = header.split()
        path = _decode_git_path(path_raw, label="HEAD tree")
        require(
            separator == b"\t"
            and len(fields) == 3
            and fields[0] in {b"100644", b"100755"}
            and fields[1] == b"blob"
            and re.fullmatch(rb"[0-9a-f]{40}", fields[2]) is not None
            and path not in tree_entries,
            f"unsupported or malformed HEAD tree entry: {path}",
        )
        tree_entries[path] = (fields[0].decode("ascii"), fields[2].decode("ascii"))

    index_entries: dict[str, tuple[str, str]] = {}
    for entry in index_raw.split(b"\0"):
        if not entry:
            continue
        header, separator, path_raw = entry.partition(b"\t")
        fields = header.split()
        path = _decode_git_path(path_raw, label="index")
        require(
            separator == b"\t"
            and len(fields) == 3
            and fields[0] in {b"100644", b"100755"}
            and re.fullmatch(rb"[0-9a-f]{40}", fields[1]) is not None
            and fields[2] == b"0"
            and path not in index_entries,
            f"unsupported or malformed index entry: {path}",
        )
        index_entries[path] = (fields[0].decode("ascii"), fields[1].decode("ascii"))

    require(index_entries == tree_entries, "Git index differs from the exact HEAD tree")
    for relative, (_, blob_sha) in sorted(tree_entries.items()):
        path = safe_child(repo_root, relative, label="tracked worktree")
        require(path.is_file() and not path.is_symlink(), f"tracked worktree path is not a regular file: {relative}")
        raw = read_bounded_bytes(
            path,
            label=f"tracked worktree {relative}",
            size_limit=MAX_TRACKED_FILE_BYTES,
        )
        require(git_blob_sha(raw) == blob_sha, f"tracked worktree bytes differ from HEAD: {relative}")
    inventory = [[path, mode, blob] for path, (mode, blob) in sorted(tree_entries.items())]
    return len(tree_entries), digest(inventory)


def verify_untracked_and_ignored_state(repo_root: Path) -> str:
    def path_set(*args: str) -> set[str]:
        raw = git(repo_root, "ls-files", "-z", *args, binary=True)
        require(isinstance(raw, bytes), "Git path inventory is not binary")
        return {
            _decode_git_path(entry, label="untracked/ignored")
            for entry in raw.split(b"\0")
            if entry
        }

    untracked_paths = path_set("--others", "--exclude-standard")
    ignored_paths = path_set("--others", "--ignored", "--exclude-standard")
    observed_paths = untracked_paths | ignored_paths
    require(
        observed_paths <= {ALLOWED_UNTRACKED_PATH},
        "committed checkout contains an unapproved untracked or ignored path",
    )
    return digest(sorted(observed_paths))


def verify_checkout_cleanliness(repo_root: Path) -> dict[str, Any]:
    visibility_digest = verify_global_index_visibility(repo_root)
    tracked_count, tracked_inventory_digest = verify_tracked_index_and_worktree(repo_root)
    other_path_digest = verify_untracked_and_ignored_state(repo_root)
    return {
        "tracked_path_count": tracked_count,
        "tracked_inventory_digest": tracked_inventory_digest,
        "index_visibility_digest": visibility_digest,
        "untracked_and_ignored_digest": other_path_digest,
    }


def verify_repository_state(
    repo_root: Path, overlay_dir: Path, *, authoring_check: bool
) -> dict[str, Any]:
    verify_commit_object(
        repo_root,
        commit=PLAN_AUTHORING_BASE_COMMIT,
        tree=PLAN_AUTHORING_BASE_TREE,
        parent=None,
        label="plan authoring base",
    )
    verify_commit_object(
        repo_root,
        commit=PAYLOAD_A_COMMIT,
        tree=PAYLOAD_A_TREE,
        parent=PLAN_AUTHORING_BASE_COMMIT,
        label="Payload A",
    )
    verify_commit_object(
        repo_root,
        commit=CORRECTION_PARENT_COMMIT,
        tree=CORRECTION_PARENT_TREE,
        parent=PAYLOAD_A_COMMIT,
        label="remanded correction parent",
    )
    require(git(repo_root, "branch", "--show-current") == TARGET_BRANCH, "live branch mismatch")
    head = str(git(repo_root, "rev-parse", "HEAD"))
    tree = str(git(repo_root, "rev-parse", "HEAD^{tree}"))
    if authoring_check:
        require(head == CORRECTION_PARENT_COMMIT, "authoring check requires the immutable correction parent HEAD")
        require(tree == CORRECTION_PARENT_TREE, "authoring check requires the immutable correction parent tree")
        return {
            "mode": "authoring-correction-check-non-executing",
            "qualification": False,
            "head": head,
            "tree": tree,
            "authoring_base_parent": PLAN_AUTHORING_BASE_COMMIT,
            "correction_parent": CORRECTION_PARENT_COMMIT,
        }

    expected_overlay = safe_child(repo_root, OVERLAY_RELATIVE_DIRECTORY, label="committed overlay directory")
    require(overlay_dir == expected_overlay, "committed verification forbids an alternate overlay path")
    parents = str(git(repo_root, "rev-list", "--parents", "-n", "1", "HEAD")).split()
    require(
        len(parents) == 2 and parents[0] == head and parents[1] == CORRECTION_PARENT_COMMIT,
        "committed payload must be one non-merge direct child of the correction parent",
    )
    verify_commit_object(
        repo_root,
        commit=head,
        tree=tree,
        parent=CORRECTION_PARENT_COMMIT,
        label="correction HEAD",
    )
    changed_raw = git(
        repo_root,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--name-only",
        "--no-renames",
        "-z",
        f"{CORRECTION_PARENT_COMMIT}..HEAD",
        binary=True,
    )
    require(isinstance(changed_raw, bytes), "committed changed-path inventory is not binary")
    changed = tuple(
        sorted(
            _decode_git_path(entry, label="committed changed")
            for entry in changed_raw.split(b"\0")
            if entry
        )
    )
    require(changed == EXPECTED_CHANGED_PATHS, "committed payload changed-path allowlist mismatch")
    checkout_snapshot = verify_checkout_cleanliness(repo_root)
    verify_committed_payload_git_bytes(repo_root, overlay_dir)
    return {
        "mode": "committed-git-boundary-correction-v3",
        "qualification": True,
        "head": head,
        "tree": tree,
        "authoring_base_parent": PLAN_AUTHORING_BASE_COMMIT,
        "correction_parent": CORRECTION_PARENT_COMMIT,
        "checkout_snapshot": checkout_snapshot,
    }


def verify_repository_state_stable_at_end(
    repo_root: Path,
    overlay_dir: Path,
    repository_state: dict[str, Any],
) -> None:
    verify_commit_object(
        repo_root,
        commit=PLAN_AUTHORING_BASE_COMMIT,
        tree=PLAN_AUTHORING_BASE_TREE,
        parent=None,
        label="final plan authoring base",
    )
    verify_commit_object(
        repo_root,
        commit=PAYLOAD_A_COMMIT,
        tree=PAYLOAD_A_TREE,
        parent=PLAN_AUTHORING_BASE_COMMIT,
        label="final Payload A",
    )
    verify_commit_object(
        repo_root,
        commit=CORRECTION_PARENT_COMMIT,
        tree=CORRECTION_PARENT_TREE,
        parent=PAYLOAD_A_COMMIT,
        label="final remanded correction parent",
    )
    require(git(repo_root, "branch", "--show-current") == TARGET_BRANCH, "live branch changed during verification")
    require(git(repo_root, "rev-parse", "HEAD") == repository_state["head"], "HEAD changed during verification")
    require(
        git(repo_root, "rev-parse", "HEAD^{tree}") == repository_state["tree"],
        "HEAD tree changed during verification",
    )
    if repository_state["qualification"]:
        verify_commit_object(
            repo_root,
            commit=repository_state["head"],
            tree=repository_state["tree"],
            parent=CORRECTION_PARENT_COMMIT,
            label="final correction HEAD",
        )
        require(
            verify_checkout_cleanliness(repo_root) == repository_state["checkout_snapshot"],
            "exact checkout snapshot changed during verification",
        )
        verify_committed_payload_git_bytes(repo_root, overlay_dir)


def acceptance_index(nodes: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in nodes:
        node_id = node["id"]
        criteria = node.get("acceptance_criteria")
        require(isinstance(criteria, list) and criteria, f"{node_id} criteria missing")
        for criterion in criteria:
            require(isinstance(criterion, str) and ":" in criterion, f"{node_id} criterion lacks id")
            criterion_id = criterion.split(":", 1)[0]
            require(criterion_id not in result, f"acceptance id collision: {criterion_id}")
            result[criterion_id] = node_id
    return result


def validate_inert_sources(
    contracts: dict[str, Any], traceability: dict[str, Any], ownership: dict[str, Any], intake: dict[str, Any]
) -> None:
    require(contracts.get("schema_version") == 3 and contracts.get("plan_id") == PLAN_ID, "node contract identity mismatch")
    nodes = contracts.get("nodes")
    require(isinstance(nodes, list) and len(nodes) == 20, "expected 20 node contracts")
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    require(ids == EXPECTED_NODE_ORDER and contracts.get("node_order") == EXPECTED_NODE_ORDER, "node order mismatch")
    require(all(node.get("parallel_safe") is False for node in nodes), "exact 20-round serialization missing")
    index = acceptance_index(nodes)

    clerk_trace = intake.get("v1_traceability")
    require(isinstance(clerk_trace, dict), "Clerk V1 traceability missing")
    clerk_rows = clerk_trace.get("rows")
    mappings = traceability.get("rows")
    require(isinstance(clerk_rows, list) and len(clerk_rows) == 89, "Clerk 89-row inventory missing")
    require(isinstance(mappings, dict) and set(mappings) == {row.get("row_id") for row in clerk_rows}, "V1 mapping coverage mismatch")
    require(sum(row.get("row_type") == "objective" for row in clerk_rows) == 16, "V1 objective count mismatch")
    require(sum(row.get("row_type") == "acceptance" for row in clerk_rows) == 73, "V1 acceptance count mismatch")
    for row in clerk_rows:
        row_id = row["row_id"]
        mapping = mappings[row_id]
        require(isinstance(mapping, dict), f"malformed mapping {row_id}")
        require(mapping.get("disposition") == row.get("disposition"), f"disposition mismatch {row_id}")
        targets = mapping.get("target_acceptance_ids")
        require(isinstance(targets, list) and len(targets) == len(set(targets)), f"target mapping malformed {row_id}")
        require(all(target in index for target in targets), f"unknown target acceptance id {row_id}")
        require(any(not target.endswith("-TRACE") for target in targets), f"no substantive mapping {row_id}")
        mapped_nodes = list(dict.fromkeys(index[target] for target in targets))
        require(mapped_nodes == row.get("target_node_ids"), f"target node mapping mismatch {row_id}")

    corners = traceability.get("v3_specific_corners")
    require(isinstance(corners, list) and len(corners) >= 27, "V3 corner inventory incomplete")
    require([item.get("corner_id") for item in corners] == [f"V3-CORNER-{i:03d}" for i in range(1, len(corners) + 1)], "V3 corner ids are not contiguous")
    for corner in corners:
        targets = corner.get("target_acceptance_ids")
        require(isinstance(targets, list) and targets and all(item in index for item in targets), f"corner mapping malformed: {corner.get('corner_id')}")
    supplement = traceability.get("supplemental_execution_path_record")
    require(isinstance(supplement, dict), "execution-path supplement missing")
    require(supplement.get("bound_clerk_intake_sha256") == SOURCE_INTAKE_DIGEST.removeprefix("sha256:"), "supplement Clerk binding mismatch")
    require(supplement.get("status") == "ARCHITECT_PROPOSAL_PENDING_DISTINCT_COURT", "supplement overclaims adjudication")
    correction = supplement.get("clerk_status_correction_nonclaim")
    require(isinstance(correction, dict), "Clerk nested-status correction missing")
    require(correction.get("top_level_status") == intake.get("status"), "Clerk top status was rewritten")
    require(correction.get("nested_topology_status") == intake.get("planned_v3_topology", {}).get("status"), "Clerk nested status was rewritten")

    write_owners: dict[str, str] = {}
    for node in nodes:
        for path in node.get("write_scope", []):
            require(isinstance(path, str) and path and path not in write_owners, f"write path collision: {path}")
            write_owners[path] = node["id"]
    require(len(write_owners) == 85, "expected exactly 85 unique write paths")
    path_contract = ownership.get("path_ownership")
    require(isinstance(path_contract, dict) and path_contract.get("expected_unique_write_path_count") == 85, "ownership path count mismatch")
    effects = ownership.get("node_effect_expectations")
    require(isinstance(effects, dict) and set(effects) == set(ids), "node effect inventory mismatch")
    for node in nodes:
        expected = effects[node["id"]]
        require(node.get("candidate_build_effects") == expected.get("candidate_build_effects"), f"candidate effect corruption: {node['id']}")
        require(node.get("capabilities_under_test") == expected.get("capabilities_under_test"), f"capability-under-test corruption: {node['id']}")

    expected_surfaces = {
        "adapter_registry": ("ADAPTER-INDEX-210", ["src/hive_mind_os/adapter_registry.py"]),
        "dag_executor": ("GENERIC-EXECUTOR-400", ["src/hive_mind_os/dag_executor.py"]),
        "host_runtime": ("WAVE-HOST-300", ["src/hive_mind_os/host_runtime.py"]),
        "integration_transaction": ("WAVE-HOST-300", ["src/hive_mind_os/integration_transaction.py"]),
        "task_reuse": ("TASK-REUSE-310", ["src/hive_mind_os/task_reuse.py"]),
        "token_ledger": ("RUNTIME-TOKEN-320", ["src/hive_mind_os/token_ledger.py"]),
        "shared_runtime_schemas_and_interfaces": (
            "RUNTIME-CONTRACTS-150",
            ["src/hive_mind_os/portable_plan.py", "src/hive_mind_os/runtime_contracts.py", "src/hive_mind_os/wave_manifest.py", "src/hive_mind_os/host_adapter.py", "docs/execution/portable-plan.schema.json", "docs/execution/runtime-contracts.schema.json"],
        ),
    }
    surfaces = ownership.get("single_writer_surfaces")
    require(isinstance(surfaces, dict) and set(surfaces) == set(expected_surfaces), "single-writer surface inventory mismatch")
    for name, (owner, paths) in expected_surfaces.items():
        require(surfaces[name] == {"owner": owner, "paths": paths}, f"single-writer surface corruption: {name}")
        require(all(write_owners.get(path) == owner for path in paths), f"surface owner does not own path: {name}")

    phase = ownership.get("phase_boundaries")
    require(isinstance(phase, dict), "phase boundaries missing")
    require(phase.get("last_node_allowed_to_change_implementation_docs_or_test_source") == "TOKEN-BENCHMARK-620", "implementation freeze boundary mismatch")
    require(phase.get("candidate_ci_exact_tests") == ["FROZEN-HOST-FULL-DOCTOR", "FROZEN-HOST-REPOSITORY-CI"], "candidate CI scope mismatch")
    locations = phase.get("post_freeze_write_locations")
    require(isinstance(locations, dict) and set(locations.values()) == {"external_evidence_worktree"}, "post-freeze evidence worktree boundary missing")
    require(phase.get("protected_merge_permitted") is False, "protected merge enabled")

    source_records = {item.get("source_id"): item for item in intake.get("source_records", []) if isinstance(item, dict)}
    src24 = source_records.get("SRC-024")
    src25 = source_records.get("SRC-025")
    require(isinstance(src24, dict) and src24.get("disposition") == "QUARANTINE" and src24.get("content_accessed") is False and src24.get("design_authority") is False, "SRC-024 quarantine corruption")
    require(isinstance(src25, dict) and src25.get("disposition") == "DEFER_UNRESOLVED_LINEAGE_AND_LICENSE" and src25.get("content_accessed") is False and src25.get("design_authority") is False, "SRC-025 unresolved posture corruption")


def graph_levels(nodes: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
    node_map = {node["id"]: node for node in nodes}
    require(len(node_map) == len(nodes), "duplicate node ids")
    levels: dict[str, int] = {}
    pending = set(node_map)
    while pending:
        ready = sorted(node_id for node_id in pending if all(dep in levels for dep in node_map[node_id]["dependencies"]))
        require(bool(ready), "dependency cycle or unknown dependency")
        for node_id in ready:
            deps = node_map[node_id]["dependencies"]
            require(isinstance(deps, list) and len(deps) == len(set(deps)), f"bad dependencies: {node_id}")
            require(all(dep in node_map and dep != node_id for dep in deps), f"unknown/self dependency: {node_id}")
            levels[node_id] = 0 if not deps else 1 + max(levels[dep] for dep in deps)
        pending.difference_update(ready)
    return levels, 1 + max(levels.values())


def ancestors(node_id: str, node_map: dict[str, dict[str, Any]], *, omit_edge: tuple[str, str] | None = None) -> set[str]:
    seen: set[str] = set()
    stack = list(node_map[node_id]["dependencies"])
    if omit_edge and omit_edge[1] == node_id:
        stack = [item for item in stack if item != omit_edge[0]]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(node_map[current]["dependencies"])
    return seen


def validate_topology_and_durability(nodes: list[dict[str, Any]], intake: dict[str, Any], ownership: dict[str, Any]) -> None:
    node_map = {node["id"]: node for node in nodes}
    edge_count = sum(len(node["dependencies"]) for node in nodes)
    levels, level_count = graph_levels(nodes)
    require(edge_count == 28 and level_count == 17, "topology must be exactly 20/28/17")
    clerk_nodes = intake.get("planned_v3_topology", {}).get("nodes")
    require(isinstance(clerk_nodes, list) and len(clerk_nodes) == 20, "Clerk topology missing")
    for clerk in clerk_nodes:
        node = node_map.get(clerk.get("id"))
        require(node is not None, f"Clerk node missing: {clerk.get('id')}")
        require(node.get("dependencies") == clerk.get("dependencies"), f"dependency mismatch: {node['id']}")
        require(levels[node["id"]] == clerk.get("level"), f"level mismatch: {node['id']}")
        require(node.get("durability_role") == clerk.get("durability_role"), f"durability role mismatch: {node['id']}")
        expected_providers = clerk.get("durability_providers") or []
        observed_providers = node.get("durability_providers") or []
        require(observed_providers == expected_providers, f"durability provider mismatch: {node['id']}")
        if node.get("durability_role") == "consumer":
            require(all(provider in ancestors(node["id"], node_map) for provider in observed_providers), f"non-ancestor durability provider: {node['id']}")
        else:
            require("durability_providers" not in node, f"non-consumer provider list present: {node['id']}")

    redundant: set[tuple[str, str]] = set()
    for dependent, node in node_map.items():
        for dependency in node["dependencies"]:
            if dependency in ancestors(dependent, node_map, omit_edge=(dependency, dependent)):
                redundant.add((dependency, dependent))
    declared = ownership.get("redundant_direct_edges")
    require(isinstance(declared, list) and len(declared) == 6, "six direct edge rationales required")
    declared_pairs = {(item.get("dependency"), item.get("dependent")) for item in declared}
    require(redundant == declared_pairs and len(redundant) == 6, "redundant direct edge set mismatch")
    require(all(isinstance(item.get("rationale"), str) and len(item["rationale"].strip()) >= 40 for item in declared), "direct edge rationale missing")


def verify_frozen_host(contracts: dict[str, Any], repo_root: Path) -> None:
    host = contracts.get("frozen_host_contract")
    require(isinstance(host, dict), "frozen host contract missing")
    require(host.get("extraction_commit") == QUALIFIED_PREREQUISITE_COMMIT, "host extraction commit mismatch")
    require(host.get("extraction_tree") == QUALIFIED_PREREQUISITE_TREE, "host extraction tree mismatch")
    files = host.get("files")
    require(isinstance(files, list) and len(files) == host.get("file_count") == 16, "host manifest must contain 16 files")
    observed_bundle: list[dict[str, str]] = []
    for row in files:
        require(isinstance(row, dict) and set(row) == {"path", "bytes", "sha256", "git_blob"}, "host file row malformed")
        path = row["path"]
        tree_line = git(repo_root, "ls-tree", QUALIFIED_PREREQUISITE_COMMIT, "--", path)
        require(isinstance(tree_line, str) and re.fullmatch(r"100(?:644|755) blob [0-9a-f]{40}\t.+", tree_line) is not None, f"host Git entry missing: {path}")
        blob = tree_line.split()[2]
        require(blob == row["git_blob"], f"host Git blob mismatch: {path}")
        raw = git(repo_root, "cat-file", "blob", blob, binary=True)
        assert isinstance(raw, bytes)
        require(len(raw) == row["bytes"], f"host byte count mismatch: {path}")
        require(sha256_bytes(raw) == row["sha256"], f"host raw digest mismatch: {path}")
        observed_bundle.append({"path": path, "sha256": row["sha256"]})
    require([item["path"] for item in files] == sorted(item["path"] for item in files), "host manifest paths not sorted")
    require(digest(observed_bundle) == host.get("bundle_digest") == EXPECTED_FROZEN_HOST_BUNDLE, "host bundle digest mismatch")
    require(host.get("status") == "REQUIRED_NOT_SATISFIED_BY_CHECKED_IN_EVIDENCE", "host contract falsely claims satisfaction")
    adverse = host.get("adverse_facts")
    require(isinstance(adverse, list) and any("same Windows SID" in item for item in adverse) and any("thirteen ignored" in item for item in adverse) and any("expired" in item for item in adverse), "host adverse facts missing")


def build_expected_plan(
    contracts: dict[str, Any], contracts_raw: bytes,
    traceability: dict[str, Any], traceability_raw: bytes,
    ownership: dict[str, Any], ownership_raw: bytes,
) -> dict[str, Any]:
    all_write_paths = sorted(path for source in contracts["nodes"] for path in source["write_scope"])
    nodes: list[dict[str, Any]] = []
    for source in contracts["nodes"]:
        node = dict(source)
        own_paths = set(node["write_scope"])
        node["downstream_unlock_value"] = node["critical_path_importance"]
        node["file_locks"] = list(node["write_scope"])
        node["forbidden_scope"] = list(contracts["common_forbidden_scope"]) + [path for path in all_write_paths if path not in own_paths]
        node["ownership_contract"] = {"write_path_owner": node["id"], "all_other_write_paths_forbidden": True}
        node["contract_digest"] = digest(node)
        nodes.append(node)

    source_documents = {
        "node_contracts": {"path": "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json", "bytes": len(contracts_raw), "raw_sha256": sha256_bytes(contracts_raw), "canonical_digest": digest(contracts)},
        "traceability": {"path": "docs/execution/dags/generic-hive-mind-product-v3/traceability.json", "bytes": len(traceability_raw), "raw_sha256": sha256_bytes(traceability_raw), "canonical_digest": digest(traceability)},
        "ownership_effects": {"path": "docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json", "bytes": len(ownership_raw), "raw_sha256": sha256_bytes(ownership_raw), "canonical_digest": digest(ownership)},
    }
    generation_material = {
        "schema": "external-plan-generation-v3", "plan_id": PLAN_ID,
        "request_id": REQUEST_ID, "objective_digest": OBJECTIVE_DIGEST,
        "repository_id": REPOSITORY_ID, "task_key": TASK_KEY,
        "launch_digest": LAUNCH_DIGEST, "target_branch": TARGET_BRANCH,
        "authoring_base_parent_commit": PLAN_AUTHORING_BASE_COMMIT,
        "authoring_base_parent_tree": PLAN_AUTHORING_BASE_TREE,
        "source_intake_digest": SOURCE_INTAKE_DIGEST,
        "standard_digest": STANDARD_DIGEST, "compiler_digest": COMPILER_DIGEST,
        "source_document_digests": {key: value["raw_sha256"] for key, value in source_documents.items()},
    }
    generation_id = digest(generation_material)
    resume_material = {
        "schema": "manual-parent-resume-v1", "plan_id": PLAN_ID,
        "generation_id": generation_id, "request_id": REQUEST_ID,
        "objective_digest": OBJECTIVE_DIGEST, "repository_id": REPOSITORY_ID,
        "task_key": TASK_KEY, "launch_digest": LAUNCH_DIGEST,
        "target_branch": TARGET_BRANCH,
        "authoring_base_parent_commit": PLAN_AUTHORING_BASE_COMMIT,
        "authoring_base_parent_tree": PLAN_AUTHORING_BASE_TREE,
    }
    plan: dict[str, Any] = {
        "schema_version": 3,
        "kind": "hive-mind-generic-product-overlay-v3",
        "plan_id": PLAN_ID,
        "title": "Bounded Generic Hive Mind Product Completion V3",
        "request_binding": {
            "request_id": REQUEST_ID, "objective_digest": OBJECTIVE_DIGEST,
            "repository_id": REPOSITORY_ID, "task_key": TASK_KEY,
            "launch_digest": LAUNCH_DIGEST, "target_branch": TARGET_BRANCH,
            "request_observed_head": REQUEST_OBSERVED_HEAD,
            "request_observed_tree": REQUEST_OBSERVED_TREE,
        },
        "repository_binding": {
            "repository": "kb4beast/hive-mind-os",
            "qualified_prerequisite_commit": QUALIFIED_PREREQUISITE_COMMIT,
            "qualified_prerequisite_tree": QUALIFIED_PREREQUISITE_TREE,
            "authoring_base_parent_commit": PLAN_AUTHORING_BASE_COMMIT,
            "authoring_base_parent_tree": PLAN_AUTHORING_BASE_TREE,
            "target_branch": TARGET_BRANCH,
        },
        "standard": {"version": 2, "path": "docs/execution/DAG_AUTHORING_STANDARD_V2.md", "bytes": 12312, "sha256": STANDARD_DIGEST, "git_blob_sha": STANDARD_BLOB},
        "compiler": {"path": ".autopilot/bin/dag_standard.py", "bytes": 104317, "sha256": COMPILER_DIGEST, "git_blob_sha": COMPILER_BLOB, "execution_trust": "external_frozen_host_required"},
        "source_intake": {"path": "docs/execution/dags/generic-hive-mind-product-v3/source-intake.json", "bytes": 58463, "sha256": SOURCE_INTAKE_DIGEST},
        "source_documents": source_documents,
        "generation": {"schema": "external-plan-generation-v3", "generation_id": generation_id, "material": generation_material},
        "resume_identity": {
            "schema": "manual-parent-resume-v1", "resume_id": digest(resume_material),
            "material": resume_material,
            "required_runtime_bindings": ["manifest_expected_plan_digest", "one_run_nonce", "lease_deadline", "frozen_host_bundle_digest", "interpreter_digest", "parent_principal", "round_ledger_digest", "committed_payload_head", "committed_payload_tree", "caller_authenticated_manifest_digest"],
        },
        "execution": {
            "mode": "manual-parent-v1", "external_plan": True,
            "external_plan_path": "docs/execution/dags/generic-hive-mind-product-v3/plan.json",
            "executable_dispatch_command_available": False,
            "round_command_policy": "all_null", "runnable_commands_embedded": False,
            "expected_round_count": 20, "expected_nodes_per_round": 1,
            "legacy_fallback": "PROHIBITED",
            "parent_consumption": "author_verified_not_dispatched_by_this_document",
        },
        "activation_contract": {
            "schema": "host-authenticated-external-plan-activation-v3",
            "checked_in_status": "REQUIRED_NOT_SATISFIED",
            "same_request_fast_path": "exact_request_on_persisted_target_before_new_target_protection_check",
            "signed_bundle_must_contain": ["complete_plan_bytes", "manifest_digest", "expected_plan_digest", "reviewer_identity_and_evidence_digest", "actor_identity", "issuer_identity", "request_id", "repository_id", "objective_digest", "target_branch", "authoring_base_parent_commit", "authoring_base_parent_tree", "committed_payload_head", "committed_payload_tree", "caller_authenticated_manifest_digest", "compiler_digest", "standard_digest", "one_run_nonce", "lease_deadline"],
            "signature_boundary": "host_external_distinct_key",
            "path_reference_sufficient": False, "detached_digest_sufficient": False,
            "repeat_resume": "idempotent_only_for_exact_generation_and_resume_identity",
            "concurrent_activation": "single_winner_compare_and_swap_ledger",
            "strict_rejections": ["duplicate_json_key", "non_finite_number", "oversize_document", "excessive_nesting_depth", "path_swap", "detached_signature_or_digest_substitution", "request_repository_objective_or_generation_collision", "replay_or_expired_lease", "repeat_resume_identity_mismatch", "concurrent_activation_loser"],
            "invalid_v3_legacy_fallback": "PROHIBITED",
        },
        "authority": {
            "execution_status": "DEFER_UNTIL_EXTERNAL_HOST_AND_AUTHORITY_EVIDENCE_SATISFIED",
            "remote_effect_default": "DENY",
            "protected_merge": "ALWAYS_SEPARATE_AUTHORITY_GATE",
            "typed_blockers": ["credentials_or_secret_acquisition", "legal_consent_signature_or_identity_attestation", "spending_or_financial_commitment", "production_mutation_or_deployment", "protected_branch_mutation_or_merge", "missing_or_quarantined_evidence", "unresolved_license_or_lineage", "destructive_or_irreversible_effect_without_explicit_scope", "unbounded_replication_or_authority_expansion"],
            "fresh_host_requirements": ["distinct_signing_principal_or_enforced_outside_repository_deny_sandbox", "exact_ca437095_pristine_bytecode_free_read_only_sixteen_file_git_extraction", "short_lived_one_run_lease_nonce_and_deadline", "unchanged_ca437_derived_host_for_compile_schedule_integration_doctor_and_ci", "exact_interpreter_reviewer_predecessor_and_new_trust_receipts_and_one_run_ledger", "exactly_twenty_manual_parent_rounds_with_all_commands_null"],
            "known_adverse_state": ["stored_controller_capability_is_stale_and_expired", "same_windows_sid_can_read_existing_authority_key", "legacy_continuation_release_publication_was_withheld_after_reconciliation_and_remote_snapshot_change"],
        },
        "source_governance": {"SRC-024": "QUARANTINE_CONTENT_UNREAD_NO_DESIGN_AUTHORITY", "SRC-025": "DEFER_UNRESOLVED_PROVENANCE_LICENSE_AND_LINEAGE"},
        "frozen_host_contract": contracts["frozen_host_contract"],
        "supplemental_execution_path_provenance": {
            "source": "traceability.json#supplemental_execution_path_record",
            "status": traceability["supplemental_execution_path_record"]["status"],
            "bound_clerk_intake_sha256": traceability["supplemental_execution_path_record"]["bound_clerk_intake_sha256"],
            "court_required": True,
        },
        "vision_posture": {
            "A5": "NOT_READY", "active_gate_reference_only_conflict": "UNRESOLVED",
            "maximum_claim": "bounded_generic_candidate_subject_to_independent_court",
            "forbidden_claims": ["full_autonomy", "full_hardened_vision_compliance", "production_readiness", "release_readiness", "deployment_readiness", "protected_merge_readiness", "superiority"],
        },
        "qualification_boundary": {
            "all_implementation_documentation_fixture_and_test_source_complete_before": "QUALIFICATION-PREP-625",
            "candidate_ci_node": "CANDIDATE-CI-627",
            "candidate_ci_exact_checks": ["FROZEN-HOST-FULL-DOCTOR", "FROZEN-HOST-REPOSITORY-CI"],
            "evidence_only_judgment_node": "GENERIC-QUALIFICATION-630",
            "effect_only_handoff_node": "HANDOFF-700",
            "handoff_effect": "authorized_draft_pull_request_only", "merge_permitted": False,
            "candidate_and_evidence_lineage": ownership["phase_boundaries"]["candidate_and_evidence_lineage"],
            "post_freeze_write_locations": ownership["phase_boundaries"]["post_freeze_write_locations"],
        },
        "historical_v1": {"status": "provenance_only_no_execution_fallback", "expected_plan_digest": V1_EXPECTED_PLAN_DIGEST, "node_count": 16, "traceability_rows": 89},
        "topology_contract": {"node_count": 20, "raw_edge_count": 28, "level_count": 17, "redundant_direct_edge_count": 6},
        "ownership_contract": {"unique_write_path_count": 85, "all_other_node_write_paths_forbidden": True, "single_writer_surface_count": 7},
        "nodes": nodes,
    }
    plan["plan_digest"] = digest(plan)
    return plan


def verify_node_and_plan_seals(plan: dict[str, Any]) -> None:
    nodes = plan.get("nodes")
    require(isinstance(nodes, list) and len(nodes) == 20, "plan nodes missing")
    for node in nodes:
        require(isinstance(node, dict), "plan node malformed")
        expected = node.get("contract_digest")
        material = dict(node)
        material.pop("contract_digest", None)
        require(expected == digest(material), f"node seal mismatch: {node.get('id')}")
    material = dict(plan)
    expected_plan = material.pop("plan_digest", None)
    require(expected_plan == digest(material) == EXPECTED_PLAN_DIGEST, "plan seal mismatch")


def verify_ownership_expansion(plan: dict[str, Any], contracts: dict[str, Any]) -> None:
    common = contracts["common_forbidden_scope"]
    all_paths = sorted(path for node in contracts["nodes"] for path in node["write_scope"])
    source_by_id = {node["id"]: node for node in contracts["nodes"]}
    for node in plan["nodes"]:
        source = source_by_id[node["id"]]
        own = set(source["write_scope"])
        require(node["write_scope"] == source["write_scope"], f"write scope materialization mismatch: {node['id']}")
        require(node["file_locks"] == source["write_scope"], f"file lock mismatch: {node['id']}")
        require(node["forbidden_scope"] == common + [path for path in all_paths if path not in own], f"forbidden scope mismatch: {node['id']}")
        require(not own.intersection(node["forbidden_scope"]), f"owner forbids own path: {node['id']}")


def verify_no_runnable_commands(value: Any, *, label: str = "external plan") -> None:
    pending = [value]
    shell_prefix = re.compile(r"^(?:python|powershell|pwsh|bash|sh|cmd)(?:\s|$)", re.IGNORECASE)
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if key == "command":
                    require(item is None, f"runnable command embedded in {label}")
                pending.append(item)
        elif isinstance(current, list):
            pending.extend(current)
    for node in value.get("nodes", []):
        require(all(isinstance(item, str) and not shell_prefix.search(item) for item in node.get("required_tests", [])), f"shell command embedded in required_tests: {node.get('id')}")


def _verify_configured(
    *,
    expected_manifest_digest: str,
    overlay_dir: Path = HERE,
    repo_root: Path = DEFAULT_REPO_ROOT,
    authoring_check: bool = False,
) -> dict[str, Any]:
    overlay_dir = overlay_dir.resolve()
    repo_root = repo_root.resolve()
    sealed_plan_path = safe_child(repo_root, ".autopilot/plan.json", label="historical sealed plan")
    sealed_before = read_bounded_bytes(
        sealed_plan_path,
        label="historical sealed plan before verification",
        size_limit=MAX_PLAN_BYTES,
    )

    # Trust order is intentional: parse only the manifest, validate its fixed
    # identity, then verify every declared source byte before interpreting any
    # authored materializer or authored JSON data.
    require(
        isinstance(expected_manifest_digest, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", expected_manifest_digest) is not None,
        "caller must supply a canonical expected manifest SHA-256",
    )
    manifest_path = safe_child(overlay_dir, "manifest.json", label="manifest")
    try:
        manifest_raw = read_bounded_bytes(
            manifest_path,
            label="manifest.json",
            size_limit=MAX_MANIFEST_BYTES,
        )
    except OSError as error:
        raise VerificationError(f"cannot read manifest.json: {error}") from error
    require(len(manifest_raw) <= MAX_MANIFEST_BYTES, f"manifest.json exceeds size limit {MAX_MANIFEST_BYTES}")
    require(
        sha256_bytes(manifest_raw) == expected_manifest_digest,
        "caller-authenticated manifest digest mismatch",
    )
    manifest = parse_strict_json(
        manifest_raw,
        label="manifest.json",
        size_limit=MAX_MANIFEST_BYTES,
    )
    validate_manifest_constants(manifest)
    repository_state = verify_repository_state(
        repo_root, overlay_dir, authoring_check=authoring_check
    )
    verify_payload_bindings(
        manifest,
        repo_root=repo_root,
        overlay_dir=overlay_dir,
        manifest_raw=manifest_raw,
    )
    verified_sources = verify_manifest_declared_sources(
        manifest, overlay_dir=overlay_dir, repo_root=repo_root
    )

    intake = parse_strict_json(
        verified_sources["repository:docs/execution/dags/generic-hive-mind-product-v3/source-intake.json"],
        label="source-intake.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    contracts = parse_strict_json(
        verified_sources["overlay:node-contracts.json"],
        label="node-contracts.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    traceability = parse_strict_json(
        verified_sources["overlay:traceability.json"],
        label="traceability.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    ownership = parse_strict_json(
        verified_sources["overlay:ownership-effects.json"],
        label="ownership-effects.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    validate_inert_sources(contracts, traceability, ownership, intake)
    verify_frozen_host(contracts, repo_root)

    expected = build_expected_plan(
        contracts,
        verified_sources["overlay:node-contracts.json"],
        traceability,
        verified_sources["overlay:traceability.json"],
        ownership,
        verified_sources["overlay:ownership-effects.json"],
    )
    plan_path = safe_child(overlay_dir, "plan.json", label="external plan")
    plan, plan_raw = read_strict_json(plan_path, label="plan.json", size_limit=MAX_PLAN_BYTES)
    require(sha256_bytes(plan_raw) == EXPECTED_PLAN_RAW_DIGEST, "external plan raw bytes mismatch")
    require(plan == expected, "external plan differs from independent reconstruction")
    verify_node_and_plan_seals(plan)
    validate_topology_and_durability(plan["nodes"], intake, ownership)
    verify_ownership_expansion(plan, contracts)
    verify_no_runnable_commands(plan)
    require(plan["execution"]["mode"] == "manual-parent-v1", "external plan execution mode mismatch")
    require(plan["execution"]["executable_dispatch_command_available"] is False, "external plan claims runnable dispatch")
    require(plan["execution"]["expected_round_count"] == 20, "external plan round count contract mismatch")
    require(plan["execution"]["legacy_fallback"] == "PROHIBITED", "external plan permits legacy fallback")
    require(plan["activation_contract"]["checked_in_status"] == "REQUIRED_NOT_SATISFIED", "activation falsely satisfied")
    require(plan["authority"]["execution_status"].startswith("DEFER_"), "authority posture is not fail-closed")
    require(plan["vision_posture"]["A5"] == "NOT_READY", "A5 readiness overclaim")

    sealed_after = read_bounded_bytes(
        sealed_plan_path,
        label="historical sealed plan after verification",
        size_limit=MAX_PLAN_BYTES,
    )
    require(sealed_after == sealed_before, "verifier mutated .autopilot/plan.json")
    require(sha256_bytes(sealed_after) == EXPECTED_REPOSITORY_SOURCES[".autopilot/plan.json"][1], "historical sealed plan changed")
    verify_repository_state_stable_at_end(repo_root, overlay_dir, repository_state)
    verify_git_executable_stable(full_digest=True)
    return {
        "verified": True,
        "plan_id": PLAN_ID,
        "manifest_raw_sha256": sha256_bytes(manifest_raw),
        "verification_mode": repository_state["mode"],
        "committed_payload_qualification": repository_state["qualification"],
        "execution_qualification": False,
        "committed_payload": {
            "head": repository_state["head"],
            "tree": repository_state["tree"],
            "authoring_base_parent": repository_state["authoring_base_parent"],
            "correction_parent": repository_state["correction_parent"],
        },
        "plan_digest": EXPECTED_PLAN_DIGEST,
        "plan_raw_sha256": EXPECTED_PLAN_RAW_DIGEST,
        "integrity": "verified-sealed",
        "durability_semantics": "typed-v2",
        "topology": {"nodes": 20, "raw_edges": 28, "levels": 17, "rounds": 20},
        "traceability": {"v1_rows": 89, "v3_corners": len(traceability["v3_specific_corners"])},
        "ownership": {"unique_write_paths": 85, "single_writer_surfaces": 7},
        "execution": {
            "mode": "manual-parent-v1",
            "executable_dispatch_command_available": False,
            "every_round_command": None,
            "legacy_fallback": "PROHIBITED",
            "authorized": False,
        },
        "frozen_host": {
            "required_commit": QUALIFIED_PREREQUISITE_COMMIT,
            "file_count": 16,
            "bundle_digest": EXPECTED_FROZEN_HOST_BUNDLE,
            "external_activation_status": "NOT_SATISFIED_BY_CHECKED_IN_EVIDENCE",
            "anti_downgrade_policy_status": "REQUIRED_NOT_SATISFIED_BY_CHECKED_IN_EVIDENCE",
        },
        "materializer_imported_or_executed": False,
        "historical_plan_unchanged": True,
        "git_boundary": {
            "executable": str(_GIT_BOUNDARY["executable"]),
            "executable_sha256": _GIT_BOUNDARY["expected_sha256"],
            "path_lookup": False,
            "inherited_git_environment": "REJECTED",
            "system_and_global_config": "DISABLED",
            "git_dir": str(_GIT_BOUNDARY["git_dir"]),
            "common_dir": str(_GIT_BOUNDARY["common_dir"]),
            "index_path": str(_GIT_BOUNDARY["index_path"]),
            "work_tree": str(_GIT_BOUNDARY["work_tree"]),
            "tracked_path_count": (
                repository_state["checkout_snapshot"]["tracked_path_count"]
                if repository_state["qualification"]
                else None
            ),
        },
    }


def verify(
    *,
    expected_manifest_digest: str,
    git_executable: Path,
    expected_git_executable_sha256: str,
    overlay_dir: Path = HERE,
    repo_root: Path = DEFAULT_REPO_ROOT,
    authoring_check: bool = False,
) -> dict[str, Any]:
    global _GIT_BOUNDARY
    overlay_dir = overlay_dir.resolve()
    repo_root = repo_root.resolve()
    configure_git_boundary(
        repo_root,
        git_executable=git_executable,
        expected_git_executable_sha256=expected_git_executable_sha256,
    )
    try:
        return _verify_configured(
            expected_manifest_digest=expected_manifest_digest,
            overlay_dir=overlay_dir,
            repo_root=repo_root,
            authoring_check=authoring_check,
        )
    finally:
        boundary = _GIT_BOUNDARY
        _GIT_BOUNDARY = None
        if boundary is not None:
            try:
                boundary["handle"].close()
            except OSError as error:
                raise VerificationError(f"cannot close retained Git executable handle: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay-dir", type=Path, default=HERE)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--expected-manifest-digest", required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--expected-git-executable-sha256", required=True)
    parser.add_argument(
        "--authoring-check",
        action="store_true",
        help="Non-executing precommit development check; never execution qualification.",
    )
    args = parser.parse_args(argv)
    result = verify(
        expected_manifest_digest=args.expected_manifest_digest,
        git_executable=args.git_executable,
        expected_git_executable_sha256=args.expected_git_executable_sha256,
        overlay_dir=args.overlay_dir,
        repo_root=args.repo_root,
        authoring_check=args.authoring_check,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(json.dumps({"verified": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
