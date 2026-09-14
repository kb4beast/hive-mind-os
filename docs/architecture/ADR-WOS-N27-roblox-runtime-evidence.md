# ADR-WOS-N27: Roblox runtime evidence boundary

Status: proposed implementation contract

## Decision

The N27 adapter is a read-only qualification boundary. It never launches Studio,
uses an account, allocates an environment, or cleans one up. A production-candidate
verdict requires all of the following for one exact qualification ID:

- an admitted candidate, profile, project/scenario manifests, signed Studio binary,
  test universe, broker lease, and environment/resource lease;
- four distinct canonical verifier identities for Studio discovery, runtime
  observations, authority/lease state, and qualification result receipts;
- fresh, unexpired Studio, engine, physical-device, metric, persistence, security,
  asset, and cleanup evidence;
- exact receipt bindings to the qualification ID, candidate/profile/manifests,
  Studio receipt, environment, both leases, and the expected verifier identity;
- a complete engine/device scenario matrix, nonempty qualified result maps, and a
  separately verified receipt for every metric/result/cleanup payload.

Metric and result values remain visible in the final evidence document, but their
canonical payload digests must match independently accepted qualification receipts.
A cleanup reference is not self-authenticating: it also needs a distinct verified
cleanup qualification receipt.

## Failure semantics and threats

Static tool discovery never implies runtime validation. Duplicate receipt references,
duplicate observation slots, foreign qualification IDs, foreign verifier identities,
stale bindings, future timestamps, expired evidence, expired leases, and substituted
payload digests fail the candidate. Missing inputs and verifier/file I/O exceptions
become typed `BLOCKED_CAPABILITY`, `BLOCKED_SOURCE`, or `BLOCKED_AUTHORITY`
obligations; adapter exceptions cannot accidentally promote or erase the blocker.
The module retains no secret material and does not infer authority from installed
software or account availability.

The trusted computing boundary is the configured host/broker implementation behind
the four injected verifier protocols. The application-facing adapter treats verifier
objects, identity strings, and opaque references as untrusted until they match the
admitted role-specific verifier manifest. The manifest reference and digest are
preserved in the evidence. Arbitrary injected objects cannot silently replace an
admitted verifier, and swapping two admitted verifier identities fails because the
manifest is role-bound rather than a set of names. The host still must prove that
those identities correspond to independently administered principals.

Timestamp evaluation is deterministic: the caller supplies `qualified_at`, the
admission supplies the maximum evidence age and lease expiries, and every receipt
supplies an observation and expiry time. The exact qualification ID prevents an old
runtime/result receipt from being replayed into a later qualification. Receipt
references must also be unique across Studio, runtime, qualification, and cleanup
evidence for the attempt.

## Bindings to the whole-OS architecture

- **N03** admits the dedicated Windows host, exact Studio path/version/digest,
  verifier adapter identities, and verifier-manifest bytes. N27 consumes those
  bindings; it does not discover or invent a host command surface.
- **N15** owns brokered external effects and supplies the finite account/broker and
  environment/resource lease references. N27 only observes their independently
  verified state and never treats repository credentials as runtime authority.
- **N18** supplies the independently attested Windows tenant/host isolation boundary.
  A Linux OCI or trusted-local-process receipt cannot be substituted for it.
- **N24** freezes scenario inputs, tolerances, functional/security grading, and the
  result payloads whose digests are attested by qualification receipts. N27 cannot
  create or relax those acceptance criteria.

## Alternatives considered

- Treating installed, signed Studio as runtime proof was rejected because static
  discovery says nothing about game execution, device behavior, persistence, or
  teardown.
- Accepting raw result maps or one aggregate runtime receipt was rejected because it
  permits caller-authored metrics and hides which acceptance surface was actually
  verified.
- Trusting whatever verifier object is injected was rejected because canonical-looking
  identity labels can be substituted; admission therefore pins identities by role and
  preserves the exact verifier-manifest digest.
- Using wall-clock reads inside the adapter was rejected in favor of an explicit
  qualification time, age window, and expiry fields so replay is deterministic.
- Stateful global replay caches were rejected because they break reproducible retries
  and process recovery. Qualification-ID binding plus attempt-wide reference uniqueness
  prevents cross-attempt and within-attempt replay without hidden mutable state.

## Migration, rollback, and limits

The evidence JSON Schema is version 2 and adds qualification, lease, verifier, and
qualification-receipt fields. Blocked legacy construction remains representable with
explicit `unknown`/`none` sentinels, but no legacy or partially populated record can
become qualified. Rollback selects the prior adapter/schema for reading historical
records only; it must not relabel them as version-2 production evidence.

Verifier identity labels and opaque references are structural bindings, not proof of
independent administration by themselves. The injected host adapters remain
responsible for authenticating verifier principals, broker/environment leases, and
receipt signatures. Missing real Roblox projects, rights, accounts, test universes,
devices, or host verifiers therefore remain honest external obligations.

## Evidence disposition

The focused test suite uses verifiers explicitly marked `CONTRACT_FIXTURE`. Successful
fixture execution proves schema, binding, freshness, matrix, and failure-transition
behavior only, and yields `RUNTIME_VALIDATED`; the runtime model and schema both reject
turning that record into `PRODUCTION_CANDIDATE`. Only all-external verifier scope from
the admitted manifest can yield the production-candidate enum, and even then N32 and
the independent promotion court must inspect the real external receipts. No current
fixture, installed binary observation, or this ADR constitutes external Roblox runtime
or production evidence.
