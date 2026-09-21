# ADR-093: Per-child credential and config boundary for Git processes

## Status

Adapted code preparation for the narrow H2 prerequisite credential boundary. It is a
Builder candidate, not a grant, a credential, a delivery, an H2 admission, an isolation
qualification or a production claim. The Builder has read/edit tools only and has run
nothing. Root's execution of the first candidate, and the Curator's probe run, are
recorded below as reported to the Builder. **The repair described under "Curator remand
(round 1)" has not been executed by anyone yet.** The checks in "Required checks" must
be run by the parent, and a separately identified Curator and Judge must reproduce and
rule on the final bytes.

Branch `codex/git-child-credentials-20260921`, base `8a9dda3`. The frozen review commit
`1373d13` differs from the base only in unrelated worker-test cleanup.

## Decision

Deliver a Git credential, and the isolated Git config, to a child process only through
a private, one-use, non-serializable *trusted child context*. Nothing is written to the
parent `os.environ` on these paths, and redaction happens before any output byte is
hashed or persisted.

1. **Context object.** `sandbox._TrustedChildContext` has `__slots__`, no dict, a redacted
   `repr`/`str`, and refuses `copy`, `deepcopy` and `pickle`. It carries the child
   environment overrides, the names the child must not inherit (`drop`), the byte forms of
   any secret, and the canonical credential-free remote where one applies. Its use state
   (`_used`, guarded by its own lock) lives on the object, never on the runner or a
   global. It is constructed only by `git_adapter._git_child_context`, and it is never
   placed in an intent, a `SandboxSpec`, `fixed_environment` or a receipt.
2. **Binding.** `SandboxRunner.run(intent, *, _trusted=None)` calls `_authorize_trusted`
   after the existing checks and before any spawn. It denies unless the context is bound
   to:
   - the *runner*: a weak reference to the exact runner object plus its
     `runner_identity` (two runners with the same identity string are still distinct);
   - the *executable*: the path as resolved by `shutil.which` and `Path.resolve()`, the
     same resolution `run()` applies;
   - the exact requested `argv[1:]`;
   - the *remote*, where the context has one: the bound remote must appear in
     `argv[1:]`, and any other `scheme://` argument is refused.

   A reused context is refused (`_consume()` is the last check). Every override name must
   already be in the runner's `env_allowlist`, so the receipt's `name-allowlist-only`
   statement stays true. Denials use fixed reasons and never include a value. The URL
   policy lives only in `git_adapter._github_remote`, which validates the remote before
   the context is built. `sandbox.py` only checks structure (an `https://` prefix, no
   userinfo, no whitespace) and equality, so it duplicates no host, port or path policy
   and imports nothing from the Git adapter. That avoids a circular import.
3. **Child environment.** `_spawn(argv, *, _trusted=None)` builds a local mapping, in this
   order:
   - allowlisted parent values, excluding the context's drop names
     (`_GIT_CREDENTIAL_ENV`);
   - the spec's nonsecret `fixed_environment`;
   - the context overrides.

   Dropped ambient values are never re-added. On Windows, names compare case-insensitively.
   The mapping goes straight to `Popen`. Name and value validation is the single shared
   rule `_check_environment_entries`, used by `SandboxSpec` (same error text) and by the
   context.
4. **One funnel.** `GitWorkspace._execute` builds the context for every Git-argv invocation:
   the staging clone, every non-credential `_run_git` and every credentialed `_run_git`.
   It carries the isolated-config values only for names the runner allowlists, as before.
   Only credentialed calls carry the header overrides (including the Windows Schannel
   options) and the redaction forms. `run_tests` and other non-Git commands use no context
   and keep the legacy path. `_git_dates` and `_scrubbed_git_environment` are unchanged.
5. **Removed.** `_git_http_credentials` (the parent-mutating helper) and
   `_isolated_git_config` (also a parent-mutating helper, no longer reachable) are deleted.
   No callable global-mutation helper for credentials remains.
6. **Compatibility.** With no context, `_spawn(argv)` is called exactly as before, so an
   old-signature subclass (`tests/test_sandbox.py`, `FailingRunner`) works unchanged. With
   a context the extra keyword is passed, so an override that cannot implement it fails
   closed with `TypeError` before any spawn. An unresolvable executable binds to `None`
   and is denied by the existing allowlist check first, so its error type is unchanged.
7. **Redaction before persistence.** After the readers join and before `_persist`, each
   stream is sanitized once over the whole joined bytes. That covers a secret split across
   pipe reads. Forms: the raw token, `x-access-token:<token>`, the base64 userinfo,
   `Basic <base64>` and the full `Authorization: Basic <base64>` line. They are replaced by
   `[REDACTED]` in a single leftmost-longest pass. A credentialed stream that was truncated
   by the output cap, or that ended in a timeout, may end inside a secret, so a fixed
   marker replaces it. An empty stream stays empty, and a non-credentialed context never
   redacts or replaces anything.
8. **Truth of resources and receipts.**
   - The cap and the `truncated` flag are decided on raw bytes by the unchanged
     `_read_capped`.
   - Each stream's `bytes` and `digest` describe the stored (sanitized) artifact.
   - `tool_intent_digest`, `spec_digest`, `sandbox_spec_digest`, the receipt schema, usage
     counters, timeout and process-tree behavior, and the Windows Job Object are unchanged.
   - `_run_git` reads stdout only from the stored artifact. Its exception text uses the
     stored stderr and no longer needs a substitution loop.

## How source claims map to independent ADAPT, code and acceptance

Sources are in the task root
`C:\Users\beesp\AppData\Local\HiveMindOS\production-closeout-20260920`. SHA256 values are
as supplied by the parent and were not recomputed here.

| Source claim | Disposition | Code | Acceptance test |
|---|---|---|---|
| Options: per-child environment preferred; dedicated process deferred (`h2-git-credential-boundary-options.md`) | ADAPT per-child; DEFER process | `sandbox.py` context, `_child_environment`; `git_adapter._git_child_context` | The whole suite below |
| Judge (`…-judge.md`, `29cd77c2…515a`) 1: private non-serializable one-use context bound to runner, executable and argv | ADAPT | `_TrustedChildContext`, `_authorize_trusted` | `test_trusted_context_denials_are_pre_spawn_and_leak_nothing`, `test_trusted_context_is_private_redacted_and_not_copyable_or_serializable`, `test_adapter_built_context_is_bound_to_runner_argv_executable_remote_and_one_use` |
| Judge 2: absent context calls `_spawn(argv)` as before; a context fails closed | ADAPT | `run`, `_spawn` | `test_old_signature_spawn_override_serves_only_context_free_calls`, `test_old_signature_spawn_subclass_serves_context_free_paths_and_fails_closed`, existing `test_subprocess_creation_error_is_a_receipted_denial` |
| Judge 3: complete child environment, reuse the existing validation | ADAPT | `_child_environment`, `_check_environment_entries` | `test_trusted_environment_is_child_only_and_ordered_drop_fixed_override`, `test_credentialed_child_receives_exactly_the_supplied_header` |
| Judge 4: remove the parent-mutating helper; credentialed `_run_git` does not touch `os.environ` | ADAPT | helpers deleted | `test_parent_mutating_helpers_are_gone_and_git_runner_calls_are_confined`, the before/during/after probes |
| Judge 5: redact before persistence, marker on a truncated credentialed stream | ADAPT (timeout extended, see below) | `_sanitize` in `run` | `test_credentialed_streams_are_redacted_before_persistence`, `test_secret_split_across_pipe_reads_is_redacted`, `test_truncated_credentialed_streams_store_a_fixed_marker_with_raw_truth`, `test_timed_out_credentialed_streams_store_a_fixed_marker`, `test_echoed_credential_forms_never_reach_artifacts_receipts_events_or_errors` |
| Judge 6: digests and schema unchanged | ADAPT | no schema, spec-field or digest change | `test_trusted_context_does_not_change_intent_spec_or_receipt_digests`, `test_public_spec_intent_and_receipt_digests_do_not_depend_on_the_credential`, the existing `env_allowlist` assertions |
| Judge 7: raw resource truth | ADAPT | `_read_capped` unchanged; usage counted as before | the cap tests and usage assertions above |
| Judge 8: sentinel probe, concurrency, echo, exceptions, bypass, legacy | ADAPT | see tests | `test_trusted_secret_is_absent_from_parent_and_unrelated_children_during_popen`, `test_parent_stays_clean_while_a_credentialed_popen_is_blocked`, `test_concurrent_trusted_children_each_receive_only_their_own_environment` |
| Clarification point 1 (`…-clarification-judge.md`, `f4029f46…f5`, controlling): the canonical credential-free URL stays in argv; no token, userinfo, header or encoded form there | ADAPT | `_github_remote` unchanged; context binds the exact URL | `test_context_mismatch_and_bad_credentials_are_denied_before_spawn`, `test_public_spec_intent_and_receipt_digests_do_not_depend_on_the_credential` (argv equals the canonical URL and no receipt byte holds a form) |
| Clarification point 2: ambient `GIT_CONFIG_*` reaches every non-credential Git child | ADAPT | drop set applied on every Git-argv context, including the clone | `test_ambient_config_injection_is_dropped_for_clone_read_and_credentialed_children`, `test_ambient_injection_does_not_reach_real_git_reads` |
| Clarification seam 2–4, 7: dates, `SYSTEMROOT`, isolated config and allowlist preserved; no secret field on `SandboxSpec` | ADAPT | `_git_dates`, `_scrubbed_git_environment`, `env_allowlist` untouched | `test_legacy_git_dates_still_reach_only_the_commit_child`, existing allowlist test |
| Clarification seam 6: direct runner callers are a stated residual, with a test that fails on a new in-tree caller | ADAPT | none (a contract statement) | the static assertions in `test_parent_mutating_helpers_are_gone_and_git_runner_calls_are_confined` |

## Curator remand (round 1): findings, repair and acceptance

**Reported results for candidate v1** (as given to the Builder, not reproduced by it):
root ran the 86 focused tests (63 passed, 1 platform skip) and Ruff passed. The
independent Curator sealed the candidate source files, ran 29 synthetic probes (23 passed, 6
failed) and released the seal for repair. The passing probes include parent isolation
during a blocked `Popen`, concurrent secrets, output redaction with caps and timeouts,
actual local-Git ambient injection, one-use bindings and the legacy tests; none of those
paths was changed by this repair. The Curator's harness, results, race detail and the
candidate-v1 snapshot stay outside the checkout under
`C:\Users\beesp\AppData\Local\HiveMindOS\production-closeout-20260920\h2-credential-curator`
(`probes.py`, `run-v1\results.json`, `run-v1\receipt-index-race-detail.json`, `PLAN.md`,
`candidate-v1\`) and were not modified.

| # | Failed probe(s) | Cause | Repair |
|---|---|---|---|
| 1 | `authenticated-missing-context` | `_execute(token=…, remote=…)` with no `git_config` skipped the context and reached `_spawn` context-free | `_execute` refuses, before any intent is built or allowance is used: a supplied `token` or `remote` without `git_config` (`GitOperationFailed`), and any argv whose executable resolves to Git without `git_config` (`GitPolicyDenied`, via `_is_git_command`, the test `run_tests` already applied). The decision derives from the argv and the supplied values, not from a flag, and no secret or context is placed in the intent or environment. `run_tests` and other non-Git commands stay context-free |
| 2 | `canonical-remote-host`, `-query`, `-path`, `-port` | `_git_child_context` bound whatever remote it was handed | `_require_canonical_remote` runs `_github_remote` on the remote and requires its output to equal the input. It is called where a context is created (`_git_child_context`) and again by `_git_credential_environment`, so no path can bind a non-canonical host, port, query, fragment, userinfo, path or spelling. A credentialed context is always checked against the default GitHub host, so the clone's `allowed_hosts` scope is not widened to credentials. `sandbox.py` is unchanged in this respect and imports nothing from the Git adapter. The canonical URL remains in `argv` and public data |
| 3 | `same-runner-receipt-index-race` | `_append_receipt` read the shared `runner.last_reference`, so invocation A's row could name B's receipt | `sandbox._canonical_receipt(receipt)` returns the canonical bytes and content address (the rule `_persist` already used; `_persist` now calls it, unchanged in effect). `_append_receipt(records, runner, receipt)` keeps its signature, derives the reference from the invocation's own returned receipt, and indexes only if the retained bytes at that address equal them exactly. A missing file is refused as unpublished, differing bytes as a mismatch. No lock or per-call shared state was added, and `last_reference` remains, unread by the Git index, for legacy callers |

Acceptance for the repair (all unrun; the Curator's frozen probes are the independent
check and must be rerun unchanged):
- `test_credential_remote_or_git_argv_without_the_context_is_refused_before_intent` and
  `test_every_workspace_git_invocation_carries_the_isolated_context` (remand 1);
- `test_non_canonical_remotes_are_denied_before_any_spawn` (host, query, path, port,
  fragment, scheme, userinfo, missing suffix and host case, through `_execute` with and
  without a credential, `_git_child_context` and `_git_credential_environment`, with no
  `Popen`, no counter change and no persisted form) and
  `test_canonical_remote_binding_keeps_the_accepted_host_scope` (remand 2);
- `test_same_runner_local_git_receipts_index_their_own_invocation`,
  `test_same_runner_credentialed_receipts_index_their_own_invocation`,
  `test_receipt_index_never_reads_the_shared_reference_and_checks_retained_bytes` and
  `test_returned_receipt_derives_the_exact_published_reference` (remand 3). The race tests
  park invocation A after its receipt exists, let B finish, and then check that each row
  matches its retained bytes, digest and metadata. They also check that the shared
  reference had really moved to B, so the race is real and the check does not only compare
  distinct token strings.
- All earlier tests, thresholds and assertions are kept.

No receipt field, schema, spec field, digest, allowlist, timeout or process-tree behavior
changed, and no authority or grant was widened.

## Curator remand (round 2): concurrent artifact publication

**Reported results for candidate remand1** (as given to the Builder, not reproduced by
it): root ran 94 focused tests (68.155 s; all passed, one platform skip) and Ruff passed.
The Curator's unchanged 29-probe harness now passes all six original failures and
everything from remand 1, and fails one new probe (28 of 29). Evidence, retained outside
the checkout and not modified, is in
`C:\Users\beesp\AppData\Local\HiveMindOS\production-closeout-20260920\h2-credential-curator`:
`REVIEW-remand1.md` (SHA256 `972d7d21…6b7`), `MANIFEST-remand1.json`,
`run-remand1\results.json`, `candidate-remand1\`, `persistence-race-v1.py`,
`persistence-race-v1.log` and `persistence-race-v1\results.json`.

**Finding.** `SandboxRunner._atomic_write` checked that the destination was absent and
then called `os.replace`. Two concurrent invocations (a credentialed child and
`run_tests`) both persist the identical empty stderr artifact, whose name is its content
address. When one writer published it and a legitimate reader had the file open, the
other writer's `os.replace` raised Windows `PermissionError` (`WinError 5`) even though the
destination already held the correct bytes, and the operation's receipt was never
persisted. Content was never corrupted and no secret was involved. The routine predates
this work, but overlapping credentialed and unrelated calls now reach it.

**Repair (`sandbox.py`, `_atomic_write` only).**
- The bytes are written, flushed and fsynced to an owned temporary file in the
  destination directory. It is closed, then hard-linked to the destination with
  `os.link`, an atomic create-if-absent. The destination therefore never exists
  partially and is never overwritten.
- `FileExistsError` means another writer published first. The existing file is adopted
  only if its complete bytes equal the content; anything else, including a partial file,
  raises the unchanged `content-addressed artifact collision` error and leaves the
  original untouched. Adoption never touches the existing file, so an open reader cannot
  fail a writer.
- Only the temporary file this call created is unlinked, best effort, in `finally`. There
  is no recursive cleanup, retry loop or backoff. A cleanup failure cannot mask the
  primary outcome. After a completed publication a leftover temporary name is a second
  link to the same complete bytes.
- A filesystem or host without hard links (`NotImplementedError`, `EPERM`, `ENOSYS`,
  `ENOTSUP`, `EOPNOTSUPP`, `EXDEV`, `EMLINK`, or Windows error 1 or 50) fails with a typed
  `SandboxError` ("requires hard-link support"). Other `OSError`s, such as a full disk,
  propagate as themselves.
- The existing absent fast path is kept. It is now only an optimization: the gap between
  the check and the publication is harmless because the publication cannot overwrite.
- No digest, receipt format or schema changed. Raw output limits, truncation flags and
  redaction happen before this call and are untouched. Receipts and artifacts share the
  routine and the semantics. No global lock and no serialization of Git or credential
  contexts was added.

**Tradeoffs and scope.**
- Alternatives considered: `os.replace` guarded by a retry loop, which is unbounded or
  arbitrary and still replaces; and exclusive-create of the destination plus in-place
  writes, which exposes a partial destination. Neither was adopted.
- A hard-link failure is deliberately not backed by a weaker fallback, so a filesystem
  such as FAT or some network shares now fails typed where it used to work. That is a
  narrowing of supported storage, chosen over a weakened guarantee.
- On Windows a reader that opens the winner's file (which shares an inode with the
  winner's temporary name) can block that winner's temporary removal. The leftover is
  harmless (same complete bytes) and the publication still succeeds.
- Not changed: the delivery-export writer in `git_adapter.py` (`_atomic_write`, also
  `os.replace`; a single-writer path to a fresh staging directory), and any other storage
  engine. No architecturally material conflict was found.

**Probe baseline.** `persistence-race-v1.py` patches `os.replace` to place its barrier.
It is retained unchanged as the baseline that exposed the defect. Against these bytes
`_atomic_write` no longer calls `os.replace`, so that probe cannot reach its barrier and
must not be read as a pass or a regression. The semantic barrier for the new primitive
that the Builder added is in the tests below, and a Curator-authored replacement that
wraps `os.link` is still needed for independent qualification.

**Acceptance (all unrun).** In `tests/test_sandbox.py`, using the real filesystem and a
barrier that wraps the real `os.link` and passes through, so a change of primitive fails
the test instead of passing vacuously:
- `test_concurrent_same_bytes_publication_adopts_the_winner_with_a_held_reader`: A parks
  after finding the destination absent, B publishes, a reader holds the winner open, A
  resumes. A succeeds, the file identity is unchanged, and no temporary file remains.
- `test_concurrent_conflicting_bytes_fail_closed_without_overwrite` and
  `test_existing_different_or_partial_bytes_are_never_accepted_or_overwritten`.
- `test_publication_cleans_only_its_owned_temporary_file`: fsync failure, a link data
  error, a cleanup failure that does not mask the error, a sibling file that survives, and
  a publication that survives a cleanup failure.
- `test_unsupported_hard_links_fail_with_a_typed_error_and_no_weaker_fallback`.
- `test_many_concurrent_writers_and_readers_publish_identical_bytes`.
- `test_concurrent_runs_with_identical_artifacts_both_persist_their_receipts`: the two-run
  scenario the Curator observed, through `runner.run`, with a held reader.

Cross-platform requirement: these must pass on both Windows and Linux CI. The tests use
no Windows-only API. The reader-blocking behavior they guard is Windows-specific, and the
Linux runs check the same semantics.

## Builder interpretations the Judge should confirm

- **Timeout is treated like truncation.** A killed child can stop mid-write, so both
  streams of a credentialed, timed-out run store the fixed marker. This is stricter than
  the text requiring it for truncation only, and it costs the timeout's partial stderr
  diagnostics. Relaxing it would need a proof that a partial prefix cannot be stored.
- **`_isolated_git_config` is also deleted.** The instruction was to remove the
  credential helper and leave no parent isolated-config mutation on the context Git
  paths. Keeping the second helper would have left an unreachable but callable global
  mutator.
- **Git children no longer take `_GIT_ENV_LOCK`.** The lock still serializes `_git_dates`
  and the `run_tests` scrub. A read-only Git child that runs while another thread's
  commit holds its date window may inherit those nonsecret dates.
- **Override names must be allowlisted.** The isolated-config values are filtered to the
  runner's allowlist, which matches the earlier behavior for a runner that lacks them. A
  credential override that the runner does not allowlist is denied before spawn.
- **Missing-executable binding** is left to the existing allowlist denial (see 6 above).

## Threat model

| Threat | Control | Residual |
|---|---|---|
| Any child, or a foreign runner, inherits a header the parent held in `os.environ` | The header is never in the parent environment, and drop names are excluded from inheritance | none for the context paths |
| A concurrent `Popen` in another thread sees the credential | No global state to observe (tested during a blocked `Popen`) | none |
| Ambient `GIT_CONFIG_*` (`http.extraHeader`, `credential.helper`, `core.sshCommand`) reaches a Git child | Drop, then fixed, then explicit overrides, on every Git-argv invocation | A trusted host that drives a Git-allowlisted runner directly, without `_execute`, still inherits allowlisted ambient names. This is a stated contract residual, guarded by the static test |
| A credential echo (for example `GIT_CURL_VERBOSE`) is hashed and stored before redaction | Redaction happens after the readers join and before `_persist`; truncated or timed-out credentialed streams become a marker | See the next two rows |
| A child that transforms the secret (other base64 alignments, percent-encoding, splitting, reversing, hashing) | Not solved | Explicit residual. Redaction covers only the five supported byte forms |
| A malicious `git` binary or a PATH substitution | Binding to the resolved path narrows this and does not prove identity | Receipts still say `executable_identity: name-allowlist-only` |
| Code inside the host process | Not claimed | Trusted Python callers remain trusted. The context is a seam between trusted callers, not isolation. A secret placed in public `fixed_environment` violates the trusted-API contract |
| Windows revocation checking | The pre-existing `http.schannelCheckRevoke=false` is preserved and not extended | Unchanged weakening |
| A very short token that is a substring of the marker | Not addressed | Real credentials are long. The marker and the token cannot both be safe for a degenerate token |

## Rollback

Reverting these bytes returns to the base, whose credentialed path holds the header in the
parent environment and persists unredacted output. **That path must not be restored or
used.** Rolling back therefore means disabling credentialed delivery: no credential is
supplied to `push_branch`, and no H2 use proceeds. Non-credential Git behavior returns to
the base with no data migration. This change writes no state, schema or receipt field, so
there is nothing else to unwind.

## Ownership

- Builder: this change and its tests.
- Curator (independent): reproduces every claim above on the final bytes, and enumerates
  further `subprocess` use.
- Judge (independent): rules on the interpretations listed above and on admission.
- Steward: the runtime residuals (direct-runner callers, Windows revocation).

## Roles and lifecycle stages

| Role | Evidence now | Pending |
|---|---|---|
| Orchestrator | Scope and the controlling documents named above | Scheduling of the parent's execution and review |
| Explorer | The options file and the code reading behind the Judge documents | Enumeration of every non-Git `subprocess` use, which the Judge did not do |
| Architect | This ADR and the options record | Judge confirmation of the interpretations |
| Builder | The source and test changes | Running them, which this Builder could not do |
| Curator | None | Independent reproduction of the final bytes |
| Integrator | None. `push_executor`, the schema and H1 are untouched | The H1 gate and the grant checks stay where they are (`push_executor._require_grant_remote`) |
| Steward | None | Long-run monitoring of the residuals |
| Optimizer | None | No metric or superiority claim is made |

| Stage | Status |
|---|---|
| Discover | Known (Judge and options documents) |
| Design | Known (this ADR) |
| Build | Known, unrun |
| Validate | Pending (independent, executed) |
| Grow | Pending, out of scope |
| Maintain | Pending |
| Integrate | Pending (full H2 needs the H1 gate) |

## Required checks (all unrun by the Builder)

1. `python -m unittest tests.test_sandbox tests.test_git_adapter -v`, then the CI gate
   `python -m unittest discover -s tests -v`. Include Windows, since several probes take
   the `os.name == "nt"` branches (the Schannel options and case-insensitive names), and a
   POSIX host if one is available.
2. A real Git of 2.31 or later for `test_ambient_injection_does_not_reach_real_git_reads`,
   which would pass vacuously on an older Git.
3. Confirm the changed-file set is exactly `src/hive_mind_os/git_adapter.py`,
   `src/hive_mind_os/sandbox.py`, `tests/test_git_adapter.py`, `tests/test_sandbox.py` and
   this file, and that no schema, spec, `push_executor` or H1 file changed.
4. Lint and type checks if the repository configures them. Two points in particular:
   `_TrustedChildContext` refers to `SandboxRunner`, which is defined later in
   `sandbox.py` (annotation only, under `from __future__ import annotations`), and
   `git_adapter.py` imports the private `_environment_key` and `_TrustedChildContext`.
5. Timing-sensitive tests (the timeout tests use a 4 s limit and a 60 s child): confirm they
   are stable, and that no child survives a failed run.
6. Recompute the SHA256 values of the four task-root documents and of the final source
   files before any qualification claim.
7. After the repair: rerun the focused tests again, then have the Curator rerun its
   frozen, unchanged `probes.py` against a new seal. The six failed probes should now
   pass, the 23 that passed must not regress, and the new tests above must pass.
   `probes.py` replaces `GitWorkspace._append_receipt` with a three-argument function,
   so that signature was kept; if a run shows otherwise, treat it as a regression.
9. After the publication repair: run `tests.test_sandbox` and `tests.test_git_adapter` on
   Windows and on Linux, then have the Curator rerun its 29 probes, replacing the
   `os.replace` persistence probe with an `os.link` barrier of its own. The earlier
   remand-1 results must not regress.
8. Run Pyright (which was in progress for candidate v1) on the changed files. Two
   points in particular: `_execute` now declares `context: _TrustedChildContext | None`,
   and `git_adapter.py` imports the private `_canonical_receipt`.

## Limitations unchanged by the repair

- **Direct-runner callers.** A trusted in-tree caller that drives a Git-allowlisted runner
  directly, without `_execute`, still inherits allowlisted ambient names. `_execute` now
  refuses a Git argv it is asked to run without the context, but it cannot stop a caller
  that never calls it; the static test and review remain the guard.
- **Other users of `last_reference`.** `pit_oracle.py` and `verify.py` still read the
  runner's shared reference. They are outside this scope and the remand, and were not
  changed. Whether they can race is not assessed here.
- **Git-argv detection is by executable name.** `_is_git_command` uses the same
  name-based check `run_tests` already used, and receipts still say
  `executable_identity: name-allowlist-only`. A Git binary under another name is not
  detected by it.
- **Residuals in the threat table stand:** a secret-transforming or malicious Git,
  in-process code, the Windows revocation setting and degenerate tokens.
- **Timeout marker** and the other Builder interpretations above remain open for the
  Judge.

## Explicit non-claims

No production readiness, H2 admission, network or GitHub use, credential, grant, authority
or policy change is claimed or made. Historical source and evidence files were not
touched. Trusted-Git assumptions and the `name-allowlist-only` receipt statement stand.

## Root execution and final independent disposition, 2026-09-21

This dated entry supersedes the stale unrun status above without deleting its
history. The first focused result was 86 tests, OK with one skip; the earlier
parenthetical "63 passed" is incorrect. Remand 1 ran 94 tests, OK with one skip,
but the independent 29-control replay found the new Windows publication race.
Remand 2 ran 101 tests in 75.808 seconds, OK with one platform skip. Changed-file
Ruff and Pyright pass. Full local and remote platform CI remain pending.

Independent Curator `/root/readiness_cross_examiner` replayed the original 29
credential controls unchanged and added 11 real-file publication controls.
All pass. They exercise held-open readers, exact-byte adoption, conflicting and
partial-byte rejection, ordinary cleanup, preserved siblings, unsupported links,
and an injected cleanup failure with a retained complete second link. Review:
`c480e7e1aaff9ff64c5f338a3a320c8baeeb7c866345e095116a2378d06b87fc`;
manifest: `a140bfceead4b5e7fd16d2dcc56fbea85521ebefa9b925ae0ebf0dbb1f3a47c0`.
The original probe failures remain retained. The subsequent H1-only propagation
to `7673d669` changes ADR-091 and the worker fixture test, with all H2 runtime and
test bytes unchanged; its explicit rebind receipt is
`bd9bcb6078cc079f1c4c576573b39d77cd7cf2c975cf2be0b1464fbcae0eaeb9`.

Separate Claude Judge session `6e49225a-dec3-4d3f-8d30-b33e15d61757` issued
ADAPT for narrow reversible code delivery, with no implementation blocker.
Its read-only review ran no tests and explicitly distinguished inspected code
from supplied execution claims. Review digest:
`c1662acc62f0dec685934a7cb0c8126dc7cf6f26958f24ca65c5c0e79da7398e`.
It accepts the timeout marker, trusted private context, canonical URL in argv,
unchanged Windows revocation scope and preserved legacy reference consumers
within the stated boundaries. Runtime/test and this updated ADR are rebound in
the root's separate final-delivery manifest; the Curator did not reproduce this
later documentation appendix.

### Storage support and admission precondition

The supported qualification scope is a trusted local NTFS/POSIX evidence root
with working hard links. This affects every SandboxRunner artifact and receipt,
not only Git. FAT/exFAT and unsupported network/FUSE configurations are not
admitted; failures are typed, with no weaker publication fallback. Exact-existing
bytes may be adopted, but that is not a capability qualification.

Future H2 composition must verify hard-link publication on the actual trusted
evidence root before its first credentialed child. Otherwise unsupported storage
can fail after a child has already caused a side effect. This is a required
preflight obligation, not a grant supplied by this PR. File fsync does not supply
a crash or power-loss directory durability claim or an atomic artifact/receipt
transaction. Cleanup is best effort; a failed unlink may retain an owned second
link to the complete bytes, which must not be treated as a new receipt.

Raw output controls govern execution limits; sanitized stored bytes/digests
describe retained artifacts. A fixed marker or redaction replacement can exceed
a very small raw-output cap without changing the raw truncation decision. The
other `last_reference` consumers and direct-runner caller residuals remain
Steward follow-ups, not silently repaired claims. Linux/POSIX and full Windows
CI, H1 qualification and real authority remain required before live H2 use.
