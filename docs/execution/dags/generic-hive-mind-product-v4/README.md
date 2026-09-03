# Generic Hive Mind Product V4

Status: candidate, inert, and not authorized to execute or merge.

This directory is the canonical product instance for the subject-neutral portable
DAG runtime. It replaces the abandoned six-file V4 draft with a complete 20-node
plan that can be compiled, inspected, scheduled, and resumed through installed
public interfaces. Host effects remain behind injected adapters and a separately
authenticated one-run capability.

## Exact bindings

- Plan ID: `generic-hive-mind-product-v4`
- Plan SHA-256:
  `sha256:283099b3d74af76c4320043044f763f2067d8c626a0e4e4e390560c1029176c1`
- Candidate base: canonical `main` commit
  `59a5364501c5e49ceb28574aad7a4ac1512291b9`, tree
  `72696b27cdd2c9cd08085c05c98513ece733cc8d`
- Qualified V3 predecessor candidate:
  `ce692c0145d9c7611b34383974fde1c78903c5ef`, tree
  `86e502763fcfd924094ba8194dd0c31b114652a9`
- Predecessor qualification receipt:
  `evidence/audits/generic-v3-baseline-recovery/V3-R4-QUALIFICATION.json`,
  raw SHA-256
  `e4b1a287bb49b961afa4c68ab3849a975853e4b8ebd324bd7761c059cccb51fb`
- Request ID:
  `sha256:3b3cde5568d2cefb2530c266093b80573db5270cc53b54bcd46d284c123a0d9e`
- Repository ID:
  `sha256:48eb2b11cd99bb34f430f5e1c7a39d9a32b9bbaac6a99db4736d2ac422915590`
- Standard: exact raw bytes of `DAG_AUTHORING_STANDARD_V2.md`, version 2
- Compiler: `hive-mind-portable-compiler-v1`
- Topology: 20 nodes, 28 declared edges, 17 dependency levels, and 6 retained
  transitive direct edges
- Source intake:
  `evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json`, raw SHA-256
  `27822617648a04965c17a9f3c4161d71d76521518aa58b5c128f916cb2e89132`
- Complete source archive index:
  `evidence/sources/v4-successor-recovery/SOURCE-ARCHIVE.json`, raw SHA-256
  `908d82cc7bccea22e37eda43eea28d9d363528b20c6b913014b0fb080c07893c`;
  all 13 registered sources have digest-bound, integrity-checked local bytes and zero
  remain unavailable

The predecessor and candidate base are intentionally separate. The V3 commit is
qualified only as an inert `ADAPT` predecessor with its SBOM deficiency carried
forward and corrected in V4. The V4 source branch is an ordinary
direct child of canonical `main`. An activation bundle binds both identities and
cannot substitute one for the other.

Successor regression tests reconstruct the exact R4 object from
`tests/fixtures/generic-v3-r4.bundle`, integrity-checked against the recorded raw
digest and prerequisite in `tests/fixtures/generic-v3-r4.provenance.json`. They do
not copy predecessor payloads from the changing V4 worktree or depend on a mutable
remote branch.

`build_plan.py` is an inert deterministic materializer. Its only permitted write is
an explicit absolute output path supplied with `--output`; without that argument it
writes canonical plan bytes to stdout. It never dispatches a node.

## Installed commands

After installing the package, or with the repository `src` directory first on
`PYTHONPATH`, use explicit absolute paths:

```powershell
$root = (Resolve-Path -LiteralPath '.').Path
$plan = Join-Path $root 'docs\execution\dags\generic-hive-mind-product-v4\plan.json'
$standard = Join-Path $root 'docs\execution\DAG_AUTHORING_STANDARD_V2.md'
$digest = 'sha256:283099b3d74af76c4320043044f763f2067d8c626a0e4e4e390560c1029176c1'
$env:PYTHONPATH = Join-Path $root 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'

python -B -m hive_mind_os.cli dag validate --plan $plan --standard $standard --expected-plan-digest $digest
python -B -m hive_mind_os.cli dag rounds --plan $plan --standard $standard --expected-plan-digest $digest
python -B -m hive_mind_os.cli dag graph --plan $plan --standard $standard --expected-plan-digest $digest
```

`build` writes a canonical copy to an explicit location and refuses to overwrite by
default. `status` integrity-checks the exact plan bytes against the caller-supplied
digest, filters the read-only journal to that plan and subject, rejects a named run from
another binding, and reports an absent journal without creating one.
`prepare-powershell` emits inert, bounded preparation text.
`execute`, `resume`, `cancel`, and `reconcile` deliberately return
`EXTERNAL_RUNTIME_REQUIRED` at the raw CLI boundary: naming a JSON file cannot mint
an `AuthorizedOneRun`.

Programmatic execution uses `SubjectExecutionService` with an injected
`DagExecutor`, authenticated adapters, a durable SQLite `ExecutionJournal`, and an
already verified `AuthorizedOneRun`. The host runtime launches every worker in a
round before waiting, freezes candidate and node deltas, checkpoints successful
siblings, resumes exact identities through stable idempotency keys, and stops on
target drift, hidden dependencies, candidate mutation, integration conflicts,
authority gaps, or ambiguous host effects. Cross-process/global duplicate-effect
exclusion still requires the trusted shared nonce/run journal and adapter-side
idempotency described below. Graph patches are additive, signed, and cannot rewrite
completed history.

## Subject and runtime coverage

The same closed contracts cover repository, offline-local, research-artifact, and
workflow subjects. Resource, capability, adapter, authority, budget, recovery,
integration, evidence, and token policies are separately typed. The plan carries
all eight specialist roles and all seven lifecycle stages. Fixture qualification
covers Python, Node/TypeScript, C#, Rust, monorepo, docs-only, no-test,
target-advancing, offline-local, research-artifact, and workflow cases without
target-repository Python dependencies.

Token accounting uses provider measurements when available and records unavailable
rather than estimating. The checked controlled comparator must preserve acceptance,
authority, route, budget, and seed while showing at least 30 percent lower input
tokens for the indexed/reuse path. That bounded observation is not a universal
superiority claim.

## Activation order

The checked-in manifest always has `execution_authorized: false`. A trusted external
host must perform these steps in order:

1. Authenticate the exact manifest, plan, candidate base, V3 predecessor and its
   qualification receipt, candidate commit/tree/content, request, and repository.
2. Verify a distinct independent review signature over the exact candidate.
3. Verify a distinct frozen-host signature that attests clean, bytecode-free,
   immutable read-only custody and exact tool identities.
4. Verify a distinct issuer signature over the complete bundle.
5. Atomically consume the globally unique nonce in host-owned storage, keyed by the
   nonce alone, authenticate the signed reservation receipt, and only then return one
   typed maximum-15-minute capability. A restarted process must freshly reverify the
   activation and the same receipt; it must not consume the nonce again.

The repository contains no signing key and no authoritative nonce store. Process-local
capability seals detect accidental or ordinary caller forgery but are not isolation from
hostile code in the same interpreter. Hard deadline enforcement, global competing-run
exclusion, and effect idempotency remain obligations of the authenticated external host
and adapter. The generated PowerShell rehashes its absolute client path immediately
before each use, but does not hold an executable handle across hash and launch; preventing
a concurrent replacement is part of that immutable host-custody obligation. The local
collector writes only a qualification-preparation packet and an explicitly
non-executable unsigned template outside the candidate worktree:

```powershell
powershell -NoProfile -File scripts\Collect-V4ActivationEvidence.ps1 `
  -OutputDirectory C:\absolute\outside-repository\v4-evidence
```

`-AllowDirty` is diagnostic only and forces `qualification_eligible: false`.
The collector replaces ambient Python path variables with the exact candidate source
and repository roots, proves the imported package path in an isolated bootstrap,
drains stdout and stderr concurrently, and bounds focused validation to 180 seconds
by default. `-FocusedTestTimeoutSeconds` may reduce that diagnostic bound but cannot
turn a timeout into qualification.

For pull requests, Linux unit tests retain GitHub's synthetic merge-result checkout to
exercise integration safety. Windows unit tests pin the immutable event head because they
exercise this collector's one-direct-child provenance invariant; that lane never infers a
parent from a merge commit.

## Remaining external gates and rollback

Independent signatures, frozen read-only host custody, the global nonce
compare-and-swap, credentials, protected merge, deployment, spending, and
production mutation are not satisfied or authorized by these files. The local
authority envelope expires at `2026-12-31T23:59:59Z` and permits only bounded
inspection, candidate editing, local tests, and evidence preparation; it explicitly
denies push, merge, credentials, payment, deployment, protected merge, and
production mutation.

Rollback is a normal revert of the unmerged candidate or closure of its draft pull
request. Preserve the V3 correction, source intake, losing designs, adverse tests,
benchmark comparators, court records, and consumed nonces. Never rewrite an expired
or failed bundle to make it appear fresh.
