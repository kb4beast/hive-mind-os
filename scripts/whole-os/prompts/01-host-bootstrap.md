Execute the Whole-OS host-bootstrap stage end to end. Read `AGENTS.md`,
`docs/plan/whole-os-tournament-2026-09-13-IMPLEMENTATION_PROMPT.md`,
`docs/execution/WHOLE_OS_SERVICE.md`, and the N28 contract. Work directly; do not
spawn agents, stop at planning, or ask routine questions.

Build or repair the concrete trusted launcher, sealed service configuration, and
real adapter composition needed for this checkout to invoke `WholeOSService` using
the installed non-interactive Codex CLI for routine reversible repository work.
Keep credentials outside repository configuration. Inspect available tools and
reuse existing production adapters. Run focused tests and the repository gate
appropriate to changed bytes. Commit changes on the current `codex/` branch, push
them, and create or update one scoped PR when credentials allow.

The stage is complete only when a fresh process can execute the trusted launcher
against a real admitted repository and persist a non-synthetic startup receipt.
Permission in the operator request authorizes this bounded work but does not prove
an unavailable credential, external signature, or runtime result. Record any such
missing input as a typed blocker and recommend a low-frequency retry.
