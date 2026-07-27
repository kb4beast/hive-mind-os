# Stage 0 Truth and Source Governance Appeal Record

## Case

- **Case:** `CASE-IMPL-003-004-STAGE0-TRUTH-SOURCE-GOVERNANCE-APPEAL`
- **Branch:** `codex/master-implementation-bootstrap`
- **Final local candidate:** `f71e37934f86bdf45030cfa1fff4203445a1a87c`
- **Burden:** implementation
- **Current disposition:** `defer`

`defer` is procedural, not a technical rejection of the final candidate. The required final
disjoint Curator and Judge could not run because the independent-agent service reported its
usage limit. No replacement identity or passing verdict is invented.

## Preserved adverse findings and appeals

| Commit | Independent disposition | Material counterexample |
|---|---|---|
| `577cc2f3bad9c7c78dd372a8207a871b8a06eb35` | Curator, Orchestrator, and Judge rejected | Clean checkout byte mismatch; permissive paths/times/numbers; incomplete action binding; mutable manifest semantics; source-blocking gaps; forgeable coverage/maturity |
| `cd09870b52c1b49b5598fdf21504424058bc4863` | Orchestrator rejected | Coordinated clearing of all mutually attacker-controlled blocker lists produced a false release-ready audit |
| `c1d709a24af56e9df1dfb787c496633265b999cf` | Orchestrator rejected | Coordinated deletion of the entire source/claim inventory still verified after re-digesting |
| `f71e37934f86bdf45030cfa1fff4203445a1a87c` | Final independent verdict unavailable | Self-digest trust was removed; schema 6 now requires a separately reconstructed clean Git/docket context |

The rejected artifacts and findings remain in history. No passing local suite overrides them.

## Final candidate design

- Strict portable relative paths reject Windows drives/reserved names/ADS, empty/current/
  parent segments, backslashes, and trailing dots/spaces.
- Date-times are calendar-valid RFC 3339 with explicit offsets; resource numbers are finite;
  exact digests have fixed lengths.
- Runtime validation independently recomputes canonical tool-intent digests and binds action,
  receipt, mission, state, role actor, policy, lease, and a distinct verifier.
- The tracked GPT fingerprint covers the complete strict manifest and committed LF bytes.
- The governed `SRC-023` manifest binds raw inventory and adjudication metadata and rejects
  re-digested changes to relationships, image independence, custody, and obligations.
- Unresolved licenses, unverified digest labels, incomplete provenance/ingestion, and every
  repository-bearing kind machine-block dependent claims.
- CurrentStateAudit schema 6 derives blockers from source metadata and reconciles issues,
  coverage, claim mappings, maturity, evidence classes, readiness, and inventory.
- A schema-6 artifact cannot verify from its own digest. `AuditVerificationContext` is
  independently reconstructed from a clean Git worktree and binds HEAD, tracked-tree digest,
  full docket inventory digest/counts, and a canonical source/claim-maturity projection.

## Local acceptance evidence

- Clean detached worktree at exact `f71e37934f86bdf45030cfa1fff4203445a1a87c`.
- Python 3.14: `133 passed, 1 skipped, 1695 subtests passed`.
- Fresh installed wheel on Python 3.12: `Ran 134 tests`, `OK (skipped=1)`.
- Ruff 0.16.0: all checks passed.
- Pyright 1.1.411: zero errors and warnings.
- Wheel: `hive_mind_os-0.6.0-py3-none-any.whl`, 92,448 bytes,
  `sha256:4ec611ebdebb4e9f042b13391a0c9182a67ee7882d6043cd8d3b60ece605b47e`,
  containing all eleven schemas.
- Tracked GPT fingerprint:
  `sha256:0314976c7acee4a56611682cf27dc36bc000f50267e26a1fb387229a0c7bdbbf`.
- Governed `SRC-023` inventory:
  `sha256:9d55be7e5d4e18fc77473e50afe8cb17dccb4e866f3c24317d300e1594455369`.
- Regression matrix covers each prior counterexample, coordinated blocker clearing,
  zero-inventory deletion, fabricated source/claim identity, metadata rewriting, maturity
  fabrication, and repository substitution.

The single Windows skip is direct symlink creation denied by privilege error 1314. It is not
counted as a passed path.

## Audit and trust boundary

- **Final artifact:** `evidence/audits/current-state-audit-f71e379.json`
- **Artifact digest:**
  `sha256:ea9ee7bcc78f2be6c5fff15137e1fb2f8339902696a3f5623aeaea1bf454a802`
- **Unanchored verification:** rejected with
  `schema 6 audit verification requires a trusted context`
- **Trusted-context verification:** `(True, ())`
- **Docket inventory digest:**
  `sha256:c4f615e7606aafc46779726069f61555aa0ae46377142c92d8bab31e0e3cbcb8`
- **Docket projection digest:**
  `sha256:51a2c91179c76b8a778ec286634c1ebbbfa1d6e3d14a8c9d6e6e3ca0230b6209`
- **Tracked-tree digest:**
  `sha256:fa3c29a8ae3d2f012bac82f7fd946bbf4fd33f4cfecfe8f68b9ecfb86517dbbc`
- **Audit facts:** schema 6, 23 sources, 84 claims, 73 machine-blocked claims,
  20 source blockers, 209 reference receipts, 26 successful commands, zero failures,
  `release_ready=false`, `complete=true`.

The envelope digest proves canonical payload integrity, not author identity or execution.
Test/command claims remain subject to independent reproduction or authenticated external
receipts.

## Governance, authority, resources, and rollback

Read-only GitHub evidence found `rulesets=[]` and HTTP 404 for main-branch protection. Local
CODEOWNERS and desired rules do not prove active host enforcement. No remote rule, push, pull
request, merge, deployment, message, credential, secret, money, or destructive action was
performed.

Work stayed within reversible local A2 authority. No numeric token/compute/cost lease or
expiry was supplied. The implementation used bounded local test/build/audit processes; the
final audit contains 26 command observations and is approximately 188 KB. Resource accounting
is qualitative and cannot support an efficiency claim.

Rollback is additive supersession. Do not delete the raw source snapshot, schemas, docket
records, rejected commits, adverse audits, or this dissent. Any relaxation requires a new
ADR and the preserved counterexamples.

## Remaining blockers

- Final disjoint Curator, lifecycle, and Judge evidence for `f71e379` is absent.
- Seven video sources remain incompletely ingested.
- Original bytes and chain of custody remain missing for several user-supplied sources.
- Multiple external source pins and licenses/reuse grants remain unresolved.
- `SRC-023` authorship, reuse rights, and `imgo.jpg` custody remain unresolved.
- Active GitHub protection and independent approvals are absent.
- Signed identities, durable external append-only storage, complete mediation, production
  operation, customer outcomes, and superiority evidence do not exist.

No Stage 0 release, production, or superiority completion is claimed.
