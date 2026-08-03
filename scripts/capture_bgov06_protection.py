from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from hive_mind_os.github_adapter import GitHubClient

DEFAULT_OUTPUT_ROOT = Path("evidence/live/B-GOV-06")


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


def _exact_dict(value: object, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{where} must be an exact dict")
    return value


def _assert_agreement(
    expected: Mapping[str, Any],
    adapter: Mapping[str, Any],
    curator: Mapping[str, Any],
) -> list[str]:
    adapter_issues = GitHubClient._compare(expected, adapter, "adapter")
    curator_issues = GitHubClient._compare(expected, curator, "curator")
    if adapter_issues or curator_issues:
        raise RuntimeError(
            "live protection does not match declared rules: "
            + "; ".join((*adapter_issues, *curator_issues))
        )
    return sorted(expected)


def capture(
    repository: Path,
    *,
    owner: str,
    repo: str,
    branch: str,
    desired_rules_path: Path,
    output_root: Path,
    curator_response: bytes,
    token_env: str,
) -> tuple[dict[str, Any], Path]:
    desired = _exact_dict(
        json.loads(desired_rules_path.read_text(encoding="utf-8")), "desired rules"
    )
    expected = _exact_dict(desired.get("rules"), "desired rules.rules")
    curator_document = _exact_dict(
        json.loads(curator_response.decode("utf-8")), "curator response"
    )
    curator_observed = GitHubClient._branch_observation(curator_document)
    curator_digest = _digest_bytes(curator_response)
    curator_path = (
        output_root
        / "curator"
        / "raw"
        / f"{curator_digest.removeprefix('sha256:')}.json"
    )
    curator_path.parent.mkdir(parents=True, exist_ok=True)
    curator_path.write_bytes(curator_response)

    client = GitHubClient(owner, repo, output_root / "adapter", token_env=token_env)
    adapter_report = client.verify_protection(desired_rules_path, branch=branch)
    if not adapter_report.matches:
        raise RuntimeError(
            "adapter protection verification failed: "
            + "; ".join(adapter_report.mismatches)
        )
    agreement = _assert_agreement(expected, adapter_report.observed, curator_observed)
    adapter_declared = {key: adapter_report.observed[key] for key in expected}
    curator_declared = {key: curator_observed[key] for key in expected}
    captured_at = datetime.now(timezone.utc).isoformat()
    body = {
        "schema_version": 1,
        "record_type": "b-gov-06-admin-enforcement-receipt",
        "repository": f"{owner}/{repo}",
        "branch": branch,
        "captured_at": captured_at,
        "declared_rules_path": desired_rules_path.relative_to(repository).as_posix(),
        "adapter": {
            "method": "hive-mind-os-github-adapter",
            "matches": adapter_report.matches,
            "observed": adapter_declared,
            "report_path": (
                output_root.relative_to(repository)
                / "adapter"
                / adapter_report.evidence_path
            ).as_posix(),
            "report_digest": adapter_report.evidence_digest,
        },
        "curator_reproduction": {
            "method": "github-cli-rest-branch-protection",
            "raw_response_path": curator_path.relative_to(repository).as_posix(),
            "raw_response_digest": curator_digest,
            "observed": curator_declared,
            "authenticated_independence_claimed": False,
        },
        "agreed_rule_fields": agreement,
        "claims": {
            "enforce_admins_verified": True,
            "all_declared_rules_match": True,
            "protected_main_delivery_observed": False,
            "b_gov_06_resolved": False,
            "review_independence_established": False,
            "release_ready": False,
        },
        "remaining_obligations": [
            "complete PR #48 through required checks and reviews without administrator bypass",
            "preserve two non-author approvals and required code-owner approval",
            "capture the resulting protected main delivery receipt before closing B-GOV-06",
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
        description="Capture independently reproduced B-GOV-06 protection evidence."
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--owner", default="kb4beast")
    parser.add_argument("--repo", default="hive-mind-os")
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--desired-rules",
        type=Path,
        default=Path(".github/governance/required-repository-rules.json"),
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--curator-response-stdin", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not args.curator_response_stdin:
        raise SystemExit("--curator-response-stdin is required")
    repository = args.repository.resolve()
    desired_rules = (
        args.desired_rules
        if args.desired_rules.is_absolute()
        else repository / args.desired_rules
    ).resolve()
    output_root = (
        args.output_root
        if args.output_root.is_absolute()
        else repository / args.output_root
    ).resolve()
    receipt, destination = capture(
        repository,
        owner=args.owner,
        repo=args.repo,
        branch=args.branch,
        desired_rules_path=desired_rules,
        output_root=output_root,
        curator_response=sys.stdin.buffer.read(),
        token_env=args.token_env,
    )
    print(destination)
    print(receipt["receipt_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
