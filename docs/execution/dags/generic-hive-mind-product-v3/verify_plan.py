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
import fnmatch
import hashlib
import json
import math
import os
import re
import stat
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parents[3] if len(HERE.parents) > 3 else HERE

MAX_MANIFEST_BYTES = 262_144
MAX_SOURCE_JSON_BYTES = 1_000_000
MAX_PLAN_BYTES = 2_000_000
MAX_JSON_DEPTH = 48
MAX_GIT_OUTPUT_BYTES = 16_777_216
GIT_TIMEOUT_SECONDS = 60
GIT_KILL_REAP_TIMEOUT_SECONDS = 5
GIT_READER_JOIN_TIMEOUT_SECONDS = 5
MAX_TRACKED_FILE_BYTES = 2_097_152
MAX_GIT_POINTER_BYTES = 4_096
MAX_GIT_INDEX_BYTES = 16_777_216
MAX_NATIVE_EXECUTABLE_BYTES = 268_435_456
MAX_NATIVE_IMAGE_TABLE_BYTES = 16_777_216
MAX_AUTOPILOT_TREE_ENTRIES = 4_096
MAX_AUTOPILOT_TREE_DEPTH = 64
MAX_AUTOPILOT_FILE_BYTES = 4_194_304
MAX_AUTOPILOT_TOTAL_BYTES = 67_108_864
MAX_AUTOPILOT_PATH_BYTES = 4_096
MAX_AUTOPILOT_WINDOWS_STREAMS_PER_ENTRY = 64
MAX_GITATTRIBUTES_BYTES = 65_536
MAX_GITATTRIBUTE_RULES = 512
MAX_GITATTRIBUTE_PATTERN_BYTES = 4_096
MAX_GITATTRIBUTE_PATTERN_PARTS = 64

NATIVE_EXECUTABLE_FORMAT_POLICY = "host-native-image-format-v1"
GIT_EXECUTION_BOUNDARY_POLICY = "caller-absolute-raw-sha256-host-native-image-windows-birthtime-v3"
SUPPORTED_NATIVE_IMAGE_FORMATS = {
    "win32": "PE_COFF_EXECUTABLE_IMAGE",
    "linux": "ELF_EXEC_OR_PIE_WITH_EXECUTABLE_LOAD_SEGMENT",
    "darwin": "MACH_O_EXECUTE_THIN_OR_HOST_SLICE_UNIVERSAL",
}

GitExecutableIdentity = tuple[int, int, int, int, int, int | None]
GitExecutableContinuityKey = tuple[int, int, int, int, int]

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
GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT = "f06e52c43a1e2d1d53523378c0d6f5564fb984bf"
GIT_ENVIRONMENT_CORRECTION_PARENT_TREE = "8730203c89835c4d1d9dac4be9b2086dacd2d869"
GIT_ENVIRONMENT_CORRECTION_PARENT_MANIFEST_RAW_DIGEST = "sha256:b3ea9cbc2766cc1fa72a41f097de491a8b0ae5b9b482c57667bd31c1393fa339"
GIT_ENVIRONMENT_CORRECTION_PARENT_AGGREGATE_DIGEST = "sha256:229821586021d8e2769035aeca4a4589cb7b458a9740a8b8ca82ebdfdadaee36"
GIT_ENVIRONMENT_CORRECTION_PARENT_REPORT_DIGEST = "sha256:731beb68c2fed2c1a3d8666530c1f193b2e21144428448816216b4f9b0bba810"
GIT_BOUNDARY_CORRECTION_COMMIT = "9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8"
GIT_BOUNDARY_CORRECTION_TREE = "0d0a251b6ff1557ca014b6b50c6f62ae787c4459"
GIT_BOUNDARY_CORRECTION_MANIFEST_RAW_DIGEST = "sha256:87b9fa29dbcd0577328eb1298413994433c43a150f0f9c3b1ca2f498e0929f9e"
GIT_BOUNDARY_CORRECTION_AGGREGATE_DIGEST = "sha256:5eb7aee3582095465a7e1a030d360ca205048ae0e8abaceab6f63f212df88477"
GIT_BOUNDARY_CORRECTION_REPORT_DIGEST = "sha256:a4714e5d3f6ec01d77fed4e722a7f781ea7e83a2300001ebc3ed70463af693ff"
CORRECTION_PARENT_COMMIT = "28463ae6dd842b0b316fcf99eab98804cdaf9735"
CORRECTION_PARENT_TREE = "72696b27cdd2c9cd08085c05c98513ece733cc8d"
CORRECTION_PARENT_PARENT_COMMIT = "9dfa1823edc9cd56cd1f404606a261a1d623f6cb"
CORRECTION_PARENT_PARENT_TREE = "7e8becaebef2ca88922c9099ae1e497f978f43f1"
CORRECTION_PARENT_MANIFEST_RAW_DIGEST = "sha256:c2f0ae0dcee177213f219eaa3031b45d6f5526fd1f2d98d73b11672068f81377"
CORRECTION_PARENT_AGGREGATE_DIGEST = "sha256:ecbeb374fc8adbb711391568d8a2f2fa8b0ef022c233ca932f24bd9ab0b4fb23"
CORRECTION_PARENT_REPORT_DIGEST = "sha256:1ac71b791a36f5c2e543039d89604123a9b8f744e022bab23f549d481e472944"
SOURCE_INTAKE_DIGEST = "sha256:dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c"
STANDARD_DIGEST = "sha256:3b072fee295e75b8c28709d417f9036fa384e31dc53ca85526babd0881d0e90a"
STANDARD_BLOB = "2bc9c0fa3baf6fb5cc720ffdbf7528e93f4e7374"
COMPILER_DIGEST = "sha256:105674faf15aaf7b9f4c9db7ad4003fda404438eed2bf8cc3a1782c1cf321e6a"
COMPILER_BLOB = "f170ac4f388d265fcaafd32437e449945dcebee3"
V1_EXPECTED_PLAN_DIGEST = "sha256:b8879d09c5a42b0feeeec19b9c8f6a7523e4ef69b117eea1a18ef6dfaf35f977"
EXPECTED_PLAN_DIGEST = "sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1"
EXPECTED_PLAN_RAW_DIGEST = "sha256:5e03c7638b2d4865dda2b2c3a5e615ea4b2b8d37f61a3a5fdfbf29c1750827c4"
EXPECTED_FROZEN_HOST_BUNDLE = "sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255"
FROZEN_HOST_MANIFEST_LOCATION = "node-contracts.json#/frozen_host_contract/files"

EXPECTED_OVERLAY_SOURCES = {
    "node-contracts.json": (64381, "sha256:eef8694c935467bade1fed286ef9cce67f01e2f35f0b914105255bf8681e3cf8"),
    "traceability.json": (24865, "sha256:4182ab1d43deaabe41b50e8c534d2f6de33d399696cb69611391858f17eaa786"),
    "ownership-effects.json": (10943, "sha256:056b74b37da1e7292d7931b93c5975c2c589ce4b64c8bf0004ca12f5deebaf80"),
    "materialize_plan.py": (25309, "sha256:63c2dd154fc1a6e4db9e9ca5ca7e06d57ef93f141a921ff3189fa77b4b48464c"),
}

EXPECTED_PAYLOAD_PATHS = (
    ".gitattributes",
    ".github/workflows/ci.yml",
    "docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md",
    "docs/architecture/ADR-070-GENERIC-V3-BASELINE-RECOVERY.md",
    "docs/architecture/ADR-071-PORTABLE-DAG-RUNTIME-AND-EXTERNAL-ACTIVATION.md",
    "docs/architecture/ADR_INDEX.md",
    "docs/execution/dags/generic-hive-mind-product-v3/README.md",
    "docs/execution/dags/generic-hive-mind-product-v3/manifest.json",
    "docs/execution/dags/generic-hive-mind-product-v3/materialize_plan.py",
    "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json",
    "docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json",
    "docs/execution/dags/generic-hive-mind-product-v3/plan.json",
    "docs/execution/dags/generic-hive-mind-product-v3/traceability.json",
    "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py",
    "tests/fixtures/generic-v3-history.bundle",
    "tests/fixtures/generic-v3-history.provenance.json",
    "tests/test_generic_dag_v3_overlay.py",
)
EXPECTED_CHANGED_PATHS = (
    ".gitattributes",
    ".github/workflows/ci.yml",
    "docs/architecture/ADR-070-GENERIC-V3-BASELINE-RECOVERY.md",
    "docs/architecture/ADR-071-PORTABLE-DAG-RUNTIME-AND-EXTERNAL-ACTIVATION.md",
    "docs/architecture/ADR_INDEX.md",
    "docs/execution/dags/generic-hive-mind-product-v3/README.md",
    "docs/execution/dags/generic-hive-mind-product-v3/manifest.json",
    "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py",
    "tests/fixtures/generic-v3-history.bundle",
    "tests/fixtures/generic-v3-history.provenance.json",
    "tests/test_generic_dag_v3_overlay.py",
)
EXPECTED_ADDED_PATHS = (
    "docs/architecture/ADR-070-GENERIC-V3-BASELINE-RECOVERY.md",
    "docs/architecture/ADR-071-PORTABLE-DAG-RUNTIME-AND-EXTERNAL-ACTIVATION.md",
    "tests/fixtures/generic-v3-history.bundle",
    "tests/fixtures/generic-v3-history.provenance.json",
)
MANIFEST_RELATIVE_PATH = "docs/execution/dags/generic-hive-mind-product-v3/manifest.json"
OVERLAY_RELATIVE_DIRECTORY = "docs/execution/dags/generic-hive-mind-product-v3"
ALLOWED_UNTRACKED_PATH = ".hive-mind/autopilot-request.json"

REQUIRED_TEXT_GITATTRIBUTE_RULES = {
    ".gitattributes": ("text", "eol=lf"),
    "LICENSE": ("text", "eol=lf"),
    "*.ps1": ("text", "eol=lf"),
}
REQUIRED_RAW_EVIDENCE_GITATTRIBUTE_RULES = {
    "evidence/sources/**/raw/**": ("-text", "-diff"),
    "evidence/live/**": ("-text", "-diff"),
    "evidence/benchmarks/**": ("-text", "-diff"),
    "evidence/experiments/_artifacts/**": ("-text", "-diff"),
    "evidence/experiments/_failed/**": ("-text", "-diff"),
    "evidence/local_assurance/**/logs/**": ("-text", "-diff"),
    "tests/fixtures/*.bundle": ("-text", "-diff"),
}
EXPECTED_GITATTRIBUTE_RULES = (
    (".gitattributes", ("text", "eol=lf")),
    ("LICENSE", ("text", "eol=lf")),
    ("*.py", ("text", "eol=lf")),
    ("*.json", ("text", "eol=lf")),
    ("*.md", ("text", "eol=lf")),
    ("*.ps1", ("text", "eol=lf")),
    ("*.toml", ("text", "eol=lf")),
    ("*.yml", ("text", "eol=lf")),
    ("*.yaml", ("text", "eol=lf")),
    *tuple(REQUIRED_RAW_EVIDENCE_GITATTRIBUTE_RULES.items()),
)

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
    """A declared trust or data invariant did not verify."""

    code = "VERIFICATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        primary_code: str | None = None,
        cleanup_evidence: Iterable[BaseException] = (),
    ) -> None:
        super().__init__(message)
        self.primary_code = primary_code or self.code
        self.cleanup_evidence: list[dict[str, str]] = []
        for error in cleanup_evidence:
            self.add_cleanup_evidence(error)

    def add_cleanup_evidence(self, error: BaseException) -> None:
        self.cleanup_evidence.append(
            {
                "code": str(getattr(error, "code", "VERIFICATION_CLEANUP_ERROR")),
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )

    def __str__(self) -> str:
        message = super().__str__()
        if not self.cleanup_evidence:
            return message
        rendered = json.dumps(
            self.cleanup_evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"{message}; cleanup_evidence={rendered}"


class GitOutputOverflowError(VerificationError):
    code = "GIT_OUTPUT_OVERFLOW"


class GitTimeoutError(VerificationError):
    code = "GIT_TIMEOUT"


class GitTimeoutAfterKillError(VerificationError):
    code = "GIT_TIMEOUT_AFTER_KILL"


class GitNonUtf8Error(VerificationError):
    code = "GIT_NON_UTF8"


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


def _optional_stat_integer(state: os.stat_result, name: str) -> int | None:
    value = getattr(state, name, None)
    return None if value is None else int(value)


def _filesystem_snapshot_state(state: os.stat_result) -> tuple[int | None, ...]:
    birthtime_ns = _optional_stat_integer(state, "st_birthtime_ns")
    if birthtime_ns is None:
        birthtime = getattr(state, "st_birthtime", None)
        if birthtime is not None:
            birthtime_ns = int(float(birthtime) * 1_000_000_000)
    return (
        state.st_dev,
        state.st_ino,
        state.st_mode,
        state.st_nlink,
        state.st_uid,
        state.st_gid,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
        _optional_stat_integer(state, "st_file_attributes"),
        _optional_stat_integer(state, "st_reparse_tag"),
        birthtime_ns,
        _optional_stat_integer(state, "st_flags"),
        _optional_stat_integer(state, "st_gen"),
    )


def _filesystem_path_open_identity(state: os.stat_result) -> tuple[int | None, ...]:
    # Windows path-stat and handle-fstat expose different ctime semantics in
    # current Python runtimes.  Preserve each ctime in its own before/after
    # observation, but exclude only ctime from the path-versus-open comparison.
    # Slicing the complete state keeps every stable optional field bound too.
    complete_state = _filesystem_snapshot_state(state)
    return complete_state[:8] + complete_state[9:]


class _WIN32_FIND_STREAM_DATA(ctypes.Structure):
    _fields_ = [
        ("StreamSize", ctypes.c_longlong),
        ("cStreamName", ctypes.c_wchar * (260 + 36)),
    ]


_WINDOWS_STREAM_API: tuple[Any, Any, Any] | None = None


def _windows_stream_api() -> tuple[Any, Any, Any]:
    global _WINDOWS_STREAM_API
    if _WINDOWS_STREAM_API is not None:
        return _WINDOWS_STREAM_API
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        find_first = kernel32.FindFirstStreamW
        find_first.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.POINTER(_WIN32_FIND_STREAM_DATA),
            ctypes.c_uint32,
        ]
        find_first.restype = ctypes.c_void_p
        find_next = kernel32.FindNextStreamW
        find_next.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WIN32_FIND_STREAM_DATA),
        ]
        find_next.restype = ctypes.c_int
        find_close = kernel32.FindClose
        find_close.argtypes = [ctypes.c_void_p]
        find_close.restype = ctypes.c_int
    except Exception as error:
        raise VerificationError(
            f"cannot initialize bounded Windows stream enumeration: {error}"
        ) from error
    _WINDOWS_STREAM_API = (find_first, find_next, find_close)
    return _WINDOWS_STREAM_API


def _windows_stream_error(*, label: str, operation: str, error_code: int) -> VerificationError:
    try:
        detail = ctypes.WinError(error_code)
    except Exception:
        detail = OSError(error_code, "unknown Windows stream enumeration error")
    return VerificationError(
        f"cannot {operation} Windows streams for .autopilot {label}: {detail}"
    )


def _windows_stream_snapshot(path: Path, *, label: str) -> tuple[tuple[str, int], ...]:
    """Return the unnamed NTFS data stream and reject every named stream."""

    if os.name != "nt":
        return ()
    find_first, find_next, find_close = _windows_stream_api()
    stream_data = _WIN32_FIND_STREAM_DATA()
    invalid_handle = ctypes.c_void_p(-1).value
    try:
        ctypes.set_last_error(0)
        handle = find_first(str(path), 0, ctypes.byref(stream_data), 0)
    except Exception as error:
        raise VerificationError(
            f"cannot begin Windows stream enumeration for .autopilot {label}: {error}"
        ) from error
    if handle == invalid_handle:
        error_code = ctypes.get_last_error()
        if error_code == 38:  # ERROR_HANDLE_EOF: the entry has no streams.
            return ()
        raise _windows_stream_error(
            label=label,
            operation="begin enumerating",
            error_code=error_code,
        )
    if handle in (None, 0):
        raise VerificationError(
            f"Windows stream enumeration returned an invalid handle for .autopilot {label}"
        )

    streams: list[tuple[str, int]] = []
    primary_error: VerificationError | None = None
    try:
        while True:
            require(
                len(streams) < MAX_AUTOPILOT_WINDOWS_STREAMS_PER_ENTRY,
                f"Windows stream inventory exceeds the limit for .autopilot {label}",
            )
            stream_name = str(stream_data.cStreamName)
            stream_size = int(stream_data.StreamSize)
            require(
                stream_name != "" and len(stream_name) < 260 + 36,
                f"malformed Windows stream name for .autopilot {label}",
            )
            require(
                stream_size >= 0,
                f"negative Windows stream size for .autopilot {label}",
            )
            require(
                stream_name == "::$DATA",
                f"named Windows data stream is forbidden for .autopilot {label}: {stream_name}",
            )
            require(
                not streams,
                f"duplicate unnamed Windows data stream for .autopilot {label}",
            )
            streams.append((stream_name, stream_size))

            try:
                ctypes.set_last_error(0)
                has_next = bool(find_next(handle, ctypes.byref(stream_data)))
            except Exception as error:
                raise VerificationError(
                    f"cannot continue Windows stream enumeration for .autopilot {label}: {error}"
                ) from error
            if has_next:
                continue
            error_code = ctypes.get_last_error()
            if error_code == 38:  # ERROR_HANDLE_EOF: successful enumeration end.
                break
            raise _windows_stream_error(
                label=label,
                operation="continue enumerating",
                error_code=error_code,
            )
    except VerificationError as error:
        primary_error = error
    finally:
        close_error: VerificationError | None = None
        try:
            ctypes.set_last_error(0)
            closed = bool(find_close(handle))
        except Exception as error:
            close_error = VerificationError(
                f"cannot close Windows stream enumeration for .autopilot {label}: {error}"
            )
        else:
            if not closed:
                close_error = _windows_stream_error(
                    label=label,
                    operation="close the enumeration of",
                    error_code=ctypes.get_last_error(),
                )
        if close_error is not None:
            if primary_error is not None:
                primary_error.add_cleanup_evidence(close_error)
            else:
                primary_error = close_error
    if primary_error is not None:
        raise primary_error
    return tuple(streams)


def snapshot_autopilot_tree(repo_root: Path) -> dict[str, Any]:
    """Record bounded point observations across the complete ``.autopilot`` tree."""

    root = repo_root / ".autopilot"
    try:
        root_state = os.lstat(root)
    except OSError as error:
        raise VerificationError(f"cannot inspect .autopilot root: {error}") from error
    require(stat.S_ISDIR(root_state.st_mode), ".autopilot root must be a directory")
    require(
        not stat.S_ISLNK(root_state.st_mode)
        and not getattr(root_state, "st_reparse_tag", 0),
        ".autopilot root cannot be a symlink or reparse point",
    )

    rows: list[tuple[Any, ...]] = []
    total_bytes = 0

    def add_row(row: tuple[Any, ...]) -> None:
        require(
            len(rows) < MAX_AUTOPILOT_TREE_ENTRIES,
            ".autopilot tree exceeds the entry limit",
        )
        rows.append(row)

    def visit_directory(directory: Path, relative: str, depth: int) -> None:
        nonlocal total_bytes
        require(depth <= MAX_AUTOPILOT_TREE_DEPTH, ".autopilot tree exceeds the depth limit")
        try:
            before_directory = os.lstat(directory)
        except OSError as error:
            raise VerificationError(f"cannot inspect .autopilot directory {relative}: {error}") from error
        require(stat.S_ISDIR(before_directory.st_mode), f".autopilot directory changed type: {relative}")
        require(
            not stat.S_ISLNK(before_directory.st_mode)
            and not getattr(before_directory, "st_reparse_tag", 0),
            f".autopilot directory cannot be a symlink or reparse point: {relative}",
        )
        before_state = _filesystem_snapshot_state(before_directory)
        before_streams = _windows_stream_snapshot(
            directory,
            label=f"directory {relative}",
        )
        try:
            after_before_stream_directory = os.lstat(directory)
        except OSError as error:
            raise VerificationError(
                f"cannot re-inspect .autopilot directory after initial stream enumeration {relative}: {error}"
            ) from error
        require(
            _filesystem_snapshot_state(after_before_stream_directory) == before_state,
            f".autopilot directory changed during initial stream enumeration: {relative}",
        )
        require(
            before_streams == (),
            f".autopilot directory cannot expose an unnamed Windows data stream: {relative}",
        )
        add_row((relative, "directory", before_state, before_streams))
        entries: list[os.DirEntry[str]] = []
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    require(
                        len(rows) + len(entries) < MAX_AUTOPILOT_TREE_ENTRIES,
                        ".autopilot tree exceeds the entry limit",
                    )
                    entries.append(entry)
        except OSError as error:
            raise VerificationError(f"cannot enumerate .autopilot directory {relative}: {error}") from error
        for entry in sorted(entries, key=lambda item: item.name):
            require(
                entry.name not in {"", ".", ".."}
                and "/" not in entry.name
                and "\\" not in entry.name
                and "\0" not in entry.name,
                f"malformed .autopilot entry name under {relative}",
            )
            child_relative = entry.name if relative == "." else f"{relative}/{entry.name}"
            require(
                len(os.fsencode(child_relative)) <= MAX_AUTOPILOT_PATH_BYTES,
                ".autopilot relative path exceeds the byte limit",
            )
            child = directory / entry.name
            try:
                before_child = os.lstat(child)
            except OSError as error:
                raise VerificationError(f"cannot inspect .autopilot entry {child_relative}: {error}") from error
            require(
                not stat.S_ISLNK(before_child.st_mode)
                and not getattr(before_child, "st_reparse_tag", 0),
                f".autopilot symlinks and reparse points are forbidden: {child_relative}",
            )
            if stat.S_ISDIR(before_child.st_mode):
                visit_directory(child, child_relative, depth + 1)
                continue
            require(
                stat.S_ISREG(before_child.st_mode),
                f"unsupported .autopilot filesystem object: {child_relative}",
            )
            require(
                0 <= before_child.st_size <= MAX_AUTOPILOT_FILE_BYTES,
                f".autopilot file exceeds the per-file limit: {child_relative}",
            )
            before_child_state = _filesystem_snapshot_state(before_child)
            before_child_streams = _windows_stream_snapshot(
                child,
                label=f"file {child_relative}",
            )
            try:
                after_before_child_stream = os.lstat(child)
            except OSError as error:
                raise VerificationError(
                    f"cannot re-inspect .autopilot file after initial stream enumeration {child_relative}: {error}"
                ) from error
            require(
                _filesystem_snapshot_state(after_before_child_stream)
                == before_child_state,
                f".autopilot file changed during initial stream enumeration: {child_relative}",
            )
            if os.name == "nt":
                require(
                    before_child_streams == (("::$DATA", before_child.st_size),),
                    f".autopilot file has an inconsistent unnamed Windows data stream: {child_relative}",
                )
            try:
                with child.open("rb") as handle:
                    open_before = os.fstat(handle.fileno())
                    require(
                        _filesystem_path_open_identity(open_before)
                        == _filesystem_path_open_identity(before_child),
                        f".autopilot path/open-file identity mismatch: {child_relative}",
                    )
                    raw = handle.read(MAX_AUTOPILOT_FILE_BYTES + 1)
                    open_after = os.fstat(handle.fileno())
            except OSError as error:
                raise VerificationError(f"cannot read .autopilot file {child_relative}: {error}") from error
            require(
                _filesystem_snapshot_state(open_after)
                == _filesystem_snapshot_state(open_before),
                f".autopilot open file changed while reading: {child_relative}",
            )
            require(
                len(raw) == before_child.st_size,
                f".autopilot file read length mismatch: {child_relative}",
            )
            try:
                after_child = os.lstat(child)
            except OSError as error:
                raise VerificationError(f"cannot re-inspect .autopilot file {child_relative}: {error}") from error
            require(
                _filesystem_snapshot_state(after_child) == before_child_state,
                f".autopilot path changed while reading: {child_relative}",
            )
            after_child_streams = _windows_stream_snapshot(
                child,
                label=f"file {child_relative}",
            )
            try:
                after_final_child_stream = os.lstat(child)
            except OSError as error:
                raise VerificationError(
                    f"cannot re-inspect .autopilot file after final stream enumeration {child_relative}: {error}"
                ) from error
            require(
                _filesystem_snapshot_state(after_final_child_stream)
                == before_child_state,
                f".autopilot file changed during final stream enumeration: {child_relative}",
            )
            require(
                after_child_streams == before_child_streams,
                f".autopilot Windows stream inventory changed while reading: {child_relative}",
            )
            total_bytes += len(raw)
            require(total_bytes <= MAX_AUTOPILOT_TOTAL_BYTES, ".autopilot tree exceeds the total-byte limit")
            add_row(
                (
                    child_relative,
                    "file",
                    before_child_state,
                    before_child_streams,
                    sha256_bytes(raw),
                )
            )
        try:
            after_directory = os.lstat(directory)
        except OSError as error:
            raise VerificationError(f"cannot re-inspect .autopilot directory {relative}: {error}") from error
        require(
            _filesystem_snapshot_state(after_directory) == before_state,
            f".autopilot directory changed during snapshot: {relative}",
        )
        after_streams = _windows_stream_snapshot(
            directory,
            label=f"directory {relative}",
        )
        try:
            after_final_stream_directory = os.lstat(directory)
        except OSError as error:
            raise VerificationError(
                f"cannot re-inspect .autopilot directory after final stream enumeration {relative}: {error}"
            ) from error
        require(
            _filesystem_snapshot_state(after_final_stream_directory) == before_state,
            f".autopilot directory changed during final stream enumeration: {relative}",
        )
        require(
            after_streams == before_streams,
            f".autopilot Windows stream inventory changed during snapshot: {relative}",
        )

    visit_directory(root, ".", 0)
    rows.sort(key=lambda row: row[0])
    material = {
        "schema": "complete-autopilot-tree-point-observation-v2",
        "entry_count": len(rows),
        "total_file_bytes": total_bytes,
        "rows": rows,
    }
    return {
        "schema": material["schema"],
        "entry_count": len(rows),
        "total_file_bytes": total_bytes,
        "digest": digest(material),
        "rows": tuple(rows),
    }


_GIT_BOUNDARY: dict[str, Any] | None = None


def _windows_system_environment() -> dict[str, str]:
    if os.name != "nt":
        return {}
    try:
        buffer = ctypes.create_unicode_buffer(32_768)
        get_windows_directory = ctypes.windll.kernel32.GetWindowsDirectoryW
        get_windows_directory.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        get_windows_directory.restype = ctypes.c_uint32
        length = get_windows_directory(buffer, len(buffer))
        require(0 < length < len(buffer), "cannot resolve the Windows system directory")
        windows_root = str(Path(buffer.value).resolve())
    except VerificationError:
        raise
    except Exception as error:
        raise VerificationError(
            f"cannot query the Windows system directory: {error}"
        ) from error
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


def _git_executable_identity_from_stat(stat_result: os.stat_result) -> GitExecutableIdentity:
    birthtime_ns = _optional_stat_integer(stat_result, "st_birthtime_ns")
    if birthtime_ns is None:
        birthtime = getattr(stat_result, "st_birthtime", None)
        if birthtime is not None:
            birthtime_ns = int(float(birthtime) * 1_000_000_000)
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
        birthtime_ns,
    )


def _git_executable_continuity_key(
    identity: GitExecutableIdentity,
    *,
    host_platform: str | None = None,
) -> GitExecutableContinuityKey:
    """Return only platform-stable fields while retaining raw ctime as evidence."""

    selected_platform = sys.platform if host_platform is None else host_platform
    if selected_platform == "win32":
        # Python 3.12 exposes creation time explicitly as st_birthtime_ns and
        # deprecates the Windows st_ctime_ns meaning.  Older Python versions
        # expose creation time through st_ctime_ns, which is the compatibility
        # fallback only when birth time is unavailable.
        creation_time_ns = identity[5] if identity[5] is not None else identity[4]
        return identity[:4] + (creation_time_ns,)
    return identity[:5]


def _git_executable_path_state(path: Path) -> GitExecutableIdentity:
    try:
        require(path.is_file() and not path.is_symlink(), "Git executable is no longer a regular file")
        stat_result = path.stat()
    except OSError as error:
        raise VerificationError(f"cannot inspect Git executable path state: {error}") from error
    require(
        0 < stat_result.st_size <= MAX_NATIVE_EXECUTABLE_BYTES,
        "Git executable size is outside the verifier limit",
    )
    return _git_executable_identity_from_stat(stat_result)


def _open_file_identity(handle: Any) -> GitExecutableIdentity:
    try:
        stat_result = os.fstat(handle.fileno())
    except (OSError, ValueError) as error:
        raise VerificationError(f"cannot inspect open Git executable identity: {error}") from error
    return _git_executable_identity_from_stat(stat_result)


def _read_immutable_executable_snapshot(
    handle: Any,
    *,
    expected_identity: GitExecutableIdentity | None,
    label: str,
    identity_platform: str | None = None,
) -> bytes:
    """Make one bounded read bracketed by platform-stable identity checks."""

    before = _open_file_identity(handle)
    require(
        0 < before[2] <= MAX_NATIVE_EXECUTABLE_BYTES,
        f"{label} size is outside the verifier limit",
    )
    if expected_identity is not None:
        require(
            _git_executable_continuity_key(
                before,
                host_platform=identity_platform,
            )
            == _git_executable_continuity_key(
                expected_identity,
                host_platform=identity_platform,
            ),
            f"{label} path/open identity or size changed before snapshot",
        )
    try:
        handle.seek(0)
        raw = handle.read(MAX_NATIVE_EXECUTABLE_BYTES + 1)
        handle.seek(0)
    except (OSError, ValueError) as error:
        raise VerificationError(f"cannot read {label}: {error}") from error
    after = _open_file_identity(handle)
    require(
        _git_executable_continuity_key(before, host_platform=identity_platform)
        == _git_executable_continuity_key(after, host_platform=identity_platform),
        f"{label} identity changed while reading one snapshot",
    )
    require(len(raw) == before[2], f"{label} read length differs from file size")
    return raw


def _normalize_host_machine(host_machine: str) -> str:
    require(isinstance(host_machine, str) and host_machine.strip(), "host machine identity is missing")
    value = host_machine.strip().casefold().replace("-", "_")
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86_64": "x86_64",
        "i386": "x86",
        "i486": "x86",
        "i586": "x86",
        "i686": "x86",
        "x86": "x86",
        "aarch64": "arm64",
        "arm64": "arm64",
        "arm64e": "arm64",
        "arm": "arm",
        "armv6l": "arm",
        "armv7l": "arm",
        "armv8l": "arm",
        "ppc64": "ppc64",
        "powerpc64": "ppc64",
        "ppc64le": "ppc64le",
        "powerpc64le": "ppc64le",
        "s390x": "s390x",
        "riscv64": "riscv64",
    }
    require(value in aliases, f"unsupported host machine: {host_machine}")
    return aliases[value]


def _current_host_machine(host_platform: str) -> str:
    if host_platform == "win32":
        class SystemInfo(ctypes.Structure):
            _fields_ = [("raw", ctypes.c_ubyte * 48)]

        system_info = SystemInfo()
        try:
            ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(system_info))
        except (AttributeError, OSError) as error:
            raise VerificationError(f"cannot resolve native Windows host architecture: {error}") from error
        processor_architecture = int.from_bytes(bytes(system_info.raw[:2]), "little")
        windows_architectures = {
            0: "x86",
            5: "arm",
            9: "x86_64",
            12: "arm64",
        }
        require(
            processor_architecture in windows_architectures,
            f"unsupported native Windows processor architecture: {processor_architecture}",
        )
        return windows_architectures[processor_architecture]
    try:
        return _normalize_host_machine(os.uname().machine)
    except (AttributeError, OSError) as error:
        raise VerificationError(f"cannot resolve native host architecture: {error}") from error


def _require_native_region(raw: bytes | memoryview, offset: int, size: int, *, label: str) -> None:
    require(
        isinstance(offset, int)
        and isinstance(size, int)
        and offset >= 0
        and size >= 0
        and offset <= len(raw)
        and size <= len(raw) - offset,
        f"native executable image is truncated in {label}",
    )


def _native_image_result(
    *, host_platform: str, host_machine: str
) -> dict[str, str]:
    return {
        "policy": NATIVE_EXECUTABLE_FORMAT_POLICY,
        "host_platform": host_platform,
        "host_machine": host_machine,
        "native_executable_format": SUPPORTED_NATIVE_IMAGE_FORMATS[host_platform],
    }


def _inspect_pe_image(raw: bytes, *, host_machine: str) -> None:
    require(raw[:2] == b"MZ", "native executable image does not use PE/COFF on host platform win32")
    _require_native_region(raw, 0, 64, label="PE DOS header")
    pe_offset = struct.unpack_from("<I", raw, 0x3C)[0]
    require(pe_offset >= 64, "PE/COFF header offset is malformed")
    _require_native_region(raw, pe_offset, 24, label="PE signature and COFF header")
    require(raw[pe_offset : pe_offset + 4] == b"PE\0\0", "PE/COFF signature mismatch")
    machine, section_count, _, _, _, optional_size, characteristics = struct.unpack_from(
        "<HHIIIHH", raw, pe_offset + 4
    )
    expected_machine = {
        "x86": (0x014C, 0x010B, 96),
        "x86_64": (0x8664, 0x020B, 112),
        "arm64": (0xAA64, 0x020B, 112),
    }
    require(host_machine in expected_machine, f"unsupported PE/COFF host machine: {host_machine}")
    required_machine, required_optional_magic, minimum_optional_size = expected_machine[host_machine]
    require(machine == required_machine, "PE/COFF machine does not match the host architecture")
    require(
        characteristics & 0x0002 and not characteristics & 0x2000,
        "PE/COFF image must be executable and must not be a DLL",
    )
    require(0 < section_count <= 96, "PE/COFF section count is invalid")
    require(
        optional_size >= minimum_optional_size,
        "PE/COFF optional header is smaller than the realistic host-image minimum",
    )
    optional_offset = pe_offset + 24
    _require_native_region(raw, optional_offset, optional_size, label="PE optional header")
    optional_magic = struct.unpack_from("<H", raw, optional_offset)[0]
    require(optional_magic == required_optional_magic, "PE/COFF optional-header class does not match the host architecture")
    entry_point = struct.unpack_from("<I", raw, optional_offset + 16)[0]
    size_of_image = struct.unpack_from("<I", raw, optional_offset + 56)[0]
    size_of_headers = struct.unpack_from("<I", raw, optional_offset + 60)[0]
    require(entry_point > 0, "PE/COFF AddressOfEntryPoint must be nonzero")
    require(size_of_image > entry_point, "PE/COFF entry point lies outside SizeOfImage")
    section_table_offset = optional_offset + optional_size
    section_table_size = section_count * 40
    require(section_table_size <= MAX_NATIVE_IMAGE_TABLE_BYTES, "PE/COFF section table exceeds the verifier limit")
    _require_native_region(raw, section_table_offset, section_table_size, label="PE section table")
    section_table_limit = section_table_offset + section_table_size
    require(
        size_of_headers >= section_table_limit and size_of_headers <= len(raw),
        "PE/COFF SizeOfHeaders does not cover the complete section table",
    )
    executable_entry_section = False
    for index in range(section_count):
        section_offset = section_table_offset + index * 40
        virtual_size = struct.unpack_from("<I", raw, section_offset + 8)[0]
        virtual_address = struct.unpack_from("<I", raw, section_offset + 12)[0]
        raw_size = struct.unpack_from("<I", raw, section_offset + 16)[0]
        raw_pointer = struct.unpack_from("<I", raw, section_offset + 20)[0]
        section_characteristics = struct.unpack_from("<I", raw, section_offset + 36)[0]
        virtual_span = max(virtual_size, raw_size)
        if virtual_span > 0:
            require(
                virtual_address < size_of_image
                and virtual_span <= size_of_image - virtual_address,
                "PE/COFF section virtual range lies outside SizeOfImage",
            )
        if raw_size > 0:
            require(
                raw_pointer >= size_of_headers,
                "PE/COFF section raw bytes overlap headers",
            )
            _require_native_region(
                raw,
                raw_pointer,
                raw_size,
                label="PE section raw range",
            )
        if section_characteristics & 0x20000000:
            require(raw_size > 0, "PE/COFF executable section has no raw bytes")
            if virtual_address <= entry_point < virtual_address + virtual_span:
                executable_entry_section = True
    require(
        executable_entry_section,
        "PE/COFF entry point is not covered by a valid executable section",
    )


def _inspect_elf_image(raw: bytes, *, host_machine: str) -> None:
    require(raw[:4] == b"\x7fELF", "native executable image does not use ELF on host platform linux")
    _require_native_region(raw, 0, 16, label="ELF identification")
    elf_class = raw[4]
    data_encoding = raw[5]
    require(elf_class in {1, 2}, "ELF class is unsupported")
    require(data_encoding in {1, 2}, "ELF data encoding is unsupported")
    require(raw[6] == 1, "ELF identification version is unsupported")
    endian = "<" if data_encoding == 1 else ">"
    expected_machine = {
        "x86": (3, 1, 1),
        "x86_64": (62, 2, 1),
        "arm": (40, 1, 1),
        "arm64": (183, 2, 1),
        "ppc64": (21, 2, 2),
        "ppc64le": (21, 2, 1),
        "s390x": (22, 2, 2),
        "riscv64": (243, 2, 1),
    }
    require(host_machine in expected_machine, f"unsupported ELF host machine: {host_machine}")
    required_machine, required_class, required_encoding = expected_machine[host_machine]
    require(
        elf_class == required_class and data_encoding == required_encoding,
        "ELF class or byte order does not match the host architecture",
    )
    header_size = 52 if elf_class == 1 else 64
    _require_native_region(raw, 0, header_size, label="ELF header")
    image_type, machine, version = struct.unpack_from(endian + "HHI", raw, 16)
    require(image_type in {2, 3}, "ELF image must be ET_EXEC or ET_DYN")
    require(machine == required_machine, "ELF machine does not match the host architecture")
    require(version == 1, "ELF header version is unsupported")
    if elf_class == 1:
        entry_point = struct.unpack_from(endian + "I", raw, 24)[0]
        program_offset = struct.unpack_from(endian + "I", raw, 28)[0]
        declared_header_size, program_entry_size, program_count = struct.unpack_from(
            endian + "HHH", raw, 40
        )
        minimum_program_entry_size = 32
        dynamic_entry_size = 8
        address_limit = 1 << 32
    else:
        entry_point = struct.unpack_from(endian + "Q", raw, 24)[0]
        program_offset = struct.unpack_from(endian + "Q", raw, 32)[0]
        declared_header_size, program_entry_size, program_count = struct.unpack_from(
            endian + "HHH", raw, 52
        )
        minimum_program_entry_size = 56
        dynamic_entry_size = 16
        address_limit = 1 << 64
    require(entry_point > 0, "ELF entry point must be nonzero")
    require(
        declared_header_size == header_size,
        "ELF declared header size does not match its class",
    )
    require(0 < program_count < 0xFFFF, "ELF program-header count is invalid or extended")
    require(
        minimum_program_entry_size <= program_entry_size <= 4096,
        "ELF program-header entry size is invalid",
    )
    require(
        program_offset >= declared_header_size,
        "ELF program-header table overlaps the declared ELF header",
    )
    program_table_size = program_entry_size * program_count
    require(program_table_size <= MAX_NATIVE_IMAGE_TABLE_BYTES, "ELF program-header table exceeds the verifier limit")
    _require_native_region(raw, program_offset, program_table_size, label="ELF program-header table")
    executable_entry_load = False
    valid_interpreter = False
    dynamic_ranges: list[tuple[int, int]] = []
    for index in range(program_count):
        entry_offset = program_offset + index * program_entry_size
        if elf_class == 1:
            (
                program_type,
                file_offset,
                virtual_address,
                _,
                file_size,
                memory_size,
                flags,
                alignment,
            ) = struct.unpack_from(endian + "IIIIIIII", raw, entry_offset)
        else:
            (
                program_type,
                flags,
                file_offset,
                virtual_address,
                _,
                file_size,
                memory_size,
                alignment,
            ) = struct.unpack_from(endian + "IIQQQQQQ", raw, entry_offset)
        if program_type == 1:
            require(memory_size > 0, "ELF PT_LOAD segment has zero memory size")
            require(file_size <= memory_size, "ELF PT_LOAD file size exceeds memory size")
            require(
                virtual_address + memory_size <= address_limit,
                "ELF PT_LOAD virtual range overflows the address class",
            )
            _require_native_region(raw, file_offset, file_size, label="ELF PT_LOAD file range")
            require(
                alignment in {0, 1}
                or (
                    alignment & (alignment - 1) == 0
                    and virtual_address % alignment == file_offset % alignment
                ),
                "ELF PT_LOAD alignment is invalid",
            )
            if (
                flags & 0x1
                and virtual_address <= entry_point < virtual_address + memory_size
                and entry_point - virtual_address < file_size
            ):
                executable_entry_load = True
        elif program_type == 3:
            require(1 < file_size <= MAX_GIT_POINTER_BYTES, "ELF PT_INTERP size is invalid")
            _require_native_region(raw, file_offset, file_size, label="ELF PT_INTERP file range")
            interpreter = raw[file_offset : file_offset + file_size]
            require(
                interpreter.endswith(b"\0")
                and b"\0" not in interpreter[:-1]
                and interpreter[:-1].startswith(b"/"),
                "ELF PT_INTERP is not one absolute NUL-terminated path",
            )
            valid_interpreter = True
        elif program_type == 2:
            require(
                0 < file_size <= MAX_NATIVE_IMAGE_TABLE_BYTES
                and file_size % dynamic_entry_size == 0,
                "ELF PT_DYNAMIC size is invalid",
            )
            _require_native_region(raw, file_offset, file_size, label="ELF PT_DYNAMIC file range")
            dynamic_ranges.append((file_offset, file_size))
    require(
        executable_entry_load,
        "ELF entry point is not file-backed by an executable PT_LOAD segment",
    )
    dynamic_pie = False
    for dynamic_offset, dynamic_size in dynamic_ranges:
        for item_offset in range(
            dynamic_offset,
            dynamic_offset + dynamic_size,
            dynamic_entry_size,
        ):
            if elf_class == 1:
                tag, value = struct.unpack_from(endian + "II", raw, item_offset)
            else:
                tag, value = struct.unpack_from(endian + "QQ", raw, item_offset)
            if tag == 0:
                break
            if tag == 0x6FFFFFFB and value & 0x08000000:
                dynamic_pie = True
    if image_type == 3:
        require(
            valid_interpreter or dynamic_pie,
            "ELF ET_DYN image lacks PT_INTERP and DF_1_PIE semantics",
        )


def _macho_host_cpu(host_machine: str) -> tuple[int, int, frozenset[int]]:
    machines = {
        "x86": (7, 32, frozenset({3})),
        "x86_64": (0x01000007, 64, frozenset({3})),
        "arm": (12, 32, frozenset({0})),
        "arm64": (0x0100000C, 64, frozenset({0})),
        "ppc64": (0x01000012, 64, frozenset({0})),
    }
    require(host_machine in machines, f"unsupported Mach-O host machine: {host_machine}")
    return machines[host_machine]


def _inspect_macho_thin(
    raw: bytes | memoryview,
    *,
    host_machine: str,
    expected_fat_subtype: int | None = None,
) -> None:
    expected_cpu, expected_bits, allowed_subtypes = _macho_host_cpu(host_machine)
    _require_native_region(raw, 0, 4, label="Mach-O magic")
    magic = bytes(raw[:4])
    magics = {
        b"\xce\xfa\xed\xfe": ("<", 32),
        b"\xfe\xed\xfa\xce": (">", 32),
        b"\xcf\xfa\xed\xfe": ("<", 64),
        b"\xfe\xed\xfa\xcf": (">", 64),
    }
    require(magic in magics, "Mach-O host slice does not contain a thin Mach-O image")
    endian, bits = magics[magic]
    require(bits == expected_bits, "Mach-O image class does not match the host architecture")
    header_size = 28 if bits == 32 else 32
    _require_native_region(raw, 0, header_size, label="Mach-O header")
    cpu_type, cpu_subtype, file_type, command_count, command_bytes = struct.unpack_from(
        endian + "IIIII", raw, 4
    )
    require(cpu_type == expected_cpu, "Mach-O CPU type does not match the host architecture")
    normalized_subtype = cpu_subtype & 0x00FFFFFF
    require(
        normalized_subtype in allowed_subtypes,
        "Mach-O CPU subtype is not compatible with the host architecture",
    )
    if expected_fat_subtype is not None:
        require(
            normalized_subtype == expected_fat_subtype & 0x00FFFFFF,
            "Mach-O universal and thin CPU subtypes disagree",
        )
    require(file_type == 2, "Mach-O image must have MH_EXECUTE file type")
    require(command_count <= 65_535, "Mach-O load-command count is invalid")
    require(command_bytes <= MAX_NATIVE_IMAGE_TABLE_BYTES, "Mach-O load commands exceed the verifier limit")
    _require_native_region(raw, header_size, command_bytes, label="Mach-O load commands")
    command_limit = header_size + command_bytes
    command_offset = header_size
    executable_file_ranges: list[tuple[int, int]] = []
    entry_offsets: list[int] = []
    for _ in range(command_count):
        require(command_offset + 8 <= command_limit, "Mach-O load-command inventory is truncated")
        command, command_size = struct.unpack_from(endian + "II", raw, command_offset)
        require(
            command_size >= 8
            and command_size % (8 if bits == 64 else 4) == 0
            and command_size <= command_limit - command_offset,
            "Mach-O load-command size is invalid",
        )
        if bits == 32 and command == 0x1:
            require(command_size >= 56, "Mach-O LC_SEGMENT command is truncated")
            virtual_size = struct.unpack_from(endian + "I", raw, command_offset + 28)[0]
            file_offset = struct.unpack_from(endian + "I", raw, command_offset + 32)[0]
            file_size = struct.unpack_from(endian + "I", raw, command_offset + 36)[0]
            initial_protection = struct.unpack_from(endian + "I", raw, command_offset + 44)[0]
            require(file_size <= virtual_size, "Mach-O segment file size exceeds virtual size")
            _require_native_region(raw, file_offset, file_size, label="Mach-O segment file range")
            if initial_protection & 0x4:
                require(file_size > 0, "Mach-O executable segment has no file-backed bytes")
                executable_file_ranges.append((file_offset, file_offset + file_size))
        elif bits == 64 and command == 0x19:
            require(command_size >= 72, "Mach-O LC_SEGMENT_64 command is truncated")
            virtual_size = struct.unpack_from(endian + "Q", raw, command_offset + 32)[0]
            file_offset = struct.unpack_from(endian + "Q", raw, command_offset + 40)[0]
            file_size = struct.unpack_from(endian + "Q", raw, command_offset + 48)[0]
            initial_protection = struct.unpack_from(endian + "I", raw, command_offset + 60)[0]
            require(file_size <= virtual_size, "Mach-O segment file size exceeds virtual size")
            _require_native_region(raw, file_offset, file_size, label="Mach-O segment file range")
            if initial_protection & 0x4:
                require(file_size > 0, "Mach-O executable segment has no file-backed bytes")
                executable_file_ranges.append((file_offset, file_offset + file_size))
        elif command == 0x80000028:
            require(command_size >= 24, "Mach-O LC_MAIN command is truncated")
            entry_offset = struct.unpack_from(endian + "Q", raw, command_offset + 8)[0]
            require(0 < entry_offset < len(raw), "Mach-O LC_MAIN entry offset is invalid")
            entry_offsets.append(entry_offset)
        command_offset += command_size
    require(command_offset == command_limit, "Mach-O load-command byte count mismatch")
    require(executable_file_ranges, "Mach-O image lacks a file-backed executable segment")
    require(len(entry_offsets) == 1, "Mach-O image must contain exactly one valid LC_MAIN entry point")
    require(
        any(start <= entry_offsets[0] < end for start, end in executable_file_ranges),
        "Mach-O LC_MAIN entry point is not covered by an executable segment",
    )


def _inspect_macho_image(raw: bytes, *, host_machine: str) -> None:
    expected_cpu, _, _ = _macho_host_cpu(host_machine)
    _require_native_region(raw, 0, 4, label="Mach-O or universal magic")
    magic = raw[:4]
    fat_magics = {
        b"\xca\xfe\xba\xbe": (">", False),
        b"\xbe\xba\xfe\xca": ("<", False),
        b"\xca\xfe\xba\xbf": (">", True),
        b"\xbf\xba\xfe\xca": ("<", True),
    }
    if magic not in fat_magics:
        _inspect_macho_thin(raw, host_machine=host_machine)
        return
    endian, fat64 = fat_magics[magic]
    _require_native_region(raw, 0, 8, label="Mach-O universal header")
    architecture_count = struct.unpack_from(endian + "I", raw, 4)[0]
    require(0 < architecture_count <= 64, "Mach-O universal architecture count is invalid")
    entry_size = 32 if fat64 else 20
    table_size = architecture_count * entry_size
    require(table_size <= MAX_NATIVE_IMAGE_TABLE_BYTES, "Mach-O universal architecture table exceeds the verifier limit")
    _require_native_region(raw, 8, table_size, label="Mach-O universal architecture table")
    table_limit = 8 + table_size
    host_slices: list[tuple[int, int, int]] = []
    all_slice_ranges: list[tuple[int, int]] = []
    for index in range(architecture_count):
        entry_offset = 8 + index * entry_size
        cpu_type = struct.unpack_from(endian + "I", raw, entry_offset)[0]
        cpu_subtype = struct.unpack_from(endian + "I", raw, entry_offset + 4)[0]
        if fat64:
            slice_offset, slice_size = struct.unpack_from(endian + "QQ", raw, entry_offset + 8)
            alignment = struct.unpack_from(endian + "I", raw, entry_offset + 24)[0]
        else:
            slice_offset, slice_size, alignment = struct.unpack_from(endian + "III", raw, entry_offset + 8)
        require(alignment <= 31, "Mach-O universal slice alignment is invalid")
        require(slice_size > 0 and slice_offset >= table_limit, "Mach-O universal slice bounds are invalid")
        require(
            slice_offset % (1 << alignment) == 0,
            "Mach-O universal slice offset violates its declared alignment",
        )
        _require_native_region(raw, slice_offset, slice_size, label="Mach-O universal slice")
        all_slice_ranges.append((slice_offset, slice_offset + slice_size))
        if cpu_type == expected_cpu:
            host_slices.append((slice_offset, slice_size, cpu_subtype))
    ordered_ranges = sorted(all_slice_ranges)
    require(
        all(previous[1] <= current[0] for previous, current in zip(ordered_ranges, ordered_ranges[1:])),
        "Mach-O universal slices overlap",
    )
    require(host_slices, "Mach-O universal image has no host-compatible slice")
    failures: list[str] = []
    for slice_offset, slice_size, cpu_subtype in host_slices:
        try:
            _inspect_macho_thin(
                memoryview(raw)[slice_offset : slice_offset + slice_size],
                host_machine=host_machine,
                expected_fat_subtype=cpu_subtype,
            )
            return
        except VerificationError as error:
            failures.append(str(error))
    raise VerificationError(f"Mach-O host-compatible slices are invalid: {failures[0]}")


def _inspect_native_image(
    raw: bytes, host_platform: str, host_machine: str
) -> dict[str, str]:
    """Inspect bounded bytes without executing them; useful for deterministic fixtures."""

    require(isinstance(raw, bytes), "native executable image fixture must be bytes")
    require(0 < len(raw) <= MAX_NATIVE_EXECUTABLE_BYTES, "native executable image size is outside the verifier limit")
    require(not raw.startswith(b"#!"), "script wrappers are forbidden as the Git executable")
    require(host_platform in SUPPORTED_NATIVE_IMAGE_FORMATS, f"unsupported host platform: {host_platform}")
    normalized_machine = _normalize_host_machine(host_machine)
    if host_platform == "win32":
        _inspect_pe_image(raw, host_machine=normalized_machine)
    elif host_platform == "linux":
        _inspect_elf_image(raw, host_machine=normalized_machine)
    else:
        _inspect_macho_image(raw, host_machine=normalized_machine)
    return _native_image_result(
        host_platform=host_platform,
        host_machine=normalized_machine,
    )


def inspect_host_native_executable(
    handle: Any,
    *,
    host_platform: str | None = None,
    host_machine: str | None = None,
) -> dict[str, str]:
    """Read and inspect one retained executable handle under the V5 byte limit."""

    inspection, _ = _inspect_and_digest_executable_snapshot(
        handle,
        expected_identity=None,
        label="retained Git executable",
        host_platform=host_platform,
        host_machine=host_machine,
    )
    return inspection


def _inspect_and_digest_executable_snapshot(
    handle: Any,
    *,
    expected_identity: GitExecutableIdentity | None,
    label: str,
    host_platform: str | None = None,
    host_machine: str | None = None,
) -> tuple[dict[str, str], str]:
    """Parse and SHA-256 the exact same one-read immutable byte snapshot."""

    selected_platform = sys.platform if host_platform is None else host_platform
    selected_machine = (
        _current_host_machine(selected_platform) if host_machine is None else host_machine
    )
    raw = _read_immutable_executable_snapshot(
        handle,
        expected_identity=expected_identity,
        label=label,
        identity_platform=selected_platform,
    )
    inspection = _inspect_native_image(raw, selected_platform, selected_machine)
    return inspection, sha256_bytes(raw)


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
    require(not git_executable.is_symlink(), "Git executable symlinks are forbidden")
    try:
        resolved_executable = git_executable.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"Git executable cannot be resolved: {error}") from error
    require(resolved_executable == git_executable, "Git executable path must already be canonical")
    if sys.platform == "win32":
        require(resolved_executable.suffix.casefold() == ".exe", "Git executable must be a native .exe file")
    else:
        require(os.access(resolved_executable, os.X_OK), "Git executable is not executable")
    identity_platform = sys.platform
    host_machine = _current_host_machine(identity_platform)
    path_state = _git_executable_path_state(resolved_executable)
    try:
        executable_handle = resolved_executable.open("rb")
    except OSError as error:
        raise VerificationError(f"cannot open Git executable: {error}") from error
    try:
        handle_identity = _open_file_identity(executable_handle)
        require(
            _git_executable_continuity_key(
                handle_identity,
                host_platform=identity_platform,
            )
            == _git_executable_continuity_key(
                path_state,
                host_platform=identity_platform,
            ),
            "Git executable path/open-file identity mismatch",
        )
        native_image, observed_digest = _inspect_and_digest_executable_snapshot(
            executable_handle,
            expected_identity=path_state,
            label="initial retained Git executable",
            host_platform=identity_platform,
            host_machine=host_machine,
        )
        require(
            _git_executable_continuity_key(
                _git_executable_path_state(resolved_executable),
                host_platform=identity_platform,
            )
            == _git_executable_continuity_key(
                path_state,
                host_platform=identity_platform,
            ),
            "Git executable path identity changed during initial snapshot",
        )
        require(
            observed_digest == expected_git_executable_sha256,
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
            "identity_platform": identity_platform,
            "host_machine": host_machine,
            "native_image": native_image,
            "git_dir": git_dir,
            "common_dir": common_dir,
            "index_path": index_path.resolve(strict=True),
            "work_tree": repo_root,
            "environment": environment,
        }
    except BaseException:
        try:
            executable_handle.close()
        except OSError:
            pass
        raise


def verify_git_executable_stable(*, full_digest: bool) -> None:
    require(_GIT_BOUNDARY is not None, "Git execution boundary is not configured")
    require(full_digest is True, "partial Git executable revalidation is prohibited")
    executable = _GIT_BOUNDARY["executable"]
    handle = _GIT_BOUNDARY["handle"]
    expected_identity = _GIT_BOUNDARY["path_state"]
    identity_platform = _GIT_BOUNDARY["identity_platform"]
    host_machine = _GIT_BOUNDARY["host_machine"]
    expected_key = _git_executable_continuity_key(
        expected_identity,
        host_platform=identity_platform,
    )
    require(
        _git_executable_continuity_key(
            _git_executable_path_state(executable),
            host_platform=identity_platform,
        )
        == expected_key,
        "Git executable identity changed during verification",
    )
    require(
        _git_executable_continuity_key(
            _open_file_identity(handle),
            host_platform=identity_platform,
        )
        == _git_executable_continuity_key(
            _GIT_BOUNDARY["handle_identity"],
            host_platform=identity_platform,
        ),
        "open Git executable identity changed during verification",
    )
    retained_native, retained_digest = _inspect_and_digest_executable_snapshot(
        handle,
        expected_identity=expected_identity,
        label="retained Git executable revalidation",
        host_platform=identity_platform,
        host_machine=host_machine,
    )
    require(
        retained_native == _GIT_BOUNDARY["native_image"],
        "retained Git executable native-image result changed during verification",
    )
    require(
        retained_digest == _GIT_BOUNDARY["expected_sha256"],
        "retained Git executable bytes changed during verification",
    )
    require(
        _git_executable_continuity_key(
            _git_executable_path_state(executable),
            host_platform=identity_platform,
        )
        == expected_key,
        "Git executable path identity changed after retained snapshot",
    )
    try:
        with executable.open("rb") as current_handle:
            require(
                _git_executable_continuity_key(
                    _open_file_identity(current_handle),
                    host_platform=identity_platform,
                )
                == expected_key,
                "Git executable path now addresses a different file",
            )
            current_native, current_digest = _inspect_and_digest_executable_snapshot(
                current_handle,
                expected_identity=expected_identity,
                label="current-path Git executable revalidation",
                host_platform=identity_platform,
                host_machine=host_machine,
            )
            require(
                current_native == _GIT_BOUNDARY["native_image"],
                "Git executable path native-image result changed during verification",
            )
            require(
                current_digest == _GIT_BOUNDARY["expected_sha256"],
                "Git executable path bytes changed during verification",
            )
    except (OSError, ValueError) as error:
        raise VerificationError(f"cannot re-open Git executable: {error}") from error
    require(
        _git_executable_continuity_key(
            _git_executable_path_state(executable),
            host_platform=identity_platform,
        )
        == expected_key,
        "Git executable path identity changed after current-path snapshot",
    )


def _terminate_and_reap_git_process(
    process: subprocess.Popen[bytes], *, reason: str
) -> VerificationError | None:
    """Best-effort kill followed by one typed, bounded reap deadline."""

    try:
        running = process.poll() is None
    except subprocess.TimeoutExpired:
        return GitTimeoutAfterKillError(
            f"Git process state inspection timed out after {reason}",
            primary_code="GIT_TIMEOUT",
        )
    except OSError as error:
        return VerificationError(f"cannot inspect Git process state after {reason}: {error}")
    if running:
        try:
            process.kill()
        except subprocess.TimeoutExpired:
            return GitTimeoutAfterKillError(
                f"Git process kill timed out after {reason}",
                primary_code="GIT_TIMEOUT",
            )
        except OSError:
            # A concurrent exit is harmless if the bounded wait below can reap it.
            pass
    try:
        process.wait(timeout=GIT_KILL_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return GitTimeoutAfterKillError(
            "Git process did not terminate and reap within "
            f"{GIT_KILL_REAP_TIMEOUT_SECONDS} seconds after {reason}",
            primary_code="GIT_TIMEOUT",
        )
    except OSError as error:
        return VerificationError(f"cannot reap Git process after {reason}: {error}")
    return None


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
    except subprocess.TimeoutExpired as error:
        primary_error = GitTimeoutError(
            f"git {' '.join(args)} timed out while starting: {error}"
        )
        try:
            verify_git_executable_stable(full_digest=True)
        except VerificationError as cleanup_error:
            primary_error.add_cleanup_evidence(cleanup_error)
        raise primary_error from error
    except OSError as error:
        primary_error = VerificationError(f"git {' '.join(args)} could not start: {error}")
        try:
            verify_git_executable_stable(full_digest=True)
        except VerificationError as cleanup_error:
            primary_error.add_cleanup_evidence(cleanup_error)
        raise primary_error from error

    if process.stdout is None:
        primary_error = VerificationError("Git output pipe was not created")
        setup_error = _terminate_and_reap_git_process(
            process,
            reason="missing output pipe",
        )
        if setup_error is not None:
            primary_error.add_cleanup_evidence(setup_error)
        try:
            verify_git_executable_stable(full_digest=True)
        except VerificationError as cleanup_error:
            primary_error.add_cleanup_evidence(cleanup_error)
        raise primary_error
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
            except BaseException:
                pass

    try:
        reader = threading.Thread(
            target=read_bounded_output,
            name="v5-git-output-reader",
            daemon=True,
        )
        reader.start()
    except Exception as error:
        primary_error = VerificationError(f"cannot start bounded Git output reader: {error}")
        setup_error = _terminate_and_reap_git_process(
            process,
            reason="output-reader setup failure",
        )
        if setup_error is not None:
            primary_error.add_cleanup_evidence(setup_error)
        try:
            process.stdout.close()
        except (OSError, ValueError) as cleanup_error:
            primary_error.add_cleanup_evidence(
                VerificationError(f"cannot close Git output pipe after reader setup failure: {cleanup_error}")
            )
        try:
            verify_git_executable_stable(full_digest=True)
        except VerificationError as cleanup_error:
            primary_error.add_cleanup_evidence(cleanup_error)
        raise primary_error from error
    timed_out = False
    lifecycle_errors: list[VerificationError] = []
    try:
        try:
            process.wait(timeout=GIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            reap_error = _terminate_and_reap_git_process(
                process,
                reason=f"primary {GIT_TIMEOUT_SECONDS}-second timeout",
            )
            if reap_error is not None:
                lifecycle_errors.append(reap_error)
        except OSError as error:
            lifecycle_errors.append(VerificationError(f"cannot wait for Git process: {error}"))
    finally:
        try:
            still_running = process.poll() is None
        except subprocess.TimeoutExpired:
            still_running = True
            lifecycle_errors.append(
                GitTimeoutAfterKillError(
                    "Git process state inspection timed out during cleanup",
                    primary_code="GIT_TIMEOUT",
                )
            )
        except OSError as error:
            still_running = True
            lifecycle_errors.append(VerificationError(f"cannot inspect Git process during cleanup: {error}"))
        if still_running:
            reap_error = _terminate_and_reap_git_process(process, reason="cleanup")
            if reap_error is not None:
                lifecycle_errors.append(reap_error)
        try:
            reader.join(timeout=GIT_READER_JOIN_TIMEOUT_SECONDS)
        except Exception as error:
            lifecycle_errors.append(VerificationError(f"cannot join Git output reader: {error}"))
        try:
            reader_alive = reader.is_alive()
        except Exception as error:
            reader_alive = True
            lifecycle_errors.append(VerificationError(f"cannot inspect Git output reader: {error}"))
        if reader_alive:
            try:
                process.stdout.close()
            except (OSError, ValueError) as error:
                lifecycle_errors.append(VerificationError(f"cannot close Git output pipe: {error}"))
            try:
                reader.join(timeout=1)
            except Exception as error:
                lifecycle_errors.append(VerificationError(f"cannot finally join Git output reader: {error}"))
        try:
            verify_git_executable_stable(full_digest=True)
        except VerificationError as error:
            lifecycle_errors.append(error)
    try:
        reader_alive = reader.is_alive()
    except Exception as error:
        reader_alive = True
        lifecycle_errors.append(
            VerificationError(f"cannot inspect final Git output reader state: {error}")
        )
    raw = bytes(output)
    decoded: str | None = None
    decoding_error: GitNonUtf8Error | None = None
    if not binary or timed_out or process.returncode != 0:
        try:
            decoded = raw.decode("utf-8").strip()
        except UnicodeError:
            decoding_error = GitNonUtf8Error(
                f"git {' '.join(args)} returned non-UTF-8 output "
                f"(bytes={len(raw)}, sha256={sha256_bytes(raw)})",
                primary_code="GIT_TIMEOUT" if timed_out else None,
            )
    primary_error: VerificationError | None = None
    if output_overflow.is_set():
        primary_error = GitOutputOverflowError("Git output exceeds the verifier limit")
    elif timed_out:
        after_kill = next(
            (
                error
                for error in lifecycle_errors
                if isinstance(error, GitTimeoutAfterKillError)
            ),
            None,
        )
        primary_error = (
            after_kill
            or decoding_error
            or GitTimeoutError(
                f"git {' '.join(args)} timed out: "
                f"{decoded or f'{GIT_TIMEOUT_SECONDS} seconds'}"
            )
        )
    elif reader_alive:
        primary_error = VerificationError("Git output pipe did not close after process exit")
    elif reader_errors:
        primary_error = VerificationError(f"Git output reader failed: {reader_errors[0]}")
    elif lifecycle_errors:
        primary_error = lifecycle_errors[0]
    elif decoding_error is not None:
        primary_error = decoding_error
    elif process.returncode != 0:
        primary_error = VerificationError(
            f"git {' '.join(args)} failed: {decoded or f'exit {process.returncode}'}"
        )
    if primary_error is not None:
        for cleanup_error in lifecycle_errors:
            if cleanup_error is not primary_error:
                primary_error.add_cleanup_evidence(cleanup_error)
        raise primary_error
    if binary:
        return raw
    require(decoded is not None, "Git text output was not decoded")
    return decoded


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
    require(manifest.get("schema_version") == 5, "manifest schema mismatch")
    require(manifest.get("kind") == "hive-mind-generic-product-overlay-manifest-v5", "manifest kind mismatch")
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
            "git_environment_correction_parent",
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
        lineage.get("git_environment_correction_parent")
        == {
            "commit": GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
            "tree": GIT_ENVIRONMENT_CORRECTION_PARENT_TREE,
        },
        "Git-environment correction parent commit/tree mismatch",
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
    require(authorship.get("architect") == "/root/verifier_architect", "architect identity mismatch")
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
            "remanded_git_boundary_predecessor",
            "remanded_git_environment_predecessor",
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
    require(
        payload.get("mode") == "exact-append-only-squash-proof-windows-identity-correction-v5",
        "committed payload mode mismatch",
    )
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
            "parent_commit": CORRECTION_PARENT_PARENT_COMMIT,
            "parent_tree": CORRECTION_PARENT_PARENT_TREE,
            "manifest_raw_sha256": CORRECTION_PARENT_MANIFEST_RAW_DIGEST,
            "full_payload_aggregate": {
                "domain": "hive-mind-os/v3-native-executable-matrix-correction-content/v4",
                "sha256": CORRECTION_PARENT_AGGREGATE_DIGEST,
            },
            "qualification_report_sha256": CORRECTION_PARENT_REPORT_DIGEST,
            "observed_status": "PUBLISHED_TREE_WITH_SQUASH_SEVERED_HISTORY_AND_RED_CONSTITUTIONAL_CI",
            "author_proposed_disposition": "ADAPT_REMAND",
        },
        "predecessor correction identity/status mismatch",
    )
    require(
        payload.get("remanded_git_boundary_predecessor")
        == {
            "commit": GIT_BOUNDARY_CORRECTION_COMMIT,
            "tree": GIT_BOUNDARY_CORRECTION_TREE,
            "parent_commit": GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
            "parent_tree": GIT_ENVIRONMENT_CORRECTION_PARENT_TREE,
            "manifest_raw_sha256": GIT_BOUNDARY_CORRECTION_MANIFEST_RAW_DIGEST,
            "full_payload_aggregate": {
                "domain": "hive-mind-os/v3-append-only-git-boundary-correction-content/v3",
                "sha256": GIT_BOUNDARY_CORRECTION_AGGREGATE_DIGEST,
            },
            "qualification_report_sha256": GIT_BOUNDARY_CORRECTION_REPORT_DIGEST,
            "observed_status": "QUALIFICATION_REMANDED_NATIVE_EXECUTABLE_FORMAT_AND_ADVERSARIAL_MATRIX_GAPS",
            "author_proposed_disposition": "ADAPT_REMAND",
        },
        "remanded Git-boundary predecessor identity/status mismatch",
    )
    require(
        payload.get("remanded_git_environment_predecessor")
        == {
            "commit": GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
            "tree": GIT_ENVIRONMENT_CORRECTION_PARENT_TREE,
            "parent_commit": PAYLOAD_A_COMMIT,
            "parent_tree": PAYLOAD_A_TREE,
            "manifest_raw_sha256": GIT_ENVIRONMENT_CORRECTION_PARENT_MANIFEST_RAW_DIGEST,
            "full_payload_aggregate": {
                "domain": "hive-mind-os/v3-append-only-correction-content/v2",
                "sha256": GIT_ENVIRONMENT_CORRECTION_PARENT_AGGREGATE_DIGEST,
            },
            "qualification_report_sha256": GIT_ENVIRONMENT_CORRECTION_PARENT_REPORT_DIGEST,
            "observed_status": "QUALIFICATION_REMANDED_GIT_ENVIRONMENT_FAIL_OPEN",
            "author_proposed_disposition": "ADAPT_REMAND",
        },
        "remanded Git-environment predecessor identity/status mismatch",
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
            "required_contract_mode": "exact-append-only-squash-proof-windows-identity-correction-v5",
            "required_git_executable_format_policy": NATIVE_EXECUTABLE_FORMAT_POLICY,
            "rejected_published_v4_manifest_raw_sha256": CORRECTION_PARENT_MANIFEST_RAW_DIGEST,
            "rejected_v3_git_boundary_manifest_raw_sha256": GIT_BOUNDARY_CORRECTION_MANIFEST_RAW_DIGEST,
            "rejected_f06_manifest_raw_sha256": GIT_ENVIRONMENT_CORRECTION_PARENT_MANIFEST_RAW_DIGEST,
            "rejected_historical_payload_a_manifest_raw_sha256": PAYLOAD_A_MANIFEST_RAW_DIGEST,
            "published_v4_activation": "PROHIBITED",
            "v3_git_boundary_activation": "PROHIBITED",
            "f06_activation": "PROHIBITED",
            "historical_payload_a_activation": "PROHIBITED",
            "legacy_v1_fallback": "PROHIBITED",
            "external_minimum_version_and_revocation_policy": "REQUIRED_NOT_SATISFIED",
        },
        "activation anti-downgrade contract mismatch",
    )
    require(
        payload.get("git_execution_boundary")
        == {
            "policy": GIT_EXECUTION_BOUNDARY_POLICY,
            "native_executable_format": "HOST_NATIVE_IMAGE_FORMAT_V1",
            "supported_hosts": SUPPORTED_NATIVE_IMAGE_FORMATS,
            "unsupported_host": "FAIL_CLOSED",
            "script_or_interpreter_wrapper": "PROHIBITED",
            "max_executable_bytes": MAX_NATIVE_EXECUTABLE_BYTES,
            "caller_path_and_raw_digest": "REQUIRED_EXTERNAL",
            "identity_continuity": {
                "windows": "DEVICE_FILE_ID_SIZE_MTIME_BIRTHTIME",
                "windows_pre_3_12_fallback": "DEVICE_FILE_ID_SIZE_MTIME_LEGACY_CREATION_CTIME",
                "windows_change_time": "DIAGNOSTIC_NOT_ACCEPTANCE_CRITICAL",
                "posix": "DEVICE_INODE_SIZE_MTIME_CTIME",
            },
            "compiled_native_delegator_exclusion": "NOT_PROVEN_BY_FORMAT",
            "runtime_dependency_closure": "REQUIRED_FOR_EXECUTION_NOT_SATISFIED",
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
            "caller_authenticated_git_path_raw_sha256_and_observed_native_format",
            "corrected_full_payload_aggregate_digest",
            "published_v4_parent_identity_report_and_remand",
            "v3_git_boundary_parent_identity",
            "v3_git_boundary_parent_remand_verdict",
            "v3_git_boundary_parent_qualification_report_digest",
            "f06_identity_report_and_remand",
            "historical_payload_a_identity_and_disposition",
            "platform_adversarial_matrix_receipt_digests",
            "focused_and_full_gate_transcript_digests",
            "court_verdict",
            "external_git_runtime_dependency_bundle_digest",
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
            "manifest_location": FROZEN_HOST_MANIFEST_LOCATION,
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


def parse_authenticated_gitattributes(raw: bytes) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Parse the authenticated root attributes without consulting ambient Git."""

    require(
        len(raw) <= MAX_GITATTRIBUTES_BYTES,
        f"authenticated .gitattributes exceeds {MAX_GITATTRIBUTES_BYTES} bytes",
    )
    require(raw and raw.endswith(b"\n"), "authenticated .gitattributes must end with LF")
    require(b"\r" not in raw, "authenticated .gitattributes must contain LF line endings only")
    require(
        all(byte in {9, 10} or 32 <= byte <= 126 for byte in raw),
        "authenticated .gitattributes must use printable ASCII plus TAB/LF only",
    )
    text = raw.decode("ascii")

    rules: list[tuple[str, tuple[str, ...]]] = []
    for line_number, line in enumerate(text.split("\n")[:-1], start=1):
        if not line or line.startswith("#"):
            continue
        require(
            line == line.strip(" \t"),
            f"authenticated .gitattributes line {line_number} has ambiguous edge whitespace",
        )
        require(
            '"' not in line and "\\" not in line,
            f"authenticated .gitattributes line {line_number} uses unsupported quoting or escaping",
        )
        fields = re.split(r"[ \t]+", line)
        require(len(fields) >= 2, f"authenticated .gitattributes line {line_number} is malformed")
        pattern, attributes = fields[0], tuple(fields[1:])
        require(
            pattern
            and not pattern.startswith(("!", "/"))
            and not pattern.endswith("/")
            and "//" not in pattern,
            f"authenticated .gitattributes pattern is unsupported: {pattern}",
        )
        require(
            len(pattern.encode("utf-8")) <= MAX_GITATTRIBUTE_PATTERN_BYTES
            and len(pattern.split("/")) <= MAX_GITATTRIBUTE_PATTERN_PARTS,
            f"authenticated .gitattributes pattern exceeds bounds: {pattern}",
        )
        seen_attributes: set[str] = set()
        for token in attributes:
            match = re.fullmatch(
                r"(?:(?P<prefix>[-!])?(?P<name>[A-Za-z][A-Za-z0-9_-]*)|(?P<set_name>[A-Za-z][A-Za-z0-9_-]*)=(?P<value>[^\s=]+))",
                token,
            )
            require(match is not None, f"authenticated .gitattributes token is malformed: {token}")
            name = match.group("name") or match.group("set_name")
            require(
                name not in seen_attributes,
                f"authenticated .gitattributes repeats attribute {name} on line {line_number}",
            )
            seen_attributes.add(name)
        rules.append((pattern, attributes))
        require(
            len(rules) <= MAX_GITATTRIBUTE_RULES,
            f"authenticated .gitattributes exceeds {MAX_GITATTRIBUTE_RULES} active rules",
        )
    require(rules, "authenticated .gitattributes has no active rules")
    return tuple(rules)


def _gitattribute_pattern_matches(pattern: str, relative: str) -> bool:
    """Match the strict Git-pattern subset used by the authenticated policy."""

    if "/" not in pattern:
        return fnmatch.fnmatchcase(relative.rsplit("/", 1)[-1], pattern)

    pattern_parts = pattern.split("/")
    path_parts = relative.split("/")
    memo: dict[tuple[int, int], bool] = {}

    def match_parts(pattern_index: int, path_index: int) -> bool:
        key = (pattern_index, path_index)
        if key in memo:
            return memo[key]
        if pattern_index == len(pattern_parts):
            result = path_index == len(path_parts)
        elif pattern_parts[pattern_index] == "**":
            result = any(
                match_parts(pattern_index + 1, next_path_index)
                for next_path_index in range(path_index, len(path_parts) + 1)
            )
        else:
            result = (
                path_index < len(path_parts)
                and fnmatch.fnmatchcase(path_parts[path_index], pattern_parts[pattern_index])
                and match_parts(pattern_index + 1, path_index + 1)
            )
        memo[key] = result
        return result

    return match_parts(0, 0)


def authenticated_gitattribute_state(
    rules: tuple[tuple[str, tuple[str, ...]], ...], relative: str
) -> dict[str, bool | str | None]:
    require(
        isinstance(relative, str)
        and relative
        and len(relative.encode("utf-8")) <= MAX_GITATTRIBUTE_PATTERN_BYTES
        and not relative.startswith("/")
        and "\\" not in relative
        and all(part not in {"", ".", ".."} for part in relative.split("/")),
        f"raw-bound path is not a canonical repository-relative path: {relative!r}",
    )
    state: dict[str, bool | str | None] = {"text": None, "eol": None}
    for pattern, attributes in rules:
        if not _gitattribute_pattern_matches(pattern, relative):
            continue
        for token in attributes:
            if token.startswith("-"):
                state[token[1:]] = False
            elif token.startswith("!"):
                state[token[1:]] = None
            elif "=" in token:
                name, value = token.split("=", 1)
                state[name] = value
            else:
                state[token] = True
    return state


def verify_bound_path_attribute_coverage(
    rules: tuple[tuple[str, tuple[str, ...]], ...], paths: Iterable[str]
) -> dict[str, str]:
    """Require each raw-bound path to have deterministic checkout byte policy."""

    coverage: dict[str, str] = {}
    for relative in sorted(set(paths)):
        state = authenticated_gitattribute_state(rules, relative)
        raw_evidence = any(
            _gitattribute_pattern_matches(pattern, relative)
            for pattern in REQUIRED_RAW_EVIDENCE_GITATTRIBUTE_RULES
        )
        required_text = (
            relative in {".gitattributes", "LICENSE"}
            or fnmatch.fnmatchcase(relative.rsplit("/", 1)[-1], "*.ps1")
        ) and not raw_evidence
        if raw_evidence:
            require(
                state.get("text") is False,
                f"raw evidence path lost its authenticated -text classification: {relative}",
            )
            coverage[relative] = "explicit--text"
            continue
        if required_text:
            require(
                state.get("text") is True and state.get("eol") == "lf",
                f"required text path lost its authenticated LF classification: {relative}",
            )
            coverage[relative] = "text-eol-lf"
            continue
        if state.get("text") is False:
            coverage[relative] = "explicit--text"
            continue
        require(
            state.get("text") is True and state.get("eol") == "lf",
            f"raw-bound path lacks authenticated deterministic checkout classification: {relative}",
        )
        coverage[relative] = "text-eol-lf"
    return coverage


def manifest_raw_bound_paths(
    manifest: dict[str, Any], contracts: dict[str, Any]
) -> tuple[str, ...]:
    bindings = manifest.get("source_bindings")
    require(isinstance(bindings, dict), "manifest source bindings missing for checkout classification")
    repository = source_rows(bindings.get("repository"), label="repository checkout classification")
    overlay = source_rows(bindings.get("overlay"), label="overlay checkout classification")
    payload = manifest.get("committed_payload_contract")
    require(isinstance(payload, dict), "committed payload missing for checkout classification")
    inventory = payload.get("payload_inventory")
    require(
        isinstance(inventory, list) and all(isinstance(path, str) for path in inventory),
        "payload inventory is malformed for checkout classification",
    )
    host = contracts.get("frozen_host_contract")
    require(isinstance(host, dict), "frozen-host contract missing for checkout classification")
    frozen = source_rows(host.get("files"), label="frozen-host checkout classification")
    paths = set(repository) | set(inventory) | set(frozen)
    paths.update(f"{OVERLAY_RELATIVE_DIRECTORY}/{relative}" for relative in overlay)
    return tuple(sorted(paths))


def verify_authenticated_checkout_reproducibility(
    raw: bytes,
    *,
    manifest: dict[str, Any],
    contracts: dict[str, Any],
) -> dict[str, str]:
    """Validate authenticated attributes and classify every raw-bound text path."""

    rules = parse_authenticated_gitattributes(raw)
    for pattern, attributes in {
        **REQUIRED_TEXT_GITATTRIBUTE_RULES,
        **REQUIRED_RAW_EVIDENCE_GITATTRIBUTE_RULES,
    }.items():
        require(
            sum(1 for rule in rules if rule == (pattern, attributes)) == 1,
            f"authenticated .gitattributes required exact rule missing: {pattern} {' '.join(attributes)}",
        )
    require(
        rules == EXPECTED_GITATTRIBUTE_RULES,
        "authenticated .gitattributes active rule set/order differs from the canonical checkout policy",
    )

    text_probes = {
        ".gitattributes": ".gitattributes",
        "LICENSE": "LICENSE",
        "*.ps1": "scripts/Invoke-PreauthorizedContinuation.ps1",
    }
    for pattern, probe in text_probes.items():
        state = authenticated_gitattribute_state(rules, probe)
        require(
            state.get("text") is True and state.get("eol") == "lf",
            f"authenticated .gitattributes required text rule is not active: {pattern}",
        )
    raw_probes = {
        "evidence/sources/**/raw/**": "evidence/sources/probe/raw/exhibit.bin",
        "evidence/live/**": "evidence/live/probe.bin",
        "evidence/benchmarks/**": "evidence/benchmarks/probe.jsonl",
        "evidence/experiments/_artifacts/**": "evidence/experiments/_artifacts/probe.json",
        "evidence/experiments/_failed/**": "evidence/experiments/_failed/probe.json",
        "evidence/local_assurance/**/logs/**": "evidence/local_assurance/probe/logs/transcript.txt",
    }
    for pattern, probe in raw_probes.items():
        state = authenticated_gitattribute_state(rules, probe)
        require(
            state.get("text") is False and state.get("diff") is False,
            f"authenticated .gitattributes raw evidence rule is not active: {pattern}",
        )
    return verify_bound_path_attribute_coverage(
        rules,
        manifest_raw_bound_paths(manifest, contracts),
    )


def verify_no_git_info_attribute_overrides(repo_root: Path) -> None:
    """Reject higher-precedence repository-local attributes before Git observes worktree bytes."""

    require(_GIT_BOUNDARY is not None, "Git execution boundary is not configured")
    require(_GIT_BOUNDARY["work_tree"] == repo_root, "Git worktree binding mismatch")
    directories = {_GIT_BOUNDARY["git_dir"], _GIT_BOUNDARY["common_dir"]}
    for directory in directories:
        path = directory / "info" / "attributes"
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise VerificationError(
                f"cannot inspect repository-local Git attributes override: {error}"
            ) from error
        raise VerificationError(
            f"repository-local Git attributes override is forbidden: {path}"
        )


def verify_no_applicable_nested_gitattributes(
    repo_root: Path, bound_paths: Iterable[str]
) -> None:
    """Reject every per-directory attributes file that can affect a bound path."""

    require(_GIT_BOUNDARY is not None, "Git execution boundary is not configured")
    require(_GIT_BOUNDARY["work_tree"] == repo_root, "Git worktree binding mismatch")
    applicable: dict[str, set[str]] = {}
    for relative in sorted(set(bound_paths)):
        # Reuse the canonical repository-path checks without consulting Git's
        # attribute engine.  The empty policy is sufficient for validation.
        authenticated_gitattribute_state((), relative)
        parts = relative.split("/")
        for depth in range(1, len(parts)):
            attribute_path = "/".join((*parts[:depth], ".gitattributes"))
            applicable.setdefault(attribute_path, set()).add(relative)

    tree_raw = git(
        repo_root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        "HEAD",
        binary=True,
    )
    index_raw = git(repo_root, "ls-files", "--stage", "-z", binary=True)
    require(
        isinstance(tree_raw, bytes) and isinstance(index_raw, bytes),
        "nested .gitattributes HEAD/index inventory is not binary",
    )
    head_attributes: set[str] = set()
    for entry in tree_raw.split(b"\0"):
        if not entry:
            continue
        header, separator, path_raw = entry.partition(b"\t")
        fields = header.split()
        path = _decode_git_path(path_raw, label="nested .gitattributes HEAD inventory")
        require(
            separator == b"\t"
            and len(fields) == 3
            and fields[0] in {b"100644", b"100755"}
            and fields[1] == b"blob"
            and re.fullmatch(rb"[0-9a-f]{40}", fields[2]) is not None,
            f"malformed HEAD entry while inspecting nested .gitattributes: {path}",
        )
        if path.endswith("/.gitattributes"):
            head_attributes.add(path)
    index_attributes: set[str] = set()
    for entry in index_raw.split(b"\0"):
        if not entry:
            continue
        header, separator, path_raw = entry.partition(b"\t")
        fields = header.split()
        path = _decode_git_path(path_raw, label="nested .gitattributes index inventory")
        require(
            separator == b"\t"
            and len(fields) == 3
            and fields[0] in {b"100644", b"100755"}
            and re.fullmatch(rb"[0-9a-f]{40}", fields[1]) is not None
            and fields[2] == b"0",
            f"malformed index entry while inspecting nested .gitattributes: {path}",
        )
        if path.endswith("/.gitattributes"):
            index_attributes.add(path)

    for relative in sorted((head_attributes | index_attributes) & set(applicable)):
        first_affected = sorted(applicable[relative])[0]
        raise VerificationError(
            "applicable nested .gitattributes is forbidden for raw-bound path: "
            f"{relative} -> {first_affected}"
        )

    for relative, affected_paths in sorted(applicable.items()):
        candidate = repo_root.joinpath(*relative.split("/"))
        try:
            os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise VerificationError(
                f"cannot inspect applicable nested .gitattributes {relative}: {error}"
            ) from error
        first_affected = sorted(affected_paths)[0]
        raise VerificationError(
            "applicable nested .gitattributes is forbidden for raw-bound path: "
            f"{relative} -> {first_affected}"
        )


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


def verify_authoring_overlay_matches_checkout(
    *,
    repo_root: Path,
    overlay_dir: Path,
    manifest_raw: bytes,
    payload_sources: dict[str, bytes],
    verified_sources: dict[str, bytes],
    plan_raw: bytes,
) -> None:
    """Bind an alternate authoring overlay to the exact eleven-path checkout state."""

    prefix = OVERLAY_RELATIVE_DIRECTORY + "/"
    for relative in EXPECTED_PAYLOAD_PATHS:
        candidate_raw = (
            manifest_raw
            if relative == MANIFEST_RELATIVE_PATH
            else payload_sources[relative]
        )
        if relative.startswith(prefix):
            local_name = relative[len(prefix) :]
            current_overlay_raw = read_bounded_bytes(
                safe_child(overlay_dir, local_name, label="current authoring overlay member"),
                label=f"current authoring overlay member {relative}",
                size_limit=MAX_TRACKED_FILE_BYTES,
            )
            require(
                current_overlay_raw == candidate_raw,
                f"authoring alternate overlay changed after authentication: {relative}",
            )
        checkout_raw = read_bounded_bytes(
            safe_child(repo_root, relative, label="authoring checkout payload member"),
            label=f"authoring checkout payload member {relative}",
            size_limit=MAX_TRACKED_FILE_BYTES,
        )
        require(
            checkout_raw == candidate_raw,
            f"authoring alternate overlay bytes differ from the checkout: {relative}",
        )

    for local_name in (*EXPECTED_OVERLAY_SOURCES, "verify_plan.py"):
        relative = prefix + local_name
        require(
            verified_sources[f"overlay:{local_name}"] == payload_sources[relative],
            f"authoring overlay source changed between authenticated reads: {relative}",
        )
    require(
        plan_raw == payload_sources[prefix + "plan.json"],
        "authoring plan changed between authenticated reads",
    )


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
        parent_entry = str(
            git(repo_root, "ls-tree", CORRECTION_PARENT_COMMIT, "--", relative)
        )
        parent_raw = (
            git(
                repo_root,
                "cat-file",
                "blob",
                f"{CORRECTION_PARENT_COMMIT}:{relative}",
                binary=True,
            )
            if parent_entry
            else None
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
        if relative in EXPECTED_ADDED_PATHS:
            require(
                parent_raw is None,
                f"required added payload path already exists in the predecessor correction: {relative}",
            )
        elif relative in changed_paths:
            require(parent_raw is not None, f"changed predecessor payload is missing: {relative}")
            require(head_raw != parent_raw, f"successor path did not change from the predecessor correction: {relative}")
        else:
            require(parent_raw is not None, f"inherited predecessor payload is missing: {relative}")
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


def verify_index_matches_head(repo_root: Path) -> str:
    """Require the complete stage-zero index mode/blob inventory to equal HEAD."""

    tree_raw = git(repo_root, "ls-tree", "-r", "-z", "--full-tree", "HEAD", binary=True)
    index_raw = git(repo_root, "ls-files", "--stage", "-z", binary=True)
    require(isinstance(tree_raw, bytes) and isinstance(index_raw, bytes), "authoring index inventory is not binary")

    tree_entries: dict[str, tuple[str, str]] = {}
    for entry in tree_raw.split(b"\0"):
        if not entry:
            continue
        header, separator, path_raw = entry.partition(b"\t")
        fields = header.split()
        path = _decode_git_path(path_raw, label="authoring HEAD tree")
        require(
            separator == b"\t"
            and len(fields) == 3
            and fields[0] in {b"100644", b"100755"}
            and fields[1] == b"blob"
            and re.fullmatch(rb"[0-9a-f]{40}", fields[2]) is not None
            and path not in tree_entries,
            f"unsupported or malformed authoring HEAD tree entry: {path}",
        )
        tree_entries[path] = (fields[0].decode("ascii"), fields[2].decode("ascii"))

    index_entries: dict[str, tuple[str, str]] = {}
    for entry in index_raw.split(b"\0"):
        if not entry:
            continue
        header, separator, path_raw = entry.partition(b"\t")
        fields = header.split()
        path = _decode_git_path(path_raw, label="authoring index")
        require(
            separator == b"\t"
            and len(fields) == 3
            and fields[0] in {b"100644", b"100755"}
            and re.fullmatch(rb"[0-9a-f]{40}", fields[1]) is not None
            and fields[2] == b"0"
            and path not in index_entries,
            f"unsupported or malformed authoring index entry: {path}",
        )
        index_entries[path] = (fields[0].decode("ascii"), fields[1].decode("ascii"))

    require(index_entries == tree_entries, "authoring Git index differs from the exact HEAD tree")
    inventory = [[path, mode, blob] for path, (mode, blob) in sorted(index_entries.items())]
    return digest(inventory)


def snapshot_tracked_index_and_worktree(
    repo_root: Path,
    *,
    index_mismatch_message: str = "Git index differs from the exact HEAD tree",
) -> tuple[int, str, str, tuple[str, ...]]:
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

    require(index_entries == tree_entries, index_mismatch_message)
    changed_paths: list[str] = []
    worktree_inventory: list[list[str]] = []
    for relative, (_, blob_sha) in sorted(tree_entries.items()):
        path = safe_child(repo_root, relative, label="tracked worktree")
        require(path.is_file() and not path.is_symlink(), f"tracked worktree path is not a regular file: {relative}")
        raw = read_bounded_bytes(
            path,
            label=f"tracked worktree {relative}",
            size_limit=MAX_TRACKED_FILE_BYTES,
        )
        observed_blob = git_blob_sha(raw)
        if observed_blob != blob_sha:
            changed_paths.append(relative)
        worktree_inventory.append([relative, sha256_bytes(raw)])
    inventory = [[path, mode, blob] for path, (mode, blob) in sorted(tree_entries.items())]
    return (
        len(tree_entries),
        digest(inventory),
        digest(worktree_inventory),
        tuple(changed_paths),
    )


def verify_tracked_index_and_worktree(repo_root: Path) -> tuple[int, str]:
    tracked_count, inventory_digest, _, changed_paths = snapshot_tracked_index_and_worktree(
        repo_root
    )
    if changed_paths:
        raise VerificationError(
            f"tracked worktree bytes differ from HEAD: {changed_paths[0]}"
        )
    return tracked_count, inventory_digest


def verify_untracked_and_ignored_state(
    repo_root: Path, *, allowed_paths: set[str] | None = None
) -> str:
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
    allowed = {ALLOWED_UNTRACKED_PATH} if allowed_paths is None else allowed_paths
    require(
        observed_paths <= allowed,
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


def verify_authoring_checkout_boundary(repo_root: Path) -> dict[str, Any]:
    (
        tracked_count,
        index_matches_head_digest,
        worktree_bytes_digest,
        changed,
    ) = snapshot_tracked_index_and_worktree(
        repo_root,
        index_mismatch_message="authoring Git index differs from the exact HEAD tree",
    )
    expected_modified = tuple(
        relative
        for relative in EXPECTED_CHANGED_PATHS
        if relative not in EXPECTED_ADDED_PATHS
    )
    require(
        changed == expected_modified,
        "authoring check requires exactly the seven modified V5 paths against HEAD",
    )
    return {
        "changed_paths": changed,
        "tracked_path_count": tracked_count,
        "index_matches_head_digest": index_matches_head_digest,
        "worktree_bytes_digest": worktree_bytes_digest,
        "index_visibility_digest": verify_global_index_visibility(repo_root),
        "untracked_and_ignored_digest": verify_untracked_and_ignored_state(
            repo_root,
            allowed_paths={ALLOWED_UNTRACKED_PATH, *EXPECTED_ADDED_PATHS},
        ),
    }


def verify_repository_state(
    repo_root: Path, overlay_dir: Path, *, authoring_check: bool
) -> dict[str, Any]:
    require(_GIT_BOUNDARY is not None, "Git execution boundary is not configured")
    require(
        _GIT_BOUNDARY["work_tree"] == repo_root
        and _GIT_BOUNDARY["git_dir"] == _resolve_git_dir(repo_root),
        "explicit Git-dir/work-tree repository binding mismatch",
    )
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
        commit=GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
        tree=GIT_ENVIRONMENT_CORRECTION_PARENT_TREE,
        parent=PAYLOAD_A_COMMIT,
        label="remanded Git-environment correction parent",
    )
    verify_commit_object(
        repo_root,
        commit=GIT_BOUNDARY_CORRECTION_COMMIT,
        tree=GIT_BOUNDARY_CORRECTION_TREE,
        parent=GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
        label="remanded native-executable-matrix correction parent",
    )
    verify_commit_object(
        repo_root,
        commit=CORRECTION_PARENT_COMMIT,
        tree=CORRECTION_PARENT_TREE,
        parent=CORRECTION_PARENT_PARENT_COMMIT,
        label="published V4 correction parent",
    )
    git(
        repo_root,
        "merge-base",
        "--is-ancestor",
        GIT_BOUNDARY_CORRECTION_COMMIT,
        CORRECTION_PARENT_COMMIT,
    )
    require(git(repo_root, "branch", "--show-current") == TARGET_BRANCH, "live branch mismatch")
    head = str(git(repo_root, "rev-parse", "HEAD"))
    tree = str(git(repo_root, "rev-parse", "HEAD^{tree}"))
    if authoring_check:
        require(head == CORRECTION_PARENT_COMMIT, "authoring check requires the immutable correction parent HEAD")
        require(tree == CORRECTION_PARENT_TREE, "authoring check requires the immutable correction parent tree")
        authoring_snapshot = verify_authoring_checkout_boundary(repo_root)
        return {
            "mode": "authoring-squash-proof-windows-identity-correction-v5-non-executing",
            "qualification": False,
            "head": head,
            "tree": tree,
            "authoring_base_parent": PLAN_AUTHORING_BASE_COMMIT,
            "git_environment_correction_parent": GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
            "correction_parent": CORRECTION_PARENT_COMMIT,
            "authoring_snapshot": authoring_snapshot,
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
        "mode": "committed-squash-proof-windows-identity-correction-v5",
        "qualification": True,
        "head": head,
        "tree": tree,
        "authoring_base_parent": PLAN_AUTHORING_BASE_COMMIT,
        "git_environment_correction_parent": GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
        "correction_parent": CORRECTION_PARENT_COMMIT,
        "checkout_snapshot": checkout_snapshot,
    }


def verify_repository_state_stable_at_end(
    repo_root: Path,
    overlay_dir: Path,
    repository_state: dict[str, Any],
    *,
    raw_bound_paths: Iterable[str],
) -> None:
    verify_no_git_info_attribute_overrides(repo_root)
    verify_no_applicable_nested_gitattributes(repo_root, raw_bound_paths)
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
        commit=GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
        tree=GIT_ENVIRONMENT_CORRECTION_PARENT_TREE,
        parent=PAYLOAD_A_COMMIT,
        label="final remanded Git-environment correction parent",
    )
    verify_commit_object(
        repo_root,
        commit=GIT_BOUNDARY_CORRECTION_COMMIT,
        tree=GIT_BOUNDARY_CORRECTION_TREE,
        parent=GIT_ENVIRONMENT_CORRECTION_PARENT_COMMIT,
        label="final remanded native-executable-matrix correction parent",
    )
    verify_commit_object(
        repo_root,
        commit=CORRECTION_PARENT_COMMIT,
        tree=CORRECTION_PARENT_TREE,
        parent=CORRECTION_PARENT_PARENT_COMMIT,
        label="final published V4 correction parent",
    )
    git(
        repo_root,
        "merge-base",
        "--is-ancestor",
        GIT_BOUNDARY_CORRECTION_COMMIT,
        CORRECTION_PARENT_COMMIT,
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
    else:
        require(
            verify_authoring_checkout_boundary(repo_root)
            == repository_state["authoring_snapshot"],
            "authoring checkout boundary changed during verification",
        )
    verify_no_git_info_attribute_overrides(repo_root)
    verify_no_applicable_nested_gitattributes(repo_root, raw_bound_paths)


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


def _decode_json_pointer_token(token: str, *, label: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        require(
            index + 1 < len(token) and token[index + 1] in {"0", "1"},
            f"{label} contains an invalid JSON Pointer escape",
        )
        decoded.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def resolve_local_json_pointer(
    reference: object,
    *,
    document_name: str,
    document: object,
    label: str,
) -> object:
    """Strictly resolve a local document reference with RFC 6901 token escaping."""

    require(isinstance(reference, str), f"{label} must be a string")
    prefix = f"{document_name}#"
    require(
        reference.startswith(prefix) and reference.count("#") == 1,
        f"{label} must reference the exact local document {document_name}",
    )
    pointer = reference[len(prefix) :]
    require(pointer == "" or pointer.startswith("/"), f"{label} JSON Pointer is malformed")
    current = document
    if pointer == "":
        return current
    for raw_token in pointer[1:].split("/"):
        token = _decode_json_pointer_token(raw_token, label=label)
        if isinstance(current, dict):
            require(token in current, f"{label} JSON Pointer member does not exist: {token}")
            current = current[token]
            continue
        if isinstance(current, list):
            require(
                re.fullmatch(r"(?:0|[1-9][0-9]*)", token) is not None,
                f"{label} JSON Pointer array index is not canonical: {token}",
            )
            item_index = int(token)
            require(item_index < len(current), f"{label} JSON Pointer array index is out of range")
            current = current[item_index]
            continue
        raise VerificationError(f"{label} JSON Pointer traverses a scalar value")
    return current


def verify_frozen_host(
    manifest: dict[str, Any], contracts: dict[str, Any], repo_root: Path
) -> None:
    prerequisite = manifest.get("frozen_host_prerequisite")
    require(isinstance(prerequisite, dict), "frozen host prerequisite missing")
    host = contracts.get("frozen_host_contract")
    require(isinstance(host, dict), "frozen host contract missing")
    require(
        host.get("extraction_commit")
        == prerequisite.get("extraction_commit")
        == QUALIFIED_PREREQUISITE_COMMIT,
        "host extraction commit mismatch",
    )
    require(
        host.get("extraction_tree")
        == prerequisite.get("extraction_tree")
        == QUALIFIED_PREREQUISITE_TREE,
        "host extraction tree mismatch",
    )
    files = host.get("files")
    pointed_files = resolve_local_json_pointer(
        prerequisite.get("manifest_location"),
        document_name="node-contracts.json",
        document=contracts,
        label="frozen host manifest location",
    )
    require(
        pointed_files is files,
        "frozen host manifest location does not resolve to the host files array",
    )
    require(
        isinstance(files, list)
        and len(files)
        == host.get("file_count")
        == prerequisite.get("file_count")
        == 16,
        "host manifest must contain the bound 16 files",
    )
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
    require(
        digest(observed_bundle)
        == host.get("bundle_digest")
        == prerequisite.get("bundle_sha256")
        == EXPECTED_FROZEN_HOST_BUNDLE,
        "host bundle digest mismatch",
    )
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

    # Trust order is intentional: authenticate the manifest and complete payload
    # bytes first, then interpret only the payload-bound checkout policy before
    # any Git command can observe worktree bytes.  Full source authentication and
    # all authored-data interpretation remain downstream of that boundary.
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
    payload_sources = verify_payload_bindings(
        manifest,
        repo_root=repo_root,
        overlay_dir=overlay_dir,
        manifest_raw=manifest_raw,
    )
    contracts = parse_strict_json(
        payload_sources[
            f"{OVERLAY_RELATIVE_DIRECTORY}/node-contracts.json"
        ],
        label="payload-bound node-contracts.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    checkout_attribute_coverage = verify_authenticated_checkout_reproducibility(
        payload_sources[".gitattributes"],
        manifest=manifest,
        contracts=contracts,
    )
    verify_no_git_info_attribute_overrides(repo_root)
    raw_bound_paths = tuple(checkout_attribute_coverage)
    verify_no_applicable_nested_gitattributes(repo_root, raw_bound_paths)
    repository_state = verify_repository_state(
        repo_root, overlay_dir, authoring_check=authoring_check
    )
    verified_sources = verify_manifest_declared_sources(
        manifest, overlay_dir=overlay_dir, repo_root=repo_root
    )

    intake = parse_strict_json(
        verified_sources["repository:docs/execution/dags/generic-hive-mind-product-v3/source-intake.json"],
        label="source-intake.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    verified_contracts = parse_strict_json(
        verified_sources["overlay:node-contracts.json"],
        label="node-contracts.json",
        size_limit=MAX_SOURCE_JSON_BYTES,
    )
    require(
        verified_contracts == contracts,
        "node-contracts changed between payload and source authentication",
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
    verify_frozen_host(manifest, contracts, repo_root)

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

    if authoring_check:
        verify_authoring_overlay_matches_checkout(
            repo_root=repo_root,
            overlay_dir=overlay_dir,
            manifest_raw=manifest_raw,
            payload_sources=payload_sources,
            verified_sources=verified_sources,
            plan_raw=plan_raw,
        )

    sealed_after = read_bounded_bytes(
        sealed_plan_path,
        label="historical sealed plan after verification",
        size_limit=MAX_PLAN_BYTES,
    )
    require(sealed_after == sealed_before, "verifier mutated .autopilot/plan.json")
    require(sha256_bytes(sealed_after) == EXPECTED_REPOSITORY_SOURCES[".autopilot/plan.json"][1], "historical sealed plan changed")
    verify_repository_state_stable_at_end(
        repo_root,
        overlay_dir,
        repository_state,
        raw_bound_paths=raw_bound_paths,
    )
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
            "git_environment_correction_parent": repository_state[
                "git_environment_correction_parent"
            ],
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
            "policy": GIT_EXECUTION_BOUNDARY_POLICY,
            "executable": str(_GIT_BOUNDARY["executable"]),
            "executable_sha256": _GIT_BOUNDARY["expected_sha256"],
            "native_executable_format_policy": NATIVE_EXECUTABLE_FORMAT_POLICY,
            "native_executable_format": _GIT_BOUNDARY["native_image"][
                "native_executable_format"
            ],
            "host_platform": _GIT_BOUNDARY["native_image"]["host_platform"],
            "host_machine": _GIT_BOUNDARY["native_image"]["host_machine"],
            "max_executable_bytes": MAX_NATIVE_EXECUTABLE_BYTES,
            "compiled_native_delegator_exclusion": "NOT_PROVEN_BY_FORMAT",
            "runtime_dependency_closure": "REQUIRED_FOR_EXECUTION_NOT_SATISFIED",
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
    result: dict[str, Any] | None = None
    primary_error: VerificationError | None = None
    cleanup_errors: list[VerificationError] = []
    autopilot_before: dict[str, Any] | None = None
    resolved_repo_root: Path | None = None
    try:
        overlay_dir = overlay_dir.resolve()
        repo_root = repo_root.resolve()
        resolved_repo_root = repo_root
        autopilot_before = snapshot_autopilot_tree(repo_root)
        configure_git_boundary(
            repo_root,
            git_executable=git_executable,
            expected_git_executable_sha256=expected_git_executable_sha256,
        )
        result = _verify_configured(
            expected_manifest_digest=expected_manifest_digest,
            overlay_dir=overlay_dir,
            repo_root=repo_root,
            authoring_check=authoring_check,
        )
    except VerificationError as error:
        primary_error = error
    except subprocess.TimeoutExpired as error:
        primary_error = GitTimeoutError(
            f"unhandled subprocess timeout was normalized at the verifier boundary: {error}"
        )
    except OSError as error:
        primary_error = VerificationError(
            f"operating-system error was normalized at the verifier boundary: {error}"
        )
    except Exception as error:
        primary_error = VerificationError(
            f"unexpected verifier failure {type(error).__name__}: {error}"
        )
    finally:
        boundary = _GIT_BOUNDARY
        if boundary is not None:
            try:
                verify_git_executable_stable(full_digest=True)
            except VerificationError as error:
                cleanup_errors.append(error)
            try:
                boundary["handle"].close()
            except (OSError, ValueError) as error:
                cleanup_errors.append(
                    VerificationError(f"cannot close retained Git executable handle: {error}")
                )
        _GIT_BOUNDARY = None
        if resolved_repo_root is not None and autopilot_before is not None:
            try:
                autopilot_after = snapshot_autopilot_tree(resolved_repo_root)
                if autopilot_after != autopilot_before:
                    cleanup_errors.append(
                        VerificationError(
                            "initial and final .autopilot point observations differ during verification"
                        )
                    )
            except VerificationError as error:
                cleanup_errors.append(error)
            except OSError as error:
                cleanup_errors.append(
                    VerificationError(f"cannot complete final .autopilot point observation: {error}")
                )
    if primary_error is not None:
        for cleanup_error in cleanup_errors:
            primary_error.add_cleanup_evidence(cleanup_error)
        raise primary_error
    if cleanup_errors:
        cleanup_error = cleanup_errors[0]
        for additional_error in cleanup_errors[1:]:
            cleanup_error.add_cleanup_evidence(additional_error)
        raise cleanup_error
    require(result is not None, "verifier returned no result")
    require(autopilot_before is not None, "initial .autopilot point observation was not captured")
    result["autopilot_tree"] = {
        "observed_unchanged": True,
        "concurrent_mutation_exclusion": False,
        "requires_external_read_only_custody_for_execution": True,
        "schema": autopilot_before["schema"],
        "entry_count": autopilot_before["entry_count"],
        "total_file_bytes": autopilot_before["total_file_bytes"],
        "snapshot_digest": autopilot_before["digest"],
    }
    return result


def verification_error_payload(error: VerificationError) -> dict[str, Any]:
    return {
        "verified": False,
        "code": error.code,
        "error_type": type(error).__name__,
        "primary_code": error.primary_code,
        "cleanup_evidence": list(error.cleanup_evidence),
        "error": str(error),
    }


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
        print(json.dumps(verification_error_payload(error), sort_keys=True))
        raise SystemExit(2) from None
