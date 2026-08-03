# ADR-043: Authenticated External Repository Source Locks

- **Status:** Adapted for a bounded local/reversible source-lock implementation after independent Curator and Judge review; not a provider-authentication promotion
- **Date:** 2026-08-03
- **Prior decisions:** ADR-040, ADR-041, ADR-042
- **Scope:** explicit remote Git materialization only; no branch, pull-request, or governance mutation

## Context

ADR-040 resolves a full Git commit SHA before queuing repository work.  That pins a
reproducible object, but it does not authenticate a remote repository, its owner, its
revision provenance, or a local lock file.  A local SHA-256 digest, Git commit SHA, Git
tree SHA, successful clone, or local SQLite row is therefore **not** a source identity
or authentication claim.

The external source-lock/identity specification named in the P1 plan is unavailable in
this worktree.  This decision cannot invent it.  It instead supplies a narrow,
replaceable verification boundary for a separately controlled source-custody authority
to make a specific, signed statement.  The authority's public root, signed keyset,
key identity, rotation, revocation, issuance window, and signature verification reuse
the bounded external public-key custody boundary introduced by ADR-042; no private key
or signing operation exists in this package.

## Court record

- **Advocate (Builder):** accept a remote source only when an external authority has
  signed the exact canonical URL, provider repository identity, external principal,
  mission/state binding, commit, and tree; verify the resulting clone against those
  signed immutable values before use.
- **Cross-examiner (Architecture review):** reject any wording that promotes a Git
  object identifier or locally stored digest to authentication, bind both the remote
  address and post-clone tree, keep source provenance append-only, and fail closed on
  signature, freshness, rotation, revocation, replay, or identity mismatch.
- **Expert testimony:** a cryptographic external signature can authenticate the
  authority's bounded statement when verified against its trusted public key and live
  keyset; a content address alone only identifies bytes.  The authority must still
  establish the upstream-provider identity and its own signing controls outside this
  process.
- **Curator disposition:** `adapt`. Independent focused reproduction confirmed strict
  durable provenance, source identity/mission/state binding, rotation/revocation,
  deferred checkout, source-tree checks, delivery-envelope lineage, and hostile replay
  cases. It found no remaining bounded-tranche correctness blocker.
- **Judge disposition:** `adapt`. Independent reproduction additionally confirmed empty
  SQLite paths are rejected as non-durable, before/after-checkout tree checks, exact
  receipt state binding, signed envelope re-verification, and delivery cross-binding
  rejection. No production, provider, or superiority claim is authorized by this ADR.

## Decision

1. `source-lock` is a closed, typed immutable record containing a canonical,
   credential-free HTTPS repository URL, mission/state binding, full lowercase commit
   SHA, full lowercase tree SHA, and a source identity (`provider`, repository ID, and
   externally asserted principal).  It is deliberately unsigned by itself.
2. `source-lock-attestation` is a separate signed external envelope over exactly that
   record.  It has a distinct audience and signature domain.  Its authority, signer
   identity, key ID, keyset sequence, issuance/expiry, nonce, and algorithm are
   verified through the public keyset boundary.  Current keyset freshness, monotonic
   rotation, and revocation all fail closed.
3. `SourceCustodyVerifier` is a replaceable adapter: it validates both closed
   contracts, checks byte-for-byte semantic equality between the requested and signed
   lock, invokes external signature/keyset verification, and writes an append-only
   local provenance record.  That record rejects changed lock IDs, attestation IDs,
   and authority/key/nonce replays.  It is retained evidence, never a trust root.
4. `GitWorkspace.materialize` receives an optional source-custody verifier and signed
   evidence.  For a remote source, `require_source_custody=True` rejects an absent
   signed lock before creating a workspace or clone.  When evidence is present, it
   verifies the caller-supplied mission/state identity, canonical remote URL, and
   commit before clone, fetches with `--no-checkout`, verifies the locked tree object,
   then verifies the detached checked-out tree after checkout. The exact bound state
   reference is propagated into every Git receipt and the signed envelope/digest is
   retained in an authenticated-source delivery manifest. A
   local repository cannot be passed off as authenticated source-lock material.
5. Existing remote materialization remains compatibility-only unless the caller
   explicitly requires custody.  It retains its previous full-pin reproducibility
   behavior but must be described as **unauthenticated**.  No existing mission path is
   silently promoted; the current repository mission materializes local repositories.

## Threat model and residuals

| Threat | Control | Residual / explicit non-claim |
|---|---|---|
| Mutable branch or changed remote URL | Exact canonical URL and full commit in the external signature | Does not establish that the chosen commit is desirable |
| A different tree at the signed commit | Detached checkout plus post-clone signed tree equality | Git object IDs remain content locators, not identities |
| Locally fabricated SHA, clone result, or SQLite row | Authentication requires the authority's public-key/keyset verification | A hostile host can deny service or erase local evidence; it cannot be treated as an authenticated authority |
| Replayed source assertion | Expiry, keyset freshness, unique external attestation ID, lock ID, and authority/key/nonce provenance checks | Clock and keyset availability remain external dependencies |
| Compromised/retired signing key | Pinned root, signed monotonic keysets, current-keyset enforcement, and revoked-key rejection | Root compromise and an authority that signs false provider claims are outside this process |
| Credential-bearing or redirected source address | Strict credential-free canonical HTTPS URL grammar | Only the narrow configured-host surface is supported |
| Fake provider/owner identity | Signed identity must exactly match canonical provider/repository fields | The authority, not this adapter, must verify provider control; no independent GitHub lookup, commit-signature validation, license review, or malware analysis is claimed |
| Branch protection or release governance change | None; this tranche never calls a hosting API or mutates governance | External branch controls remain out of scope and require explicit authorization |

## Migration and rollback

- The new provenance store is additive and append-only.  There is no backfill: legacy
  pins and local source copies are recorded as local integrity/reproducibility evidence,
  not authenticated source custody.
- A caller adopts custody by obtaining a signed lock from its independently controlled
  source-custody service, installing that service's verified keyset, and passing both
  verifier and evidence into remote materialization with `require_source_custody=True`.
  Strict mode requires durable (non-memory) keyset and source-lock provenance, and a
  caller-supplied exact mission/state binding. Missing evidence, an unavailable verifier,
  or any mismatch fails before clone.
- Rollback removes the optional hook from a caller but does not delete source-lock or
  keyset evidence.  It restores unauthenticated compatibility behavior and therefore
  cannot be used to claim the same authenticated boundary.

## Builder verification

- `tests/test_source_custody.py`: validates exact signed identity and lock binding,
  tampering, durable replay resistance across reopen, current-keyset rotation/revocation,
  required remote custody, pre-clone pin mismatch rejection, and tree mismatch rejection.
- `tests/test_contracts.py`: validates the two closed source-custody schemas in the
  catalog.
- `tests/test_git_adapter.py`: retains existing local pin/materialization receipt
  coverage; it does not authenticate local source.

## Deferred obligations

This draft does not complete source ingestion or licensing obligations, remote mirror
retention, upstream provider witness collection, commit/tag signature policy,
multi-party/threshold source custody, untrusted-code isolation, credential isolation,
or resumable model-backed role state.  Those remain separately judged tranches.  The
missing external source-lock specification and production authority operating evidence
remain explicit blocking evidence obligations.
