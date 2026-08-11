# ADR-058: OPTIMIZER-370 post-expiry completion reauthorization

Status: conditional ADAPT for isolated C2/H2 construction; activation and integration deferred

Date: 2026-08-11

## Context and Court disposition

The exact OPTIMIZER-370 repair claim expired after its adopted candidate reached
`948368b77ba8de920369f416970e83b909bd50ba`, tree
`e7fe4cdec441550a0007306182b222ac76ba73b3`. There was no continuation or completion
intent before expiry. The ordinary recovery path cannot truthfully complete an expired claim,
and rolling the live candidate back to execution merge `88f2962b64f7cc9f88284c5dd30106de5313da7b`
would discard adopted terminal-green work.

Independent Advocate, Cross-Examiner, security/durability Expert, Judge, and Appeals Judge
identities issued a narrowed `ADAPT`. They permit only construction and validation of a new
incident-specific C2 implementation and H2 reseal from exact singleton release
`G=9ea57b8ee1bb630b4fe3a8350e1629c4fb4a4379`. All activation, remote mutation, and
integration remain deferred.

Prior overlay `H=457f4608fcd1990fc89e30a2caa8019c3b02f788` and PR143 are quarantined evidence.
Their Court and code required arming while the old claim was unexpired; that event did not
occur. Neither artifact supplies authority and neither may be integrated.

## Decision

Add a new post-expiry authority schema that binds the complete immutable incident tuple: old
receipt and payload, full expired claim payload and owner, G and tree, ordered execution merge,
candidate and tree, PR135, intended replacement receipt, main and release evidence, authorized
paths, and the sealed absence of prior continuation or completion state. The old claim is never
renewed, rewritten, removed, or assigned a new status.

The runtime design is one-time and monotonic. A fresh bounded authorization is created with
`O_EXCL` in the Git common directory. File and containing-directory durability are synchronized.
Digest-bound transitions progress from `AUTHORIZED` through `CONSUMING` to irreversible
`CONSUMED`; unused expiry and ambiguous state become terminal evidence. The only possible node
mutation is a separately activated exact compare-and-swap from candidate `948368b...` to a
zero-path child containing the exact intended receipt. No transition or compensation targets
`88f2962...`, and a successful node CAS can only recover forward.

Completion authority contains no release-integration power. H2 remains quarantined after this
delivery. Once literal H2, its tree, exact topology, final focused evidence, and the full canonical
suite are immutable, a different Judge and Appeals Judge must issue a separate, freshly expiring,
one-time authority for only the exact release-ref CAS from G to H2. That later authority may not
move main, a node branch, a claim, a receipt, the dispatcher, or a PR.

Git transport continues to fail closed on environment configuration injection, includes, URL
rewrites, remote helpers, protocol/HTTP trust overrides, literal-origin mismatch, disabled TLS
verification, or disabled certificate revocation.

## Validation and rollback

Focused tests cover every sealed-field mutation, old-claim immutability, expiry boundaries,
concurrency, every durable-write and CAS crash cut, foreign and ADVERSE state, target/main/PR/tree
drift, third receipts, exact receipt topology, hostile Git configuration, TLS, and revocation.
The canonical suite runs only on immutable H2.

Before a node CAS, an unused authorization may become terminal `EXPIRED` while the live candidate
remains unchanged. At or after the node CAS, rollback is forbidden; restart can only reconcile the
same exact receipt to `CONSUMED`. C2/H2 can be abandoned without integration. Any later release or
product reversal requires new append-only Court authority.
