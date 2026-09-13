# Independent CI fixture transport review

Reviewer: `/root/continuity_repair_builder`, independent of builder
`/root/generic_guide_builder`. Exact subject
`6e134f6251fdd30b6da712df8342d1d8986093a5`, tree
`a38f5ce501198b87739743114e0e155c0bf5b080`, `C:/h/node-guide1`.
Comparison: previously reviewed `89925ecafc4ea4233ec921a26a6839bc2ca17f0a`.
Verdict: **revise — one actionable P2 finding**. The maintenance race mechanism
is corrected, but two ROOT-derived fixture paths still rely on objects normal
transport may not supply. Do not treat local focused passes as resolving this
different source-ref configuration.

## R1 / P2: supply authenticated historical objects after changing clone transport

Locations: `tests/test_generic_dag_v3_overlay.py:1389` in
`make_committed_checkout`, followed by the switch at line 1401; and the
ROOT-derived clone at line 4242 in
`test_authoring_authenticates_root_attributes_and_rejects_info_attributes_before_filters`,
followed by its switch to CORRECTION_PARENT. Both now use `--no-local` against
ROOT, then require historical commit
`28463ae6dd842b0b316fcf99eab98804cdaf9735`. Neither imports the pinned historical
bundle into its resulting clone. The separate `authoring_root` initialization
does import and verify the bundle, but that does not populate these ROOT clones.

Normal clone fetches the source's advertised branch/tag history needed by its
refspec, rather than copying all loose/packed objects from the source directory.
Objects retained only through the source's remote-tracking refs are therefore
not a reliable input. CORRECTION_PARENT is not an ancestor of this guide HEAD.
This developer repository has several local historical heads containing that
commit, masking the dependency. The retained actual CI log at line 100 shows
actions/checkout fetching `+refs/heads/*:refs/remotes/origin/*` and its PR merge
ref; that puts historical branches in a different namespace from this machine's
local heads. The repair changes an implicit object-availability assumption in
addition to excluding private commit-graph files.

Independent deterministic reproduction in `probe.py` creates a disposable
source with main plus a distinct commit retained only by
refs/remotes/origin/historical, matching the relevant CI namespace condition.
The old `clone --no-hardlinks` copies that object's storage and can switch to it.
The repaired `clone --no-local --no-hardlinks` preserves main but lacks the
historical object; switching to the supplied historical SHA exits 128 with
`fatal: unable to read tree`. The exact commands, refs, results and stderr are
in PROBE-RESULTS.json. No product test class or candidate source was executed or
modified to obtain this result.

Bounded correction: retain `--no-local`, but construct historical fixtures from
an explicitly authenticated historical object source. For example, clone the
already verified authoring fixture whose advertised branch contains the required
history, or verify/import the existing pinned bundle into each relevant ROOT
clone before selecting the historical base. Add a regression that models a
source with historical refs only under refs/remotes, so developer-only local
branches cannot mask it. Preserve all original assertions and the source-private
metadata marker checks. Do not restore local object-directory copying or relax
missing-object failures.

## Positive findings and independent evidence

- All **457** preexisting assert* call ASTs are retained exactly; the new version
  adds two marker assertions. Diff inspection found six added `--no-local`
  options and marker setup only. No original hostile autocrlf, observed-config,
  canonical/raw-byte, attribute, hook/filter or verifier assertion was weakened.
- The source-only metadata marker remains in its source and is excluded by
  transport. An independent old/new control reproduced the distinction.
- Three independent corrected clones overlapped eight actual
  `git commit-graph write --reachable --split` calls across **15** command
  intervals. All clones preserved main HEAD, tree and payload bytes and excluded
  the private marker. This supports the object-transport correction itself; it
  does not claim to reproduce the exact Linux lock-removal scheduling.
- All four CI repair MANIFEST artifact SHA-256/byte counts match immutable
  committed bytes and exact working evidence. The retained complete failed job
  log contains Git 2.55.0, the disappearing commit-graph-chain.lock error, and
  the reported 1,772 tests / one failure / 30 skips. The log representation is
  explicitly disclosed as gh API output through PowerShell UTF-8 redirection.
- All three guide documents are byte-identical to the prior reviewed commit.
  Product sources also remain unchanged. Prior guide status/authority/history
  review conclusions therefore stand; this finding concerns test-fixture history.
- Exact HEAD/tree and a clean candidate worktree were checked before and after
  the external synthetic probes.

## Scope and limits

No candidate worktree writes, runtime dispatch/activation, credentials, product
Git mutation or delivery occurred. Git commits/ref changes belong only to the
new external synthetic probe repository and its clones. Root's focused V3 tests
were not duplicated, and no full class or full suite was run. This review did not
consume root exec session 46722. The concurrent probe ran on Windows, and the
original Linux timing remains a retained CI observation rather than a recreated
schedule. Root owns subsequent repair, qualification and delivery.
