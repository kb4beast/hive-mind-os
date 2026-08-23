# Curator receipt: CONTINUATION-3060

## Identity and candidate binding

- Curator identity: independent of the Builder.
- Candidate commit: `5de1d5706f01ce219f6d5e55198e2e4f8a23ceff`
- Candidate tree: `930952d65a1a0edc2596a879ac39adddf6cdf7a8`
- Candidate parent: `ff0f47a94c01f36df2594d6e82df27a636a0149f`
- Builder receipt audited: `90ecde4d983c7b531f00d2a0b4aac90d32fddeb3`, `evidence/audits/authority-hardening-successor/builder/CONTINUATION-3060-5de1d57.md`.
- Audit start state: source, tests, ADR, and `AGENTS.md` were identical between
  the candidate and the receipt commit; that latter commit adds only the Builder
  receipt. The working tree was clean before this append-only receipt.

## Curator disposition

**ADAPT — narrow local inspection/dispatcher handoff only; do not mark
`CONTINUATION-3060` complete or promote any authority.**

The candidate is locally sound for the limited claim that its default path uses
one fixed continuation text and a PowerShell argument array, re-observes the
installed control plane, and contains no direct credential, raw-GitHub-write,
merge, deploy, spending, policy-mutation, or root-minting call. Both inspection
and `-Apply` against the currently stale control plane withheld a dispatcher
release and left the worktree unchanged.

It is not eligible for an `ADOPT`/complete disposition: the live blocked
`-Apply` result exits zero and prints `CONTINUATION APPLIED` rather than a typed
refusal, while its JSON reports an invalid stale dispatcher release. In addition,
the exposed `RepoRoot` and `Actor` inputs mean the complete invoked argument set
and provenance identity are not fixed or repository-bound. The successor DAG
does not yet contain a `CONTINUATION-3060` node, dependencies, or completion
criterion, so this receipt cannot advance a DAG state.

## Independent reproduction

| Command | Result |
| --- | --- |
| `git diff --no-ext-diff --check 5de1d57^ 5de1d57` | PASS — no whitespace error. |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_preauthorized_continuation tests.test_brain_kernel_authority tests.test_autopilot_workflow -v` | PASS — 39 tests, 1 Windows symlink-capability skip. |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s .autopilot/tests -p test_orchestration.py -v` | PASS — 24 tests, 1 Windows symlink-capability skip. |
| `python -m ruff check tests/test_preauthorized_continuation.py` | PASS. |
| PowerShell AST parse of `scripts/Invoke-PreauthorizedContinuation.ps1` | PASS — zero parser errors. |
| `powershell -NoProfile -File scripts/Invoke-PreauthorizedContinuation.ps1` | PASS — live inspection observed `WAIT`, no eligible nodes, and stale target/reconciliation/snapshot evidence. |
| `powershell -NoProfile -File scripts/Invoke-PreauthorizedContinuation.ps1 -Apply` | Exit 0; no dispatcher release and no worktree change. It reported stale target/reconciliation/snapshot evidence but then printed `CONTINUATION APPLIED`. |

The two live commands ran with `PYTHONDONTWRITEBYTECODE=1`; status before and
after the `-Apply` probe was identical. The stale controller target reported by
the probe was `release/hive-mind-os-singleton-20260812-r5` at
`b22dd33c1e94fbca22da68512e8da3839e8cb02d`; therefore no stale release was
reused or published, but live continuation is presently blocked rather than
completed.

## Static authority audit

1. `scripts/Invoke-PreauthorizedContinuation.ps1:40-53` constructs a constant
   request and an argument array, then calls Python with `& $python @arguments`.
   It has no caller-supplied request or shell-evaluation path. Static test and
   source review found no credential, `git push`, merge, deploy, execution-policy,
   or root-authority operation.
2. The launcher does not name `ARCH-100` or the former singleton branch. It
   resolves a root, checks that its `.autopilot/bin/autopilot.py` exists, and asks
   that control plane to observe live status before `--apply` can reach
   `plane.dispatch`.
3. `.autopilot/bin/orchestration.py:846-861` withholds publication when
   reconciliation is required, work is active/recovering, a release is already
   valid, or the eligible set is empty. The live adverse `-Apply` probe exercised
   the first and last refusal conditions; no `dispatch` call occurred.
4. `ADR-066:34-40` expressly retains the external-root boundary. No source,
   test, receipt, or live result supplies external verifier custody, rotation,
   revocation, deployment, rollback, or independent witness evidence.

## Dissent and required repair

1. `scripts/Invoke-PreauthorizedContinuation.ps1:3-5,28-45` accepts a caller
   `RepoRoot` and `Actor`, forwarding both to the Python control plane. A path
   containing any Git repository and `.autopilot/bin/autopilot.py` passes the
   local checks; `Actor` is only portability-validated and becomes dispatcher
   release provenance. This is an unbound repository/provenance gap, not a
   demonstrated raw-write or root bypass. Bind the launcher to its own repository
   identity (and expected controller digest) and make the dispatcher actor a
   constant or independently authenticated value.
2. `scripts/Invoke-PreauthorizedContinuation.ps1:60-63` unconditionally emits
   an `APPLIED` success message when `-Apply` was requested. The independent
   probe proves that a stale/no-eligible result instead exits zero with that
   message. Return a typed withheld/refused outcome and non-success exit status,
   or change the protocol and tests so no caller can mistake non-publication for
   a completed continuation.
3. The focused test only makes string assertions. It does not exercise a
   foreign `RepoRoot`, actor-provenance spoof, or the stale `-Apply` output.
   Add adverse runtime tests for all three before a new Curator review.
4. `CONTINUATION-3060` is absent from
   `docs/plan/authority-hardening-successor-2026-08-22/plan.json` and `PLAN.md`.
   A Builder receipt alone supplies no DAG ownership, dependency, authority
   boundary, or Judge path.
5. ADR-066 requests full `python -m unittest discover -s tests -v`; this Curator
   did not independently rerun that complete repository gate. No remote CI result
   is used as a substitute.

## Explicit non-claims and rollback

This review does **not** unblock or satisfy `ROOT-3000`, external-root custody,
promotion, raw delivery, protected merge, deployment, spending, credentials, or
policy mutation. It does not change any plan/promotion state.

If the candidate is repaired, revert or replace the launcher, ADR-066, its tests,
and the `AGENTS.md` directive together; retain this receipt and the Builder
receipt as dissent/provenance. A new exact-head Curator and independent Judge
review are required after repair.
