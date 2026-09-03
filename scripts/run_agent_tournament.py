"""Checkout-local entry point for the agent-readiness tournament."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    tournament = importlib.import_module("hive_mind_os.agent_tournament")
    return int(tournament.main())


if __name__ == "__main__":
    raise SystemExit(main())
