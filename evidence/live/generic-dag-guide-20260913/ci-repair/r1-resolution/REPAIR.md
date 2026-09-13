# Explicit authenticated history after normal clone transport

Builder: `/root/generic_guide_builder`. This repairs independent finding R1 on
the rejected, unpushed transport candidate
`6e134f6251fdd30b6da712df8342d1d8986093a5` (tree
`a38f5ce501198b87739743114e0e155c0bf5b080`). The independent finding and its
remote-tracking-only reproduction are preserved by root under
`evidence/live/generic-dag-guide-20260913/ci-repair/review-r1`.
Neither the initial failed CI nor the rejected repair attempt is replaced.

## Cause and correction

Normal clone transport fixes the source-private object-info copying race, but
does not fetch arbitrary objects retained solely through source remote-tracking
refs. Developer-local historical heads masked that difference. Two fixture
clones still took ROOT as their source and then switched to the historical
CORRECTION_PARENT SHA. That commit need not be reachable from an advertised
source branch in a CI checkout.

Those two clones now use `self.authoring_root`, whose setup first verifies the
existing pinned history and R4 bundle bytes/provenance, verifies prerequisites,
imports them, validates their advertised identities, and places the historical
CORRECTION_PARENT on its advertised TARGET_BRANCH. All five required historical
commits, including PLAN_AUTHORING_BASE used for replacement-object negatives,
are in that history. The negative base CORRECTION_PARENT^ is also reachable.
No new unverified history source or network dependency is added.

The unchanged authoring fixture extraction continues to copy the exact frozen
R4 payload from its authenticated bundle. The corrected clone transports Git
objects; it does not copy the dirty authoring worktree or its private metadata.
The existing fixture payload-copy/commit procedure is retained afterward.

All six `--no-local` flags remain. Original system/global configuration,
authenticated bytes, filters, worktree substitutions, and source-only metadata
marker checks remain. The source repair touches only the V3 fixture test file.

## Regression and cold validation

The existing
`test_history_bundle_supplies_required_objects_to_prerequisite_only_repository`
now invokes the actual `make_committed_checkout` helper while ROOT is patched
to the temporary prerequisite-only repository, after confirming that all five
required historical objects are absent there. It checks both the normal and
negative-parent bases, the resulting commit parent, and every exact required
historical tree. This ensures fixture construction depends on the explicitly
authenticated authoring source, rather than local incidental objects. All prior
bundle-before/after assertions are preserved.

`cold_history_probe.py` creates a `--no-local --single-branch --no-tags` clone of
only the candidate branch outside the subject. It proves all five historical
objects initially absent and the thin bundle prerequisite present. It copies
the exact repaired test bytes into this cold checkout and runs four tests:

1. The strengthened prerequisite-only history regression.
2. The original hostile system/global autocrlf test.
3. The authoring root/info-attribute boundary test.
4. The Git replace, hidden worktree and mode-substitution negatives.

`COLD-HISTORY-VALIDATION.json` and both `cold-focused` transcripts record the
actual result and commands. All four tests passed with exit 0 and no skips.
The validation script checks that all 457
original assertion-call ASTs are preserved; the candidate has 461, consisting
of the original assertions, two metadata assertions, and two history assertion
call sites used across both bases and five required commits.

The exact repaired test working-byte SHA-256 is
`ad124cebeea64f607b1897cad89b81c6798986340ad7afa90d827a994cc1cbfe`.
`git diff --check` passed. Root owns source after this batch and owns the final
commit, focused gate, independent exact-head review, and CI qualification.

## Compatibility, architecture, rollback and limits

No product runtime, schema, authority, source bundle, policy, or test burden
changes. There is no state migration. Source history now has an explicit
authenticated origin appropriate to normal Git transport. Negative historical
base and replacement-object cases remain exercised.

Rollback is a revert of this bounded fixture correction, preserving the
independent rejection and failed attempt as evidence. That would restore the
known CI history-availability gap. The earlier local metadata-copy race repair
is retained. No Git refs in ROOT/shared repositories are mutated by the cold
probe, and no remote effects, activation, or signing authority are involved.
The Windows cold validation cannot substitute for the Linux/Windows CI matrix;
it specifically removes the workstation's historical-branch masking condition.
