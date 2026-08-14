#!/usr/bin/env python3
"""Run one frozen commit's tests in a disposable isolated clone.

The public mode refuses a dirty source checkout, copies the exact commit into a
standalone clone, discovers the test vector in an isolated interpreter, runs that
same vector in a second isolated interpreter, and emits one canonical receipt.
The private child mode exists only so the parent can start with ``python -I``;
it never writes authority in the source repository.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Iterable


FULL_SHA256 = "sha256:" + "0" * 64
CHILD_MARKER = "HIVE_MIND_HERMETIC_RESULT="
RECEIPT_KIND = "hive-mind-hermetic-test-receipt-v1"
RUNNER_KIND = "hive-mind-hermetic-test-runner-v1"


class HermeticTestError(RuntimeError):
    """Raised when an authoritative test environment cannot be proven."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git(
    repo_root: Path,
    arguments: Iterable[str],
    *,
    check: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
        "-C",
        str(repo_root),
        *arguments,
    ]
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=environment,
    )


def _test_ids(suite: unittest.TestSuite) -> list[str]:
    result: list[str] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            result.extend(_test_ids(item))
        else:
            result.append(item.id())
    return result


def _candidate_import(repo_root: Path) -> tuple[str, str]:
    source = (repo_root / "src").resolve()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(source))
    import hive_mind_os  # noqa: PLC0415

    imported = Path(hive_mind_os.__file__).resolve()
    try:
        imported.relative_to(source)
    except ValueError as error:
        raise HermeticTestError(
            f"hive_mind_os resolved outside the frozen candidate: {imported}"
        ) from error
    return str(imported), _file_digest(imported)


def _discover(repo_root: Path, suite_path: str, pattern: str) -> tuple[unittest.TestSuite, list[str]]:
    suite_root = (repo_root / suite_path).resolve()
    try:
        suite_root.relative_to(repo_root)
    except ValueError as error:
        raise HermeticTestError("test suite path escapes the frozen candidate") from error
    if not suite_root.is_dir():
        raise HermeticTestError(f"test suite directory is absent: {suite_root}")
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(suite_root),
        pattern=pattern,
        # Match ``python -m unittest discover -s <suite>``.  The repository root
        # remains explicitly first on sys.path for namespace-package fixtures,
        # while a suite directory without __init__.py is still importable.
        top_level_dir=str(suite_root),
    )
    identifiers = _test_ids(suite)
    if not identifiers:
        raise HermeticTestError("hermetic discovery found zero tests")
    if len(identifiers) != len(set(identifiers)):
        raise HermeticTestError("hermetic discovery returned duplicate test ids")
    return suite, identifiers


def _child(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    imported_path, imported_digest = _candidate_import(repo_root)
    suite, identifiers = _discover(repo_root, args.suite, args.pattern)
    vector = {
        "schema_version": 1,
        "kind": "hive-mind-hermetic-test-vector-v1",
        "suite": args.suite,
        "pattern": args.pattern,
        "test_ids": identifiers,
    }
    vector_id = _digest(vector)
    common: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-hermetic-child-result-v1",
        "mode": args.child,
        "suite": args.suite,
        "pattern": args.pattern,
        "imported_hive_mind_os_path": imported_path,
        "imported_hive_mind_os_digest": imported_digest,
        "isolated": bool(sys.flags.isolated),
        "no_user_site": bool(sys.flags.no_user_site),
        "test_vector": vector,
        "test_vector_id": vector_id,
        "discovered": len(identifiers),
    }
    if not sys.flags.isolated or not sys.flags.no_user_site:
        raise HermeticTestError("child interpreter is not isolated from user site state")
    if args.child == "discover":
        print(CHILD_MARKER + json.dumps(common, sort_keys=True, separators=(",", ":")))
        return 0
    if args.expected_test_vector_id != vector_id:
        raise HermeticTestError("test vector changed between discovery and execution")
    runner_type = unittest.TextTestRunner
    runner = runner_type(verbosity=args.verbosity, buffer=True)
    result = runner.run(suite)
    outcome = {
        **common,
        "tests_run": result.testsRun,
        "failures": [test.id() for test, _detail in result.failures],
        "errors": [test.id() for test, _detail in result.errors],
        "skipped": [test.id() for test, _reason in result.skipped],
        "expected_failures": [test.id() for test, _detail in result.expectedFailures],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
        "successful": result.wasSuccessful(),
    }
    print(CHILD_MARKER + json.dumps(outcome, sort_keys=True, separators=(",", ":")))
    return 0 if result.wasSuccessful() else 1


def _child_environment(home: Path) -> dict[str, str]:
    allowed = {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    for key in tuple(environment):
        if key.upper().startswith(("PYTHONPATH", "OPENAI_", "GITHUB_", "GH_")):
            environment.pop(key, None)
    return environment


def _parse_child_result(stdout: str) -> dict[str, Any]:
    matching = [line for line in stdout.splitlines() if line.startswith(CHILD_MARKER)]
    if len(matching) != 1:
        raise HermeticTestError("isolated child emitted an ambiguous result marker")
    try:
        value = json.loads(matching[0][len(CHILD_MARKER) :])
    except (json.JSONDecodeError, UnicodeError) as error:
        raise HermeticTestError("isolated child result is malformed") from error
    if not isinstance(value, dict):
        raise HermeticTestError("isolated child result is not an object")
    return value


def _run_child(
    *,
    clone: Path,
    environment: dict[str, str],
    mode: str,
    suite: str,
    pattern: str,
    verbosity: int,
    expected_vector_id: str | None = None,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str] | None, dict[str, Any] | None, bool]:
    script = clone / ".autopilot" / "bin" / "hermetic_ci.py"
    command = [
        sys.executable,
        "-I",
        str(script),
        "--child",
        mode,
        "--repo-root",
        str(clone),
        "--suite",
        suite,
        "--pattern",
        pattern,
        "--verbosity",
        str(verbosity),
    ]
    if expected_vector_id is not None:
        command.extend(["--expected-test-vector-id", expected_vector_id])
    try:
        completed = subprocess.run(
            command,
            cwd=clone,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, None, True
    value = _parse_child_result(completed.stdout)
    return completed, value, False


def run_frozen_candidate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo_root = Path(args.repo_root).resolve()
    receipt_path = Path(args.receipt).resolve()
    status = _git(repo_root, ("status", "--porcelain=v1", "--untracked-files=all")).stdout
    if status:
        raise HermeticTestError("authoritative tests require a clean frozen candidate")
    commit = _git(repo_root, ("rev-parse", "HEAD")).stdout.strip()
    tree = _git(repo_root, ("rev-parse", "HEAD^{tree}")).stdout.strip()
    if len(commit) != 40 or len(tree) != 40:
        raise HermeticTestError("candidate commit or tree is malformed")
    if not args.plan_fingerprint.startswith("sha256:") or len(args.plan_fingerprint) != len(FULL_SHA256):
        raise HermeticTestError("plan fingerprint must be a SHA-256 authority id")
    if not args.execution_namespace.strip():
        raise HermeticTestError("execution namespace is required")
    interpreter = Path(sys.executable).resolve()
    git_path_text = shutil.which("git")
    if git_path_text is None:
        raise HermeticTestError("Git executable is unavailable")
    git_path = Path(git_path_text).resolve()
    started_at = _now()
    with tempfile.TemporaryDirectory(prefix="hive-mind-hermetic-") as temporary:
        temporary_root = Path(temporary).resolve()
        clone = temporary_root / "candidate"
        home = temporary_root / "home"
        home.mkdir()
        environment = _child_environment(home)
        clone_command = [
            str(git_path),
            "-c",
            "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
            "clone",
            "--no-local",
            "--no-checkout",
            str(repo_root),
            str(clone),
        ]
        subprocess.run(
            clone_command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=environment,
        )
        _git(clone, ("checkout", "--detach", commit), environment=environment)
        if _git(clone, ("rev-parse", "HEAD^{tree}"), environment=environment).stdout.strip() != tree:
            raise HermeticTestError("disposable clone tree differs from the frozen candidate")
        discovery, discovered, discovery_timed_out = _run_child(
            clone=clone,
            environment=environment,
            mode="discover",
            suite=args.suite,
            pattern=args.pattern,
            verbosity=args.verbosity,
            timeout_seconds=args.discovery_timeout_seconds,
        )
        if discovery_timed_out or discovery is None or discovered is None:
            raise HermeticTestError("isolated test discovery exceeded its bounded timeout")
        if discovery.returncode != 0:
            raise HermeticTestError(
                "isolated test discovery failed: " + discovery.stderr[-4000:]
            )
        vector_id = str(discovered.get("test_vector_id"))
        run_started_at = _now()
        execution, outcome, execution_timed_out = _run_child(
            clone=clone,
            environment=environment,
            mode="run",
            suite=args.suite,
            pattern=args.pattern,
            verbosity=args.verbosity,
            expected_vector_id=vector_id,
            timeout_seconds=args.timeout_seconds,
        )
        run_completed_at = _now()
        stderr = "" if execution is None else execution.stderr
        stdout = "" if execution is None else execution.stdout
        exit_code = None if execution is None else execution.returncode
        classification = (
            "TIMING_BUDGET_EXHAUSTED"
            if execution_timed_out
            else "PASS"
            if exit_code == 0 and isinstance(outcome, dict) and outcome.get("successful") is True
            else "FUNCTIONAL_FAILURE"
        )
        completed_at = _now()
        material: dict[str, Any] = {
            "schema_version": 1,
            "kind": RECEIPT_KIND,
            "runner": {
                "kind": RUNNER_KIND,
                "runner_digest": _file_digest(Path(__file__).resolve()),
                "interpreter_path": str(interpreter),
                "interpreter_digest": _file_digest(interpreter),
                "python_version": sys.version,
                "git_path": str(git_path),
                "git_digest": _file_digest(git_path),
                "isolated_flag": "-I",
                "user_site_disabled": True,
                "environment_allowlist": sorted(_child_environment(home)),
            },
            "candidate": {"commit": commit, "tree": tree, "repo_root": str(repo_root)},
            "authority": {
                "plan_fingerprint": args.plan_fingerprint,
                "execution_namespace": args.execution_namespace,
            },
            "test_vector": discovered["test_vector"],
            "test_vector_id": vector_id,
            "discovery": {
                "imported_hive_mind_os_path": discovered.get("imported_hive_mind_os_path"),
                "imported_hive_mind_os_digest": discovered.get("imported_hive_mind_os_digest"),
                "isolated": discovered.get("isolated"),
                "no_user_site": discovered.get("no_user_site"),
                "discovered": discovered.get("discovered"),
            },
            "run": {
                "started_at": run_started_at,
                "completed_at": run_completed_at,
                "timeout_seconds": args.timeout_seconds,
                "exit_code": exit_code,
                "classification": classification,
                "timed_out": execution_timed_out,
                "outcome": outcome,
                "stdout_digest": "sha256:" + hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
                "stderr_digest": "sha256:" + hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
            },
            "started_at": started_at,
            "completed_at": completed_at,
        }
    receipt = {**material, "receipt_id": _digest(material)}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(receipt)
    try:
        descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if receipt_path.read_bytes() != payload:
            raise HermeticTestError("receipt path already contains different bytes")
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    return receipt, 0 if receipt["run"]["classification"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--suite", default="tests")
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--plan-fingerprint")
    parser.add_argument("--execution-namespace")
    parser.add_argument("--receipt")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--discovery-timeout-seconds", type=int, default=600)
    parser.add_argument("--verbosity", type=int, default=2)
    parser.add_argument("--child", choices=("discover", "run"), help=argparse.SUPPRESS)
    parser.add_argument("--expected-test-vector-id", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.child:
            return _child(args)
        if not args.plan_fingerprint or not args.execution_namespace or not args.receipt:
            raise HermeticTestError(
                "public mode requires --plan-fingerprint, --execution-namespace, and --receipt"
            )
        receipt, exit_code = run_frozen_candidate(args)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return exit_code
    except (HermeticTestError, OSError, subprocess.SubprocessError) as error:
        print(f"hermetic-ci: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
