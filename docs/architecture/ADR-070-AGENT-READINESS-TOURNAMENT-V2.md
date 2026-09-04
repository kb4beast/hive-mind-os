# ADR-070: Evidence-qualified native specialist DAG and challenger tournament v2

- Status: implemented shadow substrate with repository-wide executable tournament scope; independent final Curator and Judge disposition was recorded as `ADAPT` for bounded local substrate and `DEFER`/`QUARANTINE` for production-facing readiness and superiority.
- Date: 2026-09-04
- Independent court disposition summary:
  - bounded substrate: `ADAPT`
  - production/full-agent readiness: `DEFER`
  - superiority claim: `QUARANTINE`
- Scope: additive successor to the shadow agent-readiness tournament and local
  eight-role execution substrate
- Historical candidate authoring base: commit
  `e788dc11a810fd98d1f3acbe73d59bf01c544bc9`; the implementation is preserved as
  successive reviewable commits rather than rewriting that baseline.
- Preserved v1 plan digest:
  `sha256:3e04ce46f9f4b09ca8fa73d1e5ef0f890c61885f8600fc9e0eb3d1391bc3f3fc`
- Preserved run-006 manifest digest:
  `sha256:214fb770cad8ff81e60686b4e83c0249919d90226062722cd2ae5c52f2627789`
- Preserved run-006 report digest:
  `sha256:521102febd793a4b522a11514ec833ca8e32de338d94a1016430bc1a0cc3cf11`
- Implementation commit:
  `cebfd7c`
- Run-001 command:
  `python -B scripts/run_agent_tournament_v2.py run --repository . --plan docs/execution/dags/agent-readiness-tournament-v2/plan.json --output-dir C:\\Users\\beesp\\.codex\\tournament-runs\\agent-readiness-20260903-v2-run-001`
- Run-001 report digest:
  `sha256:e11d15bb0b88f8e7651bedb5b4c4a229ed6e94eba23a16f236f8aa649bf2bf72`
- Run-001 manifest digest:
  `sha256:208b0de8205064830273429b57c158e4d86a6094707624e2524618b3f57434b5`
- Run-001 repository head:
  `074ad03f7a2eef37b128a3ec1d56e6a5732e9d05`
- Run-001 repository tree:
  `4327667fdee587985c2bc140a31a3749dbf89292`
- Canonical v2 plan digest:
  `sha256:651226a00eea40a606f563719c1b20109f3a721018d06e066129108767cf80fa`

## Context and evidence intake

The owner asked for a repository-wide tournament that grades every specialist both
independently and in composition, executes as a parallel DAG, preserves promising
ideas through bounded challenge and rethinking, and eventually supports a real
code-to-QA lifecycle. The request does not supply model-provider credentials,
externally controlled identities, a hostile-code sandbox, a protected-branch grant,
production telemetry, or independent comparator custody. Those absences are evidence
obligations and may not be replaced by local labels or fixtures.

Tournament v1 intentionally implemented a read/test-only shadow baseline. Its ADR
states that it cannot operationally qualify an agent, materialize a successor, or
execute the successor generation. Run 006 exercised the entire 1,020-file opening
inventory and completed all 28 v1 nodes with verified internal integrity. It showed
real assessment overlap (eight role commands and six system commands), but not
parallel product execution. "Repository-wide" in this context means complete Git-visible
inventory coverage, static checks, full test discovery (`python -m unittest discover -s tests -v`),
all eight constitutional roles, and selected native handlers, not semantic coverage of every
module or full agent embodiment. All eight roles received structural B/`adapt` grades and
remained explicitly `operationally_qualified=false`.

Run 006 is immutable adverse evidence. Its focused code-to-QA lane passed 18 tests
with one platform skip, while the canonical 1,250-test suite had one error in
`test_crash_before_intent_03`. The exact case, eight simultaneous copies, the full
66-test mission-store module, and a separate report probe subsequently passed. The
primary run-006 failure therefore remains real but causally unresolved. It is not
converted to a pass, and v2 does not add a blind runtime retry or serialize the DAG.
The test now closes its store in a `finally` block and includes the primary mission
failure in its assertion so a recurrence is not masked by SQLite cleanup.

Repository inspection found that the native specialist implementations already
exist:

- `OrchestratorPlanner`;
- `RepositoryExplorer`;
- `Architect`;
- `BuilderCoordinator`;
- `CuratorRuntime`;
- `Integrator`;
- `Steward`; and
- `Optimizer`.

They are not composed by one native executable runtime. `MissionRuntime` constructs
a serial role chain and normally calls generic local-only handlers. `RoleRuntime`
can perform effect-free provider cognition but also runs serially. The legacy
`RepositoryMission` code-to-QA path covers Explorer, Builder, and Curator around a
narrow fixture. V1 feedback deterministically derives hypotheses, but it does not
retain a changed candidate, retest one, or submit a promotion appeal.

## Court record

The Clerk preserves six atomic cases. The Advocate is the v2 architecture agent; the
Cross-Examiner is the independently assigned run-006 semantics agent; the Expert
Witnesses are the independently assigned run-006 integrity, safety, and mission-store
diagnostic agents. The Builder identities are separate implementation agents. A
later Curator and Judge must be distinct from all of them before this proposal can be
promoted.

| Case | Atomic claim | Advocate case | Cross-examination | Proposed disposition |
|---|---|---|---|---|
| V2-001 | V1 is a useful baseline but satisfies the requested endpoint. | It scans the repository, executes focused and whole-suite gates, preserves dissent, and emits feedback contracts. | Its rubric forces nonfatal roles to `adapt`, native specialist implementations are not composed, feedback cannot materialize a challenger, and no production execution is shown. | `adapt`: preserve v1 and its runs; add a versioned successor. |
| V2-002 | All eight native specialists should execute through dependency-ready work. | The repository already provides typed specialist APIs, authority boundaries, immutable results, and objective-DAG validation. | Running eight labels concurrently would be cosmetic; mutation, evaluation, and integration have true dependencies, and overlapping writes cannot be concurrent. | `adapt`: execute ready sets only, use native adapters, serialize evidence commits, and block descendants of failures without cancelling independent peers. |
| V2-003 | A high score is sufficient readiness evidence. | Scores are useful for explaining relative structural merit. | Averages can compensate for absent provider, safety, full-suite, identity, or production evidence; v1's count and symbol checks are not semantic qualification. | `reject`: use cumulative, claim-scoped, non-compensating evidence gates; retain scores as information only. |
| V2-004 | A candidate may carry the evaluator that approves it. | Co-locating code and tests is convenient and reproducible. | A challenger could weaken its own rubric, verifier, holdouts, or acceptance policy and then self-approve. | `reject`: require a caller-pinned evaluator manifest outside candidate, source, and run authority; evaluator changes require prior-evaluator meta-promotion. |
| V2-005 | Feedback is complete once hypotheses are written. | Immutable hypotheses and rollback are a safe first step. | No idea is challenged experimentally until a versioned candidate is materialized, evaluated against a preseal, independently judged, and routed to re-entry or an external promotion authority. | `adapt`: add bounded generation-one materialization, retest, court, and generation-two re-entry without moving a champion pointer. |
| V2-006 | The bounded offline slice can prove production readiness or superiority. | Local deterministic evidence can prove mechanics and bounded repository behavior. | External custody, live semantic providers, hostile-code isolation, production outcomes, and equal-budget multi-comparator trials are missing. | `defer`: permit narrowly worded structural/bounded-local adoption only; mechanically block broader claims. |

## Decision

Add a v2 substrate without changing v1's canonical plan, verifier, or historical run
bundles. V2 has four replaceable layers.

### 1. Immutable artifact transport

Specialists exchange content-addressed artifacts rather than hashes whose content is
discarded. Every envelope binds media type, schema identity and version, candidate,
producer, dependency artifacts, content digest, and its own address. The store uses
create-only writes and revalidates both envelope and bytes on every read. Missing,
mutated, aliased, wrong-candidate, or undeclared-dependency artifacts fail closed.

This is local integrity, not an external signature or a durable distributed object
store.

### 2. Claim-scoped qualification

Qualification levels are cumulative:

```text
STRUCTURAL
    -> BOUNDED_LOCAL
        -> PROVIDER_BACKED
            -> INDEPENDENT_E2E
                -> PRODUCTION
                    -> SUPERIORITY
```

Each receipt binds one claim, candidate, artifact, issuer, issuer trust domain,
execution mode, observation and expiry time. Issuer authority is an explicit caller
input. Bounded-local adoption requires real local execution plus passing strict
control-plane and full-suite receipts. Fixture or test-double evidence cannot earn
that level. Provider-backed evidence requires a provider execution. Independent E2E
additionally requires an evaluator trust domain distinct from the candidate.
Production requires production execution. Superiority requires provider or production
execution from a trust domain distinct from the candidate, at least two pinned
comparators, equal budgets, repeated runs, and distinct retained receipts. Any valid
adverse receipt quarantines the claim and cannot be canceled by a passing receipt or
score. Failed strict gates, forged bindings, unauthorized issuers, future evidence,
or stale evidence also quarantine; missing higher-scope evidence defers only that
higher claim.

An informational score never participates in the qualification decision.

### 3. Native dependency-ready DAG

The runtime accepts a validated work graph and schedules only nodes whose dependencies
have completed successfully. Its repository lifecycle is intentionally not eight-way
parallel everywhere:

```text
Orchestrator
    -> parallel Explorer observations
        -> Architect
            -> Builder
                -> Curator + bound evaluator
                    -> Integrator + Steward
                        -> Optimizer
```

Independent role probes may form an eight-way tournament wave. Product work follows
its real data dependencies. The runtime must:

- invoke all eight native specialist APIs, never a generic fallback for native credit;
- expose only declared dependency artifacts to a node;
- give every node a unique executor identity and isolate Curator from Builder;
- require ordering for overlapping write scopes and use per-node workspaces;
- fingerprint every dependency-ordered ancestor and descendant workspace before and
  after a handler, so a producer cannot plant output in a later consumer workspace;
- let unrelated peers finish when one node fails while blocking its descendants;
- serialize append-only event/receipt publication through one coordinator;
- retain deterministic logical digests independent of wall-clock completion order;
- resume from accepted node receipts without repeating accepted effects; and
- state explicitly that monitored local workspaces are not an OS hostile-code sandbox.

### 4. Evaluator custody and bounded challenger re-entry

Before candidate materialization, an `EvaluationAuthorityManifest` must be supplied
from a path outside the candidate repository and run directory together with its
expected semantic digest. It binds the repository commit and tree, current role
champions, evaluator/harness contract, opaque holdout commitment, comparator pins and
licenses, proposer/builder/evaluator/judge identities, budgets, schema version, and
validity interval. Digest substitution, expiry, identity reuse, stale parent,
candidate mismatch, early holdout revelation, or an in-scope manifest quarantines.

The bounded challenger sequence is:

```text
finding
  -> owned falsifiable hypothesis + acceptance + rollback
  -> evaluator/holdout/budget preseal
  -> immutable generation-one artifact
  -> candidate-bound evaluation receipts
  -> independent court recommendation
  -> RETEST/DEFER generation-two re-entry or external KEEP appeal
```

The tournament may register an immutable prompt challenger and retain a re-entry or
appeal request. It must not mutate the source checkout or a champion pointer. This v2
slice deliberately has no KEEP application path: KEEP submission raises the typed
`KeepPromotionUnsupportedError`/`DEFER_UNSUPPORTED` boundary. A later, separately
governed integration would have to connect an externally controlled promotion
authority without weakening compare-and-swap or court requirements. Losing artifacts,
adverse evaluations, dissent, and re-entry records remain addressable.

The evaluator must be executed from a champion-pinned or independently installed
immutable harness, never imported from the candidate checkout. A future evaluator
change requires a two-stage meta-promotion in which the prior evaluator first judges
the proposed new evaluator.

## Executable tournament topology

The code-owned plan contains 30 nodes in nine dependency waves. It produces a
create-only, recursively manifested bundle; an externally signed portable bundle
remains a separate acceptance obligation.

```text
SCAN-REPOSITORY
  -> 8 ROLE-* independent grades
  -> 8 parallel SYSTEM-* lanes
  -> SYSTEM-CONTROL-PLANE-DOCTOR
  -> CHALLENGER-G1
  -> SYSTEM-FULL-SUITE
  -> CROSS-EXAMINE
  -> 8 FEEDBACK-* rethink contracts
  -> CHAMPIONSHIP

SYSTEM-NATIVE-DAG:
  Orchestrator -> Explorer -> Architect -> Builder -> Curator
                                              \-> Integrator + Steward -> Optimizer
```

The parallel system wave contains static parsing, lifecycle, resilience/no-cheating,
evolution, strict control-plane, control-plane tests, the native eight-specialist DAG,
and the pinned code-to-QA corpus. The isolated doctor and canonical full suite follow
as non-compensating gates. The challenger node authenticates and retains a proposal
when external authority is supplied, but it does not invent a holdout or materialize a
candidate. The v2 substrate does not silently reinterpret run-006 or the predecessor
control-plane's unsealed state.

## Acceptance obligations

The proposed offline slice is acceptable only when executable tests demonstrate:

1. artifact create-only behavior, round-trip integrity, dependency/candidate binding,
   duplicate-key rejection, malformed base64 rejection, and tamper failure;
2. attainable bounded-local adoption with structural, native local, strict
   control-plane, and strict full-suite evidence;
3. inability of perfect scores, fixtures, test doubles, stale or wrong-candidate
   receipts, unauthorized issuers, same-domain evaluators, failed strict gates, or
   insufficient comparator trials to satisfy broader claims;
4. positive overlap for independent nodes, no early dependency execution, ordered
   write conflicts, isolated node workspaces, deterministic logical receipts, peer
   completion on sibling failure, descendant blocking, and replay without repeated
   accepted effects;
5. direct calls to every native specialist implementation and rejection of generic
   fallback evidence;
6. evaluator-manifest externality, expected-digest pinning, time and identity bounds,
   repository/champion binding, opaque holdout commitment, and comparator provenance;
7. seal-before-materialization, unchanged source and champion pointers, exact
   candidate-bound artifacts/evaluations, retained losing evidence, and bounded
   generation-one to generation-two re-entry;
8. KEEP submission is mechanically refused by this slice, while genuine RETEST and
   DEFER outcomes can create bounded generation-two re-entry without applying a
   promotion; and
9. the repository CI command `python -m unittest discover -s tests -v`, with any
   failure retaining its causal payload and blocking promotion.

Live provider quality, independent principals, hostile-code containment, production
outcomes, customer value, and superiority must remain reported as unproven.

## Adversarial review and remediation record

The implementation record preserves the following losing cases rather than treating
their later fixes as evidence that they never existed:

- Challenger review found a P0 path where fabricated extra receipts could reach a
  local KEEP recommendation and promotion submission. Commit `a744da3` made KEEP
  unsupported in this slice, required semantic holdout commitment checks, and retained
  RETEST/DEFER re-entry only.
- Qualification review found that a passing receipt could compensate for a failed
  non-strict receipt and that same-domain test doubles could earn SUPERIORITY. Commit
  `ee8814b` made every valid adverse receipt a quarantine veto and required
  provider/production plus a separate trust domain for superiority evidence.
- DAG review reproduced a Builder writing into the future Integrator workspace and
  having the file falsely attributed to Integrator. Commit `e3c319a` added
  content-sensitive fingerprints for dependency-ordered workspaces while retaining
  legitimate unordered-peer overlap.
- Native-handler review found arbitrary synthetic candidate digests, a Curator that
  checked only test-directory presence, all-healthy hardcoded Steward observations,
  and unconditional Optimizer evidence completeness. Commit `074ad03` bound all eight
  handlers to HEAD/tree/plan, validated the Builder product, ran a sealed smoke test,
  degraded unobserved surfaces, and made downstream evidence completeness derived.
- Additional preserved cases for this V2 run include:
  - Nested `stderr` and non-canonical JSON structures previously accepted by replay
    normalization were rejected by running fixed-root replay substitution and strict
    receipt re-derivation.
  - Mutable V1 command-runner/full-suite substitution was closed by pinning and
    identity-checking the builtin command runner for trusted verdicts.
  - Run/authority output-root overlap acceptance and in-repository authority
    manifest paths were treated as hard failures by canonical overlap guards.
  - Missing native artifact reads now fail as typed evidence-receiver errors
    instead of raising untyped `KeyError` paths.

These fixes satisfy bounded regression claims only. The review also preserved the
cooperative-isolation, timeout, unsigned-authority, schema-label, and same-trust corpus
limitations in the threat record below.

## Alternatives considered

1. Raise v1's numeric scores or change `adapt` to `adopt`: rejected because it creates
   a label without new evidence.
2. Replace every generic handler inside `MissionRuntime` immediately: deferred because
   it mixes a new scheduler, native adapters, effects, migration, and authority in one
   irreversible kernel change. V2 is additive until independently qualified.
3. Execute all eight roles simultaneously: rejected because it violates real artifact
   dependencies and creates unsafe write races.
4. Let the candidate carry its evaluator and hidden tests: rejected as self-approval.
5. Auto-apply successful challenger results to prompt or Git champions: rejected;
   capability does not grant promotion, merge, or protected-branch authority.
6. Add infrastructure retries to erase run-006: rejected. Diagnostic preservation is
   adopted; retry requires a reproduced transient class and a separate court.

## Threat model and remaining blockers

- A local semantic digest detects substitution but does not prove external custody or
  authenticated identity.
- Per-node workspaces, write-scope inventories, and ordered-workspace fingerprints do
  not confine hostile native code, child processes, or the network. Unordered peers
  are deliberately allowed to overlap and a hostile peer could race cooperative
  observation. Provider-authored code requires an OS-level sandbox before hostile-code
  qualification.
- A timed-out synchronous handler runs in a worker thread which Python cannot forcibly
  terminate; no post-timeout receipt may be treated as proof that its process effects
  stopped. Hostile or provider execution requires a killable process/container lease.
- Native candidate identity binds the committed Git HEAD, tree, and exact DAG plan.
  The tournament additionally requires a clean checkout and seals every visible file;
  callers outside that runner need an equivalent state/inventory binding if they
  evaluate dirty or untracked content.
- Qualification issuer authorities and courtroom identities are caller-provided local
  values, not signatures or authenticated principals. Their local decisions remain
  below an externally controlled trust boundary.
- Local fixture and synthetic provider episodes prove protocol mechanics, not semantic
  intelligence, customer value, or unattended production operation.
- Hidden-test commitments generated by the same trust domain are not independently
  hidden.
- The pinned code-to-QA corpus executes a deterministic, same-trust Builder test
  double without an OS or network sandbox. It is regression evidence, not arbitrary
  generated-code qualification.
- Prompt artifacts are not source patches. General code materialization still needs a
  governed Builder effect adapter, isolated checkout, sealed acceptance corpus, and
  exact changed-path verification.
- External search, credentials, spending, deployment, signing, protected merge, and
  policy mutation remain outside this authority.
- Superiority remains deferred until multiple pinned comparators are run with equal
  budgets, repetitions, noise policy, retained losing receipts, and an independent
  verdict.

## Migration and rollback

V1 and v2 operate in shadow alongside the current production paths. No persisted v1
schema, historical receipt, prompt champion, source-control pointer, authority root,
or protected state is migrated. Callers opt into v2 direct modules and must supply an
external evaluation manifest and digest where challenger evaluation is requested.

Rollback removes the new v2 modules, tests, script/entry point if later added, and
this ADR from a successor commit. Content-addressed artifacts and prior tournament
bundles remain append-only evidence and are never reinterpreted as promotion receipts.

## Promotion boundary

This ADR may move from proposed `adapt` only after a separately identified Curator
reproduces the focused and full acceptance evidence, a separate Judge addresses the
recorded dissent, and the exact candidate commit/tree plus evidence digests are
appended without rewriting the authoring-time record. Even then, the maximum claim of
the offline slice is bounded-local executable composition and challenger mechanics,
not production readiness or superiority.
