# Generic Hive Mind Product DAG V3

This directory contains an independently derived, inert Standard-V2 execution
overlay for the persisted generic Hive Mind product request. It is a sealed
design artifact, not an execution authorization. It never replaces or edits
`.autopilot/plan.json`, and its 20-node plan contains no runnable commands.

Payload A is preserved at commit
`4e2b81b932e5145f24c4b52ceeee664bff91df2e`. Its exact committed focused suite
exposed a two-test authoring-fixture defect (12/14), so the current manifest uses
an append-only v2 correction contract: one exact five-path child of Payload A,
with ten embedded non-manifest bindings plus the court-authenticated manifest
covering the complete ordered 11-path payload inventory.

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
  lineage, standards, compiler, inputs, verifier, and the expected external plan
  digest.
- `verify_plan.py` verifies all manifest-declared bytes before interpreting
  authored JSON; it never imports or executes the materializer or target product
  Python. Its default mode accepts only an exact committed payload checkout and
  requires the caller to supply the manifest digest from independent evidence.
- `plan.json` is the sealed external `manual-parent-v1` plan. Its canonical
  digest is
  `sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1`.

## Safe authoring checks

These commands inspect or reproduce the inert overlay. They do not activate it:

```powershell
python docs/execution/dags/generic-hive-mind-product-v3/materialize_plan.py --check
$manifestDigest = "sha256:" + (Get-FileHash docs/execution/dags/generic-hive-mind-product-v3/manifest.json -Algorithm SHA256).Hash.ToLowerInvariant()
python docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py --authoring-check --expected-manifest-digest $manifestDigest
python .autopilot/bin/dag_standard.py dag-lint --strict --plan docs/execution/dags/generic-hive-mind-product-v3/plan.json --expected-plan-digest sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1
python .autopilot/bin/dag_standard.py dag-rounds --plan docs/execution/dags/generic-hive-mind-product-v3/plan.json --expected-plan-digest sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1
```

The rounds result must report exactly 20 `manual-parent-v1` rounds with one node
per round and every `command` value null. `--authoring-check` is explicitly
non-executing and never qualifies a release; it is valid only in a fixture at
Payload A with the current manifest-bound correction overlaid but uncommitted.
After the five-path correction is one exact non-merge direct child commit of Payload A, omit that
flag and pass the manifest digest pinned by the independent court/Envelope B:

```powershell
python docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py --expected-manifest-digest <court-pinned-sha256>
```

Committed mode rejects a missing caller digest, the precommit authoring state,
an extra or wrong-parent commit, any changed path outside the exact five-path
correction, any mismatch in the complete 11-path payload inventory, and dirty,
staged, or unapproved untracked/ignored checkout state. The sole explicit
exception is `.hive-mind/autopilot-request.json`.
It disables Git replace objects, verifies both frozen commit objects, compares
all worktree bytes with regular-file `HEAD` blobs, and rejects hidden
skip-worktree/assume-unchanged flags on every tracked path or payload mode
substitutions. A passing committed check
means `committed_payload_qualification=true`; execution qualification and
authorization remain false.

## External activation boundary

Execution remains deferred until a host outside the candidate repository
provides all of the following as one authenticated, short-lived bundle:

1. Complete plan bytes plus manifest and expected-plan digests.
2. Reviewer, actor, and issuer identities with independent evidence.
3. Exact request, repository, objective, target, HEAD, tree, compiler, and
   Standard-V2 bindings.
4. A pristine cache-free extraction of the pinned 16-file host, its interpreter,
   predecessor and new trust receipts, and a distinct signing principal or an
   enforced outside-repository deny sandbox.
5. A one-run nonce, deadline, and compare-and-swap ledger that rejects replay,
   collision, repeat-resume mismatch, and concurrent losers.
6. A signed minimum-version and revocation policy that requires correction
   contract v2 and rejects the Payload A manifest, predecessor activation, and
   every V1 fallback.

Qualification and handoff evidence belongs in the separate external Envelope B
evidence worktree/branch. It must not dirty or reidentify the frozen candidate.
Credentials, legal consent, spending, production, protected-branch changes,
missing evidence, or ambiguous authority remain typed blockers.

SRC-024 remains quarantined with content unread. SRC-025 remains unresolved.
A5 is not ready, and this overlay makes no full-autonomy, production, release,
or superiority claim.
