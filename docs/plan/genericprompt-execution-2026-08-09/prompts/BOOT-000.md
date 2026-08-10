# Copy-Ready Prompt — BOOT-000 One-Time Bootstrap

```text
Repository: kb4beast/hive-mind-os
Bootstrap node: BOOT-000
Bundle baseline: 7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23
Plan fingerprint: sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39

Use a fresh clean checkout with authenticated GitHub access. Do not implement any Hive Mind OS
product-runtime node. This session installs only the implementation control plane from the
provided GenericPrompt execution bundle.

1. Read all applicable AGENTS.md and CLAUDE.md.
2. Fetch current main and record its exact commit and tree. Current code overrides this bundle if
   main advanced; preserve the bundle baseline as provenance.
3. Create branch `autopilot/boot-000` from current main.
4. Copy the CONTENTS of the bundle’s `REPO_ROOT/` into the repository root. Do not commit an
   enclosing archive directory. The resulting root paths must include `.autopilot/`,
   `.github/workflows/autopilot-control-room.yml`, `docs/execution/`, `USER_GUIDE/`, and
   `ORIGINAL_PLAN.md`.
5. Confirm this node changes no Hive Mind OS product runtime behavior. Do not edit files outside
   BOOT-000 write scope.
6. Run:

   python -m compileall -q .autopilot/bin .autopilot/tests
   python -m unittest discover -s .autopilot/tests -v
   python .autopilot/bin/autopilot.py --repo-root . doctor --json

7. Repair only bootstrap-package defects. Do not weaken tests, schemas, locks, role-first
   consultation, anti-cheating rules, receipt requirements, or current repository governance.
8. Create a BOOT-000 completion receipt matching `.autopilot/receipt.schema.json`, binding exact
   base/final commits and trees, changed paths, tests, evidence, roles, authority, and rollback.
9. Push `autopilot/boot-000` and open a DRAFT PR into `main`. Do not merge or enable auto-merge.
10. Stop. Report the draft PR, exact head SHA, test results, doctor result, receipt path, and any
    adverse evidence. Do not start RECON-010 or BASE-020 in this session.

Minimum model: OpenAI GPT-5.6 Terra with medium reasoning, or Claude Sonnet 5 with medium effort.
Escalate only if current main creates a cross-cutting bootstrap conflict.
```
