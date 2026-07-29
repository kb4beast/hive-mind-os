# Phase 3 item 5 source register

## Scope

This register adds only the runtime provenance needed to test local Obsidian refresh.
It reuses the already-admitted format and local-vault claims in
`PHASE1_PRIMARY_SOURCE_REGISTER.md` and `PHASE3_ITEM4_SOURCE_REGISTER.md`; it does
not duplicate their claim extraction.

## Reused primary evidence

- Inspected/retrieved: `2026-07-29T19:55:00Z`

| Evidence | Pin | Reused claim |
|---|---|---|
| Obsidian help: `How Obsidian stores data.md` | help repository commit `29e89022c6aeb0a9e9971b6f0c98733dbc2eb716`, blob `331f98bb60d699e6044b6aadb9bea9e36b53350b`, SHA-256 `add03088da7be4ab2fd364918c17b006d646eafedffada5440db83217f6942e6` | A vault is a local folder; Obsidian watches external file changes; `.obsidian` holds vault configuration. |
| Obsidian help: `Manage vaults.md` | same commit, blob `0980d45c89b86efb08334bf2bb9fdf7ac2974eab`, SHA-256 `c57c9d0d93ce60b805a0419584ff3aa7ecd2a35315e6c79c81207aab60585ee3` | An existing folder can be opened as a vault. |
| Obsidian help: `Accepted file formats.md` | same commit, blob `4bd8c9066cf145b5fc064b909c00709c7ab7f089`, SHA-256 `95ede78937600de68ad15ade8cf5044f05261eac9f72187c2880f6a7c71b517e` | Markdown, Base, and Canvas are core file formats. |

The help repository has no detected root reuse license. License remains
`NOASSERTION`; only factual behavior is abstracted.

## Runtime pin

- Inspected/retrieved: `2026-07-29T20:00:00Z`

- Official release: `https://github.com/obsidianmd/obsidian-releases/releases/tag/v1.12.7`
- Release ID: `298621467`
- Published: `2026-03-23T15:56:19Z`
- Official changelog:
  `https://obsidian.md/changelog/2026-03-23-desktop-v1.12.7/`
- Installed executable:
  `C:\Program Files\Obsidian\Obsidian.exe`
- File version: `1.12.7`; product version: `1.12.7.0`
- Executable SHA-256:
  `fb6b2133c21ef7051c41f66d5c06f0e69162febfbb3f838a3556d54d13304b69`
- Core archive SHA-256:
  `2b2483b2e1246772e0d25367ec055cbc5047ea2f0091b667c35656678f86d712`
- Authenticode: `Valid`, signer `Dynalist Inc`, thumbprint
  `69b4a9ab8355237555686ca7cd67f6763b0f7eaf`
- Host: Microsoft Windows 11 Home `10.0.26200`, x64

The release page, changelog, and installed runtime are reference/execution-only
evidence. No page text or application binary is redistributed. Their reuse license
is recorded as `NOASSERTION`; only factual version, signature, and observed behavior
are used.

## Atomic claims and limits

1. Official documentation supports an expectation of automatic local-file refresh,
   but supplies no latency service level.
2. Runtime receipts, not documentation, establish the observed item 1 and item 3
   same-pane refresh, Base recomputation, and Canvas rendering.
3. The first runtime attempt exposed an undocumented Base canonicalization side
   effect. It is preserved as a failed run and directly caused the scalar-rendering
   repair.
4. Any passing run is version-, host-, and fixture-specific. It does not establish
   remote Git synchronization, Sync behavior, other Obsidian versions, production
   readiness, usefulness, or superiority.
5. The fourth run is the only promotable passing receipt. The earlier passing run is
   retained as superseded because its subject predates final production hardening.
   The two failed receipts remain controlling regression evidence.
