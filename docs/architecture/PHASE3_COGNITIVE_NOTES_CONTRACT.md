# Phase 3 item 3 cognitive notes contract

## Scope and authority

The item-2 public release store is the only cognitive source. The canonical
Foundation database remains private and authoritative. Cognitive Markdown is a
deterministic, nonauthoritative projection.

| Operation | Required authority | Mutation |
| --- | --- | --- |
| Compile/check desired cognitive tree | explicit local read access | none |
| Publish cognitive tree | authentic `foundation.projection.write` intersection | generated namespace and external protected receipts only |

Successful output, apparent usefulness, note contents, and stored authority
references never grant authority.

## Admission and mapping

Every input must be a verified `hive-public-memory-envelope/v1` for the exact tenant,
repository, and repository identity. The source must remain a released,
nonquarantined `memory-record-v1` with `sensitivity=safe-public`, null protected
content, null retrieval receipt, and release subject digest equal to the source
digest.

Each admitted record maps exactly once:

- `opportunity` to idea;
- `semantic`, `procedural`, and `not-applicable` to evidence;
- `decision`, `counterfactual`, and `governance` to court;
- `working`, `episodic`, and `prospective` to run;
- `social` to agent; and
- `evaluation` and `resource` to telemetry.

Unknown, extra, unsupported, or ambiguously mapped kinds fail closed.

## Identity and properties

The stable record-note ID and filename depend only on the versioned note identity
domain and immutable released source record ID. HOME depends only on its versioned
identity domain and repository identity digest. Identity excludes timestamps,
status, source cursor, content digest, heading, and path.

Every record note carries strict, bounded properties for:

- schema, generator, and mapping versions;
- note kind, stable note ID, stable subject/memory ID;
- tenant, repository, and repository identity digest;
- source record/schema/digest/previous digest and source cursor;
- mission, run, step, actor, and owner;
- observed/recorded times, status, confidence, and freshness;
- previous/supersedes IDs;
- source, claim, evidence, court, code-receipt, generation, contradiction, and
  relation references;
- independent release decision and decider;
- `sensitivity=safe-public`;
- `is_generated=true`; and
- `is_authoritative=false`.

HOME contains the same scope/version markers, total admitted record count, and one
integer count for each of the six domain kinds. It contains no source ID list,
private omission count, absolute path, attempt time, lease, authority credential,
or private error.

## Rendering and publication

Output is UTF-8 without BOM, LF-only, deterministic, and final-newline terminated.
Properties and files use fixed ordering. Untrusted values are JSON-quoted YAML
scalars or indented canonical JSON; they cannot select headings, paths, links,
embeds, HTML, scripts, or commands.

The complete desired tree is bounded before publication, and the public release
store is bounded to 512 MiB before decode. The manifest commits exact paths, source
IDs/digests, and content digests. Publication stages deterministic desired bytes in
external protected state, verifies the full prior receipt chain and exact
expected-prior digests, installs files without overwriting a late writer, and
publishes the manifest last. A valid exact ownership receipt is required before
updating a prior tree.

Transaction-ID-qualified `.cognitive-prior-*` and `.cognitive-next-*` siblings may
exist only during the per-file atomic install window. They are reserved recovery
artifacts, not desired-tree files. Only an exact protected journal may authorize
their recovery; a mismatch is a typed conflict. Successful publication and normal
check state contain none.

On Windows, publication holds no-delete handles over the managed root, destination
parent, and prepared file for the final no-overwrite operation. A concurrent
junction or source move therefore conflicts before the hardlink. Cross-platform
guarantees cover ordinary destination edits and journal-governed recovery; an
uncooperative process deliberately renaming reserved internal artifacts is not
claimed as a malicious-writer filesystem transaction.

Check mode is read-only: it creates no repository or protected-state path. Missing,
edited, renamed, linked, hardlinked, unmanaged, oversized, corrupt, or racing state
returns drift, conflict, or failure without overwriting observed bytes.

On restart, an older sealed transaction is independently verified and completed
before a newly observed public snapshot is projected. Each committed snapshot has
its own receipt and source cursor; recovery never claims the older snapshot was the
newer one.

## Compatibility and explicit limits

The item-1 `generated` namespace, item-2 release store, frozen root/package APIs,
root CLI parsers, and 17/7/3 prior schemas remain unchanged. Item 3 is an opt-in
module, separate namespace, catalog, and protected-state protocol.

Telemetry notes contain released metadata only. No canonical token, cost, provider,
invoice, trace, effectiveness, or usage-accounting claim is made. No public prose
body, court verdict, agent definition/health, or protected content is inferred.

Bases, Canvas, Obsidian refresh/support, federation, self-host recursion,
Inbox/import, plugins, watchers, Sync, retrieval, encryption/KMS, cleanup/deletion,
activation, usefulness, production readiness, and superiority are outside this
contract.
