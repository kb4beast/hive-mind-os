# Court case: ADR-067 DAG Standard V2 prerequisite

## Clerk record and source custody

- Case ID: `CASE-ADR-067-DAG-STANDARD-V2`
- Base commit inspected: `44224532dc25b94a95c3184054ec81762a258259`
- Original V1 standard source: `docs/execution/DAG_AUTHORING_STANDARD.md`, Git blob
  `70e43b0a8078a303d44c0109b8dd218a948258c2`; it is preserved, not amended.
- Quarantined candidate context: the uncommitted directory
  `C:\Users\beesp\.codex\worktrees\5ff0\hive-mind-os\docs\execution\dags\generic-hive-mind-product-v2`
  at source-worktree commit `44224532dc25b94a95c3184054ec81762a258259`.
  It is not present in that commit tree. The inspected `generate_plan.py` raw SHA-256
  was `72516eab60215d4c0a3cafec52732246ce1c45514f28da43aeec2c44ac46d45f`.
  Its uncommitted status is retained as provenance, not represented as a committed
  source. This prerequisite does not edit it.
- Compiler/source evidence: `.autopilot/bin/dag_standard.py` at the base commit and
  the installed `autopilot.py` dispatch parser. No external source, license, credential,
  or network capability was used.

## Atomic claims and adverse evidence

1. Prose/lock inference classifies durability providers without a typed contract and
   can treat generic executor/public-runtime objectives as providers.
2. The exact task-to-descendant-provider graph can create a semantic edge opposite a
   raw dependency; the former rank cap can return an invalid schedule.
3. Optional plan/node seals were not checked by generic lint/round consumption. Internal
   self-consistency alone also cannot reject a substitute whose seals were recomputed; a
   caller-supplied expected digest is needed to bind consumption to a manifest/contract.
4. The installed dispatcher does not parse `dispatch --plan`, so an external-plan shell
   command was a false execution claim.
5. The V1 standard and overlay are historical sealed evidence and must remain byte-for-byte
   reproducible.
6. A typed `none` declaration that carries a durability or external-effect semantic lock is
   a contradictory machine contract and must not be admitted through prose-only checking.
7. A compiler that normalizes away duplicate declarations, malformed dependency values, or
   unknown dependency IDs can emit a schedule for a graph that was never actually declared.
8. A direct compiler API must not let a caller inject an executable command while the same
   plan is reported as `manual-parent-v1`; command availability and mode share one boundary.

## Participants and separated testimony

| Court role | Identity | Receipt / conclusion |
| --- | --- | --- |
| Clerk / Orchestrator | `/root` | Scoped this to a generic compiler/standard successor; excludes plan-specific overlay edits and public runtime implementation. |
| Builder | `/root` | Implemented only the bounded compiler, tests, V2 standard, ADR, and this record; cannot approve the result. |
| Advocate | `/root/advocate` | Recommended `ADAPT`: typed roles, combined graph, canonical seals, manual-parent external rounds, and preserved V1 bytes. |
| Cross-Examiner | `/root/cross_examiner` | Found the exact task-to-generic semantic cycle, seal substitution gap, and false `--plan` command; required fail-closed handling. |
| Expert Witness | `/root/expert` | Specified complete canonical material, one-read consumption, typed provider IDs, deterministic cycle detection, and truthful integrity states. |
| Explorer | `/root/explorer` | Independently verified V1 blobs, quarantined-source provenance, and the lock/receipt blockers; no external source or license obligation was invented. |
| Architect | `/root/architect` | `REPLAN_REQUIRED` on the earlier candidate: topology preflight must inspect original declarations before typed validation; supplied migration, rollback, and threat receipt. |
| Integrator | `/root/integrator` | `DEFER` on the earlier candidate: found direct compiler topology bypass and a command/mode mismatch; bounded compatibility remedy implemented. |
| Steward | `/root/steward` | `REPLAN_REQUIRED` on the earlier candidate: confirmed all silent-loss paths, retained invalidated CI evidence, and specified recovery controls. |
| Optimizer | `/root/optimizer` | `DEFER` on the earlier candidate: supplied negative controls, outcome metrics, rejected alternatives, and the exact next-payload hash algorithm. |
| Curator | `/root/curator` | First fresh review blocked `edcd…894365` on the direct command/mode P1. Replacement review matched `181e…c3fb9`, verified all five P1 closures, reran 106 focused tests (0 failures/errors, 0.231s), and passed protected-byte/diff checks. No Curator blocker. |
| Judge | `/root/judge` | Final `ADAPT`: independently recomputed `181e…c3fb9`, reproduced 106 focused tests and protected-byte/diff checks, accepted the qualifying full-CI receipt, and found all five P1 closures adversarially covered. |

## Decision under review

Disposition: **ADAPT** — bounded compiler/standard amendment approved for commit; no
external runtime, external dispatch, or overlay implementation is promoted.

The candidate introduces V2 `durability_role` / `durability_providers` semantics,
validates all present canonical seals from one byte snapshot, compares an optional
caller-provided expected digest to that exact snapshot, constructs and checks a combined
prerequisite graph, replaces the arbitrary relaxation cap with a topological walk plus
emitted-round postcondition, and returns manual-parent structured external rounds without
an impossible command. Integrity status (`verified-sealed`, `partially-sealed`, or
`digest-unsealed`) is reported separately from durability mode (typed or legacy
heuristic); a sealed plan may legitimately use legacy durability inference and an
unsealed plan may legitimately use typed durability semantics.

The corrected candidate additionally preflights each original declaration before typed
validation or round compilation: raw dependencies must be a list of non-empty unique
string IDs and must resolve to known non-self nodes; duplicate node declarations are
rejected before a normalized map can hide them. Typed `none` fails when a
machine-significant durability or external-effect semantic lock is present. These checks
are deliberately narrow: typed provider/consumer roles retain precedence and legacy
heuristics are unchanged for valid untyped plans.

It also derives direct API command availability and execution mode from one plan boundary:
an external plan cannot receive a caller-supplied command, and a caller cannot override
the derived execution mode. This keeps `manual-parent-v1` structured-only in every API
path, not only the CLI adapter.

The alternate proposal to modify V1 prose or its authoring standard is rejected:
it would invalidate `manifest.json`'s pinned V1 blob and would hide, rather than fix,
the classification defect. The no-semantic-ordering escape is rejected as an execution
bypass; it now refuses constrained plans.

## Implementation mapping, acceptance, and rollback

- Architecture: `docs/architecture/ADR-067-DAG-STANDARD-V2-TYPED-DURABILITY-AND-BOUND-CONSUMPTION.md`.
- Normative successor: `docs/execution/DAG_AUTHORING_STANDARD_V2.md`.
- Code: `.autopilot/bin/dag_standard.py`.
- Acceptance: focused DAG-standard suite; self-consistent substitute succeeds under
  internal seals alone but is rejected by both commands when passed the trusted expected
  digest; full `python -m unittest discover -s tests -v` in a child environment with
  only inherited `GIT_PAGER` removed; independent Curator reproduction and Judge
  disposition.
- Outcome metrics: zero emitted cycles/order violations; a digest mismatch produces no
  lint/round result; external output contains no false `dispatch --plan`; V1 standard
  and all six V1 source blobs match pinned bytes; malformed/duplicate/unknown raw graph
  material and typed-`none` semantic locks produce no schedule.
- Rollback: revert this bounded candidate atomically. Do not alter V1, the sealed plan,
  either generic-product overlay, retained cycle evidence, or the quarantined candidate.

## Dissent and retained limits

Typed roles make classification deterministic but cannot prove their real-world semantic
truth. Internal seals and a matching caller digest prove equality to supplied bytes, not
authentication of the caller or manifest. The compiler binds the exact bytes it parsed in
one invocation but cannot make a path immutable after that read. `manual-parent-v1`
communicates a bootstrap limitation; it is not native external execution, authority, or a
substitute for `PUBLIC-RUNTIME-500`.

## Validation-integrity receipt

The initial full-suite process was started at `2026-08-23T01:50:56-05:00` (Python PID
`28980`). It cannot qualify this candidate: the compiler, tests, and V2 standard were
last modified at `01:54:35`, `01:54:49`, and `01:54:59` respectively. Its live process
tree was stopped at `2026-08-23T01:57:25.5081263-05:00`; it is retained as an adverse,
invalidated receipt and is not claimed as a pass. The subsequent qualifying process is
started only after the frozen-tree hash, focused validation, and recorded final command;
no files are edited while it runs. Its exact timing/result and the final Judge disposition
are appended before commit.

The second full-suite process, Python PID `77244`, started at
`2026-08-23T02:00:12-05:00` and exited naturally before the requested termination was
received; its tree (including recorded parent session `83236`) had no remaining process
at `2026-08-23T02:20:00.3807592-05:00`. It is an adverse, invalidated timing receipt,
not a qualifying result: independent review found four P1s while it ran (typed `none`
semantic-lock contradiction; unknown dependency filtering; duplicate declaration loss;
malformed dependency normalization). No pass or exit result is claimed for it.

### Superseded frozen implementation payload

At `2026-08-23T01:59:34.9134287-05:00`, immediately before final focused validation,
the deterministic SHA-256 manifest over the implementation and normative-document paths
(UTF-8 relative path, NUL, lowercase raw-file SHA-256, LF; in an order that was not
fully listed) was
`sha256:fdce736513d57f0ec66f49ef76a8cb0707eedb2fadcac08eae15cd4dd59d3ac3`.
The Git binary diff SHA-256 for the tracked subset of those paths was
`sha256:21f4869150dce4c714eeaea7e2e344a7e4829147ce2e07f3af7bb0cd8060418a`.
The receipt file itself is deliberately excluded from this payload manifest to avoid a
self-referential digest. No implementation, test, or normative-document file may change
after this snapshot and before the qualifying full gate completes.

It is superseded by the four P1 corrections. The corrected payload receipt below must
list every included path and order exactly, and fresh Curator/Judge review must bind that
replacement digest before disposition.

### Corrected frozen implementation payload

At `2026-08-23T02:26:27.8775799-05:00`, after the four P1 corrections and before fresh
independent review, the payload manifest was
`sha256:edcd6120a5ecd72d4275336cd513d20602a32f69abc14237f3023ce9ba894365`.
It is SHA-256 over the following exact ordered records, concatenated without a header:
each record is the UTF-8 relative path, one NUL byte, the lowercase SHA-256 hex digest
of that path's raw bytes, and one LF byte.

1. `.autopilot/bin/dag_standard.py` — `1aea76fda485be9e157b6cb3d3ffbfe419664144e9d1acfedb7aec7a5aa82aa8`
2. `.autopilot/tests/test_dag_standard.py` — `a385721dee4e898e06f151f4e4a61678ccf23c0d62df67e82178b4d99b2a52e8`
3. `docs/architecture/ADR-067-DAG-STANDARD-V2-TYPED-DURABILITY-AND-BOUND-CONSUMPTION.md` — `d0d55250f94d9ac4288860c0cf4f5fa1a7d29b334d0bb929289caa2319160f3d`
4. `docs/architecture/ADR_INDEX.md` — `543307390a998ce388eede628c35289d65989a05122eff574b1da1c66106621c`
5. `docs/execution/DAG_AUTHORING_STANDARD_V2.md` — `db709c7d48352fde6a0732e07025134860431d8d63a33d5fcad592d7a3b24b1c`

The tracked-only Git binary-diff SHA-256 is ancillary, not a complete-payload claim:
`sha256:b04d2a7c88f4669eb289297fba46175490de32e17097327b9c992f0fcea48d75`.
The receipt itself is excluded solely to avoid a self-referential manifest. The source
base is `44224532dc25b94a95c3184054ec81762a258259`; status at freeze was the three
modified tracked files above plus this ADR, the V2 standard, and this court receipt as
new files. Focused validation in a child environment with only inherited `GIT_PAGER`
removed passed `105` tests, `0` failures/errors, in `0.224s`; `git diff --check` and
the V1 protected-byte diff also passed. No included payload file may change before the
single fresh qualifying full suite completes.

This payload is superseded before qualification by Curator's fifth P1: an external plan
could receive a supplied direct command while its derived mode was `manual-parent-v1`.
The corrected implementation rejects both a supplied external command and a conflicting
mode; its new adversarial test raises the focused count to 106. A replacement freeze and
fresh Curator/Judge review are required.

### Replacement frozen implementation payload

At `2026-08-23T02:30:19.7622615-05:00`, after the direct command/mode correction, the
replacement payload manifest was
`sha256:181e1dd257a487ed540fa6a26646382a2e7bb48e68013e52ff514a878c6c3fb9`.
It is SHA-256 over these exact ordered records, concatenated without a header: UTF-8
relative path, NUL, lowercase SHA-256 of that path's raw bytes, LF.

1. `.autopilot/bin/dag_standard.py` — `105674faf15aaf7b9f4c9db7ad4003fda404438eed2bf8cc3a1782c1cf321e6a`
2. `.autopilot/tests/test_dag_standard.py` — `63f5690480889aac0c344d84a78c54185e4463af8421ef2e3a6ea3637b400f07`
3. `docs/architecture/ADR-067-DAG-STANDARD-V2-TYPED-DURABILITY-AND-BOUND-CONSUMPTION.md` — `8d2becc7df831855d7d07fa13a33155f7d0f5faf2a7dc877b5d8d173c0d74be2`
4. `docs/architecture/ADR_INDEX.md` — `543307390a998ce388eede628c35289d65989a05122eff574b1da1c66106621c`
5. `docs/execution/DAG_AUTHORING_STANDARD_V2.md` — `3b072fee295e75b8c28709d417f9036fa384e31dc53ca85526babd0881d0e90a`

The tracked-only binary-diff SHA-256 is ancillary, not a complete-payload claim:
`sha256:ef5e17689ec4abd350e21cb8cc5a637a0514e859ac1931601f5c0300887a5ad4`.
The court receipt is excluded solely to avoid a self-referential manifest. The base is
`44224532dc25b94a95c3184054ec81762a258259`; freeze status is the same bounded six-path
change set described above. Focused validation in a child environment with only inherited
`GIT_PAGER` removed passed `106` tests, `0` failures/errors, in `0.247s`; diff and V1
protected-byte checks passed. No included payload file may change before fresh Curator
review and the single qualifying full gate complete.

Curator independently recomputed this exact manifest and passed the five P1 closure
controls at `106` focused tests, `0` failures/errors, `0.231s`. Its review modifies only
this excluded receipt; all included payload paths remain frozen for the qualifying gate.

### Qualifying full-CI and final judgment receipt

The sole qualifying full-suite invocation started at
`2026-08-23T02:32:22.1712613-05:00` in child test PID `21984` (wrapper PID `88800`),
with only inherited `GIT_PAGER` removed. It executed exactly
`python -m unittest discover -s tests -v`; its terminal receipt was written at
`2026-08-23T02:51:05.9471176-05:00`, with exit code `0`. The captured result was
`Ran 1119 tests in 1123.179s` and `OK (skipped=7)`. Standard error contained normal test
output and pre-existing warnings; it did not contain a test failure. The captured output
and error receipt files are retained at the recorded temporary paths during this session:
`C:\Users\beesp\AppData\Local\Temp\hive-mind-adr067-final-ci-20260823-0232.out` and
`C:\Users\beesp\AppData\Local\Temp\hive-mind-adr067-final-ci-20260823-0232.err`.

Immediately after the gate, the five-path manifest was recomputed as exactly
`sha256:181e1dd257a487ed540fa6a26646382a2e7bb48e68013e52ff514a878c6c3fb9`; `git diff
--check` and the protected V1 standard, sealed-plan, and V1-overlay diff checks passed.
No included payload path changed while the gate ran. Judge `/root/judge` independently
recomputed the same manifest, reproduced the 106 focused tests, and issued final
`ADAPT`. This final receipt is the only qualifying CI claim; the earlier PIDs `28980` and
`77244` remain adverse/invalidated evidence.
