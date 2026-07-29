# Phase 3 item 4 primary-source register

- Retrieval date: `2026-07-29`
- Case: `P3-OBSIDIAN-VIEWS-004`
- Explorer/Clerk: `/root/item4_explorer`
- Exact implementation base:
  `7e26a56eab5fe79f075cccc57a6ff0a01fb9ef9a`
- Reverification result: the official repository heads and content receipts already
  pinned by `PHASE1_PRIMARY_SOURCE_REGISTER.md` remain exact

This register narrows the previously admitted Obsidian and JSON Canvas sources to
the facts required by Phase 3 item 4. It does not silently expand documentation
reuse rights or claim runtime compatibility.

## `P3I4-SRC-OBSIDIAN-BASES`

- Publisher: Obsidian
- Official documentation repository:
  `https://github.com/obsidianmd/obsidian-help`
- Pin: `29e89022c6aeb0a9e9971b6f0c98733dbc2eb716`
- Retrieval head reverified: exact
- Primary locators:
  - `https://obsidian.md/help/bases`
  - `https://obsidian.md/help/bases/syntax`
- Pinned source files and Git blob IDs:
  - `en/Bases/Introduction to Bases.md`:
    `abb2b993659c5066a24cc74a74544914c53088d8`
  - `en/Bases/Bases syntax.md`:
    `9a072e3a8138bc961c67b1dade0c3385ae32736c`
- Preserved content SHA-256 receipts:
  - introduction:
    `3cfa5fdd36ed75fe7999f88d1c6fd120ca52058f53517d12e2b5b3b0e136f978`
  - syntax:
    `7fabd5f8fc3dadc45cdac2cac687016e9fdd9bc5e97f6879ef6beb4d26aac8e7`
- License: `NOASSERTION`; the official help repository has no detected root license
- Disposition: `adapt`

Atomic admitted claims:

1. A `.base` file is valid YAML describing filters, formulas, property display
   configuration, summaries, and views.
2. A Base defaults to vault-wide files; exact global filters are therefore required.
3. Note properties come from Markdown frontmatter.
4. A core table view can select a fixed property order.

Counterclaims and limits:

1. The pinned source publishes no numbered Base file-format version.
2. The pinned source publishes no machine-readable Base schema.
3. Bases can expose editable note properties; generated files are not a read-only UI.
4. Vault-global property typing and runtime behavior are application concerns not
   reproduced in this slice.
5. Only abstract syntax facts are used. No expressive documentation example or
   template is copied because reuse rights remain unresolved.

## `P3I4-SRC-OBSIDIAN-CANVAS-HELP`

- Publisher: Obsidian
- Repository pin:
  `29e89022c6aeb0a9e9971b6f0c98733dbc2eb716`
- Pinned file: `en/Plugins/Canvas.md`
- Git blob: `c08e136500b79760adfb78d1051c27c96c8015f3`
- Content SHA-256:
  `1544d5de218c9a84bb44666c6a19e35b6635532c0a853cd3721f2f6912207c75`
- Locator: `https://obsidian.md/help/plugins/canvas`
- License: `NOASSERTION`
- Disposition: `adapt` for the factual claim that Obsidian stores `.canvas` files
  using JSON Canvas; documentation reuse remains blocked

## `P3I4-SRC-JSON-CANVAS-1`

- Publisher: Obsidian.md / JSON Canvas
- Locator: `https://jsoncanvas.org/spec/1.0/`
- Official repository:
  `https://github.com/obsidianmd/jsoncanvas`
- Pin and reverified head:
  `456f843cb293df4f4ab1763e22ccb46a80b307c8`
- Version: JSON Canvas 1.0, dated `2024-03-11`
- Pinned specification file: `spec/1.0.md`
- Git blob: `a463e34c90fadf7981e54a73a865a7866fa5cc61`
- Specification SHA-256:
  `41d75005394f3ed43a53031ff9d07c5d49c47e897971e7afb2972cc8af67469a`
- License file Git blob: `910b7f7ff2fb14afc2a8eed8c730489096f34e02`
- License SHA-256:
  `5dc8a82e5f93308e31b729297b027d1aafbaae3b9b73696371a975a3b4a2cd5d`
- License: MIT, copyright 2024 Obsidian.md
- Disposition: `adapt`

Atomic admitted claims:

1. A Canvas is JSON with `nodes` and `edges` arrays.
2. Text and file nodes have unique string IDs and integer geometry.
3. File nodes contain system-relative file paths.
4. Node array order defines z-order.
5. Edges reference node IDs.

Counterclaims and limits:

1. The prose specification publishes no official JSON Schema.
2. A structurally valid file node does not prove how a `.base` file renders in
   Obsidian.
3. Format conformance does not prove layout usefulness, live refresh, or application
   compatibility.

## Blocking evidence obligations

- A version-pinned Obsidian runtime has not parsed or rendered the generated Bases
  or Canvas.
- Automatic refresh, repository-as-vault behavior, watchers, plugins, and Sync are
  Phase 3 item 5 or later.
- No usefulness or superiority evaluation is admitted without sealed held-out tasks
  and multiple pinned comparators.
