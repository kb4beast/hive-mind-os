# Historical execution evidence archive

This branch preserves the 968 tracked execution-evidence files removed from `main`
by P5.1 on 2026-08-03. It was cut from
`b065dc20bbc7eaefd2d1a9a91d4f52d284918c48` before the removal.

The preserved roots are:

- `evidence/audits/`
- `evidence/benchmarks/`
- `evidence/experiments/`
- `evidence/handoffs/`
- `evidence/live/`
- `evidence/pit/`

These bytes are historical receipts and are retained intact. New runtime receipts do
not belong on this branch. Current courtroom, governance, and source-provenance
records remain on `main` under `evidence/`.
