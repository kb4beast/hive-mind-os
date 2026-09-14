# N00 integration verifier rereview

## Verdict

**ACCEPT** for exact reviewed commit
`38ee04853824cd7c10320bd6cdf9ea34acef190c`.

The repair closes the prior live-path Git status defect. Every Git probe now
passes through one helper that captures `$LASTEXITCODE` immediately, rejects a
nonzero status before examining output, requires exactly one output item, and
rejects an empty or whitespace-only item before trimming it. The immutable
default verification passes, while the explicit live-checkout mode continues to
reject the intentional later source drift. No remaining blocker was found in
the requested verifier scope.

## Identity and sealed hashes

This rereview used fresh worktree `C:\h\wos-n00-integration-rereview` and branch
`codex/whole-os-n00-integration-rereview`, created directly from the reviewed
commit.

- reviewed commit: `38ee04853824cd7c10320bd6cdf9ea34acef190c`
- reviewed parent: `eccfc7b51363aa79afe5b087688c9f3362f270e6`
- reviewed tree: `e87c90c65b1f79e36033a013c78bf9b2ff51c3f9`
- `verify_n00.ps1` SHA-256:
  `90261c718f78e826e98de8ce95efdfd904c5df0521151de279877d4bedab2ae7`
- handoff `MANIFEST.json` SHA-256:
  `ffd07199c043d8825aaaf53588b0be31ad96238da07d9648a6b9a9a88636e5f5`
- handoff `local-source-manifest.json` SHA-256:
  `4951e6baa893cfefcd9e9f199b11236fc7347e4c690a0a0cd0e322222ea4f5c1`
- candidate `source-inventory.json` SHA-256:
  `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`

`git diff --name-only HEAD^ HEAD` named only
`docs/plan/whole-os-implementation/verify_n00.ps1`.
`git diff --check HEAD^ HEAD` exited 0. Both pinned commit
`d980a9cfe39f68b3de86ea0530234b3ab4e91390` and handoff commit
`3dc87ad0749ee468ed7ceab779d92c9446248b7e` are ancestors of the reviewed
commit.

## Canonical executions

From the fresh exact-commit worktree:

```powershell
powershell -NoProfile -File docs/plan/whole-os-implementation/verify_n00.ps1
```

Exit 0. The JSON receipt reported `PASS`, `pinned_snapshot`, 15 handoff files,
53 local-source paths, 32 successor sources, 15 founding sources, 18
requirements, 34 nodes, and 34 symbol classifications.

```powershell
powershell -NoProfile -File docs/plan/whole-os-implementation/verify_n00.ps1 `
  -RequireLiveCheckoutMatch
```

Exit 1 with `live local source drift:
src/hive_mind_os/tournament_plan_factory.py`, as required for the current
intentional drift.

`git status --porcelain=v1` was empty before and after both executions. An
independent object loop reproduced the recorded pinned tree
`47f873cf5924b97cfafafe1b9dfb0a450acb2e92`, all 53 pinned local-source blobs,
and all five handoff ADR blobs with zero missing objects or mismatches.

## Git-probe implementation inspection

`rg -n "\bgit\b|Invoke-GitSingleLine"` found one native Git invocation, inside
`Invoke-GitSingleLine`, and four helper call sites: pinned tree `rev-parse`, the
53 local-source `rev-parse` calls, live `hash-object`, and the five ADR
`rev-parse` calls. The helper performs these operations in order:

1. capture merged output into an array;
2. immediately copy `$LASTEXITCODE` to `$status`;
3. require status 0;
4. require exactly one output item;
5. require the item to be nonempty and non-whitespace; and
6. trim and return it.

No intervening command can overwrite the Git status before it is retained.

## Exhaustive adversarial replay

The attacks used an in-process PowerShell `git` shim. It matched the exact Git
arguments, delegated or supplied the known-good result for every non-target
probe, counted target hits, and changed no repository file. This allowed each
manifest-derived invocation to be targeted independently. For live probes after
the checkout's intentional drift, a scoped `Get-FileHash` shim supplied the
manifest-recorded live digest and the Git shim supplied expected non-target
blobs solely to reach every later `hash-object` call. Those controls test the
verifier's Git failure handling; they are not evidence that the drifted checkout
matches the manifest.

### Nonzero Git status

For each of the 59 `rev-parse` invocations (one tree, 53 local-source paths, five
ADRs), two executions were performed:

- exit 128 plus the exact expected valid-looking output; and
- exit 128 with no output.

All 118 executions hit the intended probe exactly once, failed immediately with
the typed `(git exit 128)` condition, and produced zero unexpected passes or
wrong-gate failures.

The same two attacks were applied independently to all 53 manifest-derived live
`hash-object` invocations. All 106 executions hit the intended probe exactly
once and failed with `(git exit 128)`, with zero unexpected results.

The exact prior counterexample now reports:

```text
cannot hash live local source: AGENTS.md (git exit 128)
```

It no longer continues to the later unrelated drift, and the captured status at
the failure remains 128. The no-output variant reports the same typed status
failure rather than a null `.Trim()` exception.

### Output cardinality and emptiness

Each of the same 59 `rev-parse` invocations was attacked once with two output
lines at exit 0 and once with one whitespace-only output item at exit 0. All 118
executions rejected the target with, respectively, `expected one output line`
or `empty output`.

Each of the 53 live `hash-object` invocations received the same two attacks. All
106 executions rejected the target with the expected typed condition. There
were zero unexpected results.

In total, the rereview executed 448 targeted hostile probe cases:

- 118 nonzero-status `rev-parse` cases;
- 106 nonzero-status `hash-object` cases;
- 118 output-shape `rev-parse` cases; and
- 106 output-shape `hash-object` cases.

## Read-only and independence statement

The canonical and adversarial verifier runs left `git status --porcelain=v1`
empty. The verifier contains no working-tree mutation command, and no observed
execution created or modified repository files.

This Curator rereview was performed independently in a fresh worktree. I did not
edit the verifier, manifests, inventory, implementation, or tests. The only
repository change on the review branch is this append-only report. The scope was
the N00 verifier repair, not a new judgment of all N00 artifacts or the full
campaign; no superiority or external-runtime claim is made.
