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
