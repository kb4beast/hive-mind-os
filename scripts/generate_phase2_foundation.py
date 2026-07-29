from __future__ import annotations

import argparse
from pathlib import Path

from hive_mind_os.foundation.generation import (
    compile_generation_zero_candidates,
    verify_generated_candidates,
)


def _observed(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.json"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check inert Phase 2 canonical candidates."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--root",
        type=Path,
        default=(
            Path(__file__).parents[1]
            / "src"
            / "hive_mind_os"
            / "foundation"
            / "generated"
        ),
    )
    args = parser.parse_args()
    expected = compile_generation_zero_candidates()
    if args.check:
        issues = verify_generated_candidates(_observed(args.root))
        if issues:
            raise SystemExit("\n".join(issues))
        print(f"verified {len(expected)} deterministic Phase 2 artifacts")
        return 0
    for relative, content in expected.items():
        destination = args.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    print(f"generated {len(expected)} deterministic Phase 2 artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
