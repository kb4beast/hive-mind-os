# ADR-091 independent court record

- Architect: `/root/readiness_scope_architect`, `gpt-5.6-luna`, low.
- Cross-examiner: `/root/readiness_scope_cross_exam`, `gpt-5.6-luna`, low.
- Judge: `/root/readiness_scope_judge`, `gpt-5.6-luna`, low.
- Implementation Curator: `/root/claim_scope_curator`, `gpt-5.6-luna`, low.
- Disposition: `adapt`.

The court required a closed scope enum, explicit scope in every receipt and
manifest, monotonic burden, exact candidate/host/authority/target/runtime/window/
rollback bindings, independent qualification, strict legacy defaults, and negative
tests for omission, escalation, mismatch, substitution, incomplete windows,
rollback, and stale evidence. N30 remains the superiority/full-autonomy gate.

The bounded result is useful operational evidence but is not evidence of broad
hostile-repository support or benchmark superiority. A future appeal requires new
pinned evidence or a versioned challenger and cannot lower the evidence burden.

The implementation Curator found two brittle PowerShell test slices, which were
corrected before promotion. The replay then passed all 11 pipeline tests, including
PowerShell parsing, bounded/full stage selection, strict defaults, retained-state
mismatch handling, and direct N30/N31 scope guards. The final Curator verdict was
`ADAPT` with no remaining blocking implementation defect. Production-candidate,
target/runtime, authority, and 72-hour pilot evidence remain external blockers.
