# Release version 1.1 integration ledger

- Release branch: `release/version_1.1`
- Main starting point: `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Integration date: 2026-07-30
- Preservation rule: original pull requests and source branches are not modified, closed, merged, or deleted by this integration.

## Stacked product and governance work

The exact PR stack from #28 through #42 is included through final stack head `0cbf581b77b77c1cdc15879a05164674fd5ae3ec`. Each PR base SHA equals the preceding PR head SHA, so the final head contains the complete ordered history.

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

## Independent dependency PRs

| PR | Source head | Release resolution |
|---:|---|---|
| #5 | `59d81845eb366583dee1efa1396058137acbc57f` | Applied the `actions/attest` pin `f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6` in release commit `94cda1ce2b37869678a5bb5b35b1f9da30612673`. |
| #6 | `1848ac70905f006a042a83b8dc0be02134068207` | The original `anchore/sbom-action` step was superseded within the stack by a checksum-pinned direct Syft `v1.50.0` installation. The release retains that newer hardened implementation rather than restoring the older action path. The original PR and branch remain preserved. |
| #7 | `ec9bfc65575573ead36c2c72c748725dc8018c93` | Applied `setuptools==83.0.0` in release commit `533b24a9e1f2b5836685be73d6f44fa7816f77b9`. |

## Exact ancestry preservation

The exact source commits for PRs #5, #6, and #7 are also ancestors of the release branch; their preservation does not rely only on equivalent patches or this ledger.

- Internal PR #43 merged exact PR #5 history into a branch rooted at exact PR #6 head; merge commit `7f5e471391a597ca96c55e476418b9fcba4df8cf`.
- Internal PR #45 combined that PR #5/#6 history with a branch rooted at exact PR #7 head; merge commit `f5940ae9a2038625959a9e45c47124d45f72017f`.
- Internal PR #46 merged the combined dependency history into `release/version_1.1`; merge commit `a2900fa2f394887084af5fa235357013adb7cbdc`.
- Comparing the pre-ancestry release head `d36a7ed648a195fdd353c2e20833f9f1f43ee75a` with `a2900fa2f394887084af5fa235357013adb7cbdc` yields ten additional commits and zero file changes. The merge changed ancestry only.
- Internal PR #44 was closed unmerged after GitHub detected conflicts in the first attempted merge direction. It did not modify an original PR or source branch.

## Scope boundary

This branch consolidates the existing work without changing `main`, retargeting the original source PRs, or deleting any original source ref. PR #6 is preserved as a superseded implementation proposal; its older workflow mechanism is not reintroduced over the stronger implementation already present in the stack.
