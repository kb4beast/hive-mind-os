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

## Static-check repair handoff, 2026-09-12

The builder read the complete diff from
`aff97517b5d2c416bbfc2dd148e34910f0ae9d29`, this ADR, the changed tests, and all
four supplied failed-command logs. The logs are retained unchanged under
`C:/h/one-touch/state/run-20260912-183953-1214c3cd/`:

- `20260912-193306-ruff-5a928be6.stdout.log`, SHA-256
  `4e958e2ea4576b3fc80d8a9fcad987e5002603c061abbbaf89a3b57b3d4ea2a3`.
- `20260912-193306-pyright-e72b0324.stdout.log`, SHA-256
  `c9290aaba86933befd98002d260022ef86b054db8619364fdf3584f87b1c8be7`.
- The corresponding `.stderr.log` files are both empty, SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

This repair sorts the eight reported import blocks, annotates the authentication
failure helper as `NoReturn`, and expresses the nullable-number exact-type guard
as explicit float/int comparisons so the type checker can narrow its input.
The helper still always raises; booleans, numeric subclasses and nonfinite values
remain refused. No runtime authority, acceptance criterion, test assertion or
configured check was relaxed. Existing malformed-number and unknown-principal
tests remain the verification specifications for these paths.

The caller inspection again located registry promotion and rollback as the
authoritative prompt-pointer writers, with bootstrap and model-backend
initialization entering the same admission gate. The external-sink adapter's
separate boundary and the controller follow-up above remain unchanged.

This batch is ready for launcher verification, not a green-check or independent
review claim. The builder ran no tests, Ruff, Pyright or launcher. The supplied
Pyright log also contains six `reportUnsupportedDunderAll` warnings in
`brain_kernel/__init__.py`, which is unchanged from the pinned base; they remain
visible for launcher review. Independent review, deterministic verification and
non-draft PR delivery remain launcher-owned outstanding work.

## Independent-review repair handoff, 2026-09-12

The builder read the full branch diff from `aff97517b5d2c416bbfc2dd148e34910f0ae9d29`,
the ADR and changed tests, and the independent review of pinned HEAD `88e4c6c`:
`C:/h/one-touch/state/run-20260912-183953-1214c3cd/independent-review-70e0ec1a4410423c8bc3ea1cc252c654.json`,
SHA-256 `41bfafcd06d7738e2b034e858163c51b9448694efc3271444e5b87e20056841e`.
That review's `revise` verdict and three P2 findings remain retained unchanged.
Its reported earlier verification results do not establish this repair's results.

The STOP finding is addressed by treating STOP as the existing terminal court
decision to close candidate work and retain the champion. It is not a new
measurement verdict. Any exact schema-4 evaluation outcome can support that
decision only after its own verdict, scores, contract, identities and artifacts
are reproduced. The signed decision still says STOP and binds the precise record,
reason and action. Four independent authenticated stages, the live-parent check,
and atomic evaluation/nonce consumption remain required. STOP grants neither
rollback nor quarantine nor promotion; existing restrictions remain in force.
The court's existing DEFER/REJECT compatibility and terminal log rule are retained.
Tests specify refusal of unsigned/relabelled STOP, forged but rehashed metrics,
rollback substitution, replay, and recovery after observation failure and restart.

The newline finding is addressed by idempotent normalization: normalize CRLF/CR
to LF, then remove all trailing LF. Internal blank lines, spaces and tabs remain
significant. Registration, hashing and reading now agree on the exact stored
bytes. This intentionally changes the formerly inconsistent identities for some
inputs with repeated trailing line endings; no old digest or artifact is rewritten.
Legacy stored bytes with trailing LF fail with `artifact-noncanonical`, which
`migration_status()` reports as a blocked role. A new registration colliding with
different legacy bytes fails with `artifact-conflict` and requires explicit
migration review. A noncolliding canonical registration cannot move an old pointer
or supply promotion authority. Tests retain original legacy bytes and pointers
for both collision and distinct-digest cases, and cover repeated LF/CRLF/CR input.
Old callers hashing repeated-newline source text may calculate a different digest
from corrected registration; they must resolve the recorded canonical artifact.
Already canonical stored bytes keep their digest. The schema-2 complete-registry
preservation and reviewed operational downgrade obligations above still apply.

The rejection-custody finding is addressed with a shared authority receipt sink
for known and unknown decisions. Signed refusals are saved as immutable file
evidence before ledger publication, preserving a valid signature during a ledger
outage. Signing or persistence failure attempts one explicitly unsigned
`promotion-receipt-unavailable` diagnostic in each independent sink. It retains
the original refusal payload, actor, experiment and custody/persistence error,
and raises `rejection-persistence-failed`, including any fallback sink failures.
It never adds a failed receipt to the successful in-memory receipt collection.
Postcommit receipt failure continues to report committed evidence pending.
Regression specifications cover unknown and already-applied decisions through
both apply and rollback, custody loss, ledger loss with retained signed file proof,
and failure of both diagnostic sinks without repeated attempts.

The pointer-writer inspection again found the shared registry commit primitive
behind promotion/bootstrap and adverse/rollback actions. Model-backend missing-role
initialization enters the same generation-zero gate. No new champion-changing
path, execution authority or controller was introduced. The separate controller
campaign remains in `PROMOTION-BINDING-CONTROLLER-FOLLOW-UP.md`.

Builder disposition: implementation ready for launcher verification. No tests,
Ruff, Pyright, launcher, Git mutation, dependency installation or live promotion
were executed by this builder. Original assertions remain; the non-KEEP coverage
loop additionally includes STOP. Independent reproduction, deterministic checks
and non-draft PR delivery remain outstanding and owned by the launcher. This
addendum records implementation reasoning, not an independent approval or green CI.

## Active-champion read refusal repair, 2026-09-12

The builder read the complete diff from
`aff97517b5d2c416bbfc2dd148e34910f0ae9d29`, this ADR, changed tests and the
independent review of `c9ab5ef` at
`C:/h/one-touch/state/run-20260912-183953-1214c3cd/independent-review-1a8eaade97a343e3a9fe4e32c04b7882.json`,
SHA-256 `8fffa53562eb4183e15b919222b7c25b36115871f6ab436a625befe72bafd32a`.
Its retained `revise` verdict identifies a P2 gap: evaluation, admission or I/O
errors while resolving the active champion could escape apply/rollback before
the action's rejection receipt handling. The review's earlier green verification
receipts do not verify this repair.

Both action paths now share a guarded initial champion read. Read failures retain
the exact requested decision and operation through the existing signed immutable
file and ledger sinks, then propagate the original exception. The receipt leaves
both observed pointer fields unset because resolution failed. An existing
`commit-state-unknown` blocker retains that distinct status; committed-evidence
and rejection-persistence exceptions keep their original recovery semantics.
The guard does not encompass pointer mutation or postcommit observation, so it
cannot relabel those outcomes as pre-action rejection. Signing or sink outages
continue through the existing typed unavailable-receipt diagnostic path.

New regression specifications exercise KEEP, RETEST and rollback with a deleted
active evaluation record, a noncanonical active admission manifest, an unreadable
manifest and a retained unknown-state marker. They check exact signature payloads,
both durable sinks, unchanged pointer/replay bytes, no decision/action ledger
event and continued action eligibility. Additional observation fault cases retain
committed-evidence-pending status and consumption without a rejection receipt.
All original assertions remain. These specifications are not execution receipts.

The pointer-writer inspection again located promotion/bootstrap and adverse/
rollback behind the shared registry commit primitive; model-backend initialization
uses the same generation-zero admission. The separate controller campaign remains
in `PROMOTION-BINDING-CONTROLLER-FOLLOW-UP.md`. No controller work or live action
is included. Earlier dissent, review findings and provenance remain retained.

Builder disposition: ready for launcher verification. No tests, static-check
commands, launcher or Git mutations were run. Independent review, deterministic
verification and non-draft PR delivery remain launcher-owned outstanding work.

## Decision publication refusal repair, 2026-09-12

The builder read the full branch diff from
`aff97517b5d2c416bbfc2dd148e34910f0ae9d29`, this ADR, the changed tests and the
independent review of `cdc687a` at
`C:/h/one-touch/state/run-20260912-183953-1214c3cd/independent-review-473e6b9239b840ec8319b36e63d5babb.json`,
SHA-256 `ede2f4b6d09aec1164eaaa60249921a8a3eabbd2d7e5b8f3105ada0b42d77ae2`.
Its retained `revise` verdict identifies a P2 gap: KEEP and non-KEEP decision
publication preceded receipt handling, while rollback's handler excluded native
SQLite failures. The review's earlier verification receipts do not verify this
repair. Original review evidence and dissent remain unchanged.

All three authority action paths now publish through one guarded helper before
entering registry admission. Publication exceptions, including native SQLite
errors, use the existing signed immutable file and ledger rejection sinks. The
receipt binds the requested operation, exact decision payload, last observed
champion and requested rollback target. Its post-action pointer field remains
unset: publication does not obtain an under-lock pointer observation. The helper
does not retry publication, consume evidence or mark the decision applied. Even
an event retained before a publication error remains evidence, without starting
admission or implying a pointer commit.

If rejection ledger publication also fails, signed file proof remains retained
and the existing diagnostic fallback reports `rejection-persistence-failed`.
Successful rejection persistence propagates the original publication exception.
The guard excludes registry mutation and postcommit observations, preserving
their distinct committed-evidence-pending and unknown-state recovery behavior.

Added regression specifications exercise KEEP, RETEST and rollback with both
`OSError` and `sqlite3.OperationalError`, before publication, after event retention,
and throughout a ledger-write outage. They check exact signed payloads, bounded
sink attempts, retained event provenance, unchanged pointer/replay bytes and
admission/lineage records, no registry admission call, continued action eligibility,
and signed file evidence after opening a new registry instance. Original assertions
are retained. These specifications have not been executed by this builder.

The pointer-writer inspection again found the shared registry commit primitive
behind promotion/bootstrap and adverse/rollback; model-backend initialization
uses the same bootstrap gate. Arena/controller recommendations and the separately
configured external-sink adapter remain outside authoritative registry mutation.
The concrete next campaign remains in
`PROMOTION-BINDING-CONTROLLER-FOLLOW-UP.md`; no controller work is included here.

Builder disposition: implementation ready for launcher verification. No tests,
static-check commands, launcher, Git mutations or live promotions were run.
Independent review, deterministic verification and non-draft PR delivery remain
launcher-owned outstanding work; this handoff claims none of those results.
