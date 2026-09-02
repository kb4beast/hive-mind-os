# Generic Hive Mind Product DAG V3 — V5 baseline-recovery correction

This directory contains an inert Standard-V2 `manual-parent-v1` overlay for the
persisted Generic Hive Mind product request. Its 20-node plan has exactly 20 serial
one-node rounds and no runnable command. It is a qualification artifact, not an
activation or execution authorization, and it never edits `.autopilot/plan.json`.

The append-only lineage is:

- Payload A: commit `4e2b81b932e5145f24c4b52ceeee664bff91df2e`, tree
  `8c42aeaf4ed480dd3ccc353356b7fa9f3ed49157`;
- ambient-Git remand: commit
  `f06e52c43a1e2d1d53523378c0d6f5564fb984bf`, tree
  `8730203c89835c4d1d9dac4be9b2086dacd2d869`, with frozen report
  `evidence/autopilot/GENERIC-V3-DAG-QUALIFICATION-2026-08-23.md`, 17,703 bytes,
  SHA-256 `731beb68c2fed2c1a3d8666530c1f193b2e21144428448816216b4f9b0bba810`;
  and
- remanded Git-boundary correction: commit
  `9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8`, tree
  `0d0a251b6ff1557ca014b6b50c6f62ae787c4459`; and
- published V4 direct parent: commit
  `28463ae6dd842b0b316fcf99eab98804cdaf9735`, tree
  `72696b27cdd2c9cd08085c05c98513ece733cc8d`.

`9b1cbcfe` passed its implemented committed verifier and 19-test focused suite
under a pinned Windows Git engine, but it is remanded because its POSIX native-file
check accepted executable script wrappers and its suite did not implement the full
required adversarial matrix. Its frozen report is
`evidence/autopilot/GENERIC-V3-DAG-GIT-BOUNDARY-CORRECTION-QUALIFICATION-2026-08-23.md`,
23,865 bytes, SHA-256
`a4714e5d3f6ec01d77fed4e722a7f781ea7e83a2300001ebc3ed70463af693ff`.
The preserved observed status is
`QUALIFICATION_REMANDED_NATIVE_EXECUTABLE_FORMAT_AND_ADVERSARIAL_MATRIX_GAPS`
with author-proposed disposition `ADAPT_REMAND`. The report and predecessor commit
remain unchanged adverse evidence.

The published V4 tree was squash-merged as `59a5364501c5e49ceb28574aad7a4ac1512291b9`.
That commit has the same tree but not the V3 ancestry. Its first post-merge
Constitutional CI failed because the tests could no longer resolve `9b1cbcfe`. The
frozen assessment is
`evidence/audits/generic-v3-baseline-recovery/PREDECESSOR-28463AE-ASSESSMENT.json`,
SHA-256 `1ac71b791a36f5c2e543039d89604123a9b8f744e022bab23f549d481e472944`.

The current working contract is
`exact-append-only-squash-proof-windows-identity-correction-v5`: exactly one
non-merge direct child of `28463ae`, changing exactly eight predecessor files:
`.gitattributes`, `.github/workflows/ci.yml`, `ADR_INDEX.md`, this README,
`manifest.json`, `verify_plan.py`, `tests/test_autopilot_workflow.py`, and
`tests/test_generic_dag_v3_overlay.py`.
It also adds exactly nine durable evidence and decision files: ADR-070, ADR-071,
the thin Git bundle, its provenance record, the strict recovery source intake, the
two predecessor qualification reports named above, and the published-parent
assessment, plus the content-addressed raw-source archive bound by that intake.
Each changed blob must differ from the parent. ADR-069,
`materialize_plan.py`, `node-contracts.json`,
`ownership-effects.json`, `plan.json`, and `traceability.json` remain byte-for-byte
inherited. No future V5 commit, tree,
manifest digest, aggregate, report digest, or court result is asserted in these
candidate bytes.

## Easy user surface

The intended eventual command is simply:

```text
hive-mind autopilot run "foobar"
```

It may use a same-request fast path only when `foobar` exactly matches the persisted
subject and an external controller authenticates the complete successor request, target,
plan, payload, runtime, and one-run activation bundle. The command does not derive
authority from an existing branch, request repetition, repository contents, or a
locally calculated digest. No current file makes this command executable.

## V5 sealed content and policy names

- `manifest.json` has schema version `5`, kind
  `hive-mind-generic-product-overlay-manifest-v5`, and contract mode
  `exact-append-only-squash-proof-windows-identity-correction-v5`.
- `.gitattributes` is an authenticated payload member. It pins LF checkout bytes for
  itself, `LICENSE`, every current raw-bound repository text extension (`*.py`,
  `*.json`, `*.md`, `*.toml`, `*.yml`, and `*.yaml`), and all `*.ps1` PowerShell
  files while preserving every evidentiary `-text` override. A regression invariant
  rejects any future raw-byte-bound text path without deterministic `text eol=lf`
  coverage or an explicit `-text` exception. For the manifest-derived raw-bound path
  set, this authenticated root file is the sole accepted `.gitattributes` policy.
  Before any Git operation that can apply attributes or filters, an applicable
  non-root ancestor `.gitattributes` in the worktree, index, or HEAD is
  forbidden and the absence check is repeated at final repository stability. A
  nested file outside every currently bound ancestor chain is allowed; a future
  bound path beneath it makes it applicable and fails qualification closed. These
  are defined-phase observations, not atomic or universal concurrent-mutation
  exclusion.
- The Git policy is
  `caller-absolute-raw-sha256-host-native-image-windows-birthtime-v3`; the
  anti-downgrade image-policy
  identifier is `host-native-image-format-v1`; the execution-boundary enforced
  state is `HOST_NATIVE_IMAGE_FORMAT_V1`; and the maximum image size is
  268,435,456 bytes. The lowercase policy identifier and uppercase enforced-state
  enum have distinct roles and are both exact values.
- `source-intake.json` remains the immutable 58,463-byte Clerk intake with SHA-256
  `dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c`.
- `node-contracts.json` retains 20 complete node contracts, exact typed durability,
  85 single-owner write paths, and the exact 16-file frozen-host prerequisite.
- `traceability.json` retains all 89 V1 requirement rows and V3 threat corners.
- `ownership-effects.json` separates candidate effects, tested capabilities, and
  external Envelope B evidence.
- `materialize_plan.py` reads only the inert contracts and writes only this
  directory's `plan.json`.
- `plan.json` retains canonical plan digest
  `sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1`.
- `verify_plan.py` never imports or executes repository or materializer Python. It
  requires independent caller pins for both the raw manifest and direct Git image.

The manifest embeds 22 non-manifest bindings. An external caller supplies the raw
manifest digest, completing the non-circular 23-path inventory, and independently
supplies the already-canonical absolute Git path and raw image digest. Candidate
instructions, `PATH`, a suffix, a shebang, or executable permission cannot select
or authenticate those values.

## Host-native executable boundary

Before launch, the verifier bounds, opens, hashes, and parses the complete native
image:

- Windows accepts a valid host-compatible PE/COFF executable, not a DLL, with a
  bounded section table and an entry point file-backed by an executable section.
- Linux accepts a host-compatible ELF `ET_EXEC` or PIE `ET_DYN` with at least one
  executable `PT_LOAD` segment that file-backs its entry point.
- macOS accepts a host-compatible thin or selected fat/universal Mach-O
  `MH_EXECUTE` slice with exactly one `LC_MAIN` entry point file-backed by an
  executable segment; legacy `LC_UNIXTHREAD`-only images are rejected.
- Unsupported hosts and scripts, wrappers, links, malformed or truncated images,
  forged headers, and foreign-host images fail closed before launch.

The parser excludes script wrappers but cannot prove intent or reject every compiled
native delegator. The raw image digest does not cover the loader, DLLs/shared
objects, `libexec`, runtime data, operating-system services, or filesystem. Path,
handle, and digest rechecks also cannot observe a perfect swap-and-restore entirely
between observation points. Those limits require an externally attested read-only
runtime bundle and custody before execution.

Every Git invocation uses the bound absolute program directly with `shell=False`,
an argument list, a neutral working directory, explicit `--git-dir` and
`--work-tree`, and a minimal new child environment. The verifier rejects every
inherited case-insensitive `GIT_*` name, never searches caller `PATH`, rejects object
alternates, and disables dangerous config, hooks, attributes/excludes helpers,
external diff/textconv, fsmonitor, replacement objects, prompts, and implicit
repository discovery.

Executable identity is platform-scoped. Windows binds device, file ID, size,
modification time, and `st_birthtime_ns`; Python older than 3.12 falls back to the
legacy creation-time value exposed by `st_ctime_ns`. Raw Windows change time remains
diagnostic because it can differ between path and retained-handle observations.
POSIX continues to bind ctime. In every case the verifier parses and SHA-256 hashes
the exact same bounded byte snapshot, so a ctime-only allowance cannot admit a byte
change. This remains a point-observation proof and requires external read-only
custody for activation.

The `complete-autopilot-tree-point-observation-v2` observation adds a fail-closed
Windows filesystem boundary. Each directory and regular file binds
`st_file_attributes` plus every exposed stable optional metadata field across the
applicable path/open/before/after observations. Every directory and regular-file
stream enumeration is bracketed by before and after identity observations.
Directories must expose no data streams; regular files must expose exactly one
size-consistent unnamed `::$DATA` stream. Any named stream, unsupported enumeration
result, unavailable enumeration API, or enumeration error is rejected. This
statement is scoped to `.autopilot`; it does not claim the same attribute or stream
proof for the Git executable.

These finite, bracketed point observations are not an atomic filesystem transaction
and do not exclude concurrent mutation. A concurrent writer can create a named data
stream after its relevant enumeration and leave that ADS persistent, or mutate other
state between observation points. Windows ACL/security-descriptor bytes also remain
outside this proof. Execution therefore requires an external write-denying or
read-only custody boundary for the complete observed tree; point-observation
equality alone cannot support activation.

Output is incrementally bounded and overflow kills the child. Timeout kills and
reaps the child; inability to confirm termination is a distinct typed
`timeout-after-kill` failure. Non-UTF-8 output is a typed failure. The verifier
revalidates path/open identity, native format, and retained/current full digests
around every invocation and again before success.

## Required adversarial matrix

Committed qualification requires all 14 executable cases:

1. noncanonical, link, wrapper, and non-native rejection before launch;
2. truncated, forged, malformed, and wrong-host image rejection;
3. acceptance and branch proof for the actual pinned host Git image;
4. missing, malformed, wrong, and changed digest rejection;
5. executable mutation at every observable phase;
6. bounded-output overflow, kill, and typed failure;
7. timeout, kill-and-reap, and typed timeout-after-kill;
8. typed non-UTF-8 rejection;
9. exact absolute `Popen`, no shell, neutral cwd, explicit repository, and minimal
   environment assertions;
10. hostile hooks, attributes, excludes, external diff/textconv, fsmonitor, and
    helper markers that prove no helper ran;
11. non-stage-zero index-entry rejection;
12. predecessor report/status/lineage substitution and contract-downgrade rejection;
13. frozen-host and external-evidence substitution/self-review rejection; and
14. after a complete initial `.autopilot` point observation exists, complete final
    observation equality, including applicable Windows attribute/stream evidence,
    and no bytecode or other mutation on every success and rejection path. Rejection
    during the initial observation fails closed but makes no before/after equality
    claim because no complete initial reference exists.

Synthetic PE/ELF/thin-Mach-O/fat-Mach-O parser tests are required everywhere. They
do not replace actual Windows, Linux, and macOS host-launch evidence. A Windows
symlink test skipped for missing privilege is non-affirmative, and the new
file-attribute and named-stream checks do not satisfy it; a privilege-capable
Windows runner remains required. A missing macOS runner is a blocking evidence
obligation for any macOS-host claim. Those gaps may be reported by a court while
qualifying only inert, non-executing content; they can never support execution or
activation.

## Safe checks with external pins

Use values obtained from an independent caller or court receipt. Do not compute the
expected manifest digest from the candidate for qualification, and do not discover
Git by name or through `PATH`.

Both authoring and committed qualification repositories must begin as
`--no-checkout` clones. Set repository-local `core.autocrlf=false`, `core.eol=lf`,
and `core.longpaths=true` before the first working-tree checkout. On Windows, choose
a deliberately short absolute qualification root that can materialize the longest
tracked repository path; do not accept a deeply nested temporary root by default.
Then create or select the named `release/hive-mind-autopilot` branch at the intended
parent or candidate. Inspect the checkout's native exit code immediately after it
returns (PowerShell: `if ($LASTEXITCODE -ne 0) { throw "checkout failed" }`) and
never qualify a detached HEAD. A nonzero checkout or any partial materialization
abandons the entire clone; do not repair or qualify it in place, and retry only from
a new `--no-checkout` clone at a sufficiently short root. The verifier's exact clean
HEAD/index/worktree inventory independently rejects missing or incomplete tracked
content, but is not a substitute for the immediate exit-code check. Before
materialization, verification, lint, rounds, focused tests, or full CI, reject every
inherited environment name beginning `GIT_` under case-insensitive comparison
without printing its value. This outer preflight complements the verifier's own
branch, raw-byte, and inherited-environment rejection.
The verifier requires that exact live branch in both modes, and the focused
committed-mode matrix explicitly tests rejection of both detached HEAD and a wrong
named branch.

Focused and full Python gates must import from this candidate. Either put the
candidate's absolute `src` first in the gate's import path with no competing checkout,
or use a checkout-owned isolated runtime. Before accepting each gate, record the
resolved `hive_mind_os.__file__` and require it to reside beneath the candidate's
`src/hive_mind_os` directory. The full gate remains
`python -m unittest discover -s tests -v` under that pinned environment. This check
prevents a stale user-level editable install from serving as the recorded candidate
import; it does not attest all transitive dependencies or exclude concurrent
environment mutation.

For authoring, use that raw-byte checkout at exact parent `28463ae`, overlay the 23
current payload members, and leave exactly the seventeen V5 paths uncommitted. Eight
are modified predecessor files; nine are new, self-contained history, decision,
source, and qualification records: `ADR-070`, `ADR-071`, the thin Git bundle, its
provenance record, the strict external-source intake, the two predecessor
qualification reports, the published-parent assessment named above, and the
raw-source archive.

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$repoRoot = (Resolve-Path -LiteralPath ".").Path
$overlayDir = Join-Path $repoRoot "docs/execution/dags/generic-hive-mind-product-v3"
$materializer = Join-Path $overlayDir "materialize_plan.py"
$verifier = Join-Path $overlayDir "verify_plan.py"
$dagStandard = Join-Path $repoRoot ".autopilot/bin/dag_standard.py"
$planPath = Join-Path $overlayDir "plan.json"
$externalManifestDigest = "sha256:<EXTERNAL-CALLER-PINNED-64-HEX>"
$externalGitExecutable = "<EXTERNAL-CALLER-PINNED-ABSOLUTE-NATIVE-GIT-PATH>"
$externalGitDigest = "sha256:<EXTERNAL-CALLER-PINNED-64-HEX>"

python -B $materializer --check
if ($LASTEXITCODE -ne 0) { throw "materialize_plan.py --check failed with exit code $LASTEXITCODE" }
python -B $verifier `
  --repo-root $repoRoot `
  --overlay-dir $overlayDir `
  --expected-manifest-digest $externalManifestDigest `
  --git-executable $externalGitExecutable `
  --expected-git-executable-sha256 $externalGitDigest `
  --authoring-check
if ($LASTEXITCODE -ne 0) { throw "verify_plan.py authoring check failed with exit code $LASTEXITCODE" }
python -B $dagStandard dag-lint --strict --plan $planPath --expected-plan-digest sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1
if ($LASTEXITCODE -ne 0) { throw "dag-lint failed with exit code $LASTEXITCODE" }
python -B $dagStandard dag-rounds --plan $planPath --expected-plan-digest sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1
if ($LASTEXITCODE -ne 0) { throw "dag-rounds failed with exit code $LASTEXITCODE" }

$forbiddenPythonCache = @(
  Get-ChildItem -LiteralPath (Join-Path $repoRoot ".autopilot") -Recurse -Force -ErrorAction Stop |
    Where-Object {
      ($_.PSIsContainer -and $_.Name -ceq "__pycache__") -or
      (-not $_.PSIsContainer -and $_.Extension -ieq ".pyc")
    }
)
if ($forbiddenPythonCache.Count -ne 0) {
  throw "Safe checks left forbidden Python bytecode under .autopilot: $($forbiddenPythonCache.FullName -join ', ')"
}
```

Authoring mode must return
`authoring-squash-proof-windows-identity-correction-v5-non-executing`,
`committed_payload_qualification=false`, `execution_qualification=false`, and
`execution.authorized=false`. Its `autopilot_tree` result uses schema
`complete-autopilot-tree-point-observation-v2` and reports
`observed_unchanged=true`, `concurrent_mutation_exclusion=false`, and
`requires_external_read_only_custody_for_execution=true`. Here
`observed_unchanged=true` means only that complete initial and final point
observations compared equal; it does not exclude a concurrent ADS or other mutation.
The rounds output must contain exactly 20 `manual-parent-v1` one-node rounds and
every `command` must be null.

After the exact seventeen-path child is committed directly on `28463ae`, use the same
external receipt fields without `--authoring-check`:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$repoRoot = (Resolve-Path -LiteralPath ".").Path
$overlayDir = Join-Path $repoRoot "docs/execution/dags/generic-hive-mind-product-v3"
$verifier = Join-Path $overlayDir "verify_plan.py"
$externalManifestDigest = "sha256:<EXTERNAL-COURT-PINNED-64-HEX>"
$externalGitExecutable = "<EXTERNAL-COURT-PINNED-ABSOLUTE-NATIVE-GIT-PATH>"
$externalGitDigest = "sha256:<EXTERNAL-COURT-PINNED-64-HEX>"

python -B $verifier `
  --repo-root $repoRoot `
  --overlay-dir $overlayDir `
  --expected-manifest-digest $externalManifestDigest `
  --git-executable $externalGitExecutable `
  --expected-git-executable-sha256 $externalGitDigest
if ($LASTEXITCODE -ne 0) { throw "verify_plan.py committed check failed with exit code $LASTEXITCODE" }

$forbiddenPythonCache = @(
  Get-ChildItem -LiteralPath (Join-Path $repoRoot ".autopilot") -Recurse -Force -ErrorAction Stop |
    Where-Object {
      ($_.PSIsContainer -and $_.Name -ceq "__pycache__") -or
      (-not $_.PSIsContainer -and $_.Extension -ieq ".pyc")
    }
)
if ($forbiddenPythonCache.Count -ne 0) {
  throw "Safe checks left forbidden Python bytecode under .autopilot: $($forbiddenPythonCache.FullName -join ', ')"
}
```

Committed success returns mode
`committed-squash-proof-windows-identity-correction-v5` and may set
`committed_payload_qualification=true`. It always returns
`execution_qualification=false` and `execution.authorized=false`. Its
`autopilot_tree` result has the same
`complete-autopilot-tree-point-observation-v2` schema and the same three explicit
observation/custody fields as authoring mode. It rejects a missing caller pin,
authoring state, wrong parent or extra commit, an imprecise seventeen-path diff, changed
inherited blob, unchanged required correction blob, dirty index/worktree,
unapproved untracked or ignored path, non-stage-zero index, alternate object source,
hidden visibility flag, source substitution, downgrade, or observed `.autopilot`
mutation. A rejection during the initial observation has no before/after equality
claim because no complete initial reference exists.

## External activation and deferred actions

Execution requires a host-external authenticated bundle that binds complete plan
and manifest bytes; request, repository, objective, launch, branch, HEAD, tree, and
aggregate; external manifest and native Git pins; a read-only dependency-complete
runtime; platform launch/custody evidence; the frozen host and interpreter;
independent reviewer/actor/issuer identities; predecessor remand and revocation;
and a one-run nonce, deadline, and compare-and-swap ledger. A minimum-version policy
must reject published V4, `9b1cbcfe`, `f06e52c`, Payload A, and every V1 fallback.

Qualification receipts belong in a separate external Envelope B evidence lineage
and must not dirty or reidentify the candidate. Credentials, legal consent,
spending, production, signing, missing evidence, protected-branch changes, and
ambiguous authority remain typed blockers.

Every command remains null. DAG execution, activation, release, deployment,
pull-request creation, protected-branch change, and merge are deferred. Rollback is
append-only and preserves Payload A, `f06e52c`, `9b1cbcfe`, published V4, all frozen
reports, failed and passing observations, V5 evidence, and dissent. It never reactivates
a predecessor or legacy fallback.

`SRC-024` remains quarantined with content unread. `SRC-025` remains unresolved.
A5 is not ready. This overlay makes no full-autonomy, product-completion,
production, release, execution, merge, or superiority claim.
