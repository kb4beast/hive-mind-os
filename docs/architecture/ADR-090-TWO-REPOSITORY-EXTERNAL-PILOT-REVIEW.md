# Independent review of ADR-090

Observed on `2026-09-21` against the working tree based on
`213392dbf74d879a02fb2c613f809a3eb83cf31b`.

## Identities and scope

- Builder/Orchestrator: `/root`.
- Independent Curator/Cross-Examiner: `/root/two_target_pilot_packet`, using
  `gpt-5.6-luna` at low reasoning effort.
- Reviewed: ADR-090, the N32 prose and launcher prompt, status and acceptance
  receipts, the regenerated plan artifacts, and the focused pilot regression test.
- The reviewer made no repository edits.

## Cross-examination

The first review found two wording risks: repository selection could be mistaken for
host-issued authority, and a typed prerequisite test could be mistaken for runtime
qualification. The builder changed ADR-090 to state that selection is not authority
evidence and that the test proves schema compatibility only.

The second review found no remaining contract or generated-artifact blocker. N32
still requires two admitted targets, isolated state, scoped authority, runtime
receipts, an independently admitted N30 candidate, rollback evidence, and a real
72-hour observation. Roblox remains available through N26/N27 but is not claimed by
the current release scope.

## Disposition

`ADOPT / CLEAR` for the contract change. Production readiness remains blocked on the
operational receipts listed in `docs/execution/EXTERNAL_PILOT_RECEIPT.md`.
