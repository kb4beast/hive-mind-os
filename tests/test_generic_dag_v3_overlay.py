"""Adversarial checks for the inert Generic Hive Mind V3 execution overlay."""

from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
HISTORY_BUNDLE = ROOT / "tests" / "fixtures" / "generic-v3-history.bundle"
HISTORY_BUNDLE_PROVENANCE = ROOT / "tests" / "fixtures" / "generic-v3-history.provenance.json"
HISTORY_BUNDLE_SHA256 = "2de9a9db506e8561d21b86f7887c9030868337862ae755074d447f19dfcd2ae7"
HISTORY_BUNDLE_REF = "refs/heads/release/hive-mind-autopilot"
HISTORY_EVIDENCE_REF = "refs/hive-mind-evidence/generic-v3-history"
PLAN_AUTHORING_BASE = "42b4aeef17f816430a7d8a435102635afea8761a"
PAYLOAD_A = "4e2b81b932e5145f24c4b52ceeee664bff91df2e"
GIT_ENVIRONMENT_CORRECTION_PARENT = "f06e52c43a1e2d1d53523378c0d6f5564fb984bf"
GIT_BOUNDARY_CORRECTION_PARENT = "9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8"
CORRECTION_PARENT = "28463ae6dd842b0b316fcf99eab98804cdaf9735"
CORRECTION_PARENT_TREE = "72696b27cdd2c9cd08085c05c98513ece733cc8d"
CORRECTION_PARENT_PARENT = "9dfa1823edc9cd56cd1f404606a261a1d623f6cb"
CORRECTION_PARENT_PARENT_TREE = "7e8becaebef2ca88922c9099ae1e497f978f43f1"
CORRECTION_PARENT_MANIFEST_SHA256 = "sha256:c2f0ae0dcee177213f219eaa3031b45d6f5526fd1f2d98d73b11672068f81377"
CORRECTION_PARENT_AGGREGATE_SHA256 = "sha256:ecbeb374fc8adbb711391568d8a2f2fa8b0ef022c233ca932f24bd9ab0b4fb23"
CORRECTION_PARENT_REPORT_SHA256 = "sha256:1ac71b791a36f5c2e543039d89604123a9b8f744e022bab23f549d481e472944"
CORRECTION_PARENT_STATUS = "PUBLISHED_TREE_WITH_SQUASH_SEVERED_HISTORY_AND_RED_CONSTITUTIONAL_CI"
V5_MANIFEST_KIND = "hive-mind-generic-product-overlay-manifest-v5"
V5_CONTRACT_MODE = "exact-append-only-squash-proof-windows-identity-correction-v5"
V5_AUTHORING_MODE = "authoring-squash-proof-windows-identity-correction-v5-non-executing"
V5_COMMITTED_MODE = "committed-squash-proof-windows-identity-correction-v5"
TARGET_BRANCH = "release/hive-mind-autopilot"
PAYLOAD_PATHS = (
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
CORRECTION_PATHS = (
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
ADDED_CORRECTION_PATHS = (
    "docs/architecture/ADR-070-GENERIC-V3-BASELINE-RECOVERY.md",
    "docs/architecture/ADR-071-PORTABLE-DAG-RUNTIME-AND-EXTERNAL-ACTIVATION.md",
    "tests/fixtures/generic-v3-history.bundle",
    "tests/fixtures/generic-v3-history.provenance.json",
)

WINDOWS_ERROR_HANDLE_EOF = 38
WINDOWS_ERROR_INVALID_PARAMETER = 87
WINDOWS_FILE_ATTRIBUTE_HIDDEN = 0x00000002
WINDOWS_FILE_ATTRIBUTE_SYSTEM = 0x00000004
WINDOWS_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


class WindowsStreamEnumerationUnsupported(RuntimeError):
    """The current Windows filesystem does not implement stream enumeration."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            "FindFirstStreamW does not support the filesystem for "
            f"{path} (ERROR_INVALID_PARAMETER={WINDOWS_ERROR_INVALID_PARAMETER})"
        )
        self.winerror = WINDOWS_ERROR_INVALID_PARAMETER


if os.name == "nt":
    class _Win32FindStreamData(ctypes.Structure):
        _fields_ = [
            ("StreamSize", ctypes.c_longlong),
            ("cStreamName", ctypes.c_wchar * 296),
        ]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _GET_FILE_ATTRIBUTES = _KERNEL32.GetFileAttributesW
    _GET_FILE_ATTRIBUTES.argtypes = [wintypes.LPCWSTR]
    _GET_FILE_ATTRIBUTES.restype = wintypes.DWORD
    _SET_FILE_ATTRIBUTES = _KERNEL32.SetFileAttributesW
    _SET_FILE_ATTRIBUTES.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _SET_FILE_ATTRIBUTES.restype = wintypes.BOOL
    _FIND_FIRST_STREAM = _KERNEL32.FindFirstStreamW
    _FIND_FIRST_STREAM.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(_Win32FindStreamData),
        wintypes.DWORD,
    ]
    _FIND_FIRST_STREAM.restype = wintypes.HANDLE
    _FIND_NEXT_STREAM = _KERNEL32.FindNextStreamW
    _FIND_NEXT_STREAM.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_Win32FindStreamData),
    ]
    _FIND_NEXT_STREAM.restype = wintypes.BOOL
    _FIND_CLOSE = _KERNEL32.FindClose
    _FIND_CLOSE.argtypes = [wintypes.HANDLE]
    _FIND_CLOSE.restype = wintypes.BOOL
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
else:
    _GET_FILE_ATTRIBUTES = None
    _SET_FILE_ATTRIBUTES = None
    _FIND_FIRST_STREAM = None
    _FIND_NEXT_STREAM = None
    _FIND_CLOSE = None
    _INVALID_HANDLE_VALUE = None


def canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def raw_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shell_command(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def windows_file_attributes(path: Path) -> int:
    if os.name != "nt":
        raise RuntimeError("Win32 file attributes are available only on Windows")
    assert _GET_FILE_ATTRIBUTES is not None
    ctypes.set_last_error(0)
    attributes = int(_GET_FILE_ATTRIBUTES(str(path)))
    if attributes == WINDOWS_INVALID_FILE_ATTRIBUTES:
        raise ctypes.WinError(ctypes.get_last_error())
    return attributes


def set_windows_file_attributes(path: Path, attributes: int) -> None:
    if os.name != "nt":
        raise RuntimeError("Win32 file attributes are available only on Windows")
    assert _SET_FILE_ATTRIBUTES is not None
    ctypes.set_last_error(0)
    if not _SET_FILE_ATTRIBUTES(str(path), attributes):
        raise ctypes.WinError(ctypes.get_last_error())


def windows_stream_snapshot(
    path: Path,
    *,
    include_unnamed: bool = False,
) -> tuple[tuple[str, int, str], ...]:
    """Enumerate data streams through Win32 and independently hash their bytes."""

    if os.name != "nt":
        raise RuntimeError("Win32 stream enumeration is available only on Windows")
    assert _FIND_FIRST_STREAM is not None
    assert _FIND_NEXT_STREAM is not None
    assert _FIND_CLOSE is not None
    data = _Win32FindStreamData()
    ctypes.set_last_error(0)
    handle = _FIND_FIRST_STREAM(str(path), 0, ctypes.byref(data), 0)
    if handle == _INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error == WINDOWS_ERROR_HANDLE_EOF:
            return ()
        if error == WINDOWS_ERROR_INVALID_PARAMETER:
            raise WindowsStreamEnumerationUnsupported(path)
        raise ctypes.WinError(error)

    rows: list[tuple[str, int, str]] = []
    try:
        while True:
            stream_name = str(data.cStreamName)
            stream_size = int(data.StreamSize)
            if stream_size < 0:
                raise AssertionError(
                    f"negative Win32 stream size for {path}{stream_name}: {stream_size}"
                )
            if stream_name != "::$DATA" or include_unnamed:
                stream_path = path if stream_name == "::$DATA" else Path(f"{path}{stream_name}")
                raw = stream_path.read_bytes()
                if len(raw) != stream_size:
                    raise AssertionError(
                        f"Win32 stream size changed while reading {path}{stream_name}: "
                        f"declared={stream_size} observed={len(raw)}"
                    )
                rows.append(
                    (stream_name, stream_size, hashlib.sha256(raw).hexdigest())
                )
            ctypes.set_last_error(0)
            if _FIND_NEXT_STREAM(handle, ctypes.byref(data)):
                continue
            error = ctypes.get_last_error()
            if error == WINDOWS_ERROR_HANDLE_EOF:
                break
            if error == WINDOWS_ERROR_INVALID_PARAMETER:
                raise WindowsStreamEnumerationUnsupported(path)
            raise ctypes.WinError(error)
    finally:
        ctypes.set_last_error(0)
        if not _FIND_CLOSE(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    return tuple(sorted(rows))


def optional_filesystem_snapshot(path: Path, state: os.stat_result) -> tuple[object, ...]:
    optional_stat_fields = tuple(
        (field, int(getattr(state, field)))
        for field in (
            "st_birthtime_ns",
            "st_file_attributes",
            "st_reparse_tag",
        )
        if hasattr(state, field)
    )
    if os.name != "nt":
        return (optional_stat_fields, None, ())
    attributes = windows_file_attributes(path)
    if stat.S_ISLNK(state.st_mode) or getattr(state, "st_reparse_tag", 0):
        streams: tuple[object, ...] = ()
    else:
        try:
            streams = windows_stream_snapshot(path)
        except WindowsStreamEnumerationUnsupported as error:
            streams = (("stream-enumeration-unsupported", error.winerror),)
    return (optional_stat_fields, attributes, streams)


def python_bytecode_inventory(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if (path.is_dir() and path.name == "__pycache__")
            or (path.is_file() and path.suffix.casefold() == ".pyc")
        )
    )


def complete_tree_snapshot(root: Path) -> tuple[tuple[object, ...], ...]:
    """Capture every directory, regular file byte digest, and symlink target."""

    root_state = root.lstat()
    root_metadata = (
        root_state.st_dev,
        root_state.st_ino,
        root_state.st_size,
        root_state.st_mtime_ns,
        root_state.st_ctime_ns,
    )
    rows: list[tuple[object, ...]] = [
        (
            ".",
            "directory",
            stat.S_IMODE(root_state.st_mode),
            root_metadata,
            optional_filesystem_snapshot(root, root_state),
        )
    ]
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        state = path.lstat()
        mode = stat.S_IMODE(state.st_mode)
        metadata = (
            state.st_dev,
            state.st_ino,
            state.st_size,
            state.st_mtime_ns,
            state.st_ctime_ns,
        )
        optional_metadata = optional_filesystem_snapshot(path, state)
        if stat.S_ISLNK(state.st_mode):
            rows.append(
                (
                    relative,
                    "symlink",
                    mode,
                    metadata,
                    optional_metadata,
                    os.readlink(path),
                )
            )
        elif stat.S_ISDIR(state.st_mode):
            rows.append((relative, "directory", mode, metadata, optional_metadata))
        elif stat.S_ISREG(state.st_mode):
            raw = path.read_bytes()
            rows.append(
                (
                    relative,
                    "file",
                    mode,
                    metadata,
                    optional_metadata,
                    len(raw),
                    hashlib.sha256(raw).hexdigest(),
                )
            )
        else:
            rows.append((relative, "other", mode, metadata, optional_metadata))
    return tuple(rows)


def synthetic_pe_x86() -> bytes:
    pe_offset = 0x80
    optional_size = 96
    optional_offset = pe_offset + 24
    section_offset = optional_offset + optional_size
    size_of_headers = 0x200
    raw_pointer = 0x200
    raw_size = 0x200
    raw = bytearray(raw_pointer + raw_size)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, pe_offset)
    raw[pe_offset : pe_offset + 4] = b"PE\0\0"
    struct.pack_into(
        "<HHIIIHH",
        raw,
        pe_offset + 4,
        0x014C,
        1,
        0,
        0,
        0,
        optional_size,
        0x0002,
    )
    struct.pack_into("<H", raw, optional_offset, 0x010B)
    struct.pack_into("<I", raw, optional_offset + 16, 0x1000)
    struct.pack_into("<I", raw, optional_offset + 56, 0x2000)
    struct.pack_into("<I", raw, optional_offset + 60, size_of_headers)
    raw[section_offset : section_offset + 8] = b".text\0\0\0"
    struct.pack_into("<I", raw, section_offset + 8, 0x100)
    struct.pack_into("<I", raw, section_offset + 12, 0x1000)
    struct.pack_into("<I", raw, section_offset + 16, raw_size)
    struct.pack_into("<I", raw, section_offset + 20, raw_pointer)
    struct.pack_into("<I", raw, section_offset + 36, 0x60000020)
    raw[raw_pointer] = 0xC3
    return bytes(raw)


def synthetic_elf_x86_64() -> bytes:
    load_offset = 0x1000
    load_size = 0x100
    load_address = 0x401000
    raw = bytearray(load_offset + load_size)
    raw[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", raw, 16, 2, 62, 1)
    struct.pack_into("<Q", raw, 24, load_address + 8)
    struct.pack_into("<Q", raw, 32, 64)
    struct.pack_into("<HHH", raw, 52, 64, 56, 1)
    struct.pack_into("<II", raw, 64, 1, 0x5)
    struct.pack_into("<QQ", raw, 72, load_offset, load_address)
    struct.pack_into("<Q", raw, 88, load_address)
    struct.pack_into("<QQQ", raw, 96, load_size, load_size, 0x1000)
    raw[load_offset + 8] = 0xC3
    return bytes(raw)


def synthetic_macho_x86_64() -> bytes:
    raw = bytearray(0x100)
    raw[:4] = b"\xcf\xfa\xed\xfe"
    struct.pack_into("<IIIII", raw, 4, 0x01000007, 3, 2, 2, 96)
    struct.pack_into("<II", raw, 32, 0x19, 72)
    raw[40:56] = b"__TEXT\0\0\0\0\0\0\0\0\0\0"
    struct.pack_into("<Q", raw, 56, 0x100000000)
    struct.pack_into("<Q", raw, 64, 0x1000)
    struct.pack_into("<Q", raw, 72, 0)
    struct.pack_into("<Q", raw, 80, len(raw))
    struct.pack_into("<II", raw, 88, 0x7, 0x5)
    struct.pack_into("<II", raw, 104, 0x80000028, 24)
    struct.pack_into("<QQ", raw, 112, 0x80, 0)
    raw[0x80] = 0xC3
    return bytes(raw)


def synthetic_macho_fat_x86_64() -> bytes:
    thin = synthetic_macho_x86_64()
    slice_offset = 0x1000
    raw = bytearray(slice_offset + len(thin))
    raw[:4] = b"\xca\xfe\xba\xbe"
    struct.pack_into(">I", raw, 4, 1)
    struct.pack_into(
        ">IIIII",
        raw,
        8,
        0x01000007,
        3,
        slice_offset,
        len(thin),
        12,
    )
    raw[slice_offset : slice_offset + len(thin)] = thin
    return bytes(raw)


class FakeProcess:
    def __init__(
        self,
        output: bytes = b"",
        *,
        returncode: int = 0,
        wait_action=None,
    ) -> None:
        self.stdout = io.BytesIO(output)
        self.returncode = returncode
        self.wait_action = wait_action
        self.wait_calls = 0
        self.wait_completed = False
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.wait_action is not None:
            self.wait_action(self, timeout, self.wait_calls)
        self.wait_completed = True
        return self.returncode

    def kill(self) -> None:
        self.killed = True

    def poll(self) -> int | None:
        return self.returncode if self.wait_completed else None


class DeferredThread:
    """Run a Git-output target during join, strictly after process.wait."""

    def __init__(self, target, before_target) -> None:
        self.target = target
        self.before_target = before_target
        self.started = False
        self.finished = False

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        del timeout
        if self.started and not self.finished:
            self.before_target()
            self.target()
            self.finished = True

    def is_alive(self) -> bool:
        return self.started and not self.finished


class GenericDagV3OverlayTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        discovered_git = shutil.which("git")
        if discovered_git is None:
            raise unittest.SkipTest("Git executable is unavailable")
        git_executable = Path(discovered_git).resolve()
        if os.name == "nt":
            direct_git = git_executable.parents[1] / "mingw64" / "bin" / "git.exe"
            if direct_git.is_file():
                git_executable = direct_git.resolve()
        cls.git_executable = git_executable
        cls.git_executable_sha256 = "sha256:" + hashlib.sha256(git_executable.read_bytes()).hexdigest()
        cls.git_environment = dict(os.environ)
        for key in list(cls.git_environment):
            if key.casefold().startswith("git_"):
                cls.git_environment.pop(key)
        cls.git_environment.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_OPTIONAL_LOCKS": "0",
            }
        )
        cls._authoring_directory = tempfile.TemporaryDirectory()
        cls.authoring_root = Path(cls._authoring_directory.name) / "authoring"
        subprocess.run(
            [
                str(cls.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(ROOT),
                str(cls.authoring_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            env=cls.git_environment,
        )
        provenance = json.loads(HISTORY_BUNDLE_PROVENANCE.read_text(encoding="utf-8"))
        bundle_contract = provenance["bundle"]
        if bundle_contract["sha256"] != "sha256:" + HISTORY_BUNDLE_SHA256:
            raise AssertionError("V3 history bundle provenance digest mismatch")
        if hashlib.sha256(HISTORY_BUNDLE.read_bytes()).hexdigest() != HISTORY_BUNDLE_SHA256:
            raise AssertionError("V3 history bundle raw digest mismatch")
        cls.run_git(cls.authoring_root, "bundle", "verify", str(HISTORY_BUNDLE))
        cls.run_git(
            cls.authoring_root,
            "fetch",
            "--quiet",
            "--no-tags",
            str(HISTORY_BUNDLE),
            f"{HISTORY_BUNDLE_REF}:{HISTORY_EVIDENCE_REF}",
        )
        advertised = cls.run_git(
            cls.authoring_root,
            "rev-parse",
            "--verify",
            HISTORY_EVIDENCE_REF,
        ).stdout.strip()
        if advertised != CORRECTION_PARENT:
            raise AssertionError("V3 history bundle advertised commit mismatch")
        for required_commit in provenance["required_commits"]:
            cls.run_git(cls.authoring_root, "cat-file", "-e", f"{required_commit}^{{commit}}")
        cls.run_git(cls.authoring_root, "switch", "--quiet", "-C", TARGET_BRANCH, CORRECTION_PARENT)
        for relative in PAYLOAD_PATHS:
            destination = cls.authoring_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        cls.verifier = load_module(
            "_generic_dag_v5_verifier_under_test",
            OVERLAY / "verify_plan.py",
        )
        cls.addClassCleanup(cls.reset_verifier_boundary)

    def setUp(self) -> None:
        super().setUp()
        self._test_autopilot_snapshots = tuple(
            (root, complete_tree_snapshot(root / ".autopilot"))
            for root in (ROOT, self.authoring_root)
        )
        self.addCleanup(self._assert_test_autopilot_snapshots)

    def _assert_test_autopilot_snapshots(self) -> None:
        for root, before in self._test_autopilot_snapshots:
            self.assertEqual(
                complete_tree_snapshot(root / ".autopilot"),
                before,
                f"test path changed .autopilot bytes or metadata under {root}",
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._authoring_directory.cleanup()
        super().tearDownClass()

    @classmethod
    def reset_verifier_boundary(cls) -> None:
        boundary = cls.verifier._GIT_BOUNDARY
        cls.verifier._GIT_BOUNDARY = None
        if boundary is not None:
            handle = boundary.get("handle")
            if handle is not None and not handle.closed:
                handle.close()

    def tearDown(self) -> None:
        self.reset_verifier_boundary()
        super().tearDown()

    def test_history_bundle_is_digest_pinned_complete_and_prerequisite_bound(self) -> None:
        provenance = json.loads(HISTORY_BUNDLE_PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(HISTORY_BUNDLE.read_bytes()).hexdigest(),
            HISTORY_BUNDLE_SHA256,
        )
        self.assertEqual(
            provenance["bundle"]["sha256"],
            "sha256:" + HISTORY_BUNDLE_SHA256,
        )
        heads = self.run_git(
            self.authoring_root,
            "bundle",
            "list-heads",
            str(HISTORY_BUNDLE),
        ).stdout.splitlines()
        self.assertEqual(heads, [f"{CORRECTION_PARENT} {HISTORY_BUNDLE_REF}"])
        self.run_git(self.authoring_root, "bundle", "verify", str(HISTORY_BUNDLE))
        for required_commit in provenance["required_commits"]:
            self.run_git(
                self.authoring_root,
                "cat-file",
                "-e",
                f"{required_commit}^{{commit}}",
            )

        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / "tampered.bundle"
            raw = bytearray(HISTORY_BUNDLE.read_bytes())
            raw[0] ^= 0xFF
            tampered.write_bytes(raw)
            self.assertNotEqual(hashlib.sha256(raw).hexdigest(), HISTORY_BUNDLE_SHA256)
            result = subprocess.run(
                [str(self.git_executable), "-C", str(self.authoring_root), "bundle", "verify", str(tampered)],
                text=True,
                capture_output=True,
                check=False,
                env=self.git_environment,
            )
            self.assertNotEqual(result.returncode, 0)

        with tempfile.TemporaryDirectory() as directory:
            empty_repository = Path(directory) / "empty"
            self.run_git(Path(directory), "init", "--quiet", str(empty_repository))
            result = subprocess.run(
                [
                    str(self.git_executable),
                    "-C",
                    str(empty_repository),
                    "bundle",
                    "verify",
                    str(HISTORY_BUNDLE),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=self.git_environment,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("prerequisite", (result.stdout + result.stderr).casefold())

    def copy_git_executable(self, directory: Path) -> Path:
        executable = directory / self.git_executable.name
        shutil.copy2(self.git_executable, executable)
        if os.name != "nt":
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable.resolve(strict=True)

    def mutate_executable(self, executable: Path) -> None:
        with executable.open("r+b") as handle:
            original = handle.read(1)
            self.assertTrue(original)
            handle.seek(0)
            handle.write(bytes([original[0] ^ 0xFF]))
            handle.flush()
            os.fsync(handle.fileno())

    def mutate_executable_digest_only(self, executable: Path) -> None:
        """Change a byte outside the parsed image headers while retaining its format."""

        with executable.open("r+b") as handle:
            handle.seek(-1, os.SEEK_END)
            original = handle.read(1)
            self.assertTrue(original)
            handle.seek(-1, os.SEEK_END)
            handle.write(bytes([original[0] ^ 0xFF]))
            handle.flush()
            os.fsync(handle.fileno())

    def assert_autopilot_preserved(self, action, *, repo_root: Path | None = None):
        selected_root = self.authoring_root if repo_root is None else repo_root
        autopilot = selected_root / ".autopilot"
        before = complete_tree_snapshot(autopilot)
        try:
            return action()
        finally:
            after = complete_tree_snapshot(autopilot)
            self.assertEqual(after, before, f".autopilot byte/metadata drift under {selected_root}")

    @contextmanager
    def configured_boundary(
        self,
        executable: Path,
        *,
        expected_digest: str | None = None,
    ):
        self.reset_verifier_boundary()
        authoring_root = self.authoring_root.resolve()
        autopilot_before = complete_tree_snapshot(authoring_root / ".autopilot")
        hostile_ambient = {
            "HOME": str(executable.parent / "hostile-home"),
            "XDG_CONFIG_HOME": str(executable.parent / "hostile-xdg"),
            "PATH": str(executable.parent / "hostile-path"),
        }
        try:
            with mock.patch.dict(os.environ, hostile_ambient, clear=True):
                self.verifier.configure_git_boundary(
                    authoring_root,
                    git_executable=executable,
                    expected_git_executable_sha256=expected_digest or "sha256:" + raw_digest(executable),
                )
                yield self.verifier._GIT_BOUNDARY
        finally:
            self.reset_verifier_boundary()
            autopilot_after = complete_tree_snapshot(authoring_root / ".autopilot")
            self.assertEqual(autopilot_after, autopilot_before)

    def assert_executable_changed(self, action) -> None:
        with self.assertRaises(self.verifier.VerificationError) as raised:
            action()
        self.assertIn("changed", str(raised.exception).casefold())

    def assert_git_error_code(
        self,
        expected_type,
        expected_code: str,
        action,
        *,
        primary_code: str | None = None,
    ):
        with self.assertRaises(self.verifier.VerificationError) as raised:
            action()
        error = raised.exception
        self.assertIs(type(error), expected_type)
        self.assertEqual(error.code, expected_code)
        self.assertEqual(error.primary_code, primary_code or expected_code)
        self.assertIsInstance(error.cleanup_evidence, list)
        return error

    def require_windows_file_attribute_support(self) -> None:
        if os.name != "nt":
            self.skipTest("Win32 hidden/system attributes require Windows")
        with tempfile.TemporaryDirectory(dir=self.authoring_root.parent) as directory:
            probe = Path(directory) / "attribute-probe.bin"
            probe.write_bytes(b"attribute probe")
            original = windows_file_attributes(probe)
            requested = original | WINDOWS_FILE_ATTRIBUTE_HIDDEN | WINDOWS_FILE_ATTRIBUTE_SYSTEM
            try:
                try:
                    set_windows_file_attributes(probe, requested)
                except OSError as error:
                    self.skipTest(
                        "SetFileAttributesW cannot set hidden/system attributes "
                        f"on the test filesystem (winerror={getattr(error, 'winerror', None)})"
                    )
                observed = windows_file_attributes(probe)
                if observed & requested != requested:
                    self.skipTest(
                        "SetFileAttributesW did not retain hidden/system attributes "
                        f"on the test filesystem (observed=0x{observed:08x})"
                    )
            finally:
                set_windows_file_attributes(probe, original)

    def require_windows_named_stream_support(self) -> None:
        if os.name != "nt":
            self.skipTest("NTFS named-stream lifecycle coverage requires Windows")
        with tempfile.TemporaryDirectory(dir=self.authoring_root.parent) as directory:
            probe = Path(directory) / "stream-probe.bin"
            probe.write_bytes(b"unnamed")
            named = Path(f"{probe}:hive_mind_stream_capability_probe")
            try:
                try:
                    initial = windows_stream_snapshot(probe, include_unnamed=True)
                except WindowsStreamEnumerationUnsupported as error:
                    self.skipTest(str(error))
                self.assertEqual(
                    [row[0] for row in initial],
                    ["::$DATA"],
                    "ordinary files must enumerate exactly their unnamed data stream before the probe",
                )
                try:
                    named.write_bytes(b"named")
                except OSError as error:
                    self.skipTest(
                        "the test filesystem cannot create a named NTFS stream "
                        f"(winerror={getattr(error, 'winerror', None)})"
                    )
                observed = windows_stream_snapshot(probe, include_unnamed=True)
                if ":hive_mind_stream_capability_probe:$DATA" not in {
                    row[0] for row in observed
                }:
                    self.skipTest(
                        "FindFirstStreamW did not enumerate the created named stream"
                    )
            finally:
                named.unlink(missing_ok=True)

    def assert_outer_verify_autopilot_mutation(
        self,
        *,
        mutate,
        restore,
        primary_failure: bool,
        expected_cleanup_pattern: str = (
            r"(?i)(?:\.autopilot.*changed|\.autopilot.*point observations differ)"
        ),
    ) -> None:
        autopilot = self.authoring_root / ".autopilot"
        overlay = self.authoring_root / "docs/execution/dags/generic-hive-mind-product-v3"
        before = complete_tree_snapshot(autopilot)
        mutation_observed = False

        def lifecycle_result(**kwargs):
            nonlocal mutation_observed
            del kwargs
            mutate()
            mutation_observed = True
            self.assertNotEqual(
                complete_tree_snapshot(autopilot),
                before,
                "the independent test oracle did not observe the .autopilot mutation",
            )
            if primary_failure:
                raise self.verifier.GitTimeoutError(
                    "synthetic typed primary failure before .autopilot cleanup"
                )
            return {"verified": True}

        raised_error = None
        try:
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                self.verifier,
                "_verify_configured",
                side_effect=lifecycle_result,
            ):
                expected_type = (
                    self.verifier.GitTimeoutError
                    if primary_failure
                    else self.verifier.VerificationError
                )
                with self.assertRaises(expected_type) as raised:
                    self.verifier.verify(
                        expected_manifest_digest="sha256:" + raw_digest(overlay / "manifest.json"),
                        git_executable=self.git_executable,
                        expected_git_executable_sha256=self.git_executable_sha256,
                        overlay_dir=overlay,
                        repo_root=self.authoring_root,
                        authoring_check=True,
                    )
                raised_error = raised.exception
        finally:
            restore()
        self.assertTrue(mutation_observed)
        self.assertEqual(
            complete_tree_snapshot(autopilot),
            before,
            "the lifecycle fixture did not restore the complete .autopilot state",
        )
        self.assertIsNotNone(raised_error)
        payload = self.verifier.verification_error_payload(raised_error)
        if primary_failure:
            self.assertIs(type(raised_error), self.verifier.GitTimeoutError)
            self.assertEqual(payload["code"], "GIT_TIMEOUT")
            self.assertEqual(payload["primary_code"], "GIT_TIMEOUT")
            self.assertEqual(len(payload["cleanup_evidence"]), 1)
            cleanup = payload["cleanup_evidence"][0]
            self.assertEqual(cleanup["code"], "VERIFICATION_ERROR")
            self.assertEqual(cleanup["error_type"], "VerificationError")
            self.assertRegex(cleanup["error"], expected_cleanup_pattern)
        else:
            self.assertEqual(payload["code"], "VERIFICATION_ERROR")
            self.assertEqual(payload["primary_code"], "VERIFICATION_ERROR")
            self.assertEqual(payload["cleanup_evidence"], [])
            self.assertRegex(payload["error"], expected_cleanup_pattern)
        self.assertIsNone(self.verifier._GIT_BOUNDARY)

    def assert_configuration_rejected(self, action, expected_pattern: str) -> None:
        autopilot_before = complete_tree_snapshot(self.authoring_root / ".autopilot")
        try:
            action()
        except self.verifier.VerificationError as error:
            self.assertRegex(str(error), expected_pattern)
            cursor = error.__traceback__
            while cursor is not None:
                handle = cursor.tb_frame.f_locals.get("executable_handle")
                if handle is not None and not handle.closed:
                    handle.close()
                cursor = cursor.tb_next
            error.__traceback__ = None
        else:
            self.fail("Git boundary configuration unexpectedly succeeded")
        finally:
            self.reset_verifier_boundary()
            autopilot_after = complete_tree_snapshot(self.authoring_root / ".autopilot")
            self.assertEqual(autopilot_after, autopilot_before)

    def copy_overlay(self, target: Path) -> Path:
        copied = target / "overlay"
        shutil.copytree(
            self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3",
            copied,
        )
        return copied

    def run_verifier(
        self,
        overlay: Path,
        *,
        repo_root: Path | None = None,
        authoring_check: bool = True,
        include_expected_manifest: bool = True,
        environment_updates: dict[str, str] | None = None,
        git_executable: Path | None = None,
        git_executable_sha256: str | None = None,
        include_expected_git_digest: bool = True,
        expected_manifest_digest: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if repo_root is None:
            repo_root = self.authoring_root if authoring_check else ROOT
        command = [
            sys.executable,
            str(overlay / "verify_plan.py"),
            "--overlay-dir",
            str(overlay),
            "--repo-root",
            str(repo_root),
            "--git-executable",
            str(git_executable or self.git_executable),
        ]
        if include_expected_git_digest:
            command.extend(
                [
                    "--expected-git-executable-sha256",
                    git_executable_sha256 or self.git_executable_sha256,
                ]
            )
        if include_expected_manifest:
            command.extend(
                [
                    "--expected-manifest-digest",
                    expected_manifest_digest
                    or "sha256:" + hashlib.sha256((overlay / "manifest.json").read_bytes()).hexdigest(),
                ]
            )
        if authoring_check:
            command.append("--authoring-check")
        environment = dict(os.environ)
        for key in list(environment):
            if key.casefold().startswith("git_"):
                environment.pop(key)
        if environment_updates:
            environment.update(environment_updates)
        return self.assert_autopilot_preserved(
            lambda: subprocess.run(
                command,
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            ),
            repo_root=repo_root,
        )

    @classmethod
    def run_git(cls, repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(cls.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "-C",
                str(repository),
                *args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            env=cls.git_environment,
        )

    def make_committed_checkout(
        self,
        parent: Path,
        *,
        base: str = CORRECTION_PARENT,
        extra_path: bool = False,
        executable_path: str | None = None,
    ) -> Path:
        checkout = parent / "committed"
        subprocess.run(
            [
                str(self.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(ROOT),
                str(checkout),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            env=self.git_environment,
        )
        self.run_git(checkout, "switch", "--quiet", "-C", TARGET_BRANCH, base)
        self.run_git(checkout, "config", "user.name", "V3 Fixture")
        self.run_git(checkout, "config", "user.email", "v3-fixture@example.invalid")
        for relative in PAYLOAD_PATHS:
            destination = checkout / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.authoring_root / relative, destination)
        paths = list(CORRECTION_PATHS)
        if extra_path:
            unexpected = checkout / "unexpected-v3-payload.txt"
            unexpected.write_text("not allowlisted\n", encoding="utf-8")
            paths.append("unexpected-v3-payload.txt")
        self.run_git(checkout, "add", "--", *paths)
        if executable_path is not None:
            self.run_git(checkout, "update-index", "--chmod=+x", "--", executable_path)
        if base == CORRECTION_PARENT:
            staged = tuple(
                sorted(
                    line
                    for line in self.run_git(
                        checkout,
                        "diff",
                        "--cached",
                        "--name-only",
                        "--no-renames",
                    ).stdout.splitlines()
                    if line
                )
            )
            self.assertEqual(staged, tuple(sorted(paths)))
        self.run_git(checkout, "commit", "--quiet", "-m", "fixture: exact V3 payload")
        return checkout

    def assert_rejected(
        self,
        result: subprocess.CompletedProcess[str],
        expected_error: str | None = None,
    ) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertIs(payload["verified"], False)
        self.assertTrue(payload["error"])
        self.assertRegex(payload["code"], r"^[A-Z][A-Z0-9_]+$")
        self.assertTrue(payload["error_type"].endswith("Error"))
        self.assertRegex(payload["primary_code"], r"^[A-Z][A-Z0-9_]+$")
        self.assertIsInstance(payload["cleanup_evidence"], list)
        if expected_error is not None:
            self.assertIn(expected_error, payload["error"])

    def rewrite_manifest(self, overlay: Path, mutate) -> None:
        path = overlay / "manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        mutate(value)
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_authenticated_gitattributes_rules_bind_and_cover_every_raw_path(self) -> None:
        manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))
        contracts = json.loads(
            (OVERLAY / "node-contracts.json").read_text(encoding="utf-8")
        )
        raw = (ROOT / ".gitattributes").read_bytes()
        rules = self.verifier.parse_authenticated_gitattributes(raw)
        coverage = self.verifier.verify_authenticated_checkout_reproducibility(
            raw,
            manifest=manifest,
            contracts=contracts,
        )

        repository_paths = {
            row["path"] for row in manifest["source_bindings"]["repository"]
        }
        payload_paths = set(
            manifest["committed_payload_contract"]["payload_inventory"]
        )
        overlay_paths = {
            "docs/execution/dags/generic-hive-mind-product-v3/" + row["path"]
            for row in manifest["source_bindings"]["overlay"]
        }
        frozen_paths = {
            row["path"] for row in contracts["frozen_host_contract"]["files"]
        }
        expected = repository_paths | payload_paths | overlay_paths | frozen_paths
        self.assertEqual(set(coverage), expected)
        self.assertEqual(coverage["tests/fixtures/generic-v3-history.bundle"], "explicit--text")
        self.assertEqual(
            {value for path, value in coverage.items() if not path.endswith(".bundle")},
            {"text-eol-lf"},
            "all non-bundle bound inputs are repository-authored text",
        )
        with self.configured_boundary(self.git_executable):
            self.verifier.verify_no_applicable_nested_gitattributes(
                self.authoring_root,
                coverage,
            )
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                r"applicable nested \.gitattributes is forbidden.*\.autopilot/lessons/\.gitattributes",
            ):
                self.verifier.verify_no_applicable_nested_gitattributes(
                    self.authoring_root,
                    [".autopilot/lessons/future-bound-ledger.jsonl"],
                )
        with tempfile.TemporaryDirectory() as directory:
            fallback_repo = Path(directory) / "index-fallback"
            fallback_repo.mkdir()
            self.run_git(fallback_repo, "init", "--quiet")
            self.run_git(fallback_repo, "config", "user.name", "Attribute Fallback")
            self.run_git(
                fallback_repo,
                "config",
                "user.email",
                "attribute-fallback@example.invalid",
            )
            fallback_attributes = (
                fallback_repo / ".autopilot" / "lessons" / ".gitattributes"
            )
            fallback_attributes.parent.mkdir(parents=True)
            fallback_attributes.write_text(
                "*.jsonl filter=hostile text eol=crlf\n",
                encoding="utf-8",
            )
            self.run_git(fallback_repo, "add", "--", ".autopilot/lessons/.gitattributes")
            self.run_git(
                fallback_repo,
                "commit",
                "--quiet",
                "-m",
                "nested attribute fallback fixture",
            )
            fallback_attributes.unlink()
            self.reset_verifier_boundary()
            try:
                with mock.patch.dict(os.environ, {}, clear=True):
                    self.verifier.configure_git_boundary(
                        fallback_repo,
                        git_executable=self.git_executable,
                        expected_git_executable_sha256=self.git_executable_sha256,
                    )
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        r"applicable nested \.gitattributes is forbidden.*\.autopilot/lessons/\.gitattributes",
                    ):
                        self.verifier.verify_no_applicable_nested_gitattributes(
                            fallback_repo,
                            [".autopilot/lessons/future-bound-ledger.jsonl"],
                        )
            finally:
                self.reset_verifier_boundary()
        self.assertEqual(len(CORRECTION_PATHS), 11)
        self.assertEqual(CORRECTION_PATHS[0], ".gitattributes")
        self.assertIn(".gitattributes", PAYLOAD_PATHS)
        with self.assertRaisesRegex(
            self.verifier.VerificationError,
            "raw-bound path lacks authenticated deterministic checkout classification",
        ):
            self.verifier.verify_bound_path_attribute_coverage(
                rules,
                ["future/raw-bound-input.opaque"],
            )

    def test_gitattributes_payload_binding_and_every_required_rule_fail_closed(self) -> None:
        manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))
        manifest_raw = (OVERLAY / "manifest.json").read_bytes()
        bindings = manifest["committed_payload_contract"]["payload_bindings"]
        attribute_row = next(row for row in bindings if row["path"] == ".gitattributes")

        omitted_binding = json.loads(json.dumps(manifest))
        omitted_binding["committed_payload_contract"]["payload_bindings"] = [
            row
            for row in omitted_binding["committed_payload_contract"]["payload_bindings"]
            if row["path"] != ".gitattributes"
        ]
        with self.assertRaisesRegex(
            self.verifier.VerificationError,
            "committed payload binding inventory mismatch",
        ):
            self.verifier.verify_payload_bindings(
                omitted_binding,
                repo_root=self.authoring_root,
                overlay_dir=(
                    self.authoring_root
                    / "docs/execution/dags/generic-hive-mind-product-v3"
                ),
                manifest_raw=manifest_raw,
            )

        mutated_binding = json.loads(json.dumps(manifest))
        mutated_row = next(
            row
            for row in mutated_binding["committed_payload_contract"]["payload_bindings"]
            if row["path"] == ".gitattributes"
        )
        mutated_row["sha256"] = "sha256:" + "0" * 64
        self.assertNotEqual(mutated_row, attribute_row)
        with self.assertRaisesRegex(
            self.verifier.VerificationError,
            "committed payload digest mismatch: .gitattributes",
        ):
            self.verifier.verify_payload_bindings(
                mutated_binding,
                repo_root=self.authoring_root,
                overlay_dir=(
                    self.authoring_root
                    / "docs/execution/dags/generic-hive-mind-product-v3"
                ),
                manifest_raw=manifest_raw,
            )

        contracts = json.loads(
            (OVERLAY / "node-contracts.json").read_text(encoding="utf-8")
        )
        raw = (ROOT / ".gitattributes").read_bytes()
        hostile_whitespace = {
            "nbsp": "\u00a0".encode("utf-8"),
            "nel": "\u0085".encode("utf-8"),
            "unicode_line_separator": "\u2028".encode("utf-8"),
            "vertical_tab": b"\x0b",
            "form_feed": b"\x0c",
        }
        for label, separator in hostile_whitespace.items():
            with self.subTest(hostile_whitespace=label):
                substituted = raw.replace(
                    b".gitattributes text eol=lf",
                    b".gitattributes" + separator + b"text" + separator + b"eol=lf",
                    1,
                )
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "printable ASCII",
                ):
                    self.verifier.parse_authenticated_gitattributes(substituted)
        required_rules = {
            **self.verifier.REQUIRED_TEXT_GITATTRIBUTE_RULES,
            **self.verifier.REQUIRED_RAW_EVIDENCE_GITATTRIBUTE_RULES,
        }
        for pattern, attributes in required_rules.items():
            literal = f"{pattern} {' '.join(attributes)}\n".encode("utf-8")
            self.assertEqual(raw.count(literal), 1, pattern)
            with self.subTest(rule=pattern, mutation="omitted"):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "required exact rule missing",
                ):
                    self.verifier.verify_authenticated_checkout_reproducibility(
                        raw.replace(literal, b"", 1),
                        manifest=manifest,
                        contracts=contracts,
                    )
            replacement_attributes = list(attributes)
            replacement_attributes[-1] = (
                "eol=crlf" if replacement_attributes[-1] == "eol=lf" else "diff"
            )
            mutated = (
                f"{pattern} {' '.join(replacement_attributes)}\n".encode("utf-8")
            )
            with self.subTest(rule=pattern, mutation="changed"):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "required exact rule missing",
                ):
                    self.verifier.verify_authenticated_checkout_reproducibility(
                        raw.replace(literal, mutated, 1),
                        manifest=manifest,
                        contracts=contracts,
                    )

        active_rule_overrides = {
            "required_text": b"LICENSE -text\n",
            "raw_evidence": b"evidence/live/** text eol=lf\n",
            "narrow_raw_text": b"evidence/live/*.json text eol=crlf\n",
            "narrow_raw_diff": b"evidence/live/*.json diff\n",
        }
        for label, override in active_rule_overrides.items():
            with self.subTest(late_override=label):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "canonical checkout policy",
                ):
                    self.verifier.verify_authenticated_checkout_reproducibility(
                        raw + override,
                        manifest=manifest,
                        contracts=contracts,
                    )

    def test_authenticated_attributes_defeat_system_and_global_autocrlf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            candidate = self.make_committed_checkout(parent)
            system_config = parent / "system.gitconfig"
            global_config = parent / "global.gitconfig"
            config_text = "[core]\n\tautocrlf = true\n"
            system_config.write_text(config_text, encoding="utf-8", newline="\n")
            global_config.write_text(config_text, encoding="utf-8", newline="\n")

            hostile_environment = dict(os.environ)
            for key in list(hostile_environment):
                if key.casefold().startswith("git_"):
                    hostile_environment.pop(key)
            hostile_environment.update(
                {
                    "GIT_CONFIG_SYSTEM": str(system_config),
                    "GIT_CONFIG_GLOBAL": str(global_config),
                }
            )
            fresh = parent / "autocrlf-true-checkout"
            clone = subprocess.run(
                [
                    str(self.git_executable),
                    "clone",
                    "--quiet",
                    "--no-hardlinks",
                    str(candidate),
                    str(fresh),
                ],
                cwd=parent,
                text=True,
                capture_output=True,
                check=False,
                env=hostile_environment,
            )
            self.assertEqual(clone.returncode, 0, clone.stdout + clone.stderr)
            observed_config = subprocess.run(
                [
                    str(self.git_executable),
                    "-C",
                    str(fresh),
                    "config",
                    "--show-origin",
                    "--get-all",
                    "core.autocrlf",
                ],
                cwd=parent,
                text=True,
                capture_output=True,
                check=False,
                env=hostile_environment,
            )
            self.assertEqual(
                observed_config.returncode,
                0,
                observed_config.stdout + observed_config.stderr,
            )
            configured_values = [
                line.rsplit(maxsplit=1)[-1].casefold()
                for line in observed_config.stdout.splitlines()
                if line.strip()
            ]
            self.assertGreaterEqual(configured_values.count("true"), 2)

            manifest = json.loads(
                (
                    fresh
                    / "docs/execution/dags/generic-hive-mind-product-v3/manifest.json"
                ).read_text(encoding="utf-8")
            )
            contracts = json.loads(
                (
                    fresh
                    / "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json"
                ).read_text(encoding="utf-8")
            )
            bound_paths = self.verifier.manifest_raw_bound_paths(manifest, contracts)
            for relative in bound_paths:
                with self.subTest(relative=relative):
                    blob = subprocess.run(
                        [
                            str(self.git_executable),
                            "-C",
                            str(fresh),
                            "show",
                            f"HEAD:{relative}",
                        ],
                        cwd=parent,
                        capture_output=True,
                        check=False,
                        env=hostile_environment,
                    )
                    self.assertEqual(blob.returncode, 0, blob.stderr)
                    self.assertEqual((fresh / relative).read_bytes(), blob.stdout)

            fixture = parent / "attribute-semantics-source"
            fixture.mkdir()
            self.run_git(fixture, "init", "--quiet")
            self.run_git(fixture, "config", "user.name", "Attribute Fixture")
            self.run_git(
                fixture,
                "config",
                "user.email",
                "attribute-fixture@example.invalid",
            )
            shutil.copy2(ROOT / ".gitattributes", fixture / ".gitattributes")
            text_samples = {
                "LICENSE",
                "probe.ps1",
                "probe.toml",
                "probe.yml",
                "probe.yaml",
            }
            raw_samples = {
                "evidence/sources/probe/raw/exhibit.md",
                "evidence/live/receipt.json",
                "evidence/benchmarks/receipt.jsonl",
                "evidence/experiments/_artifacts/output.json",
                "evidence/experiments/_failed/output.json",
                "evidence/local_assurance/probe/logs/transcript.txt",
            }
            for relative in sorted(text_samples | raw_samples):
                path = fixture / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"first\r\nsecond\r\n")
            self.run_git(fixture, "add", "--", ".")
            self.run_git(fixture, "commit", "--quiet", "-m", "attribute fixture")

            hostile_fixture = parent / "attribute-semantics-autocrlf-true"
            fixture_clone = subprocess.run(
                [
                    str(self.git_executable),
                    "clone",
                    "--quiet",
                    "--no-hardlinks",
                    str(fixture),
                    str(hostile_fixture),
                ],
                cwd=parent,
                text=True,
                capture_output=True,
                check=False,
                env=hostile_environment,
            )
            self.assertEqual(
                fixture_clone.returncode,
                0,
                fixture_clone.stdout + fixture_clone.stderr,
            )
            for relative in sorted(text_samples | raw_samples | {".gitattributes"}):
                blob = subprocess.run(
                    [
                        str(self.git_executable),
                        "-C",
                        str(hostile_fixture),
                        "show",
                        f"HEAD:{relative}",
                    ],
                    cwd=parent,
                    capture_output=True,
                    check=True,
                    env=hostile_environment,
                ).stdout
                self.assertEqual((hostile_fixture / relative).read_bytes(), blob)
                attributes = subprocess.run(
                    [
                        str(self.git_executable),
                        "-C",
                        str(hostile_fixture),
                        "check-attr",
                        "text",
                        "eol",
                        "diff",
                        "--",
                        relative,
                    ],
                    cwd=parent,
                    text=True,
                    capture_output=True,
                    check=True,
                    env=hostile_environment,
                ).stdout
                if relative in raw_samples:
                    self.assertIn(f"{relative}: text: unset", attributes)
                    self.assertIn(f"{relative}: diff: unset", attributes)
                    self.assertIn(b"\r\n", blob)
                else:
                    self.assertIn(f"{relative}: text: set", attributes)
                    self.assertIn(f"{relative}: eol: lf", attributes)
                    self.assertNotIn(b"\r\n", blob)

    def test_shallow_copied_verifier_import_and_help_are_repository_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = {
                "shallow": root / "verify_plan.py",
                "deep": root / "one" / "two" / "three" / "four" / "verify_plan.py",
            }
            for label, verifier_copy in variants.items():
                with self.subTest(depth=label):
                    verifier_copy.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(OVERLAY / "verify_plan.py", verifier_copy)
                    imported = load_module(
                        f"_generic_dag_v5_{label}_help_probe",
                        verifier_copy,
                    )
                    self.assertTrue(callable(imported.main))
                    environment = dict(os.environ)
                    environment["PYTHONDONTWRITEBYTECODE"] = "1"
                    result = subprocess.run(
                        [sys.executable, "-B", str(verifier_copy), "--help"],
                        cwd=verifier_copy.parent,
                        text=True,
                        capture_output=True,
                        check=False,
                        env=environment,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("--repo-root", result.stdout)
                    self.assertIn("--overlay-dir", result.stdout)
                    self.assertIn("--expected-manifest-digest", result.stdout)

    def test_valid_overlay_verifies_without_mutating_historical_plan(self) -> None:
        sealed_legacy_plan = self.authoring_root / ".autopilot" / "plan.json"
        before = sealed_legacy_plan.read_bytes()
        complete_before = complete_tree_snapshot(self.authoring_root / ".autopilot")
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            result = self.run_verifier(overlay)
            complete_after_success = complete_tree_snapshot(self.authoring_root / ".autopilot")
            self.rewrite_manifest(
                overlay,
                lambda manifest: manifest.__setitem__("untrusted_extra", True),
            )
            rejected = self.run_verifier(overlay)
            self.assert_rejected(rejected, "manifest top-level field inventory mismatch")
            complete_after_rejection = complete_tree_snapshot(self.authoring_root / ".autopilot")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["verified"])
        self.assertEqual(payload["integrity"], "verified-sealed")
        self.assertEqual(payload["durability_semantics"], "typed-v2")
        self.assertEqual(payload["topology"], {"nodes": 20, "raw_edges": 28, "levels": 17, "rounds": 20})
        self.assertFalse(payload["materializer_imported_or_executed"])
        self.assertEqual(payload["verification_mode"], V5_AUTHORING_MODE)
        self.assertFalse(payload["committed_payload_qualification"])
        self.assertFalse(payload["execution_qualification"])
        self.assertFalse(payload["execution"]["authorized"])
        autopilot_disclosure = payload["autopilot_tree"]
        self.assertEqual(
            set(autopilot_disclosure),
            {
                "schema",
                "entry_count",
                "total_file_bytes",
                "snapshot_digest",
                "observed_unchanged",
                "concurrent_mutation_exclusion",
                "requires_external_read_only_custody_for_execution",
            },
        )
        self.assertNotIn("unchanged", autopilot_disclosure)
        self.assertEqual(
            autopilot_disclosure["schema"],
            "complete-autopilot-tree-point-observation-v2",
        )
        self.assertIs(autopilot_disclosure["observed_unchanged"], True)
        self.assertIs(autopilot_disclosure["concurrent_mutation_exclusion"], False)
        self.assertIs(
            autopilot_disclosure[
                "requires_external_read_only_custody_for_execution"
            ],
            True,
        )
        self.assertEqual(sealed_legacy_plan.read_bytes(), before)
        self.assertEqual(complete_after_success, complete_before)
        self.assertEqual(complete_after_rejection, complete_before)

    def test_windows_optional_metadata_and_named_stream_oracle(self) -> None:
        self.require_windows_file_attribute_support()
        self.require_windows_named_stream_support()
        with tempfile.TemporaryDirectory(dir=self.authoring_root.parent) as directory:
            root = Path(directory)
            probe = root / "oracle-probe.bin"
            probe.write_bytes(b"unnamed stream bytes")
            stream_name = ":hive_mind_oracle_stream:$DATA"
            stream_path = Path(f"{probe}:hive_mind_oracle_stream")
            original_state = probe.stat()
            original_attributes = windows_file_attributes(probe)
            original_times = (original_state.st_atime_ns, original_state.st_mtime_ns)
            before = optional_filesystem_snapshot(probe, original_state)

            unnamed = windows_stream_snapshot(probe, include_unnamed=True)
            self.assertEqual(
                unnamed,
                (
                    (
                        "::$DATA",
                        len(b"unnamed stream bytes"),
                        hashlib.sha256(b"unnamed stream bytes").hexdigest(),
                    ),
                ),
            )
            self.assertEqual(
                windows_stream_snapshot(root, include_unnamed=True),
                (),
                "a directory with no data streams must map ERROR_HANDLE_EOF (38) to an empty inventory",
            )

            requested_attributes = (
                original_attributes
                | WINDOWS_FILE_ATTRIBUTE_HIDDEN
                | WINDOWS_FILE_ATTRIBUTE_SYSTEM
            )
            try:
                set_windows_file_attributes(probe, requested_attributes)
                stream_path.write_bytes(b"independent named stream bytes")
                os.utime(probe, ns=original_times)
                changed_state = probe.stat()
                changed = optional_filesystem_snapshot(probe, changed_state)
                self.assertNotEqual(changed, before)
                self.assertEqual(
                    changed[1] & (
                        WINDOWS_FILE_ATTRIBUTE_HIDDEN | WINDOWS_FILE_ATTRIBUTE_SYSTEM
                    ),
                    WINDOWS_FILE_ATTRIBUTE_HIDDEN | WINDOWS_FILE_ATTRIBUTE_SYSTEM,
                )
                optional_stat_fields = dict(changed[0])
                if "st_file_attributes" in optional_stat_fields:
                    self.assertEqual(optional_stat_fields["st_file_attributes"], changed[1])
                named_streams = {row[0]: row for row in changed[2]}
                self.assertEqual(
                    named_streams[stream_name],
                    (
                        stream_name,
                        len(b"independent named stream bytes"),
                        hashlib.sha256(b"independent named stream bytes").hexdigest(),
                    ),
                )
            finally:
                stream_path.unlink(missing_ok=True)
                set_windows_file_attributes(probe, original_attributes)
                os.utime(probe, ns=original_times)
            self.assertEqual(
                optional_filesystem_snapshot(probe, probe.stat()),
                before,
                "the independent Win32 oracle fixture did not restore exactly",
            )

    def test_path_open_identity_rejects_optional_windows_attribute_mismatch(self) -> None:
        common = {
            "st_dev": 11,
            "st_ino": 22,
            "st_mode": stat.S_IFREG | 0o644,
            "st_nlink": 1,
            "st_uid": 33,
            "st_gid": 44,
            "st_size": 33,
            "st_mtime_ns": 44,
            "st_ctime_ns": 45,
            "st_reparse_tag": 0,
            "st_birthtime_ns": 55,
            "st_flags": 0,
            "st_gen": 66,
        }
        stable_optional = {
            "st_file_attributes": 0x20,
            "st_reparse_tag": 0,
            "st_birthtime_ns": 55,
            "st_flags": 0,
            "st_gen": 66,
        }
        for name in stable_optional:
            common.pop(name, None)
        path_state = SimpleNamespace(**common, **stable_optional)
        same_open_state = SimpleNamespace(**common, **stable_optional)
        path_identity = self.verifier._filesystem_path_open_identity(path_state)
        self.assertEqual(
            path_identity,
            self.verifier._filesystem_path_open_identity(same_open_state),
        )
        for name, value in stable_optional.items():
            with self.subTest(optional_field=name):
                changed_optional = dict(stable_optional)
                changed_optional[name] = value + 1
                changed_open_state = SimpleNamespace(**common, **changed_optional)
                self.assertNotEqual(
                    path_identity,
                    self.verifier._filesystem_path_open_identity(changed_open_state),
                    f"path/open identity omitted optional field {name}",
                )
        ctime_only = dict(common)
        ctime_only["st_ctime_ns"] += 1
        self.assertEqual(
            path_identity,
            self.verifier._filesystem_path_open_identity(
                SimpleNamespace(**ctime_only, **stable_optional)
            ),
            "path/open identity must exclude only the documented ctime difference",
        )

        class FileAttributeOverride:
            def __init__(self, base_state, file_attributes: int) -> None:
                self._base_state = base_state
                self.st_file_attributes = file_attributes

            def __getattr__(self, name: str):
                return getattr(self._base_state, name)

        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            autopilot = repo_root / ".autopilot"
            autopilot.mkdir()
            target = autopilot / "path-open-attribute-probe.bin"
            target.write_bytes(b"path/open attribute mismatch")
            original_fstat = self.verifier.os.fstat

            def mismatched_fstat(file_descriptor: int):
                state = original_fstat(file_descriptor)
                path_attributes = getattr(os.lstat(target), "st_file_attributes", 0)
                return FileAttributeOverride(
                    state,
                    path_attributes ^ WINDOWS_FILE_ATTRIBUTE_HIDDEN,
                )

            with mock.patch.object(
                self.verifier.os,
                "fstat",
                side_effect=mismatched_fstat,
            ):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "path/open-file identity mismatch",
                ):
                    self.verifier.snapshot_autopilot_tree(repo_root)

    def test_windows_stream_api_failures_and_cleanup_fail_closed(self) -> None:
        if os.name != "nt":
            self.skipTest("synthetic Win32 stream API failure coverage requires Windows")

        with mock.patch.object(
            self.verifier,
            "_WINDOWS_STREAM_API",
            None,
        ), mock.patch.object(
            self.verifier.ctypes,
            "WinDLL",
            side_effect=OSError("synthetic kernel32 API unavailable"),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "cannot initialize bounded Windows stream enumeration",
            ):
                self.verifier._windows_stream_api()

        invalid_handle = ctypes.c_void_p(-1).value
        for error_code in (5, WINDOWS_ERROR_INVALID_PARAMETER):
            first = mock.Mock()

            def fail_first(path, info_level, data, flags, *, code=error_code):
                del path, info_level, data, flags
                ctypes.set_last_error(code)
                return invalid_handle

            first.side_effect = fail_first
            next_stream = mock.Mock()
            close = mock.Mock()
            with self.subTest(find_first_error=error_code), mock.patch.object(
                self.verifier,
                "_windows_stream_api",
                return_value=(first, next_stream, close),
            ):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "cannot begin enumerating Windows streams",
                ):
                    self.verifier._windows_stream_snapshot(
                        Path("synthetic"),
                        label="file synthetic",
                    )
                next_stream.assert_not_called()
                close.assert_not_called()

        first_exception = mock.Mock(side_effect=OSError("synthetic FindFirstStreamW exception"))
        next_stream = mock.Mock()
        close = mock.Mock()
        with mock.patch.object(
            self.verifier,
            "_windows_stream_api",
            return_value=(first_exception, next_stream, close),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "cannot begin Windows stream enumeration",
            ):
                self.verifier._windows_stream_snapshot(
                    Path("synthetic"),
                    label="file synthetic",
                )
        next_stream.assert_not_called()
        close.assert_not_called()

        for null_handle in (None, 0):
            first_null = mock.Mock(return_value=null_handle)
            next_stream = mock.Mock()
            close = mock.Mock()
            with self.subTest(null_handle=null_handle), mock.patch.object(
                self.verifier,
                "_windows_stream_api",
                return_value=(first_null, next_stream, close),
            ):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "returned an invalid handle",
                ):
                    self.verifier._windows_stream_snapshot(
                        Path("synthetic"),
                        label="file synthetic",
                    )
                next_stream.assert_not_called()
                close.assert_not_called()

        stream_type = self.verifier._WIN32_FIND_STREAM_DATA

        def populate_unnamed(pointer, size: int = 7) -> None:
            stream = ctypes.cast(pointer, ctypes.POINTER(stream_type)).contents
            stream.StreamSize = size
            stream.cStreamName = "::$DATA"

        def successful_first(path, info_level, data, flags):
            del path, info_level, flags
            populate_unnamed(data)
            return 0x1234

        def failed_next(handle, data):
            del handle, data
            ctypes.set_last_error(5)
            return 0

        def failed_close(handle):
            del handle
            ctypes.set_last_error(6)
            return 0

        def successful_close(handle):
            del handle
            return 1

        def exceptional_next(handle, data):
            del handle, data
            raise OSError("synthetic FindNextStreamW exception")

        close = mock.Mock(side_effect=successful_close)
        with mock.patch.object(
            self.verifier,
            "_windows_stream_api",
            return_value=(successful_first, exceptional_next, close),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "cannot continue Windows stream enumeration",
            ):
                self.verifier._windows_stream_snapshot(
                    Path("synthetic"),
                    label="file synthetic",
                )
        close.assert_called_once_with(0x1234)

        close = mock.Mock(side_effect=failed_close)
        with mock.patch.object(
            self.verifier,
            "_windows_stream_api",
            return_value=(successful_first, failed_next, close),
        ):
            with self.assertRaises(self.verifier.VerificationError) as raised:
                self.verifier._windows_stream_snapshot(
                    Path("synthetic"),
                    label="file synthetic",
                )
        payload = self.verifier.verification_error_payload(raised.exception)
        self.assertIn("continue enumerating", payload["error"])
        self.assertEqual(len(payload["cleanup_evidence"]), 1)
        self.assertIn("close the enumeration", payload["cleanup_evidence"][0]["error"])
        close.assert_called_once_with(0x1234)

        def exhausted_next(handle, data):
            del handle, data
            ctypes.set_last_error(WINDOWS_ERROR_HANDLE_EOF)
            return 0

        with mock.patch.object(
            self.verifier,
            "_windows_stream_api",
            return_value=(successful_first, exhausted_next, failed_close),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "close the enumeration",
            ):
                self.verifier._windows_stream_snapshot(
                    Path("synthetic"),
                    label="file synthetic",
                )

        def exceptional_close(handle):
            del handle
            raise OSError("synthetic FindClose exception")

        with mock.patch.object(
            self.verifier,
            "_windows_stream_api",
            return_value=(successful_first, exhausted_next, exceptional_close),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "cannot close Windows stream enumeration",
            ):
                self.verifier._windows_stream_snapshot(
                    Path("synthetic"),
                    label="file synthetic",
                )

        def unexpected_second_stream(handle, data):
            del handle, data
            return 1

        close = mock.Mock(side_effect=successful_close)
        with mock.patch.object(
            self.verifier,
            "MAX_AUTOPILOT_WINDOWS_STREAMS_PER_ENTRY",
            1,
        ), mock.patch.object(
            self.verifier,
            "_windows_stream_api",
            return_value=(successful_first, unexpected_second_stream, close),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "stream inventory exceeds the limit",
            ):
                self.verifier._windows_stream_snapshot(
                    Path("synthetic"),
                    label="file synthetic",
                )
        close.assert_called_once_with(0x1234)

    def test_windows_system_environment_api_failure_is_normalized(self) -> None:
        if os.name != "nt":
            self.skipTest("GetWindowsDirectoryW failure normalization requires Windows")
        kernel32 = self.verifier.ctypes.windll.kernel32
        with mock.patch.object(
            kernel32,
            "GetWindowsDirectoryW",
            side_effect=OSError("synthetic GetWindowsDirectoryW failure"),
        ):
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "cannot query the Windows system directory",
            ):
                self.verifier._windows_system_environment()

    def test_windows_unnamed_stream_size_inconsistency_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            autopilot = repo_root / ".autopilot"
            autopilot.mkdir()
            target = autopilot / "probe.bin"
            target.write_bytes(b"seven!!")

            def inconsistent_stream(path: Path, *, label: str):
                del label
                if path == target:
                    return (("::$DATA", target.stat().st_size + 1),)
                return ()

            with mock.patch.object(
                self.verifier,
                "_windows_stream_snapshot",
                side_effect=inconsistent_stream,
            ), mock.patch.object(self.verifier.os, "name", "nt"):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "inconsistent unnamed Windows data stream",
                ):
                    self.verifier.snapshot_autopilot_tree(repo_root)

    def test_final_stream_enumeration_mutation_is_caught_by_post_lstat(self) -> None:
        original_stream_snapshot = self.verifier._windows_stream_snapshot
        for kind in ("file", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                repo_root = Path(directory)
                autopilot = repo_root / ".autopilot"
                autopilot.mkdir()
                target = autopilot
                if kind == "file":
                    target = autopilot / "probe.bin"
                    target.write_bytes(b"post-stream lstat probe")
                state = target.stat()
                original_times = (state.st_atime_ns, state.st_mtime_ns)
                calls = 0

                def mutate_after_final_stream(path: Path, *, label: str):
                    nonlocal calls
                    observed = original_stream_snapshot(path, label=label)
                    if path == target:
                        calls += 1
                        if calls == 2:
                            os.utime(
                                target,
                                ns=(original_times[0], original_times[1] + 2_000_000_000),
                            )
                    return observed

                try:
                    with mock.patch.object(
                        self.verifier,
                        "_windows_stream_snapshot",
                        side_effect=mutate_after_final_stream,
                    ):
                        with self.assertRaisesRegex(
                            self.verifier.VerificationError,
                            r"(?i)changed.*(?:stream|snapshot)|stream.*changed",
                        ):
                            self.verifier.snapshot_autopilot_tree(repo_root)
                    self.assertEqual(calls, 2)
                finally:
                    os.utime(target, ns=original_times)

    def test_autopilot_snapshot_enforces_every_resource_bound(self) -> None:
        cases = (
            (
                "entry",
                "MAX_AUTOPILOT_TREE_ENTRIES",
                1,
                lambda root: (root / "one").write_bytes(b"1"),
                "entry limit",
            ),
            (
                "depth",
                "MAX_AUTOPILOT_TREE_DEPTH",
                0,
                lambda root: (root / "one" / "two").mkdir(parents=True),
                "depth limit",
            ),
            (
                "path",
                "MAX_AUTOPILOT_PATH_BYTES",
                1,
                lambda root: (root / "long-name").write_bytes(b"1"),
                "path exceeds the byte limit",
            ),
            (
                "per_file",
                "MAX_AUTOPILOT_FILE_BYTES",
                1,
                lambda root: (root / "two-bytes").write_bytes(b"12"),
                "per-file limit",
            ),
            (
                "total",
                "MAX_AUTOPILOT_TOTAL_BYTES",
                1,
                lambda root: (
                    (root / "first").write_bytes(b"1"),
                    (root / "second").write_bytes(b"2"),
                ),
                "total-byte limit",
            ),
        )
        for label, constant, limit, build, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                repo_root = Path(directory)
                autopilot = repo_root / ".autopilot"
                autopilot.mkdir()
                build(autopilot)
                with mock.patch.object(self.verifier, constant, limit):
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        expected,
                    ):
                        self.verifier.snapshot_autopilot_tree(repo_root)

        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            (repo_root / ".autopilot").mkdir()
            observed = self.verifier.snapshot_autopilot_tree(repo_root)
            self.assertEqual(
                observed["schema"],
                "complete-autopilot-tree-point-observation-v2",
            )

    def test_authoring_mode_rejects_any_state_beyond_exact_eleven_payload_paths(self) -> None:
        overlay = self.authoring_root / "docs/execution/dags/generic-hive-mind-product-v3"
        changed = tuple(
            sorted(
                line
                for line in self.run_git(
                    self.authoring_root,
                    "diff",
                    "--name-only",
                    "--no-renames",
                ).stdout.splitlines()
                if line
            )
        )
        untracked = tuple(
            sorted(
                line
                for line in self.run_git(
                    self.authoring_root,
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                ).stdout.splitlines()
                if line
            )
        )
        self.assertEqual(changed, tuple(sorted(set(CORRECTION_PATHS) - set(ADDED_CORRECTION_PATHS))))
        self.assertEqual(untracked, tuple(sorted(ADDED_CORRECTION_PATHS)))

        tracked = self.authoring_root / "CONTRIBUTING.md"
        tracked_before = tracked.read_bytes()
        try:
            tracked.write_bytes(tracked_before + b"\nunexpected authoring dirt\n")
            self.assert_rejected(self.run_verifier(overlay))
        finally:
            tracked.write_bytes(tracked_before)

        unexpected = self.authoring_root / "unexpected-authoring-state.tmp"
        try:
            unexpected.write_text("untracked authoring state\n", encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))
        finally:
            unexpected.unlink(missing_ok=True)

        try:
            tracked.write_bytes(tracked_before + b"\nhidden staged authoring content\n")
            self.run_git(self.authoring_root, "add", "--", "CONTRIBUTING.md")
            tracked.write_bytes(tracked_before)
            self.assert_rejected(
                self.run_verifier(overlay),
                "authoring Git index differs from the exact HEAD tree",
            )
        finally:
            self.run_git(
                self.authoring_root,
                "restore",
                "--staged",
                "--source=HEAD",
                "--",
                "CONTRIBUTING.md",
            )
            tracked.write_bytes(tracked_before)

        try:
            self.run_git(
                self.authoring_root,
                "update-index",
                "--chmod=+x",
                "--",
                "CONTRIBUTING.md",
            )
            expected_error = "authoring Git index differs from the exact HEAD tree"
            result = self.run_verifier(overlay)
            self.assert_rejected(result, expected_error)
            self.assertEqual(
                json.loads(result.stdout.strip().splitlines()[-1])["error"],
                expected_error,
            )
        finally:
            self.run_git(
                self.authoring_root,
                "update-index",
                "--chmod=-x",
                "--",
                "CONTRIBUTING.md",
            )

        with tempfile.TemporaryDirectory() as directory:
            alternate_overlay = self.copy_overlay(Path(directory))
            readme = alternate_overlay / "README.md"
            readme.write_bytes(readme.read_bytes() + b"\nresealed alternate overlay\n")
            readme_raw = readme.read_bytes()

            def reseal_readme(manifest) -> None:
                row = next(
                    item
                    for item in manifest["committed_payload_contract"]["payload_bindings"]
                    if item["path"]
                    == "docs/execution/dags/generic-hive-mind-product-v3/README.md"
                )
                row["bytes"] = len(readme_raw)
                row["sha256"] = "sha256:" + hashlib.sha256(readme_raw).hexdigest()

            self.rewrite_manifest(alternate_overlay, reseal_readme)
            self.assert_rejected(
                self.run_verifier(alternate_overlay),
                "authoring alternate overlay bytes differ from the checkout",
            )

    def test_authoring_late_alternate_overlay_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            alternate_overlay = self.copy_overlay(Path(directory))
            expected_manifest_digest = "sha256:" + raw_digest(
                alternate_overlay / "manifest.json"
            )
            original_final_binding = (
                self.verifier.verify_authoring_overlay_matches_checkout
            )
            mutated = False

            def mutate_at_final_binding(**kwargs):
                nonlocal mutated
                self.assertFalse(mutated)
                mutated = True
                readme = alternate_overlay / "README.md"
                readme.write_bytes(readme.read_bytes() + b"\nlate overlay mutation\n")
                return original_final_binding(**kwargs)

            with self.configured_boundary(self.git_executable):
                with mock.patch.object(
                    self.verifier,
                    "verify_authoring_overlay_matches_checkout",
                    side_effect=mutate_at_final_binding,
                ):
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        "authoring alternate overlay changed after authentication",
                    ):
                        self.verifier._verify_configured(
                            expected_manifest_digest=expected_manifest_digest,
                            overlay_dir=alternate_overlay,
                            repo_root=self.authoring_root,
                            authoring_check=True,
                        )
            self.assertTrue(mutated)

    def test_authoring_late_root_attributes_mutation_is_rejected(self) -> None:
        overlay = self.authoring_root / "docs/execution/dags/generic-hive-mind-product-v3"
        attributes = self.authoring_root / ".gitattributes"
        original_raw = attributes.read_bytes()
        expected_manifest_digest = "sha256:" + raw_digest(overlay / "manifest.json")
        original_final_binding = self.verifier.verify_authoring_overlay_matches_checkout
        mutated = False

        def mutate_at_final_binding(**kwargs):
            nonlocal mutated
            self.assertFalse(mutated)
            mutated = True
            attributes.write_bytes(original_raw + b"*.hostile filter=hostile\n")
            return original_final_binding(**kwargs)

        try:
            with self.configured_boundary(self.git_executable):
                with mock.patch.object(
                    self.verifier,
                    "verify_authoring_overlay_matches_checkout",
                    side_effect=mutate_at_final_binding,
                ):
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        "authoring alternate overlay bytes differ from the checkout: .gitattributes",
                    ):
                        self.verifier._verify_configured(
                            expected_manifest_digest=expected_manifest_digest,
                            overlay_dir=overlay,
                            repo_root=self.authoring_root,
                            authoring_check=True,
                        )
        finally:
            attributes.write_bytes(original_raw)
        self.assertTrue(mutated)

    def test_authoring_late_nested_attributes_creation_is_rejected(self) -> None:
        overlay = self.authoring_root / "docs/execution/dags/generic-hive-mind-product-v3"
        nested_attributes = self.authoring_root / "docs" / ".gitattributes"
        expected_manifest_digest = "sha256:" + raw_digest(overlay / "manifest.json")
        original_final_binding = self.verifier.verify_authoring_overlay_matches_checkout
        mutated = False

        def mutate_at_final_binding(**kwargs):
            nonlocal mutated
            self.assertFalse(mutated)
            mutated = True
            nested_attributes.write_text("* filter=hostile\n", encoding="utf-8")
            return original_final_binding(**kwargs)

        try:
            with self.configured_boundary(self.git_executable):
                with mock.patch.object(
                    self.verifier,
                    "verify_authoring_overlay_matches_checkout",
                    side_effect=mutate_at_final_binding,
                ):
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        r"applicable nested \.gitattributes is forbidden.*docs/\.gitattributes",
                    ):
                        self.verifier._verify_configured(
                            expected_manifest_digest=expected_manifest_digest,
                            overlay_dir=overlay,
                            repo_root=self.authoring_root,
                            authoring_check=True,
                        )
        finally:
            nested_attributes.unlink(missing_ok=True)
        self.assertTrue(mutated)

    def test_default_mode_requires_exact_committed_payload_and_caller_manifest_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            result = self.run_verifier(overlay, repo_root=checkout, authoring_check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verification_mode"], V5_COMMITTED_MODE)
            self.assertTrue(payload["committed_payload_qualification"])
            self.assertFalse(payload["execution_qualification"])
            self.assertFalse(payload["execution"]["authorized"])
            self.assertEqual(
                set(payload["autopilot_tree"]),
                {
                    "schema",
                    "entry_count",
                    "total_file_bytes",
                    "snapshot_digest",
                    "observed_unchanged",
                    "concurrent_mutation_exclusion",
                    "requires_external_read_only_custody_for_execution",
                },
            )
            self.assertNotIn("unchanged", payload["autopilot_tree"])
            self.assertEqual(
                payload["autopilot_tree"]["schema"],
                "complete-autopilot-tree-point-observation-v2",
            )
            self.assertIs(payload["autopilot_tree"]["observed_unchanged"], True)
            self.assertIs(
                payload["autopilot_tree"]["concurrent_mutation_exclusion"],
                False,
            )
            self.assertIs(
                payload["autopilot_tree"][
                    "requires_external_read_only_custody_for_execution"
                ],
                True,
            )
            self.assertEqual(payload["committed_payload"]["authoring_base_parent"], PLAN_AUTHORING_BASE)
            self.assertEqual(payload["committed_payload"]["correction_parent"], CORRECTION_PARENT)
            self.assertEqual(
                payload["committed_payload"]["head"],
                self.run_git(checkout, "rev-parse", "HEAD").stdout.strip(),
            )
            missing = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=False,
                include_expected_manifest=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("--expected-manifest-digest", missing.stderr)

    def test_committed_mode_rejects_detached_head_and_wrong_live_branch(self) -> None:
        for state in ("detached", "wrong_branch"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                checkout = self.make_committed_checkout(Path(directory))
                overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
                if state == "detached":
                    self.run_git(checkout, "switch", "--quiet", "--detach", "HEAD")
                else:
                    self.run_git(
                        checkout,
                        "switch",
                        "--quiet",
                        "-c",
                        "hostile/wrong-live-branch",
                    )
                self.assert_rejected(
                    self.run_verifier(
                        overlay,
                        repo_root=checkout,
                        authoring_check=False,
                    ),
                    "live branch mismatch",
                )

    def test_manifest_digest_malformed_wrong_and_changed_bindings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            malformed = self.run_verifier(
                overlay,
                expected_manifest_digest="sha256:not-a-digest",
            )
            self.assert_rejected(
                malformed,
                "caller must supply a canonical expected manifest SHA-256",
            )

            wrong = self.run_verifier(
                overlay,
                expected_manifest_digest="sha256:" + "0" * 64,
            )
            self.assert_rejected(wrong, "caller-authenticated manifest digest mismatch")

            expected_before_change = "sha256:" + raw_digest(overlay / "manifest.json")
            manifest = overlay / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" ")
            changed = self.run_verifier(
                overlay,
                expected_manifest_digest=expected_before_change,
            )
            self.assert_rejected(changed, "caller-authenticated manifest digest mismatch")

    def test_default_mode_refuses_precommit_extra_commit_wrong_parent_and_path_change(self) -> None:
        overlay = self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
        self.assert_rejected(
            self.run_verifier(
                overlay,
                repo_root=self.authoring_root,
                authoring_check=False,
            ),
            "committed payload must be one non-merge direct child of the correction parent",
        )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            self.run_git(checkout, "commit", "--quiet", "--allow-empty", "-m", "unexpected second commit")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload must be one non-merge direct child of the correction parent",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory), base=CORRECTION_PARENT + "^")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload must be one non-merge direct child of the correction parent",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory), extra_path=True)
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload changed-path allowlist mismatch",
            )

    def test_default_mode_refuses_dirty_staged_and_other_untracked_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            readme = overlay / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "dirty\n", encoding="utf-8")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload size mismatch: docs/execution/dags/generic-hive-mind-product-v3/README.md",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            readme = overlay / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "staged\n", encoding="utf-8")
            self.run_git(checkout, "add", "--", "docs/execution/dags/generic-hive-mind-product-v3/README.md")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload size mismatch: docs/execution/dags/generic-hive-mind-product-v3/README.md",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            (checkout / "unapproved.txt").write_text("untracked\n", encoding="utf-8")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed checkout contains an unapproved untracked or ignored path",
            )

    def test_git_boundary_rejects_case_insensitive_ambient_overrides(self) -> None:
        overlay = self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"
        poison_path = str(self.authoring_root / ".git" / "poison")
        overrides = (
            ("GIT_WORK_TREE", poison_path),
            ("GIT_DIR", poison_path),
            ("gIt_CoMmOn_DiR", poison_path),
            ("GIT_INDEX_FILE", poison_path),
            ("GIT_OBJECT_DIRECTORY", poison_path),
            ("GIT_ALTERNATE_OBJECT_DIRECTORIES", poison_path),
            ("GIT_CONFIG_GLOBAL", poison_path),
            ("GIT_CONFIG_SYSTEM", poison_path),
            ("GIT_CONFIG_COUNT", "1"),
            ("GIT_CONFIG_KEY_0", "core.fsmonitor"),
            ("GIT_CONFIG_VALUE_0", "hostile"),
            ("gIt_CoNfIg_PaRaMeTeRs", "'core.fsmonitor=hostile'"),
            ("GIT_EXEC_PATH", poison_path),
            ("GIT_PAGER", "hostile"),
            ("GIT_EXTERNAL_DIFF", "hostile"),
            ("GIT_REPLACE_REF_BASE", "refs/replace/hostile"),
        )
        for key, value in overrides:
            with self.subTest(key=key):
                result = self.run_verifier(
                    overlay,
                    environment_updates={key: value},
                )
                self.assert_rejected(result, "inherited Git environment is forbidden")
                error = json.loads(result.stdout.strip().splitlines()[-1])["error"]
                self.assertIn(key.casefold(), error.casefold())

    def test_git_boundary_binds_absolute_executable_digest_and_ignores_path(self) -> None:
        overlay = self.authoring_root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v3"

        relative = self.run_verifier(overlay, git_executable=Path("git"))
        self.assert_rejected(relative, "Git executable path must be absolute")

        missing_digest = self.run_verifier(
            overlay,
            include_expected_git_digest=False,
        )
        self.assertNotEqual(missing_digest.returncode, 0)
        self.assertIn("--expected-git-executable-sha256", missing_digest.stderr)

        malformed_digest = self.run_verifier(
            overlay,
            git_executable_sha256="sha256:not-a-digest",
        )
        self.assert_rejected(
            malformed_digest,
            "canonical expected Git executable SHA-256",
        )

        wrong_digest = self.run_verifier(
            overlay,
            git_executable_sha256="sha256:" + "0" * 64,
        )
        self.assert_rejected(wrong_digest, "caller-authenticated Git executable digest mismatch")

        with tempfile.TemporaryDirectory() as directory:
            changed_git = self.copy_git_executable(Path(directory))
            original_digest = "sha256:" + raw_digest(changed_git)
            with changed_git.open("r+b") as handle:
                handle.seek(-1, os.SEEK_END)
                original = handle.read(1)
                self.assertTrue(original)
                handle.seek(-1, os.SEEK_END)
                handle.write(bytes([original[0] ^ 0xFF]))
                handle.flush()
                os.fsync(handle.fileno())
            changed_digest = self.run_verifier(
                overlay,
                git_executable=changed_git,
                git_executable_sha256=original_digest,
            )
        self.assert_rejected(
            changed_digest,
            "caller-authenticated Git executable digest mismatch",
        )

        with tempfile.TemporaryDirectory() as directory:
            fake_directory = Path(directory) / "fake-path"
            fake_directory.mkdir()
            fake_git = fake_directory / ("git.exe" if os.name == "nt" else "git")
            if os.name == "nt":
                fake_git.write_bytes(b"not a Git executable\n")
            else:
                fake_git.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
                fake_git.chmod(0o755)
            result = self.run_verifier(
                overlay,
                environment_updates={"PATH": str(fake_directory)},
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["git_boundary"]["executable"], str(self.git_executable))
        self.assertEqual(payload["git_boundary"]["executable_sha256"], self.git_executable_sha256)
        self.assertEqual(
            payload["git_boundary"]["native_executable_format_policy"],
            "host-native-image-format-v1",
        )
        self.assertEqual(
            payload["git_boundary"]["native_executable_format"],
            self.verifier.SUPPORTED_NATIVE_IMAGE_FORMATS[sys.platform],
        )
        self.assertFalse(payload["git_boundary"]["path_lookup"])

    def test_git_boundary_rejects_noncanonical_executable_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = self.copy_git_executable(root)
            detour = root / "detour"
            detour.mkdir()
            noncanonical = detour / ".." / executable.name
            self.assertTrue(noncanonical.is_absolute())
            self.assertNotEqual(noncanonical, noncanonical.resolve(strict=True))
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assert_configuration_rejected(
                    lambda: self.verifier.configure_git_boundary(
                        self.authoring_root,
                        git_executable=noncanonical,
                        expected_git_executable_sha256="sha256:" + raw_digest(executable),
                    ),
                    "path must already be canonical",
                )

    def test_git_boundary_rejects_symlink_executable_path_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = self.copy_git_executable(root)
            link = root / ("linked-git.exe" if os.name == "nt" else "linked-git")
            try:
                link.symlink_to(executable)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"file symlinks are unavailable: {error}")
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assert_configuration_rejected(
                    lambda: self.verifier.configure_git_boundary(
                        self.authoring_root,
                        git_executable=link.absolute(),
                        expected_git_executable_sha256="sha256:" + raw_digest(executable),
                    ),
                    "Git executable symlinks are forbidden",
                )

    def test_script_wrapper_and_non_native_image_are_rejected_before_popen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "wrapper.marker"
            if os.name == "nt":
                wrapper = root / "git.cmd"
                wrapper.write_text(
                    f'@echo executed>"{marker}"\r\n@"{self.git_executable}" %*\r\n',
                    encoding="utf-8",
                )
            else:
                wrapper = root / "git"
                wrapper.write_text(
                    "#!/bin/sh\n"
                    f"printf executed > {shell_command([str(marker)])}\n"
                    f"exec {shell_command([str(self.git_executable)])} \"$@\"\n",
                    encoding="utf-8",
                )
                wrapper.chmod(0o755)

            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                self.verifier.subprocess,
                "Popen",
            ) as popen:
                self.assert_configuration_rejected(
                    lambda: self.verifier.configure_git_boundary(
                        self.authoring_root,
                        git_executable=wrapper.resolve(strict=True),
                        expected_git_executable_sha256="sha256:" + raw_digest(wrapper),
                    ),
                    "(?i)native|script|format|\\.exe",
                )
                popen.assert_not_called()
            self.assertFalse(marker.exists())

            non_native = root / ("non-native.exe" if os.name == "nt" else "non-native")
            non_native.write_bytes(b"not a native executable image\n")
            if os.name != "nt":
                non_native.chmod(0o755)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                self.verifier.subprocess,
                "Popen",
            ) as popen:
                self.assert_configuration_rejected(
                    lambda: self.verifier.configure_git_boundary(
                        self.authoring_root,
                        git_executable=non_native.resolve(strict=True),
                        expected_git_executable_sha256="sha256:" + raw_digest(non_native),
                    ),
                    "(?i)native|format|image|header",
                )
                popen.assert_not_called()

            with mock.patch.dict(os.environ, {}, clear=True):
                self.assert_configuration_rejected(
                    lambda: self.verifier.configure_git_boundary(
                        self.authoring_root,
                        git_executable=wrapper.resolve(strict=True),
                        expected_git_executable_sha256=self.git_executable_sha256,
                    ),
                    "(?i)script wrappers are forbidden|digest mismatch|native \\.exe",
                )
            self.assertFalse(marker.exists())

    def test_native_image_parser_covers_pe_elf_macho_and_actual_host_git(self) -> None:
        valid_fixtures = (
            ("pe", synthetic_pe_x86(), "win32", "x86", "PE_COFF_EXECUTABLE_IMAGE"),
            ("elf", synthetic_elf_x86_64(), "linux", "x86_64", "ELF_EXEC_OR_PIE_WITH_EXECUTABLE_LOAD_SEGMENT"),
            ("macho_thin", synthetic_macho_x86_64(), "darwin", "x86_64", "MACH_O_EXECUTE_THIN_OR_HOST_SLICE_UNIVERSAL"),
            ("macho_fat", synthetic_macho_fat_x86_64(), "darwin", "x86_64", "MACH_O_EXECUTE_THIN_OR_HOST_SLICE_UNIVERSAL"),
        )
        for label, raw, platform, machine, expected_format in valid_fixtures:
            with self.subTest(label=label, disposition="valid"):
                result = self.assert_autopilot_preserved(
                    lambda: self.verifier._inspect_native_image(raw, platform, machine)
                )
                self.assertEqual(
                    result,
                    {
                        "policy": "host-native-image-format-v1",
                        "host_platform": platform,
                        "host_machine": machine,
                        "native_executable_format": expected_format,
                    },
                )

        forged_pe = bytearray(synthetic_pe_x86())
        forged_pe[0x80:0x84] = b"PX\0\0"
        malformed_pe_optional = bytearray(synthetic_pe_x86())
        struct.pack_into("<H", malformed_pe_optional, 0x94, 95)
        malformed_pe_range = bytearray(synthetic_pe_x86())
        struct.pack_into("<I", malformed_pe_range, 0x10C, len(malformed_pe_range))
        malformed_pe_nonexec_range = bytearray(synthetic_pe_x86())
        struct.pack_into("<H", malformed_pe_nonexec_range, 0x86, 2)
        second_section = 0x120
        malformed_pe_nonexec_range[second_section : second_section + 8] = b".data\0\0\0"
        struct.pack_into("<I", malformed_pe_nonexec_range, second_section + 8, 0x80)
        struct.pack_into("<I", malformed_pe_nonexec_range, second_section + 12, 0x1800)
        struct.pack_into("<I", malformed_pe_nonexec_range, second_section + 16, 0x20)
        struct.pack_into(
            "<I",
            malformed_pe_nonexec_range,
            second_section + 20,
            len(malformed_pe_nonexec_range) + 0x100,
        )
        struct.pack_into("<I", malformed_pe_nonexec_range, second_section + 36, 0x40000040)
        malformed_pe_virtual_range = bytearray(synthetic_pe_x86())
        struct.pack_into("<I", malformed_pe_virtual_range, 0x104, 0x1F80)
        struct.pack_into("<I", malformed_pe_virtual_range, 0x100, 0x200)
        zero_pe_entry = bytearray(synthetic_pe_x86())
        struct.pack_into("<I", zero_pe_entry, 0xA8, 0)
        uncovered_pe_entry = bytearray(synthetic_pe_x86())
        struct.pack_into("<I", uncovered_pe_entry, 0xA8, 0x3000)

        forged_elf = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<I", forged_elf, 68, 0)
        malformed_elf_range = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<Q", malformed_elf_range, 72, len(malformed_elf_range) - 0x20)
        huge_elf_header = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<H", huge_elf_header, 52, 0xFFFF)
        overlapping_elf_header = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<Q", overlapping_elf_header, 32, 32)
        zero_elf_entry = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<Q", zero_elf_entry, 24, 0)
        uncovered_elf_entry = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<Q", uncovered_elf_entry, 24, 0x500000)
        non_file_backed_elf_entry = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<Q", non_file_backed_elf_entry, 24, 0x401080)
        struct.pack_into("<Q", non_file_backed_elf_entry, 96, 0x40)
        shared_object_not_pie = bytearray(synthetic_elf_x86_64())
        struct.pack_into("<H", shared_object_not_pie, 16, 3)

        forged_macho = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<I", forged_macho, 12, 1)
        malformed_macho_segment = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<Q", malformed_macho_segment, 72, 0xF0)
        struct.pack_into("<Q", malformed_macho_segment, 80, 0x20)
        oversized_macho_segment = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<Q", oversized_macho_segment, 80, 0x2000)
        zero_macho_entry = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<Q", zero_macho_entry, 112, 0)
        uncovered_macho_entry = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<Q", uncovered_macho_entry, 112, 0x200)
        wrong_thin_subtype = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<I", wrong_thin_subtype, 8, 4)
        unproven_x86_64h_subtype = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<I", unproven_x86_64h_subtype, 8, 8)
        misaligned_macho_command = bytearray(synthetic_macho_x86_64())
        struct.pack_into("<I", misaligned_macho_command, 36, 76)
        misaligned_fat = bytearray(synthetic_macho_fat_x86_64())
        struct.pack_into(">I", misaligned_fat, 16, 0x1001)
        wrong_fat_subtype = bytearray(synthetic_macho_fat_x86_64())
        struct.pack_into(">I", wrong_fat_subtype, 12, 4)

        invalid_fixtures = (
            ("pe_truncated", b"MZ", "win32", "x86"),
            ("pe_forged", bytes(forged_pe), "win32", "x86"),
            ("pe_optional", bytes(malformed_pe_optional), "win32", "x86"),
            ("pe_range", bytes(malformed_pe_range), "win32", "x86"),
            ("pe_nonexec_range", bytes(malformed_pe_nonexec_range), "win32", "x86"),
            ("pe_virtual_range", bytes(malformed_pe_virtual_range), "win32", "x86"),
            ("pe_zero_entry", bytes(zero_pe_entry), "win32", "x86"),
            ("pe_uncovered_entry", bytes(uncovered_pe_entry), "win32", "x86"),
            ("pe_wrong_host", synthetic_pe_x86(), "win32", "x86_64"),
            ("elf_truncated", b"\x7fELF", "linux", "x86_64"),
            ("elf_forged", bytes(forged_elf), "linux", "x86_64"),
            ("elf_range", bytes(malformed_elf_range), "linux", "x86_64"),
            ("elf_huge_header", bytes(huge_elf_header), "linux", "x86_64"),
            ("elf_header_overlap", bytes(overlapping_elf_header), "linux", "x86_64"),
            ("elf_zero_entry", bytes(zero_elf_entry), "linux", "x86_64"),
            ("elf_uncovered_entry", bytes(uncovered_elf_entry), "linux", "x86_64"),
            ("elf_non_file_backed_entry", bytes(non_file_backed_elf_entry), "linux", "x86_64"),
            ("elf_shared_object_not_pie", bytes(shared_object_not_pie), "linux", "x86_64"),
            ("elf_wrong_host", synthetic_elf_x86_64(), "linux", "arm64"),
            ("macho_truncated", b"\xcf\xfa\xed\xfe", "darwin", "x86_64"),
            ("macho_forged", bytes(forged_macho), "darwin", "x86_64"),
            ("macho_segment_range", bytes(malformed_macho_segment), "darwin", "x86_64"),
            ("macho_segment_size", bytes(oversized_macho_segment), "darwin", "x86_64"),
            ("macho_zero_entry", bytes(zero_macho_entry), "darwin", "x86_64"),
            ("macho_uncovered_entry", bytes(uncovered_macho_entry), "darwin", "x86_64"),
            ("macho_thin_subtype", bytes(wrong_thin_subtype), "darwin", "x86_64"),
            ("macho_unproven_x86_64h", bytes(unproven_x86_64h_subtype), "darwin", "x86_64"),
            ("macho_command_alignment", bytes(misaligned_macho_command), "darwin", "x86_64"),
            ("macho_fat_alignment", bytes(misaligned_fat), "darwin", "x86_64"),
            ("macho_fat_subtype", bytes(wrong_fat_subtype), "darwin", "x86_64"),
            ("macho_wrong_host", synthetic_macho_x86_64(), "darwin", "arm64"),
            ("script_wrapper", b"#!/bin/sh\nexec git \"$@\"\n", "linux", "x86_64"),
            ("wrong_platform_format", synthetic_elf_x86_64(), "win32", "x86_64"),
        )
        for label, raw, platform, machine in invalid_fixtures:
            with self.subTest(label=label, disposition="rejected"):
                with self.assertRaises(self.verifier.VerificationError):
                    self.assert_autopilot_preserved(
                        lambda: self.verifier._inspect_native_image(raw, platform, machine)
                    )

        host_platform = sys.platform
        host_machine = self.verifier._current_host_machine(host_platform)
        actual = self.assert_autopilot_preserved(
            lambda: self.verifier._inspect_native_image(
                self.git_executable.read_bytes(),
                host_platform,
                host_machine,
            )
        )
        self.assertEqual(actual["policy"], "host-native-image-format-v1")
        self.assertEqual(actual["host_platform"], host_platform)
        self.assertEqual(actual["host_machine"], host_machine)
        self.assertEqual(
            actual["native_executable_format"],
            self.verifier.SUPPORTED_NATIVE_IMAGE_FORMATS[host_platform],
        )

    def test_git_executable_mutation_before_popen_is_rejected_without_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            with self.configured_boundary(executable):
                self.mutate_executable(executable)
                with mock.patch.object(self.verifier.subprocess, "Popen") as popen:
                    self.assert_executable_changed(
                        lambda: self.verifier.git(self.authoring_root, "--version")
                    )
                    popen.assert_not_called()

    def test_git_executable_mutation_in_popen_construction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))

            def mutate_then_fail(*args, **kwargs):
                del args, kwargs
                self.mutate_executable(executable)
                raise OSError("synthetic construction failure")

            with self.configured_boundary(executable):
                with mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    side_effect=mutate_then_fail,
                ) as popen:
                    self.assert_executable_changed(
                        lambda: self.verifier.git(self.authoring_root, "--version")
                    )
                    popen.assert_called_once()

    def test_git_executable_mutation_during_wait_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))

            def mutate_on_wait(process, timeout, call_number):
                del process, timeout
                if call_number == 1:
                    self.mutate_executable(executable)

            process = FakeProcess(wait_action=mutate_on_wait)
            with self.configured_boundary(executable):
                with mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ):
                    self.assert_executable_changed(
                        lambda: self.verifier.git(self.authoring_root, "--version")
                    )

    def test_git_executable_mutation_after_wait_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess()

            def thread_factory(*args, **kwargs):
                del args
                return DeferredThread(kwargs["target"], lambda: self.mutate_executable(executable))

            with self.configured_boundary(executable):
                with mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ), mock.patch.object(
                    self.verifier.threading,
                    "Thread",
                    side_effect=thread_factory,
                ):
                    self.assert_executable_changed(
                        lambda: self.verifier.git(self.authoring_root, "--version")
                    )
            self.assertEqual(process.wait_calls, 1)

    def test_path_and_retained_identity_mutations_are_rejected_before_popen(self) -> None:
        for label, identity_function in (
            ("path", "_git_executable_path_state"),
            ("retained_handle", "_open_file_identity"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                executable = self.copy_git_executable(Path(directory))
                with self.configured_boundary(executable) as boundary:
                    baseline = list(
                        boundary["path_state" if label == "path" else "handle_identity"]
                    )
                    baseline[3] += 1
                    with mock.patch.object(
                        self.verifier,
                        identity_function,
                        return_value=tuple(baseline),
                    ), mock.patch.object(self.verifier.subprocess, "Popen") as popen:
                        self.assert_executable_changed(
                            lambda: self.verifier.git(self.authoring_root, "--version")
                        )
                        popen.assert_not_called()

    def test_git_executable_continuity_keys_are_platform_scoped(self) -> None:
        baseline = (11, 22, 33, 44, 55, 66)
        ctime_drift = (11, 22, 33, 44, 99, 66)
        self.assertEqual(
            self.verifier._git_executable_continuity_key(
                baseline,
                host_platform="win32",
            ),
            self.verifier._git_executable_continuity_key(
                ctime_drift,
                host_platform="win32",
            ),
        )
        self.assertNotEqual(
            self.verifier._git_executable_continuity_key(
                baseline,
                host_platform="linux",
            ),
            self.verifier._git_executable_continuity_key(
                ctime_drift,
                host_platform="linux",
            ),
        )
        legacy = (11, 22, 33, 44, 55, None)
        self.assertEqual(
            self.verifier._git_executable_continuity_key(
                legacy,
                host_platform="win32",
            ),
            (11, 22, 33, 44, 55),
        )
        for field in (0, 1, 2, 3, 5):
            with self.subTest(windows_continuity_field=field):
                mutated = list(baseline)
                mutated[field] += 1
                self.assertNotEqual(
                    self.verifier._git_executable_continuity_key(
                        baseline,
                        host_platform="win32",
                    ),
                    self.verifier._git_executable_continuity_key(
                        tuple(mutated),
                        host_platform="win32",
                    ),
                )

    @unittest.skipUnless(sys.platform == "win32", "requires a native Windows Git executable")
    def test_windows_ctime_drift_accepts_stable_bytes_and_rejects_changed_bytes_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess(b"git version synthetic\n")
            with self.configured_boundary(executable) as boundary:
                birthtime = 1776656106008279900
                path_identity = tuple(boundary["path_state"][:5]) + (birthtime,)
                handle_identity = tuple(boundary["handle_identity"][:5]) + (birthtime,)
                boundary["path_state"] = path_identity
                boundary["handle_identity"] = handle_identity
                boundary["identity_platform"] = "win32"
                path_drift = list(path_identity)
                handle_drift = list(handle_identity)
                path_drift[4] += 100
                handle_drift[4] += 200
                with mock.patch.object(
                    self.verifier,
                    "_git_executable_path_state",
                    return_value=tuple(path_drift),
                ), mock.patch.object(
                    self.verifier,
                    "_open_file_identity",
                    return_value=tuple(handle_drift),
                ), mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ) as popen:
                    self.assertEqual(
                        self.verifier.git(self.authoring_root, "--version"),
                        "git version synthetic",
                    )
                    popen.assert_called_once()

        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            with self.configured_boundary(executable) as boundary:
                birthtime = 1776656106008279900
                path_identity = tuple(boundary["path_state"][:5]) + (birthtime,)
                handle_identity = tuple(boundary["handle_identity"][:5]) + (birthtime,)
                boundary["path_state"] = path_identity
                boundary["handle_identity"] = handle_identity
                boundary["identity_platform"] = "win32"
                path_drift = list(path_identity)
                handle_drift = list(handle_identity)
                path_drift[4] += 100
                handle_drift[4] += 200
                changed = bytearray(executable.read_bytes())
                changed[-1] ^= 0xFF
                original_handle = boundary["handle"]
                original_handle.close()
                boundary["handle"] = io.BytesIO(changed)
                with mock.patch.object(
                    self.verifier,
                    "_git_executable_path_state",
                    return_value=tuple(path_drift),
                ), mock.patch.object(
                    self.verifier,
                    "_open_file_identity",
                    return_value=tuple(handle_drift),
                ), mock.patch.object(self.verifier.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        "retained Git executable bytes changed",
                    ):
                        self.verifier.git(self.authoring_root, "--version")
                    popen.assert_not_called()

    def test_native_format_and_digest_mutations_are_detected_at_lifecycle_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))

            def mutate_format_then_fail(*args, **kwargs):
                del args, kwargs
                self.mutate_executable(executable)
                raise OSError("synthetic Popen construction failure")

            with self.configured_boundary(executable) as boundary:
                with mock.patch.object(
                    self.verifier,
                    "_git_executable_path_state",
                    return_value=boundary["path_state"],
                ), mock.patch.object(
                    self.verifier,
                    "_open_file_identity",
                    return_value=boundary["handle_identity"],
                ), mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    side_effect=mutate_format_then_fail,
                ):
                    with self.assertRaises(self.verifier.VerificationError) as raised:
                        self.verifier.git(self.authoring_root, "--version")
            self.assertRegex(str(raised.exception), "(?i)PE|ELF|Mach-O|native|magic|header")

        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))

            def mutate_digest_on_wait(process, timeout, call_number):
                del process, timeout
                if call_number == 1:
                    self.mutate_executable_digest_only(executable)

            process = FakeProcess(wait_action=mutate_digest_on_wait)
            with self.configured_boundary(executable) as boundary:
                with mock.patch.object(
                    self.verifier,
                    "_git_executable_path_state",
                    return_value=boundary["path_state"],
                ), mock.patch.object(
                    self.verifier,
                    "_open_file_identity",
                    return_value=boundary["handle_identity"],
                ), mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ):
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        "bytes changed",
                    ):
                        self.verifier.git(self.authoring_root, "--version")

    def test_digest_mutation_between_calls_is_rejected_before_second_popen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess(b"first call\n")
            with self.configured_boundary(executable) as boundary:
                with mock.patch.object(
                    self.verifier,
                    "_git_executable_path_state",
                    return_value=boundary["path_state"],
                ), mock.patch.object(
                    self.verifier,
                    "_open_file_identity",
                    return_value=boundary["handle_identity"],
                ), mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ) as popen:
                    self.assertEqual(
                        self.verifier.git(self.authoring_root, "--version"),
                        "first call",
                    )
                    self.mutate_executable_digest_only(executable)
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        "bytes changed",
                    ):
                        self.verifier.git(self.authoring_root, "status")
                    popen.assert_called_once()

    def test_outer_verify_finally_rechecks_digest_after_apparent_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            expected_git_digest = "sha256:" + raw_digest(executable)
            overlay = self.authoring_root / "docs/execution/dags/generic-hive-mind-product-v3"
            expected_manifest_digest = "sha256:" + raw_digest(overlay / "manifest.json")
            original_path_state = self.verifier._git_executable_path_state
            original_open_identity = self.verifier._open_file_identity

            def frozen_path_state(path):
                boundary = self.verifier._GIT_BOUNDARY
                return boundary["path_state"] if boundary is not None else original_path_state(path)

            def frozen_open_identity(handle):
                boundary = self.verifier._GIT_BOUNDARY
                return (
                    boundary["handle_identity"]
                    if boundary is not None
                    else original_open_identity(handle)
                )

            def apparent_success(**kwargs):
                del kwargs
                self.mutate_executable_digest_only(executable)
                return {"verified": True}

            def verify_action():
                with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                    self.verifier,
                    "_git_executable_path_state",
                    side_effect=frozen_path_state,
                ), mock.patch.object(
                    self.verifier,
                    "_open_file_identity",
                    side_effect=frozen_open_identity,
                ), mock.patch.object(
                    self.verifier,
                    "_verify_configured",
                    side_effect=apparent_success,
                ):
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        "bytes changed",
                    ):
                        self.verifier.verify(
                            expected_manifest_digest=expected_manifest_digest,
                            git_executable=executable,
                            expected_git_executable_sha256=expected_git_digest,
                            overlay_dir=overlay,
                            repo_root=self.authoring_root,
                            authoring_check=True,
                        )

            self.assert_autopilot_preserved(verify_action)
            self.assertIsNone(self.verifier._GIT_BOUNDARY)

    def test_outer_verify_preserves_primary_and_serializes_cleanup_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            overlay = self.authoring_root / "docs/execution/dags/generic-hive-mind-product-v3"
            primary = self.verifier.GitTimeoutError("synthetic primary timeout")
            cleanup = self.verifier.VerificationError("synthetic cleanup revalidation")

            def verify_action():
                with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                    self.verifier,
                    "_verify_configured",
                    side_effect=primary,
                ), mock.patch.object(
                    self.verifier,
                    "verify_git_executable_stable",
                    side_effect=cleanup,
                ):
                    with self.assertRaises(self.verifier.GitTimeoutError) as raised:
                        self.verifier.verify(
                            expected_manifest_digest="sha256:" + raw_digest(overlay / "manifest.json"),
                            git_executable=executable,
                            expected_git_executable_sha256="sha256:" + raw_digest(executable),
                            overlay_dir=overlay,
                            repo_root=self.authoring_root,
                            authoring_check=True,
                        )
                payload = self.verifier.verification_error_payload(raised.exception)
                self.assertEqual(payload["code"], "GIT_TIMEOUT")
                self.assertEqual(payload["primary_code"], "GIT_TIMEOUT")
                self.assertEqual(
                    payload["cleanup_evidence"],
                    [
                        {
                            "code": "VERIFICATION_ERROR",
                            "error_type": "VerificationError",
                            "error": "synthetic cleanup revalidation",
                        }
                    ],
                )

            self.assert_autopilot_preserved(verify_action)
            self.assertIsNone(self.verifier._GIT_BOUNDARY)

    def test_outer_verify_detects_hidden_and_system_attribute_mutation(self) -> None:
        self.require_windows_file_attribute_support()
        target = self.authoring_root / ".autopilot" / "plan.json"
        original_state = target.stat()
        original_attributes = windows_file_attributes(target)
        original_times = (original_state.st_atime_ns, original_state.st_mtime_ns)

        def restore() -> None:
            set_windows_file_attributes(target, original_attributes)
            os.utime(target, ns=original_times)

        try:
            for attribute_name, attribute_flag in (
                ("hidden", WINDOWS_FILE_ATTRIBUTE_HIDDEN),
                ("system", WINDOWS_FILE_ATTRIBUTE_SYSTEM),
            ):
                requested_attributes = original_attributes | attribute_flag

                def mutate() -> None:
                    set_windows_file_attributes(target, requested_attributes)
                    os.utime(target, ns=original_times)
                    self.assertEqual(
                        windows_file_attributes(target) & attribute_flag,
                        attribute_flag,
                    )
                    self.assertEqual(target.stat().st_mtime_ns, original_times[1])

                for primary_failure in (False, True):
                    with self.subTest(
                        attribute=attribute_name,
                        primary_failure=primary_failure,
                    ):
                        self.assert_outer_verify_autopilot_mutation(
                            mutate=mutate,
                            restore=restore,
                            primary_failure=primary_failure,
                        )
        finally:
            restore()

    def test_outer_verify_detects_named_stream_mutation(self) -> None:
        self.require_windows_named_stream_support()
        target = self.authoring_root / ".autopilot" / "plan.json"
        stream_name = ":hive_mind_outer_verify_probe:$DATA"
        stream_path = Path(f"{target}:hive_mind_outer_verify_probe")
        original_state = target.stat()
        original_times = (original_state.st_atime_ns, original_state.st_mtime_ns)
        self.assertNotIn(
            stream_name,
            {row[0] for row in windows_stream_snapshot(target)},
            "the lifecycle ADS fixture name is already present",
        )

        def mutate() -> None:
            raw = b"named stream mutation with restored timestamps"
            stream_path.write_bytes(raw)
            os.utime(target, ns=original_times)
            streams = {row[0]: row for row in windows_stream_snapshot(target)}
            self.assertEqual(
                streams[stream_name],
                (stream_name, len(raw), hashlib.sha256(raw).hexdigest()),
            )
            self.assertEqual(target.stat().st_mtime_ns, original_times[1])

        def restore() -> None:
            stream_path.unlink(missing_ok=True)
            os.utime(target, ns=original_times)

        try:
            for primary_failure in (False, True):
                with self.subTest(primary_failure=primary_failure):
                    self.assert_outer_verify_autopilot_mutation(
                        mutate=mutate,
                        restore=restore,
                        primary_failure=primary_failure,
                        expected_cleanup_pattern=(
                            r"(?i)named Windows data stream is forbidden for "
                            r"\.autopilot file"
                        ),
                    )
        finally:
            restore()

    def test_outer_verify_detects_named_directory_stream_mutation(self) -> None:
        self.require_windows_named_stream_support()
        target = self.authoring_root / ".autopilot" / "bin"
        stream_name = ":hive_mind_outer_directory_probe:$DATA"
        stream_path = Path(f"{target}:hive_mind_outer_directory_probe")
        original_state = target.stat()
        original_attributes = windows_file_attributes(target)
        original_times = (original_state.st_atime_ns, original_state.st_mtime_ns)
        self.assertNotIn(
            stream_name,
            {row[0] for row in windows_stream_snapshot(target)},
            "the directory ADS fixture name is already present",
        )
        try:
            stream_path.write_bytes(b"directory stream capability probe")
        except OSError as error:
            self.skipTest(
                "the test filesystem cannot create a named stream on a directory "
                f"(winerror={getattr(error, 'winerror', None)})"
            )
        finally:
            stream_path.unlink(missing_ok=True)
            set_windows_file_attributes(target, original_attributes)
            os.utime(target, ns=original_times)

        def mutate() -> None:
            raw = b"named directory stream mutation with restored timestamps"
            stream_path.write_bytes(raw)
            os.utime(target, ns=original_times)
            streams = {row[0]: row for row in windows_stream_snapshot(target)}
            self.assertEqual(
                streams[stream_name],
                (stream_name, len(raw), hashlib.sha256(raw).hexdigest()),
            )
            self.assertEqual(target.stat().st_mtime_ns, original_times[1])

        def restore() -> None:
            stream_path.unlink(missing_ok=True)
            set_windows_file_attributes(target, original_attributes)
            os.utime(target, ns=original_times)

        try:
            for primary_failure in (False, True):
                with self.subTest(primary_failure=primary_failure):
                    self.assert_outer_verify_autopilot_mutation(
                        mutate=mutate,
                        restore=restore,
                        primary_failure=primary_failure,
                        expected_cleanup_pattern=(
                            r"(?i)named Windows data stream is forbidden for "
                            r"\.autopilot directory"
                        ),
                    )
        finally:
            restore()

    def test_preexisting_file_and_directory_ads_are_rejected_initially(self) -> None:
        self.require_windows_named_stream_support()
        for kind in ("file", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                repo_root = Path(directory)
                autopilot = repo_root / ".autopilot"
                autopilot.mkdir()
                target = autopilot / f"{kind}-target"
                if kind == "file":
                    target.write_bytes(b"base data")
                else:
                    target.mkdir()
                stream_path = Path(f"{target}:hive_mind_preexisting_probe")
                state = target.stat()
                attributes = windows_file_attributes(target)
                original_times = (state.st_atime_ns, state.st_mtime_ns)
                try:
                    try:
                        stream_path.write_bytes(b"preexisting named stream")
                    except OSError as error:
                        self.skipTest(
                            f"cannot create a named stream on a {kind} test fixture "
                            f"(winerror={getattr(error, 'winerror', None)})"
                        )
                    os.utime(target, ns=original_times)
                    with self.assertRaisesRegex(
                        self.verifier.VerificationError,
                        rf"(?i)named Windows data stream.*{kind}",
                    ):
                        self.verifier.snapshot_autopilot_tree(repo_root)
                finally:
                    stream_path.unlink(missing_ok=True)
                    set_windows_file_attributes(target, attributes)
                    os.utime(target, ns=original_times)

    def test_outer_verify_detects_directory_hidden_and_system_attributes(self) -> None:
        self.require_windows_file_attribute_support()
        target = self.authoring_root / ".autopilot" / "bin"
        original_state = target.stat()
        original_attributes = windows_file_attributes(target)
        original_times = (original_state.st_atime_ns, original_state.st_mtime_ns)

        def restore() -> None:
            set_windows_file_attributes(target, original_attributes)
            os.utime(target, ns=original_times)

        try:
            for attribute_name, attribute_flag in (
                ("hidden", WINDOWS_FILE_ATTRIBUTE_HIDDEN),
                ("system", WINDOWS_FILE_ATTRIBUTE_SYSTEM),
            ):
                requested_attributes = original_attributes | attribute_flag

                def mutate() -> None:
                    set_windows_file_attributes(target, requested_attributes)
                    os.utime(target, ns=original_times)
                    self.assertEqual(
                        windows_file_attributes(target) & attribute_flag,
                        attribute_flag,
                    )
                    self.assertEqual(target.stat().st_mtime_ns, original_times[1])

                for primary_failure in (False, True):
                    with self.subTest(
                        attribute=attribute_name,
                        primary_failure=primary_failure,
                    ):
                        self.assert_outer_verify_autopilot_mutation(
                            mutate=mutate,
                            restore=restore,
                            primary_failure=primary_failure,
                        )
        finally:
            restore()

    def test_git_output_overflow_timeout_and_non_utf8_fail_closed(self) -> None:
        cases = (
            (
                "overflow",
                FakeProcess(b"x" * (self.verifier.MAX_GIT_OUTPUT_BYTES + 1)),
                self.verifier.GitOutputOverflowError,
                "GIT_OUTPUT_OVERFLOW",
                "Git output exceeds the verifier limit",
            ),
            (
                "non_utf8_success",
                FakeProcess(b"git-output-\xff\xfe"),
                self.verifier.GitNonUtf8Error,
                "GIT_NON_UTF8",
                "returned non-UTF-8 output",
            ),
            (
                "non_utf8_nonzero",
                FakeProcess(b"git-error-\xff\xfe", returncode=9),
                self.verifier.GitNonUtf8Error,
                "GIT_NON_UTF8",
                "returned non-UTF-8 output",
            ),
        )
        for label, process, expected_type, expected_code, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                executable = self.copy_git_executable(Path(directory))
                with self.configured_boundary(executable):
                    with mock.patch.object(
                        self.verifier.subprocess,
                        "Popen",
                        return_value=process,
                    ):
                        error = self.assert_git_error_code(
                            expected_type,
                            expected_code,
                            lambda: self.verifier.git(self.authoring_root, "status"),
                        )
                        self.assertIn(expected_error, str(error))
                if label == "overflow":
                    self.assertTrue(process.killed)

        def timeout_once(process, timeout, call_number):
            del process
            if call_number == 1:
                raise subprocess.TimeoutExpired("synthetic-git", timeout)

        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess(b"timeout-diagnostic-\xff\xfe", wait_action=timeout_once)
            with self.configured_boundary(executable):
                with mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ):
                    error = self.assert_git_error_code(
                        self.verifier.GitNonUtf8Error,
                        "GIT_NON_UTF8",
                        lambda: self.verifier.git(self.authoring_root, "status"),
                        primary_code="GIT_TIMEOUT",
                    )
                    self.assertIn("returned non-UTF-8 output", str(error))
            self.assertTrue(process.killed)
            self.assertEqual(process.wait_calls, 2)

    def test_valid_utf8_first_wait_timeout_is_typed_killed_and_reaped(self) -> None:
        def timeout_once(process, timeout, call_number):
            del process
            if call_number == 1:
                raise subprocess.TimeoutExpired("synthetic-git", timeout)

        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess(
                b"ordinary valid UTF-8 timeout diagnostic\n",
                wait_action=timeout_once,
            )
            with self.configured_boundary(executable):
                with mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ):
                    error = self.assert_git_error_code(
                        self.verifier.GitTimeoutError,
                        "GIT_TIMEOUT",
                        lambda: self.verifier.git(self.authoring_root, "status"),
                    )
            payload = self.verifier.verification_error_payload(error)
            self.assertEqual(payload["code"], "GIT_TIMEOUT")
            self.assertEqual(payload["primary_code"], "GIT_TIMEOUT")
            self.assertEqual(payload["cleanup_evidence"], [])
            self.assertNotIn("cleanup_evidence=", payload["error"])
            self.assertIn("ordinary valid UTF-8 timeout diagnostic", payload["error"])
            self.assertTrue(process.killed)
            self.assertEqual(process.wait_calls, 2)

    def test_second_timeout_after_kill_is_a_typed_verification_failure(self) -> None:
        def never_exits(process, timeout, call_number):
            del process
            raise subprocess.TimeoutExpired(
                "synthetic-git-after-kill" if call_number > 1 else "synthetic-git",
                timeout,
            )

        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess(wait_action=never_exits)
            with self.configured_boundary(executable):
                with mock.patch.object(
                    self.verifier.subprocess,
                    "Popen",
                    return_value=process,
                ):
                    error = self.assert_git_error_code(
                        self.verifier.GitTimeoutAfterKillError,
                        "GIT_TIMEOUT_AFTER_KILL",
                        lambda: self.verifier.git(self.authoring_root, "status"),
                        primary_code="GIT_TIMEOUT",
                    )
            self.assertRegex(str(error), "(?i)kill|terminate|reap|exit|timeout")
            self.assertTrue(process.killed)
            self.assertGreaterEqual(process.wait_calls, 2)

    def test_popen_uses_exact_executable_no_shell_and_minimal_child_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = self.copy_git_executable(Path(directory))
            process = FakeProcess(b"git version synthetic\n")
            captured: dict[str, object] = {}

            def capture(command, **kwargs):
                captured["command"] = command
                captured["kwargs"] = kwargs
                return process

            with self.configured_boundary(executable) as boundary:
                with mock.patch.object(self.verifier.subprocess, "Popen", side_effect=capture):
                    output = self.verifier.git(self.authoring_root, "--version")

            self.assertEqual(output, "git version synthetic")
            command = captured["command"]
            kwargs = captured["kwargs"]
            self.assertIsInstance(command, list)
            self.assertEqual(command[0], str(executable))
            self.assertTrue(Path(command[0]).is_absolute())
            self.assertEqual(command[-1], "--version")
            self.assertEqual(
                [item for item in command if item.startswith("--git-dir=")],
                [f"--git-dir={boundary['git_dir']}"],
            )
            self.assertEqual(
                [item for item in command if item.startswith("--work-tree=")],
                [f"--work-tree={self.authoring_root}"],
            )
            self.assertEqual(kwargs["executable"], str(executable))
            self.assertIs(kwargs["shell"], False)
            self.assertEqual(kwargs["cwd"], executable.parent)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
            self.assertIs(kwargs["close_fds"], True)
            child_environment = kwargs["env"]
            expected_keys = {
                "PATH",
                "LC_ALL",
                "LANG",
                "GIT_ATTR_NOSYSTEM",
                "GIT_CONFIG_COUNT",
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "GIT_CONFIG_SYSTEM",
                "GIT_DISCOVERY_ACROSS_FILESYSTEM",
                "GIT_NO_LAZY_FETCH",
                "GIT_NO_REPLACE_OBJECTS",
                "GIT_OPTIONAL_LOCKS",
                "GIT_TERMINAL_PROMPT",
            }
            if os.name == "nt":
                expected_keys.update({"SYSTEMROOT", "WINDIR"})
            self.assertEqual(set(child_environment), expected_keys)
            self.assertEqual(child_environment, boundary["environment"])
            self.assertEqual(child_environment["PATH"], str(executable.parent))
            self.assertNotIn("HOME", child_environment)
            self.assertNotIn("XDG_CONFIG_HOME", child_environment)

    def test_git_boundary_blocks_hostile_configs_and_local_worktree_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = self.make_committed_checkout(root / "fixture")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            hook = root / "fsmonitor_hook.py"
            hook.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[1]).write_text('executed', encoding='utf-8')\n"
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )

            local_marker = root / "local.marker"
            home_marker = root / "home.marker"
            xdg_marker = root / "xdg.marker"

            def marker_command(marker: Path) -> str:
                return shell_command([sys.executable, str(hook), str(marker)])

            empty_home = root / "empty-home"
            empty_xdg = root / "empty-xdg"
            hostile_home = root / "hostile-home"
            hostile_xdg = root / "hostile-xdg"
            for path in (empty_home, empty_xdg, hostile_home, hostile_xdg / "git"):
                path.mkdir(parents=True, exist_ok=True)

            self.run_git(checkout, "config", "core.fsmonitor", marker_command(local_marker))
            self.run_git(
                checkout,
                "config",
                "--file",
                str(hostile_home / ".gitconfig"),
                "core.fsmonitor",
                marker_command(home_marker),
            )
            self.run_git(
                checkout,
                "config",
                "--file",
                str(hostile_xdg / "git" / "config"),
                "core.fsmonitor",
                marker_command(xdg_marker),
            )

            config_cases = (
                (
                    "local",
                    {"HOME": str(empty_home), "XDG_CONFIG_HOME": str(empty_xdg)},
                ),
                (
                    "home",
                    {"HOME": str(hostile_home), "XDG_CONFIG_HOME": str(empty_xdg)},
                ),
                (
                    "xdg",
                    {"HOME": str(empty_home), "XDG_CONFIG_HOME": str(hostile_xdg)},
                ),
            )
            for label, environment in config_cases:
                with self.subTest(config=label):
                    for marker in (local_marker, home_marker, xdg_marker):
                        marker.unlink(missing_ok=True)
                    result = self.run_verifier(
                        overlay,
                        repo_root=checkout,
                        authoring_check=False,
                        environment_updates=environment,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse(local_marker.exists())
                    self.assertFalse(home_marker.exists())
                    self.assertFalse(xdg_marker.exists())

            self.run_git(checkout, "config", "--unset", "core.fsmonitor")
            shadow = root / "shadow"
            subprocess.run(
                [
                    str(self.git_executable),
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "clone",
                    "--quiet",
                    "--no-hardlinks",
                    str(checkout),
                    str(shadow),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
                env=self.git_environment,
            )
            self.run_git(checkout, "config", "core.worktree", str(shadow))
            contributing = checkout / "CONTRIBUTING.md"
            contributing.write_bytes(contributing.read_bytes() + b"hidden by hostile core.worktree\n")
            redirected = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=False,
            )
            self.assert_rejected(
                redirected,
                "tracked worktree bytes differ from HEAD: CONTRIBUTING.md",
            )

    def test_hostile_hooks_attributes_ignores_external_diff_and_textconv_never_execute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = self.make_committed_checkout(root)
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            helper = root / "marker_helper.py"
            helper.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[1]).write_text('executed', encoding='utf-8')\n"
                "raise SystemExit(97)\n",
                encoding="utf-8",
            )
            labels = ("hook", "external-diff", "textconv", "clean", "smudge")
            markers = {label: root / f"{label}.marker" for label in labels}

            def marker_command(label: str) -> str:
                return shell_command([sys.executable, str(helper), str(markers[label])])

            hooks = root / "hooks"
            hooks.mkdir()
            hook_body = (
                f"#!{Path(sys.executable).as_posix()}\n"
                "from pathlib import Path\n"
                f"Path({str(markers['hook'])!r}).write_text('executed', encoding='utf-8')\n"
                "raise SystemExit(97)\n"
            )
            for name in ("post-checkout", "post-index-change", "reference-transaction", "pre-auto-gc"):
                hook = hooks / name
                hook.write_text(hook_body, encoding="utf-8")
                hook.chmod(0o755)

            attributes = root / "hostile.attributes"
            attributes.write_text("*.md diff=hostile filter=hostile\n", encoding="utf-8")
            excludes = root / "hostile.excludes"
            excludes.write_text("hidden-by-hostile-ignore.tmp\n", encoding="utf-8")
            hostile_config = (
                ("core.hooksPath", str(hooks)),
                ("core.attributesFile", str(attributes)),
                ("core.excludesFile", str(excludes)),
                ("diff.external", marker_command("external-diff")),
                ("diff.hostile.textconv", marker_command("textconv")),
                ("filter.hostile.clean", marker_command("clean")),
                ("filter.hostile.smudge", marker_command("smudge")),
            )
            for key, value in hostile_config:
                self.run_git(checkout, "config", key, value)

            (checkout / "hidden-by-hostile-ignore.tmp").write_text(
                "must remain visible to the verifier\n",
                encoding="utf-8",
            )
            result = self.run_verifier(overlay, repo_root=checkout, authoring_check=False)
            self.assert_rejected(
                result,
                "committed checkout contains an unapproved untracked or ignored path",
            )
            self.assertTrue(all(not marker.exists() for marker in markers.values()))

    def test_authoring_authenticates_root_attributes_and_rejects_info_attributes_before_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "authoring-filter-boundary"
            subprocess.run(
                [
                    str(self.git_executable),
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "clone",
                    "--quiet",
                    "--no-hardlinks",
                    str(ROOT),
                    str(checkout),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
                env=self.git_environment,
            )
            self.run_git(
                checkout,
                "switch",
                "--quiet",
                "-C",
                TARGET_BRANCH,
                CORRECTION_PARENT,
            )
            for relative in PAYLOAD_PATHS:
                destination = checkout / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.authoring_root / relative, destination)

            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            helper = root / "authoring_filter_marker.py"
            marker = root / "authoring-filter.marker"
            helper.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[1]).write_text('executed', encoding='utf-8')\n"
                "raise SystemExit(97)\n",
                encoding="utf-8",
            )
            command = shell_command([sys.executable, str(helper), str(marker)])
            self.run_git(checkout, "config", "filter.hostile.clean", command)
            self.run_git(checkout, "config", "filter.hostile.smudge", command)
            self.run_git(checkout, "config", "filter.hostile.required", "true")

            attributes = checkout / ".gitattributes"
            canonical_attributes = attributes.read_bytes()
            attributes.write_bytes(canonical_attributes + b"* filter=hostile\n")
            root_override = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=True,
            )
            self.assert_rejected(
                root_override,
                "committed payload size mismatch: .gitattributes",
            )
            self.assertFalse(marker.exists(), "root attributes filter executed before authentication")

            attributes.write_bytes(canonical_attributes)
            nested_attributes = checkout / "docs" / ".gitattributes"
            nested_attributes.write_text("* filter=hostile\n", encoding="utf-8")
            nested_override = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=True,
            )
            self.assert_rejected(
                nested_override,
                "applicable nested .gitattributes is forbidden for raw-bound path",
            )
            self.assertFalse(
                marker.exists(),
                "nested attributes filter executed before rejection",
            )
            nested_attributes.unlink()

            git_dir = Path(
                self.run_git(checkout, "rev-parse", "--absolute-git-dir").stdout.strip()
            )
            info_attributes = git_dir / "info" / "attributes"
            info_attributes.parent.mkdir(parents=True, exist_ok=True)
            info_attributes.write_text("* filter=hostile\n", encoding="utf-8")
            info_override = self.run_verifier(
                overlay,
                repo_root=checkout,
                authoring_check=True,
            )
            self.assert_rejected(
                info_override,
                "repository-local Git attributes override is forbidden",
            )
            self.assertFalse(marker.exists(), "info attributes filter executed before rejection")

    def test_git_boundary_rejects_on_disk_object_alternates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = self.make_committed_checkout(root / "fixture")
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            git_dir = Path(
                self.run_git(checkout, "rev-parse", "--absolute-git-dir").stdout.strip()
            )
            alternate_objects = root / "alternate-objects"
            alternate_objects.mkdir()
            alternates = git_dir / "objects" / "info" / "alternates"
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(str(alternate_objects.resolve()) + "\n", encoding="utf-8")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "Git object alternates are forbidden",
            )

    def test_git_replace_hidden_worktree_and_mode_substitution_fail_closed(self) -> None:
        readme_relative = "docs/execution/dags/generic-hive-mind-product-v3/README.md"
        unrelated_relative = "CONTRIBUTING.md"

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.run_git(checkout, "replace", CORRECTION_PARENT, PLAN_AUTHORING_BASE)
            result = self.run_verifier(overlay, repo_root=checkout, authoring_check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for flag in ("--skip-worktree", "--assume-unchanged"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                checkout = self.make_committed_checkout(Path(directory))
                overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
                unrelated = checkout / unrelated_relative
                self.run_git(checkout, "update-index", flag, "--", unrelated_relative)
                unrelated.write_bytes(unrelated.read_bytes() + b"hidden substitution\n")
                self.assert_rejected(
                    self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                    "tracked index visibility flag is not pristine",
                )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(
                Path(directory),
                executable_path=readme_relative,
            )
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed payload is not one regular file",
            )

        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            (checkout / "ignored.tmp").write_text("ignored\n", encoding="utf-8")
            self.run_git(checkout, "check-ignore", "--quiet", "--", "ignored.tmp")
            self.assert_rejected(
                self.run_verifier(overlay, repo_root=checkout, authoring_check=False),
                "committed checkout contains an unapproved untracked or ignored path",
            )

    def test_non_stage_zero_index_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            relative = "CONTRIBUTING.md"
            stage_sources = (relative, "LICENSE", "README.md")
            stage_blobs = tuple(
                self.run_git(checkout, "rev-parse", f"HEAD:{source}").stdout.strip()
                for source in stage_sources
            )
            blob = stage_blobs[0]
            index_info = (
                f"0 {'0' * 40}\t{relative}\n"
                + "".join(
                    f"100644 {stage_blob} {stage}\t{relative}\n"
                    for stage, stage_blob in enumerate(stage_blobs, start=1)
                )
            )
            command = [
                str(self.git_executable),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "-C",
                str(checkout),
                "update-index",
                "--index-info",
            ]
            subprocess.run(
                command,
                cwd=ROOT,
                input=index_info.encode("utf-8"),
                capture_output=True,
                check=True,
                env=self.git_environment,
            )
            staged = self.run_git(checkout, "ls-files", "--stage", "--", relative).stdout
            self.assertIn(f" 1\t{relative}", staged)
            self.assertIn(f" 2\t{relative}", staged)
            self.assertIn(f" 3\t{relative}", staged)

            result = self.run_verifier(overlay, repo_root=checkout, authoring_check=False)
            self.assert_rejected(result)
            error = json.loads(result.stdout.strip().splitlines()[-1])["error"]
            self.assertTrue(
                "unsupported or malformed index entry" in error
                or "tracked index visibility flag is not pristine" in error
                or "malformed index entry while inspecting nested .gitattributes" in error,
                error,
            )

            tree_entry = f"100644 blob {blob}\t{relative}\0".encode("utf-8")
            index_entry = f"100644 {blob} 1\t{relative}\0".encode("utf-8")

            def fake_git(repo_root, *args, binary=False):
                del repo_root, binary
                if args[:3] == ("ls-tree", "-r", "-z"):
                    return tree_entry
                if args[:3] == ("ls-files", "--stage", "-z"):
                    return index_entry
                raise AssertionError(f"unexpected Git call: {args}")

            with mock.patch.object(self.verifier, "git", side_effect=fake_git):
                with self.assertRaisesRegex(
                    self.verifier.VerificationError,
                    "unsupported or malformed index entry",
                ):
                    self.assert_autopilot_preserved(
                        lambda: self.verifier.verify_tracked_index_and_worktree(checkout),
                        repo_root=checkout,
                    )

    def test_source_substitution_is_rejected_before_materializer_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            marker = overlay / "MATERIALIZER_EXECUTED"
            (overlay / "materialize_plan.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
                encoding="utf-8",
            )
            result = self.run_verifier(overlay)
            self.assert_rejected(result, "materialize_plan.py")
            self.assertFalse(marker.exists())

    def test_v5_manifest_binds_predecessor_report_status_lineage_and_anti_downgrade(self) -> None:
        manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 5)
        self.assertEqual(manifest["kind"], V5_MANIFEST_KIND)
        contract = manifest["committed_payload_contract"]
        self.assertEqual(contract["mode"], V5_CONTRACT_MODE)
        self.assertEqual(
            contract["correction_parent"],
            {"commit": CORRECTION_PARENT, "tree": CORRECTION_PARENT_TREE},
        )
        predecessor = contract["predecessor_payload"]
        self.assertEqual(predecessor["commit"], CORRECTION_PARENT)
        self.assertEqual(predecessor["tree"], CORRECTION_PARENT_TREE)
        self.assertEqual(predecessor["parent_commit"], CORRECTION_PARENT_PARENT)
        self.assertEqual(predecessor["parent_tree"], CORRECTION_PARENT_PARENT_TREE)
        self.assertEqual(predecessor["manifest_raw_sha256"], CORRECTION_PARENT_MANIFEST_SHA256)
        self.assertEqual(
            predecessor["full_payload_aggregate"]["sha256"],
            CORRECTION_PARENT_AGGREGATE_SHA256,
        )
        self.assertEqual(predecessor["qualification_report_sha256"], CORRECTION_PARENT_REPORT_SHA256)
        self.assertEqual(predecessor["observed_status"], CORRECTION_PARENT_STATUS)
        self.assertEqual(predecessor["author_proposed_disposition"], "ADAPT_REMAND")
        remanded_git_boundary = contract["remanded_git_boundary_predecessor"]
        self.assertEqual(remanded_git_boundary["commit"], GIT_BOUNDARY_CORRECTION_PARENT)
        self.assertEqual(
            remanded_git_boundary["observed_status"],
            "QUALIFICATION_REMANDED_NATIVE_EXECUTABLE_FORMAT_AND_ADVERSARIAL_MATRIX_GAPS",
        )
        self.assertEqual(
            manifest["snapshot_lineage"]["correction_parent"],
            {"commit": CORRECTION_PARENT, "tree": CORRECTION_PARENT_TREE},
        )
        anti_downgrade = contract["activation_anti_downgrade"]
        self.assertEqual(anti_downgrade["required_contract_mode"], V5_CONTRACT_MODE)
        self.assertEqual(
            anti_downgrade["required_git_executable_format_policy"],
            "host-native-image-format-v1",
        )
        self.assertEqual(anti_downgrade["published_v4_activation"], "PROHIBITED")
        self.assertEqual(anti_downgrade["v3_git_boundary_activation"], "PROHIBITED")

    def test_manifest_identity_snapshot_and_tool_substitution_fail_closed(self) -> None:
        mutations = {
            "schema_downgrade": lambda m: m.__setitem__("schema_version", 4),
            "kind_downgrade": lambda m: m.__setitem__("kind", "hive-mind-generic-product-overlay-manifest-v4"),
            "request": lambda m: m["request_binding"].__setitem__("request_id", "sha256:stale"),
            "objective": lambda m: m["request_binding"].__setitem__("objective_digest", "sha256:stale"),
            "repository": lambda m: m["request_binding"].__setitem__("repository_id", "sha256:stale"),
            "branch": lambda m: m["request_binding"].__setitem__("target_branch", "main"),
            "head": lambda m: m["snapshot_lineage"]["authoring_base_parent"].__setitem__("commit", "0" * 40),
            "tree": lambda m: m["snapshot_lineage"]["authoring_base_parent"].__setitem__("tree", "0" * 40),
            "correction_head": lambda m: m["snapshot_lineage"]["correction_parent"].__setitem__("commit", "0" * 40),
            "correction_tree": lambda m: m["snapshot_lineage"]["correction_parent"].__setitem__("tree", "0" * 40),
            "predecessor_manifest": lambda m: m["committed_payload_contract"]["predecessor_payload"].__setitem__("manifest_raw_sha256", "sha256:stale"),
            "predecessor_aggregate": lambda m: m["committed_payload_contract"]["predecessor_payload"]["full_payload_aggregate"].__setitem__("sha256", "sha256:stale"),
            "predecessor_report": lambda m: m["committed_payload_contract"]["predecessor_payload"].__setitem__("qualification_report_sha256", "sha256:stale"),
            "predecessor_status": lambda m: m["committed_payload_contract"]["predecessor_payload"].__setitem__("observed_status", "QUALIFIED"),
            "predecessor_lineage": lambda m: m["committed_payload_contract"]["predecessor_payload"].__setitem__("parent_commit", "0" * 40),
            "predecessor_disposition": lambda m: m["committed_payload_contract"]["predecessor_payload"].__setitem__("author_proposed_disposition", "ADOPT"),
            "v3_git_boundary_record": lambda m: m["committed_payload_contract"]["remanded_git_boundary_predecessor"].__setitem__("commit", "0" * 40),
            "f06_record": lambda m: m["committed_payload_contract"]["remanded_git_environment_predecessor"].__setitem__("commit", "0" * 40),
            "payload_a_record": lambda m: m["committed_payload_contract"]["historical_payload_a"].__setitem__("commit", "0" * 40),
            "contract_mode_downgrade": lambda m: m["committed_payload_contract"].__setitem__("mode", "exact-append-only-git-boundary-correction-v3"),
            "payload_inventory": lambda m: m["committed_payload_contract"]["payload_inventory"].pop(),
            "anti_downgrade": lambda m: m["committed_payload_contract"]["activation_anti_downgrade"].__setitem__("v3_git_boundary_activation", "ALLOWED"),
            "published_v4_activation": lambda m: m["committed_payload_contract"]["activation_anti_downgrade"].__setitem__("published_v4_activation", "ALLOWED"),
            "f06_activation": lambda m: m["committed_payload_contract"]["activation_anti_downgrade"].__setitem__("f06_activation", "ALLOWED"),
            "payload_a_activation": lambda m: m["committed_payload_contract"]["activation_anti_downgrade"].__setitem__("historical_payload_a_activation", "ALLOWED"),
            "v1_fallback": lambda m: m["committed_payload_contract"]["activation_anti_downgrade"].__setitem__("legacy_v1_fallback", "ALLOWED"),
            "native_policy_downgrade": lambda m: m["committed_payload_contract"]["git_execution_boundary"].__setitem__("policy", "caller-absolute-raw-sha256-v1"),
            "court_binding_missing": lambda m: m["committed_payload_contract"]["court_envelope_b_bindings"].pop(),
            "court_binding_wrong": lambda m: m["committed_payload_contract"]["court_envelope_b_bindings"].__setitem__(0, "unbound_contract_mode"),
            "request_snapshot": lambda m: m["snapshot_lineage"]["request_observation"].__setitem__("commit", "0" * 40),
            "compiler": lambda m: next(
                row for row in m["source_bindings"]["repository"] if row["path"] == ".autopilot/bin/dag_standard.py"
            ).__setitem__("sha256", "sha256:substituted"),
            "standard": lambda m: next(
                row for row in m["source_bindings"]["repository"] if row["path"] == "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
            ).__setitem__("sha256", "sha256:substituted"),
            "execution_authority": lambda m: m["authorship"].__setitem__("execution_authority", "SELF_GRANTED"),
            "extra_authority_field": lambda m: m["authorship"].__setitem__("delegated_authority", "SELF_GRANTED"),
            "extra_top_level_authority": lambda m: m.__setitem__("execution_authority", "GRANTED"),
            "extra_execution_command": lambda m: m["execution_contract"].__setitem__("command", "powershell hostile.ps1"),
            "execution_v1_fallback": lambda m: m["execution_contract"].__setitem__("legacy_fallback", "ALLOW_V1"),
            "extra_evidence_authority": lambda m: m["evidence_partition"].__setitem__("external_execution_authority", "GRANTED"),
            "external_evidence_missing": lambda m: m["evidence_partition"].pop("host_external"),
            "external_evidence_wrong": lambda m: m["evidence_partition"].__setitem__("host_external", "SELF_ATTESTED"),
            "removed_nonclaims": lambda m: m.__setitem__("nonclaims", []),
            "self_review": lambda m: m["authorship"].__setitem__("judge", "/root/generation_architect"),
        }
        expected_errors = {
            "schema_downgrade": "manifest schema mismatch",
            "kind_downgrade": "manifest kind mismatch",
            "request": "manifest request/repository/objective binding mismatch",
            "objective": "manifest request/repository/objective binding mismatch",
            "repository": "manifest request/repository/objective binding mismatch",
            "branch": "manifest request/repository/objective binding mismatch",
            "head": "authoring-base parent commit/tree mismatch",
            "tree": "authoring-base parent commit/tree mismatch",
            "correction_head": "correction parent commit/tree mismatch",
            "correction_tree": "correction parent commit/tree mismatch",
            "predecessor_manifest": "predecessor correction identity/status mismatch",
            "predecessor_aggregate": "predecessor correction identity/status mismatch",
            "predecessor_report": "predecessor correction identity/status mismatch",
            "predecessor_status": "predecessor correction identity/status mismatch",
            "predecessor_lineage": "predecessor correction identity/status mismatch",
            "predecessor_disposition": "predecessor correction identity/status mismatch",
            "v3_git_boundary_record": "remanded Git-boundary predecessor identity/status mismatch",
            "f06_record": "remanded Git-environment predecessor identity/status mismatch",
            "payload_a_record": "historical Payload A identity/status mismatch",
            "contract_mode_downgrade": "committed payload mode mismatch",
            "payload_inventory": "committed payload inventory mismatch",
            "anti_downgrade": "activation anti-downgrade contract mismatch",
            "published_v4_activation": "activation anti-downgrade contract mismatch",
            "f06_activation": "activation anti-downgrade contract mismatch",
            "payload_a_activation": "activation anti-downgrade contract mismatch",
            "v1_fallback": "activation anti-downgrade contract mismatch",
            "native_policy_downgrade": "Git execution boundary contract mismatch",
            "court_binding_missing": "court Envelope B committed identity contract mismatch",
            "court_binding_wrong": "court Envelope B committed identity contract mismatch",
            "request_snapshot": "request snapshot mismatch",
            "compiler": "manifest repository source binding mismatch",
            "standard": "manifest repository source binding mismatch",
            "execution_authority": "author manifest cannot grant execution authority",
            "extra_authority_field": "manifest authorship field inventory mismatch",
            "extra_top_level_authority": "manifest top-level field inventory mismatch",
            "extra_execution_command": "manifest execution contract mismatch",
            "execution_v1_fallback": "manifest execution contract mismatch",
            "extra_evidence_authority": "evidence partition contract mismatch",
            "external_evidence_missing": "evidence partition contract mismatch",
            "external_evidence_wrong": "evidence partition contract mismatch",
            "removed_nonclaims": "manifest nonclaims mismatch",
            "self_review": "author manifest cannot self-assign a judge",
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                overlay = self.copy_overlay(Path(directory))
                self.rewrite_manifest(overlay, mutation)
                self.assert_rejected(self.run_verifier(overlay), expected_errors[label])

    def test_strict_json_rejects_duplicate_nonfinite_oversize_and_deep_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            manifest = overlay / "manifest.json"
            text = manifest.read_text(encoding="utf-8")
            manifest.write_text(text.replace('"schema_version": 5,', '"schema_version": 5,\n  "schema_version": 5,', 1), encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            manifest = overlay / "manifest.json"
            text = manifest.read_text(encoding="utf-8")
            manifest.write_text(text.replace("{", '{"poison":NaN,', 1), encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            manifest = overlay / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" " * 262_144)
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            self.rewrite_manifest(overlay, lambda m: m.__setitem__("too_deep", [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]))
            self.assert_rejected(self.run_verifier(overlay))

    def test_plan_and_node_reseal_substitution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            plan_path = overlay / "plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["nodes"][0]["objective"] += " substituted"
            for node in plan["nodes"]:
                node.pop("contract_digest", None)
                node["contract_digest"] = canonical_digest(node)
            plan.pop("plan_digest", None)
            plan["plan_digest"] = canonical_digest(plan)
            rendered = json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            plan_path.write_text(rendered, encoding="utf-8")
            new_plan_digest = plan["plan_digest"]
            new_raw_digest = "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
            self.rewrite_manifest(
                overlay,
                lambda m: m["plan_binding"].update(
                    expected_plan_digest=new_plan_digest,
                    expected_raw_bytes_digest=new_raw_digest,
                ),
            )
            self.assert_rejected(self.run_verifier(overlay))

    def test_contract_topology_durability_ownership_effect_trace_and_quarantine_corruption(self) -> None:
        corruptions = {
            "topology": ("node-contracts.json", lambda d: d["nodes"][1].__setitem__("dependencies", [])),
            "durability": ("node-contracts.json", lambda d: d["nodes"][0].__setitem__("durability", "ephemeral")),
            "ownership": ("node-contracts.json", lambda d: d["nodes"][1]["write_scope"].append(d["nodes"][0]["write_scope"][0])),
            "effects": ("ownership-effects.json", lambda d: d["node_effect_expectations"]["BASELINE-000"].__setitem__("candidate_build_effects", ["concealed-effect"])),
            "frozen_host": ("node-contracts.json", lambda d: d["frozen_host_contract"].__setitem__("bundle_digest", "sha256:substituted")),
            "evidence_lineage": ("ownership-effects.json", lambda d: d["phase_boundaries"]["candidate_and_evidence_lineage"].__setitem__("identity_rule", "evidence may rewrite the candidate")),
            "missing_v1_mapping": ("traceability.json", lambda d: d["rows"].pop(next(iter(d["rows"])))),
            "source_quarantine": ("plan.json", lambda d: d["source_governance"].__setitem__("SRC-024", "ADOPT")),
        }
        for label, (name, mutate) in corruptions.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                overlay = self.copy_overlay(Path(directory))
                path = overlay / name
                data = json.loads(path.read_text(encoding="utf-8"))
                mutate(data)
                path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                self.assert_rejected(self.run_verifier(overlay))

    def test_frozen_host_tool_and_evidence_source_byte_mutations_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_committed_checkout(Path(directory))
            overlay = checkout / "docs/execution/dags/generic-hive-mind-product-v3"
            protected_paths = (
                ".autopilot/bin/dag_standard.py",
                "evidence/autopilot/COMBINED-PREREQUISITE-QUALIFICATION-2026-08-23.md",
            )
            for relative in protected_paths:
                with self.subTest(relative=relative):
                    path = checkout / relative
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original + b"\nsubstituted frozen evidence\n")
                        self.assert_rejected(
                            self.run_verifier(
                                overlay,
                                repo_root=checkout,
                                authoring_check=False,
                            ),
                            f"tracked worktree bytes differ from HEAD: {relative}",
                        )
                    finally:
                        path.write_bytes(original)

    def test_frozen_host_files_pointer_is_strict_and_resealed_substitutions_fail(self) -> None:
        manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))
        contracts = json.loads(
            (OVERLAY / "node-contracts.json").read_text(encoding="utf-8")
        )
        location = manifest["frozen_host_prerequisite"]["manifest_location"]
        self.assertEqual(
            location,
            "node-contracts.json#/frozen_host_contract/files",
        )
        document, pointer = location.split("#", 1)
        self.assertEqual(document, "node-contracts.json")
        pointed = contracts
        for token in pointer.removeprefix("/").split("/"):
            pointed = pointed[token.replace("~1", "/").replace("~0", "~")]
        self.assertIs(pointed, contracts["frozen_host_contract"]["files"])
        self.assertEqual(self.verifier.FROZEN_HOST_MANIFEST_LOCATION, location)
        self.assertIs(
            self.verifier.resolve_local_json_pointer(
                location,
                document_name="node-contracts.json",
                document=contracts,
                label="test frozen host manifest location",
            ),
            pointed,
        )
        self.assertEqual(len(pointed), 16)

        invalid_references = {
            "wrong_document": "other.json#/frozen_host_contract/files",
            "missing_slash": "node-contracts.json#frozen_host_contract/files",
            "multiple_fragments": "node-contracts.json#/frozen_host_contract/files#extra",
            "invalid_escape": "node-contracts.json#/frozen_host_contract/~2files",
            "missing_member": "node-contracts.json#/frozen_host_contract/missing",
            "noncanonical_index": "node-contracts.json#/frozen_host_contract/files/00",
            "out_of_range_index": "node-contracts.json#/frozen_host_contract/files/999",
        }
        for label, reference in invalid_references.items():
            with self.subTest(invalid_pointer=label):
                with self.assertRaises(self.verifier.VerificationError):
                    self.verifier.resolve_local_json_pointer(
                        reference,
                        document_name="node-contracts.json",
                        document=contracts,
                        label="test invalid frozen host manifest location",
                    )

        with mock.patch.object(
            self.verifier,
            "resolve_local_json_pointer",
            side_effect=self.verifier.VerificationError(
                "sentinel strict frozen-host pointer dereference"
            ),
        ) as resolver:
            with self.assertRaisesRegex(
                self.verifier.VerificationError,
                "sentinel strict frozen-host pointer dereference",
            ):
                self.verifier.verify_frozen_host(
                    manifest,
                    contracts,
                    self.authoring_root,
                )
        resolver.assert_called_once_with(
            location,
            document_name="node-contracts.json",
            document=contracts,
            label="frozen host manifest location",
        )

        for reference in (
            "node-contracts.json#/frozen_host_contract/file_manifest",
            "node-contracts.json#/frozen_host_contract/adverse_facts",
            "node-contracts.json#/frozen_host_contract/missing",
        ):
            with self.subTest(verify_wrong_pointer=reference):
                substituted = json.loads(json.dumps(manifest))
                substituted["frozen_host_prerequisite"]["manifest_location"] = reference
                with self.assertRaises(self.verifier.VerificationError):
                    self.verifier.verify_frozen_host(
                        substituted,
                        contracts,
                        self.authoring_root,
                    )

        mutations = {
            "missing": lambda value: value["frozen_host_prerequisite"].pop(
                "manifest_location"
            ),
            "wrong_existing_type": lambda value: value[
                "frozen_host_prerequisite"
            ].__setitem__(
                "manifest_location",
                "node-contracts.json#/frozen_host_contract/adverse_facts",
            ),
            "missing_target": lambda value: value[
                "frozen_host_prerequisite"
            ].__setitem__(
                "manifest_location",
                "node-contracts.json#/frozen_host_contract/missing",
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                overlay = self.copy_overlay(Path(directory))
                self.rewrite_manifest(overlay, mutation)
                resealed_digest = "sha256:" + raw_digest(overlay / "manifest.json")
                result = self.run_verifier(
                    overlay,
                    expected_manifest_digest=resealed_digest,
                )
                self.assert_rejected(result, "frozen-host prerequisite contract mismatch")
                error = json.loads(result.stdout.strip().splitlines()[-1])["error"]
                self.assertNotIn("caller-authenticated manifest digest mismatch", error)

    def test_source_path_swap_collision_and_detached_binding_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            left = overlay / "node-contracts.json"
            right = overlay / "traceability.json"
            left_bytes, right_bytes = left.read_bytes(), right.read_bytes()
            left.write_bytes(right_bytes)
            right.write_bytes(left_bytes)
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            self.rewrite_manifest(
                overlay,
                lambda m: m["source_bindings"]["overlay"].append(dict(m["source_bindings"]["overlay"][0])),
            )
            self.assert_rejected(self.run_verifier(overlay))

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            self.rewrite_manifest(
                overlay,
                lambda m: m["plan_binding"].__setitem__("external_path", "detached/plan.json"),
            )
            self.assert_rejected(self.run_verifier(overlay))

    def test_invalid_v3_has_no_legacy_fallback_and_activation_attacks_are_explicit(self) -> None:
        plan = json.loads((OVERLAY / "plan.json").read_text(encoding="utf-8"))
        activation = plan["activation_contract"]
        self.assertEqual(activation["invalid_v3_legacy_fallback"], "PROHIBITED")
        self.assertEqual(activation["concurrent_activation"], "single_winner_compare_and_swap_ledger")
        self.assertEqual(activation["repeat_resume"], "idempotent_only_for_exact_generation_and_resume_identity")
        self.assertEqual(activation["same_request_fast_path"], "exact_request_on_persisted_target_before_new_target_protection_check")
        expected_attacks = {
            "duplicate_json_key",
            "non_finite_number",
            "oversize_document",
            "excessive_nesting_depth",
            "path_swap",
            "detached_signature_or_digest_substitution",
            "request_repository_objective_or_generation_collision",
            "replay_or_expired_lease",
            "repeat_resume_identity_mismatch",
            "concurrent_activation_loser",
        }
        self.assertEqual(set(activation["strict_rejections"]), expected_attacks)
        self.assertFalse(activation["path_reference_sufficient"])
        self.assertFalse(activation["detached_digest_sufficient"])

        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            plan_path = overlay / "plan.json"
            invalid = json.loads(plan_path.read_text(encoding="utf-8"))
            invalid["execution"]["legacy_fallback"] = "ALLOW_V1"
            plan_path.write_text(json.dumps(invalid, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            self.assert_rejected(self.run_verifier(overlay))

    def test_exact_host_evidence_lineage_and_manual_parent_boundaries(self) -> None:
        contracts = json.loads((OVERLAY / "node-contracts.json").read_text(encoding="utf-8"))
        ownership = json.loads((OVERLAY / "ownership-effects.json").read_text(encoding="utf-8"))
        plan = json.loads((OVERLAY / "plan.json").read_text(encoding="utf-8"))
        host = contracts["frozen_host_contract"]
        self.assertEqual(host["extraction_commit"], "ca43709591313c1c166a2e655b8982ccff16daf3")
        self.assertEqual(host["file_count"], 16)
        self.assertEqual(len(host["files"]), 16)
        self.assertTrue(all(set(row) >= {"path", "bytes", "sha256", "git_blob"} for row in host["files"]))
        self.assertEqual(host["bundle_digest"], "sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255")
        lineage = ownership["phase_boundaries"]["candidate_and_evidence_lineage"]
        self.assertIn("Envelope B", json.dumps(lineage))
        self.assertEqual(plan["execution"]["mode"], "manual-parent-v1")
        self.assertEqual(plan["execution"]["expected_round_count"], 20)
        self.assertEqual(plan["execution"]["expected_nodes_per_round"], 1)
        self.assertEqual(plan["execution"]["round_command_policy"], "all_null")
        self.assertNotIn('"command"', json.dumps(plan, sort_keys=True))
        self.assertFalse(plan["execution"]["executable_dispatch_command_available"])

    def test_literal_powershell_recipes_check_every_python_last_exit_code(self) -> None:
        readme = (OVERLAY / "README.md").read_text(encoding="utf-8")
        powershell_blocks = []
        cursor = 0
        opening = "```powershell\n"
        while True:
            start = readme.find(opening, cursor)
            if start < 0:
                break
            start += len(opening)
            end = readme.find("```", start)
            self.assertGreaterEqual(end, 0)
            powershell_blocks.append(readme[start:end])
            cursor = end + 3
        self.assertEqual(len(powershell_blocks), 2)

        command_count = 0
        for block in powershell_blocks:
            lines = block.splitlines()
            command_lines = [
                index for index, line in enumerate(lines) if line.startswith("python -B ")
            ]
            command_count += len(command_lines)
            for command_line in command_lines:
                final_command_line = command_line
                while lines[final_command_line].rstrip().endswith("`"):
                    final_command_line += 1
                    self.assertLess(
                        final_command_line,
                        len(lines),
                        "PowerShell recipe ends inside a continued Python command",
                    )
                self.assertLess(
                    final_command_line + 1,
                    len(lines),
                    "PowerShell recipe command lacks an immediate exit-code guard",
                )
                guard = lines[final_command_line + 1].strip()
                self.assertRegex(
                    guard,
                    r'^if \(\$LASTEXITCODE -ne 0\) \{ throw ".+\$LASTEXITCODE" \}$',
                    f"PowerShell recipe command lacks an immediate literal exit-code guard: {lines[command_line:final_command_line + 2]}",
                )
        self.assertEqual(command_count, 5)

    def test_frozen_standard_v2_compiles_exact_null_command_rounds(self) -> None:
        digest = "sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1"
        compiler = self.authoring_root / ".autopilot" / "bin" / "dag_standard.py"
        plan = (
            self.authoring_root
            / "docs"
            / "execution"
            / "dags"
            / "generic-hive-mind-product-v3"
            / "plan.json"
        )
        autopilot = self.authoring_root / ".autopilot"
        self.assertEqual(
            python_bytecode_inventory(autopilot),
            (),
            "the literal compiler recipe requires a bytecode-free .autopilot input",
        )
        compiler_environment = dict(os.environ)
        compiler_environment["PYTHONDONTWRITEBYTECODE"] = "1"
        lint = subprocess.run(
            [sys.executable, "-B", str(compiler), "dag-lint", "--json", "--strict", "--plan", str(plan), "--expected-plan-digest", digest],
            cwd=self.authoring_root,
            text=True,
            capture_output=True,
            check=False,
            env=compiler_environment,
        )
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        lint_result = json.loads(lint.stdout)
        self.assertEqual(lint_result["counts"], {"error": 0, "warning": 0, "info": 0})
        self.assertEqual(lint_result["integrity"]["status"], "verified-sealed")
        self.assertEqual(lint_result["durability_semantics"]["mode"], "typed-v2")
        self.assertTrue(lint_result["expected_plan_binding"]["matched"])

        rounds = subprocess.run(
            [sys.executable, "-B", str(compiler), "dag-rounds", "--json", "--plan", str(plan), "--expected-plan-digest", digest],
            cwd=self.authoring_root,
            text=True,
            capture_output=True,
            check=False,
            env=compiler_environment,
        )
        self.assertEqual(rounds.returncode, 0, rounds.stdout + rounds.stderr)
        result = json.loads(rounds.stdout)
        self.assertEqual(result["execution"]["mode"], "manual-parent-v1")
        self.assertFalse(result["execution"]["executable_dispatch_command_available"])
        self.assertEqual(len(result["rounds"]), 20)
        self.assertEqual([round_["round_id"] for round_ in result["rounds"]], [f"R{number}" for number in range(1, 21)])
        self.assertTrue(all(round_["command"] is None for round_ in result["rounds"]))
        self.assertTrue(all(len(round_["nodes"]) == 1 for round_ in result["rounds"]))
        self.assertEqual(
            python_bytecode_inventory(autopilot),
            (),
            "the literal `python -B` compiler recipe created forbidden bytecode",
        )

    def test_materialization_is_repeatable_and_refuses_autopilot_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overlay = self.copy_overlay(Path(directory))
            plan_path = overlay / "plan.json"
            plan_path.unlink()
            command = [sys.executable, str(overlay / "materialize_plan.py")]
            first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            first_bytes = plan_path.read_bytes()
            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(plan_path.read_bytes(), first_bytes)

            forbidden = ROOT / ".autopilot" / "v3-test-plan.json"
            self.assertFalse(forbidden.exists())
            refused = subprocess.run(
                command + ["--output", str(forbidden)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
