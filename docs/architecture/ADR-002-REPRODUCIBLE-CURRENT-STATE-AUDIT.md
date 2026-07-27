# ADR-002: Reproducible Current-State and History Audit

- **Status:** Accepted for Stage 0
- **Date:** 2026-07-27
- **Originating work order:** `docs/architecture/MASTER_IMPLEMENTATION_PROMPT.md`,
  Stage 0 and first implementation backlog item 1
- **Source claims:** `CLM-013`, `CLM-051`, `CLM-075`, `CLM-077`, `CLM-080`
- **Capability maturity:** structurally prototyped

## Court record

**Case:** `CASE-IMPL-001-CURRENT-STATE-AUDIT`

**Question:** How should Hive Mind OS reproduce its repository, history, source-docket, broken
receipt, and test baseline before later implementation claims rely on it?

**Advocate:** `advocate-audit-pass-1` argued for a deterministic command that preserves exact
commands and outputs, compares facts with the pinned baseline, and emits a canonical digest.
This makes stale or broken implementation claims visible to later gates.

**Cross-Examiner:** `cross-audit-pass-1` identified unstable timestamps, local-ref-dependent
commit counts, self-referential committed artifacts, secret leakage through signing inputs,
recursive test invocation, platform variance, and the risk of calling a plain digest a
signature.

**Expert testimony:**

- `expert-product-audit-pass-1`: the audit reduces false completion and repeated manual
  rediscovery, but it has no customer-outcome proof yet.
- `expert-security-audit-pass-1`: canonical SHA-256 integrity is useful but is not external
  authenticity; key-backed signing must be explicit and must not serialize the key.
- `expert-sre-audit-pass-1`: command failures and skipped tests must remain visible and make
  the artifact incomplete.

**Judge:** `judge-audit-pass-1`

**Independence disclosure:** These are labeled same-session role passes with correlated error.
They are not independent Curator verification. Promotion remains blocked pending a disjoint
verifier.

**Verdict:** `adapt`

Adopt a deterministic collector and adapt the requested “signed/digested” output into an
always-present canonical SHA-256 digest plus optional HMAC signing from an external key file.
The unsigned state is explicit. Exact command observations, failures, test results, source
blockers, broken local references, tool versions, and discrepancy cases are retained in the
artifact.

## Considered alternatives

1. **No change/manual audit:** rejected because the stale baseline and dangling
   `tests/test_policy_invariants.py` receipt remain machine-invisible.
2. **Write only a prose snapshot:** rejected because it cannot be replayed or integrity
   checked.
3. **Require signing before any audit can run:** deferred until an external workload identity
   and trust root exist; manufacturing a repository-owned signing secret would weaken the
   truth boundary.
4. **Implement all Stage 0 work in one rewrite:** deferred because it expands scope before the
   evidence foundation exists.

## Decision

Add `hive-mind audit`, backed by a provider-neutral Python collector. The command:

- inventories the current Git SHA, all reachable refs, tracked and historical paths, ignored
  and dirty entries, deletes, renames, and content digests;
- records source, claim, status, state, disposition, docket issue, blocker, and broken local
  reference counts;
- executes the configured test command and preserves its exact observation;
- compares results with the pinned audited baseline and opens additive discrepancy cases;
- emits a canonical SHA-256 envelope and optionally an HMAC-SHA256 signature with a named key;
- creates audit files exclusively so an existing artifact cannot be overwritten;
- fails its process status when required collection or tests fail, while still writing the
  evidence artifact.

## Threats and controls

| Threat | Control |
|---|---|
| A modified audit payload retains an old digest | Recompute the canonical payload digest during verification |
| A digest is misrepresented as proof of authorship | Signature is `null` unless a key file and key ID are supplied |
| A signing secret leaks into evidence | Read key bytes directly; never include them in commands or output |
| Missing or failing commands disappear | Preserve return code, stdout, stderr, and an explicit failure list |
| Skipped tests appear successful | Mark test status `not_run` and the audit incomplete |
| A later run overwrites prior evidence | Open output files in exclusive-create mode |
| Stale docket receipts pass silently | Resolve architecture/code/test/benchmark file references against the audited worktree |
| Volatile facts are mistaken for the old baseline | Emit additive discrepancy cases rather than overwriting audited values |

## Acceptance tests

- A real repository audit reports the 22-source/80-claim docket and all seven current source
  blockers.
- The dangling `tests/test_policy_invariants.py` receipt is reported.
- Mutation after serialization fails digest verification.
- A signature verifies only with the matching key.
- Skipped tests cannot produce a complete artifact.

## Migration and compatibility

The existing `hive-mind "<goal>"` invocation remains unchanged. `hive-mind audit` is a new
reserved first argument. The artifact schema starts at version 1. Unknown future versions
must not be treated as verified by consumers without an explicit compatibility decision.

## Rollback

Remove the `audit` dispatch and the new audit module/export/tests. Existing kernel behavior and
data remain unchanged. Previously emitted audit artifacts remain historical evidence and must
not be deleted; a superseding artifact records the rollback.

## Metrics and ownership

- broken-reference detection rate;
- audit reproduction success rate;
- false-complete audit rate (target zero);
- baseline discrepancy resolution latency;
- test-receipt coverage.

The Steward owns command reliability and evidence retention. The Curator owns independent
reproduction. The Integrator owns schema compatibility. The Optimizer may propose changes but
cannot promote its own audit implementation.
