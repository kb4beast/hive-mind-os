# ADR-059: Host-authorized external controller trust

## Status

Adapted implementation candidate. Independent Curator and security review are required
before promotion.

## Context

ADR-058 required a controller bundle pin outside the target repository, but the pinning
command accepted caller-supplied actor and evidence strings. A malicious or mistaken
caller could therefore appoint itself reviewer, cite an unresolvable reference, and
self-pin target-controlled Python. The trust JSON had an unkeyed digest, so a writer to
the state directory could also replace it and recompute that digest.

## Court record and disposition

- Advocate: keep the portable external pin and make authorization an explicit host
  capability rather than a command-line assertion.
- Cross-Examiner: reject self-issued identities, repository-owned evidence, unsigned
  grants, path escapes, stale bundle scope, and one-time verification that is not
  repeated before execution.
- Expert: use a replaceable host trust boundary with a narrowly scoped authenticated
  capability; do not add target-controller execution or a repository-side issuer.
- Judge: **adapt** ADR-058 with the controls below. Public-key authenticated identities
  remain a separate higher-burden obligation; this decision establishes a local host
  capability boundary and does not claim cross-host identity proof.

## Decision

1. `trust-controller` requires a host-issued
   `hive-mind-controller-trust-authorization-v1` capability. It cannot mint one or
   redirect verification to a caller-selected authorization root.
2. The capability is authenticated with HMAC-SHA-256 by a key stored under an external
   host authorization root. It binds one repository identity, controller source commit,
   exact canonical bundle digest, grant, validity interval, authorized pinning actor,
   host issuer, independent reviewer, and evidence URI/digest.
3. Authorized actor, issuer, and reviewer are pairwise distinct. A capability naming a
   self-review or an unapproved actor fails closed.
4. Capability, key, and evidence must be regular, non-link files inside the host
   authorization root and outside the target repository. Evidence bytes must resolve and
   match their bound SHA-256 digest.
5. The external trust record uses schema v2 and stores the authorization bindings. Every
   `inspect` re-resolves and revalidates the capability, host key, expiry, reviewer
   separation, and evidence bytes before emitting a controller invocation.
6. Host adapters protect the authorization root with operating-system access controls and
   do not expose its key to target-controller subprocesses. Repository content is never
   accepted as authority.

## Threats, migration, and rollback

Existing v1 trust records are intentionally invalid and require a newly issued host
capability. HMAC establishes integrity within one host boundary; it is not a public-key
identity claim and does not close the authenticated-identity obligation. Compromise of
the host key requires revocation, key replacement, and new capabilities. Rollback removes
v2 trust records and restores review-required behavior; it must not restore arbitrary
actor/evidence pinning.

## Acceptance evidence

Tests must prove valid external authorization, self-review rejection, actor-scope
rejection, repository-owned evidence rejection, evidence-tamper revocation, stale bundle
rejection, and continued non-execution of untrusted target Python.
