"""Create and verify the committed agent change used by this offline example."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

EXAMPLE_ROOT = Path(__file__).resolve().parent
BASE_REPOSITORY = EXAMPLE_ROOT / "repository"
AGENT_PATCH = EXAMPLE_ROOT / "agent-change.patch"
ACCEPTANCE_SPECIFICATION = EXAMPLE_ROOT / "acceptance-spec.json"


def _run_git(repository: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )


def _prepare_repository(output: Path) -> Path:
    repository = output / "nonprofit-checkout"
    shutil.copytree(BASE_REPOSITORY, repository)
    for relative in ("discounts.py", "check_discount.py"):
        path = repository / relative
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    _run_git(repository, "init", "--quiet")
    _run_git(repository, "config", "user.name", "Example Maintainer")
    _run_git(repository, "config", "user.email", "maintainer@example.invalid")
    _run_git(repository, "add", "discounts.py", "check_discount.py")
    _run_git(repository, "commit", "--quiet", "-m", "baseline checkout rule")
    normalized_patch = output / "agent-change.normalized.patch"
    normalized_patch.write_bytes(AGENT_PATCH.read_bytes().replace(b"\r\n", b"\n"))
    _run_git(repository, "apply", "--whitespace=error", str(normalized_patch))
    _run_git(repository, "add", "discounts.py")
    _run_git(
        repository,
        "commit",
        "--quiet",
        "--author",
        "Codex Example Agent <codex@example.invalid>",
        "-m",
        "agent: apply nonprofit discount",
    )
    return repository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a local agent change and verify it with Hive Mind OS."
    )
    parser.add_argument(
        "--output",
        default="example-out",
        help="new directory for the Git worktree and receipt bundle (default: ./example-out)",
    )
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        parser.error(f"output directory must not already exist: {output}")

    output.mkdir(parents=True)
    try:
        repository = _prepare_repository(output)
        candidate = subprocess.run(
            ("git", "-C", str(repository), "rev-parse", "HEAD"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if candidate.returncode != 0:
            raise RuntimeError("could not resolve the example candidate commit")
        bundle = output / "receipt-bundle"
        completed = subprocess.run(
            (
                sys.executable,
                "-m",
                "hive_mind_os.cli",
                "verify",
                "--repository",
                str(repository),
                "--spec",
                str(ACCEPTANCE_SPECIFICATION),
                "--candidate",
                candidate.stdout.strip(),
                "--output",
                str(bundle),
            ),
            cwd=EXAMPLE_ROOT.parents[1] / "src",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "hive-mind verify failed: " + completed.stderr.strip()
            )
        summary = json.loads(completed.stdout)
        verification = json.loads((bundle / "verification.json").read_text(encoding="utf-8"))
        if (
            summary.get("status") != "adopt"
            or verification.get("changed_paths") != ["discounts.py"]
            or verification.get("seal_sequence", 0)
            >= verification.get("repository_read_sequence", 0)
        ):
            raise RuntimeError("verification result did not satisfy the example contract")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Example failed: {error}", file=sys.stderr)
        return 1

    print("Example complete: committed Codex agent patch verified.")
    print(f"Repository: {repository}")
    print("Changed paths: discounts.py")
    print("Curator verdict: adopt; acceptance was sealed before the candidate was read.")
    print(f"Receipt bundle: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
