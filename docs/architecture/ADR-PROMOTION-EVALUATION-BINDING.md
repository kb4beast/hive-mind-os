# Explicit evaluation binding and authenticated promotion admission

Status: implemented for later review; acceptance execution and independent review
are pending. No deployment, promotion, protected merge or green CI is claimed.

The owner directed implementation first on 2026-09-12, bypassing further
pre-implementation tournaments and deferring the checking pass. That execution
direction supersedes the earlier procedural retry stop for this development
work. Existing failed reports and court records remain untouched. It does not
turn this document into an independent court verdict or provide signing keys.

## Problem and scope

At base commit `aff97517b5d2c416bbfc2dd148e34910f0ae9d29`, tree
`242b967852a7e93298df676fe0f0e8d67bb41d2f`, a structural KEEP event could reach
the prompt registry without resolving an exact evaluation record. The proposal
descriptor identifies a proposal, while the promotion candidate identifies
prompt bytes. Neither the proposal digest nor an opaque change reference may
be repurposed as the prompt artifact digest.

This change joins explicit evaluation subjects, retained record validation,
host-configured principal authentication, and transactional registry admission.
It excludes the separate post-merge campaign controller, deployment automation,
new credentials, provider installation, and benchmark superiority claims.

## Evaluation contract

An additive `PromptEvaluationSubject` identifies the exact candidate, role,
experiment, prompt and parent digests, proposer, builder, proposal descriptor,
ordered evidence references and evaluation contract fingerprint. Its canonical
digest is the immutable version of that complete assertion. A pure candidate
adapter preserves the existing candidate fields and their digest semantics.

Supplying that subject to the producer creates schema-4 evaluation evidence.
Calls without a subject retain the schema-2/3 producer path. Legacy records
remain inspectable; inspection does not grant new promotion authority. Every
verdict remains evidence, including an unsealed quarantine record.

The reader validates canonical document identity, schema-specific shapes and
types, full record digest and evaluation ID. The KEEP resolver checks the
declared subject, exact retained contract, identities, seal state, surface
artifacts and sufficient recorded metrics. It recomputes the verdict and derived
selection/scores rather than trusting a rehashed KEEP label. It performs no
model call, holdout reveal or pointer mutation. The registry separately resolves
the actual canonical prompt bytes and current parent before activation.

Canonical document digests and raw file hashes are separate domains. A truncated
evaluation ID is a label, never the durable replay key. A relocated record keeps
its content identity and has a different reference path. Rechecking files proves
observed bytes at that time; it does not make the filesystem immutable.

## Principal authentication

`PromotionPrincipalVerifier` requires host-supplied trusted principal bindings,
a signature verifier and a rejection receipt signer. Builder, verifier, judge
and promoter must be different principals with different configured
administrations and public-key pins. Evidence cannot nominate its own trust
policy. No default credential, permissive verifier or automatic trust bootstrap
exists.

Builder attestation binds the immutable subject before evaluation; verifier
attestation additionally binds the full evaluation record; judge and promoter
attestations also bind the exact decision event payload. Stage-specific nonces,
UTC validity intervals, maximum age, ordering and the trust-policy digest are
verified. The promoter is separate from the judge. Evaluation and nonce
consumption belong to the atomic registry transaction, not an in-memory verifier.

An optional Ed25519 adapter loads the external `cryptography` provider only when
used and checks each raw public key against its trusted digest. Missing provider
or keys fail closed. Applications may instead inject an external signing and
verification service through the protocols. Test HMAC adapters are confined to
tests and do not demonstrate independent production administration.

Independent administration is an explicit trusted configuration assumption.
Distinct labels alone cannot prove that real administrators are independent.
Signatures attest who endorsed content, not that measurements necessarily came
from executing the claimed prompt. Colluding authorized principals or a
compromised trust host remain outside the guarantees of content validation.

## Registry transaction and adverse evidence

Non-bootstrap promotion requires the resolved evaluation subject/reference and
authenticated authorization in the decision event. Under the shared-root and
interprocess lock, admission compares the live parent and exact prompt bytes,
rechecks evidence, and refuses previously consumed evaluation/nonce identities.

Pointer schema 2 co-commits the champion, its admission binding and durable
consumption maps. An immutable admission manifest and prepared event precede
the atomic pointer replacement. Final lineage and ledger observations follow.
Failure before commit must not consume evidence or move the champion; failure
after commit must be represented as committed evidence pending, not an unchanged
pointer or a rejected promotion. Observation recovery must be idempotent and
must not move a pointer or clear replay state.

Historical serving checks the retained committed binding rather than trying to
consume it again or requiring its former parent to remain current. Rollback
preserves consumption and restores the selected historical binding. Rejection
payloads are authenticated by configured receipt custody and retained in the
ledger. Without signing custody the system cannot manufacture authenticated
rejection proof; it retains an explicit unavailable-authentication diagnostic
and refuses activation.

## Threats and limitations to inspect

Acceptance cases must cover missing or substituted subject/record/contract,
rehashes of false scores or insufficient measurements, stale/future signatures,
wrong principals/keys/policy, duplicate administrations and nonces, replay after
restart/relocation/rollback, wrong live parent, file changes after resolution,
and competing writers. Fault injection must distinguish manifest/preparation
failure, precommit replacement failure, committed observation failure and
ambiguous state. Recovery after later promotion or rollback needs explicit
coverage. Do not treat these listed cases as executed results.

Local files, the registry lock and trusted signature adapters are the boundary;
this is not a sandbox against a privileged hostile filesystem writer. Retained
trust policy/key material is required to verify historical authorization after
rotation. No claim of universal closure of every possible repository mutation
surface is made without the later review and acceptance evidence.

## Migration, compatibility and rollback

Existing candidate and decision binding digest meanings stay unchanged. Historical
receipt bytes are retained; legacy evidence is not silently rewritten into a
new authorized evaluation. New non-bootstrap promotions need fresh bound
evidence and configured authenticating principals. Exact generation-zero
initialization remains the explicit existing bootstrap exception.

Before any live rollout, inspect legacy active pointers and produce an explicit
migration disposition. Preserve original pointer, ledger, lineage, evidence and
trust snapshots. Reading old evidence is distinct from granting it new
activation authority. No startup rewrite or automatic live promotion is part
of this development change.

This delivery is currently reversible by discarding or reverting the unmerged
code. After any schema-2 pointer has been written, a code revert alone is not an
operational downgrade: old code cannot read that schema. A later live rollout
requires a compatible reader or reviewed whole-registry recovery procedure that
preserves audit and replay state. Never erase consumption to make old code start.

## Acceptance status and provenance

Tests and fixture migrations are included for the next checking pass. The owner
requested that execution and independent review be deferred. Therefore no
focused test, full unittest, Ruff, Pyright, platform matrix or CI success is
claimed for this implementation. The canonical gate remains
`python -m unittest discover -s tests -v`; existing assertions and CI controls
are not removed.

Sources are the MIT-licensed pinned repository above and retained local evidence:
`C:/h/t31/ARCHITECTURE-REMAND.md` (SHA-256
`6bf51c461c55e2355c4b51d3bf0d9f9e66639020984813d91d76663518d04e4b`),
`C:/h/t31/CURATOR-ARCHITECTURE-EXAMINATION.md` (SHA-256
`d17a7b246f771e831e2408d7dab32667de87d7897c09b3306b7f68911d545e16`),
and the original baseline reproduction and failed tournament closeout at
`C:/h/t33/DELIVERY-BLOCKER-CLOSEOUT.md`. These are evidence, not additional
execution instructions. Full-V1 transaction/migration dissent and the narrower
prerequisite's failure to close admission are preserved in those originals.

## Owner-authorized repair batch, 2026-09-12

This addendum records the builder repair against the existing implementation.
The current owner scope assigns deterministic verification, independent review,
Git commits, push and non-draft PR delivery to the external launcher. This
builder did not invoke that launcher, any continuation dispatcher, tournament,
test suite, dependency installer, credential provisioning or live promotion.
The earlier acceptance-status paragraph describes the original implementation;
this addendum does not claim that its pending verification has since passed.

The signed decision payload now includes `action` (`apply` or `rollback`).
RETEST, DISCARD and QUARANTINE actions require the same four authenticated
stage principals as KEEP, an exact schema-4 subject and record, and recomputation
of the declared verdict. The proposer remains separate from all four actors.
A retained unsealed quarantine can authorize an adverse action when the record,
contract and referenced artifacts remain intact. Missing artifacts are readable
as adverse evidence but do not grant action authority. KEEP cannot be relabelled
as a rollback; neither a changed action nor a changed reason reuses its signatures.

`rollback_champion` now requires an exact event sequence, evaluation experiment,
expected live candidate and independently authenticated promoter. The signed
subject binds both the live artifact and restored parent. A new adverse
evaluation may use a new experiment while referencing the original retained
artifact registration; it cannot substitute the original author, role or parent.
The target must resolve to an already committed admission or an exact historical
generation-zero promotion. Consumption maps are never cleared by rollback.

All adverse actions prepare immutable admission manifests and atomically commit
record/nonce consumption with their pointer effects. Quarantine state is part of
that commit, so a failed post-rollback observation cannot leave the rejected
candidate eligible again. New generation-zero initialization also has a prepared
manifest and committed binding, keeping the existing exact-bootstrap exception
recoverable without granting it general promotion authority. Observation files
are published only after their bytes are complete, using an exclusive hard link
within the registry directory. Filesystems lacking that operation fail closed.
The guarantee concerns process interruption and restart on the supported local
filesystem; no storage-device/power-loss certification is claimed.

`recover_promotion_observation` handles KEEP, bootstrap and adverse admissions
without replaying actions or changing pointers. `PromotionAuthority.recover_receipt`
uses a retained, resubmitted court-backed decision and committed admission to
recover a failed authority receipt, including after later champion changes.
An error reported after pointer replacement remains committed-evidence-pending;
an unreadable or conflicting replacement remains a durable unknown-state blocker.
No automatic repair of an ambiguous pointer or its marker is provided.

Rejection signatures now include the requesting actor and experiment as well as
the exact referenced decision, record and authorization identities. Custody or
persistence failure produces a typed failure and attempts an explicitly unsigned
unavailable-authentication diagnostic; it does not manufacture signed evidence.
Prompt reads also refuse noncanonical raw bytes even when their normalized hash
would match. Decision and manifest rechecks still occur immediately before commit.

`migration_status()` reports per-role serving/migration obligations without
rewriting historical artifacts. Unbound legacy non-bootstrap pointers fail with
`legacy-promotion-evidence-required`. Fresh authenticated evidence may replace
an explicitly selected legacy parent through normal admission; merely reading
old records supplies no authorization. Relabelling schema-2 state as schema 1
while retaining admission fields is rejected. A real downgrade remains an
unsupported operational recovery requiring preservation of the complete registry;
there is no lossy export, automatic startup rewrite or replay-state deletion.

The inspected prompt-pointer writers are registry KEEP/initialization and
rollback; `bootstrap` and the model backend's missing-role initialization both
enter that registry gate. The experiment runner proposes KEEP for later review
and can emit a restriction-only quarantine safety signal, but cannot activate a
champion. The low-level `quarantine` API remains that fail-closed restriction
surface; its actor label is explicitly not an authenticated court decision.
The autonomy arena and recursive improvement controller recommend or simulate
decisions without changing the authoritative pointer. The separately enabled
`evidence_court.PromotionAdapter` calls a host-supplied sink and has no repository
caller or direct prompt-pointer access; external sinks remain outside this
registry's authority and recovery contract.

Added regression specifications cover authenticated non-KEEP actions, unsigned
rollback refusal, action/actor/reason/current-candidate substitutions, verdict
relabelling, durable consumption after restart and relocation, precommit and
postcommit rollback faults, co-committed quarantine, bootstrap recovery,
authority-receipt recovery, competing registry writers, byte mutation during
preparation, and legacy/downgrade dispositions. Original assertions are retained;
successful rollback fixtures now supply fresh adverse evidence and signatures.
These specifications have not been executed by this builder. Launcher verification
and an independent reviewer must establish their results.

The separate continuation/controller campaign is explicitly deferred to
[PROMOTION-BINDING-CONTROLLER-FOLLOW-UP.md](PROMOTION-BINDING-CONTROLLER-FOLLOW-UP.md).
Existing dissent, failed tournament evidence and source-ingestion obligations
remain in their original locations and are neither replayed nor superseded by
an invented court verdict.
