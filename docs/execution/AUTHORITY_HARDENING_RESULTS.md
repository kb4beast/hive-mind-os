# Authority hardening — what execution actually proved

Node `REAUDIT-1900`. Branch `plan/authority-hardening-v1`, base commit
`4c85ebe`. Host Windows 11 Home 10.0.26200, Python 3.14.4.

This document is written for a future session that must not mistake it for
"the system is now secure". Read [§ What this does NOT establish](#what-this-does-not-establish)
before you read anything else in it.

---

## The verdict

**Hardened, not authenticated. Still `not-ready`.**

Every forgery the A5-900 probes demonstrated is now refused, and every refusal
below was re-derived by running something on this host at this commit — not
read out of a commit message. Thirteen of eighteen tracked rows are CLOSED,
three are PARTIALLY CLOSED, two are OPEN and untouched.

What the plan did not do is give authority an origin outside the process.
`AuthorityRegistry.mint_root` accepts any issuer string an in-process caller
types. This node minted a root declaring

```
issuer        = "owner:Brian Espinosa"
authority_ref = "docs/architecture/HUMAN_AUTHORITY_GATES.md"
```

granting `write`/`push`/`deploy` over path scope `("secrets",)`, received a
**genuinely issued** `CapabilityToken` for `secrets/keys.txt`, handed it to an
authority-bound `EffectGateway`, and the adapter ran. `status=SUCCEEDED`.
Both production paths mint their roots exactly that way
(`local_execution.py:215`, `mission_adapter.py:151`).

The plan raised the bar from *"construct a dataclass"* to *"call the mint
ceremony with a string"*. That is a real, measured improvement: the two retained
probes recorded **eleven** `[FINDING]` rows between them, and **ten of the
eleven are now refused**. The eleventh — `P2.1`, self-issuing a delivery grant
against the unanchored module-level ledger — **still succeeds verbatim**. It is
not the audited code boundary acceptance criterion 4 asks for, and calling it
one would be exactly the inflation A5-900 warned against.

---

## The findings matrix

Machine-readable at `evidence/audits/authority-hardening/findings-matrix.json`.
"Test that bites" means a test in the mandated run that fails if the fix is
removed — the implementing nodes each recorded mutation evidence for these; the
column here names the test, and the mandated suite is the run that exercised it.

### From `evidence/pilots/a5/audits/authority-boundary.json`

| ID | Finding | Status | Measurement | Test that bites |
|---|---|---|---|---|
| **A5-F3** | Envelope digest is an identifier, not a seal | **CLOSED** | `P1.9b`: `mint_root(b)` while `b` wears `a`'s digest → *"envelope digest does not seal its contents"*. `a`'s digest still resolves to `a`'s narrow authority. | `test_registry_refuses_an_envelope_whose_digest_is_not_its_content_digest`, `test_two_authorities_cannot_share_one_digest` |
| **A5-F4** | A fresh ROOT can be minted in-process with any authority | **PARTIALLY CLOSED** | `P1.5`: `register(fresh_root)` → *"root envelope requires an explicit mint ceremony"*. **But `P7.1`**: `mint_root` authenticates nothing; a self-minted root in the owner's name executed on `secrets/keys.txt`. | `test_bare_root_registration_is_refused_and_the_ceremony_records_provenance`, `test_ceremony_refuses_an_unattributed_or_undated_mint` |
| **A5-F5** | Revocation keyed by digest string | **PARTIALLY CLOSED** | `P1.8b`: re-mint under a new digest, same `authority_key` → *"authority is revoked"*. `P1.8c`: descendant of a revoked parent refused. `P3.3b`: bound gateway refuses a pre-revocation token. **But `P3.3c`**: an *unbound* gateway spent that same token after revocation. | `test_revoked_authority_cannot_be_reminted_under_a_new_digest`, `test_revoking_a_parent_refuses_its_already_admitted_descendant`, `test_revoked_envelope_is_refused_after_a_legitimate_issue` |
| **A5-F6** | `DeliveryGrant` is self-issuable | **PARTIALLY CLOSED** — closed in fixtures, **open in a real run** | On a bare import `grants.LEDGER.anchor_digest == ''`. The verbatim `P2.1` payload **still succeeds**, recorded `issuer='self-issued'`. Anchored, `P2.1b` refuses it. **0 `.anchor(` sites in `src/**`; 10 in `tests/**`.** | `test_a_self_issued_grant_is_refused_once_the_owner_authority_is_anchored`, `test_self_issuance_is_refused_outright_while_an_anchor_stands`, `test_a_fabricated_owner_authority_record_is_refused` |
| **A5-F10** | The effect boundary never consults the registry | **CLOSED** | `P3.1` (verbatim) refused at construction. `P3.1b/c` — the same forgery rebuilt at the **slot level** so construction cannot catch it — refused by the boundary on both gateway shapes. `P3.2/P3.2b`: `adapter_calls unbound=[] bound=[]`. `P3.7`: the outbox refuses it too. | `test_hand_built_token_for_an_unissued_envelope_is_refused`, `test_token_outside_the_envelope_scope_is_refused`, `test_durable_gateway_refuses_a_forged_token_before_it_is_recorded`, `test_a_token_no_registry_issued_cannot_be_constructed` |
| **A5-F11** | Only `write` is target-scoped | **CLOSED** | `P4.1`: `push` to the same out-of-scope target → *"target is outside write scope"*. | `test_a_non_write_action_is_refused_outside_the_write_scope`, `test_a_read_action_is_bound_to_the_read_scope` |
| **A5-F12** | `is_no_broader_than` omits the spend ceiling | **CLOSED** | `P5.1`: `is_no_broader_than -> False`; `register` refused. Still LATENT — nothing in `src/**` spends against `max_cost_microunits`. | `test_registry_resolved_parent_still_refuses_a_broadening_child` |
| **A5-F13** | Caller-supplied parent the registry never saw | **CLOSED** | `P6.1`: → *"parent envelope is required"*; the child does not authorize. | `test_caller_supplied_parent_the_registry_never_admitted_is_refused` |
| **A5-F14** | `network_allowlist` enforced nowhere | **CLOSED at the effect boundary** | `P3.6`: bound gateway → *"effect reaches a host outside the network allowlist: api.github.com"*. `P3.6b`: unbound gateway refuses any network-declaring adapter. | `test_effect_reaching_a_host_outside_the_allowlist_is_refused`, `test_network_effect_requires_an_authority_bound_gateway` |

### From `evidence/pilots/a4/summary.json`

| ID | Defect | Status | Measurement |
|---|---|---|---|
| **D1** | Receipt written after the irreversible effect; no long-path handling | **CLOSED (both halves)** | `tests.test_mission_store` 66 OK (write-ahead record, MAX_PATH temp naming, component limit, receipt adoption without re-execution); `tests.test_github_adapter` 51 OK (interrupted PR / push reconciled, unwitnessed effect refuses to re-fire, receipts written and validated beyond MAX_PATH) |
| **D2** | `find_open_draft_pr` does not encode its query | **CLOSED** | `rest_gateway.py:160` uses `urlencode`; `test_find_open_draft_pr_encodes_its_query_parameters` |
| **D3** | `list_comments` does not paginate | **CLOSED** | `rest_gateway.py:196-205` paginates, stops on a short page, bounded at 50; `test_a_comment_marker_beyond_page_one_is_found_and_not_reposted`, `test_a_short_first_comment_page_ends_the_read` |
| **D4** | `DeliveryGrant` has no expiry | **CLOSED** | `P2.7`, **both directions**: one second past `expires_at` refused; before it, allowed. A one-sided check would have been vacuous. |
| **D5** | `EffectIntent.intent_digest` never verified to seal its fields | **CLOSED** | `P3.4`/`P3.4b`: an unsealed intent presented with a **genuinely issued** token is refused on the bound gateway *and* the unbound one. The second half is what the `4c85ebe` repair added; measured, not assumed. |
| **D6** | The gateway has no ref-read method | **CLOSED** | `rest_gateway.py:269` `read_branch_ref`, carrying the same `_branch_ref` guard as the delete path; four tests |
| **D7** | No remote receipt cites the sealed plan digest | **OPEN — untouched** | 7 JSON files in `evidence/pilots/a4/remote/`, **0** contain `plan_digest`. `pilot-plan.json` still reads `pilot_repository: "UNGRANTED"`, `authority_gate.status: "CLOSED"`. |

### From A3

| ID | Finding | Status | Measurement |
|---|---|---|---|
| **F3** | `verify_bundle` never reads the recorded verdict | **CLOSED for schema-v2 bundles** | `_verify_verdict` called at `verify.py:324`, defined at `:1031`. `tests.test_verify` 22 OK (skipped=1). |
| **F2** | `workers.py:155` `_canonical_bindings_provider` is `None`, so jobs dead-letter | **OPEN — untouched, verified still open** | On a bare import it is `None`. `set_canonical_mission_bindings_provider` appears **once** in `src/**` — `workers.py:158`, its own definition. Only callers anywhere are in `tests/test_hive_cortex_cli_migration.py`. `workers.py:209` is the refusal the canonical route raises. |

### `DAG_EXECUTION_HANDOFF.md` §11

| Item | Maps to | Status |
|---|---|---|
| 1 — `validate_capability_token` authenticates nothing | A5-F10 | CLOSED, with the in-process key residual named below |
| 2 — `verify_bundle` never reads the verdict | A3-F3 | CLOSED for schema-v2, unkeyed |
| 3 — receipt after the irreversible effect | A4 D1 | CLOSED both halves, liveness trade-off named |
| 4 — the lower-severity list | F11, F12, F14, D2, D3, D4, D5, D6 | all CLOSED |
| 5 — containment unproven on Windows | SANDBOX-1300 | CLOSED, and **load-bearing on exactly one test** — see below |
| 6 — the authority chain is unsigned | — | **DELIBERATELY OUT OF SCOPE, an owner decision.** Unchanged: four `N` and one `E` over `HUMAN_AUTHORITY_GATES.md`; this plan's own nine commits are all `N`. Recorded as such, not as a failure of this plan. |

---

## How this was measured

Nothing here is adopted from a commit message. The probe sources live in this
session's scratchpad — never in the repository — and are retained verbatim
inside each transcript, the way the A5 transcripts do it.

| Transcript | What it is |
|---|---|
| `evidence/audits/authority-hardening/probes/reaudit_probe1.txt` | The retained A5 probe 1, adapted setup, attack payloads byte-identical |
| `.../reaudit_probe2.txt` | The retained A5 probe 2 at the effect boundary, plus the P7 residual block |
| `.../reaudit_probe3_sandbox.txt` | Traced coverage of the Windows containment guard |
| `.../reaudit_probe4_residuals.txt` | The seven declared residuals, A3-F2, A4 D7, §11.6 |
| `.../orch_probe_token.txt` | The orchestrator's own probe, run **unmodified** |
| `evidence/audits/authority-hardening/tests/mandated-suite.txt` | The nine mandated modules, one run |

### A refusal is not a refusal unless it is the *right* refusal

`REG-1000` added two new preconditions — envelopes must seal their own
contents, and roots may only enter through `mint_root` — that fire **before**
several of the retained attacks reach the control they were written to test.
Scoring those as "closed" would have been wrong. Where it happened, the
verbatim attack is recorded as *refused by an unrelated precondition* and a NEW
measurement isolates the original control:

- `P1.9` is refused by the root-ceremony rule → `P1.9b` isolates the **seal**.
- `P1.8` is refused by the root-ceremony rule → `P1.8b` isolates **revocation**.
- `P3.1`'s hand-built token now fails at `CapabilityToken.__post_init__`, i.e.
  in `authority.py`, not at the effect boundary → `P3.1b/c` rebuild the same
  forgery at the **slot level** so the boundary itself has to refuse it.

Probe 2's recorder reports `CRASHED` as a third outcome distinct from `DENIED`
for the same reason.

### Setup changes, stated precisely

Only setup was changed. Every attack payload is byte-identical unless the
constructor signature itself changed.

**Probe 1**
- *SETUP CHANGE 0* — added a `MINT` dict supplying `issuer` / `authority_ref` /
  `recorded_at`. `mint_root` did not exist at the A5 base commit.
- *SETUP CHANGE 1* — `narrow = envelope(D1, ...).sealed()`; `D1 =
  narrow.digest_value`; `registry.register(narrow)` → `registry.mint_root(narrow,
  **MINT)`. `_admit` refuses a digest that is not the content digest, and
  `register` refuses a parentless envelope. `D1` is **rebound** rather than the
  attack lines rewritten, so every later attack line is textually unchanged.
- *SETUP CHANGE 2 / 3* — two bare `register(...)` statements were routed through
  the recorder. They now raise, and a bare raise aborts the probe. The payloads
  are unchanged; only the recorder around them is new.
- *SETUP CHANGE 4* — `P2.6`'s `DeliveryGrant(...)` grew from 8 positional
  arguments to 11, the three new ones (`expires_at`, `issuer`, `authority_ref`)
  copied verbatim from the grant under test. `GRANT-1020` added three sealed
  fields, so the original call is now a `TypeError` — a crash, which must never
  be recorded as a refusal. The mutation under test (`issued_at` rewritten to
  `2026-01-01T00:00:00Z`) is unchanged.

**Probe 2**
- *SETUP CHANGE 1* — identical to probe 1's.
- *Reorganisation* — the retained probe 2's `P4`/`P5`/`P6` sections were
  re-homed into probe 1 (as NEW 3/4/5) because they are registry-level and probe
  1 already carries the registry setup. Attack payloads unchanged. **A reader
  looking for `P4.1` will find it in `reaudit_probe1.txt`.**

---

## Test numbers actually observed

One run, start to finish, in one process:

```
PYTHONPATH=src python -m unittest tests.test_brain_kernel_authority \
  tests.test_hive_cortex_effects tests.test_delivery_grants \
  tests.test_github_adapter tests.test_verify tests.test_mission_store \
  tests.test_sandbox tests.test_hive_cortex_delivery \
  tests.test_hive_cortex_durability -v

Ran 273 tests in 567.457s
OK (skipped=2)          exit 0
```

| Module | Tests |
|---|---|
| `tests.test_mission_store` | 66 |
| `tests.test_github_adapter` | 51 |
| `tests.test_sandbox` | 40 |
| `tests.test_hive_cortex_delivery` | 23 |
| `tests.test_verify` | 22 |
| `tests.test_delivery_grants` | 22 |
| `tests.test_hive_cortex_durability` | 21 |
| `tests.test_hive_cortex_effects` | 16 |
| `tests.test_brain_kernel_authority` | 12 |
| **total** | **273** |

Both skips, with their real reasons:

- `test_rejects_symlink_candidate_layout_when_supported` — *symlink creation
  unavailable: [WinError 1314] A required privilege is not held by the client*
- `test_symlink_escape_is_rejected` — *POSIX-only symlink confinement case*

The orchestrator ran the repository-wide suite separately. **This node did not**,
so nothing here is a claim about the whole repository.

---

## Every residual, verified rather than trusted

Each implementing node declared a residual. All seven were re-derived here.
All seven are real.

**1. `grants.LEDGER` is anchored by no production path.** `'.anchor('` call
sites: **0 in `src/**`, 10 in `tests/**`** (`test_delivery_grants` ×8,
`test_github_adapter:1169`, `test_hive_cortex_delivery:223`). On a bare import
`anchor_digest` is `''`. **A5-F6 is closed in the fixtures and open in a real
run.** Do not round this up: the probe's original self-issuance attack still
succeeds against the module-level ledger, producing a usable five-action grant
naming an owner and repository the repository owner never named.

**2. `effect_outbox.py` still makes `reconciliation_required` terminal.** Nine
raise/mark sites inside `DurableEffectOutbox.execute`, no branch that clears the
state. `mission_store` has its own non-terminal route; the outbox does not.

**3. A claimed effect can never re-fire.** `GitHubClient._reconcile_interrupted_effect`
raises `GitHubEffectReconciliationRequired` when there is no write-ahead record,
and again when the observer is absent or returns `None`. It never calls
`operation()` again. **An effect that provably never reached the remote wedges
the mission permanently.** That is the safe direction for an irreversible remote
effect and it is still a liveness defect. Clearing it needs an observer contract
that can prove absence.

**4. The verify digest chain is unkeyed and unanchored.** `verify.py` contains
no `hmac` and no `sign`/`signature`. `ledger.py` contains no `hmac` and uses
plain `sha256` in three places. A retained bundle proves integrity **relative to
its own evidence**, not authorship. Whole-bundle reconstruction by anyone with
write access to the directory is still possible. Same class as §11.6.

**5. The containment proof rests on a single test.** Traced, on this host:
`sandbox.py:487` (`resolved.relative_to`) is executed by 2 of 40 tests;
`sandbox.py:491`, the *"path argument escapes sandbox root"* refusal, is executed
by **exactly one** — `test_windows_junction_escape_is_rejected`. The POSIX case
skips. **Delete that one test and the original Windows blind spot returns
silently, with a green suite.**

**6. The two retained A3 bundles have never been self-verifiable.** Both:
`schema_version 1`, 10 files listed, **5 absent**, including `ledger.sqlite3`.
`verify_bundle` now refuses both with *"integrity manifest schema is
unsupported"* — it never even reaches the missing files. Pre-existing A3
evidence defect; **not caused by this plan and not fixed by it**.

**7. `tests/test_workers` cannot be imported under plain unittest.** Exit 1,
`ModuleNotFoundError: No module named 'fixtures'` — `tests/test_workers.py:13`
does `from fixtures.fixture_repo import ...`, which needs `tests/` on
`sys.path`. Pre-existing.

---

## What this does NOT establish

Read this section before quoting any other part of this document.

- **It does not establish that authority originates outside the process.**
  `mint_root` records an issuer string; it authenticates nobody. `P7.1` minted a
  root in the owner's name, with the owner's authority document as its
  `authority_ref`, and spent it to completion on `secrets/keys.txt`.

- **It does not establish any cryptographic property.** There is no key an
  attacker does not also hold, and no signature anywhere in this plan. The
  envelope seal, the grant digest, the intent seal, the bundle manifest and the
  ledger chain are all plain `sha256` over their own contents. **They detect
  edits. They do not attribute authorship.** The one "keyed" construct — the
  `CapabilityToken` issuance witness — uses a module-level key any in-process
  caller can read: `P7.3` read `authority._ISSUANCE_KEY`, computed the witness by
  hand, and the resulting token constructed *and executed*. This is attribution
  by record within one process. It stops a forged token crossing a module
  boundary. It does not stop code already running in the process.

- **It does not establish that an in-process caller cannot obtain authority.**
  It can, three measured ways: mint its own root (`P7.1`), read the issuance key
  (`P7.3`), or self-issue a delivery grant while the ledger is unanchored
  (`P2.1`).

- **It does not establish that the delivery grant boundary holds in a real
  run.** It holds in the fixtures. No production path anchors the ledger.

- **It does not establish that an *unbound* gateway is safe.** `P3.3c` and
  `P3.5b`: an unbound `EffectGateway` executed a genuinely issued token whose
  envelope was **revoked**, and another whose envelope had **expired**. An
  unbound gateway checks only that *some* registry in this process issued the
  token — never which one, never whether it still stands. Mitigating and
  measured: neither production construction site is unbound today
  (`local_execution.py:219`, `mission_adapter.py:155`, both `authority=`;
  confirmed independently by the orchestrator's probe). It is a supported public
  API, so this is latent, not absent.

- **It does not establish robust Windows containment.** One test.

- **It does not establish that the retained A3 and A4 evidence is sound.** Both
  A3 bundles fail verification. No A4 remote receipt cites the sealed plan
  digest.

- **It does not establish that the repository-wide suite passes.** Nine modules
  were run here.

- **It says nothing about behaviour against a real remote.** Every measurement
  is in-process, with fake adapters, no network and no credential.

---

## What could not be measured here, and why

Stated rather than estimated. A plausible-looking number nobody ran would be
worse than its absence.

- **Whether an owner-anchored grant ledger holds in a real deployment** — no
  deployment path exists to anchor it, so there is nothing to run.
- **Whether the reconciliation wedge (residual 3) occurs in practice** — it needs
  a real interrupted remote effect, which needs a credential and a network,
  neither of which this node may use.
- **Whether the two retained A3 bundles ever verified** — the five absent files,
  `ledger.sqlite3` among them, are not recoverable from what is committed.
- **Cross-process and post-restart behaviour of the issuance key and the grant
  ledger** — both are process-local by construction, so a single-process probe
  cannot exercise the boundary they lack.
- **GPG signature validity beyond git's own `%G?`** — no keyring is configured on
  this host, so `N` means "no signature recorded", which is the fact reported.

---

## In the order they should be fixed next

1. **Give `mint_root` an external authenticator.** Everything else on this list
   is downstream of it. A root the running process can mint is not a root. This
   is `B-GOV-02` and it is the same missing thing as §11.6 seen from the other
   direction — an unsigned authority document and an unauthenticated mint
   ceremony fail together.
2. **Anchor `grants.LEDGER` on a production path.** The mechanism exists and is
   tested; nothing calls it. Until something does, A5-F6 is open in every real
   run.
3. **Make `authority=` mandatory, or make the unbound path refuse a stale
   token.** `P3.3c` / `P3.5b`.
4. **Give the reconciliation path an observer that can prove absence**, so a
   never-fired effect stops wedging a mission (residual 3), and give
   `effect_outbox` the non-terminal route `mission_store` already has
   (residual 2).
5. **A3-F2** — register a canonical bindings provider, or delete the route.
6. **A4 D7** — evidence-chain only. Re-sealing the plan now would be back-dating
   a seal, so it was deliberately not done.

---

## The rule this node was held to

**Repair nothing. A finding the measurement still reproduces is recorded OPEN.**

This node changed no code, fixed no defect, and ran no state-changing git. Three
rows would have been more comfortable rounded up to CLOSED — A5-F4 on the
strength of `register()` now refusing bare roots, A5-F5 on the strength of the
bound gateway, A5-F6 on the strength of the fixtures. Each is recorded PARTIALLY
CLOSED because a command run on this host reproduced the residue.

A5-900 adjudicated `not-ready` and was right to. Its own record put the reason
best: a readiness record produced without executing anything would have found
none of the six production defects that execution found, and would have reported
a sound authority boundary. That remains the standard. The point of this node was
to be accurate, not to be positive.
