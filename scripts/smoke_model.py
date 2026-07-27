"""Manual network smoke test for P02. This script is not run in CI."""

from __future__ import annotations

import asyncio
import json

from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import provider_from_env
from hive_mind_os.models import Objective, Role, WorkItem
from hive_mind_os.roles import ROLE_CONTRACTS


async def main() -> None:
    provider = provider_from_env()
    ledger = EvidenceLedger()
    backend = ModelBackend(provider, ledger=ledger)
    objective = Objective("Return one schema-valid Orchestrator turn")
    work_item = WorkItem(objective.id, Role.ORCHESTRATOR, "Plan one bounded smoke task")
    result = await backend.execute(
        ROLE_CONTRACTS[Role.ORCHESTRATOR], work_item, objective, ()
    )
    receipt = ledger.events()[0]["payload"]
    print(
        json.dumps(
            {
                "success": result.success,
                "provider": receipt["provider_kind"],
                "model": receipt["model_id"],
                "request_digest": receipt["request_digest"],
                "response_digest": receipt["response_digest"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
