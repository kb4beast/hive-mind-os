# Release Version 1.1 integration ledger

- Integration train: `1.1`
- Python distribution: `hive-mind-os==0.6.0`
- Release archive branch: `release/version_1.1`
- Pre-hardening release head: `07b19ba809b1be24d50f64de5a8704a760414db0`
- Immutable preservation ref: `archive/release-version_1.1-pre-hardening-2026-07-30`
- Main starting point: `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Integration date: 2026-07-30
- Preservation rule: original pull requests and source branches are not modified,
  closed, merged, force-updated, or deleted by this integration.

## Version terminology

The branch name and manifest identify **integration train 1.1**. They do not rename the
Python package. The distribution remains `0.6.0`, and CI derives the SBOM version from
the installed package metadata. A package-version change requires a separate release
decision and regenerated wheel/SBOM/provenance evidence.

## Accepted stacked product and governance work

The accepted stack #28, #29, and #31 through #42 is present in order through final
stack head `0cbf581b77b77c1cdc15879a05164674fd5ae3ec`. PR #30 is intentionally not
classified as accepted stack work; its losing candidate is dispositioned and preserved
separately below.

| PR | Head SHA |
|---:|---|
| #28 | `0948f7ec385238f5825ce7c39dd25de2e9a1035d` |
| #29 | `3298078c41ce69103eb2bdce61960a69dc6aab93` |
| #31 | `94e67cde15fa8a75d92561384241f0419c9f589b` |
| #32 | `7f7013c99d86bbd34f966b902bb873cf5c10d740` |
| #33 | `40a508b6b1bfb4a8624cf1ef8169384d32a39d44` |
| #34 | `7e26a56eab5fe79f075cccc57a6ff0a01fb9ef9a` |
| #35 | `ff2bbb14729cf8b3d1475a1d3ef0281f6e713e50` |
| #36 | `376a4a6082f6bdf154ba6252ccb70062a17a549b` |
| #37 | `2cbfe1d0e4dccd6f1758e5ddba10f799834bf857` |
| #38 | `316ee55da4ea7449bcdb934ab442ef0d95f54ba5` |
| #39 | `55ec59828dcd999723627219210e5b224c65a36f` |
| #40 | `59df5f5f2d0af45f403f74dac9781d2664f227cd` |
| #41 | `11e4a7b16b00e11caf59c231b5b718f14ed65195` |
| #42 | `0cbf581b77b77c1cdc15879a05164674fd5ae3ec` |

## Historical PR #30

PR #30 at `39e07c9e3c3ce439911481be2d38d901d05d4824` implemented a quarantined
`hive_mind_os_v2` alternative. The selected PR #31 foundation adapted most of its
contracts into `hive_mind_os.foundation` and rejected a second active namespace.

The exact PR #30 commit is preserved through a tree-neutral ancestry merge. The
selected tree does not copy the obsolete sibling package. See:

- `ADR-021-PR30-QUARANTINED-V2-FOUNDATION-NAMESPACE.md`;
- `PR30_SUPERSESSION_AND_DISPOSITION.md`; and
- `version_1.1-manifest.json`.

The exact preservation merge SHA is sealed in the manifest after the merge is created.

## Independent dependency PRs

| PR | Source head | Selected resolution |
|---:|---|---|
| #5 | `59d81845eb366583dee1efa1396058137acbc57f` | Retain the updated `actions/attest` commit pin. |
| #6 | `1848ac70905f006a042a83b8dc0be02134068207` | Preserve exact history, but retain the stronger checksum-pinned direct Syft `v1.50.0` implementation selected later. |
| #7 | `ec9bfc65575573ead36c2c72c748725dc8018c93` | Select `setuptools==83.0.0` and bind governance tests to that exact pin. |

## Existing dependency-history preservation

- Internal PR #43 merged exact PR #5 history into a branch rooted at exact PR #6
  head; merge commit `7f5e471391a597ca96c55e476418b9fcba4df8cf`.
- Internal PR #45 combined that history with a branch rooted at exact PR #7 head;
  merge commit `f5940ae9a2038625959a9e45c47124d45f72017f`.
- Internal PR #46 merged the combined dependency history into the release archive;
  merge commit `a2900fa2f394887084af5fa235357013adb7cbdc`.
- Comparing `d36a7ed648a195fdd353c2e20833f9f1f43ee75a` to `a2900fa...`
  produced ten additional commits and zero file changes.
- Internal PR #44 was an integration-only failed direction and was closed unmerged;
  no original PR or source branch was changed.

## Handoff correction

The old public/private-memory handoff is retained with a `SUPERSEDED — DO NOT
EXECUTE` banner. The current next-session objective is the conservative Phase 5A
Orchestrator handoff. It does not invent the unavailable off-repository wording and
cannot rely on the deferred Explorer comparison or resolve `B-OPS-09`.

## Authority and scope boundary

No merge is authorized by this ledger. The hardening work may produce an open draft
PR and exact-head CI evidence only. It does not modify `main`, activate a runtime,
resolve P20, close `B-OPS-09`, or claim production readiness, release readiness,
customer value, learning, promotion, or superiority.
