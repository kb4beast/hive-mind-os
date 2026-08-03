from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_ROOT = Path("evidence/live/B-GOV-07")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _canonical_text_bytes(value: bytes) -> bytes:
    """Return UTF-8 text with Git-compatible LF line endings."""
    return value.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode()


def _exact_dict(value: object, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{where} must be an exact dict")
    return value


def _codeowners(codeowners: str) -> list[str]:
    owners: set[str] = set()
    for line in codeowners.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        owners.update(field for field in fields[1:] if field.startswith("@"))
    if not owners:
        raise ValueError("CODEOWNERS has no owners")
    return sorted(owners)


def capture(
    repository: Path,
    *,
    owner: str,
    repo: str,
    pr_author: str,
    output_root: Path,
    collaborator_response: bytes,
) -> tuple[dict[str, Any], Path]:
    parsed = json.loads(collaborator_response.decode("utf-8"))
    if type(parsed) is not list:
        raise ValueError("collaborator response must be an exact list")
    collaborators = [_exact_dict(item, "collaborator") for item in parsed]
    raw_digest = _digest_bytes(collaborator_response)
    raw_path = (
        output_root
        / "collaborators"
        / "raw"
        / f"{raw_digest.removeprefix('sha256:')}.json"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(collaborator_response)

    write_capable: list[str] = []
    for collaborator in collaborators:
        login = collaborator.get("login")
        permissions = collaborator.get("permissions")
        if type(login) is not str or type(permissions) is not dict:
            raise ValueError("collaborator identity or permissions are malformed")
        if permissions.get("push") is True:
            write_capable.append(login)
    write_capable.sort()
    non_author = [login for login in write_capable if login != pr_author]

    codeowners_path = repository / ".github/CODEOWNERS"
    codeowners_bytes = _canonical_text_bytes(codeowners_path.read_bytes())
    codeowners = _codeowners(codeowners_bytes.decode("utf-8"))
    non_author_codeowners = [
        owner_id for owner_id in codeowners if owner_id != f"@{pr_author}"
    ]
    body = {
        "schema_version": 1,
        "record_type": "b-gov-07-reviewer-topology-receipt",
        "repository": f"{owner}/{repo}",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "pr_number": 48,
        "pr_author": pr_author,
        "collaborator_response": {
            "path": raw_path.relative_to(repository).as_posix(),
            "digest": raw_digest,
        },
        "write_capable_accounts": write_capable,
        "non_author_write_capable_accounts": non_author,
        "codeowners": {
            "path": ".github/CODEOWNERS",
            "digest": _digest_bytes(codeowners_bytes),
            "owners": codeowners,
            "non_author_owners": non_author_codeowners,
        },
        "claims": {
            "two_non_author_write_capable_accounts_observed": len(non_author) >= 2,
            "non_author_codeowner_coverage_observed": bool(non_author_codeowners),
            "reviewer_consent_observed": False,
            "human_independence_authenticated": False,
            "required_approvals_observed": False,
            "b_gov_07_resolved": False,
            "release_ready": False,
        },
        "remaining_obligations": [
            "obtain consent from genuinely independent eligible reviewers",
            "add approved non-author CODEOWNER coverage through a reviewed change",
            "obtain two non-author approvals including required code-owner approval on PR #48",
            "capture conflict, review, last-push, merge, and no-bypass receipts",
        ],
    }
    receipt = {**body, "receipt_digest": _digest_bytes(_canonical_bytes(body))}
    encoded = _canonical_bytes(receipt) + b"\n"
    destination = (
        output_root
        / "reconciliation"
        / f"{_digest_bytes(encoded).removeprefix('sha256:')}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return receipt, destination


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture bounded B-GOV-07 reviewer topology evidence."
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--owner", default="kb4beast")
    parser.add_argument("--repo", default="hive-mind-os")
    parser.add_argument("--pr-author", default="kb4beast")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--collaborator-response-stdin", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not args.collaborator_response_stdin:
        raise SystemExit("--collaborator-response-stdin is required")
    repository = args.repository.resolve()
    output_root = (
        args.output_root
        if args.output_root.is_absolute()
        else repository / args.output_root
    ).resolve()
    receipt, destination = capture(
        repository,
        owner=args.owner,
        repo=args.repo,
        pr_author=args.pr_author,
        output_root=output_root,
        collaborator_response=sys.stdin.buffer.read(),
    )
    print(destination)
    print(receipt["receipt_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
