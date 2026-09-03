# Generic Hive Mind V3 DAG qualification - append-only correction

## Status, provenance, and bounded scope

- Integrator: /root
- Observation date: 2026-08-23
- Final report assembly observation: 2026-08-23T15:49:31Z
- Candidate commit: f06e52c43a1e2d1d53523378c0d6f5564fb984bf
- Candidate tree: 8730203c89835c4d1d9dac4be9b2086dacd2d869
- Sole and direct parent: 4e2b81b932e5145f24c4b52ceeee664bff91df2e
- Parent tree: 8c42aeaf4ed480dd3ccc353356b7fa9f3ed49157
- Branch contract: release/hive-mind-autopilot
- Qualification mode: exact-append-only-correction-v2

This packet qualifies only the exact inert committed DAG payload. It does not
activate the DAG, establish controller or signing-principal trust, authorize remote
effects, qualify later product implementation, satisfy a protected merge, or support
a full-autonomy, production, release, deployment, or superiority claim. The report is
Envelope B outside the corrected 11-path payload. A later independent court must bind
the final report bytes and digest; this report does not approve itself.

The plan-authoring base remains commit
42b4aeef17f816430a7d8a435102635afea8761a with tree
b896e16755a1d6864989757732fdc5ca9d2b5eed. The correction lineage is separately
bound to its direct Payload A parent above.

## Exact request and prerequisite lineage

- Raw request: 2,809 bytes; SHA-256
  0046dfd87f3774fec320471cd487692e3bc860d509444bd2c57c2eec9d15898d.
- Request ID:
  sha256:baa813bdcbd1b3bd459736cb65dccaf060758991a8a9b581fe8a1bf17dd65562.
- Objective digest:
  sha256:36125297e861b0fea8d1be8b81e985445957f85378dc35c6712896b7b4d93c9c.
- Repository ID:
  sha256:48eb2b11cd99bb34f430f5e1c7a39d9a32b9bbaac6a99db4736d2ac422915590.
- Task key: DAG-BUILD-48eb2b11cd99-baa813bdcbd1.
- Launch ID:
  sha256:475c6908392956991faec25293170750e17fac70a97e62f550bb6d6164eb4461.
- Request observation: commit
  44224532dc25b94a95c3184054ec81762a258259; tree
  c2e7b983e9ed430ea8e3f7013ee2d8cb02a60e33.
- Qualified prerequisite: commit
  ca43709591313c1c166a2e655b8982ccff16daf3; tree
  22639258c7a524ffda25272ccf34fede176b2663.
- Combined prerequisite Envelope B: commit
  877bf9fc9cdbef94e6fc33ff9e22fe53349db130; tree
  1ede87e53fc7fc75d29968698ba4b8dab082dd1e.

## Superseded predecessor - exact Payload A

Payload A remains append-only evidence at commit
4e2b81b932e5145f24c4b52ceeee664bff91df2e, tree
8c42aeaf4ed480dd3ccc353356b7fa9f3ed49157, with sole parent
42b4aeef17f816430a7d8a435102635afea8761a.

Its ordered line manifest is 1,380 bytes with SHA-256
2d21c77d2cd8a97047d1e676b25049750b1be1f4d647a1c7b0b362fd2692be17.
Its raw aggregate uses domain hive-mind-os/v3-payload-a-content/v1 and the
path/NUL/byte-count/NUL/raw-bytes/NUL algorithm. It is 419,724 bytes with
SHA-256 ff7a0f323aac32da18c70d6f871ddc0918225ddd47de0c15618822be84706d78.
Its manifest is 12,333 bytes with SHA-256
87914018e98effc32a067146593191a82f4a01c122f4ab0695304c0c3eb54522.

| Path | Bytes | SHA-256 | Git blob |
| --- | ---: | --- | --- |
| docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md | 12,221 | 586157b57b23b1e00999e305c7f6d8943ada3050564a2e62419c2f6409892f98 | 1d73b36aec9d1de11791e295feddce8eafc123b9 |
| docs/architecture/ADR_INDEX.md | 11,435 | d573e57748bc0a0d4b8990b87e00aa00a3f0f3c68f3bfdc93a87743747a12b9b | 21c4abf5ad579efc63fd9a6500230583f0c5972e |
| docs/execution/dags/generic-hive-mind-product-v3/README.md | 5,329 | aa981c8bb6f4da075f1230eb4642b4a6ecef99eefa95de52c72bddb831f36d41 | 8a0b32778d5c820ea6832077a44426c451806be3 |
| docs/execution/dags/generic-hive-mind-product-v3/manifest.json | 12,333 | 87914018e98effc32a067146593191a82f4a01c122f4ab0695304c0c3eb54522 | 25ea0bac5f2f9a008a1dac28cd853d72a01d8e11 |
| docs/execution/dags/generic-hive-mind-product-v3/materialize_plan.py | 25,309 | 63c2dd154fc1a6e4db9e9ca5ca7e06d57ef93f141a921ff3189fa77b4b48464c | 6b0c8b7b1a37f8680f78775afb91e1a90a12dfc3 |
| docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json | 64,381 | eef8694c935467bade1fed286ef9cce67f01e2f35f0b914105255bf8681e3cf8 | 86685b62e5853cfe2f5c96b09812aee5131f6b0e |
| docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json | 10,943 | 056b74b37da1e7292d7931b93c5975c2c589ce4b64c8bf0004ca12f5deebaf80 | 0f2b97986446337d825f1f162e59cef12044d554 |
| docs/execution/dags/generic-hive-mind-product-v3/plan.json | 170,172 | 5e03c7638b2d4865dda2b2c3a5e615ea4b2b8d37f61a3a5fdfbf29c1750827c4 | 156ca61619e3f01fbdf5fe777394412f12ba6aeb |
| docs/execution/dags/generic-hive-mind-product-v3/traceability.json | 24,865 | 4182ab1d43deaabe41b50e8c534d2f6de33d399696cb69611391858f17eaa786 | d97b730948f8194c11059306f65063a02acc9743 |
| docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py | 57,521 | b9d11b55e4549bea19cbb5139ded53e81fdde80d1cfe1c09af31f2bfed4cb02a | b04deff8697cb625b350532f9e074bae11309a6f |
| tests/test_generic_dag_v3_overlay.py | 24,447 | f89a1afc5eee86e12c4aa07efc7a1b3cb660c3e538fdb96b9adf783e3edd0e1f | a605632f09fd46a8301edc499b0701a1d4ad5aea |

The exact committed Payload A suite independently reproduced 12 of 14 tests.
The two failures were:

- test_valid_overlay_verifies_without_mutating_historical_plan; and
- test_source_substitution_is_rejected_before_materializer_execution.

Both tests sent committed HEAD through a precommit-only authoring check. The earlier
14-of-14 observation belonged only to an authoring/precommit overlay. Attribution of
that result to exact committed Payload A is REJECTED. Payload A is recommended
ADAPT/superseded, must remain preserved, and must never be reactivated.

## Exact corrected 11-path payload

Ten non-manifest file bindings are embedded in the manifest. The caller and later
court authenticate the manifest itself, completing the non-circular 11-path
inventory. All paths have regular-file mode 100644.

| Path | Bytes | SHA-256 | Git blob |
| --- | ---: | --- | --- |
| docs/architecture/ADR-069-GENERIC-HIVE-MIND-V3-EXECUTION-DAG.md | 15,001 | 4e9a9cd8b91e1ebb8b6eaf199cfcd2b4c82d2408c592f8b9d786295ce8fd3340 | 4575d2e78b1d2157f8d5e50dc8d9abc3dd6d9e21 |
| docs/architecture/ADR_INDEX.md | 11,435 | d573e57748bc0a0d4b8990b87e00aa00a3f0f3c68f3bfdc93a87743747a12b9b | 21c4abf5ad579efc63fd9a6500230583f0c5972e |
| docs/execution/dags/generic-hive-mind-product-v3/README.md | 6,450 | 0d122b9073b78b9d97a50feca04d3dc632e5a2e670481d36c1997eb6ce7ec33b | 57c17f845a86bb22fe853d70aace362794b1086d |
| docs/execution/dags/generic-hive-mind-product-v3/manifest.json | 14,404 | b3ea9cbc2766cc1fa72a41f097de491a8b0ae5b9b482c57667bd31c1393fa339 | 363065cacbae6402dbbc60eb4203dadc07e1f743 |
| docs/execution/dags/generic-hive-mind-product-v3/materialize_plan.py | 25,309 | 63c2dd154fc1a6e4db9e9ca5ca7e06d57ef93f141a921ff3189fa77b4b48464c | 6b0c8b7b1a37f8680f78775afb91e1a90a12dfc3 |
| docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json | 64,381 | eef8694c935467bade1fed286ef9cce67f01e2f35f0b914105255bf8681e3cf8 | 86685b62e5853cfe2f5c96b09812aee5131f6b0e |
| docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json | 10,943 | 056b74b37da1e7292d7931b93c5975c2c589ce4b64c8bf0004ca12f5deebaf80 | 0f2b97986446337d825f1f162e59cef12044d554 |
| docs/execution/dags/generic-hive-mind-product-v3/plan.json | 170,172 | 5e03c7638b2d4865dda2b2c3a5e615ea4b2b8d37f61a3a5fdfbf29c1750827c4 | 156ca61619e3f01fbdf5fe777394412f12ba6aeb |
| docs/execution/dags/generic-hive-mind-product-v3/traceability.json | 24,865 | 4182ab1d43deaabe41b50e8c534d2f6de33d399696cb69611391858f17eaa786 | d97b730948f8194c11059306f65063a02acc9743 |
| docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py | 63,880 | 5aa43bb7ced681d3987e8f600744f8f88f8bdf28b97fdaeeecc3ee58edbb891c | a55642c15e42090d5df4f345fc3a88aab5d1bb55 |
| tests/test_generic_dag_v3_overlay.py | 32,966 | 43520b1d91bc3720c51cd309c19820fcd12d19e7273af696310f724f7f6c0ef7 | bf605d5d6c4891455d51af6fe35666bf5aa319df |

The corrected ordered line manifest is 1,380 bytes with SHA-256
6a5f0d9fab2946b0c777d7c2ccbcc4111012c69ec28c20b5d82284b79f7da681.
The corrected raw aggregate uses domain
hive-mind-os/v3-append-only-correction-content/v2 and the same
path/NUL/byte-count/NUL/raw-bytes/NUL algorithm. It is 440,587 bytes with SHA-256
229821586021d8e2769035aeca4a4589cb7b458a9740a8b8ca82ebdfdadaee36.

Exactly five paths differ from Payload A: ADR-069, the V3 README, manifest, verifier,
and focused test. Six blobs are inherited byte-for-byte. The verifier requires every
tracked index entry to be visible and normal, each payload worktree byte sequence to
equal HEAD:path, exact commit/tree/parent objects, the exact five-path diff, and all
11 regular-file modes. It disables Git replace objects. Skip-worktree, assume-
unchanged, source substitution, worktree dirt, extra paths, and predecessor/V1
activation fail closed. The authorship contract declares execution_authority NONE.

## Stable source, seal, topology, and host bindings

- Clerk intake: 58,463 bytes; SHA-256
  dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c.
- Manifest raw SHA-256:
  b3ea9cbc2766cc1fa72a41f097de491a8b0ae5b9b482c57667bd31c1393fa339.
- Plan canonical digest:
  sha256:43121c323dd652cd05807ccc5acdec70bb4a4b81a376e00c45acd16a5fc56ce1.
- Plan raw SHA-256:
  5e03c7638b2d4865dda2b2c3a5e615ea4b2b8d37f61a3a5fdfbf29c1750827c4.
- Historical .autopilot/plan.json: 169,053 bytes; SHA-256
  85fd0c69fed4aa8cd40019bfeaccc5a686fa408ae5183060ae0320d412cea9ef;
  unchanged.
- Standard V2 blob: 2bc9c0fa3baf6fb5cc720ffdbf7528e93f4e7374.
- Frozen compiler blob: f170ac4f388d265fcaafd32437e449945dcebee3.
- Frozen-host bundle:
  sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255.

The graph has 20 nodes, 28 raw edges, 17 dependency levels, 20 one-node rounds,
89 mapped V1 rows, 27 V3-specific corners, 85 unique write paths, and seven
mandated sole-writer surfaces. Every node has a Standard-V2 contract seal and typed
durability declaration. External execution mode is manual-parent-v1. Executable
dispatch is false and every round command is null. Frozen-host activation is not
satisfied.

## Corrected postcommit validation

The reproduction workspace was
C:\Users\beesp\AppData\Local\Temp\hive-v3-v2-ccabfd12255d47fb975bc61d50533df4.
It had zero tracked, untracked, and ignored state before verification. Default
committed verification ran first and passed with:

- verified true;
- committed_payload_qualification true;
- execution_qualification false;
- execution.authorized false; and
- exact correction lineage, inventory, manifest, aggregate, topology, and
  anti-downgrade bindings.

The exact focused suite then passed 15 of 15 tests in 101.932 seconds with terminal
OK. It includes rejection of unrelated CONTRIBUTING.md skip-worktree and
assume-unchanged flags with the exact error tracked index visibility flag is not
pristine. It also exercises Git-replace, substitution, dirty, ignored, untracked,
parent, path, downgrade, and activation attacks. The historical plan remained
unchanged.

The materializer check exited 0. Strict DAG lint reported 0 errors, 0 warnings, and
0 informational findings. Round derivation returned exactly 20 rounds with no
executable dispatcher command.

Corroborating precommit reviews are separate from the postcommit evidence:

- /root/v3_v2_curator passed 15 of 15 in 141.450 seconds and recommended ADOPT for
  the inert correction and DEFER for execution.
- /root/v3_v2_cross passed 15 of 15 in 135.931 seconds, reproduced Payload A at
  12 of 14, and recommended ADOPT correction, ADAPT Payload A, and DEFER execution.

After verification and tests, the retained reproduction workspace accumulated ignored
Python cache directories throughout .autopilot, benchmarks, src, and tests. The full
gate also left 18 temporary loose-object garbage files. It is now ignored-dirty. It
is an ephemeral reproduction workspace, not a trust root, and must not be reused for
another pristine-verifier claim.

## Full repository CI truth

The prescribed gate was run exactly:

    C:\Python314\python.exe -m unittest discover -s tests -v

It ran 1,138 tests in 1,232.422 seconds and exited 1 with 5 failures, 4 errors, and
7 skips. The prescribed gate therefore FAILED and is not relabeled.

Failure inventory:

- ERROR:
  test_different_valid_requests_cannot_reuse_dag_build_identity
  raised KeyError request_id.
- FAIL:
  test_initialize_and_inspect_uninstalled_repository.
- FAIL:
  test_run_does_not_recheck_a_controller_that_appears_after_decision.
- FAIL:
  test_run_from_subdirectory_uses_initialized_git_root.
- FAIL:
  test_run_initializes_subject_and_emits_an_execution_contract.
- FAIL:
  test_run_with_installed_controller_requires_a_subject_bound_plan.
- ERROR:
  test_explorer_can_read_history_and_discover_tests_through_receipts.
- ERROR:
  test_fake_git_path_entry_is_not_invoked.
- ERROR:
  test_prediction_mutation_after_reveal_is_detected_at_grading, where Git reported
  permission denied while reading a temporary fixture repository config.

The first eight failures were independently reproduced and separated on two ambient
environment axes. Default Python imported hive_mind_os from the stale editable
installation at C:\Repos\HiveMind\hive-mind-os\src through
C:\Users\beesp\AppData\Roaming\Python\Python314\site-packages\
__editable__.hive_mind_os-0.7.0.pth instead of from candidate f06e52c. The inherited
GIT_PAGER value was cat, which the Explorer correctly rejects as Git environment
injection.

- Candidate src first plus GIT_PAGER=cat made the six autopilot cases pass and left
  only the two Explorer errors.
- Stale editable main plus GIT_PAGER removed made the two Explorer cases pass and
  retained the six autopilot failures/errors.
- Candidate src first plus GIT_PAGER removed made all eight targeted cases pass in
  4.466 seconds.
- The complete two affected modules ran 33 tests in 23.614 seconds with terminal
  OK (skipped=1); the skip was the Windows symlink-privilege case.

Those diagnostics establish that the first eight outcomes are environment
contamination, not a V3-correction defect. They do not convert the prescribed gate
to a pass. The point-in-time fixture case passed on an immediate candidate-bound
retry: 1 test in 3.512 seconds, exit 0, terminal OK. Its prescribed-run permission
error was not reproduced.

The controlled full-gate diagnostic selected candidate src through PYTHONPATH and
removed inherited GIT_PAGER, then ran the same CI command. It exited 0 after running
all 1,138 tests in 1,246.530 seconds with terminal OK (skipped=7). It reproduced none
of the 5 failures or 4 errors. This sanitized-environment result establishes a green
candidate checkout and resolves the point-in-time retry question. It is retained as
separate diagnostic evidence and does not relabel, erase, or overwrite the failed
prescribed invocation.

## Recommended court dispositions and claim boundary

The report author recommends, but does not judicially issue:

1. ADOPT f06e52c43a1e2d1d53523378c0d6f5564fb984bf only as the exact inert
   committed append-only correction.
2. ADAPT/supersede Payload A while preserving its exact commit and 12-of-14 result.
3. REJECT attribution of the precommit 14-of-14 observation to exact Payload A.
4. DEFER execution and activation.
5. DEFER release and protected merge pending the provider's eight required checks,
   code-owner and last-push approval, and conversation resolution. The controlled
   local pass does not satisfy those protected-main gates, and the failed prescribed
   invocation remains adverse evidence.

Allowed claim: exact inert committed-payload qualification, subject to the later
court's authentication of this report.

Forbidden claims include full autonomy, A5 readiness, product or production
readiness, release or deployment readiness, remote-effect authority, controller or
principal trust, protected-merge satisfaction, and superiority.

## Retained blockers, dissent, and nonclaims

1. The same Windows SID can read the authority key. Logical identity separation
   cannot establish distinct-principal trust. Activation requires a distinct signing
   principal or an enforced external deny sandbox/restricted token.
2. Activation also requires an external signed minimum-version/revocation policy, a
   fresh short capability and lease, exact interpreter binding, a pristine frozen
   host, independent external trust receipts, a one-run nonce/deadline/ledger, and
   externally authenticated Envelope B.
3. The canonical continuation launcher returned structured WAIT with publication
   withheld and zero tasks. It is not V3 authority and grants no credentials.
4. SRC-024 remains QUARANTINE_CONTENT_UNREAD; SRC-025 remains unresolved. No
   quarantined SRC-024 or SRC-025 content was retrieved.
5. The Hardened Vision Contract/runtime-reference conflict remains deferred. No full
   machine-vision compliance claim is made.
6. Capability never expands authority. The owner's durable continuation authorizes
   routine reversible work in the existing scope; it does not bypass credentials,
   spending, production, signing, policy, protected merge, or external review gates.
7. Execution remains unauthorized and unattempted. Every authored dispatcher command
   is null.

## Rollback

Disable or revert the correction only through ancestry-preserving commits while
retaining a deny state. A rollback must not reactivate Payload A or V1; predecessor
activation and legacy fallback remain prohibited. Preserve the request, Clerk intake,
Payload A, its failed 12-of-14 evidence, the correction, corrected 15-of-15 evidence,
the failed prescribed CI result, controlled diagnostics, report, dissent, and later
court append-only. Do not reset, squash, amend, or rewrite evidence-bearing commits.
