# ADR-069: V4 native-executable correction for the Generic Hive Mind V3 execution DAG

- Status: proposed `adapt`; distinct Curator and Judge disposition pending
- Date: 2026-08-23
- Scope: repeated persisted-subject Autopilot invocation and its bounded product-completion DAG
- Immutable plan authoring base: commit `42b4aeef17f816430a7d8a435102635afea8761a`, tree `b896e16755a1d6864989757732fdc5ca9d2b5eed`
- Immutable historical Payload A: commit `4e2b81b932e5145f24c4b52ceeee664bff91df2e`, tree `8c42aeaf4ed480dd3ccc353356b7fa9f3ed49157`
- Immutable ambient-Git remand: commit `f06e52c43a1e2d1d53523378c0d6f5564fb984bf`, tree `8730203c89835c4d1d9dac4be9b2086dacd2d869`
- Immutable V4 direct parent: commit `9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8`, tree `0d0a251b6ff1557ca014b6b50c6f62ae787c4459`
- Immutable Clerk intake: `docs/execution/dags/generic-hive-mind-product-v3/source-intake.json`, 58,463 bytes, SHA-256 `dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c`

## Context and preserved adverse evidence

The intended user surface remains as small as:

```text
hive-mind autopilot run "foobar"
```

That command does not itself confer authority. A future same-request fast path may
reuse an exact persisted subject and target only when an external controller binds
the request, repository, objective, launch, branch, plan, payload, executable, and
activation identity. Repetition, an existing branch, or a checked-in digest is not
an execution grant.

Every earlier payload remains append-only evidence. Payload A at `4e2b81b` exposed
an exact-commit 12-of-14 focused-test defect. Its correction at `f06e52c` passed its
focused tests but allowed ambient `GIT_*` variables and `PATH` to redirect its Git
proof. The next correction at `9b1cbcfe` bound an absolute Git path and raw digest,
scrubbed the Git environment, and qualified its exact inert committed payload under
the recorded Windows engine. It nevertheless failed its own intended acceptance
boundary: on POSIX an executable script wrapper could satisfy the file checks and
delegate to Git, and its 19-test suite did not implement the complete required
adversarial matrix.

The frozen report recording that later remand is
`evidence/autopilot/GENERIC-V3-DAG-GIT-BOUNDARY-CORRECTION-QUALIFICATION-2026-08-23.md`,
exactly 23,865 bytes with raw SHA-256
`a4714e5d3f6ec01d77fed4e722a7f781ea7e83a2300001ebc3ed70463af693ff`.
It records `ADAPT/REMAND` as the author recommendation for `9b1cbcfe`; it is not
rewritten, superseded silently, or treated as a qualification receipt. The earlier
`f06e52c` report also remains frozen at 17,703 bytes with SHA-256
`731beb68c2fed2c1a3d8666530c1f193b2e21144428448816216b4f9b0bba810`.

This ADR proposes V4 as exactly one non-merge direct child of `9b1cbcfe`. Its final
commit, tree, manifest digest, ordered line-manifest digest, full-payload aggregate,
qualification report, and court verdict do not exist while these candidate bytes
are authored and are intentionally not asserted here.

## Decision

Adopt an append-only successor contract named
`exact-append-only-native-executable-matrix-correction-v4`. It retains the sealed
external Standard-V2 `manual-parent-v1` overlay: 20 nodes, 28 raw edges, 17 levels,
six intentionally redundant direct edges, exactly 20 serial one-node rounds, and
no runnable command. It corrects evidence qualification only; it does not activate
the DAG.

The V4 child changes exactly these six regular-file paths, and every one must have
a blob different from `9b1cbcfe`:

1. `.gitattributes`;
2. `docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md`;
3. `docs/execution/dags/generic-hive-mind-product-v3/README.md`;
4. `docs/execution/dags/generic-hive-mind-product-v3/manifest.json`;
5. `docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py`; and
6. `tests/test_generic_dag_v3_overlay.py`.

`.gitattributes` is authenticated payload, not ambient checkout policy. It pins LF
checkout bytes for itself, `LICENSE`, every current raw-bound repository text
extension (`*.py`, `*.json`, `*.md`, `*.toml`, `*.yml`, and `*.yaml`), and every
PowerShell file (`*.ps1`). Existing evidentiary byte domains retain their explicit
`-text` rules. A regression invariant rejects any future raw-byte-bound text path
that lacks either deterministic `text eol=lf` coverage or an explicit `-text`
exception, so adding a new text format cannot silently reintroduce checkout-dependent
content.

For the manifest-derived raw-bound path set, that authenticated root file is the
sole accepted `.gitattributes` policy. Before any Git operation that can apply
attributes or filters, the verifier rejects an applicable non-root ancestor
`.gitattributes` found in the worktree, index, or HEAD, and repeats that
check during final repository stability verification. A nested `.gitattributes`
whose directory is outside the ancestor chain of every currently bound path remains
allowed. If a future manifest or frozen-host binding names a path beneath that
directory, the existing nested file becomes applicable and qualification fails
closed. These checks are observations at defined phases, not a claim of atomic or
universal concurrent-mutation prevention.

It inherits the other six members of the ordered 12-path payload inventory
byte-for-byte and blob-for-blob from `9b1cbcfe`: `ADR_INDEX.md`,
`materialize_plan.py`, `node-contracts.json`, `ownership-effects.json`, `plan.json`,
and `traceability.json`. Any addition, deletion, mode change, merge parent, wrong
parent, unchanged required correction blob, or changed inherited blob fails closed.

### V4 manifest and independent caller bindings

`manifest.json` uses schema version `4`, kind
`hive-mind-generic-product-overlay-manifest-v4`, and the committed payload mode
`exact-append-only-native-executable-matrix-correction-v4`. It preserves complete
bindings for Payload A, the remanded `f06e52c` predecessor, and the remanded
`9b1cbcfe` predecessor, including their commits, trees, manifests, aggregates,
observed statuses, reports, and proposed dispositions. The V4 predecessor binding
includes:

- commit `9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8` and tree
  `0d0a251b6ff1557ca014b6b50c6f62ae787c4459`;
- manifest 16,533 bytes with SHA-256
  `87b9fa29dbcd0577328eb1298413994433c43a150f0f9c3b1ca2f498e0929f9e`;
- aggregate domain
  `hive-mind-os/v3-append-only-git-boundary-correction-content/v3`, 499,012 bytes,
  with SHA-256
  `5eb7aee3582095465a7e1a030d360ca205048ae0e8abaceab6f63f212df88477`;
- the frozen 23,865-byte remand report and its raw SHA-256
  `a4714e5d3f6ec01d77fed4e722a7f781ea7e83a2300001ebc3ed70463af693ff`;
- observed status
  `QUALIFICATION_REMANDED_NATIVE_EXECUTABLE_FORMAT_AND_ADVERSARIAL_MATRIX_GAPS`; and
- author-proposed disposition `ADAPT_REMAND`.

The checked-in manifest embeds the eleven non-manifest payload bindings. It cannot
authenticate itself: an independent caller must supply the exact raw manifest
SHA-256. The executable is also an independent caller input. The manifest must not
select it, derive it through `PATH`, or replace the caller's expected digest with a
digest computed from an untrusted candidate instruction.

The exact executable policies are:

```text
git_execution_policy=caller-absolute-raw-sha256-host-native-image-v2
activation_anti_downgrade.required_git_executable_format_policy=host-native-image-format-v1
git_execution_boundary.native_executable_format=HOST_NATIVE_IMAGE_FORMAT_V1
maximum_native_executable_bytes=268435456
```

The lowercase value is the versioned anti-downgrade policy identifier; the
uppercase value is the enforced-state enum inside the Git execution boundary.
They have distinct roles and are both exact, required values.

The caller supplies an already-canonical absolute Git executable path and a
lowercase `sha256:<64-hex>` digest of its raw bytes. Those values, the caller's raw
manifest digest, and the eventual V4 HEAD/tree/aggregate must be authenticated in
Envelope B by a principal and custody boundary outside the candidate repository.

### Host-native executable parser policy

Before any subprocess launch, the verifier must bound the executable at 268,435,456
bytes, retain its open handle, hash the complete bytes, and parse the image itself.
Suffix, executable permission, shebang, MIME label, or caller assertion is never a
substitute for format validation.

- On Windows, accept only a structurally valid host-compatible PE/COFF executable:
  bounded DOS and PE headers, valid optional header, executable-image semantics,
  no DLL characteristic, bounded section table and raw ranges, and at least one
  executable section that file-backs the declared entry point.
- On Linux, accept only a structurally valid host-compatible ELF image whose type
  is `ET_EXEC` or PIE `ET_DYN`, with bounded headers and at least one executable
  `PT_LOAD` segment that file-backs the declared entry point.
- On macOS, accept only a structurally valid host-compatible thin or selected
  fat/universal Mach-O slice of file type `MH_EXECUTE`, with bounded load commands
  and exactly one `LC_MAIN` entry point file-backed by an executable segment.
  Legacy `LC_UNIXTHREAD`-only executables are deliberately outside this V4 policy.
- On every other host, fail closed before launch. A foreign-host PE, ELF, or Mach-O
  image, a truncated image, a forged header, a script, a symlink, a wrapper script,
  or a noncanonical path is rejected.

This format proof closes the demonstrated script-wrapper gap. It does not prove
program intent: a compiled native delegator can still satisfy its host format and
forward to another program. Nor does the raw executable digest bind the dynamic
loader, DLLs/shared objects, `libexec` helpers, locale/runtime data, operating-system
services, or filesystem implementation. Those remain external runtime-bundle and
custody obligations.

### Repository and launch boundary

Both authoring and committed qualification repositories must start as
`--no-checkout` clones. Before the first working-tree checkout, the repository-local
configuration must set `core.autocrlf=false`, `core.eol=lf`, and
`core.longpaths=true`. On Windows, the clone must use a deliberately short absolute
qualification root that can materialize the repository's longest tracked path; a
deep temporary-directory default is not acceptable evidence. The first checkout
must create or select the named `release/hive-mind-autopilot` branch at the intended
parent or candidate; detached HEAD qualification is prohibited. The outer driver
must inspect the checkout's native exit code immediately after that process returns.
Any nonzero exit or partial materialization abandons the entire clone; it may not be
repaired or qualified in place, and the next attempt starts from a new
`--no-checkout` clone at a sufficiently short root. The verifier's exact clean
HEAD/index/worktree inventory independently rejects missing or incomplete tracked
content, but does not replace the checkout exit check. Before entering any
materialization, verification, lint, rounds, focused-test, or full-CI phase, the
outer qualification driver must reject inherited environment names beginning
`GIT_` under case-insensitive comparison, without revealing their values. These
checkout and outer-driver requirements complement the verifier's own fail-closed
branch, raw-byte, and inherited-environment checks; they do not replace them.
The verifier requires the live branch name to equal
`release/hive-mind-autopilot` in both modes. The focused committed-mode matrix
explicitly exercises and requires rejection of both detached HEAD and an alternate
named branch.

The V4 verifier retains the V3 repository controls. Before Git, it rejects every
inherited environment name beginning `GIT_` under case-insensitive comparison and
does not reveal values. It resolves `.git`, linked-worktree `commondir`, object
directory, worktree, and index explicitly and rejects object alternates. Each call
uses the caller-bound absolute executable as both the program and subprocess
executable, an argument list, `shell=False`, a neutral working directory, explicit
`--git-dir` and `--work-tree`, and a new minimal host environment. There is no
`PATH` search.

System and global Git config, replacement objects, lazy fetch, prompts, hooks,
fsmonitor, untracked cache, global attributes and excludes, external diff,
textconv, optional locks, and implicit repository discovery are disabled or
rejected. The verifier compares the raw HEAD tree, stage-zero index, and directly
hashed worktree bytes; rejects non-stage-zero entries and hidden index flags; checks
untracked plus ignored contamination; proves exact parent/tree/diff/inventory; and
records a final complete point observation before returning.

The `complete-autopilot-tree-point-observation-v2` observation has an additional
fail-closed Windows boundary. Every directory and regular-file row binds
`st_file_attributes` and every exposed stable optional metadata field across its
applicable path/open/before/after observations. Each directory and regular-file
stream enumeration is itself bracketed by before and after identity observations.
Directories must expose no data streams; regular files must expose exactly one
size-consistent unnamed `::$DATA` stream. Any named stream is rejected. An
unavailable stream-enumeration API, unsupported result, or enumeration error also
fails closed. This rule is scoped to the complete `.autopilot` observation and is
not a claim that the Git executable's attributes or streams have been bound by the
same proof.

These finite, bracketed point observations are not an atomic filesystem transaction
and do not exclude concurrent mutation. A concurrent writer can create a named data
stream after its relevant enumeration and leave that ADS persistent, or mutate other
state between observation points. Windows ACL/security-descriptor bytes also remain
outside this proof. Execution therefore requires an external write-denying or
read-only custody boundary for the complete observed tree; point-observation
equality alone cannot support activation.

The executable path, retained handle, identity, format, and both retained/current
full digest are revalidated around every invocation and before success. Subprocess
output is incrementally bounded. Overflow must kill the child and return a typed
failure. Timeout must kill the child and return a typed timeout; failure to confirm
termination after the kill is a distinct typed `timeout-after-kill` failure. Non-
UTF-8 output is a typed failure rather than replacement-decoded evidence.

## Mandatory 14-case adversarial matrix

V4 qualification requires executable tests for every numbered case below. A prose
claim, code-path inspection, or coverage by a neighboring case is not a substitute.

1. Reject noncanonical, link, wrapper-script, and non-native executable inputs
   before launch.
2. Reject truncated, forged, malformed, and wrong-host PE/ELF/Mach-O images in the
   native parser.
3. Accept the actual host's independently pinned direct native Git executable and
   prove that the intended host-native parser branch ran.
4. Reject missing, malformed, wrong, or changed manifest and executable digests.
5. Detect executable path, identity, format, or digest mutation at every observable
   phase: initial bind, immediately before launch, while a call is outstanding where
   observable, immediately after return, between calls, and final success recheck.
6. Bound combined subprocess output, kill on overflow, and return the typed overflow
   failure without accepting partial output.
7. Exercise timeout, successful kill-and-reap, and the distinct typed
   timeout-after-kill failure when termination cannot be confirmed.
8. Reject non-UTF-8 Git output with its typed decoding failure.
9. Assert the exact absolute `Popen` executable, argument-list/no-shell launch,
   neutral working directory, explicit repository arguments, and minimal child
   environment with no caller search path or user environment inheritance.
10. Inject hostile hooks, attributes, excludes, external diff/textconv, fsmonitor,
    and related helper configuration and prove no marker helper executes.
11. Create non-stage-zero index entries and require rejection independently of
    porcelain status.
12. Reject substitution of predecessor report/status/lineage and every contract or
    manifest downgrade, including fallback to `9b1cbcfe`, `f06e52c`, Payload A, or
    V1.
13. Reject frozen-host or Envelope-B evidence substitution, wrong digest, missing
    binding, mutable candidate-selected authority, and self-review.
14. After a complete initial `.autopilot` point observation exists, take and compare
    a complete final observation for every successful and rejecting path, including
    the Windows attribute/stream boundary where applicable; no case may create
    bytecode or otherwise mutate `.autopilot`. Rejection during the initial
    observation fails closed but makes no before/after equality claim because no
    complete initial reference exists.

The matrix is additive to the existing ambient `GIT_*`, hostile `PATH`, object
alternate, dirty/staged/untracked/ignored, hidden-index, wrong-parent, path-diff,
manifest-schema, source-binding, topology, durability, ownership, no-command, and
anti-activation tests. All failures remain non-executing and fail closed.

### Cross-platform evidence boundary

Synthetic parser fixtures must exercise PE, ELF, thin Mach-O, and fat Mach-O
acceptance and rejection logic on every development host. Synthetic parsing does
not establish real process-launch behavior on another operating system. Real-host
qualification evidence is separate for Windows, Linux, and macOS and must pin the
actual native Git bytes used on that host.

A Windows symlink case skipped because the runner lacks symlink privilege is
non-affirmative; it cannot support the Windows link-rejection claim. Binding
Windows file attributes and rejecting named streams does not cure that distinct
evidence gap: a privilege-capable Windows runner must still execute the symlink
case. A missing macOS runner is likewise a blocking evidence obligation for a
macOS-host claim. Such missing platform evidence does not authorize execution, but
it need not prevent a court from qualifying the exact payload as inert,
non-executing content if the court states the platform limitations and keeps
activation deferred.

## Verification modes and result contract

The required CLI is:

```text
verify_plan.py --repo-root <repository> --overlay-dir <overlay>
  --expected-manifest-digest sha256:<external-64-hex>
  --git-executable <external-absolute-canonical-native-file>
  --expected-git-executable-sha256 sha256:<external-64-hex>
  [--authoring-check]
```

Every documented Python safe check sets
`PYTHONDONTWRITEBYTECODE=1` and invokes the interpreter with `-B`, including the
materializer, verifier, lint, and rounds processes. After each safe-check group, the
operator recursively inventories `.autopilot` with hidden entries included and
fails if any directory named `__pycache__` or file ending in `.pyc` exists. A clean
exit that leaves Python bytecode under `.autopilot` is a failed safe check.

Focused and full Python gates must also bind imports to the candidate checkout:
either place that checkout's absolute `src` first in the gate's import path with no
competing checkout, or use a checkout-owned isolated runtime. Each gate receipt must
record the resolved `hive_mind_os.__file__` origin and require it to be beneath the
candidate's `src/hive_mind_os` directory before accepting results. The full gate
remains `python -m unittest discover -s tests -v` in that pinned environment. This
closes stale user-level editable-install contamination for the recorded gate import;
it does not attest every transitive dependency or exclude concurrent environment
mutation.

`--authoring-check` exists only at exact parent `9b1cbcfe` with the six V4 paths
overlaid and uncommitted. Its result mode is
`authoring-native-executable-matrix-correction-v4-non-executing`; it must report
`committed_payload_qualification=false`, `execution_qualification=false`, and
`execution.authorized=false`.

Default mode accepts only the exact one-commit, six-path V4 child and uses result
mode `committed-native-executable-matrix-correction-v4`. A successful committed
check may report `committed_payload_qualification=true`; it must still report
`execution_qualification=false` and `execution.authorized=false`. Neither result is
activation, release, deployment, pull-request, protected-branch, or merge evidence.

For either successful mode, `autopilot_tree.schema` is
`complete-autopilot-tree-point-observation-v2`. The result reports
`observed_unchanged=true` only when a complete initial point observation and a
complete final point observation compare equal; it also reports
`concurrent_mutation_exclusion=false` and
`requires_external_read_only_custody_for_execution=true`. Those disclosures are
deliberate: finite observation equality is not concurrent-mutation exclusion, and a
failure during the initial observation has no before/after equality result.

The resulting DAG remains `manual-parent-v1`, `executable=false`, with 20 one-node
rounds and `command=null` for every round. No executable dispatch command exists.
PowerShell may prepare an inert, inspectable script only within separately granted
authority; it cannot impersonate a person, mint credentials, accept legal terms,
spend, mutate production, bypass protection, or supply missing evidence.

## External activation, ownership, and authority

An eventual activation bundle must be authenticated outside the repository and bind
the complete plan and manifest bytes; request/repository/objective/launch/branch;
all lineage; eventual V4 HEAD/tree/aggregate; external manifest and Git path/raw
digest; host-native parser policy; complete read-only Git runtime dependency bundle;
platform launch primitive; frozen 16-file host and interpreter; independent reviewer,
actor, and issuer; predecessor remand and revocation; one-run nonce and deadline;
and compare-and-swap ledger. A minimum-version policy must reject all predecessors
and legacy fallback.

The overlay's 85 writable candidate paths retain exactly one owner each. Candidate
freeze, CI, qualification, and handoff identities remain distinct. Qualification
receipts belong in an external Envelope B evidence lineage and may not dirty or
reidentify the candidate. No worker may judge or approve its own material change.

All commands in this payload are null. DAG execution, activation, release,
deployment, pull-request creation, protected-branch modification, and merge remain
deferred. The owner's continuation directive does not grant credentials, external
signing, independent review, production access, or permission to bypass protected
main.

## Migration and rollback

Migration is append-only:

1. Preserve V1 and `.autopilot/plan.json` as historical evidence.
2. Preserve Payload A, its exact result, and its disposition.
3. Preserve `f06e52c`, its report, and its ambient-Git remand.
4. Preserve `9b1cbcfe`, its exact passing implemented checks, frozen 23,865-byte
   report, POSIX-wrapper defect, incomplete-matrix dissent, and `ADAPT/REMAND`.
5. Land exactly the six changed V4 paths as one non-merge direct child of
   `9b1cbcfe`; preserve the six inherited blobs and do not predeclare the new
   commit, tree, manifest, aggregate, report, or verdict.
6. Run the complete matrix and platform-scoped qualification, then have independent
   Clerk, Curator, Advocate, and Judge identities bind the resulting bytes and
   limitations.
7. Only after external runtime, trust, lease, revocation, and protected-branch gates
   exist may a separately authorized integration expose the easy command.

Rollback is a new append-only deny-state commit or feature-gate disablement. It
retires V4 leases and nonces, preserves every receipt and dissent, and never falls
back to `9b1cbcfe`, `f06e52c`, Payload A, or V1. Do not reset, amend, squash, delete,
or rewrite evidence-bearing commits. A published pull request may be closed; a
merged change must be rolled back by a new independently reviewed revert.

## Consequences and nonclaims

V4 makes the direct-native requirement machine-checkable across the three supported
host families and turns the prior aspirational threat list into a mandatory matrix.
The added parser and subprocess tests increase maintenance cost and still do not
turn a content verifier into a trusted execution kernel.

Path and retained-handle observations detect many substitutions but cannot eliminate
a hostile swap-and-restore entirely between observation points. A compiled native
delegator can pass the format parser. Runtime dependencies remain outside the raw
Git executable digest. Strong read-only custody, dependency attestation, separate
principals, and actual Windows/Linux/macOS host evidence remain prerequisites for
execution.

`SRC-024` remains `QUARANTINE_CONTENT_UNREAD`; `SRC-025` remains unresolved. A5 is
not ready. No execution, activation, product-completion, production, release,
deployment, merge, full-autonomy, or superiority claim is made.
