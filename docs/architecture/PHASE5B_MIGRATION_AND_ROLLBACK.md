# Phase 5B migration and rollback

## Migration posture

Phase 5B is additive and inactive. It adds ordinary Python modules, tests, evidence, and
CI verification. It does not alter:

- root or package exports;
- CLI parsers;
- Generation Zero or Phase 5A behavior;
- Foundation database schema or authority mapping;
- public or private memory stores;
- projectors, Obsidian views, or federation;
- Explorer or Orchestrator runtime state;
- packaged JSON resources; or
- provider, tool, host, scheduler, or deployment configuration.

No backfill, dual write, pointer switch, or data migration occurs.

## Development use

An explicit caller may import the package-private compiler and submit a strict request.
The result is development metadata only. It is not proof that a design was independently
reviewed, selected, funded, implemented, verified, or activated.

## Future binding prerequisites

Before any active binding, a later court must provide:

1. authenticated actor and authority receipts;
2. durable request, design, checkpoint, and handoff storage;
3. actual hierarchical budget leases with reserve enforcement;
4. repository and host evidence acquisition through governed adapters;
5. held-out Architect behavioral evaluation;
6. separate Builder and Curator execution paths;
7. privacy, retention, and tenant-isolation review;
8. reversible champion pointer migration; and
9. independent Curator and Judge authorization.

## Rollback procedure

1. Stop explicit development imports of the Phase 5B candidate.
2. Remove the two Architect modules and focused tests.
3. Remove the Phase 5B inventory and evidence only through a reviewed change; retain
   published Git history.
4. Remove the Phase 5B installed-wheel verifier and restore the previous CI paths.
5. Remove ADR-034 from the current index while retaining the historical commit.
6. Re-run Generation Zero and Phase 2 through Phase 5A compatibility checks.

No database deletion or history rewrite is required. Existing champions remain unchanged.
