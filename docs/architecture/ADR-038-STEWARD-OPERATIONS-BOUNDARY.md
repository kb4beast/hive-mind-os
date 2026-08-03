# ADR-038: Steward operations boundary

- Status: adapted bounded record
- Phase: 5F

Steward health, maintenance, recovery, evidence-integrity, and interruption records must fail closed
on unknown observations and must separate proposed reversible actions from executed receipts. The
current intake remains degraded, `not-run`, and authority-free. A runbook may describe deterministic
checks, but it cannot manufacture recovery success, dependency mutation authority, or readiness.

Future operational outputs are additive schema versions. Rollback reverts those versions without
deleting evidence. Optimizer eligibility remains blocked until real authorized exercises pass.
