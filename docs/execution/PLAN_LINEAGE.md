# Authenticated Plan Lineage

`PLAN-CORE-100` adds an external, subject-neutral plan lineage. It does not
replace or reinterpret `.autopilot/plan.json`, and a generated plan is inert
data. Generation never grants credentials, host trust, an execution lease, or
permission for an external effect.

## Identity

`GenerationRecord` derives `generation_id` from canonical JSON containing all
of these bindings:

- request and objective digests;
- typed subject identity, optional repository identity, and target;
- parent generation plus the exact parent commit and tree for repositories;
- node-mapping and complete source-inventory digests;
- standard version and digest, compiler digest, and complete plan digest.

The identity is nested canonical JSON, not a flattened concatenation. A changed
field therefore creates a new generation rather than aliasing an old one.
`GenerationLineage.register` accepts an exact repeat idempotently. It rejects a
missing parent, request or target substitution, cross-subject lineage, standard
downgrade, and reuse of one flat plan fingerprint across subjects. A caller must
also use `require_expected` against its current request and observed target
snapshot before it trusts a generation.

`PinnedArtifact` accepts complete immutable bytes and their raw SHA-256. A path
or detached digest is not an input artifact. `PlanGenerator.generate` consumes
the complete portable plan, mapping, source, standard, and compiler bytes. It
returns `GeneratedPlan`, whose `ActivationMaterial` contains both complete
canonical plan bytes and complete external-manifest bytes.

## External activation boundary

The generated manifest explicitly requires a host signature, a key distinct
from repository content, and prohibition of a repository-stored signature. The
repository does not implement that signature, nonce ledger, or host trust
decision. An external host must authenticate the full bytes, bind a one-run
nonce and deadline, and resolve concurrent activation with compare-and-swap.
Failure at that boundary must stop; no legacy-plan fallback exists.

Generation is not a restart or resume API. Persistence, activation leases, and
resume identities are separate contracts. The only repetition guaranteed here
is exact generation identity replay.

## Receipt carry-forward

`carry_forward_receipts` applies the following rules on one exact subject:

| Node relationship | Result |
| --- | --- |
| Same node and same contract digest | Exact receipt bytes carry forward |
| Same node and changed contract digest | Requalification required |
| Removed node | Receipt retained as historical |
| New node | No inherited completion |
| Receipt from another subject | Contract violation |

Receipts authenticate their own immutable bytes. Missing, duplicate, or
contract-mismatched receipts cannot be silently promoted.

## Traceability and history

`TraceabilityDisposition` and `validate_traceability` require exact row coverage,
one disposition per source row, and an explicit target acceptance criterion.
`verify_historical_bytes` compares raw bytes with the expected SHA-256 and never
parses the historical plan to assign it a new meaning.

The focused checks are:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -B -m unittest tests.test_plan_lineage tests.test_plan_generation -v
```
