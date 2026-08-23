# Generic Hive Mind Product DAG V3

This directory contains an independently derived, inert Standard-V2 execution
overlay for the persisted generic Hive Mind product request. It is a sealed
design artifact, not an execution authorization. It never replaces or edits
`.autopilot/plan.json`, and its 20-node plan contains no runnable commands.

Payload A is preserved at commit
`4e2b81b932e5145f24c4b52ceeee664bff91df2e`. Its exact committed focused suite
exposed a two-test authoring-fixture defect (12/14). Its first five-path correction
is preserved as the sole direct child at
`f06e52c43a1e2d1d53523378c0d6f5564fb984bf`, tree
`8730203c89835c4d1d9dac4be9b2086dacd2d869`.

The `f06e52c` verifier inherited the caller environment and ran `git` through
`PATH`. A reproduced inherited `GIT_WORK_TREE` redirected its Git queries to a
different clean checkout. This successor therefore records
`QUALIFICATION_REMANDED_GIT_ENVIRONMENT_FAIL_OPEN` and proposes `ADAPT_REMAND` for
the v2 qualification conclusion; a distinct court must disposition that proposal.
The commit remains append-only, and the external report bytes are retained as
predecessor evidence under raw SHA-256
`731beb68c2fed2c1a3d8666530c1f193b2e21144428448816216b4f9b0bba810`.
This working payload proposes an append-only Git-boundary v3 correction: one exact
five-path, non-merge direct child of `f06e52c`, with ten embedded non-manifest
bindings plus the caller-authenticated manifest covering the complete ordered
11-path inventory. No final successor commit, tree, manifest digest, aggregate, or
qualification report is asserted before that child exists and a distinct court
binds it.

The intended post-implementation user surface is deliberately small:

```text
hive-mind autopilot run "foobar"
```

When `foobar` is the exact persisted subject and the current branch is the
already-persisted target, the future same-request fast path may consume a fresh,
host-authenticated V3 activation bundle. It must not regenerate a target merely
because the request was repeated. No checked-in file in this directory satisfies
that activation requirement, and an invalid V3 bundle may never fall back to the
historical plan.

## What is sealed here

- `source-intake.json` is the immutable Clerk intake: 58,463 bytes and SHA-256
  `dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c`.
- `node-contracts.json` is inert JSON containing 20 complete node contracts,
  exact typed durability, 85 single-owner write paths, and the exact 16-file
  frozen-host prerequisite.
- `traceability.json` preserves all 89 V1 requirement rows, each with at least
  one substantive acceptance target, plus V3 activation and threat corners.
- `ownership-effects.json` separates candidate-build effects from capabilities
  under test and separates the frozen candidate from the external Envelope B
  evidence worktree/branch.
- `materialize_plan.py` deterministically reads only the three inert JSON
  contracts and writes only this directory's `plan.json`.
- `manifest.json` pins request, objective, repository, launch, branch, snapshot
  lineage, standards, compiler, inputs, verifier, the expected external plan
  digest, the remanded `f06e52c` predecessor, historical Payload A, the exact
  five-path successor allowlist, and `authorship.execution_authority=NONE`.
- `verify_plan.py` verifies all manifest-declared bytes before interpreting
  authored JSON; it never imports or executes the materializer or target product
  Python. It requires an absolute canonical native Git executable and its
  caller-supplied raw SHA-256, rejects every inherited case-insensitive `GIT_*`
  variable, and never discovers Git through `PATH`. Its default mode accepts only
  an exact committed payload checkout and requires the caller to supply the
  manifest and Git bindings from independent evidence.
- `plan.json` is the sealed external `manual-parent-v1` plan. Its canonical
  digest is
  `sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1`.

## Safe authoring checks

These commands inspect or reproduce the inert overlay. Run them only in a fixture
whose `HEAD` is exactly `f06e52c`, with the current 11 manifest-bound payload files
overlaid and the five successor paths uncommitted. Replace the Git placeholder with
the direct native executable, not `git` by name, a `.cmd`/`.bat` wrapper, symlink,
or launcher shim. A conventional Git-for-Windows installation normally places the
direct core executable under `mingw64\bin\git.exe`; do not assume that location or
digest on another host.

The fixture must expose raw tracked bytes exactly as stored in Git blobs. On
Windows, create and switch the qualification clone with
`git -c core.autocrlf=false -c core.eol=lf ...`; an existing checkout whose line
endings were rewritten by `core.autocrlf` is intentionally rejected and must not be
used as committed qualification evidence.

```powershell
$repoRoot = (Resolve-Path -LiteralPath ".").Path
$overlayDir = Join-Path $repoRoot "docs/execution/dags/generic-hive-mind-product-v3"
$materializer = Join-Path $overlayDir "materialize_plan.py"
$verifier = Join-Path $overlayDir "verify_plan.py"
$dagStandard = Join-Path $repoRoot ".autopilot/bin/dag_standard.py"
$planPath = Join-Path $overlayDir "plan.json"
$gitExecutable = (Resolve-Path -LiteralPath "<ABSOLUTE-NATIVE-GIT-PATH>").Path
$manifestDigest = "sha256:" + (Get-FileHash -LiteralPath (Join-Path $overlayDir "manifest.json") -Algorithm SHA256).Hash.ToLowerInvariant()
$gitDigest = "sha256:" + (Get-FileHash -LiteralPath $gitExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
$ambientGitNames = @(Get-ChildItem Env: | Where-Object { $_.Name.StartsWith("GIT_", [StringComparison]::OrdinalIgnoreCase) } | Select-Object -ExpandProperty Name)
if ($ambientGitNames.Count -ne 0) { throw "Start a clean shell without inherited GIT_* variables: $($ambientGitNames -join ', ')" }

python $materializer --check
python $verifier `
  --repo-root $repoRoot `
  --overlay-dir $overlayDir `
  --expected-manifest-digest $manifestDigest `
  --git-executable $gitExecutable `
  --expected-git-executable-sha256 $gitDigest `
  --authoring-check
python $dagStandard dag-lint --strict --plan $planPath --expected-plan-digest sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1
python $dagStandard dag-rounds --plan $planPath --expected-plan-digest sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1
```

The rounds result must report exactly 20 `manual-parent-v1` rounds with one node
per round and every `command` value null. The locally computed manifest and Git
digests above are convenient only for non-qualifying authoring. `--authoring-check`
must return `committed_payload_qualification=false` and
`execution_qualification=false`; it never qualifies execution, activation, a
release, or a merge.

After the five-path successor is one exact non-merge direct child commit of
`f06e52c`, omit `--authoring-check` and use the manifest digest and Git executable
path/digest supplied by the independent court/Envelope B. Do not replace these
court inputs with values selected from the candidate or its `PATH`:

```powershell
$repoRoot = (Resolve-Path -LiteralPath ".").Path
$overlayDir = Join-Path $repoRoot "docs/execution/dags/generic-hive-mind-product-v3"
$verifier = Join-Path $overlayDir "verify_plan.py"
$courtManifestDigest = "sha256:<COURT-PINNED-64-HEX>"
$courtGitExecutable = "<COURT-PINNED-ABSOLUTE-NATIVE-GIT-PATH>"
$courtGitDigest = "sha256:<COURT-PINNED-64-HEX>"

python $verifier `
  --repo-root $repoRoot `
  --overlay-dir $overlayDir `
  --expected-manifest-digest $courtManifestDigest `
  --git-executable $courtGitExecutable `
  --expected-git-executable-sha256 $courtGitDigest
```

Committed mode rejects a missing caller digest, the precommit authoring state,
an extra or wrong-parent commit, any changed path outside the exact five-path
correction, any mismatch in the complete 11-path payload inventory, and dirty,
staged, or unapproved untracked/ignored checkout state. The sole explicit
exception is `.hive-mind/autopilot-request.json`.
It verifies the plan base, Payload A, and `f06e52c` objects and lineage. It requires
the raw `HEAD` tree and stage-zero index to have the same paths, modes, and blob
IDs, hashes every tracked worktree file directly, and rejects hidden
skip-worktree/assume-unchanged flags, ignored-only contamination, payload mode
substitution, object alternates, and replace objects.

Every Git invocation uses the caller-bound absolute executable with explicit
`--git-dir` and `--work-tree`, an argument list with no shell, and a minimal child
environment. The verifier rejects all inherited variable names beginning `GIT_`
case-insensitively, ignores the caller's `PATH`, and disables system/global config
plus locally dangerous fsmonitor, hook, global-attribute-file, global-excludes,
untracked-cache, and external-diff settings. Repository `.gitattributes` cannot
change the verifier's direct raw-byte blob proof. It reports variable names on
rejection, never their values.

The verifier rechecks the executable's path/open-handle identity and full digest
around every invocation, but this portable check detects rather than eliminates
all swap-and-restore races. The executable digest also does not bind its dynamic
loader, DLLs/shared objects, `libexec` helpers, or other runtime dependencies. A
passing committed check can mean `committed_payload_qualification=true`; it always
returns `execution_qualification=false` and `execution.authorized=false`.

## External activation boundary

Execution remains deferred until a host outside the candidate repository
provides all of the following as one authenticated, short-lived bundle:

1. Complete plan bytes plus manifest and expected-plan digests.
2. Reviewer, actor, and issuer identities with independent evidence.
3. Exact request, repository, objective, target, HEAD, tree, compiler, and
   Standard-V2 bindings, including proof that the successor is the sole direct
   child of `f06e52c` with exactly the five allowed changed paths.
4. The court-selected absolute canonical native Git executable and raw SHA-256,
   plus an externally attested read-only runtime bundle covering its loader,
   DLLs/shared objects, `libexec` helpers, and platform dependencies. POSIX needs
   an execution primitive equivalent to immutable pathname or file-descriptor
   custody; Windows needs deny-write/deny-delete or equivalent immutable volume,
   reparse-point, and ACL custody.
5. A pristine cache-free extraction of the pinned 16-file host, its interpreter,
   predecessor and new trust receipts, and a distinct signing principal or an
   enforced outside-repository deny sandbox.
6. A one-run nonce, deadline, and compare-and-swap ledger that rejects replay,
   collision, repeat-resume mismatch, and concurrent losers.
7. A signed minimum-version and revocation policy that requires
   `exact-append-only-git-boundary-correction-v3` and rejects the remanded
   `f06e52c` manifest, the Payload A manifest, predecessor activation, and every
   V1 fallback.

Qualification and handoff evidence belongs in the separate external Envelope B
evidence worktree/branch. It must not dirty or reidentify the frozen candidate.
Credentials, legal consent, spending, production, protected-branch changes,
missing evidence, or ambiguous authority remain typed blockers. The current
working payload does not authorize DAG execution, activation, release, deployment,
pull-request creation, protected-branch change, or merge.

SRC-024 remains quarantined with content unread. SRC-025 remains unresolved.
A5 is not ready, and this overlay makes no full-autonomy, production, release,
or superiority claim.
