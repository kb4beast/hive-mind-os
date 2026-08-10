# Context Preservation and Repository Installation Map

## Provenance

- Original observed `main`: `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23`
- Original observed tree: `ac76686aa004cf8188f0281b1ec9ac1f5c666929`
- Plan ID: `hive-mind-os-verifiable-hive-cortex-v1`
- Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
- Extracted bundle manifest SHA-256: `ce0943ff5c0515169361929e14c77124899515f11a54b1dedb266fad9e26e5cd`
- Original ZIP SHA-256: `8e915a90d6488f55652820a9187ea537f411442cfc44cb57cad925b7740ee56b`

## Installation map

- Every file under the generated `REPO_ROOT/` directory was installed at its corresponding actual repository-root path.
- Every non-`REPO_ROOT` bundle artifact was preserved verbatim under this directory.
- The generated `prompts/` directory was preserved under `prompts/` here.
- `IMPLEMENTATION_LEVELS.md` was added under `docs/execution/` from the machine-readable dependency graph.
- `NEXT_SESSION_PROMPTS.md` was added under `docs/execution/` from the original copy-ready first parallel prompts.
- `USER_OBJECTIVE.md` preserves the user-provided subject and publication directives that the plan must continue to satisfy.

No enclosing `REPO_ROOT/` archive directory was installed into the repository root. The
archive copy here exists only to preserve analysis provenance and context; runtime and
controller paths live at their actual root locations.

## Context recovery order

1. `USER_OBJECTIVE.md`
2. `FULL_REPORT.md`
3. `ARCHITECTURE_DECISION.md`
4. `IMPLEMENTATION_PROGRAM.md`
5. `TOURNAMENT_RESULTS.json`
6. `SOURCE_REGISTER.md`
7. `RUN_CHECKPOINT.json`
8. repository-root `.autopilot/plan.json`
9. repository-root `docs/execution/IMPLEMENTATION_LEVELS.md`
10. repository-root `docs/execution/NEXT_SESSION_PROMPTS.md`
