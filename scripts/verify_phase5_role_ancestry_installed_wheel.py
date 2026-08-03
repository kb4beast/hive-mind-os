from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: object) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def verify_installed(index: dict[str, Any], installed_root: Path) -> dict[str, Any]:
    body = {key: value for key, value in index.items() if key != "index_digest"}
    if index.get("index_digest") != _digest_json(body):
        raise RuntimeError("role ancestry index digest is invalid")
    verified: list[dict[str, object]] = []
    for role in index["roles"]:
        paths = role["package_paths"]
        receipts = (role["implementation"], role["contract"])
        for relative, receipt in zip(paths, receipts, strict=True):
            installed_path = (installed_root / relative).resolve()
            if not installed_path.is_relative_to(installed_root.resolve()):
                raise RuntimeError(f"installed path escaped root: {relative}")
            if not installed_path.is_file():
                raise RuntimeError(f"installed role file is missing: {relative}")
            observed = _digest_bytes(installed_path.read_bytes())
            if observed != receipt["sha256"]:
                raise RuntimeError(f"installed role file drifted: {relative}")
        verified.append(
            {
                "phase_item": role["phase_item"],
                "role": role["role"],
                "package_paths": list(paths),
                "matches_git_subject": True,
            }
        )
    return {
        "schema_version": 1,
        "verification": "phase5-role-ancestry-installed-wheel",
        "subject_commit": index["subject_commit"],
        "index_digest": index["index_digest"],
        "verified_roles": verified,
        "role_count": len(verified),
        "authenticated_independence_claimed": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    result = verify_installed(index, args.installed_root.resolve())
    print(json.dumps(result, sort_keys=True))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
