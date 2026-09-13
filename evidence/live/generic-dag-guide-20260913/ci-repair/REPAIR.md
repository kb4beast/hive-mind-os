# PR 179 fixture clone transport repair

Builder: `/root/generic_guide_builder`. Delegated repair only, in
`C:\h\node-guide1` at pre-repair commit
`89925ecafc4ea4233ec921a26a6839bc2ca17f0a`. No Git commits or pushes performed by
this builder. The original documentation edits are already committed by root.

## Failure and root cause

CI run `34774982609`, job `103771336682` (Linux Python 3.14) ran 1,772 tests in
303.831 seconds with one failure and 30 skips. The failure was
`test_authenticated_attributes_defeat_system_and_global_autocrlf`, before any
authenticated-byte assertion, at the fixture clone return-code assertion:

> fatal: failed to copy file to '/tmp/tmpj4iue9ac/autocrlf-true-checkout/.git/objects/info/commit-graphs/commit-graph-chain.lock': No such file or directory

The complete downloaded job log is preserved here as
`pr179-linux314-failure-api.log`, SHA-256
`b9be759dbe9ee4ea57711e20b70e507fe4ba23a0490f8d5ea83f07fb4d3e5c55`.
Git was 2.55.0 on the failed job. The observed failure is consistent with source
commit-graph maintenance renaming/removing a transient file while Git's local
clone optimization copies the object directory. `--no-hardlinks` changes that
optimization from linking to copying; it does not select the object transport.
The log does not identify the particular background process that removed it.

## Correction

Only `tests/test_generic_dag_v3_overlay.py` changes. All six filesystem fixture
clone calls in that module now include `--no-local`, retaining `--no-hardlinks`.
They obtain objects through Git's transport instead of copying mutable source
metadata. This covers the failed clone, its second autocrlf fixture, shared
authoring/committed fixture creation, and the two further adversarial clones
with the same exposure. No policy, maintenance configuration, CI gate, exception
tolerance, retries, runtime implementation, or source evidence changes.

The failing test gains a source-only marker at
`.git/objects/info/source-maintenance-probe.lock`, an arbitrary name not used by
Git's maintenance locking. After the actual hostile-autocrlf clone, it asserts
that the marker remains unchanged in the source and is absent from the clone.
All existing system/global autocrlf and exact raw-byte/attribute assertions
remain. This exercises the corrected boundary inside the original test rather
than substituting a mocked successful clone.

## Meaningful validation

`transport_probe.py` and `TRANSPORT-VALIDATION.json` retain executable controls:

- Before-fix `clone --no-hardlinks` copies the source-only marker.
- Corrected `clone --no-local --no-hardlinks` excludes it.
- Both clones retain exactly the source HEAD, tree, and payload bytes.
- Three corrected clones run concurrently with six actual
  `git commit-graph write --reachable --split` commands. All commands succeed;
  all clones retain the exact HEAD/tree/payload and omit the private marker.
  Fifteen clone/write command intervals overlap. This is a concurrent exercise,
  not a claim to reproduce the exact failed Linux timing.
- `git diff --check` passes. Root owns subsequent focused affected V3 tests,
  independent review, complete gate, and CI qualification. They are not claimed
  passed by this builder evidence.

## Architecture, compatibility, rollback

This is a test-fixture transport repair, with no product architecture or data
migration. Hostile system/global configuration is still applied to the fresh
checkout; authenticated source paths and Git objects are still compared byte for
byte. Transport may cost more than a local copy, but does not inherit private
source commit-graph/lock files. Missing objects or clone failures still fail
immediately. Normal Git maintenance remains enabled.

Rollback is an ordinary revert of this test-only repair, restoring the prior
clone mechanism and its known race; retain the failed CI and probe evidence.
No release, promotion, or node-completion authority follows from this repair.
